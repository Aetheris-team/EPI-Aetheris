"""El pool de Postgres descarta las conexiones muertas en vez de reusarlas.

Con POSTGRES_POOL_MIN >= 1, una conexión ociosa que el servidor cortó
(pg_terminate_backend, reinicio de la base, Neon dormido) salía del pool en la
siguiente petición y terminaba en OperationalError -> 503. Las pruebas con
pool falso no necesitan base; la de integración se omite sin Postgres en
localhost:5432.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import psycopg2
import pytest
from dotenv import load_dotenv
from psycopg2 import InterfaceError, OperationalError
from psycopg2.pool import ThreadedConnectionPool

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BACKEND_DIR.parent / ".env", override=False)
os.environ.setdefault("POSTGRES_HOST", "localhost")
sys.path.insert(0, str(BACKEND_DIR))

from api import main  # noqa: E402
from api.conexion_db import parametros_conexion  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class _CursorFalso:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql):
        if self._conn.muerta:
            self._conn.closed = 2
            raise OperationalError("server closed the connection unexpectedly")


class _ConexionFalsa:
    def __init__(self, muerta=False, rollback_falla=False):
        self.muerta = muerta
        self.rollback_falla = rollback_falla
        self.closed = 0
        self.autocommit = False

    def cursor(self):
        if self.closed:
            raise InterfaceError("connection already closed")
        return _CursorFalso(self)

    def rollback(self):
        if self.closed or self.rollback_falla:
            raise InterfaceError("connection already closed")


class _PoolFalso:
    """Entrega las conexiones en orden y anota cómo se devuelve cada una."""

    def __init__(self, *conexiones):
        self._pendientes = list(conexiones)
        self.devueltas: list[tuple[_ConexionFalsa, bool]] = []

    def getconn(self):
        return self._pendientes.pop(0)

    def putconn(self, conn, close=False):
        self.devueltas.append((conn, close))


@pytest.fixture
def pool_falso(monkeypatch):
    def instalar(*conexiones, minimo=1):
        pool = _PoolFalso(*conexiones)
        monkeypatch.setattr(main, "_pool", pool)
        monkeypatch.setattr(main, "POSTGRES_POOL_MIN", minimo)
        return pool

    return instalar


def test_conexion_sana_vuelve_al_pool(pool_falso):
    conn = _ConexionFalsa()
    pool = pool_falso(conn)
    with main._conexion() as entregada:
        assert entregada is conn
        assert entregada.autocommit is False
    assert pool.devueltas == [(conn, False)]


def test_conexion_cerrada_durante_la_peticion_se_descarta(pool_falso):
    conn = _ConexionFalsa()
    pool = pool_falso(conn)
    with pytest.raises(OperationalError):
        with main._conexion() as entregada:
            entregada.muerta = True
            with entregada.cursor() as cursor:
                cursor.execute("SELECT 1;")
    assert pool.devueltas == [(conn, True)]


def test_rollback_fallido_descarta_la_conexion(pool_falso):
    conn = _ConexionFalsa(rollback_falla=True)
    pool = pool_falso(conn)
    with main._conexion():
        pass
    assert conn.closed == 0
    assert pool.devueltas == [(conn, True)]


def test_conexion_ociosa_muerta_se_reemplaza_antes_de_entregarla(pool_falso):
    muerta = _ConexionFalsa(muerta=True)
    nueva = _ConexionFalsa()
    pool = pool_falso(muerta, nueva)
    with main._conexion() as entregada:
        assert entregada is nueva
    assert pool.devueltas == [(muerta, True), (nueva, False)]


def test_descarta_hasta_el_minimo_del_pool_y_luego_falla(pool_falso):
    # Con POSTGRES_POOL_MIN=2 puede haber dos ociosas muertas; la tercera
    # conexión es nueva, y si también falla la base está caída de verdad.
    conexiones = [_ConexionFalsa(muerta=True) for _ in range(3)]
    pool = pool_falso(*conexiones, minimo=2)
    with pytest.raises(OperationalError):
        with main._conexion():
            pass
    assert pool.devueltas == [(c, True) for c in conexiones]
    # El semáforo se liberó: otra petición puede tomar su turno.
    assert main._pool_semaforo.acquire(timeout=0)
    main._pool_semaforo.release()


def _db_disponible() -> bool:
    try:
        conn = psycopg2.connect(**parametros_conexion(), connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


def test_health_sobrevive_a_pg_terminate_backend(monkeypatch):
    if not _db_disponible():
        pytest.skip("Postgres no disponible -- se omite la prueba con pool real.")
    pool = ThreadedConnectionPool(1, 2, **parametros_conexion(), connect_timeout=5)
    monkeypatch.setattr(main, "_pool", pool)
    monkeypatch.setattr(main, "POSTGRES_POOL_MIN", 1)
    try:
        cliente = TestClient(main.app)
        assert cliente.get("/health").status_code == 200
        with main._conexion() as conn:
            pid = conn.get_backend_pid()

        # Un rol puede terminar los procesos de su mismo rol sin ser superusuario.
        verdugo = psycopg2.connect(**parametros_conexion(), connect_timeout=5)
        verdugo.autocommit = True
        try:
            with verdugo.cursor() as cursor:
                cursor.execute("SELECT pg_terminate_backend(%s);", (pid,))
                assert cursor.fetchone()[0] is True
                for _ in range(50):
                    cursor.execute("SELECT 1 FROM pg_stat_activity WHERE pid = %s;", (pid,))
                    if cursor.fetchone() is None:
                        break
                    time.sleep(0.05)
        finally:
            verdugo.close()

        assert cliente.get("/health").status_code == 200
        with main._conexion() as conn:
            assert conn.get_backend_pid() != pid
    finally:
        pool.closeall()
