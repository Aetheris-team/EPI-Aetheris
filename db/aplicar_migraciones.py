"""
Runner minimo de migraciones para una base ya inicializada.

`docker-entrypoint-initdb.d` corre db/migrations/*.sql una sola vez, sobre
volumen vacio, al crear el contenedor de Postgres -- una migracion agregada
despues nunca se aplica sola sobre una base que ya existe. Este script cubre
ese caso, via una tabla `schema_migrations` que registra que archivos ya
corrieron. Ver docs/adr/0009-runner-minimo-de-migraciones.md para el porque.

Uso (desde el host, con el stack levantado -- el puerto 5432 esta publicado
por docker-compose.yml):

    python db/aplicar_migraciones.py --bootstrap   # una sola vez, ver ADR 0009 punto C
    python db/aplicar_migraciones.py               # aplica lo nuevo

En Render, el mismo comando (sin --bootstrap) corre como preDeployCommand
dentro de la imagen del backend, con las env vars POSTGRES_* que ya inyecta
el servicio (fromDatabase).

Conexion (ADR 0024, punto E). El runner necesita un rol que sea propietario
del esquema; la API usa otro, sin permiso para alterarlo. Orden de resolucion:

    1. DATABASE_URL_MIGRACIONES  (rol propietario; lo usa solo este script)
    2. DATABASE_URL              (si la anterior falta; retrocompatibilidad)
    3. POSTGRES_HOST/PORT/DB/USER/PASSWORD

Las variables vacias cuentan como no definidas. Despues de aplicar las
migraciones pendientes, y aunque no haya ninguna, el runner llama a
aplicar_privilegios_roles() (migracion 0018): concede al rol de la API sus
privilegios si el rol ya existe, de modo que crear el rol y desplegar en
cualquier orden converge al mismo estado.

Requiere psycopg2 y python-dotenv (ya en backend/requirements.txt; usar
backend/.venv o instalar ambos en el entorno desde el que se corra).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).parent.parent
_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
# Solo migraciones numeradas. Ignora residuos como seed_datos_reales.sql
# (vacio, ya borrado en #100) u otros .sql que no son DDL versionado.
_NOMBRE_MIGRACION = re.compile(r"^\d{4}_.+\.sql$")


def _valor(nombre: str) -> str | None:
    valor = (os.getenv(nombre) or "").strip()
    return valor or None


def _parametros_conexion() -> dict[str, str]:
    """Argumentos de psycopg2.connect segun el orden del docstring del modulo."""
    url = _valor("DATABASE_URL_MIGRACIONES") or _valor("DATABASE_URL")
    if url:
        return {"dsn": url}
    host = os.getenv("POSTGRES_HOST", "localhost")
    if host == "db":
        # Nombre de servicio de docker-compose: solo resuelve dentro de
        # aetheris_network. Este runner corre desde el host (ADR 0009) o en
        # el preDeploy de Render, donde POSTGRES_HOST ya es el hostname
        # gestionado. No usar MIGRACIONES_POSTGRES_HOST.
        host = "localhost"
    return {
        "host": host,
        "database": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
    }


def _conectar() -> psycopg2.extensions.connection:
    load_dotenv(_REPO_ROOT / ".env")
    return psycopg2.connect(**_parametros_conexion())


def _tabla_existe(cur, nombre: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (nombre,))
    return cur.fetchone()[0]


def _archivos_migracion() -> list[Path]:
    archivos: list[Path] = []
    for ruta in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        if not _NOMBRE_MIGRACION.match(ruta.name):
            continue
        if ruta.stat().st_size == 0:
            continue
        archivos.append(ruta)
    return archivos


def _checksum(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def bootstrap(conn) -> None:
    with conn.cursor() as cur:
        if _tabla_existe(cur, "schema_migrations"):
            print("schema_migrations ya existe -- no se vuelve a sembrar. Usa la corrida normal.")
            return

        cur.execute(
            """
            CREATE TABLE schema_migrations (
                filename    text PRIMARY KEY,
                checksum    text NOT NULL,
                applied_at  timestamptz NOT NULL DEFAULT now()
            )
            """
        )

        archivos = _archivos_migracion()
        for ruta in archivos:
            cur.execute(
                "INSERT INTO schema_migrations (filename, checksum) VALUES (%s, %s)",
                (ruta.name, _checksum(ruta)),
            )
        conn.commit()
        print(f"schema_migrations creada. Sembrados como ya aplicados ({len(archivos)}):")
        for ruta in archivos:
            print(f"  - {ruta.name}")


def aplicar_pendientes(conn) -> None:
    with conn.cursor() as cur:
        if not _tabla_existe(cur, "schema_migrations"):
            sys.exit(
                "schema_migrations no existe todavia. Corre primero:\n"
                "  python db/aplicar_migraciones.py --bootstrap"
            )

        cur.execute("SELECT filename, checksum FROM schema_migrations")
        aplicadas = dict(cur.fetchall())

    pendientes = [r for r in _archivos_migracion() if r.name not in aplicadas]

    for ruta in _archivos_migracion():
        if ruta.name in aplicadas and _checksum(ruta) != aplicadas[ruta.name]:
            print(
                f"AVISO: {ruta.name} ya estaba aplicado pero su contenido cambio "
                "desde entonces (checksum no coincide). No se reaplica solo -- "
                "revisar manualmente."
            )

    if not pendientes:
        print("Nada pendiente. La base ya tiene todas las migraciones de db/migrations/.")
        aplicar_privilegios(conn)
        return

    for ruta in pendientes:
        sql = ruta.read_text()
        with conn.cursor() as cur:
            try:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_migrations (filename, checksum) VALUES (%s, %s)",
                    (ruta.name, _checksum(ruta)),
                )
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()
        print(f"aplicada: {ruta.name}")
    aplicar_privilegios(conn)


def aplicar_privilegios(conn) -> None:
    """Concede al rol de la API sus privilegios (migracion 0018), si el rol existe.

    Nunca interrumpe el despliegue: las migraciones ya quedaron aplicadas y un
    fallo aqui solo deja al rol de la API sin los permisos nuevos, lo que se
    ve como errores de permiso en sus consultas, no como un esquema roto.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT current_user, to_regproc('aplicar_privilegios_roles') IS NOT NULL")
        usuario, existe = cur.fetchone()
        if not existe:
            conn.rollback()
            return
        try:
            cur.execute("SELECT aplicar_privilegios_roles()")
            concedidos = cur.fetchone()[0]
        except psycopg2.Error as exc:
            conn.rollback()
            print(
                f"AVISO: no se pudieron aplicar los privilegios de roles como {usuario}: "
                f"{exc.pgerror or exc}. Revisar que DATABASE_URL_MIGRACIONES use el "
                "rol propietario del esquema."
            )
            return
        conn.commit()
    if concedidos:
        print("privilegios del rol de aplicacion aplicados (aplicar_privilegios_roles).")
    else:
        print("el rol de aplicacion no existe todavia: no se concedio nada (ver docs/seguridad/roles-de-base-de-datos.md).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Crea schema_migrations y siembra los archivos actuales como ya aplicados (una sola vez).",
    )
    args = parser.parse_args()

    conn = _conectar()
    try:
        if args.bootstrap:
            bootstrap(conn)
        else:
            aplicar_pendientes(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
