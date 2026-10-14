"""Disparo del refresco periódico de clima (ADR 0027, A2 del ADR 0018).

El endpoint no corre `cargar_clima.py` in-process: ADR 0018 ya deja
constancia de que no existe un paquete compartido entre `backend/api` y
`backend/ingestion` (ver docstring de `backend/api/idoneidad.py`), y el
loader asume ejecutarse como script standalone desde su propio directorio
(`from db import get_connection`, import de paquete relativo implícito).
En vez de forzar ese acople, se lanza como subproceso -- mismo patrón que
`INGESTION_DIR` ya usa en `main.py` para ubicar artefactos del modelo.

Mismo esquema de autenticación que `alertas.py`: Bearer contra una
variable de entorno comparada con `secrets.compare_digest`, pero con su
propio token (`CLIMA_REFRESCO_TOKEN`) -- un token filtrado de una
superficie no debe dar acceso a la otra.
"""

from __future__ import annotations

import logging
import os
import secrets
import subprocess
import sys
from pathlib import Path

INGESTION_DIR = Path(__file__).parent.parent / "ingestion"
CARGAR_CLIMA_SCRIPT = INGESTION_DIR / "cargar_clima.py"

_registro = logging.getLogger("uvicorn.error")


def extraer_bearer(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    partes = authorization.split(None, 1)
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return None
    token = partes[1].strip()
    return token or None


def comprobar_token_refresco(authorization: str | None) -> tuple[int, str] | None:
    """None si autorizado; si no, (status, detail). Lee el env en cada llamada."""
    esperado = os.environ.get("CLIMA_REFRESCO_TOKEN") or ""
    if esperado.strip() == "":
        return (
            503,
            "Refresco de clima no configurado (CLIMA_REFRESCO_TOKEN ausente).",
        )
    recibido = extraer_bearer(authorization)
    if recibido is None:
        return (401, "No autenticado")
    try:
        coincide = secrets.compare_digest(recibido, esperado)
    except (TypeError, ValueError):
        coincide = False
    if not coincide:
        return (401, "No autenticado")
    return None


def ejecutar_refresco_clima() -> None:
    """Corre cargar_clima.py con los defaults del script (2018-año en curso).

    Pensada para BackgroundTasks: FastAPI la corre en threadpool tras
    responder, así que el rate-limit backoff de Open-Meteo (minutos, ver
    cargar_clima.py) no bloquea al worker de la API. Un fallo queda en el
    log del backend -- no reintenta ni notifica por sí sola; el workflow
    de GitHub Actions que dispara el endpoint solo ve el 202 de aceptación,
    no el resultado de la carga (ver ADR 0027).
    """
    resultado = subprocess.run(
        [sys.executable, str(CARGAR_CLIMA_SCRIPT)],
        cwd=INGESTION_DIR,
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        _registro.error(
            "Refresco de clima falló (código %s): %s",
            resultado.returncode,
            resultado.stderr.strip(),
        )
        return
    _registro.info("Refresco de clima OK: %s", resultado.stdout.strip().splitlines()[-1:])
