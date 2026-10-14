"""
Conexion compartida a Postgres para scripts de ingesta.

Mismas variables de entorno que backend/api/conexion_db.py (DATABASE_URL y, si
no esta definida, POSTGRES_HOST/DB/USER/PASSWORD/PORT) para no introducir una
segunda convencion de configuracion.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).parent.parent.parent / ".env"
_env_cargado = False


def get_connection() -> psycopg2.extensions.connection:
    global _env_cargado
    if not _env_cargado:
        load_dotenv(_ENV_PATH)
        _env_cargado = True

    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        return psycopg2.connect(dsn=url)

    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "db"),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        port=os.getenv("POSTGRES_PORT", "5432"),
    )
