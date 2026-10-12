"""/health registra la causa del fallo de conexión sin filtrar credenciales.

Sin base de datos: _conexion se reemplaza por una que falla. Antes de este
registro, una clave equivocada en DATABASE_URL solo dejaba un 500 mudo.
"""
from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from psycopg2 import OperationalError, ProgrammingError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from api import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _con_fallo(excepcion):
    @contextmanager
    def falso():
        raise excepcion
        yield

    return falso


def test_operational_error_registra_el_mensaje_del_servidor(monkeypatch, caplog):
    mensaje = 'FATAL:  password authentication failed for user "epi_app"'
    monkeypatch.setattr(main, "_conexion", _con_fallo(OperationalError(mensaje)))
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        respuesta = TestClient(main.app).get("/health")
    assert respuesta.status_code == 500
    assert "password authentication failed" not in respuesta.text
    assert "OperationalError" in caplog.text
    assert "password authentication failed" in caplog.text


def test_otra_clase_registra_solo_su_nombre(monkeypatch, caplog):
    secreto = "postgresql://epi_app:ClaveSecreta123@host/db"
    monkeypatch.setattr(
        main, "_conexion", _con_fallo(ProgrammingError(f"invalid dsn: {secreto}"))
    )
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        respuesta = TestClient(main.app).get("/health")
    assert respuesta.status_code == 500
    assert "ProgrammingError" in caplog.text
    assert "ClaveSecreta123" not in caplog.text
    assert "ClaveSecreta123" not in respuesta.text
