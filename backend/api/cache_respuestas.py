"""Cache en memoria de respuestas JSON de solo lectura.

Las series que sirve la API solo cambian con una corrida de ingesta o un
despliegue, pero cada request las volvía a leer de Postgres, a recalcular
(M1-M4) y a serializar. Este cache guarda el cuerpo ya serializado durante el
mismo TTL que la respuesta declara en `Cache-Control`, así que no cambia la
frescura prometida: un cliente nunca recibe un dato más viejo que ese TTL,
porque el `max-age` que se envía en un acierto es el tiempo que le queda a la
entrada, no el TTL completo.

Solo stdlib, por proceso (Uvicorn corre con un worker, ver el comentario del
rate limiting en main.py). Nada se persiste. No se usa para /health, las
alertas de campo ni las cuentas: ahí la frescura o la sesión importan más que
el costo de la consulta.

API_CACHE_ENABLED=false lo apaga (cada request vuelve a calcular).
API_CACHE_MAX_BYTES acota la memoria: al pasarse se descartan las entradas
usadas hace más tiempo. Hay parámetros libres (p. ej. `anio` en las series
temporales), así que sin ese techo cualquiera podría llenar la memoria
variando la URL.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Hashable

from fastapi.encoders import jsonable_encoder

API_CACHE_ENABLED = os.getenv("API_CACHE_ENABLED", "true").lower() != "false"
API_CACHE_MAX_BYTES = int(os.getenv("API_CACHE_MAX_BYTES", str(32 * 1024 * 1024)))


def serializar_json(cuerpo: Any) -> bytes:
    """Mismos parámetros que starlette.responses.JSONResponse.render, para
    que el cuerpo sea idéntico byte a byte al que FastAPI producía.

    FastAPI pasa antes todo por jsonable_encoder, que recorre la respuesta
    entera y en las grandes cuesta más que el propio json.dumps. Aquí solo
    se usa si el cuerpo trae algo que json no sabe escribir (fechas,
    Decimal...)."""
    try:
        texto = json.dumps(
            cuerpo, ensure_ascii=False, allow_nan=False, indent=None, separators=(",", ":")
        )
    except TypeError:
        texto = json.dumps(
            jsonable_encoder(cuerpo),
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        )
    return texto.encode("utf-8")


class CacheRespuestas:
    """LRU acotado por bytes con caducidad por entrada. Seguro entre hilos:
    las path operations síncronas corren en el threadpool de FastAPI."""

    def __init__(self, max_bytes: int, habilitado: bool = True) -> None:
        self.max_bytes = max_bytes
        self.habilitado = habilitado
        self._entradas: OrderedDict[Hashable, tuple[bytes, float]] = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def obtener(self, clave: Hashable) -> tuple[bytes, int] | None:
        """(cuerpo, segundos que le quedan) o None si no hay entrada vigente."""
        if not self.habilitado:
            return None
        ahora = time.monotonic()
        with self._lock:
            entrada = self._entradas.get(clave)
            if entrada is None:
                return None
            cuerpo, expira = entrada
            if expira <= ahora:
                self._quitar(clave)
                return None
            self._entradas.move_to_end(clave)
            return cuerpo, max(1, math.ceil(expira - ahora))

    def guardar(self, clave: Hashable, cuerpo: bytes, ttl: int) -> None:
        if not self.habilitado or len(cuerpo) > self.max_bytes:
            return
        with self._lock:
            if clave in self._entradas:
                self._quitar(clave)
            self._entradas[clave] = (cuerpo, time.monotonic() + ttl)
            self._bytes += len(cuerpo)
            while self._bytes > self.max_bytes:
                self._quitar(next(iter(self._entradas)))

    def limpiar(self) -> None:
        with self._lock:
            self._entradas.clear()
            self._bytes = 0

    def _quitar(self, clave: Hashable) -> None:
        cuerpo, _ = self._entradas.pop(clave)
        self._bytes -= len(cuerpo)


CACHE = CacheRespuestas(API_CACHE_MAX_BYTES, habilitado=API_CACHE_ENABLED)
