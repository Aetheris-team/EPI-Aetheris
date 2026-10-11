"""Parámetros de conexión a Postgres para la API y sus órdenes de consola.

La API se conecta con el rol de aplicación (ADR 0024, punto E), que no puede
alterar el esquema ni modificar la auditoría. Ese rol llega en DATABASE_URL.
Si DATABASE_URL no está definida o está vacía se usan las variables
POSTGRES_*, que es lo que había antes y lo que sigue inyectando Render con
fromDatabase hasta que se configure el rol de aplicación.

El runner de migraciones tiene su propia resolución (db/aplicar_migraciones.py)
porque vive fuera del paquete y usa otra variable: DATABASE_URL_MIGRACIONES.
"""

from __future__ import annotations

import os


def parametros_conexion() -> dict[str, str]:
    """Argumentos para psycopg2.connect o ThreadedConnectionPool."""
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        return {"dsn": url}
    return {
        "host": os.getenv("POSTGRES_HOST", "db"),
        "database": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
    }
