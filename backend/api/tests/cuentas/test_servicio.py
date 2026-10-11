import psycopg2.errors
import pyotp
import pytest

from api.cuentas import auditoria, correo, recuperacion, servicio, sesiones, tokens, totp
from api.cuentas.servicio import ErrorCuentas

CLAVE = "una clave bastante larga 1"


def _admin_sesion(conn, config, crear_usuario):
    uid = crear_usuario(roles=("administrador",))
    token, _ = sesiones.crear(conn, config, usuario_id=uid, nivel="completo", metodos=["clave", "webauthn"], reciente=True)
    return sesiones.obtener(conn, config, token)


def _invitar(conn, config, admin, correo="nueva@ejemplo.org", roles=("publicador",), **kw):
    kw.setdefault("institucion_id", None)
    kw.setdefault("nota_verificacion", "Confirmado por llamada con su jefatura")
    kw.setdefault("justificacion_dominio", None)
    return servicio.crear_invitacion(conn, config, invitador=admin, correo=correo, roles=list(roles), **kw)


def _aceptar(conn, config, token, **kw):
    kw.setdefault("nombre_visible", "Nueva Persona")
    kw.setdefault("cargo", None)
    kw.setdefault("contrasena", CLAVE)
    kw.setdefault("terminos_version", servicio.VERSION_TERMINOS)
    kw.setdefault("agente", "pruebas")
    kw.setdefault("red", None)
    return servicio.aceptar_invitacion(conn, config, token=token, **kw)


def _alta_completa(conn, config, admin, correo="nueva@ejemplo.org", roles=("publicador",)):
    """Invita, acepta y activa con TOTP. Devuelve (usuario_id, secreto)."""
    _, token, _ = _invitar(conn, config, admin, correo, roles)
    token_sesion, sesion = _aceptar(conn, config, token)
    datos = servicio.iniciar_totp(conn, config, sesion, "Teléfono")
    codigo = pyotp.TOTP(datos["secreto"]).now()
    resultado = servicio.confirmar_totp(conn, config, sesion, datos["factor_id"], codigo)
    assert resultado["activada"]
    return sesion.usuario_id, datos["secreto"], resultado


# --- invitaciones ---------------------------------------------------------------

def test_invitacion_y_alta(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    inv_id, token, correo = _invitar(conn, config, admin)
    assert correo.plantilla == "invitacion" and token in correo.datos["enlace"]
    assert servicio.ver_invitacion(conn, token)["correo"] == "nueva@ejemplo.org"
    uid, _, resultado = _alta_completa(conn, config, admin)
    assert len(resultado["codigos_recuperacion"]) == 10
    assert servicio.roles_de(conn, uid) == {"publicador"}
    # La invitación quedó consumida.
    assert servicio.ver_invitacion(conn, token) is None


def test_invitacion_no_se_acepta_dos_veces(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    _, token, _ = _invitar(conn, config, admin)
    _aceptar(conn, config, token)
    with pytest.raises(ErrorCuentas) as e:
        _aceptar(conn, config, token)
    assert e.value.codigo == "invitacion_invalida"


def test_invitacion_a_correo_ya_registrado(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    with pytest.raises(ErrorCuentas) as e:
        _invitar(conn, config, admin, correo="PERSONA1@ejemplo.org")
    assert e.value.codigo == "correo_en_uso"


def test_invitacion_nueva_revoca_la_anterior(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    _, viejo, _ = _invitar(conn, config, admin)
    _, nuevo, _ = _invitar(conn, config, admin)
    assert servicio.ver_invitacion(conn, viejo) is None
    assert servicio.ver_invitacion(conn, nuevo) is not None


def test_invitacion_caducada(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    inv_id, token, _ = _invitar(conn, config, admin)
    with conn.cursor() as cur:
        cur.execute("UPDATE invitaciones SET caduca_en = now() - interval '1 second' WHERE id = %s", (inv_id,))
    with pytest.raises(ErrorCuentas):
        _aceptar(conn, config, token)


@pytest.mark.parametrize("campo,valor,codigo", [
    ("roles", ("jefe",), "roles_invalidos"),
    ("roles", (), "roles_invalidos"),
    ("nota_verificacion", "corta", "nota_corta"),
])
def test_invitacion_validaciones(conn, config, crear_usuario, campo, valor, codigo):
    admin = _admin_sesion(conn, config, crear_usuario)
    with pytest.raises(ErrorCuentas) as e:
        _invitar(conn, config, admin, **{campo: valor})
    assert e.value.codigo == codigo


def test_dominio_fuera_de_la_institucion_exige_justificacion(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    iid = servicio.crear_institucion(conn, admin, nombre="Hospital de prueba", tipo="hospital", dominios=["hospital.gob.sv"], sitio_web=None)
    with pytest.raises(ErrorCuentas) as e:
        _invitar(conn, config, admin, correo="alguien@gmail.com", institucion_id=iid)
    assert e.value.codigo == "dominio_fuera_de_institucion"
    _invitar(conn, config, admin, correo="alguien@gmail.com", institucion_id=iid, justificacion_dominio="Usa correo personal por convenio")
    _invitar(conn, config, admin, correo="otra@hospital.gob.sv", institucion_id=iid)


def test_contrasena_debil_o_con_datos_personales_no_crea_cuenta(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    _, token, _ = _invitar(conn, config, admin)
    for mala in ("corta", "nueva-persona-2026!"):
        with pytest.raises(ErrorCuentas) as e:
            _aceptar(conn, config, token, contrasena=mala)
        assert e.value.codigo == "contrasena_invalida"
    # Falló antes de consumir: la invitación sigue sirviendo.
    assert servicio.ver_invitacion(conn, token) is not None


def test_terminos_obligatorios(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    _, token, _ = _invitar(conn, config, admin)
    with pytest.raises(ErrorCuentas) as e:
        _aceptar(conn, config, token, terminos_version="vieja")
    assert e.value.codigo == "terminos"


# --- alta: administrador necesita llave -----------------------------------------------

def test_administrador_no_se_activa_solo_con_totp(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    _, token, _ = _invitar(conn, config, admin, correo="otro.admin@ejemplo.org", roles=("administrador",))
    _, sesion = _aceptar(conn, config, token)
    datos = servicio.iniciar_totp(conn, config, sesion, "")
    r = servicio.confirmar_totp(conn, config, sesion, datos["factor_id"], pyotp.TOTP(datos["secreto"]).now())
    assert r["activada"] is False
    with pytest.raises(ErrorCuentas) as e:
        servicio.promover_alta(conn, config, sesion)
    assert e.value.codigo == "alta_incompleta"


def test_confirmar_totp_con_codigo_incorrecto(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    _, token, _ = _invitar(conn, config, admin)
    _, sesion = _aceptar(conn, config, token)
    datos = servicio.iniciar_totp(conn, config, sesion, "")
    with pytest.raises(ErrorCuentas) as e:
        servicio.confirmar_totp(conn, config, sesion, datos["factor_id"], "000000")
    assert e.value.codigo == "codigo_incorrecto"


# --- ingreso ---------------------------------------------------------------------------

def _ingreso_completo(conn, config, correo, secreto, ahora):
    token, sesion = servicio.ingresar(conn, config, correo=correo, contrasena=CLAVE, ip="203.0.113.7", agente="pruebas")
    assert sesion.nivel == "segundo_factor"
    nuevo = servicio.completar_con_totp(conn, config, sesion, pyotp.TOTP(secreto).at(ahora))
    return sesiones.obtener(conn, config, nuevo)


def test_ingreso_en_dos_pasos(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    uid, secreto, _ = _alta_completa(conn, config, admin)
    # El código de la confirmación ya se usó: hay que esperar al siguiente paso.
    import time
    ahora = time.time() + 30
    s = _ingreso_completo(conn, config, "NUEVA@ejemplo.org", secreto, ahora)
    assert s.nivel == "completo" and s.metodos == ("clave", "totp")


def test_un_codigo_totp_no_se_reutiliza(conn, config, crear_usuario):
    import time
    admin = _admin_sesion(conn, config, crear_usuario)
    uid, secreto, _ = _alta_completa(conn, config, admin)
    ahora = time.time() + 30
    _ingreso_completo(conn, config, "nueva@ejemplo.org", secreto, ahora)
    _, sesion = servicio.ingresar(conn, config, correo="nueva@ejemplo.org", contrasena=CLAVE, ip=None, agente=None)
    with pytest.raises(ErrorCuentas) as e:
        servicio.completar_con_totp(conn, config, sesion, pyotp.TOTP(secreto).at(ahora))
    assert e.value.codigo == "codigo_incorrecto"


def test_mensaje_igual_con_cuenta_inexistente_o_clave_mala(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    _alta_completa(conn, config, admin)
    mensajes = set()
    for correo, clave in (("nueva@ejemplo.org", "clave equivocada 123"), ("nadie@ejemplo.org", CLAVE)):
        with pytest.raises(ErrorCuentas) as e:
            servicio.ingresar(conn, config, correo=correo, contrasena=clave, ip=None, agente=None)
        mensajes.add((e.value.mensaje, e.value.status))
    assert len(mensajes) == 1


def test_bloqueo_por_intentos_fallidos(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    _alta_completa(conn, config, admin)
    for _ in range(config.max_fallos_cuenta):
        with pytest.raises(ErrorCuentas):
            servicio.ingresar(conn, config, correo="nueva@ejemplo.org", contrasena="mala mala mala 1", ip=None, agente=None)
    with pytest.raises(ErrorCuentas) as e:
        servicio.ingresar(conn, config, correo="nueva@ejemplo.org", contrasena=CLAVE, ip=None, agente=None)
    assert e.value.status == 429 and e.value.espera_s > 0


def test_cuenta_suspendida_no_ingresa(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    uid, _, _ = _alta_completa(conn, config, admin)
    servicio.cambiar_estado(conn, admin, uid, "suspendido", "Pruebas de suspensión")
    with pytest.raises(ErrorCuentas):
        servicio.ingresar(conn, config, correo="nueva@ejemplo.org", contrasena=CLAVE, ip=None, agente=None)


def test_segundo_factor_con_codigo_de_recuperacion(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    _, _, resultado = _alta_completa(conn, config, admin)
    _, sesion = servicio.ingresar(conn, config, correo="nueva@ejemplo.org", contrasena=CLAVE, ip=None, agente=None)
    nuevo, aviso = servicio.completar_con_recuperacion(conn, config, sesion, resultado["codigos_recuperacion"][0])
    assert aviso.plantilla == "aviso_codigo_recuperacion" and aviso.datos["restantes"] == "9"
    assert sesiones.obtener(conn, config, nuevo).metodos == ("clave", "recuperacion")


def test_un_paso_no_salta_al_siguiente(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    _alta_completa(conn, config, admin)
    _, sesion = servicio.ingresar(conn, config, correo="nueva@ejemplo.org", contrasena=CLAVE, ip=None, agente=None)
    with pytest.raises(ErrorCuentas) as e:
        servicio.cambiar_clave(conn, config, sesion, actual=CLAVE, nueva="otra clave bastante larga 2")
    assert e.value.codigo == "sesion_en_otro_paso"


# --- restablecer y cambiar contraseña ---------------------------------------------------------

def test_restablecer_clave(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    uid, _, _ = _alta_completa(conn, config, admin)
    abierta, _ = sesiones.crear(conn, config, usuario_id=uid, nivel="completo", metodos=["clave", "totp"])
    correo = servicio.solicitar_restablecimiento(conn, config, "Nueva@ejemplo.org", "198.51.100.1")
    token = correo.datos["enlace"].split("#t=")[1]
    aviso = servicio.restablecer_clave(conn, config, token=token, contrasena="frase distinta muy larga", ip=None)
    assert aviso.plantilla == "aviso_clave_cambiada"
    assert sesiones.obtener(conn, config, abierta) is None
    servicio.ingresar(conn, config, correo="nueva@ejemplo.org", contrasena="frase distinta muy larga", ip=None, agente=None)
    with pytest.raises(ErrorCuentas):
        servicio.restablecer_clave(conn, config, token=token, contrasena="otra clave bastante larga", ip=None)


def test_restablecer_no_revela_si_existe(conn, config):
    assert servicio.solicitar_restablecimiento(conn, config, "nadie@ejemplo.org", None) is None


def test_restablecer_con_clave_debil_conserva_el_token(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    _alta_completa(conn, config, admin)
    correo = servicio.solicitar_restablecimiento(conn, config, "nueva@ejemplo.org", None)
    token = correo.datos["enlace"].split("#t=")[1]
    with pytest.raises(ErrorCuentas):
        servicio.restablecer_clave(conn, config, token=token, contrasena="corta", ip=None)
    servicio.restablecer_clave(conn, config, token=token, contrasena="frase distinta muy larga", ip=None)


def test_cambiar_clave_cierra_las_demas_sesiones(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    uid, _, _ = _alta_completa(conn, config, admin)
    otra, _ = sesiones.crear(conn, config, usuario_id=uid, nivel="completo", metodos=["clave"])
    actual, _ = sesiones.crear(conn, config, usuario_id=uid, nivel="completo", metodos=["clave"])
    nuevo, _ = servicio.cambiar_clave(conn, config, sesiones.obtener(conn, config, actual), actual=CLAVE, nueva="frase distinta muy larga")
    assert sesiones.obtener(conn, config, otra) is None
    assert sesiones.obtener(conn, config, actual) is None  # el token anterior se rotó
    assert sesiones.obtener(conn, config, nuevo) is not None


# --- administración -------------------------------------------------------------------------------

def test_no_se_cambian_los_propios_roles(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    with pytest.raises(ErrorCuentas) as e:
        servicio.cambiar_roles(conn, config, admin, admin.usuario_id, ["administrador", "revisor"])
    assert e.value.codigo == "sobre_uno_mismo"


def test_no_se_deja_al_sistema_sin_administradores(conn, config, crear_usuario):
    with conn.cursor() as cur:  # aísla la prueba de administradores que ya haya en la base
        cur.execute("UPDATE usuarios_roles SET revocado_en = now() WHERE rol = 'administrador' AND revocado_en IS NULL")
    unico = _admin_sesion(conn, config, crear_usuario)
    # Quien actúa es otro administrador que ya no está activo, así que no cuenta.
    inactivo = type("Actor", (), {"usuario_id": crear_usuario(estado="suspendido", roles=("administrador",)), "id": None})()
    with pytest.raises(ErrorCuentas) as e:
        servicio.cambiar_estado(conn, inactivo, unico.usuario_id, "suspendido", "Prueba del último administrador")
    assert e.value.codigo == "ultimo_administrador"
    with pytest.raises(ErrorCuentas) as e:
        servicio.cambiar_roles(conn, config, inactivo, unico.usuario_id, ["publicador"])
    assert e.value.codigo == "ultimo_administrador"


def _tiene_el_bloqueo_de_administradores(conn) -> bool:
    # La auditoría también toma bloqueos asesores (cadena de hashes), así que se
    # busca el de administradores por su clave. pg_locks parte la clave bigint
    # en classid (32 bits altos) y objid (32 bajos).
    clave = servicio._BLOQUEO_ADMINISTRADORES
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid() "
            "AND classid = %s AND objid = %s AND objsubid = 1",
            (clave >> 32, clave & 0xFFFFFFFF),
        )
        return cur.fetchone()[0] == 1


def test_cambiar_estado_serializa_los_cambios_de_administradores(conn, config, crear_usuario):
    # Dos administradores que se suspenden entre sí a la vez pasarían ambos la
    # cuenta de "queda otro activo" (READ COMMITTED). El bloqueo asesor los
    # pone en fila; la prueba comprueba que se toma, sin simular la concurrencia.
    actor = _admin_sesion(conn, config, crear_usuario)
    otro = crear_usuario(roles=("administrador",))
    assert not _tiene_el_bloqueo_de_administradores(conn)
    servicio.cambiar_estado(conn, actor, otro, "suspendido", "Prueba de serialización")
    assert _tiene_el_bloqueo_de_administradores(conn)


def test_cambiar_roles_serializa_los_cambios_de_administradores(conn, config, crear_usuario):
    actor = _admin_sesion(conn, config, crear_usuario)
    otro = crear_usuario(roles=("administrador",))
    assert not _tiene_el_bloqueo_de_administradores(conn)
    servicio.cambiar_roles(conn, config, actor, otro, ["publicador"])
    assert _tiene_el_bloqueo_de_administradores(conn)


def test_cambio_de_roles_cierra_sesiones_y_audita(conn, config, crear_usuario):
    actor = _admin_sesion(conn, config, crear_usuario)
    uid = crear_usuario(roles=("publicador",))
    token, _ = sesiones.crear(conn, config, usuario_id=uid, nivel="completo", metodos=["clave", "totp"])
    servicio.cambiar_roles(conn, config, actor, uid, ["publicador", "revisor"])
    assert sesiones.obtener(conn, config, token) is None
    assert servicio.roles_de(conn, uid) == {"publicador", "revisor"}
    with conn.cursor() as cur:
        cur.execute("SELECT detalle FROM auditoria WHERE accion = 'roles_cambiados' AND objeto_id = %s", (uid,))
        assert cur.fetchone()[0]["despues"] == ["publicador", "revisor"]


def test_restablecer_factores_devuelve_la_cuenta_al_alta(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    uid, _, _ = _alta_completa(conn, config, admin)
    aviso = servicio.restablecer_factores(conn, uid, actor=admin, motivo="Perdió el teléfono")
    assert aviso.plantilla == "aviso_factores_restablecidos"
    assert recuperacion.restantes(conn, uid) == 0
    _, sesion = servicio.ingresar(conn, config, correo="nueva@ejemplo.org", contrasena=CLAVE, ip=None, agente=None)
    assert sesion.nivel == "alta_pendiente"


def test_no_se_restablecen_los_propios_factores(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    with pytest.raises(ErrorCuentas):
        servicio.restablecer_factores(conn, admin.usuario_id, actor=admin, motivo="no")


# --- restablecer factores de un administrador: segunda aprobación ---------------------------------

def _solo_estos_administradores(conn, *ids):
    """Aísla la prueba de administradores que ya haya en la base."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE usuarios_roles SET revocado_en = now() WHERE rol = 'administrador' AND revocado_en IS NULL "
            "AND NOT (usuario_id = ANY(%s::uuid[]))",
            (list(ids),),
        )


def _sesion_de(conn, config, uid):
    token, _ = sesiones.crear(conn, config, usuario_id=uid, nivel="completo", metodos=["clave", "webauthn"], reciente=True)
    return sesiones.obtener(conn, config, token)


def _administrador_con_factor(conn, crear_usuario) -> str:
    uid = crear_usuario(roles=("administrador",))
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO factores_autenticacion (usuario_id, tipo, etiqueta, totp_secreto_cifrado, totp_clave_version, confirmado_en) "
            "VALUES (%s, 'totp', 'Teléfono', %s, 1, now())",
            (uid, b"cifrado"),
        )
    return uid


def _tres_administradores(conn, config, crear_usuario):
    """Quien pide, la cuenta afectada (con TOTP y una sesión abierta) y quien puede aprobar."""
    pide = _admin_sesion(conn, config, crear_usuario)
    uid_objetivo = _administrador_con_factor(conn, crear_usuario)
    token_objetivo, _ = sesiones.crear(conn, config, usuario_id=uid_objetivo, nivel="completo", metodos=["clave", "totp"])
    aprueba = _admin_sesion(conn, config, crear_usuario)
    _solo_estos_administradores(conn, pide.usuario_id, uid_objetivo, aprueba.usuario_id)
    return pide, uid_objetivo, token_objetivo, aprueba


def _factores_vigentes(conn, uid) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM factores_autenticacion WHERE usuario_id = %s AND revocado_en IS NULL", (uid,))
        return cur.fetchone()[0]


def test_un_administrador_no_restablece_solo_los_factores_de_otro_administrador(conn, config, crear_usuario):
    pide, objetivo, token_objetivo, _ = _tres_administradores(conn, config, crear_usuario)
    assert _factores_vigentes(conn, objetivo) == 1
    resultado = servicio.solicitar_restablecimiento_de_factores(conn, config, pide, objetivo, "Perdió el teléfono")
    assert not resultado.hecho and resultado.aprobacion["id"]
    # Nada cambió en la cuenta afectada mientras nadie confirme.
    assert _factores_vigentes(conn, objetivo) == 1
    assert sesiones.obtener(conn, config, token_objetivo) is not None
    with conn.cursor() as cur:
        cur.execute("SELECT estado FROM usuarios WHERE id = %s", (objetivo,))
        assert cur.fetchone()[0] == "activo"


def test_la_funcion_de_bajo_nivel_tampoco_restablece_a_un_administrador_sin_aprobacion(conn, config, crear_usuario):
    pide, objetivo, _, _ = _tres_administradores(conn, config, crear_usuario)
    with pytest.raises(ErrorCuentas) as e:
        servicio.restablecer_factores(conn, objetivo, actor=pide, motivo="Perdió el teléfono")
    assert e.value.codigo == "requiere_aprobacion"
    assert _factores_vigentes(conn, objetivo) == 1


def test_otro_administrador_confirma_y_la_auditoria_nombra_a_los_dos(conn, config, crear_usuario):
    pide, objetivo, token_objetivo, aprueba = _tres_administradores(conn, config, crear_usuario)
    aprobacion = servicio.solicitar_restablecimiento_de_factores(conn, config, pide, objetivo, "Perdió el teléfono").aprobacion
    aviso = servicio.confirmar_restablecimiento_de_factores(conn, aprueba, aprobacion["id"])
    assert aviso.plantilla == "aviso_factores_restablecidos"
    assert _factores_vigentes(conn, objetivo) == 0
    assert sesiones.obtener(conn, config, token_objetivo) is None
    with conn.cursor() as cur:
        cur.execute("SELECT estado, resuelta_por FROM aprobaciones_administrativas WHERE id = %s", (aprobacion["id"],))
        assert cur.fetchone() == ("aprobada", aprueba.usuario_id)
        cur.execute("SELECT actor_id, detalle FROM auditoria WHERE accion = 'factores_restablecidos' AND objeto_id = %s", (objetivo,))
        actor, detalle = cur.fetchone()
        assert str(actor) == aprueba.usuario_id
        assert detalle["solicitado_por"] == pide.usuario_id and detalle["aprobado_por"] == aprueba.usuario_id
        assert detalle["aprobacion_id"] == aprobacion["id"]
        cur.execute("SELECT actor_id FROM auditoria WHERE accion = 'restablecimiento_factores_solicitado' AND objeto_id = %s", (objetivo,))
        assert str(cur.fetchone()[0]) == pide.usuario_id
    assert servicio.listar_aprobaciones(conn, aprueba) == []


def test_nadie_aprueba_su_propia_solicitud_ni_la_de_su_cuenta(conn, config, crear_usuario):
    pide, objetivo, token_objetivo, _ = _tres_administradores(conn, config, crear_usuario)
    aprobacion = servicio.solicitar_restablecimiento_de_factores(conn, config, pide, objetivo, "Perdió el teléfono").aprobacion
    with pytest.raises(ErrorCuentas) as e:
        servicio.confirmar_restablecimiento_de_factores(conn, pide, aprobacion["id"])
    assert e.value.codigo == "autoaprobacion"
    with pytest.raises(ErrorCuentas) as e:
        servicio.confirmar_restablecimiento_de_factores(conn, _sesion_de(conn, config, objetivo), aprobacion["id"])
    assert e.value.codigo == "sobre_uno_mismo"
    assert _factores_vigentes(conn, objetivo) == 1
    assert sesiones.obtener(conn, config, token_objetivo) is not None


def test_la_base_rechaza_una_aprobacion_del_propio_solicitante(conn, config, crear_usuario):
    pide, objetivo, _, _ = _tres_administradores(conn, config, crear_usuario)
    aprobacion = servicio.solicitar_restablecimiento_de_factores(conn, config, pide, objetivo, "Perdió el teléfono").aprobacion
    with conn.cursor() as cur:
        cur.execute("SAVEPOINT intento")
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                "UPDATE aprobaciones_administrativas SET estado = 'aprobada', resuelta_por = solicitante_id, "
                "resuelta_en = now() WHERE id = %s",
                (aprobacion["id"],),
            )
        cur.execute("ROLLBACK TO SAVEPOINT intento")


def test_la_solicitud_caduca(conn, config, crear_usuario):
    pide, objetivo, token_objetivo, aprueba = _tres_administradores(conn, config, crear_usuario)
    aprobacion = servicio.solicitar_restablecimiento_de_factores(conn, config, pide, objetivo, "Perdió el teléfono").aprobacion
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE aprobaciones_administrativas SET creada_en = now() - interval '2 days', "
            "caduca_en = now() - interval '1 day' WHERE id = %s",
            (aprobacion["id"],),
        )
    assert servicio.listar_aprobaciones(conn, aprueba) == []
    with pytest.raises(ErrorCuentas) as e:
        servicio.confirmar_restablecimiento_de_factores(conn, aprueba, aprobacion["id"])
    assert e.value.codigo == "aprobacion_caducada" and e.value.status == 410
    assert _factores_vigentes(conn, objetivo) == 1
    assert sesiones.obtener(conn, config, token_objetivo) is not None
    with conn.cursor() as cur:
        cur.execute("SELECT estado FROM aprobaciones_administrativas WHERE id = %s", (aprobacion["id"],))
        assert cur.fetchone()[0] == "caducada"
    # Con la anterior caducada se puede pedir otra.
    assert not servicio.solicitar_restablecimiento_de_factores(conn, config, pide, objetivo, "Perdió el teléfono").hecho


def test_sin_otro_administrador_la_solicitud_se_niega_y_la_consola_sigue_siendo_la_salida(conn, config, crear_usuario):
    pide = _admin_sesion(conn, config, crear_usuario)
    objetivo = _administrador_con_factor(conn, crear_usuario)
    _solo_estos_administradores(conn, pide.usuario_id, objetivo)
    with pytest.raises(ErrorCuentas) as e:
        servicio.solicitar_restablecimiento_de_factores(conn, config, pide, objetivo, "Perdió el teléfono")
    assert e.value.codigo == "sin_aprobador" and "cli" in e.value.mensaje
    assert _factores_vigentes(conn, objetivo) == 1
    # La consola del propietario no necesita aprobación y deja actor 'sistema'.
    servicio.restablecer_factores(conn, objetivo, actor=None, motivo="Salida de la consola")
    assert _factores_vigentes(conn, objetivo) == 0


def test_no_hay_dos_solicitudes_pendientes_para_la_misma_cuenta(conn, config, crear_usuario):
    pide, objetivo, _, aprueba = _tres_administradores(conn, config, crear_usuario)
    servicio.solicitar_restablecimiento_de_factores(conn, config, pide, objetivo, "Perdió el teléfono")
    for actor in (pide, aprueba):
        with pytest.raises(ErrorCuentas) as e:
            servicio.solicitar_restablecimiento_de_factores(conn, config, actor, objetivo, "Otra vez, por si acaso")
        assert e.value.codigo == "aprobacion_pendiente"


def test_rechazar_y_cancelar_dejan_la_cuenta_intacta(conn, config, crear_usuario):
    pide, objetivo, _, aprueba = _tres_administradores(conn, config, crear_usuario)
    primera = servicio.solicitar_restablecimiento_de_factores(conn, config, pide, objetivo, "Perdió el teléfono").aprobacion
    servicio.rechazar_restablecimiento_de_factores(conn, aprueba, primera["id"])
    segunda = servicio.solicitar_restablecimiento_de_factores(conn, config, pide, objetivo, "Perdió el teléfono").aprobacion
    servicio.rechazar_restablecimiento_de_factores(conn, pide, segunda["id"])
    with conn.cursor() as cur:
        cur.execute("SELECT estado FROM aprobaciones_administrativas WHERE id IN (%s, %s) ORDER BY creada_en", (primera["id"], segunda["id"]))
        assert [f[0] for f in cur.fetchall()] == ["rechazada", "cancelada"]
    with pytest.raises(ErrorCuentas) as e:
        servicio.confirmar_restablecimiento_de_factores(conn, aprueba, primera["id"])
    assert e.value.codigo == "aprobacion_resuelta"
    assert _factores_vigentes(conn, objetivo) == 1


def test_si_quien_pidio_ya_no_es_administrador_no_se_ejecuta(conn, config, crear_usuario):
    pide, objetivo, _, aprueba = _tres_administradores(conn, config, crear_usuario)
    aprobacion = servicio.solicitar_restablecimiento_de_factores(conn, config, pide, objetivo, "Perdió el teléfono").aprobacion
    servicio.cambiar_estado(conn, aprueba, pide.usuario_id, "suspendido", "Cuenta comprometida")
    with pytest.raises(ErrorCuentas) as e:
        servicio.confirmar_restablecimiento_de_factores(conn, aprueba, aprobacion["id"])
    assert e.value.codigo == "solicitante_sin_vigencia"
    assert _factores_vigentes(conn, objetivo) == 1


def test_la_solicitud_avisa_a_los_demas_administradores(conn, config, crear_usuario):
    pide, objetivo, _, aprueba = _tres_administradores(conn, config, crear_usuario)
    resultado = servicio.solicitar_restablecimiento_de_factores(conn, config, pide, objetivo, "Perdió el teléfono")
    assert {c.usuario_id for c in resultado.correos} == {objetivo, aprueba.usuario_id}
    assert all(c.plantilla == "aprobacion_pendiente" for c in resultado.correos)
    construido = correo.construir("aprobacion_pendiente", "x@ejemplo.org", resultado.correos[0].datos)
    assert "/admin/usuarios" in construido.cuerpo


def test_restablecer_a_alguien_que_no_es_administrador_sigue_siendo_inmediato(conn, config, crear_usuario):
    pide, _, _, _ = _tres_administradores(conn, config, crear_usuario)
    uid, _, _ = _alta_completa(conn, config, pide, correo="publicadora@ejemplo.org")
    resultado = servicio.solicitar_restablecimiento_de_factores(conn, config, pide, uid, "Perdió el teléfono")
    assert resultado.hecho and _factores_vigentes(conn, uid) == 0


def test_auditoria_encadenada_y_sin_secretos(conn, config, crear_usuario):
    admin = _admin_sesion(conn, config, crear_usuario)
    _alta_completa(conn, config, admin)
    assert auditoria.verificar_cadena(conn) is None
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM auditoria WHERE detalle::text ~* '(contrasena|secreto|token)'")
        assert cur.fetchone()[0] == 0
    with pytest.raises(ValueError):
        auditoria.registrar(conn, categoria="seguridad", accion="x", detalle={"contrasena": "no"})


def test_red_truncada():
    assert auditoria.truncar_red("203.0.113.77") == "203.0.113.0/24"
    assert auditoria.truncar_red("2001:db8:abcd:1234::1") == "2001:db8:abcd::/48"
    assert auditoria.truncar_red("no-es-ip") is None and auditoria.truncar_red(None) is None
