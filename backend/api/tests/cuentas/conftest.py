"""Fixtures de las pruebas de cuentas.

Las pruebas que tocan la base abren una conexión real (la del servicio de CI o
un Postgres local con las migraciones aplicadas) y deshacen todo al terminar:
los módulos de cuentas no hacen commit, así que un rollback limpia la prueba.
"""

from __future__ import annotations

import base64
import os

import psycopg2
import pytest

from api.cuentas import contrasenas
from api.cuentas.config import ConfigCuentas


@pytest.fixture(autouse=True)
def _sin_presupuesto_global_de_hashes(monkeypatch):
    """La suite calcula cientos de hashes seguidos; el presupuesto global por
    minuto lo ejercitan solo las pruebas que lo fijan a propósito."""
    monkeypatch.setattr(contrasenas, "POR_MINUTO_MAX", 0)


def _clave(byte: int) -> bytes:
    return bytes([byte]) * 32


@pytest.fixture
def config() -> ConfigCuentas:
    return ConfigCuentas(
        pimientas={1: _clave(1), 2: _clave(2)},
        version_pimienta=2,
        claves_cifrado={1: _clave(3)},
        version_cifrado=1,
        origen_canonico="https://epi-aetheris.dev",
        rp_id="epi-aetheris.dev",
        consultar_hibp=False,
    )


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


@pytest.fixture
def conn():
    try:
        conexion = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            dbname=os.getenv("POSTGRES_DB", "epi_aetheris"),
            user=os.getenv("POSTGRES_USER", "aetheris_user"),
            password=os.getenv("POSTGRES_PASSWORD", "aetheris_ci_password"),
            connect_timeout=3,
        )
    except psycopg2.OperationalError:
        if os.getenv("CI"):
            raise
        pytest.skip("Sin Postgres con migraciones para las pruebas de cuentas")
    try:
        with conexion.cursor() as cur:
            cur.execute("SELECT to_regclass('public.sesiones')")
            if cur.fetchone()[0] is None:
                pytest.skip("Faltan las migraciones 0014 a 0016")
        yield conexion
    finally:
        conexion.rollback()
        conexion.close()


@pytest.fixture
def crear_usuario(conn):
    contador = {"n": 0}

    def _crear(estado: str = "activo", roles: tuple[str, ...] = ()) -> str:
        contador["n"] += 1
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usuarios (correo, nombre_visible, estado, correo_verificado_en, "
                "terminos_version, terminos_aceptados_en) "
                "VALUES (%s, %s, %s, now(), 'v1', now()) RETURNING id",
                (f"persona{contador['n']}@ejemplo.org", f"Persona {contador['n']}", estado),
            )
            uid = str(cur.fetchone()[0])
            for rol in roles:
                cur.execute("INSERT INTO usuarios_roles (usuario_id, rol) VALUES (%s, %s)", (uid, rol))
        return uid

    return _crear
