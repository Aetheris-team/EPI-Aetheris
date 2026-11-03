"""Endpoints del análisis descriptivo de clima y dengue (ADR 0023).

Sirven dos JSON precomputados y versionados; sin el archivo responden 200 con
disponible=false, mismo contrato que /api/nowcast-dengue. No tocan Postgres,
así que la suite corre sin base de datos.
"""
from __future__ import annotations

import json
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
    "/api/clima-dengue/por-anio": "CLIMA_DENGUE_POR_ANIO_PATH",
    "/api/clima-dengue/multipais": "CLIMA_DENGUE_MULTIPAIS_PATH",
}

ANIOS_SEMANALES = {"2014", "2015", "2016", "2017", "2018", "2019", "2021", "2022", "2023"}
VARIABLES = {
    "temp_media", "temp_max", "temp_min", "precipitation_sum",
    "precipitation_hours", "humedad_relativa_media", "punto_rocio", "oni",
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
    archivo.write_text('{"parametros": {"horizonte": 4}}', encoding="utf-8")
    with patch.object(rutas_dengue, RUTAS[ruta], archivo):
        respuesta = client.get(ruta)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["disponible"] is True
    assert cuerpo["aviso"]
    assert cuerpo["parametros"] == {"horizonte": 4}


@pytest.mark.parametrize("ruta", RUTAS)
def test_cabecera_de_cache(client, ruta):
    respuesta = client.get(ruta)
    assert respuesta.status_code == 200
    assert "max-age=3600" in respuesta.headers["cache-control"]


def test_por_anio_versionado_es_coherente(client):
    cuerpo = client.get("/api/clima-dengue/por-anio").json()
    assert cuerpo["disponible"] is True
    assert {"parametros", "A1", "A2", "A3", "A4", "A5", "series"} <= cuerpo.keys()
    assert {str(a) for a in cuerpo["parametros"]["anios"]} == ANIOS_SEMANALES
    assert set(cuerpo["A3"]["por_anio"]) == ANIOS_SEMANALES
    assert set(cuerpo["A4"]["por_anio"]) == ANIOS_SEMANALES
    agrupado = cuerpo["A3"]["agrupado"]
    assert agrupado["pares"] > 400
    for variable in VARIABLES:
        r = agrupado[variable]["r"]
        bajo, alto = agrupado[variable]["ic95"]
        assert -1 <= bajo <= r <= alto <= 1
    assert set(cuerpo["A5"]) == VARIABLES
    assert len(cuerpo["A2"]["casos_climatologia"]) == 52


def test_multipais_versionado_es_coherente(client):
    cuerpo = client.get("/api/clima-dengue/multipais").json()
    assert cuerpo["disponible"] is True
    paises = set(cuerpo["P1"])
    assert len(paises) == 18
    assert "EL SALVADOR" in paises
    assert set(cuerpo["P2"]["por_pais"]) == paises
    assert set(cuerpo["P3"]) == paises
    assert set(cuerpo["P4"]) == paises
    assert len(cuerpo["entradas"]["casos"]["sha256"]) == 64
    assert len(cuerpo["entradas"]["clima"]["sha256"]) == 64

    # Replicación del documento histórico: El Salvador +0,280, el menor de 18.
    el_salvador = cuerpo["P2"]["por_pais"]["EL SALVADOR"]
    assert el_salvador["r_con_senal"] == pytest.approx(0.280, abs=0.0015)
    assert cuerpo["P2"]["posicion_r_con_senal"]["EL SALVADOR"] == 1
    bajo, alto = el_salvador["ic95"]
    assert bajo < el_salvador["r_con_senal"] < alto

    # Las dos islas sin clima de superficie no tienen estimación agrupada.
    sin_estimacion = {p for p, v in cuerpo["P3"].items() if not v["estimacion"]}
    assert sin_estimacion == {"BERMUDA", "VIRGIN ISLANDS (US)"}

    for pais in paises - sin_estimacion:
        assert set(cuerpo["P3"][pais]["por_variable"]) <= VARIABLES
        assert len(cuerpo["P4"][pais]["casos"]["climatologia"]) == 52
    assert cuerpo["P6"]["r_con_senal"]["paises"] == 18
    assert set(cuerpo["P5"]) == {"A", "B", "C"}


def test_artefactos_son_json_valido():
    for nombre in ("clima_dengue_por_anio.json", "clima_dengue_multipais.json"):
        ruta = Path(main.__file__).parent / "datos" / nombre
        assert isinstance(json.loads(ruta.read_text(encoding="utf-8")), dict)
