import logging
import os
import threading
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from psycopg2 import InterfaceError, OperationalError
from psycopg2.pool import ThreadedConnectionPool

from .conexion_db import parametros_conexion
from .rutas import alertas as _rutas_alertas
from .rutas import dengue as _rutas_dengue
from .rutas import modulos as _rutas_modulos
from .rutas import respiratorio as _rutas_respiratorio

# La documentación interactiva (/docs, /redoc) y el esquema (/openapi.json)
# se apagan en producción con API_DOCS_ENABLED=false (ADR 0024): exponen toda
# la superficie de la API y Swagger UI carga scripts de un CDN, lo que obliga
# a una CSP más abierta de la necesaria. Por defecto siguen activos para el
# desarrollo local y los tests.
API_DOCS_ENABLED = os.getenv("API_DOCS_ENABLED", "true").lower() != "false"

app = FastAPI(
    title="EPI-Aetheris API",
    description="API para ingesta, análisis y consulta de datos epidemiológicos descriptivos",
    version="0.1.0",
    docs_url="/docs" if API_DOCS_ENABLED else None,
    redoc_url="/redoc" if API_DOCS_ENABLED else None,
    openapi_url="/openapi.json" if API_DOCS_ENABLED else None,
)

# --- Rate limiting (issue #61) -------------------------------------------------
# slowapi en memoria: el proceso es un solo worker de Uvicorn tanto en
# docker-compose (--reload) como en Render (dockerCommand sin --workers), asi
# que un contador por proceso ES el contador global. Si algun dia se pasa a
# --workers N el limite efectivo seria N veces el configurado -- ahi tocaria
# un backend compartido (Redis), no ahora.
#
# key_func: Uvicorn NO corre con --proxy-headers, y en Render el peer TCP es
# el balanceador de la plataforma (una sola IP para todo el trafico). Sin
# esto, todos los clientes compartirian un unico bucket y el limite global
# estrangularia a todos los usuarios a la vez.
#
# Tomamos el salto de X-Forwarded-For que anexo el ultimo proxy de confianza
# contando desde la derecha, no el primero (issue #67): un cliente puede mandar
# la cabecera ya seteada, pero no puede quitar los saltos que anexan nuestros
# proxies. Con el primer valor, quien mande "X-Forwarded-For: 1.2.3.4" se
# bucketiza como una IP distinta en cada request y evade el rate limiter.
#
# TRUSTED_PROXY_DEPTH es cuantos proxies de confianza hay entre el cliente y
# Uvicorn. Por defecto 1 (el balanceador de Render anexa la IP de quien le
# llama). En produccion la API esta ademas detras del Cloudflare de Render, y
# con 1 la IP que se toma es la del servidor de Cloudflare, no la del cliente
# (se vio en la auditoria de cuentas: la red guardada era 172.71.146.0/24):
# todos los visitantes de un mismo servidor comparten contador y la auditoria
# no sirve. Con 2 se toma el salto anterior al de Cloudflare. Si hay menos
# saltos de los esperados, los proxies no anexaron nada y se toma el primero.
# Caemos a la IP del socket solo en local/tests donde la cabecera no existe.
def _profundidad_proxy() -> int:
    try:
        return max(1, int(os.getenv("TRUSTED_PROXY_DEPTH", "1")))
    except ValueError:
        return 1


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        saltos = [salto.strip() for salto in forwarded.split(",") if salto.strip()]
        if saltos:
            profundidad = _profundidad_proxy()
            return saltos[-profundidad] if len(saltos) >= profundidad else saltos[0]
    return get_remote_address(request)


RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "false"
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "120/minute")
# Umbral mas estricto para los endpoints que recalculan on-demand desde CSV +
# modelo joblib y abren una conexion nueva a Postgres por request.
RATE_LIMIT_HEAVY = os.getenv("RATE_LIMIT_HEAVY", "30/minute")
# Escritura de alertas (POST/PATCH): operacion humana de baja frecuencia.
# Mas estricto que el global; configurable por env igual que los otros dos.
# El valor se lee en import para que los tests puedan bajarlo via
# monkeypatch + importlib.reload (un literal en el decorador lo romperia).
RATE_LIMIT_WRITE = os.getenv("RATE_LIMIT_WRITE", "10/minute")
# Ingreso, segundo factor y recuperación de cuentas (ADR 0024): por IP, además
# del límite por cuenta que lleva la tabla intentos_ingreso.
RATE_LIMIT_AUTH = os.getenv("RATE_LIMIT_AUTH", "10/minute")
# Las rutas de cuentas (ADR 0024) no se montan mientras esta variable no sea
# "true": el despliegue actual no tiene las claves ni el correo que necesitan.
CUENTAS_HABILITADAS = os.getenv("CUENTAS_HABILITADAS", "false").lower() == "true"

limiter = Limiter(
    key_func=_client_ip,
    default_limits=[RATE_LIMIT_DEFAULT],
    enabled=RATE_LIMIT_ENABLED,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Se anade ANTES del bloque CORS de abajo para que quede por DENTRO de
# CORSMiddleware: asi la respuesta 429 tambien lleva las cabeceras
# Access-Control-Allow-Origin y el frontend Astro ve un 429 legible en vez de
# un error de red opaco.
app.add_middleware(SlowAPIMiddleware)

# El frontend Astro corre en un origen distinto (puerto 4321) al de esta API
# (puerto 8000) tanto en desarrollo local como dentro de docker-compose.
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:4321").split(",")
    if origin.strip()
]

if "*" in cors_origins:
    raise ValueError("CORS_ALLOWED_ORIGINS must not contain '*' for security reasons.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST", "PATCH", "HEAD", "OPTIONS"],
    # Lista explicita: el formulario de /alertas/nueva manda Authorization
    # (Bearer) y Content-Type (JSON). Un comodín aqui no es necesario y
    # oculta que cabeceras reales acepta el preflight. Con cuentas activas se
    # suma X-CSRF-Token y se aceptan credenciales (la cookie de sesión), solo
    # para los orígenes de la lista, que nunca puede contener "*".
    allow_headers=["Authorization", "Content-Type"] + (["X-CSRF-Token"] if CUENTAS_HABILITADAS else []),
    allow_credentials=CUENTAS_HABILITADAS,
)

# Las respuestas grandes de esta API son series históricas completas en JSON
# sin paginar (p.ej. /api/casos-departamentales) -- muy compresibles. FastAPI
# no comprime nada por defecto.
#
# compresslevel=5 y no el 9 que Starlette trae por defecto: con
# /api/nowcast-dengue/retrospectivo (~220 KB) el 9 tarda unos 39 ms por
# request y el 5 unos 10 ms, para un cuerpo comprimido solo un 2 % mayor
# (70,3 KB frente a 72,0 KB). El gzip se rehace en cada respuesta, también
# en las que salen del cache del servidor.
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)


# --- Pool de conexiones a Postgres (informe de rendimiento externo) --------
# Antes: psycopg2.connect() nuevo por request, sin timeout. Las path
# operations son `def` (síncronas) -> FastAPI las corre en su threadpool
# (~40 hilos por defecto); bajo concurrencia modesta eso son hasta ~40
# conexiones simultáneas abriéndose contra un plan de BD chico
# (basic-256mb), suficiente para agotar el límite de conexiones del
# servidor y salir como el 500 genérico de abajo.
#
# POSTGRES_POOL_MAX es el techo real de conexiones simultáneas hacia
# Postgres ahora (antes no había techo salvo el límite del servidor mismo);
# se deja configurable porque depende del plan de BD, no del código.
POSTGRES_POOL_MIN = int(os.getenv("POSTGRES_POOL_MIN", "1"))
POSTGRES_POOL_MAX = int(os.getenv("POSTGRES_POOL_MAX", "10"))
POSTGRES_CONNECT_TIMEOUT = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5"))
# ThreadedConnectionPool.getconn() NO espera cuando el pool esta al tope --
# lanza PoolError de inmediato ("connection pool exhausted"), lo que
# convertiria un pico de concurrencia corto (perfectamente atendible en
# serie en unos ms) en un 500 seco. Este semaforo hace que el hilo de mas
# espere su turno en vez de fallar; el timeout evita que se quede colgado
# para siempre si la BD de verdad esta saturada.
POSTGRES_POOL_ACQUIRE_TIMEOUT = int(os.getenv("POSTGRES_POOL_ACQUIRE_TIMEOUT", "10"))

_pool: ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()
_pool_semaforo = threading.Semaphore(POSTGRES_POOL_MAX)


def _obtener_pool() -> ThreadedConnectionPool:
    # Perezoso en vez de un handler `lifespan`: evita añadir el primer
    # lifespan de la app solo para esto, y TestClient(app) -- como ya lo usa
    # toda la suite existente -- no siempre dispara eventos de startup si no
    # se usa como context manager. Doble-check con lock: varios requests del
    # threadpool pueden llegar aquí antes de que exista el pool.
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadedConnectionPool(
                    POSTGRES_POOL_MIN,
                    POSTGRES_POOL_MAX,
                    **parametros_conexion(),
                    connect_timeout=POSTGRES_CONNECT_TIMEOUT,
                )
    return _pool


def _tomar_conexion_viva(pool: ThreadedConnectionPool):
    """getconn() con un ping antes de entregar la conexión.

    Con POSTGRES_POOL_MIN >= 1 el pool guarda conexiones ociosas, y si el
    servidor las cortó mientras esperaban (pg_terminate_backend, reinicio de
    la base, Neon que suspende el cómputo) psycopg2 no se entera hasta el
    próximo uso: sin el ping, la primera petición después del corte falla
    con OperationalError -> 503. El ping corre en autocommit para costar un
    solo viaje de ida y vuelta (sin BEGIN ni ROLLBACK); cambiar autocommit
    en una conexión ociosa no habla con el servidor.

    Una conexión muerta se cierra y se pide otra. El pool guarda a lo sumo
    POSTGRES_POOL_MIN ociosas, así que tras ese número de descartes la que
    llega es nueva; si también falla, la base está caída de verdad y el
    error sube."""
    for intento in range(POSTGRES_POOL_MIN + 1):
        conn = pool.getconn()
        try:
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1;")
            conn.autocommit = False
            return conn
        except (OperationalError, InterfaceError):
            pool.putconn(conn, close=True)
            if intento == POSTGRES_POOL_MIN:
                raise


@contextmanager
def _conexion():
    """Toma una conexión del pool y la repone al salir -- también en error,
    para que un request que falla a mitad de camino no se quede con una
    conexión fuera del pool para siempre (con maxconn chico eso agota el
    pool rápido). rollback() antes de devolverla: todas las queries de esta
    API son de solo lectura, pero psycopg2 abre una transacción implícita en
    el primer SELECT -- sin esto la conexión volvería "idle in transaction",
    reteniendo locks hasta el próximo uso.

    Si la conexión quedó cerrada (conn.closed != 0) o el rollback() falló, se
    devuelve con close=True: el pool la descarta en vez de guardarla para la
    próxima petición. Sin close=True, putconn() reintenta el rollback sobre
    una conexión en error, y si ese también falla la excepción sale antes de
    que el pool libere el slot, que queda ocupado para siempre."""
    if not _pool_semaforo.acquire(timeout=POSTGRES_POOL_ACQUIRE_TIMEOUT):
        raise TimeoutError(
            "Tiempo de espera agotado para obtener una conexión del pool de Postgres."
        )
    try:
        pool = _obtener_pool()
        conn = _tomar_conexion_viva(pool)
        try:
            yield conn
        finally:
            descartar = False
            try:
                conn.rollback()
            except Exception:
                descartar = True
            pool.putconn(conn, close=descartar or conn.closed != 0)
    finally:
        _pool_semaforo.release()


def _abrir_conexion():
    """Lo que reciben los routers de api/rutas/. Busca _conexion en cada
    llamada, así que un monkeypatch de api.main._conexion (como hacen los
    tests de degradación y de registro de fallos) también los alcanza."""
    return _conexion()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # La API no usa geolocalizacion, camara, microfono ni pagos; negarlas
        # no cambia el contrato JSON y cubre clientes que si interpretan la
        # cabecera (p.ej. si /docs se abre en un navegador).
        response.headers["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=(), payment=()"
        )
        if API_DOCS_ENABLED:
            # Allow inline styles/scripts and jsdelivr to ensure FastAPI Swagger UI works.
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com"
        else:
            # Sin Swagger UI la API solo sirve JSON y XML: no hay nada que
            # cargar ni que enmarcar.
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

app.add_middleware(SecurityHeadersMiddleware)

_registro_salud = logging.getLogger("uvicorn.error")


@app.get("/health")
@limiter.exempt
def health_check(response: Response):
    """Endpoint de comprobación de salud que valida la conexión directa a PostgreSQL."""
    # no-store: es un chequeo de salud, cachear una respuesta "ok" vieja
    # derrotaria su proposito (Render lo sondea continuamente).
    response.headers["Cache-Control"] = "no-store"
    try:
        with _conexion() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1;")
        return {
            "status": "ok",
            "service": "backend",
            "database": "connected"
        }
    except Exception as exc:
        # Al cliente nunca se le devuelve la causa. En el registro del servidor
        # va la clase de la excepcion y, solo para OperationalError, el
        # mensaje del servidor ("password authentication failed for user ...",
        # "database ... does not exist"): ese texto no lleva credenciales. El
        # mensaje de otras clases (un DSN mal formado, por ejemplo) puede
        # repetir fragmentos de la URL con la clave, asi que no se registra.
        detalle = str(exc).strip().splitlines()[0] if isinstance(exc, OperationalError) and str(exc).strip() else ""
        _registro_salud.error(
            "health: fallo la conexion a la base (%s)%s",
            type(exc).__name__,
            f": {detalle}" if detalle else "",
        )
        raise HTTPException(
            status_code=500,
            detail="Error de conexión a la base de datos"
        )


# --- Rutas por dominio (api/rutas/) ------------------------------------------
# Cada router se crea aquí, al importar main, con el limiter y la conexión de
# esta app: un importlib.reload(api.main) (los tests de rate limiting, CORS y
# docs) los vuelve a crear con la configuración nueva. El orden es el de
# antes de separarlos; Starlette prueba las rutas en ese orden.
for _router in (
    _rutas_dengue.crear_router(
        limiter=limiter, abrir_conexion=_abrir_conexion, limite_pesado=RATE_LIMIT_HEAVY
    ),
    _rutas_modulos.crear_router(
        limiter=limiter, abrir_conexion=_abrir_conexion, limite_pesado=RATE_LIMIT_HEAVY
    ),
    _rutas_respiratorio.crear_router(
        limiter=limiter, abrir_conexion=_abrir_conexion, limite_pesado=RATE_LIMIT_HEAVY
    ),
    _rutas_alertas.crear_router(
        limiter=limiter, abrir_conexion=_abrir_conexion, limite_escritura=RATE_LIMIT_WRITE
    ),
):
    app.include_router(_router)


# --- Cuentas de usuario (ADR 0024) -----------------------------------------------
# Se monta al final, con todos los helpers ya definidos. Con la variable apagada
# la API es idéntica a la anterior: ninguna ruta nueva y CORS sin credenciales.
if CUENTAS_HABILITADAS:
    from functools import lru_cache

    from .cuentas import correo as _correo_cuentas
    from .cuentas import rutas as _rutas_cuentas
    from .cuentas.config import cargar_config as _cargar_config_cuentas

    app.include_router(
        _rutas_cuentas.crear_router(
            limiter=limiter,
            abrir_conexion=_conexion,
            limite_auth=RATE_LIMIT_AUTH,
            # lru_cache no guarda las excepciones: sin claves configuradas las
            # rutas responden 503 en vez de impedir que arranque la API.
            config_fn=lru_cache(maxsize=1)(_cargar_config_cuentas),
            remitente=_correo_cuentas.RemitenteSmtp(),
            ip_fn=_client_ip,
        )
    )
