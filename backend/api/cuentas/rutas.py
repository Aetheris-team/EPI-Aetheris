"""Rutas HTTP de cuentas: `/api/cuenta/*` (la persona sobre sí misma) y
`/api/admin/*` (administración).

El router se arma con una fábrica para no importar `main.py` (que es quien lo
incluye) y para poder probarlo con una base y un correo de pruebas.

Toda ruta declara una de tres cosas: está en RUTAS_SIN_SESION, exige un nivel
de sesión concreto (`en_nivel`) o exige una acción de la tabla de permisos
(`requerir`). Una prueba recorre el árbol de rutas y falla si alguna no declara
ninguna.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import auditoria, contrasenas, correo, csrf, llaves, permisos, servicio, sesiones
from .config import COOKIE_SESION, ConfigCuentas
from .servicio import CorreoPendiente, ErrorCuentas
from .sesiones import Sesion

# Rutas que se usan sin sesión. Todo lo demás exige sesión.
RUTAS_SIN_SESION = frozenset(
    {
        ("POST", "/api/cuenta/ingresar"),
        ("POST", "/api/cuenta/clave/olvide"),
        ("POST", "/api/cuenta/clave/restablecer"),
        ("POST", "/api/cuenta/invitacion/ver"),
        ("POST", "/api/cuenta/invitacion/aceptar"),
        ("GET", "/api/cuenta/sesion"),
    }
)


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class IngresoIn(_Entrada):
    correo: str = Field(max_length=254)
    contrasena: str = Field(max_length=256)


class CodigoIn(_Entrada):
    codigo: str = Field(max_length=32)


class CorreoIn(_Entrada):
    correo: str = Field(max_length=254)


class RestablecerIn(_Entrada):
    token: str = Field(max_length=200)
    contrasena: str = Field(max_length=256)


class TokenIn(_Entrada):
    token: str = Field(max_length=200)


class AceptarIn(_Entrada):
    token: str = Field(max_length=200)
    nombre_visible: str = Field(max_length=120)
    cargo: str | None = Field(default=None, max_length=120)
    contrasena: str = Field(max_length=256)
    terminos_version: str = Field(max_length=40)


class EtiquetaIn(_Entrada):
    etiqueta: str = Field(default="", max_length=60)


class ConfirmarTotpIn(_Entrada):
    factor_id: str = Field(max_length=40)
    codigo: str = Field(max_length=32)


class LlaveIn(_Entrada):
    credencial: dict
    etiqueta: str = Field(default="", max_length=60)


class CredencialIn(_Entrada):
    credencial: dict


class ReautenticarIn(_Entrada):
    contrasena: str = Field(max_length=256)


class CambiarClaveIn(_Entrada):
    actual: str = Field(max_length=256)
    nueva: str = Field(max_length=256)


class InvitarIn(_Entrada):
    correo: str = Field(max_length=254)
    roles: list[str] = Field(max_length=3)
    institucion_id: int | None = None
    nota_verificacion: str = Field(max_length=500)
    justificacion_dominio: str | None = Field(default=None, max_length=500)


class RolesIn(_Entrada):
    roles: list[str] = Field(max_length=3)


class EstadoIn(_Entrada):
    estado: str = Field(max_length=20)
    motivo: str = Field(max_length=500)


class MotivoIn(_Entrada):
    motivo: str = Field(max_length=500)


class InstitucionIn(_Entrada):
    nombre: str = Field(min_length=2, max_length=200)
    tipo: str = Field(max_length=20)
    dominios_correo: list[str] = Field(default_factory=list, max_length=20)
    sitio_web: str | None = Field(default=None, max_length=300)

    @field_validator("sitio_web")
    @classmethod
    def _solo_http(cls, valor: str | None) -> str | None:
        # Solo http(s): un esquema como javascript: o data: en un href futuro
        # ejecutaría código en quien haga clic.
        if valor is None or not valor.strip():
            return None
        partes = urlparse(valor.strip())
        if partes.scheme not in ("http", "https") or not partes.netloc:
            raise ValueError("El sitio web debe empezar por http:// o https://")
        return valor.strip()


class VerificarInstitucionIn(_Entrada):
    metodo: str = Field(max_length=500)


def _http(exc: ErrorCuentas) -> HTTPException:
    cabeceras = {"Retry-After": str(exc.espera_s)} if exc.espera_s else None
    return HTTPException(
        status_code=exc.status,
        detail={"codigo": exc.codigo, "mensaje": exc.mensaje, "espera_s": exc.espera_s},
        headers=cabeceras,
    )


def _http_saturado(exc: contrasenas.Saturado) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "codigo": "servidor_ocupado",
            "mensaje": "Hay muchas verificaciones en curso. Vuelve a intentarlo en unos segundos.",
            "espera_s": exc.espera_s,
        },
        headers={"Retry-After": str(exc.espera_s)},
    )


def crear_router(
    *,
    limiter,
    abrir_conexion: Callable,
    limite_auth: str,
    config_fn: Callable[[], ConfigCuentas],
    remitente: correo.Remitente,
    ip_fn: Callable[[Request], str],
) -> APIRouter:
    router = APIRouter()

    @contextmanager
    def tx():
        """Una transacción por petición. Se confirma también cuando el servicio
        lanza ErrorCuentas: ahí están los registros de intentos fallidos y de
        auditoría que deben sobrevivir al rechazo."""
        with abrir_conexion() as conn:
            try:
                yield conn
            except ErrorCuentas as exc:
                conn.commit()
                raise _http(exc) from exc
            except contrasenas.Saturado as exc:
                # No es un intento fallido: no se registra nada.
                conn.rollback()
                raise _http_saturado(exc) from exc
            except BaseException:
                conn.rollback()
                raise
            else:
                conn.commit()

    def _config() -> ConfigCuentas:
        try:
            return config_fn()
        except Exception as exc:
            raise HTTPException(503, detail={"codigo": "cuentas_no_configuradas", "mensaje": "Las cuentas no están disponibles."}) from exc

    def _nombre_cookie(config: ConfigCuentas) -> str:
        return COOKIE_SESION if config.cookie_segura else "epi_sid"

    def _poner_cookie(response: Response, config: ConfigCuentas, token: str) -> None:
        response.set_cookie(
            _nombre_cookie(config), token, httponly=True, secure=config.cookie_segura,
            samesite="strict", path="/",
        )

    def _quitar_cookie(response: Response, config: ConfigCuentas) -> None:
        response.delete_cookie(_nombre_cookie(config), path="/", secure=config.cookie_segura, httponly=True, samesite="strict")

    def _enviar(tareas: BackgroundTasks, conn, config: ConfigCuentas, pendiente: CorreoPendiente | None) -> None:
        if pendiente is None:
            return
        bandeja_id = correo.registrar_en_bandeja(
            conn, plantilla=pendiente.plantilla, destinatario=pendiente.destinatario, usuario_id=pendiente.usuario_id
        )
        mensaje = correo.construir(pendiente.plantilla, pendiente.destinatario, pendiente.datos)
        tareas.add_task(correo.despachar, config, remitente, _abrir_y_confirmar, bandeja_id, mensaje)

    @contextmanager
    def _abrir_y_confirmar():
        with abrir_conexion() as conn:
            yield conn

    def verificar_origen(request: Request, config: ConfigCuentas = Depends(_config)) -> None:
        """Toda petición que cambia estado debe venir del origen canónico."""
        if request.method not in csrf.METODOS_SEGUROS and not csrf.origen_valido(config, request.headers.get("origin")):
            raise HTTPException(403, detail={"codigo": "origen", "mensaje": "Origen no permitido."})

    def _sesion_de(request: Request, config: ConfigCuentas) -> Sesion | None:
        token = request.cookies.get(_nombre_cookie(config))
        if not token:
            return None
        with abrir_conexion() as conn:
            sesion = sesiones.obtener(conn, config, token)
            conn.commit()
        return sesion

    def _exigir_csrf(request: Request, config: ConfigCuentas, sesion: Sesion) -> None:
        if request.method not in csrf.METODOS_SEGUROS and not csrf.token_valido(
            config, sesion.id, request.headers.get("x-csrf-token")
        ):
            raise HTTPException(403, detail={"codigo": "csrf", "mensaje": "Falta o no coincide el token de la sesión."})

    def en_nivel(*niveles: str):
        def dependencia(request: Request, config: ConfigCuentas = Depends(_config)) -> Sesion:
            sesion = _sesion_de(request, config)
            if sesion is None:
                raise HTTPException(401, detail={"codigo": "sin_sesion", "mensaje": "Inicia sesión para continuar."})
            _exigir_csrf(request, config, sesion)
            if sesion.nivel not in niveles:
                raise HTTPException(403, detail={"codigo": "sesion_en_otro_paso", "mensaje": "Esa acción no corresponde al paso actual."})
            return sesion

        dependencia.nivel = niveles
        return dependencia

    def requerir(accion: str):
        if accion not in permisos.POLITICA:
            raise ValueError(f"Acción sin política: {accion}")

        def dependencia(request: Request, config: ConfigCuentas = Depends(_config)) -> Sesion:
            sesion = _sesion_de(request, config)
            if sesion is None:
                raise HTTPException(401, detail={"codigo": "sin_sesion", "mensaje": "Inicia sesión para continuar."})
            _exigir_csrf(request, config, sesion)
            if sesion.nivel != "completo":
                raise HTTPException(403, detail={"codigo": "sesion_en_otro_paso", "mensaje": "Termina el ingreso primero."})
            if not permisos.permitido(sesion.roles, accion):
                raise HTTPException(403, detail={"codigo": "sin_permiso", "mensaje": "No tienes permiso para esta acción."})
            if accion in permisos.REQUIEREN_LLAVE and not sesion.usa_llave:
                raise HTTPException(403, detail={"codigo": "requiere_llave", "mensaje": "Esta acción exige haber ingresado con una llave de acceso."})
            if accion in permisos.REQUIEREN_REAUTENTICACION and not sesiones.reautenticada(
                sesion, config, datetime.now(timezone.utc)
            ):
                raise HTTPException(403, detail={"codigo": "requiere_reautenticacion", "mensaje": "Confirma tu contraseña para continuar."})
            return sesion

        dependencia.accion = accion
        return dependencia

    def _estado_sesion(config: ConfigCuentas, sesion: Sesion, conn) -> dict:
        return {
            "autenticada": True,
            "nivel": sesion.nivel,
            "usuario": {"id": sesion.usuario_id, "correo": sesion.correo, "nombre": sesion.nombre_visible},
            "roles": sorted(sesion.roles),
            "metodos": list(sesion.metodos),
            "csrf_token": csrf.token_para_sesion(config, sesion.id),
            "reautenticacion_vigente": sesiones.reautenticada(sesion, config, datetime.now(timezone.utc)),
            "factores": [{"id": i, "tipo": t, "etiqueta": e} for i, t, e in servicio.factores_confirmados(conn, sesion.usuario_id)],
        }

    def _respuesta_con_sesion(response: Response, config: ConfigCuentas, conn, token: str) -> dict:
        sesion = sesiones.obtener(conn, config, token)
        _poner_cookie(response, config, token)
        return _estado_sesion(config, sesion, conn)

    cuenta = APIRouter(prefix="/api/cuenta", tags=["cuenta"], dependencies=[Depends(verificar_origen)])
    admin = APIRouter(prefix="/api/admin", tags=["administración"], dependencies=[Depends(verificar_origen)])

    # --- sin sesión ------------------------------------------------------------

    @cuenta.get("/sesion")
    def ver_sesion(request: Request, response: Response, config: ConfigCuentas = Depends(_config)):
        response.headers["Cache-Control"] = "no-store"
        sesion = _sesion_de(request, config)
        if sesion is None:
            return {"autenticada": False}
        with abrir_conexion() as conn:
            return _estado_sesion(config, sesion, conn)

    @cuenta.post("/ingresar")
    @limiter.limit(limite_auth)
    def ingresar(request: Request, response: Response, datos: IngresoIn, config: ConfigCuentas = Depends(_config)):
        response.headers["Cache-Control"] = "no-store"
        try:
            contrasenas.comprobar_cupo()
        except contrasenas.Saturado as exc:
            raise _http_saturado(exc) from exc
        with tx() as conn:
            token, _ = servicio.ingresar(
                conn, config, correo=datos.correo, contrasena=datos.contrasena,
                ip=ip_fn(request), agente=request.headers.get("user-agent"),
            )
            return _respuesta_con_sesion(response, config, conn, token)

    @cuenta.post("/clave/olvide", status_code=202)
    @limiter.limit(limite_auth)
    def olvide_clave(request: Request, datos: CorreoIn, tareas: BackgroundTasks, config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            _enviar(tareas, conn, config, servicio.solicitar_restablecimiento(conn, config, datos.correo, ip_fn(request)))
        # La misma respuesta exista o no la cuenta.
        return {"mensaje": "Si el correo tiene una cuenta, enviamos un enlace para restablecer la contraseña."}

    @cuenta.post("/clave/restablecer")
    @limiter.limit(limite_auth)
    def restablecer(request: Request, datos: RestablecerIn, tareas: BackgroundTasks, config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            _enviar(tareas, conn, config, servicio.restablecer_clave(conn, config, token=datos.token, contrasena=datos.contrasena, ip=ip_fn(request)))
        return {"mensaje": "Contraseña actualizada. Ya puedes ingresar."}

    @cuenta.post("/invitacion/ver")
    @limiter.limit(limite_auth)
    def ver_invitacion(request: Request, datos: TokenIn, config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            info = servicio.ver_invitacion(conn, datos.token)
        if info is None:
            raise HTTPException(410, detail={"codigo": "invitacion_invalida", "mensaje": "La invitación no es válida o ya caducó."})
        return info

    @cuenta.post("/invitacion/aceptar")
    @limiter.limit(limite_auth)
    def aceptar_invitacion(request: Request, response: Response, datos: AceptarIn, config: ConfigCuentas = Depends(_config)):
        response.headers["Cache-Control"] = "no-store"
        with tx() as conn:
            token, _ = servicio.aceptar_invitacion(
                conn, config, token=datos.token, nombre_visible=datos.nombre_visible, cargo=datos.cargo,
                contrasena=datos.contrasena, terminos_version=datos.terminos_version,
                agente=request.headers.get("user-agent"), red=auditoria.truncar_red(ip_fn(request)),
            )
            return _respuesta_con_sesion(response, config, conn, token)

    # --- ingreso en dos pasos --------------------------------------------------------

    paso2 = en_nivel("segundo_factor")

    @cuenta.post("/ingresar/totp")
    @limiter.limit(limite_auth)
    def ingresar_totp(request: Request, response: Response, datos: CodigoIn, sesion: Sesion = Depends(paso2), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            return _respuesta_con_sesion(response, config, conn, servicio.completar_con_totp(conn, config, sesion, datos.codigo))

    @cuenta.post("/ingresar/recuperacion")
    @limiter.limit(limite_auth)
    def ingresar_recuperacion(request: Request, response: Response, datos: CodigoIn, tareas: BackgroundTasks, sesion: Sesion = Depends(paso2), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            token, aviso = servicio.completar_con_recuperacion(conn, config, sesion, datos.codigo)
            _enviar(tareas, conn, config, aviso)
            return _respuesta_con_sesion(response, config, conn, token)

    @cuenta.post("/ingresar/llave/opciones")
    @limiter.limit(limite_auth)
    def ingresar_llave_opciones(request: Request, sesion: Sesion = Depends(paso2), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            return llaves.opciones_ingreso(conn, config, sesion)

    @cuenta.post("/ingresar/llave")
    @limiter.limit(limite_auth)
    def ingresar_llave(request: Request, response: Response, datos: CredencialIn, sesion: Sesion = Depends(paso2), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            return _respuesta_con_sesion(response, config, conn, llaves.verificar_ingreso(conn, config, sesion, datos.credencial))

    # --- alta de factores (en el alta y con sesión completa) ------------------------------

    alta_o_completa = en_nivel("alta_pendiente", "completo")

    @cuenta.post("/factores/totp/iniciar")
    def iniciar_totp(datos: EtiquetaIn, sesion: Sesion = Depends(alta_o_completa), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            return servicio.iniciar_totp(conn, config, sesion, datos.etiqueta)

    @cuenta.post("/factores/totp/confirmar")
    def confirmar_totp(datos: ConfirmarTotpIn, tareas: BackgroundTasks, sesion: Sesion = Depends(alta_o_completa), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            r = servicio.confirmar_totp(conn, config, sesion, datos.factor_id, datos.codigo)
            _enviar(tareas, conn, config, r.pop("aviso"))
            return r

    @cuenta.post("/factores/llave/opciones")
    def llave_opciones(sesion: Sesion = Depends(alta_o_completa), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            return llaves.opciones_registro(conn, config, sesion)

    @cuenta.post("/factores/llave")
    def llave_registrar(datos: LlaveIn, tareas: BackgroundTasks, sesion: Sesion = Depends(alta_o_completa), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            r = llaves.verificar_registro(conn, config, sesion, datos.credencial, datos.etiqueta)
            _enviar(tareas, conn, config, r.pop("aviso"))
            return r

    @cuenta.post("/alta/completar")
    def completar_alta(response: Response, sesion: Sesion = Depends(en_nivel("alta_pendiente")), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            return _respuesta_con_sesion(response, config, conn, servicio.promover_alta(conn, config, sesion))

    # --- cuenta propia (acciones con política) --------------------------------------------

    @cuenta.post("/salir")
    def salir(response: Response, sesion: Sesion = Depends(requerir("cuenta.ver")), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            servicio.cerrar_sesion(conn, sesion)
        _quitar_cookie(response, config)
        return {"mensaje": "Sesión cerrada."}

    @cuenta.post("/reautenticar")
    @limiter.limit(limite_auth)
    def reautenticar(request: Request, response: Response, datos: ReautenticarIn, sesion: Sesion = Depends(requerir("cuenta.ver")), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            return _respuesta_con_sesion(response, config, conn, servicio.reautenticar(conn, config, sesion, datos.contrasena))

    @cuenta.post("/clave/cambiar")
    @limiter.limit(limite_auth)
    def cambiar_clave(request: Request, response: Response, datos: CambiarClaveIn, tareas: BackgroundTasks, sesion: Sesion = Depends(requerir("cuenta.cambiar_clave")), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            token, aviso = servicio.cambiar_clave(conn, config, sesion, actual=datos.actual, nueva=datos.nueva)
            _enviar(tareas, conn, config, aviso)
            return _respuesta_con_sesion(response, config, conn, token)

    @cuenta.post("/factores/{factor_id}/revocar")
    def revocar_factor(factor_id: str, sesion: Sesion = Depends(requerir("cuenta.gestionar_factores")), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            servicio.revocar_factor(conn, config, sesion, factor_id)
        return {"mensaje": "Factor eliminado."}

    @cuenta.get("/sesiones")
    def listar_sesiones(response: Response, sesion: Sesion = Depends(requerir("cuenta.ver"))):
        response.headers["Cache-Control"] = "no-store"
        with abrir_conexion() as conn:
            return {"sesiones": servicio.sesiones_propias(conn, sesion)}

    @cuenta.post("/sesiones/cerrar-otras")
    def cerrar_otras(sesion: Sesion = Depends(requerir("cuenta.cerrar_sesiones"))):
        with tx() as conn:
            cerradas = sesiones.revocar_todas(conn, sesion.usuario_id, "cierre_de_otras", excepto=sesion.id)
            auditoria.registrar(conn, categoria="seguridad", accion="otras_sesiones_cerradas", actor_id=sesion.usuario_id, sesion_id=sesion.id, detalle={"cantidad": cerradas})
        return {"cerradas": cerradas}

    # --- administración ------------------------------------------------------------------------

    @admin.get("/usuarios")
    def usuarios(response: Response, sesion: Sesion = Depends(requerir("admin.listar_usuarios"))):
        response.headers["Cache-Control"] = "no-store"
        with abrir_conexion() as conn:
            return {"usuarios": servicio.listar_usuarios(conn)}

    @admin.post("/invitaciones", status_code=201)
    def invitar(request: Request, datos: InvitarIn, tareas: BackgroundTasks, sesion: Sesion = Depends(requerir("admin.invitar")), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            inv_id, _, pendiente = servicio.crear_invitacion(
                conn, config, invitador=sesion, correo=datos.correo, roles=datos.roles,
                institucion_id=datos.institucion_id, nota_verificacion=datos.nota_verificacion,
                justificacion_dominio=datos.justificacion_dominio, red=auditoria.truncar_red(ip_fn(request)),
            )
            _enviar(tareas, conn, config, pendiente)
        return {"id": inv_id}

    @admin.patch("/usuarios/{usuario_id}/roles")
    def roles(usuario_id: str, datos: RolesIn, sesion: Sesion = Depends(requerir("admin.cambiar_roles")), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            servicio.cambiar_roles(conn, config, sesion, usuario_id, datos.roles)
        return {"mensaje": "Roles actualizados."}

    @admin.post("/usuarios/{usuario_id}/estado")
    def estado(usuario_id: str, datos: EstadoIn, sesion: Sesion = Depends(requerir("admin.suspender"))):
        with tx() as conn:
            servicio.cambiar_estado(conn, sesion, usuario_id, datos.estado, datos.motivo)
        return {"mensaje": "Estado actualizado."}

    @admin.post("/usuarios/{usuario_id}/restablecer-factores")
    @limiter.limit(limite_auth)
    def restablecer_factores(request: Request, response: Response, usuario_id: str, datos: MotivoIn, tareas: BackgroundTasks, sesion: Sesion = Depends(requerir("admin.restablecer_factores")), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            resultado = servicio.solicitar_restablecimiento_de_factores(conn, config, sesion, usuario_id, datos.motivo)
            for pendiente in resultado.correos:
                _enviar(tareas, conn, config, pendiente)
        if resultado.hecho:
            return {"mensaje": "Factores restablecidos."}
        # Sobre un administrador queda esperando a que otro lo confirme.
        response.status_code = 202
        return {
            "mensaje": "Solicitud creada. Otro administrador debe confirmarla antes de que caduque.",
            "aprobacion": resultado.aprobacion,
        }

    @admin.get("/aprobaciones")
    def aprobaciones(response: Response, sesion: Sesion = Depends(requerir("admin.ver_aprobaciones"))):
        response.headers["Cache-Control"] = "no-store"
        with abrir_conexion() as conn:
            return {"aprobaciones": servicio.listar_aprobaciones(conn, sesion)}

    @admin.post("/aprobaciones/{aprobacion_id}/confirmar")
    @limiter.limit(limite_auth)
    def confirmar_aprobacion(request: Request, aprobacion_id: str, tareas: BackgroundTasks, sesion: Sesion = Depends(requerir("admin.resolver_aprobaciones")), config: ConfigCuentas = Depends(_config)):
        with tx() as conn:
            _enviar(tareas, conn, config, servicio.confirmar_restablecimiento_de_factores(conn, sesion, aprobacion_id))
        return {"mensaje": "Factores restablecidos."}

    @admin.post("/aprobaciones/{aprobacion_id}/rechazar")
    @limiter.limit(limite_auth)
    def rechazar_aprobacion(request: Request, aprobacion_id: str, sesion: Sesion = Depends(requerir("admin.resolver_aprobaciones"))):
        with tx() as conn:
            servicio.rechazar_restablecimiento_de_factores(conn, sesion, aprobacion_id)
        return {"mensaje": "Solicitud resuelta sin cambios."}

    @admin.get("/instituciones")
    def instituciones(response: Response, sesion: Sesion = Depends(requerir("admin.gestionar_instituciones"))):
        response.headers["Cache-Control"] = "no-store"
        with abrir_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, nombre, tipo, dominios_correo, verificada_en, activa FROM instituciones ORDER BY nombre")
            return {"instituciones": [
                {"id": a, "nombre": b, "tipo": c, "dominios_correo": d, "verificada": e is not None, "activa": f}
                for a, b, c, d, e, f in cur.fetchall()
            ]}

    @admin.post("/instituciones", status_code=201)
    def crear_institucion(datos: InstitucionIn, sesion: Sesion = Depends(requerir("admin.gestionar_instituciones"))):
        with tx() as conn:
            iid = servicio.crear_institucion(conn, sesion, nombre=datos.nombre, tipo=datos.tipo, dominios=datos.dominios_correo, sitio_web=datos.sitio_web)
        return {"id": iid}

    @admin.post("/instituciones/{institucion_id}/verificar")
    def verificar_institucion(institucion_id: int, datos: VerificarInstitucionIn, sesion: Sesion = Depends(requerir("admin.gestionar_instituciones"))):
        with tx() as conn:
            servicio.verificar_institucion(conn, sesion, institucion_id, datos.metodo)
        return {"mensaje": "Institución verificada."}

    @admin.get("/auditoria")
    def ver_auditoria(response: Response, limite: int = 100, sesion: Sesion = Depends(requerir("admin.ver_auditoria"))):
        response.headers["Cache-Control"] = "no-store"
        limite = max(1, min(limite, 500))
        with abrir_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, en, categoria, actor_tipo, actor_id, accion, objeto_tipo, objeto_id, detalle "
                "FROM auditoria ORDER BY id DESC LIMIT %s", (limite,),
            )
            filas = [
                {"id": a, "en": b.isoformat(), "categoria": c, "actor_tipo": d, "actor_id": str(e) if e else None,
                 "accion": f, "objeto_tipo": g, "objeto_id": h, "detalle": i}
                for a, b, c, d, e, f, g, h, i in cur.fetchall()
            ]
            return {"eventos": filas, "cadena_integra": auditoria.verificar_cadena(conn) is None}

    router.include_router(cuenta)
    router.include_router(admin)
    return router
