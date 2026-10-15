"""API_DOCS_ENABLED apaga /docs, /redoc y /openapi.json (ADR 0024).

El flag se lee al importar api.main, así que cada prueba recarga el módulo y
el finally lo deja como estaba para no contaminar a las demás suites.
"""
import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

RUTAS_DOCUMENTACION = ("/docs", "/redoc", "/openapi.json")


def _recargar(monkeypatch, valor):
    if valor is None:
        monkeypatch.delenv("API_DOCS_ENABLED", raising=False)
    else:
        monkeypatch.setenv("API_DOCS_ENABLED", valor)
    import api.main

    return importlib.reload(api.main)


def _restaurar(monkeypatch):
    monkeypatch.undo()
    import api.main

    importlib.reload(api.main)


def test_docs_apagados_responden_404(monkeypatch):
    modulo = _recargar(monkeypatch, "false")
    try:
        cliente = TestClient(modulo.app)
        for ruta in RUTAS_DOCUMENTACION:
            assert cliente.get(ruta).status_code == 404, ruta
    finally:
        _restaurar(monkeypatch)


def test_docs_apagados_usan_csp_cerrada(monkeypatch):
    modulo = _recargar(monkeypatch, "false")
    try:
        respuesta = TestClient(modulo.app).get("/docs")
        csp = respuesta.headers["content-security-policy"]
        assert "default-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "cdn.jsdelivr.net" not in csp
        # Las demás cabeceras de seguridad no cambian.
        assert respuesta.headers["x-content-type-options"] == "nosniff"
        assert respuesta.headers["x-frame-options"] == "DENY"
    finally:
        _restaurar(monkeypatch)


def test_docs_activos_por_defecto(monkeypatch):
    modulo = _recargar(monkeypatch, None)
    try:
        cliente = TestClient(modulo.app)
        for ruta in RUTAS_DOCUMENTACION:
            assert cliente.get(ruta).status_code == 200, ruta
        csp = cliente.get("/docs").headers["content-security-policy"]
        assert "default-src 'self'" in csp
    finally:
        _restaurar(monkeypatch)


def _rutas(lista):
    """Aplana el árbol de rutas: desde FastAPI 0.137 cada include_router queda
    en `app.routes` como un nodo con `original_router` (api/rutas/)."""
    for ruta in lista:
        if hasattr(ruta, "original_router"):
            yield from _rutas(ruta.original_router.routes)
        else:
            yield ruta


def test_el_resto_de_la_api_sigue_con_los_docs_apagados(monkeypatch):
    modulo = _recargar(monkeypatch, "false")
    try:
        rutas = {ruta.path for ruta in _rutas(modulo.app.routes)}
        assert "/health" in rutas
        assert "/api/alertas" in rutas
    finally:
        _restaurar(monkeypatch)
