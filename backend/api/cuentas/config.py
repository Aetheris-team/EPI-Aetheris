"""Configuración de cuentas leída del entorno.

Los secretos (pimientas y claves de cifrado) llegan como listas versionadas
`version:valor`, separadas por comas, la primera es la vigente. Así se puede
rotar una clave sin invalidar lo ya guardado: se agrega una nueva al inicio y
se conserva la anterior hasta que nada la use (ADR 0024, decisión C).
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field

COOKIE_SESION = "__Host-epi_sid"
ROLES = ("publicador", "revisor", "administrador")


class ConfiguracionInvalida(RuntimeError):
    pass


def _entero(nombre: str, defecto: int) -> int:
    return int(os.getenv(nombre, str(defecto)))


def _claves_versionadas(valor: str, nombre: str) -> tuple[dict[int, bytes], int]:
    claves: dict[int, bytes] = {}
    orden: list[int] = []
    for parte in valor.split(","):
        parte = parte.strip()
        if not parte:
            continue
        version, _, secreto = parte.partition(":")
        if not secreto or not version.isdigit():
            raise ConfiguracionInvalida(f"{nombre}: cada entrada debe ser 'version:valor'")
        try:
            bruto = base64.urlsafe_b64decode(secreto + "=" * (-len(secreto) % 4))
        except ValueError as exc:
            raise ConfiguracionInvalida(f"{nombre}: el valor no es base64 url-safe") from exc
        if len(bruto) < 32:
            raise ConfiguracionInvalida(f"{nombre}: cada clave debe tener al menos 32 bytes")
        claves[int(version)] = bruto
        orden.append(int(version))
    if not claves:
        raise ConfiguracionInvalida(f"{nombre} no está definida")
    # La vigente es la primera de la lista.
    return claves, orden[0]


@dataclass(frozen=True)
class ConfigCuentas:
    pimientas: dict[int, bytes]
    version_pimienta: int
    claves_cifrado: dict[int, bytes]
    version_cifrado: int
    origen_canonico: str
    rp_id: str
    rp_nombre: str = "EPI-Aetheris"
    emisor_totp: str = "EPI-Aetheris"
    inactividad_publica_s: int = 20 * 60
    inactividad_admin_s: int = 10 * 60
    absoluta_publica_s: int = 8 * 3600
    absoluta_admin_s: int = 4 * 3600
    sesion_segundo_factor_s: int = 5 * 60
    max_sesiones: int = 5
    reautenticacion_s: int = 5 * 60
    caduca_restablecer_s: int = 30 * 60
    caduca_invitacion_s: int = 72 * 3600
    caduca_verificar_correo_s: int = 24 * 3600
    # Plazo para que otro administrador confirme una acción que lo exige.
    caduca_aprobacion_s: int = 24 * 3600
    max_fallos_cuenta: int = 5
    ventana_fallos_s: int = 15 * 60
    consultar_hibp: bool = True
    cookie_segura: bool = True
    correo_remitente: str = "cuentas@epi-aetheris.dev"
    smtp: dict[str, str] = field(default_factory=dict)

    @property
    def pimienta_vigente(self) -> bytes:
        return self.pimientas[self.version_pimienta]

    @property
    def clave_cifrado_vigente(self) -> bytes:
        return self.claves_cifrado[self.version_cifrado]


def cargar_config() -> ConfigCuentas:
    origen = os.getenv("AUTH_ORIGEN_CANONICO", "http://localhost:4321").rstrip("/")
    rp_id = os.getenv("AUTH_RP_ID", "localhost")
    smtp = {
        "host": os.getenv("SMTP_HOST", ""),
        "port": os.getenv("SMTP_PORT", "587"),
        "usuario": os.getenv("SMTP_USUARIO", ""),
        "clave": os.getenv("SMTP_CLAVE", ""),
        "starttls": os.getenv("SMTP_STARTTLS", "true"),
    }
    pimientas, version_pimienta = _claves_versionadas(os.getenv("AUTH_PEPPERS", ""), "AUTH_PEPPERS")
    claves_cifrado, version_cifrado = _claves_versionadas(
        os.getenv("AUTH_CLAVES_CIFRADO", ""), "AUTH_CLAVES_CIFRADO"
    )
    return ConfigCuentas(
        pimientas=pimientas,
        version_pimienta=version_pimienta,
        claves_cifrado=claves_cifrado,
        version_cifrado=version_cifrado,
        origen_canonico=origen,
        rp_id=rp_id,
        consultar_hibp=os.getenv("AUTH_HIBP", "true").lower() != "false",
        cookie_segura=origen.startswith("https://"),
        correo_remitente=os.getenv("CORREO_REMITENTE", "cuentas@epi-aetheris.dev"),
        smtp=smtp,
        max_fallos_cuenta=_entero("AUTH_MAX_FALLOS_CUENTA", 5),
    )
