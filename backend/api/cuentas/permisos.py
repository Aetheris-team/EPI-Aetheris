"""Política de permisos: una sola tabla de acción a roles.

Una acción nueva se agrega aquí y en la ruta con `requerir(...)`. La prueba de
la matriz recorre todas las rutas del árbol de FastAPI y falla si alguna ruta
privada no declara una acción de esta tabla.
"""

from __future__ import annotations

from .config import ROLES

# Todo lo que cualquier persona con sesión completa puede hacer sobre su propia cuenta.
CUALQUIER_SESION = "sesion"

POLITICA: dict[str, frozenset[str]] = {
    # Cuenta propia
    "cuenta.ver": frozenset(ROLES),
    "cuenta.cambiar_clave": frozenset(ROLES),
    "cuenta.gestionar_factores": frozenset(ROLES),
    "cuenta.cerrar_sesiones": frozenset(ROLES),
    # Administración de personas
    "admin.invitar": frozenset({"administrador"}),
    "admin.listar_usuarios": frozenset({"administrador"}),
    "admin.cambiar_roles": frozenset({"administrador"}),
    "admin.suspender": frozenset({"administrador"}),
    "admin.restablecer_factores": frozenset({"administrador"}),
    "admin.ver_aprobaciones": frozenset({"administrador"}),
    "admin.resolver_aprobaciones": frozenset({"administrador"}),
    "admin.gestionar_instituciones": frozenset({"administrador"}),
    "admin.ver_auditoria": frozenset({"administrador"}),
}

# Acciones que, además del rol, exigen haber confirmado la contraseña hace poco.
REQUIEREN_REAUTENTICACION = frozenset(
    {
        "cuenta.cambiar_clave",
        "cuenta.gestionar_factores",
        "admin.invitar",
        "admin.cambiar_roles",
        "admin.suspender",
        "admin.restablecer_factores",
        "admin.resolver_aprobaciones",
    }
)

# Acciones que un administrador solo puede hacer con llave de acceso. Invitar
# entra aquí porque una invitación puede crear otro administrador: sin esto,
# una sesión con solo contraseña y TOTP ampliaría el grupo que exige llave.
REQUIEREN_LLAVE = frozenset(
    {
        "admin.invitar",
        "admin.cambiar_roles",
        "admin.restablecer_factores",
        "admin.resolver_aprobaciones",
        "admin.suspender",
    }
)


def permitido(roles: set[str] | frozenset[str], accion: str) -> bool:
    permitidos = POLITICA.get(accion)
    return bool(permitidos and permitidos & set(roles))
