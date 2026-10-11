"""Órdenes de consola para lo que no puede depender de una cuenta existente.

    python -m api.cuentas.cli crear-admin --correo ana@institucion.org
    python -m api.cuentas.cli restablecer-factores --correo ana@institucion.org --motivo "..."
    python -m api.cuentas.cli verificar-auditoria

Se ejecutan con acceso a la base y al entorno del servicio (Render shell o un
contenedor local); quien las usa ya tiene ese acceso, y cada una deja su fila
en la auditoría como actor 'sistema'.
"""

from __future__ import annotations

import argparse
import sys

import psycopg2

from ..conexion_db import parametros_conexion
from . import auditoria, servicio
from .config import cargar_config


def _conectar():
    return psycopg2.connect(**parametros_conexion(), connect_timeout=5)


def _crear_admin(conn, args) -> int:
    config = cargar_config()
    try:
        _, token, _ = servicio.crear_invitacion(
            conn, config, invitador=None, correo=args.correo, roles=["administrador"],
            institucion_id=None,
            nota_verificacion="Alta inicial por línea de órdenes, autorizada por quien opera el servicio",
            justificacion_dominio=None,
        )
    except servicio.ErrorCuentas as exc:
        print(f"No se pudo crear la invitación: {exc.mensaje}", file=sys.stderr)
        return 1
    conn.commit()
    # El enlace se muestra una sola vez y no se guarda en ningún registro.
    print("Invitación creada. Abre este enlace en las próximas 72 horas:")
    print(f"{config.origen_canonico}/cuenta/aceptar#t={token}")
    return 0


def _restablecer_factores(conn, args) -> int:
    fila = servicio._usuario_por_correo(conn, args.correo)
    if fila is None:
        print("No existe una cuenta con ese correo.", file=sys.stderr)
        return 1
    try:
        servicio.restablecer_factores(conn, str(fila[0]), actor=None, motivo=args.motivo)
    except servicio.ErrorCuentas as exc:
        print(exc.mensaje, file=sys.stderr)
        return 1
    conn.commit()
    print("Factores restablecidos. La persona debe ingresar con su contraseña y configurarlos de nuevo.")
    return 0


def _verificar_auditoria(conn, args) -> int:
    rota = auditoria.verificar_cadena(conn)
    if rota is None:
        print("La cadena de auditoría está íntegra.")
        return 0
    print(f"La cadena de auditoría no cuadra desde la fila {rota}.", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None, conn=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m api.cuentas.cli")
    sub = parser.add_subparsers(dest="orden", required=True)
    p = sub.add_parser("crear-admin", help="crea la invitación del primer administrador")
    p.add_argument("--correo", required=True)
    p.set_defaults(accion=_crear_admin)
    p = sub.add_parser("restablecer-factores", help="devuelve una cuenta al paso de configurar factores")
    p.add_argument("--correo", required=True)
    p.add_argument("--motivo", required=True)
    p.set_defaults(accion=_restablecer_factores)
    p = sub.add_parser("verificar-auditoria", help="comprueba la cadena de hashes de la auditoría")
    p.set_defaults(accion=_verificar_auditoria)
    args = parser.parse_args(argv)
    propia = conn is None
    conn = conn or _conectar()
    try:
        return args.accion(conn, args)
    finally:
        if propia:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
