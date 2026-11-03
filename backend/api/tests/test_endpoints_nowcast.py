"""Endpoints de la prediccion de dengue a corto plazo (ADR 0020).

Los dos sirven un JSON precomputado y versionado; sin el archivo responden
200 con disponible=false, mismo contrato que /api/riesgo-nacional. No tocan
Postgres, asi que la suite corre sin base de datos.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from api import main  # noqa: E402
from api.rutas import dengue as rutas_dengue  # noqa: E402

RUTAS = {
    "/api/nowcast-dengue": "NOWCAST_DENGUE_PATH",
    "/api/nowcast-dengue/retrospectivo": "NOWCAST_DENGUE_RETRO_PATH",
}


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.mark.parametrize("ruta", RUTAS)
def test_sin_artefacto_responde_disponible_false(client, ruta, tmp_path):
    with patch.object(rutas_dengue, RUTAS[ruta], tmp_path / "no-existe.json"):
        respuesta = client.get(ruta)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["disponible"] is False
    assert cuerpo["motivo"]
    assert cuerpo["aviso"]


@pytest.mark.parametrize("ruta", RUTAS)
def test_con_artefacto_lo_sirve_con_aviso(client, ruta, tmp_path):
    archivo = tmp_path / "artefacto.json"
    archivo.write_text('{"horizontes": [1, 2]}', encoding="utf-8")
    with patch.object(rutas_dengue, RUTAS[ruta], archivo):
        respuesta = client.get(ruta)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["disponible"] is True
    assert cuerpo["aviso"]
    assert cuerpo["horizontes"] == [1, 2]


def test_retrospectivo_versionado_es_coherente():
    """El artefacto versionado: un abanico por semana salvo la ultima (que es
    la estimacion del artefacto principal), 8 horizontes por semana y la misma
    serie observada que termina en el ancla."""
    import json

    if not rutas_dengue.NOWCAST_DENGUE_RETRO_PATH.exists():
        pytest.skip("artefacto retrospectivo no generado")
    retro = json.loads(rutas_dengue.NOWCAST_DENGUE_RETRO_PATH.read_text(encoding="utf-8"))
    principal = json.loads(rutas_dengue.NOWCAST_DENGUE_PATH.read_text(encoding="utf-8"))

    assert retro["observado"][-1][0] == principal["ancla"]["fecha"]
    assert len(retro["origenes"]) == len(retro["observado"]) - 1
    n_campos = len(retro["campos_horizonte"])
    for fila in retro["origenes"]:
        assert ("h" in fila) != ("motivo" in fila)
        for valores in fila.get("h", []):
            assert valores is None or len(valores) == n_campos
