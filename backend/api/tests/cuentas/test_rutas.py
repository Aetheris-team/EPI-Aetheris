import re
import time
from dataclasses import dataclass

import pyotp
import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.testclient import TestClient

from api.cuentas import contrasenas, intentos, permisos, rutas, servicio, sesiones
from api.cuentas.rutas import InstitucionIn

from .conftest_http import crear_app
from .test_servicio import CLAVE, _admin_sesion

ORIGEN = {"origin": "https://epi-aetheris.dev"}


@pytest.fixture
def web(conn, config):
    app, bandeja = crear_app(conn, config)
    cliente = TestClient(app, base_url="https://api.epi-aetheris.dev")
    cliente.bandeja = bandeja
    cliente.app_ = app
    return cliente


def _csrf(cliente, token):
    return {**ORIGEN, "x-csrf-token": token}


def _admin_con_cookie(conn, config, crear_usuario, web, metodos=("clave", "webauthn")):
    uid = crear_usuario(roles=("administrador",))
    token, _ = sesiones.crear(conn, config, usuario_id=uid, nivel="completo", metodos=list(metodos), reciente=True)
    web.cookies.set("__Host-epi_sid", token, domain="api.epi-aetheris.dev")
    s = sesiones.obtener(conn, config, token)
    return uid, {**ORIGEN, "x-csrf-token": __import__("api.cuentas.csrf", fromlist=["x"]).token_para_sesion(config, s.id)}


# --- flujo completo por HTTP ----------------------------------------------------------

def test_flujo_invitacion_alta_e_ingreso(conn, config, crear_usuario, web):
    uid_admin, h_admin = _admin_con_cookie(conn, config, crear_usuario, web)
    r = web.post("/api/admin/invitaciones", headers=h_admin, json={
        "correo": "pilar@ejemplo.org", "roles": ["publicador"], "nota_verificacion": "Verificada por llamada al SIBASI",
    })
    assert r.status_code == 201
    token = re.search(r"#t=([\w-]+)", web.bandeja.enviados[-1].cuerpo).group(1)

    web.cookies.clear()
    assert web.post("/api/cuenta/invitacion/ver", headers=ORIGEN, json={"token": token}).json()["correo"] == "pilar@ejemplo.org"
    r = web.post("/api/cuenta/invitacion/aceptar", headers=ORIGEN, json={
        "token": token, "nombre_visible": "Pilar Gómez", "cargo": "Epidemióloga",
        "contrasena": CLAVE, "terminos_version": servicio.VERSION_TERMINOS,
    })
    assert r.status_code == 200 and r.json()["nivel"] == "alta_pendiente"
    set_cookie = r.headers["set-cookie"]
    assert "__Host-epi_sid=" in set_cookie and "HttpOnly" in set_cookie and "Secure" in set_cookie
    assert "SameSite=strict" in set_cookie and "Path=/" in set_cookie and "Domain" not in set_cookie
    h = _csrf(web, r.json()["csrf_token"])

    iniciar = web.post("/api/cuenta/factores/totp/iniciar", headers=h, json={"etiqueta": "Teléfono"}).json()
    assert "<svg" in iniciar["qr_svg"]
    r = web.post("/api/cuenta/factores/totp/confirmar", headers=h, json={
        "factor_id": iniciar["factor_id"], "codigo": pyotp.TOTP(iniciar["secreto"]).now()})
    assert r.json()["activada"] and len(r.json()["codigos_recuperacion"]) == 10
    r = web.post("/api/cuenta/alta/completar", headers=h)
    assert r.json()["nivel"] == "completo" and r.json()["roles"] == ["publicador"]

    # Cierra sesión y vuelve a entrar en dos pasos.
    h = _csrf(web, r.json()["csrf_token"])
    assert web.post("/api/cuenta/salir", headers=h).status_code == 200
    assert web.get("/api/cuenta/sesion").json() == {"autenticada": False}
    r = web.post("/api/cuenta/ingresar", headers=ORIGEN, json={"correo": "PILAR@ejemplo.org", "contrasena": CLAVE})
    assert r.json()["nivel"] == "segundo_factor"
    h = _csrf(web, r.json()["csrf_token"])
    # Antes del segundo factor no hay acceso a nada con permisos.
    assert web.get("/api/cuenta/sesiones").status_code == 403
    codigo = pyotp.TOTP(iniciar["secreto"]).at(time.time() + 30)
    r = web.post("/api/cuenta/ingresar/totp", headers=h, json={"codigo": codigo})
    assert r.status_code == 200 and r.json()["nivel"] == "completo"
    assert web.get("/api/cuenta/sesiones").status_code == 200
    # Un publicador no entra a la administración.
    h = _csrf(web, r.json()["csrf_token"])
    assert web.get("/api/admin/usuarios").status_code == 403


def test_sesion_sin_cookie_es_200_anonima(web):
    r = web.get("/api/cuenta/sesion")
    assert r.status_code == 200 and r.json() == {"autenticada": False}
    assert r.headers["cache-control"] == "no-store"


# --- CSRF, origen y formato -----------------------------------------------------------------

def test_post_sin_origen_se_rechaza(web):
    r = web.post("/api/cuenta/ingresar", json={"correo": "a@b.org", "contrasena": "x"})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "origen"


def test_post_con_otro_origen_se_rechaza(web):
    r = web.post("/api/cuenta/ingresar", headers={"origin": "https://evil.example"}, json={"correo": "a@b.org", "contrasena": "x"})
    assert r.status_code == 403


def test_post_con_sesion_sin_csrf_se_rechaza(conn, config, crear_usuario, web):
    _admin_con_cookie(conn, config, crear_usuario, web)
    r = web.post("/api/admin/invitaciones", headers=ORIGEN, json={
        "correo": "x@ejemplo.org", "roles": ["publicador"], "nota_verificacion": "Verificada por llamada"})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "csrf"


def test_csrf_de_otra_sesion_no_sirve(conn, config, crear_usuario, web):
    _admin_con_cookie(conn, config, crear_usuario, web)
    r = web.post("/api/admin/invitaciones", headers={**ORIGEN, "x-csrf-token": "0" * 64}, json={
        "correo": "x@ejemplo.org", "roles": ["publicador"], "nota_verificacion": "Verificada por llamada"})
    assert r.status_code == 403


def test_cuerpo_con_campos_de_mas_se_rechaza(web):
    r = web.post("/api/cuenta/ingresar", headers=ORIGEN, json={"correo": "a@b.org", "contrasena": "x", "rol": "administrador"})
    assert r.status_code == 422


def test_cuerpo_que_no_es_json_se_rechaza(web):
    r = web.post("/api/cuenta/ingresar", headers={**ORIGEN, "content-type": "text/plain"}, content='{"correo":"a@b.org","contrasena":"x"}')
    assert r.status_code == 422


# --- ingreso con el límite de verificaciones saturado ----------------------------------------

def _fallos_registrados(conn, config, correo):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM intentos_ingreso WHERE clave = %s",
            (intentos.clave(config, "correo", correo),),
        )
        return cur.fetchone()[0]


def test_ingreso_saturado_responde_503_con_reintento_y_sin_consultar(web, monkeypatch):
    monkeypatch.setattr(contrasenas, "_en_curso", contrasenas.PARALELAS + contrasenas.COLA_MAX)

    def no_debe_llamarse(*_a, **_k):
        raise AssertionError("se consultó la base con el cupo lleno")

    monkeypatch.setattr(servicio, "ingresar", no_debe_llamarse)
    r = web.post("/api/cuenta/ingresar", headers=ORIGEN, json={"correo": "nadie@ejemplo.org", "contrasena": "una clave bastante larga"})
    assert r.status_code == 503
    assert int(r.headers["retry-after"]) >= 1
    assert r.json()["detail"]["codigo"] == "servidor_ocupado"
    assert "set-cookie" not in r.headers


def test_ingreso_sin_turno_no_cuenta_como_intento_fallido(conn, config, crear_usuario, web, monkeypatch):
    crear_usuario()
    antes = _fallos_registrados(conn, config, "persona1@ejemplo.org")

    def sin_turno(*_a, **_k):
        raise contrasenas.Saturado(3)

    monkeypatch.setattr(contrasenas, "verificar", sin_turno)
    r = web.post("/api/cuenta/ingresar", headers=ORIGEN, json={"correo": "persona1@ejemplo.org", "contrasena": "una clave bastante larga"})
    assert r.status_code == 503
    assert r.headers["retry-after"] == "3"
    assert _fallos_registrados(conn, config, "persona1@ejemplo.org") == antes == 0


# --- olvidé mi contraseña ---------------------------------------------------------------------

def test_olvide_clave_responde_igual(conn, config, crear_usuario, web):
    crear_usuario()
    existente = web.post("/api/cuenta/clave/olvide", headers=ORIGEN, json={"correo": "persona1@ejemplo.org"})
    inexistente = web.post("/api/cuenta/clave/olvide", headers=ORIGEN, json={"correo": "nadie@ejemplo.org"})
    assert existente.status_code == inexistente.status_code == 202
    assert existente.json() == inexistente.json()
    assert len(web.bandeja.enviados) == 1  # solo la cuenta real recibió correo


def test_correos_no_dejan_el_token_en_la_bandeja(conn, config, crear_usuario, web):
    crear_usuario()
    web.post("/api/cuenta/clave/olvide", headers=ORIGEN, json={"correo": "persona1@ejemplo.org"})
    token = re.search(r"#t=([\w-]+)", web.bandeja.enviados[-1].cuerpo).group(1)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM correos_salientes WHERE contexto::text LIKE %s OR plantilla LIKE %s", (f"%{token}%", f"%{token}%"))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT estado FROM correos_salientes ORDER BY id DESC LIMIT 1")
        assert cur.fetchone()[0] == "enviado"


def test_fallo_de_correo_queda_registrado(conn, config, crear_usuario, web):
    crear_usuario()
    web.bandeja.fallar = True
    r = web.post("/api/cuenta/clave/olvide", headers=ORIGEN, json={"correo": "persona1@ejemplo.org"})
    assert r.status_code == 202
    with conn.cursor() as cur:
        cur.execute("SELECT estado, error_codigo FROM correos_salientes ORDER BY id DESC LIMIT 1")
        assert cur.fetchone() == ("fallido", "RuntimeError")


# --- permisos --------------------------------------------------------------------------------------

def test_accion_que_exige_reautenticacion(conn, config, crear_usuario, web):
    uid = crear_usuario(roles=("administrador",))
    token, _ = sesiones.crear(conn, config, usuario_id=uid, nivel="completo", metodos=["clave", "webauthn"], reciente=False)
    web.cookies.set("__Host-epi_sid", token, domain="api.epi-aetheris.dev")
    from api.cuentas import csrf
    h = {**ORIGEN, "x-csrf-token": csrf.token_para_sesion(config, sesiones.obtener(conn, config, token).id)}
    r = web.post("/api/admin/invitaciones", headers=h, json={
        "correo": "x@ejemplo.org", "roles": ["publicador"], "nota_verificacion": "Verificada por llamada"})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "requiere_reautenticacion"
    r = web.post("/api/cuenta/reautenticar", headers=h, json={"contrasena": "no"})
    assert r.status_code in (401, 403)


def test_administrador_sin_llave_no_invita(conn, config, crear_usuario, web):
    # Una invitación puede crear otro administrador: con solo contraseña y TOTP
    # la sesión no puede ampliar el grupo que exige llave de acceso.
    _, h = _admin_con_cookie(conn, config, crear_usuario, web, metodos=("clave", "totp"))
    r = web.post("/api/admin/invitaciones", headers=h, json={
        "correo": "otra.admin@ejemplo.org", "roles": ["administrador"], "nota_verificacion": "Verificada por llamada"})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "requiere_llave"


def test_administrador_sin_llave_no_cambia_roles(conn, config, crear_usuario, web):
    _, h = _admin_con_cookie(conn, config, crear_usuario, web, metodos=("clave", "totp"))
    otro = crear_usuario(roles=("publicador",))
    r = web.patch(f"/api/admin/usuarios/{otro}/roles", headers=h, json={"roles": ["revisor"]})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "requiere_llave"


def test_administrador_con_llave_cambia_roles(conn, config, crear_usuario, web):
    _, h = _admin_con_cookie(conn, config, crear_usuario, web)
    otro = crear_usuario(roles=("publicador",))
    r = web.patch(f"/api/admin/usuarios/{otro}/roles", headers=h, json={"roles": ["revisor"]})
    assert r.status_code == 200
    assert web.get("/api/admin/usuarios").json()["usuarios"]


def test_listado_nunca_expone_secretos(conn, config, crear_usuario, web):
    _admin_con_cookie(conn, config, crear_usuario, web)
    cuerpo = web.get("/api/admin/usuarios").text.lower()
    for palabra in ("hash", "secreto", "token", "pepper"):
        assert palabra not in cuerpo


def test_auditoria_visible_con_cadena_integra(conn, config, crear_usuario, web):
    _admin_con_cookie(conn, config, crear_usuario, web)
    r = web.get("/api/admin/auditoria")
    assert r.status_code == 200 and r.json()["cadena_integra"] is True


# --- matriz de permisos ---------------------------------------------------------------------------

@dataclass
class RutaPlana:
    path: str
    methods: set
    llamadas: list


def _llamadas_de(dependant):
    """Todas las funciones de dependencia de una ruta, a cualquier profundidad."""
    encontradas, pila = [], list(dependant.dependencies)
    while pila:
        d = pila.pop()
        encontradas.append(d.call)
        pila.extend(d.dependencies)
    return encontradas


def _rutas_de(app):
    """Aplana el árbol de rutas. Desde FastAPI 0.137 `app.routes` trae routers
    incluidos anidados, cada uno con su prefijo y sus dependencias."""
    resultado = []

    def recorrer(rutas, prefijo, heredadas):
        for r in rutas:
            if type(r).__name__ == "_IncludedRouter":
                ctx = r.include_context
                recorrer(r.original_router.routes, prefijo + ctx.prefix, heredadas + [d.dependency for d in ctx.dependencies])
            elif isinstance(r, APIRoute):
                propias = [d.dependency for d in r.dependencies]
                resultado.append(RutaPlana(prefijo + r.path, set(r.methods), heredadas + propias + _llamadas_de(r.dependant)))

    recorrer(app.routes, "", [])
    return resultado


def _declaraciones(ruta):
    acciones = [c.accion for c in ruta.llamadas if hasattr(c, "accion")]
    niveles = [c.nivel for c in ruta.llamadas if hasattr(c, "nivel")]
    return acciones, niveles


def _metodo(ruta):
    return sorted(ruta.methods - {"HEAD", "OPTIONS"})[0]


def test_toda_ruta_declara_su_permiso(web):
    privadas = [r for r in _rutas_de(web.app_) if r.path.startswith(("/api/cuenta", "/api/admin"))]
    assert len(privadas) > 25
    sin_declarar = []
    for r in privadas:
        metodo = _metodo(r)
        acciones, niveles = _declaraciones(r)
        if not acciones and not niveles and (metodo, r.path) not in rutas.RUTAS_SIN_SESION:
            sin_declarar.append((metodo, r.path))
    assert sin_declarar == []


def test_toda_accion_de_la_tabla_se_usa_y_toda_ruta_usa_una_de_la_tabla(web):
    usadas = set()
    for r in _rutas_de(web.app_):
        usadas.update(_declaraciones(r)[0])
    assert usadas == set(permisos.POLITICA)


def test_las_rutas_sin_sesion_son_solo_las_declaradas(web):
    existentes = {(_metodo(r), r.path) for r in _rutas_de(web.app_)}
    assert rutas.RUTAS_SIN_SESION <= existentes


@pytest.mark.parametrize("rol", ["publicador", "revisor"])
def test_ninguna_ruta_de_administracion_acepta_otros_roles(conn, config, crear_usuario, web, rol):
    uid = crear_usuario(roles=(rol,))
    token, _ = sesiones.crear(conn, config, usuario_id=uid, nivel="completo", metodos=["clave", "webauthn"], reciente=True)
    web.cookies.set("__Host-epi_sid", token, domain="api.epi-aetheris.dev")
    from api.cuentas import csrf
    h = {**ORIGEN, "x-csrf-token": csrf.token_para_sesion(config, sesiones.obtener(conn, config, token).id)}
    for r in _rutas_de(web.app_):
        if not r.path.startswith("/api/admin"):
            continue
        ruta = r.path.replace("{usuario_id}", uid).replace("{institucion_id}", "1")
        metodo = _metodo(r)
        resp = web.request(metodo, ruta, headers=h, json={} if metodo != "GET" else None)
        assert resp.status_code == 403, (metodo, r.path, resp.status_code)


def test_sin_cookie_toda_ruta_privada_da_401(web):
    for r in _rutas_de(web.app_):
        if not r.path.startswith(("/api/cuenta", "/api/admin")):
            continue
        metodo = _metodo(r)
        if (metodo, r.path) in rutas.RUTAS_SIN_SESION:
            continue
        ruta = r.path.replace("{usuario_id}", "x").replace("{institucion_id}", "1").replace("{factor_id}", "x")
        resp = web.request(metodo, ruta, headers=ORIGEN, json={} if metodo != "GET" else None)
        assert resp.status_code == 401, (metodo, r.path, resp.status_code)


# --- límite por IP ---------------------------------------------------------------------------------------

def test_limite_por_ip_en_el_ingreso(conn, config):
    app, _ = crear_app(conn, config, limite_auth="3/minute", limiter_activo=True)
    cliente = TestClient(app, base_url="https://api.epi-aetheris.dev")
    codigos = [cliente.post("/api/cuenta/ingresar", headers=ORIGEN, json={"correo": "a@b.org", "contrasena": "x"}).status_code for _ in range(5)]
    assert codigos[:3] == [401, 401, 401] and codigos[3:] == [429, 429]


def test_sin_configuracion_las_rutas_responden_503(conn):
    from contextlib import contextmanager

    from fastapi import FastAPI
    from slowapi import Limiter

    from api.cuentas import correo

    def sin_config():
        raise RuntimeError("AUTH_PEPPERS no está definida")

    @contextmanager
    def abrir():
        yield conn

    app = FastAPI()
    app.include_router(rutas.crear_router(
        limiter=Limiter(key_func=lambda r: "x", enabled=False), abrir_conexion=abrir, limite_auth="10/minute",
        config_fn=sin_config, remitente=correo.RemitenteEnMemoria(), ip_fn=lambda r: "x"))
    resp = TestClient(app).post("/api/cuenta/ingresar", headers=ORIGEN, json={"correo": "a@b.org", "contrasena": "x"})
    assert resp.status_code == 503 and resp.json()["detail"]["codigo"] == "cuentas_no_configuradas"


@pytest.mark.parametrize(
    "sitio", ["javascript:alert(1)", "data:text/html,<b>x</b>", "ftp://institucion.org", "//institucion.org", "institucion.org", "https://"]
)
def test_institucion_rechaza_sitio_web_que_no_es_http(sitio):
    with pytest.raises(ValidationError):
        InstitucionIn(nombre="Institución de prueba", tipo="academica", sitio_web=sitio)


@pytest.mark.parametrize("sitio", ["https://institucion.org", " http://institucion.org/ruta ", None, "  "])
def test_institucion_acepta_sitio_web_http_o_vacio(sitio):
    datos = InstitucionIn(nombre="Institución de prueba", tipo="academica", sitio_web=sitio)
    assert datos.sitio_web in ("https://institucion.org", "http://institucion.org/ruta", None)
