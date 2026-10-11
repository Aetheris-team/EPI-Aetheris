"""Crea (o rota la clave de) el rol de aplicacion de la base (ADR 0024, punto E).

Una migracion no puede crear este rol: llevaria la contrasena dentro de un
archivo versionado. Se ejecuta una vez a mano, con el rol propietario del
esquema, y despues solo para rotar la clave:

    python db/crear_rol_aplicacion.py            # pide la clave sin mostrarla
    python db/crear_rol_aplicacion.py --rol otro # nombre distinto del rol

En Render se corre desde la pestana Shell del servicio epi-aetheris-backend,
donde ya estan las POSTGRES_* del propietario. La conexion se resuelve igual
que en db/aplicar_migraciones.py (DATABASE_URL_MIGRACIONES, DATABASE_URL,
POSTGRES_*).

La clave llega por getpass, o por la variable EPI_APP_CLAVE si no hay
terminal. Nunca se imprime ni se guarda. Al terminar el script imprime la
forma de la URL sin clave, para armar DATABASE_URL en el panel.

Despues de crear el rol llama a aplicar_privilegios_roles() (migracion 0018),
asi que el rol queda listo sin esperar a otro despliegue.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys

import psycopg2
from psycopg2 import sql

from aplicar_migraciones import _conectar

_NOMBRE_ROL = re.compile(r"^[a-z][a-z0-9_]{2,62}$")
_LARGO_MINIMO = 24


def _leer_clave() -> str:
    clave = os.getenv("EPI_APP_CLAVE") or ""
    if not clave:
        clave = getpass.getpass("Clave nueva del rol de aplicacion: ")
        if clave != getpass.getpass("Repite la clave: "):
            sys.exit("Las dos claves no coinciden. No se hizo ningun cambio.")
    if len(clave) < _LARGO_MINIMO:
        sys.exit(f"La clave debe tener al menos {_LARGO_MINIMO} caracteres. No se hizo ningun cambio.")
    if not re.fullmatch(r"[A-Za-z0-9]+", clave):
        # Va dentro de una URL (DATABASE_URL): evita tener que escapar simbolos.
        sys.exit("Usa solo letras y numeros en la clave, para que quepa en la URL sin escapes.")
    return clave


def crear_o_rotar(conn, rol: str, clave: str) -> bool:
    """Devuelve True si el rol se creo, False si ya existia y solo se roto la clave."""
    with conn.cursor() as cur:
        cur.execute("SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user")
        if not cur.fetchone()[0]:
            sys.exit(
                "El usuario de esta conexion no tiene permiso para crear roles (CREATEROLE). "
                "Ver 'Si el usuario no puede crear roles' en docs/seguridad/roles-de-base-de-datos.md."
            )
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (rol,))
        existe = cur.fetchone() is not None
        nombre = sql.Identifier(rol)
        if existe:
            cur.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(nombre, sql.Literal(clave)))
        else:
            cur.execute(sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(nombre, sql.Literal(clave)))
        # Explicito: ningun atributo que permita alterar el esquema u otros roles.
        cur.execute(
            sql.SQL(
                "ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT"
            ).format(nombre)
        )
        cur.execute("SELECT current_database()")
        base = cur.fetchone()[0]
        cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(base), nombre))
        cur.execute("SELECT to_regproc('aplicar_privilegios_roles') IS NOT NULL")
        if not cur.fetchone()[0]:
            conn.rollback()
            sys.exit(
                "Falta la funcion aplicar_privilegios_roles (migracion 0018). "
                "Despliega primero la migracion y vuelve a correr este script."
            )
        cur.execute("SELECT aplicar_privilegios_roles(%s)", (rol,))
        assert cur.fetchone()[0] is True
    conn.commit()
    return not existe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rol", default="epi_app", help="nombre del rol (por defecto epi_app)")
    args = parser.parse_args()
    if not _NOMBRE_ROL.match(args.rol):
        sys.exit("Nombre de rol no valido: minusculas, digitos y guion bajo, empezando por letra.")

    clave = _leer_clave()
    conn = _conectar()
    try:
        creado = crear_o_rotar(conn, args.rol, clave)
        host = conn.get_dsn_parameters().get("host") or "<host interno de la base>"
        with conn.cursor() as cur:
            cur.execute("SELECT current_user, current_database(), inet_server_port()")
            propietario, base, puerto = cur.fetchone()
    finally:
        conn.close()

    print(f"Rol {args.rol}: {'creado' if creado else 'ya existia, clave rotada'}. Privilegios aplicados.")
    print(f"Conexion hecha como {propietario}.")
    print("Forma de DATABASE_URL (pon la clave en el panel, no aqui):")
    print(f"  postgresql://{args.rol}:<CLAVE>@{host}:{puerto}/{base}")


if __name__ == "__main__":
    main()
