"""Cache de respuestas del servidor (api/cache_respuestas.py).

Las pruebas del LRU no tocan Postgres. Las de los endpoints parchean
_conexion para contar cuántas veces se abre: un acierto no debe abrir
ninguna conexión y debe anunciar en max-age solo el tiempo que le queda a la
entrada, nunca más que el TTL del endpoint.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from api import cache_respuestas  # noqa: E402
from api.cache_respuestas import CacheRespuestas, serializar_json  # noqa: E402
from api.main import CACHE_TTL_HISTORICO, app  # noqa: E402


def test_guarda_y_devuelve_el_tiempo_restante():
    cache = CacheRespuestas(max_bytes=1000)
    cache.guardar("a", b"{}", ttl=60)
    cuerpo, restante = cache.obtener("a")
    assert cuerpo == b"{}"
    assert 1 <= restante <= 60


def test_entrada_caducada_no_se_devuelve(monkeypatch):
    reloj = [100.0]
    monkeypatch.setattr(cache_respuestas.time, "monotonic", lambda: reloj[0])
    cache = CacheRespuestas(max_bytes=1000)
    cache.guardar("a", b"{}", ttl=10)
    reloj[0] = 110.0
    assert cache.obtener("a") is None


def test_respeta_el_techo_de_bytes_descartando_la_menos_usada():
    cache = CacheRespuestas(max_bytes=10)
    cache.guardar("a", b"1234", ttl=60)
    cache.guardar("b", b"1234", ttl=60)
    cache.obtener("a")  # "b" pasa a ser la menos usada
    cache.guardar("c", b"1234", ttl=60)
    assert cache.obtener("b") is None
    assert cache.obtener("a") is not None
    assert cache.obtener("c") is not None


def test_cuerpo_mayor_que_el_techo_no_se_guarda():
    cache = CacheRespuestas(max_bytes=3)
    cache.guardar("a", b"1234", ttl=60)
    assert cache.obtener("a") is None


def test_apagado_no_guarda_nada():
    cache = CacheRespuestas(max_bytes=1000, habilitado=False)
    cache.guardar("a", b"{}", ttl=60)
    assert cache.obtener("a") is None


def test_serializa_igual_que_jsonresponse():
    from starlette.responses import JSONResponse

    cuerpo = {"ñ": "á", 2019: [1.5, None, True], "x": (1, 2)}
    assert serializar_json(cuerpo) == JSONResponse(cuerpo).body


def test_serializa_tipos_que_json_no_conoce():
    from datetime import date
    from decimal import Decimal

    assert json.loads(serializar_json({"d": date(2023, 1, 2), "n": Decimal("1.5")})) == {
        "d": "2023-01-02",
        "n": 1.5,
    }


def _conexion_contada():
    """_conexion falso que cuenta aperturas; listar_virus se parchea aparte."""
    mock_cx = MagicMock()
    mock_cx.return_value.__enter__.return_value = MagicMock()
    mock_cx.return_value.__exit__.return_value = False
    return mock_cx


def test_segundo_request_sale_del_cache_sin_abrir_conexion():
    series = [{"virus": "vsr", "metrica": "detecciones", "unidad": "n",
               "primer_anio": 2018, "ultimo_anio": 2023, "semanas_con_dato": 10}]
    mock_cx = _conexion_contada()
    client = TestClient(app)
    with patch("api.main._conexion", mock_cx), patch(
        "api.main.listar_virus", return_value=series
    ):
        primera = client.get("/api/respiratorios/virus")
        segunda = client.get("/api/respiratorios/virus")
    assert mock_cx.call_count == 1
    assert primera.content == segunda.content
    assert primera.headers["cache-control"] == f"public, max-age={CACHE_TTL_HISTORICO}"
    max_age = int(re.search(r"max-age=(\d+)", segunda.headers["cache-control"]).group(1))
    assert 1 <= max_age <= CACHE_TTL_HISTORICO


def test_respuesta_degradada_no_se_guarda():
    mock_cx = _conexion_contada()
    client = TestClient(app)
    with patch("api.main._conexion", mock_cx), patch(
        "api.main.listar_virus", return_value=[]
    ):
        client.get("/api/respiratorios/virus")
        respuesta = client.get("/api/respiratorios/virus")
    assert respuesta.json()["disponible"] is False
    assert mock_cx.call_count == 2
