"""Correo transaccional: invitaciones, restablecer contraseña y avisos de seguridad.

Solo texto plano, sin imágenes ni seguimiento de apertura. La bandeja
`correos_salientes` guarda qué se envió y a quién, no el cuerpo: los enlaces
llevan un token de un solo uso que no debe quedar en la base. Si un envío
falla, se emite un token nuevo, no se reintenta el mismo.
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from .config import ConfigCuentas

PLANTILLAS: dict[str, tuple[str, str]] = {
    "invitacion": (
        "Invitación a EPI-Aetheris",
        "Hola {nombre},\n\n"
        "{invitador} te invita a crear una cuenta en EPI-Aetheris como {roles}.\n\n"
        "Para aceptar, abre este enlace en las próximas 72 horas:\n{enlace}\n\n"
        "Te pediremos elegir una contraseña y configurar un segundo factor.\n"
        "Si no esperabas esta invitación, puedes ignorar este mensaje.\n",
    ),
    "restablecer_clave": (
        "Restablecer tu contraseña de EPI-Aetheris",
        "Alguien pidió restablecer la contraseña de esta cuenta.\n\n"
        "Para elegir una nueva, abre este enlace en los próximos 30 minutos:\n{enlace}\n\n"
        "Si no fuiste tú, ignora este mensaje: tu contraseña no cambia mientras no uses el enlace.\n",
    ),
    "aviso_clave_cambiada": (
        "Tu contraseña de EPI-Aetheris cambió",
        "La contraseña de tu cuenta se cambió y se cerraron tus sesiones abiertas.\n\n"
        "Si no fuiste tú, pide a un administrador que suspenda tu cuenta.\n",
    ),
    "aviso_factor_agregado": (
        "Se agregó un segundo factor a tu cuenta",
        "Se agregó un nuevo segundo factor ({factor}) a tu cuenta de EPI-Aetheris.\n\n"
        "Si no fuiste tú, pide a un administrador que suspenda tu cuenta.\n",
    ),
    "aviso_factores_restablecidos": (
        "Se restablecieron los segundos factores de tu cuenta",
        "Un administrador restableció los segundos factores de tu cuenta de EPI-Aetheris.\n"
        "La próxima vez que ingreses con tu contraseña te pediremos configurarlos de nuevo.\n",
    ),
    "aprobacion_pendiente": (
        "Hay un restablecimiento de factores pendiente de tu aprobación",
        "{solicitante} pidió restablecer los segundos factores de la cuenta de administrador de {objetivo}.\n"
        "Motivo indicado: {motivo}\n\n"
        "Otro administrador, distinto de quien lo pidió y de la cuenta afectada, debe confirmarlo o rechazarlo "
        "antes de que caduque. Hazlo desde el panel de administración:\n{enlace}\n\n"
        "Si no reconoces la solicitud, recházala.\n",
    ),
    "aviso_codigo_recuperacion": (
        "Usaste un código de recuperación",
        "Se usó un código de recuperación para entrar a tu cuenta de EPI-Aetheris.\n"
        "Quedan {restantes} códigos. Configura un segundo factor nuevo cuando puedas.\n\n"
        "Si no fuiste tú, pide a un administrador que suspenda tu cuenta.\n",
    ),
}


@dataclass(frozen=True)
class Mensaje:
    destinatario: str
    asunto: str
    cuerpo: str


def construir(plantilla: str, destinatario: str, datos: dict[str, str]) -> Mensaje:
    asunto, cuerpo = PLANTILLAS[plantilla]
    # Los valores van como texto plano: no hay HTML que escapar, pero sí
    # saltos de línea que podrían inyectar cabeceras si llegaran al asunto.
    limpios = {k: str(v).replace("\r", " ").replace("\n", " ") for k, v in datos.items()}
    return Mensaje(destinatario=destinatario, asunto=asunto, cuerpo=cuerpo.format(**limpios))


class Remitente(Protocol):
    def enviar(self, config: ConfigCuentas, mensaje: Mensaje) -> None: ...


class RemitenteSmtp:
    def enviar(self, config: ConfigCuentas, mensaje: Mensaje) -> None:
        if not config.smtp.get("host"):
            raise RuntimeError("SMTP_HOST no está configurado")
        correo = EmailMessage()
        correo["From"] = config.correo_remitente
        correo["To"] = mensaje.destinatario
        correo["Subject"] = mensaje.asunto
        correo.set_content(mensaje.cuerpo)
        with smtplib.SMTP(config.smtp["host"], int(config.smtp["port"]), timeout=10) as smtp:
            if config.smtp.get("starttls", "true").lower() != "false":
                smtp.starttls(context=ssl.create_default_context())
            if config.smtp.get("usuario"):
                smtp.login(config.smtp["usuario"], config.smtp["clave"])
            smtp.send_message(correo)


@dataclass
class RemitenteEnMemoria:
    """Para pruebas: guarda lo enviado en vez de mandarlo."""

    enviados: list[Mensaje] = field(default_factory=list)
    fallar: bool = False

    def enviar(self, config: ConfigCuentas, mensaje: Mensaje) -> None:
        if self.fallar:
            raise RuntimeError("fallo simulado")
        self.enviados.append(mensaje)


def registrar_en_bandeja(conn, *, plantilla: str, destinatario: str, usuario_id: str | None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO correos_salientes (plantilla, destinatario, usuario_id) VALUES (%s, %s, %s) RETURNING id",
            (plantilla, destinatario, usuario_id),
        )
        return cur.fetchone()[0]


def despachar(config: ConfigCuentas, remitente: Remitente, abrir_conexion, bandeja_id: int, mensaje: Mensaje) -> bool:
    """Envía y anota el resultado. Se llama después de confirmar la
    transacción que lo originó, con una conexión propia."""
    try:
        remitente.enviar(config, mensaje)
        estado, error = "enviado", None
    except Exception as exc:  # el motivo no incluye el contenido del mensaje
        estado, error = "fallido", type(exc).__name__
    with abrir_conexion() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE correos_salientes SET estado = %s, error_codigo = %s, intentos = intentos + 1, "
                "enviado_en = CASE WHEN %s = 'enviado' THEN now() ELSE NULL END WHERE id = %s",
                (estado, error, estado, bandeja_id),
            )
        conn.commit()
    return estado == "enviado"
