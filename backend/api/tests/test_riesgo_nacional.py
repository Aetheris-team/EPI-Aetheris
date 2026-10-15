"""/api/riesgo-nacional sirve las salidas congeladas del clasificador retirado
(ADR 0025) con el mismo contrato que cuando el modelo corría en cada request.

Sin el artefacto (issue #72) el endpoint no responde 503: responde 200 con
disponible=false para que el frontend muestre un aviso explicito. Que el
artefacto coincida con el modelo lo comprueba
ingestion/tests/test_congelar_clasificador.py.
"""
import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

import api.main  # noqa: E402


@pytest.fixture
def client():
    api.main._riesgo_nacional_cache = None
    yield TestClient(api.main.app)
    api.main._riesgo_nacional_cache = None


def test_sin_artefacto_responde_200_disponible_false(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api.main, "RIESGO_NACIONAL_PATH", tmp_path / "no_existe.json")
    respuesta = client.get("/api/riesgo-nacional")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["disponible"] is False
    assert "motivo" in cuerpo
    assert cuerpo["aviso"]


def test_sin_parametros_devuelve_la_ultima_semana(client):
    cuerpo = client.get("/api/riesgo-nacional").json()
    assert cuerpo["disponible"] is True
    semanas = json.loads(api.main.RIESGO_NACIONAL_PATH.read_text(encoding="utf-8"))["semanas"]
    ultima = max(semanas, key=lambda f: (f["anio"], f["semana_epi"]))
    assert (cuerpo["anio"], cuerpo["semana_epi"]) == (ultima["anio"], ultima["semana_epi"])
    assert set(cuerpo) == {
        "disponible", "anio", "semana_epi", "etiqueta_predicha", "etiqueta_real",
        "probabilidades", "casos_observados", "metricas_modelo", "aviso",
    }
    assert list(cuerpo["probabilidades"]) == ["bajo", "medio", "alto"]
    assert cuerpo["metricas_modelo"]["anio_prueba"] == 2023


def test_semana_pedida(client):
    cuerpo = client.get("/api/riesgo-nacional?anio=2018&semana=31").json()
    assert (cuerpo["anio"], cuerpo["semana_epi"]) == (2018, 31)
    assert cuerpo["etiqueta_real"] in {"bajo", "medio", "alto"}


def test_semana_sin_datos_responde_404(client):
    respuesta = client.get("/api/riesgo-nacional?anio=2030&semana=1")
    assert respuesta.status_code == 404
    assert "año=2030, semana=1" in respuesta.json()["detail"]


def test_la_api_no_importa_scikit_learn_ni_joblib():
    fuente = (BACKEND_DIR / "api" / "main.py").read_text(encoding="utf-8")
    assert "import joblib" not in fuente
    assert "sklearn" not in fuente
