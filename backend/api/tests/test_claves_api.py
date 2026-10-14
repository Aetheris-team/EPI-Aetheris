"""Claves de API con límites más altos (ADR 0025).

Mismo idiom que test_rate_limiting.py: se reactiva el rate limiting con
monkeypatch + importlib.reload(api.main), porque la configuración se lee en
import y conftest.py lo desactiva para el resto de la suite.
"""
import hashlib
import importlib
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from api.claves_api import identificar, parsear_claves  # noqa: E402
from api.tests.test_rate_limiting import CUERPO_ALERTA_MINIMO  # noqa: E402

CLAVE = "clave-de-prueba-no-real"
HUELLA = hashlib.sha256(CLAVE.encode()).hexdigest()
ORIGEN = "http://localhost:4321"


@pytest.fixture
def cliente(monkeypatch):
    """Anónimo: 3/min global, 2/min pesado. Con clave: 8/min y 5/min."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_DEFAULT", "3/minute")
    monkeypatch.setenv("RATE_LIMIT_HEAVY", "2/minute")
    monkeypatch.setenv("RATE_LIMIT_WRITE", "2/minute")
    monkeypatch.setenv("RATE_LIMIT_CLAVE_DEFAULT", "8/minute")
    monkeypatch.setenv("RATE_LIMIT_CLAVE_HEAVY", "5/minute")
    monkeypatch.setenv("API_CLAVES", f"scripts:{HUELLA}")

    import api.main
    importlib.reload(api.main)
    try:
        yield TestClient(api.main.app)
    finally:
        monkeypatch.undo()
        importlib.reload(api.main)


def _codigos(cliente, ruta, n, clave=None, **kwargs):
    headers = {"X-API-Key": clave} if clave else {}
    return [cliente.get(ruta, headers=headers, **kwargs).status_code for _ in range(n)]


def test_clave_valida_sube_el_limite_global(cliente):
    # /openapi.json: ruta sin decorador que no toca la BD.
    anonimo = _codigos(cliente, "/openapi.json", 4)
    assert anonimo[3] == 429
    con_clave = _codigos(cliente, "/openapi.json", 9, clave=CLAVE)
    assert con_clave[:8] == [200] * 8
    assert con_clave[8] == 429


def test_clave_cuenta_aparte_del_contador_anonimo_de_la_misma_ip(cliente):
    assert _codigos(cliente, "/openapi.json", 4)[3] == 429
    assert _codigos(cliente, "/openapi.json", 1, clave=CLAVE) == [200]


def test_clave_valida_sube_el_limite_pesado(cliente):
    params = {"week": 30, "year": 2023}
    anonimo = _codigos(cliente, "/api/v1/spatial/current", 3, params=params)
    assert anonimo[2] == 429
    con_clave = _codigos(cliente, "/api/v1/spatial/current", 6, clave=CLAVE, params=params)
    assert 429 not in con_clave[:5]
    assert con_clave[5] == 429


def test_clave_no_sube_el_limite_de_escritura(cliente):
    # Sin Authorization: lo que no sea 429 es 401/503 del handler.
    codigos = [
        cliente.post("/api/alertas", json=CUERPO_ALERTA_MINIMO, headers={"X-API-Key": CLAVE}).status_code
        for _ in range(3)
    ]
    assert codigos[2] == 429


def test_clave_desconocida_responde_401_con_cors(cliente):
    respuesta = cliente.get(
        "/openapi.json", headers={"X-API-Key": "otra", "Origin": ORIGEN}
    )
    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": "Clave de API no válida."}
    assert respuesta.headers.get("access-control-allow-origin") == ORIGEN


def test_cabecera_vacia_es_anonima(cliente):
    codigos = [
        cliente.get("/openapi.json", headers={"X-API-Key": ""}).status_code
        for _ in range(4)
    ]
    assert codigos[3] == 429


def test_parsear_claves_acepta_varias_y_normaliza():
    otra = "b" * 64
    assert parsear_claves(f" a:{HUELLA.upper()} , b-2:{otra},") == {HUELLA: "a", otra: "b-2"}
    assert parsear_claves(None) == {}
    assert parsear_claves("") == {}


@pytest.mark.parametrize(
    "valor",
    [
        "sin-separador",
        "nombre:corta",
        f":{HUELLA}",
        f"con espacio:{HUELLA}",
        f"a:{HUELLA},a:{'c' * 64}",
    ],
)
def test_parsear_claves_rechaza_entradas_mal_formadas(valor):
    with pytest.raises(ValueError):
        parsear_claves(valor)


def test_identificar():
    claves = {HUELLA: "scripts"}
    assert identificar(CLAVE, claves) == "scripts"
    assert identificar("otra", claves) is None
    assert identificar(CLAVE, {}) is None
