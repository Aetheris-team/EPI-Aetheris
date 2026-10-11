"""Reglas de negocio de las cuentas: invitación, alta, ingreso, segundo factor,
recuperación y administración de personas.

Cada función recibe una conexión y no confirma la transacción; registra su
propia auditoría en esa misma transacción. Los errores que se muestran a la
persona son `ErrorCuentas` con un mensaje apto para la interfaz.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import psycopg2.errors

from . import auditoria, contrasenas, intentos, recuperacion, sesiones, tokens, totp
from .config import ROLES, ConfigCuentas
from .sesiones import Sesion

VERSION_TERMINOS = "2026-10"
MENSAJE_CREDENCIALES = "Correo o contraseña incorrectos."


class ErrorCuentas(Exception):
    def __init__(self, codigo: str, mensaje: str, status: int = 400, espera_s: int | None = None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.status = status
        self.espera_s = espera_s


@dataclass(frozen=True)
class CorreoPendiente:
    """Un mensaje que hay que enviar después de confirmar la transacción."""

    plantilla: str
    destinatario: str
    usuario_id: str | None
    datos: dict[str, str]


def normalizar_correo(correo: str) -> str:
    return correo.strip().lower()


def _dominio(correo: str) -> str:
    return correo.rsplit("@", 1)[-1].lower()


def _usuario_por_correo(conn, correo: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, correo, nombre_visible, estado FROM usuarios WHERE lower(correo) = %s",
            (normalizar_correo(correo),),
        )
        return cur.fetchone()


def roles_de(conn, usuario_id: str) -> frozenset[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT rol FROM usuarios_roles WHERE usuario_id = %s AND revocado_en IS NULL", (usuario_id,))
        return frozenset(r[0] for r in cur.fetchall())


def factores_confirmados(conn, usuario_id: str) -> list[tuple[str, str, str]]:
    """[(id, tipo, etiqueta)] de los factores vigentes."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, tipo, etiqueta FROM factores_autenticacion "
            "WHERE usuario_id = %s AND revocado_en IS NULL AND confirmado_en IS NOT NULL ORDER BY creado_en",
            (usuario_id,),
        )
        return [(str(a), b, c) for a, b, c in cur.fetchall()]


# --- Invitaciones -------------------------------------------------------------

def crear_invitacion(
    conn,
    config: ConfigCuentas,
    *,
    invitador: Sesion | None,
    correo: str,
    roles: list[str],
    institucion_id: int | None,
    nota_verificacion: str,
    justificacion_dominio: str | None,
    red: str | None = None,
) -> tuple[str, str, CorreoPendiente]:
    """Devuelve (id de invitación, token, correo a enviar). `invitador` es None
    solo cuando la crea la línea de órdenes para el primer administrador."""
    correo = normalizar_correo(correo)
    roles = sorted(set(roles))
    if not roles or any(r not in ROLES for r in roles):
        raise ErrorCuentas("roles_invalidos", "Elige al menos un rol válido.")
    if len(nota_verificacion.strip()) < 10:
        raise ErrorCuentas("nota_corta", "Indica cómo verificaste a la persona (mínimo 10 caracteres).")
    if _usuario_por_correo(conn, correo) is not None:
        raise ErrorCuentas("correo_en_uso", "Ya existe una cuenta con ese correo.", 409)
    with conn.cursor() as cur:
        if institucion_id is not None:
            cur.execute("SELECT dominios_correo, activa FROM instituciones WHERE id = %s", (institucion_id,))
            fila = cur.fetchone()
            if fila is None or not fila[1]:
                raise ErrorCuentas("institucion_invalida", "La institución no existe o está inactiva.")
            dominios = fila[0] or []
            if dominios and _dominio(correo) not in dominios and not (justificacion_dominio or "").strip():
                raise ErrorCuentas(
                    "dominio_fuera_de_institucion",
                    "El correo no pertenece a los dominios de la institución. Escribe una justificación.",
                )
        cur.execute(
            "UPDATE invitaciones SET revocada_en = now() "
            "WHERE lower(correo) = %s AND aceptada_en IS NULL AND revocada_en IS NULL",
            (correo,),
        )
        token = tokens.generar()
        cur.execute(
            "INSERT INTO invitaciones (correo, institucion_id, roles_propuestos, token_hash, invitado_por, "
            "caduca_en, nota_verificacion, justificacion_dominio) "
            "VALUES (%s, %s, %s, %s, %s, now() + make_interval(secs => %s), %s, %s) RETURNING id",
            (
                correo, institucion_id, roles, tokens.hash_token(token),
                invitador.usuario_id if invitador else None,
                config.caduca_invitacion_s, nota_verificacion.strip(),
                (justificacion_dominio or "").strip() or None,
            ),
        )
        invitacion_id = str(cur.fetchone()[0])
    auditoria.registrar(
        conn,
        categoria="administracion",
        accion="invitacion_creada",
        actor_tipo="usuario" if invitador else "sistema",
        actor_id=invitador.usuario_id if invitador else None,
        sesion_id=invitador.id if invitador else None,
        objeto_tipo="invitacion",
        objeto_id=invitacion_id,
        detalle={"roles": roles, "institucion_id": institucion_id, "dominio_justificado": bool(justificacion_dominio)},
        red_truncada=red,
    )
    enlace = f"{config.origen_canonico}/cuenta/aceptar#t={token}"
    correo_pendiente = CorreoPendiente(
        plantilla="invitacion",
        destinatario=correo,
        usuario_id=None,
        datos={
            "nombre": correo.split("@")[0],
            "invitador": invitador.nombre_visible if invitador else "El equipo de EPI-Aetheris",
            "roles": ", ".join(roles),
            "enlace": enlace,
        },
    )
    return invitacion_id, token, correo_pendiente


def _invitacion_vigente(conn, token: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, correo, institucion_id, roles_propuestos, invitado_por FROM invitaciones "
            "WHERE token_hash = %s AND aceptada_en IS NULL AND revocada_en IS NULL AND caduca_en > now()",
            (tokens.hash_token(token),),
        )
        return cur.fetchone()


def ver_invitacion(conn, token: str) -> dict | None:
    """Lo mínimo que la página de aceptación necesita mostrar."""
    fila = _invitacion_vigente(conn, token)
    if fila is None:
        return None
    with conn.cursor() as cur:
        nombre = None
        if fila[2] is not None:
            cur.execute("SELECT nombre FROM instituciones WHERE id = %s", (fila[2],))
            nombre = cur.fetchone()[0]
    return {"correo": fila[1], "roles": list(fila[3]), "institucion": nombre, "terminos_version": VERSION_TERMINOS}


def aceptar_invitacion(
    conn,
    config: ConfigCuentas,
    *,
    token: str,
    nombre_visible: str,
    cargo: str | None,
    contrasena: str,
    terminos_version: str,
    agente: str | None,
    red: str | None,
) -> tuple[str, Sesion]:
    """Crea la cuenta (aún 'invitado') y abre una sesión de alta pendiente: la
    cuenta pasa a activa cuando confirma su segundo factor."""
    if terminos_version != VERSION_TERMINOS:
        raise ErrorCuentas("terminos", "Debes aceptar los términos vigentes.")
    nombre_visible = nombre_visible.strip()
    if not 2 <= len(nombre_visible) <= 120:
        raise ErrorCuentas("nombre_invalido", "El nombre debe tener entre 2 y 120 caracteres.")
    invitacion = _invitacion_vigente(conn, token)
    if invitacion is None:
        raise ErrorCuentas("invitacion_invalida", "La invitación no es válida o ya caducó.", 410)
    inv_id, correo, institucion_id, roles, invitado_por = invitacion
    try:
        normal = contrasenas.validar_politica(contrasena, datos_personales=(correo.split("@")[0], nombre_visible))
    except contrasenas.ContrasenaInvalida as exc:
        raise ErrorCuentas("contrasena_invalida", str(exc)) from exc
    if config.consultar_hibp and contrasenas.esta_filtrada(normal):
        raise ErrorCuentas("contrasena_filtrada", "Esa contraseña aparece en filtraciones conocidas. Elige otra.")
    with conn.cursor() as cur:
        # El consumo es lo que decide: dos aceptaciones simultáneas no pueden ganar las dos.
        cur.execute(
            "UPDATE invitaciones SET aceptada_en = now() WHERE id = %s AND aceptada_en IS NULL "
            "AND revocada_en IS NULL AND caduca_en > now() RETURNING id",
            (inv_id,),
        )
        if cur.fetchone() is None:
            raise ErrorCuentas("invitacion_invalida", "La invitación no es válida o ya caducó.", 410)
        cur.execute(
            "INSERT INTO usuarios (correo, correo_verificado_en, nombre_visible, cargo, institucion_id, estado, "
            "terminos_version, terminos_aceptados_en, creado_por) "
            "VALUES (%s, now(), %s, %s, %s, 'invitado', %s, now(), %s) RETURNING id",
            (correo, nombre_visible, (cargo or "").strip() or None, institucion_id, terminos_version, invitado_por),
        )
        uid = str(cur.fetchone()[0])
        cur.execute("UPDATE invitaciones SET usuario_id = %s WHERE id = %s", (uid, inv_id))
        for rol in roles:
            cur.execute(
                "INSERT INTO usuarios_roles (usuario_id, rol, otorgado_por) VALUES (%s, %s, %s)",
                (uid, rol, invitado_por),
            )
    _guardar_clave(conn, config, uid, normal)
    token_sesion, sid = sesiones.crear(
        conn, config, usuario_id=uid, nivel="alta_pendiente", metodos=["clave"], agente=agente, red=red, reciente=True
    )
    auditoria.registrar(
        conn, categoria="seguridad", accion="invitacion_aceptada", actor_id=uid, sesion_id=sid,
        objeto_tipo="usuario", objeto_id=uid, detalle={"roles": list(roles)}, red_truncada=red,
    )
    return token_sesion, sesiones.obtener(conn, config, token_sesion)


def _guardar_clave(conn, config: ConfigCuentas, usuario_id: str, normal: str) -> None:
    hash_, version = contrasenas.hashear(config, normal)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO credenciales_clave (usuario_id, hash, pepper_version) VALUES (%s, %s, %s) "
            "ON CONFLICT (usuario_id) DO UPDATE SET hash = EXCLUDED.hash, "
            "pepper_version = EXCLUDED.pepper_version, cambiada_en = now()",
            (usuario_id, hash_, version),
        )


# --- Ingreso ---------------------------------------------------------------------

def ingresar(
    conn, config: ConfigCuentas, *, correo: str, contrasena: str, ip: str | None, agente: str | None
) -> tuple[str, Sesion]:
    """Primer paso: contraseña. Abre una sesión intermedia que no concede
    permisos hasta completar el segundo factor. El mensaje de error es el mismo
    exista o no la cuenta."""
    correo = normalizar_correo(correo)
    k_cuenta = intentos.clave(config, "correo", correo)
    k_red = intentos.clave(config, "ip", ip or "desconocida")
    espera = max(intentos.segundos_de_espera(config, conn, k_cuenta), intentos.segundos_de_espera(config, conn, k_red))
    if espera:
        raise ErrorCuentas("demasiados_intentos", "Demasiados intentos. Espera antes de volver a probar.", 429, espera)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT u.id, u.estado, c.hash, c.pepper_version FROM usuarios u "
            "LEFT JOIN credenciales_clave c ON c.usuario_id = u.id WHERE lower(u.correo) = %s",
            (correo,),
        )
        fila = cur.fetchone()
    valida = contrasenas.verificar(config, contrasena, fila[2] if fila else None, fila[3] if fila else None)
    if not valida or fila[1] not in ("activo", "invitado"):
        intentos.registrar_fallo(config, conn, k_cuenta)
        intentos.registrar_fallo(config, conn, k_red)
        auditoria.registrar(
            conn, categoria="seguridad", accion="ingreso_fallido",
            actor_tipo="usuario" if fila else "anonimo", actor_id=str(fila[0]) if fila else None,
            red_truncada=auditoria.truncar_red(ip),
        )
        raise ErrorCuentas("credenciales", MENSAJE_CREDENCIALES, 401)
    uid, estado = str(fila[0]), fila[1]
    intentos.limpiar(conn, k_cuenta)
    if contrasenas.requiere_rehash(config, fila[2], fila[3]):
        _guardar_clave(conn, config, uid, contrasenas.normalizar(contrasena))
    nivel = "segundo_factor" if estado == "activo" else "alta_pendiente"
    token, sid = sesiones.crear(
        conn, config, usuario_id=uid, nivel=nivel, metodos=["clave"],
        agente=agente, red=auditoria.truncar_red(ip), reciente=True,
    )
    auditoria.registrar(
        conn, categoria="seguridad", accion="ingreso_clave_correcto", actor_id=uid, sesion_id=sid,
        red_truncada=auditoria.truncar_red(ip),
    )
    return token, sesiones.obtener(conn, config, token)


def _exigir_nivel(sesion: Sesion, nivel: str) -> None:
    if sesion.nivel != nivel:
        raise ErrorCuentas("sesion_en_otro_paso", "Esa acción no corresponde al paso actual del ingreso.", 403)


def _verificar_totp_de(conn, config: ConfigCuentas, usuario_id: str, codigo: str, *, solo_confirmados: bool = True):
    """Devuelve el id del factor TOTP que acepta el código, o None."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, totp_secreto_cifrado, totp_clave_version, totp_ultimo_paso FROM factores_autenticacion "
            "WHERE usuario_id = %s AND tipo = 'totp' AND revocado_en IS NULL "
            + ("AND confirmado_en IS NOT NULL " if solo_confirmados else "")
            + "ORDER BY creado_en FOR UPDATE",
            (usuario_id,),
        )
        factores = cur.fetchall()
        for fid, cifrado, version, ultimo in factores:
            secreto = totp.descifrar(config, cifrado, version, usuario_id)
            paso = totp.verificar(secreto, codigo, ultimo)
            if paso is not None:
                cur.execute(
                    "UPDATE factores_autenticacion SET totp_ultimo_paso = %s, ultimo_uso_en = now() WHERE id = %s",
                    (paso, fid),
                )
                return str(fid)
    return None


def _fallo_segundo_factor(conn, config: ConfigCuentas, sesion: Sesion, accion: str) -> None:
    k = intentos.clave(config, "correo", sesion.correo)
    intentos.registrar_fallo(config, conn, k)
    auditoria.registrar(conn, categoria="seguridad", accion=accion, actor_id=sesion.usuario_id, sesion_id=sesion.id)


def _control_espera(conn, config: ConfigCuentas, sesion: Sesion) -> None:
    espera = intentos.segundos_de_espera(config, conn, intentos.clave(config, "correo", sesion.correo))
    if espera:
        raise ErrorCuentas("demasiados_intentos", "Demasiados intentos. Espera antes de volver a probar.", 429, espera)


def completar_con_totp(conn, config: ConfigCuentas, sesion: Sesion, codigo: str) -> str:
    _exigir_nivel(sesion, "segundo_factor")
    _control_espera(conn, config, sesion)
    if _verificar_totp_de(conn, config, sesion.usuario_id, codigo) is None:
        _fallo_segundo_factor(conn, config, sesion, "segundo_factor_fallido")
        raise ErrorCuentas("codigo_incorrecto", "Código incorrecto.", 401)
    return _promover(conn, config, sesion, "totp")


def completar_con_recuperacion(conn, config: ConfigCuentas, sesion: Sesion, codigo: str) -> tuple[str, CorreoPendiente]:
    _exigir_nivel(sesion, "segundo_factor")
    _control_espera(conn, config, sesion)
    if not recuperacion.consumir(conn, sesion.usuario_id, codigo):
        _fallo_segundo_factor(conn, config, sesion, "recuperacion_fallida")
        raise ErrorCuentas("codigo_incorrecto", "Código incorrecto.", 401)
    nuevo = _promover(conn, config, sesion, "recuperacion")
    auditoria.registrar(
        conn, categoria="seguridad", accion="codigo_recuperacion_usado", actor_id=sesion.usuario_id, sesion_id=sesion.id
    )
    aviso = CorreoPendiente(
        "aviso_codigo_recuperacion", sesion.correo, sesion.usuario_id,
        {"restantes": str(recuperacion.restantes(conn, sesion.usuario_id))},
    )
    return nuevo, aviso


def _promover(conn, config: ConfigCuentas, sesion: Sesion, metodo: str) -> str:
    nuevo = sesiones.rotar(conn, config, sesion.id, nivel="completo", agregar_metodo=metodo, reautenticar=True)
    with conn.cursor() as cur:
        cur.execute("UPDATE usuarios SET ultimo_ingreso_en = now() WHERE id = %s", (sesion.usuario_id,))
    intentos.limpiar(conn, intentos.clave(config, "correo", sesion.correo))
    auditoria.registrar(
        conn, categoria="seguridad", accion="ingreso_completo", actor_id=sesion.usuario_id, sesion_id=sesion.id,
        detalle={"metodo": metodo},
    )
    return nuevo


def cerrar_sesion(conn, sesion: Sesion) -> None:
    sesiones.revocar(conn, sesion.id, "cierre_voluntario")
    auditoria.registrar(conn, categoria="seguridad", accion="sesion_cerrada", actor_id=sesion.usuario_id, sesion_id=sesion.id)


def reautenticar(conn, config: ConfigCuentas, sesion: Sesion, contrasena: str) -> str:
    _exigir_nivel(sesion, "completo")
    _control_espera(conn, config, sesion)
    with conn.cursor() as cur:
        cur.execute("SELECT hash, pepper_version FROM credenciales_clave WHERE usuario_id = %s", (sesion.usuario_id,))
        fila = cur.fetchone()
    if not contrasenas.verificar(config, contrasena, fila[0] if fila else None, fila[1] if fila else None):
        _fallo_segundo_factor(conn, config, sesion, "reautenticacion_fallida")
        raise ErrorCuentas("credenciales", "Contraseña incorrecta.", 401)
    nuevo = sesiones.rotar(conn, config, sesion.id, reautenticar=True)
    auditoria.registrar(conn, categoria="seguridad", accion="reautenticacion", actor_id=sesion.usuario_id, sesion_id=sesion.id)
    return nuevo


# --- Alta de segundo factor ----------------------------------------------------------

def iniciar_totp(conn, config: ConfigCuentas, sesion: Sesion, etiqueta: str) -> dict:
    if sesion.nivel not in ("alta_pendiente", "completo"):
        raise ErrorCuentas("sesion_en_otro_paso", "Termina primero el ingreso.", 403)
    etiqueta = etiqueta.strip() or "Aplicación de autenticación"
    secreto = totp.nuevo_secreto()
    cifrado, version = totp.cifrar(config, secreto, sesion.usuario_id)
    with conn.cursor() as cur:
        # Los intentos de configuración sin confirmar no se acumulan.
        cur.execute(
            "DELETE FROM factores_autenticacion WHERE usuario_id = %s AND tipo = 'totp' AND confirmado_en IS NULL",
            (sesion.usuario_id,),
        )
        cur.execute(
            "INSERT INTO factores_autenticacion (usuario_id, tipo, etiqueta, totp_secreto_cifrado, totp_clave_version) "
            "VALUES (%s, 'totp', %s, %s, %s) RETURNING id",
            (sesion.usuario_id, etiqueta[:60], cifrado, version),
        )
        fid = str(cur.fetchone()[0])
    uri = totp.uri_aprovisionamiento(config, secreto, sesion.correo)
    return {"factor_id": fid, "secreto": secreto, "uri": uri, "qr_svg": totp.qr_svg(uri)}


def confirmar_totp(conn, config: ConfigCuentas, sesion: Sesion, factor_id: str, codigo: str) -> dict:
    if sesion.nivel not in ("alta_pendiente", "completo"):
        raise ErrorCuentas("sesion_en_otro_paso", "Termina primero el ingreso.", 403)
    _control_espera(conn, config, sesion)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT totp_secreto_cifrado, totp_clave_version FROM factores_autenticacion "
            "WHERE id = %s AND usuario_id = %s AND tipo = 'totp' AND confirmado_en IS NULL AND revocado_en IS NULL "
            "FOR UPDATE",
            (factor_id, sesion.usuario_id),
        )
        fila = cur.fetchone()
        if fila is None:
            raise ErrorCuentas("factor_inexistente", "No hay una configuración pendiente con ese identificador.", 404)
        paso = totp.verificar(totp.descifrar(config, fila[0], fila[1], sesion.usuario_id), codigo, None)
        if paso is None:
            _fallo_segundo_factor(conn, config, sesion, "totp_confirmacion_fallida")
            raise ErrorCuentas("codigo_incorrecto", "Código incorrecto.", 401)
        cur.execute(
            "UPDATE factores_autenticacion SET confirmado_en = now(), totp_ultimo_paso = %s, ultimo_uso_en = now() "
            "WHERE id = %s",
            (paso, factor_id),
        )
    return _tras_factor_confirmado(conn, config, sesion, "totp")


def _tras_factor_confirmado(conn, config: ConfigCuentas, sesion: Sesion, tipo: str) -> dict:
    auditoria.registrar(
        conn, categoria="seguridad", accion="factor_agregado", actor_id=sesion.usuario_id, sesion_id=sesion.id,
        detalle={"tipo": tipo},
    )
    resultado: dict = {"activada": False, "codigos_recuperacion": None, "aviso": None}
    resultado["activada"] = _activar_si_cumple(conn, config, sesion)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM codigos_recuperacion WHERE usuario_id = %s LIMIT 1", (sesion.usuario_id,))
        primera_vez = cur.fetchone() is None
    if primera_vez and resultado["activada"]:
        resultado["codigos_recuperacion"] = recuperacion.generar_lote(conn, sesion.usuario_id)
    if sesion.nivel == "completo":
        resultado["aviso"] = CorreoPendiente("aviso_factor_agregado", sesion.correo, sesion.usuario_id, {"factor": tipo})
    return resultado


def _activar_si_cumple(conn, config: ConfigCuentas, sesion: Sesion) -> bool:
    """Pasa la cuenta de 'invitado' a 'activo' cuando cumple los requisitos:
    un factor confirmado y, si tiene el rol de administrador, una llave de
    acceso. Devuelve True si la cuenta quedó activa."""
    with conn.cursor() as cur:
        cur.execute("SELECT estado FROM usuarios WHERE id = %s FOR UPDATE", (sesion.usuario_id,))
        estado = cur.fetchone()[0]
    if estado == "activo":
        return True
    factores = factores_confirmados(conn, sesion.usuario_id)
    if not factores:
        return False
    if "administrador" in roles_de(conn, sesion.usuario_id) and not any(t == "webauthn" for _, t, _ in factores):
        return False
    with conn.cursor() as cur:
        cur.execute("UPDATE usuarios SET estado = 'activo' WHERE id = %s AND estado = 'invitado'", (sesion.usuario_id,))
    auditoria.registrar(
        conn, categoria="seguridad", accion="cuenta_activada", actor_id=sesion.usuario_id, sesion_id=sesion.id,
        objeto_tipo="usuario", objeto_id=sesion.usuario_id,
    )
    return True


def promover_alta(conn, config: ConfigCuentas, sesion: Sesion) -> str:
    """Tras activar la cuenta, la sesión de alta pasa a completa."""
    _exigir_nivel(sesion, "alta_pendiente")
    with conn.cursor() as cur:
        cur.execute("SELECT estado FROM usuarios WHERE id = %s", (sesion.usuario_id,))
        if cur.fetchone()[0] != "activo":
            raise ErrorCuentas("alta_incompleta", "Falta completar los factores de autenticación.", 409)
    return _promover(conn, config, sesion, "totp")


def revocar_factor(conn, config: ConfigCuentas, sesion: Sesion, factor_id: str) -> None:
    """Quita un factor propio. Siempre queda al menos uno, y un administrador
    conserva al menos una llave de acceso."""
    _exigir_nivel(sesion, "completo")
    factores = factores_confirmados(conn, sesion.usuario_id)
    objetivo = next((f for f in factores if f[0] == factor_id), None)
    if objetivo is None:
        raise ErrorCuentas("factor_inexistente", "No existe ese factor.", 404)
    restantes = [f for f in factores if f[0] != factor_id]
    if not restantes:
        raise ErrorCuentas("ultimo_factor", "Debes conservar al menos un segundo factor.", 409)
    if sesion.es_administrador and not any(t == "webauthn" for _, t, _ in restantes):
        raise ErrorCuentas("ultima_llave", "Un administrador debe conservar al menos una llave de acceso.", 409)
    with conn.cursor() as cur:
        cur.execute("UPDATE factores_autenticacion SET revocado_en = now() WHERE id = %s", (factor_id,))
    auditoria.registrar(
        conn, categoria="seguridad", accion="factor_revocado", actor_id=sesion.usuario_id, sesion_id=sesion.id,
        detalle={"tipo": objetivo[1]},
    )


# --- Restablecer contraseña ------------------------------------------------------------

def solicitar_restablecimiento(conn, config: ConfigCuentas, correo: str, ip: str | None) -> CorreoPendiente | None:
    """Devuelve el correo a enviar si la cuenta existe y está activa; la
    respuesta HTTP es la misma en ambos casos."""
    fila = _usuario_por_correo(conn, correo)
    auditoria.registrar(
        conn, categoria="seguridad", accion="restablecimiento_solicitado",
        actor_tipo="usuario" if fila else "anonimo", actor_id=str(fila[0]) if fila else None,
        red_truncada=auditoria.truncar_red(ip),
    )
    if fila is None or fila[3] != "activo":
        return None
    token = tokens.emitir(conn, proposito="restablecer_clave", usuario_id=str(fila[0]), caduca_s=config.caduca_restablecer_s)
    enlace = f"{config.origen_canonico}/cuenta/restablecer#t={token}"
    return CorreoPendiente("restablecer_clave", fila[1], str(fila[0]), {"enlace": enlace})


def restablecer_clave(conn, config: ConfigCuentas, *, token: str, contrasena: str, ip: str | None) -> CorreoPendiente:
    consumido = tokens.consumir(conn, proposito="restablecer_clave", token=token)
    if consumido is None:
        raise ErrorCuentas("token_invalido", "El enlace no es válido o ya caducó.", 410)
    with conn.cursor() as cur:
        cur.execute("SELECT correo, nombre_visible FROM usuarios WHERE id = %s AND estado = 'activo'", (consumido.usuario_id,))
        fila = cur.fetchone()
    if fila is None:
        raise ErrorCuentas("token_invalido", "El enlace no es válido o ya caducó.", 410)
    try:
        normal = contrasenas.validar_politica(contrasena, datos_personales=(fila[0].split("@")[0], fila[1]))
    except contrasenas.ContrasenaInvalida as exc:
        # El token ya se consumió con el UPDATE; se devuelve para que pueda reintentar.
        with conn.cursor() as cur:
            cur.execute("UPDATE tokens_un_solo_uso SET usado_en = NULL WHERE id = %s", (consumido.id,))
        raise ErrorCuentas("contrasena_invalida", str(exc)) from exc
    if config.consultar_hibp and contrasenas.esta_filtrada(normal):
        with conn.cursor() as cur:
            cur.execute("UPDATE tokens_un_solo_uso SET usado_en = NULL WHERE id = %s", (consumido.id,))
        raise ErrorCuentas("contrasena_filtrada", "Esa contraseña aparece en filtraciones conocidas. Elige otra.")
    _guardar_clave(conn, config, consumido.usuario_id, normal)
    cerradas = sesiones.revocar_todas(conn, consumido.usuario_id, "restablecimiento_de_clave")
    auditoria.registrar(
        conn, categoria="seguridad", accion="clave_restablecida", actor_id=consumido.usuario_id,
        detalle={"sesiones_cerradas": cerradas}, red_truncada=auditoria.truncar_red(ip),
    )
    return CorreoPendiente("aviso_clave_cambiada", fila[0], consumido.usuario_id, {})


def cambiar_clave(conn, config: ConfigCuentas, sesion: Sesion, *, actual: str, nueva: str) -> tuple[str, CorreoPendiente]:
    _exigir_nivel(sesion, "completo")
    _control_espera(conn, config, sesion)
    with conn.cursor() as cur:
        cur.execute("SELECT hash, pepper_version FROM credenciales_clave WHERE usuario_id = %s", (sesion.usuario_id,))
        fila = cur.fetchone()
    if not contrasenas.verificar(config, actual, fila[0] if fila else None, fila[1] if fila else None):
        _fallo_segundo_factor(conn, config, sesion, "cambio_clave_fallido")
        raise ErrorCuentas("credenciales", "La contraseña actual es incorrecta.", 401)
    try:
        normal = contrasenas.validar_politica(nueva, datos_personales=(sesion.correo.split("@")[0], sesion.nombre_visible))
    except contrasenas.ContrasenaInvalida as exc:
        raise ErrorCuentas("contrasena_invalida", str(exc)) from exc
    if config.consultar_hibp and contrasenas.esta_filtrada(normal):
        raise ErrorCuentas("contrasena_filtrada", "Esa contraseña aparece en filtraciones conocidas. Elige otra.")
    _guardar_clave(conn, config, sesion.usuario_id, normal)
    sesiones.revocar_todas(conn, sesion.usuario_id, "cambio_de_clave", excepto=sesion.id)
    nuevo = sesiones.rotar(conn, config, sesion.id, reautenticar=True)
    auditoria.registrar(conn, categoria="seguridad", accion="clave_cambiada", actor_id=sesion.usuario_id, sesion_id=sesion.id)
    return nuevo, CorreoPendiente("aviso_clave_cambiada", sesion.correo, sesion.usuario_id, {})


# --- Administración de personas -------------------------------------------------------------

# Número arbitrario y fijo: todas las operaciones que pueden reducir el grupo
# de administradores toman este bloqueo antes de contarlos. Sin él, dos
# administradores que se suspenden entre sí a la vez ven cada uno al otro como
# activo (READ COMMITTED) y ambos pasan la comprobación, y el sistema se queda
# sin administradores. El bloqueo se libera solo al cerrar la transacción.
_BLOQUEO_ADMINISTRADORES = 5_202_410_001


def _serializar_cambios_de_administradores(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (_BLOQUEO_ADMINISTRADORES,))


def _administradores_activos(conn, excluyendo: str | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(DISTINCT u.id) FROM usuarios u JOIN usuarios_roles r ON r.usuario_id = u.id "
            "WHERE u.estado = 'activo' AND r.rol = 'administrador' AND r.revocado_en IS NULL "
            "AND (%s::uuid IS NULL OR u.id <> %s::uuid)",
            (excluyendo, excluyendo),
        )
        return cur.fetchone()[0]


def listar_usuarios(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT u.id, u.correo, u.nombre_visible, u.estado, i.nombre, u.ultimo_ingreso_en, "
            "COALESCE(array_agg(r.rol ORDER BY r.rol) FILTER (WHERE r.rol IS NOT NULL), '{}') "
            "FROM usuarios u LEFT JOIN instituciones i ON i.id = u.institucion_id "
            "LEFT JOIN usuarios_roles r ON r.usuario_id = u.id AND r.revocado_en IS NULL "
            "WHERE u.estado <> 'sistema' GROUP BY u.id, i.nombre ORDER BY u.creado_en"
        )
        return [
            {"id": str(a), "correo": b, "nombre": c, "estado": d, "institucion": e,
             "ultimo_ingreso_en": f.isoformat() if f else None, "roles": list(g)}
            for a, b, c, d, e, f, g in cur.fetchall()
        ]


def cambiar_roles(conn, config: ConfigCuentas, actor: Sesion, usuario_id: str, roles: list[str]) -> None:
    roles = sorted(set(roles))
    if any(r not in ROLES for r in roles):
        raise ErrorCuentas("roles_invalidos", "Hay roles que no existen.")
    if usuario_id == actor.usuario_id:
        raise ErrorCuentas("sobre_uno_mismo", "No puedes cambiar tus propios roles.", 403)
    _serializar_cambios_de_administradores(conn)
    actuales = roles_de(conn, usuario_id)
    if "administrador" in actuales and "administrador" not in roles and _administradores_activos(conn, usuario_id) < 1:
        raise ErrorCuentas("ultimo_administrador", "No se puede dejar al sistema sin administradores.", 409)
    with conn.cursor() as cur:
        for rol in actuales - set(roles):
            cur.execute(
                "UPDATE usuarios_roles SET revocado_en = now() WHERE usuario_id = %s AND rol = %s AND revocado_en IS NULL",
                (usuario_id, rol),
            )
        for rol in set(roles) - actuales:
            cur.execute(
                "INSERT INTO usuarios_roles (usuario_id, rol, otorgado_por) VALUES (%s, %s, %s)",
                (usuario_id, rol, actor.usuario_id),
            )
    # Un cambio de privilegios invalida las sesiones de esa persona.
    sesiones.revocar_todas(conn, usuario_id, "cambio_de_roles")
    auditoria.registrar(
        conn, categoria="administracion", accion="roles_cambiados", actor_id=actor.usuario_id, sesion_id=actor.id,
        objeto_tipo="usuario", objeto_id=usuario_id, detalle={"antes": sorted(actuales), "despues": roles},
    )


def cambiar_estado(conn, actor: Sesion, usuario_id: str, nuevo_estado: str, motivo: str) -> None:
    if nuevo_estado not in ("activo", "suspendido", "baja"):
        raise ErrorCuentas("estado_invalido", "Estado no válido.")
    if usuario_id == actor.usuario_id:
        raise ErrorCuentas("sobre_uno_mismo", "No puedes cambiar el estado de tu propia cuenta.", 403)
    if len(motivo.strip()) < 5:
        raise ErrorCuentas("motivo_corto", "Escribe el motivo.")
    _serializar_cambios_de_administradores(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT estado FROM usuarios WHERE id = %s FOR UPDATE", (usuario_id,))
        fila = cur.fetchone()
        if fila is None or fila[0] == "sistema":
            raise ErrorCuentas("usuario_inexistente", "No existe esa persona.", 404)
        if nuevo_estado != "activo" and "administrador" in roles_de(conn, usuario_id) and _administradores_activos(conn, usuario_id) < 1:
            raise ErrorCuentas("ultimo_administrador", "No se puede dejar al sistema sin administradores.", 409)
        cur.execute(
            "UPDATE usuarios SET estado = %s, baja_en = CASE WHEN %s = 'baja' THEN now() ELSE baja_en END, "
            "baja_motivo = CASE WHEN %s <> 'activo' THEN %s ELSE NULL END WHERE id = %s",
            (nuevo_estado, nuevo_estado, nuevo_estado, motivo.strip(), usuario_id),
        )
    if nuevo_estado != "activo":
        sesiones.revocar_todas(conn, usuario_id, f"cuenta_{nuevo_estado}")
    auditoria.registrar(
        conn, categoria="administracion", accion=f"cuenta_{nuevo_estado}", actor_id=actor.usuario_id, sesion_id=actor.id,
        objeto_tipo="usuario", objeto_id=usuario_id, detalle={"motivo": motivo.strip()},
    )


def _es_uuid(valor: str) -> bool:
    try:
        uuid.UUID(str(valor))
    except ValueError:
        return False
    return True


def _es_administrador_activo(conn, usuario_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM usuarios u JOIN usuarios_roles r ON r.usuario_id = u.id "
            "WHERE u.id = %s AND u.estado = 'activo' AND r.rol = 'administrador' AND r.revocado_en IS NULL",
            (usuario_id,),
        )
        return cur.fetchone() is not None


def _administradores_activos_excepto(conn, excluyendo: list[str]) -> list[tuple[str, str, str]]:
    """[(id, correo, nombre)] de los administradores activos que no están en `excluyendo`."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT u.id, u.correo, u.nombre_visible FROM usuarios u "
            "JOIN usuarios_roles r ON r.usuario_id = u.id "
            "WHERE u.estado = 'activo' AND r.rol = 'administrador' AND r.revocado_en IS NULL "
            "AND NOT (u.id = ANY(%s::uuid[])) ORDER BY u.id",
            (excluyendo,),
        )
        return [(str(a), b, c) for a, b, c in cur.fetchall()]


def restablecer_factores(
    conn, usuario_id: str, *, actor: Sesion | None, motivo: str, aprobacion: dict | None = None
) -> CorreoPendiente | None:
    """Revoca factores y códigos y devuelve la cuenta al paso de alta: la
    persona entra con su contraseña y configura sus factores de nuevo.

    Sobre una cuenta de administrador, quien actúa como persona necesita una
    aprobación ya confirmada de otro administrador (`aprobacion`). La consola
    del propietario (`actor=None`) no la necesita: es la salida documentada
    cuando no hay un segundo administrador disponible."""
    if actor is not None and actor.usuario_id == usuario_id:
        raise ErrorCuentas("sobre_uno_mismo", "No puedes restablecer tus propios factores.", 403)
    if not _es_uuid(usuario_id):
        raise ErrorCuentas("usuario_inexistente", "No existe esa persona.", 404)
    with conn.cursor() as cur:
        cur.execute("SELECT correo, estado FROM usuarios WHERE id = %s FOR UPDATE", (usuario_id,))
        fila = cur.fetchone()
        if fila is None or fila[1] == "sistema":
            raise ErrorCuentas("usuario_inexistente", "No existe esa persona.", 404)
        if actor is not None and aprobacion is None and "administrador" in roles_de(conn, usuario_id):
            raise ErrorCuentas(
                "requiere_aprobacion",
                "Restablecer los factores de un administrador necesita la aprobación de otro administrador.",
                409,
            )
        cur.execute("UPDATE factores_autenticacion SET revocado_en = now() WHERE usuario_id = %s AND revocado_en IS NULL", (usuario_id,))
        cur.execute("UPDATE codigos_recuperacion SET usado_en = now() WHERE usuario_id = %s AND usado_en IS NULL", (usuario_id,))
        cur.execute("UPDATE usuarios SET estado = 'invitado' WHERE id = %s AND estado = 'activo'", (usuario_id,))
    cerradas = sesiones.revocar_todas(conn, usuario_id, "factores_restablecidos")
    auditoria.registrar(
        conn, categoria="administracion" if actor else "sistema", accion="factores_restablecidos",
        actor_tipo="usuario" if actor else "sistema", actor_id=actor.usuario_id if actor else None,
        sesion_id=actor.id if actor else None, objeto_tipo="usuario", objeto_id=usuario_id,
        detalle={"motivo": motivo, "sesiones_cerradas": cerradas, **(aprobacion or {})},
    )
    return CorreoPendiente("aviso_factores_restablecidos", fila[0], usuario_id, {})


@dataclass(frozen=True)
class ResultadoRestablecimiento:
    """`aprobacion` viene con datos solo cuando la acción quedó esperando a otro administrador."""

    correos: list[CorreoPendiente] = field(default_factory=list)
    aprobacion: dict | None = None

    @property
    def hecho(self) -> bool:
        return self.aprobacion is None


def solicitar_restablecimiento_de_factores(
    conn, config: ConfigCuentas, actor: Sesion, usuario_id: str, motivo: str
) -> ResultadoRestablecimiento:
    """Restablece de inmediato los factores de una cuenta que no es de
    administrador. Sobre un administrador abre una solicitud que otro
    administrador, distinto de quien la pide y de la cuenta afectada, debe
    confirmar con `confirmar_restablecimiento_de_factores`."""
    if actor.usuario_id == usuario_id:
        raise ErrorCuentas("sobre_uno_mismo", "No puedes restablecer tus propios factores.", 403)
    if not _es_uuid(usuario_id):
        raise ErrorCuentas("usuario_inexistente", "No existe esa persona.", 404)
    _serializar_cambios_de_administradores(conn)
    if "administrador" not in roles_de(conn, usuario_id):
        return ResultadoRestablecimiento(correos=[restablecer_factores(conn, usuario_id, actor=actor, motivo=motivo)])

    motivo = motivo.strip()
    if len(motivo) < 5:
        raise ErrorCuentas("motivo_corto", "Escribe el motivo.")
    with conn.cursor() as cur:
        cur.execute("SELECT nombre_visible FROM usuarios WHERE id = %s", (usuario_id,))
        objetivo = cur.fetchone()
    if objetivo is None:
        raise ErrorCuentas("usuario_inexistente", "No existe esa persona.", 404)
    _caducar_vencidas(conn)
    aprobadores = _administradores_activos_excepto(conn, [actor.usuario_id, usuario_id])
    if not aprobadores:
        raise ErrorCuentas(
            "sin_aprobador",
            "No hay otro administrador activo que pueda aprobarlo. Quien opera el servicio puede hacerlo desde la "
            "consola con `python -m api.cuentas.cli restablecer-factores`.",
            409,
        )
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM aprobaciones_administrativas WHERE accion = 'restablecer_factores' "
            "AND objetivo_id = %s AND estado = 'pendiente'",
            (usuario_id,),
        )
        if cur.fetchone():
            raise ErrorCuentas(
                "aprobacion_pendiente",
                "Ya hay una solicitud pendiente para esa cuenta. Espera a que otro administrador la resuelva o a que caduque.",
                409,
            )
        cur.execute(
            "INSERT INTO aprobaciones_administrativas (accion, objetivo_id, solicitante_id, motivo, caduca_en) "
            "VALUES ('restablecer_factores', %s, %s, %s, now() + make_interval(secs => %s)) RETURNING id, caduca_en",
            (usuario_id, actor.usuario_id, motivo, config.caduca_aprobacion_s),
        )
        aprobacion_id, caduca_en = cur.fetchone()
    auditoria.registrar(
        conn, categoria="administracion", accion="restablecimiento_factores_solicitado",
        actor_id=actor.usuario_id, sesion_id=actor.id, objeto_tipo="usuario", objeto_id=usuario_id,
        detalle={"aprobacion_id": str(aprobacion_id), "motivo": motivo, "caduca_en": caduca_en.isoformat()},
    )
    # Avisan a los demás administradores, incluida la cuenta afectada.
    datos = {
        "solicitante": actor.nombre_visible, "objetivo": objetivo[0], "motivo": motivo,
        "enlace": f"{config.origen_canonico}/admin/usuarios",
    }
    correos = [
        CorreoPendiente("aprobacion_pendiente", correo, uid, datos)
        for uid, correo, _ in _administradores_activos_excepto(conn, [actor.usuario_id])
    ]
    return ResultadoRestablecimiento(
        correos=correos, aprobacion={"id": str(aprobacion_id), "caduca_en": caduca_en.isoformat()}
    )


def _caducar_vencidas(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE aprobaciones_administrativas SET estado = 'caducada', resuelta_en = now() "
            "WHERE estado = 'pendiente' AND caduca_en <= now() RETURNING id, objetivo_id, solicitante_id"
        )
        vencidas = cur.fetchall()
    for aprobacion_id, objetivo_id, solicitante_id in vencidas:
        auditoria.registrar(
            conn, categoria="administracion", accion="restablecimiento_factores_caducado",
            actor_tipo="sistema", objeto_tipo="usuario", objeto_id=str(objetivo_id),
            detalle={"aprobacion_id": str(aprobacion_id), "solicitado_por": str(solicitante_id)},
        )


def _aprobacion_pendiente(conn, aprobacion_id: str) -> tuple:
    """Bloquea y devuelve (id, objetivo_id, solicitante_id, motivo) de una solicitud vigente."""
    if not _es_uuid(aprobacion_id):
        raise ErrorCuentas("aprobacion_inexistente", "No existe esa solicitud.", 404)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, objetivo_id, solicitante_id, motivo, estado, caduca_en <= now() "
            "FROM aprobaciones_administrativas WHERE id = %s FOR UPDATE",
            (aprobacion_id,),
        )
        fila = cur.fetchone()
    if fila is None:
        raise ErrorCuentas("aprobacion_inexistente", "No existe esa solicitud.", 404)
    if fila[4] != "pendiente":
        raise ErrorCuentas("aprobacion_resuelta", "Esa solicitud ya se resolvió.", 409)
    if fila[5]:
        _caducar_vencidas(conn)
        raise ErrorCuentas("aprobacion_caducada", "La solicitud caducó. Quien la pidió puede crear otra.", 410)
    return fila[0], str(fila[1]), str(fila[2]), fila[3]


def confirmar_restablecimiento_de_factores(conn, actor: Sesion, aprobacion_id: str) -> CorreoPendiente | None:
    """Segunda aprobación: ejecuta el restablecimiento que otro administrador pidió."""
    _serializar_cambios_de_administradores(conn)
    aprobacion_id, objetivo_id, solicitante_id, motivo = _aprobacion_pendiente(conn, aprobacion_id)
    if actor.usuario_id == solicitante_id:
        raise ErrorCuentas("autoaprobacion", "No puedes aprobar una solicitud que hiciste tú.", 403)
    if actor.usuario_id == objetivo_id:
        raise ErrorCuentas("sobre_uno_mismo", "No puedes aprobar el restablecimiento de tus propios factores.", 403)
    if not _es_administrador_activo(conn, actor.usuario_id):
        raise ErrorCuentas("sin_permiso", "No tienes permiso para esta acción.", 403)
    if not _es_administrador_activo(conn, solicitante_id):
        # Quien pidió ya no es administrador activo: la solicitud perdió a su responsable.
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE aprobaciones_administrativas SET estado = 'cancelada', resuelta_en = now() WHERE id = %s",
                (aprobacion_id,),
            )
        auditoria.registrar(
            conn, categoria="administracion", accion="restablecimiento_factores_cancelado", actor_tipo="sistema",
            objeto_tipo="usuario", objeto_id=objetivo_id,
            detalle={"aprobacion_id": str(aprobacion_id), "razon": "solicitante_sin_vigencia"},
        )
        raise ErrorCuentas("solicitante_sin_vigencia", "Quien pidió el restablecimiento ya no es administrador activo.", 409)
    aviso = restablecer_factores(
        conn, objetivo_id, actor=actor, motivo=motivo,
        aprobacion={
            "aprobacion_id": str(aprobacion_id), "solicitado_por": solicitante_id, "aprobado_por": actor.usuario_id,
        },
    )
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE aprobaciones_administrativas SET estado = 'aprobada', resuelta_por = %s, resuelta_en = now() WHERE id = %s",
            (actor.usuario_id, aprobacion_id),
        )
    return aviso


def rechazar_restablecimiento_de_factores(conn, actor: Sesion, aprobacion_id: str) -> None:
    """Cualquier administrador puede rechazar; si lo hace quien la pidió, queda como cancelada."""
    aprobacion_id, objetivo_id, solicitante_id, _ = _aprobacion_pendiente(conn, aprobacion_id)
    if not _es_administrador_activo(conn, actor.usuario_id):
        raise ErrorCuentas("sin_permiso", "No tienes permiso para esta acción.", 403)
    estado, accion = (
        ("cancelada", "restablecimiento_factores_cancelado")
        if actor.usuario_id == solicitante_id
        else ("rechazada", "restablecimiento_factores_rechazado")
    )
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE aprobaciones_administrativas SET estado = %s, resuelta_por = %s, resuelta_en = now() WHERE id = %s",
            (estado, actor.usuario_id, aprobacion_id),
        )
    auditoria.registrar(
        conn, categoria="administracion", accion=accion,
        actor_id=actor.usuario_id, sesion_id=actor.id, objeto_tipo="usuario", objeto_id=objetivo_id,
        detalle={"aprobacion_id": str(aprobacion_id), "solicitado_por": solicitante_id},
    )


def listar_aprobaciones(conn, actor: Sesion) -> list[dict]:
    """Solicitudes vigentes, con lo que `actor` puede hacer con cada una."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT a.id, a.accion, a.objetivo_id, o.nombre_visible, o.correo, a.solicitante_id, s.nombre_visible, "
            "a.motivo, a.creada_en, a.caduca_en FROM aprobaciones_administrativas a "
            "JOIN usuarios o ON o.id = a.objetivo_id JOIN usuarios s ON s.id = a.solicitante_id "
            "WHERE a.estado = 'pendiente' AND a.caduca_en > now() ORDER BY a.creada_en"
        )
        return [
            {
                "id": str(i), "accion": accion,
                "objetivo": {"id": str(oid), "nombre": onombre, "correo": ocorreo},
                "solicitante": {"id": str(sid), "nombre": snombre},
                "motivo": motivo, "creada_en": creada.isoformat(), "caduca_en": caduca.isoformat(),
                "es_propia": str(sid) == actor.usuario_id,
                "puede_confirmar": actor.usuario_id not in (str(sid), str(oid)),
            }
            for i, accion, oid, onombre, ocorreo, sid, snombre, motivo, creada, caduca in cur.fetchall()
        ]


def crear_institucion(conn, actor: Sesion | None, *, nombre: str, tipo: str, dominios: list[str], sitio_web: str | None) -> int:
    dominios = sorted({d.strip().lower() for d in dominios if d.strip()})
    with conn.cursor() as cur:
        # Punto de guardado: un nombre repetido no debe deshacer el resto de la transacción.
        cur.execute("SAVEPOINT nueva_institucion")
        try:
            cur.execute(
                "INSERT INTO instituciones (nombre, tipo, dominios_correo, sitio_web) VALUES (%s, %s, %s, %s) RETURNING id",
                (nombre.strip(), tipo, dominios, sitio_web),
            )
        except psycopg2.errors.UniqueViolation as exc:
            cur.execute("ROLLBACK TO SAVEPOINT nueva_institucion")
            raise ErrorCuentas("institucion_repetida", "Ya existe una institución con ese nombre.", 409) from exc
        except psycopg2.errors.CheckViolation as exc:
            cur.execute("ROLLBACK TO SAVEPOINT nueva_institucion")
            raise ErrorCuentas("institucion_invalida", "El tipo de institución no es válido.") from exc
        iid = cur.fetchone()[0]
    auditoria.registrar(
        conn, categoria="administracion", accion="institucion_creada",
        actor_tipo="usuario" if actor else "sistema", actor_id=actor.usuario_id if actor else None,
        sesion_id=actor.id if actor else None, objeto_tipo="institucion", objeto_id=str(iid), detalle={"tipo": tipo},
    )
    return iid


def verificar_institucion(conn, actor: Sesion, institucion_id: int, metodo: str) -> None:
    if len(metodo.strip()) < 10:
        raise ErrorCuentas("metodo_corto", "Describe cómo verificaste la institución (mínimo 10 caracteres).")
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE instituciones SET verificada_en = now(), verificada_por = %s, verificacion_metodo = %s "
            "WHERE id = %s RETURNING id",
            (actor.usuario_id, metodo.strip(), institucion_id),
        )
        if cur.fetchone() is None:
            raise ErrorCuentas("institucion_inexistente", "No existe esa institución.", 404)
    auditoria.registrar(
        conn, categoria="administracion", accion="institucion_verificada", actor_id=actor.usuario_id, sesion_id=actor.id,
        objeto_tipo="institucion", objeto_id=str(institucion_id), detalle={"metodo": metodo.strip()},
    )


def sesiones_propias(conn, sesion: Sesion) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, creada_en, ultima_actividad_en, agente_resumen, red_truncada FROM sesiones "
            "WHERE usuario_id = %s AND revocada_en IS NULL AND nivel = 'completo' ORDER BY creada_en DESC",
            (sesion.usuario_id,),
        )
        return [
            {"id": str(a), "creada_en": b.isoformat(), "ultima_actividad_en": c.isoformat(),
             "agente": d, "red": e, "actual": str(a) == sesion.id}
            for a, b, c, d, e in cur.fetchall()
        ]
