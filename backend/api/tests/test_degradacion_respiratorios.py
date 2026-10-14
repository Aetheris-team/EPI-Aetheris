"""Degradacion elegante de /api/respiratorios/* y /api/neumonias/* (issue #84).

Cuando falta la tabla (UndefinedTable) o no hay filas, los endpoints
responden 200 con disponible=false -- mismo contrato que /api/riesgo-nacional.
Un fallo real de conexion sigue siendo 503/500, no un aviso de "sin datos".
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from psycopg2 import OperationalError
from psycopg2.errors import UndefinedTable

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from api.main import app  # noqa: E402
from api.ira import cargar_ira_departamental  # noqa: E402
from api.neumonias import cargar_neumonias_departamental  # noqa: E402

ENDPOINTS_DEGRADABLES = [
    "/api/respiratorios/virus",
    "/api/respiratorios/temporal?virus=vsr&metrica=detecciones",
    "/api/respiratorios/semana/2023/25",
    "/api/respiratorios/cobertura",
    "/api/neumonias/departamental",
    "/api/neumonias/temporal/SV-SS",
    "/api/neumonias/heatmap/2023",
    "/api/ira/nacional",
    "/api/neumonias/nacional",
]


@pytest.fixture
def client():
    return TestClient(app)


def _conexion_que_lanza(exc: BaseException):
    mock_cx = MagicMock()
    mock_cx.return_value.__enter__.side_effect = exc
    mock_cx.return_value.__exit__.return_value = False
    return mock_cx


@pytest.mark.parametrize("ruta", ENDPOINTS_DEGRADABLES)
def test_tabla_ausente_responde_200_disponible_false(client, ruta):
    with patch("api.main._conexion", _conexion_que_lanza(UndefinedTable())):
        respuesta = client.get(ruta)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["disponible"] is False
    assert cuerpo["motivo"]
    assert cuerpo["aviso"]


@pytest.mark.parametrize("ruta", ENDPOINTS_DEGRADABLES)
def test_fallo_conexion_responde_503(client, ruta):
    with patch(
        "api.main._conexion",
        _conexion_que_lanza(OperationalError("could not connect to server")),
    ):
        respuesta = client.get(ruta)
    assert respuesta.status_code == 503
    assert respuesta.json()["detail"] == "Error de conexión a la base de datos"


def test_virus_sin_filas_responde_200_disponible_false(client):
    mock_cx = MagicMock()
    mock_cx.return_value.__enter__.return_value = MagicMock()
    mock_cx.return_value.__exit__.return_value = False
    with patch("api.main._conexion", mock_cx), patch(
        "api.rutas.respiratorio.listar_virus", return_value=[]
    ):
        respuesta = client.get("/api/respiratorios/virus")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["disponible"] is False
    assert "sin filas" in cuerpo["motivo"]


@pytest.mark.parametrize("ruta", ["/api/ira/nacional", "/api/neumonias/nacional"])
def test_serie_nacional_sin_capturas_responde_disponible_false(client, ruta):
    # El seed del repositorio no trae el tablero: sin filas no es un error.
    mock_cx = MagicMock()
    mock_cx.return_value.__enter__.return_value = MagicMock()
    mock_cx.return_value.__exit__.return_value = False
    with patch("api.main._conexion", mock_cx), patch(
        "api.rutas.respiratorio.cargar_serie_tablero_nacional", return_value=[]
    ):
        respuesta = client.get(ruta)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["disponible"] is False
    assert "tablero" in cuerpo["motivo"]


def test_error_inesperado_sigue_siendo_500(client):
    with patch("api.main._conexion", _conexion_que_lanza(RuntimeError("boom"))):
        respuesta = client.get("/api/respiratorios/virus")
    assert respuesta.status_code == 500
    assert respuesta.json()["detail"] == "Error de conexión a la base de datos"


def test_cargar_neumonias_departamental_semanas_cero_si_join_vacio():
    """El LEFT JOIN sin coincidencias no debe reportar semanas_con_dato=1."""

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            self.sql = sql

        def fetchall(self):
            # Lo que Postgres devuelve con count(c.id) sobre un JOIN vacío.
            return [("Ahuachapán", "SV-AH", None, 0, None, None)]

    class _Conn:
        def __init__(self):
            self.cur = _Cursor()

        def cursor(self):
            return self.cur

    conn = _Conn()
    filas = cargar_neumonias_departamental(conn)
    assert len(filas) == 1
    assert filas[0]["semanas_con_dato"] == 0
    assert filas[0]["notificado_total"] == 0
    assert filas[0]["primer_anio"] is None
    assert filas[0]["ultimo_anio"] is None
    assert "count(c.id)" in conn.cur.sql
    assert "count(*)" not in conn.cur.sql


def test_cargar_ira_departamental_semanas_cero_si_join_vacio():
    """Mismo caso que neumonías: un departamento sin filas de IRA no debe
    reportar semanas_con_dato=1 por la fila fantasma del LEFT JOIN."""

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            self.sql = sql

        def fetchall(self):
            return [("Ahuachapán", "SV-AH", None, 0, None, None)]

    class _Conn:
        def __init__(self):
            self.cur = _Cursor()

        def cursor(self):
            return self.cur

    conn = _Conn()
    filas = cargar_ira_departamental(conn)
    assert filas[0]["semanas_con_dato"] == 0
    assert filas[0]["notificado_total"] == 0
    assert "count(c.id)" in conn.cur.sql
    assert "count(*)" not in conn.cur.sql
