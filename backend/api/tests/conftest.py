"""Configuración compartida de la suite de tests de la API.

El rate limiting (issue #61) se desactiva por defecto durante los tests: las
suites existentes disparan muchas peticiones seguidas con el mismo TestClient
(misma IP) y de otro modo tropezarían con el límite. El test que sí verifica
el rate limiting (test_rate_limiting.py) lo reactiva explícitamente vía
monkeypatch + reload, siguiendo el mismo idiom que test_cors.py.
"""
import os

# Asignacion explicita, no setdefault (issue #69): si el desarrollador
# exporto el .env del repo al shell antes de correr pytest, RATE_LIMIT_ENABLED
# ya vale "true" en os.environ y setdefault() no haria nada -- el rate limiter
# quedaria activo y las suites de endpoints (muchas requests seguidas desde la
# misma IP) fallarian de forma intermitente con 429. test_rate_limiting.py lo
# reactiva explicitamente via monkeypatch + reload cuando lo necesita.
os.environ["RATE_LIMIT_ENABLED"] = "false"

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


@pytest.fixture(autouse=True)
def _cache_de_respuestas_vacio():
    """El cache de respuestas del servidor (api/cache_respuestas.py) es por
    proceso y sobrevive entre tests: sin vaciarlo, un test que parchea
    _conexion para simular un fallo recibiría la respuesta que otro test ya
    dejó guardada para la misma URL."""
    from api.cache_respuestas import CACHE

    CACHE.limpiar()
    yield
    CACHE.limpiar()
