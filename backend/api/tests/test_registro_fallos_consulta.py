"""Los endpoints de consulta registran la causa de un fallo de la base.

Antes, una docena de endpoints envolvía cualquier excepción en un 500
"Error de conexión a la base de datos" sin registrar nada: un KeyError en el
código de la consulta y una base caída se veían igual y la traza se perdía.
Ahora pasan por _fallo_base_datos, con el mismo criterio de /health para no
filtrar credenciales (test_health_registro.py).

Sin base de datos: _conexion se reemplaza por una que falla.
"""
from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from psycopg2 import OperationalError, ProgrammingError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from api import main  # noqa: E402

DETALLE = "Error de conexión a la base de datos"

# Uno por cada forma de endpoint: los que antes respondían 500 mudo, uno de
# los degradables (UndefinedTable → disponible=false) y uno de alertas.
RUTAS = [
    "/api/casos-nacional",
    "/api/casos-departamentales",
    "/api/v1/spatial/current?week=10&year=2023",
    "/api/v1/presion/temporal/SV-SS?anio=2023",
    "/api/v1/vigilancia/integridad",
    "/api/ira/departamental",
    "/api/respiratorios/virus",
    "/api/alertas",
]


def _con_fallo(excepcion):
    @contextmanager
    def falso():
        raise excepcion
        yield

    return falso


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.mark.parametrize("ruta", RUTAS)
def test_error_de_python_responde_500_y_registra_la_traza(client, monkeypatch, caplog, ruta):
    monkeypatch.setattr(main, "_conexion", _con_fallo(KeyError("columna_que_no_existe")))
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        respuesta = client.get(ruta)
    assert respuesta.status_code == 500
    assert respuesta.json()["detail"] == DETALLE
    assert "columna_que_no_existe" not in respuesta.text
    registro = [r for r in caplog.records if r.getMessage().startswith("consulta:")]
    assert len(registro) == 1
    assert "KeyError" in registro[0].getMessage()
    assert registro[0].exc_info is not None


@pytest.mark.parametrize("ruta", RUTAS)
def test_fallo_de_conexion_responde_503_con_el_mensaje_del_servidor(client, monkeypatch, caplog, ruta):
    mensaje = 'FATAL:  password authentication failed for user "epi_app"'
    monkeypatch.setattr(main, "_conexion", _con_fallo(OperationalError(mensaje)))
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        respuesta = client.get(ruta)
    assert respuesta.status_code == 503
    assert respuesta.json()["detail"] == DETALLE
    assert "password authentication failed" not in respuesta.text
    assert "OperationalError" in caplog.text
    assert "password authentication failed" in caplog.text


@pytest.mark.parametrize("ruta", RUTAS)
def test_otro_error_de_psycopg2_registra_solo_su_clase(client, monkeypatch, caplog, ruta):
    secreto = "postgresql://epi_app:ClaveSecreta123@host/db"
    monkeypatch.setattr(main, "_conexion", _con_fallo(ProgrammingError(f"invalid dsn: {secreto}")))
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        respuesta = client.get(ruta)
    assert respuesta.status_code == 500
    assert "ProgrammingError" in caplog.text
    assert "ClaveSecreta123" not in caplog.text
    assert "ClaveSecreta123" not in respuesta.text
