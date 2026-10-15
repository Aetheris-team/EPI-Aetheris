"""Piezas compartidas por las rutas de la API: Cache-Control, el cache de
respuestas del servidor y la traducción de un fallo de Postgres a una
respuesta HTTP (degradación a disponible=false, 503 o 500).

Viven aparte de main.py para que los routers de api/rutas/ las usen sin
importar main (que crea la app y lee el entorno al importarse). No leen
variables de entorno: recargar main en los tests no las afecta.
"""

from __future__ import annotations

import logging
from typing import NoReturn

import psycopg2
from fastapi import HTTPException, Response
from psycopg2 import InterfaceError, OperationalError
from psycopg2.errors import UndefinedTable

from .cache_respuestas import CACHE as CACHE_RESPUESTAS, serializar_json


# --- Cache-Control (informe de rendimiento externo) -------------------------
# Cabeceras HTTP estándar: el navegador reutiliza la respuesta sin volver a
# pedirla. Los mismos TTL gobiernan el cache del servidor (más abajo), así
# que ninguna respuesta sale más vieja de lo que su max-age ya admitía. TTL
# segun que tan seguido cambia el dato real -- ninguno de estos endpoints
# escribe en caliente:
#   - CACHE_TTL_HISTORICO: series ya cargadas en Postgres que solo cambian
#     con una corrida nueva de ingesta (cargar_ira.py, etc.).
#   - CACHE_TTL_COMPUTO: capas espaciales/de cómputo (idoneidad, presión,
#     riesgo-nacional) recalculadas en cada request -- TTL más corto porque
#     son las más caras y las que más se beneficiarían de un cambio de
#     metodología sin esperar una hora completa de cache.
#   - CACHE_TTL_ALERTAS: alertas de campo (ADR 0013). Las redacta y apaga
#     el equipo a mano; el valor de la vista es "¿hay algo vigente ahora?".
#     TTL corto para que un cambio se refleje en el minuto, no en la hora.
CACHE_TTL_HISTORICO = 3600
CACHE_TTL_COMPUTO = 900
CACHE_TTL_ALERTAS = 60


def cache_control(response: Response, max_age: int) -> None:
    response.headers["Cache-Control"] = f"public, max-age={max_age}"


# --- Cache de respuestas en el servidor (backend/api/cache_respuestas.py) ----
# Lo de arriba solo evita que el MISMO navegador repita la petición; cada
# visitante nuevo volvía a pagar la consulta y el cálculo. Los endpoints de
# solo lectura consultan aquí primero con una clave armada con sus parámetros
# ya validados (no con la URL cruda: un parámetro basura no debe crear otra
# entrada) y guardan el cuerpo serializado con el mismo TTL de su
# Cache-Control. Las respuestas de error y las degradadas
# (disponible=false) no se guardan.
def _json_cacheable(cuerpo: bytes, max_age: int) -> Response:
    return Response(
        content=cuerpo,
        media_type="application/json",
        headers={"Cache-Control": f"public, max-age={max_age}"},
    )


def desde_cache(clave) -> Response | None:
    acierto = CACHE_RESPUESTAS.obtener(clave)
    if acierto is None:
        return None
    cuerpo, restante = acierto
    return _json_cacheable(cuerpo, restante)


def cachear(clave, ttl: int, cuerpo) -> Response:
    serializado = serializar_json(cuerpo)
    CACHE_RESPUESTAS.guardar(clave, serializado, ttl)
    return _json_cacheable(serializado, ttl)


# Degradación elegante (issue #84): tabla ausente / sin filas no es un
# fallo de conexión. Mismo contrato que /api/riesgo-nacional (#72):
# 200 { disponible: false, motivo } para que el frontend muestre un aviso
# explícito. Un OperationalError/timeout sí es un problema de servicio.
def es_tabla_ausente(exc: BaseException) -> bool:
    """True si Postgres reporta relación inexistente (SQLSTATE 42P01)."""
    actual: BaseException | None = exc
    vistos: set[int] = set()
    while actual is not None and id(actual) not in vistos:
        vistos.add(id(actual))
        if isinstance(actual, UndefinedTable):
            return True
        if getattr(actual, "pgcode", None) == "42P01":
            return True
        actual = actual.__cause__ or actual.__context__
    return False


def es_fallo_conexion(exc: BaseException) -> bool:
    return isinstance(exc, (OperationalError, InterfaceError, TimeoutError))


_registro = logging.getLogger("uvicorn.error")


def fallo_base_datos(exc: BaseException) -> NoReturn:
    """Registra la causa y responde 503 (conexión) o 500 (resto).

    Al cliente nunca se le devuelve la causa. En el registro, mismo criterio
    que /health: un error de Python (KeyError, TypeError...) va con su traza
    completa, porque es un fallo del código de la consulta y sin ella no se
    puede depurar; un error que reporta el servidor (con SQLSTATE) o un
    OperationalError, con la primera línea de su mensaje; cualquier otro error
    de psycopg2 (un DSN mal formado, por ejemplo), solo con el nombre de su
    clase, porque su mensaje puede repetir la URL con la clave.
    """
    if not isinstance(exc, (psycopg2.Error, TimeoutError)):
        _registro.error(
            "consulta: error inesperado (%s)", type(exc).__name__, exc_info=exc
        )
    else:
        mensaje = str(exc).strip()
        con_mensaje = mensaje and (
            getattr(exc, "pgcode", None) or isinstance(exc, (OperationalError, TimeoutError))
        )
        _registro.error(
            "consulta: fallo la base de datos (%s)%s",
            type(exc).__name__,
            f": {mensaje.splitlines()[0]}" if con_mensaje else "",
        )
    raise HTTPException(
        status_code=503 if es_fallo_conexion(exc) else 500,
        detail="Error de conexión a la base de datos",
    ) from exc


def respuesta_no_disponible(response: Response, motivo: str, aviso: str) -> dict:
    cache_control(response, CACHE_TTL_HISTORICO)
    return {"disponible": False, "motivo": motivo, "aviso": aviso}


def degradar_consulta(
    exc: BaseException, response: Response, motivo: str, aviso: str
) -> dict:
    """UndefinedTable → 200 disponible=false. Conexión → 503. Resto → 500."""
    if es_tabla_ausente(exc):
        return respuesta_no_disponible(response, motivo, aviso)
    fallo_base_datos(exc)
