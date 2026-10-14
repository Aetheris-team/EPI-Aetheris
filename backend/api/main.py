import csv
import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import joblib
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from psycopg2 import InterfaceError, OperationalError
from psycopg2.errors import UndefinedTable
from psycopg2.pool import ThreadedConnectionPool

from .analisis import (
    ANIOS_ANALISIS_DENGUE,
    cargar_procedencia_observacion,
    construir_dataset_dengue,
)
from .idoneidad import (
    ANIOS_CLIMA,
    calcular_baseline_semana,
    calcular_serie_iv,
    calcular_sigma,
    cargar_clima_departamento,
    cargar_clima_departamentos,
    percentil,
)
from .presion import (
    ANIOS_BASE as ANIOS_BASE_PRESION,
    SERIES as SERIES_PRESION,
    calcular_presion,
    cargar_casos_departamentales,
    cargar_casos_departamento,
)
from .ira import (
    AVISO_HONESTIDAD_IRA,
    cargar_ira_departamental,
    cargar_ira_departamento_temporal,
)
from .neumonias import (
    AVISO_HONESTIDAD_NEUMONIAS,
    ANIOS_NEUMONIAS,
    cargar_heatmap_neumonias,
    cargar_neumonias_departamental,
    cargar_neumonias_departamento_temporal,
)
from .tablero import (
    AVISO_TABLERO_RESPIRATORIO,
    EVENTOS_TABLERO,
    MOTIVO_TABLERO_AUSENTE,
    cargar_serie_tablero_nacional,
)
from .cache_respuestas import CACHE as CACHE_RESPUESTAS, serializar_json
from .claves_api import ClaveApiMiddleware, clave_actual, parsear_claves
from .cobertura import AVISO_COBERTURA, cargar_cobertura
from .conexion_db import parametros_conexion
from .vigilancia import construir_integridad
from .respiratorios import (
    AVISO_HONESTIDAD_VIRUS,
    listar_virus,
    semana_virus,
    serie_virus,
)
from .alertas import (
    DEPARTAMENTOS_ALERTA,
    TIPOS_ALERTA,
    AlertaCrear,
    AlertaParche,
    comprobar_token_escritura,
    consultar_alertas_publicas,
    construir_feed_atom,
    crear_alerta,
    parchear_alerta,
)

# Artefactos de la tarjeta 23/24 -- generados por
# backend/ingestion/construir_dataset_modelado.py y entrenar_clasificador.py,
# leidos aqui via el mismo bind mount de ./backend (docker-compose.yml). No
# hay tabla de predicciones en el esquema (punto G de las decisiones
# abiertas, sin resolver) -- esta es la opcion "on-demand": recalcula desde
# el dataset ya generado en vez de persistir nada nuevo en Postgres.
INGESTION_DIR = Path(__file__).parent.parent / "ingestion"
DATASET_RIESGO_PATH = INGESTION_DIR / "data" / "interim" / "dataset_modelado" / "dataset_modelado.csv"
MODELO_PATH = INGESTION_DIR / "data" / "interim" / "modelo" / "clasificador_riesgo_nacional_v1.joblib"
METRICAS_MODELO_PATH = INGESTION_DIR / "data" / "interim" / "modelo" / "metricas_modelo.json"

AVISO_HONESTIDAD_RIESGO_NACIONAL = (
    "Clasificación entrenada sobre la serie nacional agregada de El Salvador. "
    "El mapa departamental es una capa descriptiva aparte (volumen de casos MINSAL); "
    "estos datos no alimentan ningún clasificador."
)

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

# Claves de API (ADR 0025): quien manda X-API-Key válida usa estos umbrales en
# lugar de RATE_LIMIT_DEFAULT y RATE_LIMIT_HEAVY. La key_func sigue siendo la
# IP: el contador de `limits` lleva el umbral en su llave, así que las
# peticiones con clave cuentan aparte de las anónimas de la misma IP. Escritura
# de alertas y cuentas conservan su umbral, con o sin clave.
API_CLAVES = parsear_claves(os.getenv("API_CLAVES"))
RATE_LIMIT_CLAVE_DEFAULT = os.getenv("RATE_LIMIT_CLAVE_DEFAULT", "1200/minute")
RATE_LIMIT_CLAVE_HEAVY = os.getenv("RATE_LIMIT_CLAVE_HEAVY", "300/minute")


def _limite_global() -> str:
    return RATE_LIMIT_CLAVE_DEFAULT if clave_actual.get() else RATE_LIMIT_DEFAULT


def _limite_pesado() -> str:
    return RATE_LIMIT_CLAVE_HEAVY if clave_actual.get() else RATE_LIMIT_HEAVY


limiter = Limiter(
    key_func=_client_ip,
    default_limits=[_limite_global],
    enabled=RATE_LIMIT_ENABLED,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Se anade ANTES del bloque CORS de abajo para que quede por DENTRO de
# CORSMiddleware: asi la respuesta 429 tambien lleva las cabeceras
# Access-Control-Allow-Origin y el frontend Astro ve un 429 legible en vez de
# un error de red opaco.
app.add_middleware(SlowAPIMiddleware)
# Por fuera de SlowAPIMiddleware (fija la clave antes de que se resuelvan los
# límites) y por dentro de CORS (el 401 de clave inválida lleva sus cabeceras).
app.add_middleware(ClaveApiMiddleware, claves=API_CLAVES)

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


@contextmanager
def _conexion():
    """Toma una conexión del pool y la repone al salir -- también en error,
    para que un request que falla a mitad de camino no se quede con una
    conexión fuera del pool para siempre (con maxconn chico eso agota el
    pool rápido). rollback() antes de devolverla: todas las queries de esta
    API son de solo lectura, pero psycopg2 abre una transacción implícita en
    el primer SELECT -- sin esto la conexión volvería "idle in transaction",
    reteniendo locks hasta el próximo uso."""
    if not _pool_semaforo.acquire(timeout=POSTGRES_POOL_ACQUIRE_TIMEOUT):
        raise TimeoutError(
            "Tiempo de espera agotado para obtener una conexión del pool de Postgres."
        )
    try:
        pool = _obtener_pool()
        conn = pool.getconn()
        try:
            yield conn
        finally:
            try:
                conn.rollback()
            except Exception:
                pass
            pool.putconn(conn)
    finally:
        _pool_semaforo.release()


# --- Cache-Control (informe de rendimiento externo) -------------------------
# Cabeceras HTTP estándar: el navegador reutiliza la respuesta sin volver a
# pedirla. Los mismos TTL gobiernan el cache del servidor (más abajo), así
# que ninguna respuesta sale más vieja de lo que su max-age ya admitía. TTL
# segun que tan seguido cambia el dato real -- ninguno de estos endpoints
# escribe en caliente:
#   - CACHE_TTL_HISTORICO: series ya cargadas en Postgres que solo cambian
#     con una corrida nueva de ingesta (cargar_ira.py, etc.).
#   - CACHE_TTL_COMPUTO: capas espaciales/de cómputo (idoneidad, presión,
#     riesgo-nacional) recalculadas en cada request -- TTL más corto porque
#     son las más caras y las que más se beneficiarían de un cambio de
#     metodología sin esperar una hora completa de cache.
#   - CACHE_TTL_ALERTAS: alertas de campo (ADR 0013). Las redacta y apaga
#     el equipo a mano; el valor de la vista es "¿hay algo vigente ahora?".
#     TTL corto para que un cambio se refleje en el minuto, no en la hora.
CACHE_TTL_HISTORICO = 3600
CACHE_TTL_COMPUTO = 900
CACHE_TTL_ALERTAS = 60


def _cache_control(response: Response, max_age: int) -> None:
    response.headers["Cache-Control"] = f"public, max-age={max_age}"


# --- Cache de respuestas en el servidor (backend/api/cache_respuestas.py) ----
# Lo de arriba solo evita que el MISMO navegador repita la petición; cada
# visitante nuevo volvía a pagar la consulta y el cálculo. Los endpoints de
# solo lectura consultan aquí primero con una clave armada con sus parámetros
# ya validados (no con la URL cruda: un parámetro basura no debe crear otra
# entrada) y guardan el cuerpo serializado con el mismo TTL de su
# Cache-Control. Las respuestas de error y las degradadas
# (disponible=false) no se guardan.
def _json_cacheable(cuerpo: bytes, max_age: int) -> Response:
    return Response(
        content=cuerpo,
        media_type="application/json",
        headers={"Cache-Control": f"public, max-age={max_age}"},
    )


def _desde_cache(clave) -> Response | None:
    acierto = CACHE_RESPUESTAS.obtener(clave)
    if acierto is None:
        return None
    cuerpo, restante = acierto
    return _json_cacheable(cuerpo, restante)


def _cachear(clave, ttl: int, cuerpo) -> Response:
    serializado = serializar_json(cuerpo)
    CACHE_RESPUESTAS.guardar(clave, serializado, ttl)
    return _json_cacheable(serializado, ttl)


# Degradación elegante (issue #84): tabla ausente / sin filas no es un
# fallo de conexión. Mismo contrato que /api/riesgo-nacional (#72):
# 200 { disponible: false, motivo } para que el frontend muestre un aviso
# explícito. Un OperationalError/timeout sí es un problema de servicio.
MOTIVO_VIRUS_AUSENTE = (
    "Los datos de vigilancia de virus respiratorios no están disponibles "
    "en este despliegue (tabla ausente o sin filas)."
)
MOTIVO_NEUMONIAS_AUSENTE = (
    "Los datos de neumonías no están disponibles en este despliegue "
    "(tabla ausente o sin filas)."
)
MOTIVO_COBERTURA_AUSENTE = (
    "La cobertura del observatorio respiratorio no está disponible en "
    "este despliegue (tabla ausente o sin filas)."
)


def _es_tabla_ausente(exc: BaseException) -> bool:
    """True si Postgres reporta relación inexistente (SQLSTATE 42P01)."""
    actual: BaseException | None = exc
    vistos: set[int] = set()
    while actual is not None and id(actual) not in vistos:
        vistos.add(id(actual))
        if isinstance(actual, UndefinedTable):
            return True
        if getattr(actual, "pgcode", None) == "42P01":
            return True
        actual = actual.__cause__ or actual.__context__
    return False


def _es_fallo_conexion(exc: BaseException) -> bool:
    return isinstance(exc, (OperationalError, InterfaceError, TimeoutError))


def _respuesta_no_disponible(response: Response, motivo: str, aviso: str) -> dict:
    _cache_control(response, CACHE_TTL_HISTORICO)
    return {"disponible": False, "motivo": motivo, "aviso": aviso}


def _degradar_consulta(
    exc: BaseException, response: Response, motivo: str, aviso: str
) -> dict:
    """UndefinedTable → 200 disponible=false. Conexión → 503. Resto → 500."""
    if _es_tabla_ausente(exc):
        return _respuesta_no_disponible(response, motivo, aviso)
    status = 503 if _es_fallo_conexion(exc) else 500
    raise HTTPException(
        status_code=status,
        detail="Error de conexión a la base de datos",
    )


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


@app.get("/api/casos-nacional")
def casos_nacional(response: Response):
    """Serie semanal nacional de dengue: el total de OpenDengue
    (opendengue_v1_3) y, en las semanas posteriores a su ultima fila, los
    casos sospechosos del tablero de MINSAL (minsal_tablero, ADR 0021). Es la
    misma definicion de caso; el tablero publica cada semana como un promedio
    de varias. Cada fila lleva su `fuente` para que la UI distinga los dos
    tramos. La semana 53 de 2025, que el tablero no publica, no tiene fila.
    No es clasificacion de riesgo -- para eso ver /api/riesgo-nacional."""
    clave = ("casos-nacional",)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada
    try:
        with _conexion() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    WITH opendengue AS (
                        SELECT s.fecha_inicio, c.anio, c.semana_epi, c.conteo,
                               f.codigo AS fuente
                        FROM casos_epidemiologicos c
                        JOIN regiones r ON r.id = c.region_id
                        JOIN fuentes_datos f ON f.id = c.fuente_id
                        JOIN semanas_epidemiologicas s
                            ON s.anio = c.anio AND s.semana_epi = c.semana_epi
                        WHERE r.codigo = 'SV'
                          AND c.clasificacion = 'total'
                          AND f.codigo = 'opendengue_v1_3'
                    )
                    SELECT * FROM opendengue
                    UNION ALL
                    SELECT s.fecha_inicio, c.anio, c.semana_epi, c.conteo,
                           f.codigo
                    FROM casos_epidemiologicos c
                    JOIN regiones r ON r.id = c.region_id
                    JOIN tipos_evento t ON t.id = c.tipo_evento_id
                    JOIN fuentes_datos f ON f.id = c.fuente_id
                    JOIN semanas_epidemiologicas s
                        ON s.anio = c.anio AND s.semana_epi = c.semana_epi
                    WHERE r.codigo = 'SV'
                      AND t.codigo = 'dengue'
                      AND c.clasificacion = 'sospechoso'
                      AND f.codigo = 'minsal_tablero'
                      AND s.fecha_inicio > COALESCE(
                          (SELECT max(fecha_inicio) FROM opendengue),
                          '-infinity'::date
                      )
                    ORDER BY anio, semana_epi
                    """
                )
                filas = cursor.fetchall()
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Error de conexión a la base de datos"
        )

    return _cachear(clave, CACHE_TTL_HISTORICO, [
        {
            "semana_inicio": fecha_inicio.isoformat(),
            "anio": anio,
            "semana_epi": semana_epi,
            "conteo": conteo,
            "fuente": fuente,
        }
        for fecha_inicio, anio, semana_epi, conteo, fuente in filas
    ])


# Artefactos derivados del clasificador historico (dataset CSV + joblib +
# metricas). La carga es perezosa y se protege con un lock (issue #71): sin
# el, dos requests concurrentes en cold start leen la cache como None a la
# vez y ambos deserializan el joblib / parsean el CSV completo de forma
# redundante -- justo en la rafaga de trafico que el rate limiter busca
# absorber. Double-checked locking: el chequeo rapido sin lock cubre el
# caso normal (cache ya poblada), el lock solo se toma en el arranque.
_artefactos_lock = threading.Lock()
_modelo_cache = None
_dataset_riesgo_cache = None


def _cargar_modelo():
    """Devuelve el paquete del modelo, o None si el joblib no existe en este
    despliegue (issue #72) -- el handler traduce None a una respuesta 200
    explicita en vez de un 503."""
    global _modelo_cache
    if _modelo_cache is None:
        with _artefactos_lock:
            if _modelo_cache is None:
                if not MODELO_PATH.exists():
                    return None
                _modelo_cache = joblib.load(MODELO_PATH)
    return _modelo_cache


def _cargar_dataset_riesgo():
    """Devuelve las filas del dataset de modelado, o None si el CSV no
    existe en este despliegue (issue #72)."""
    global _dataset_riesgo_cache
    if _dataset_riesgo_cache is None:
        with _artefactos_lock:
            if _dataset_riesgo_cache is None:
                if not DATASET_RIESGO_PATH.exists():
                    return None
                with open(DATASET_RIESGO_PATH, newline="", encoding="utf-8") as f:
                    _dataset_riesgo_cache = list(csv.DictReader(f))
    return _dataset_riesgo_cache


@app.get("/api/riesgo-nacional")
@limiter.limit(_limite_pesado)
def riesgo_nacional(
    request: Request,
    response: Response,
    anio: int | None = None,
    semana: int | None = None,
):
    """Clasificación de riesgo NACIONAL para una semana epidemiológica dada
    (tarjetas 23/24/25, primera versión: semana fija, colores planos --
    selector de semanas viene después). Recalcula on-demand desde el dataset
    ya generado, no persiste nada nuevo en Postgres (ver comentario junto a
    DATASET_RIESGO_PATH).

    Sin parámetros, devuelve la última semana disponible del dataset (fin
    de 2023, año de prueba de la tarjeta 24) -- el sistema no tiene forma
    de verificar en vivo lo que predice, no hay fuente departamental
    automatizable después de 2023.
    """
    filas = _cargar_dataset_riesgo()
    modelo_paquete = _cargar_modelo() if filas is not None else None
    if filas is None or modelo_paquete is None:
        # Los artefactos derivados (dataset_modelado.csv + joblib) estan en
        # .gitignore y no se generan en el build de Render, asi que faltan en
        # produccion (issue #72). No es un error del servidor: se responde
        # 200 con disponible=false y el frontend muestra un aviso explicito,
        # mismo patron que /ira cuando falta su extracto exploratorio.
        _cache_control(response, CACHE_TTL_COMPUTO)
        return {
            "disponible": False,
            "motivo": (
                "El clasificador nacional historico no esta generado en este "
                "despliegue (dataset de modelado y/o modelo entrenado ausentes)."
            ),
            "aviso": AVISO_HONESTIDAD_RIESGO_NACIONAL,
        }

    if anio is None or semana is None:
        fila = max(filas, key=lambda r: (int(r["anio"]), int(r["semana_epi"])))
    else:
        coincidencias = [r for r in filas if int(r["anio"]) == anio and int(r["semana_epi"]) == semana]
        if not coincidencias:
            raise HTTPException(
                status_code=404,
                detail=f"No hay datos de modelado para año={anio}, semana={semana}.",
            )
        fila = coincidencias[0]

    modelo = modelo_paquete["modelo"]
    columnas_feature = modelo_paquete["columnas_feature"]
    clases = modelo_paquete["clases"]

    X = [[float(fila[c]) for c in columnas_feature]]
    etiqueta_predicha = modelo.predict(X)[0]
    probabilidades = dict(zip(modelo.classes_, modelo.predict_proba(X)[0].tolist()))

    metricas_modelo = None
    if METRICAS_MODELO_PATH.exists():
        metricas_modelo = json.loads(METRICAS_MODELO_PATH.read_text(encoding="utf-8"))

    _cache_control(response, CACHE_TTL_COMPUTO)
    return {
        "disponible": True,
        "anio": int(fila["anio"]),
        "semana_epi": int(fila["semana_epi"]),
        "etiqueta_predicha": etiqueta_predicha,
        "etiqueta_real": fila["etiqueta_riesgo"],
        "probabilidades": {clase: round(probabilidades.get(clase, 0.0), 4) for clase in clases},
        "casos_observados": float(fila["casos"]),
        "metricas_modelo": metricas_modelo,
        "aviso": AVISO_HONESTIDAD_RIESGO_NACIONAL,
    }


NOWCAST_DENGUE_PATH = Path(__file__).parent / "datos" / "nowcast_dengue.json"


def _servir_artefacto(ruta: Path, aviso: str) -> Response:
    """Cuerpo de los artefactos versionados de backend/api/datos/: el JSON
    tal cual con `disponible` y `aviso` delante. Leerlo, parsearlo y volver a
    serializarlo costaba decenas de ms por request en los de 200-300 KB; la
    clave lleva el mtime para que un artefacto regenerado no se sirva viejo.
    Quien llama ya comprobó que el archivo existe."""
    clave = ("artefacto", str(ruta), ruta.stat().st_mtime_ns)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return _cachear(clave, CACHE_TTL_HISTORICO, {"disponible": True, "aviso": aviso, **datos})

AVISO_HONESTIDAD_NOWCAST_DENGUE = (
    "Prediccion estadistica de horizonte corto sobre la serie nacional de "
    "dengue: OpenDengue hasta 2024 y sospechosos del tablero de MINSAL desde "
    "2025. Se extiende desde la ultima semana publicada. Desde 2025 combina el "
    "modelo validado con una tendencia amortiguada y esta en prueba con las "
    "semanas publicadas desde 2026-S38."
)


@app.get("/api/nowcast-dengue")
@limiter.limit(_limite_pesado)
def nowcast_dengue(request: Request, response: Response):
    """Artefacto de prediccion de horizonte corto de dengue, precomputado por
    backend/ingestion/nowcast_tablero_dengue.py sobre la base de
    nowcast_estimacion_dengue.py (ADR 0020 y
    docs/experimentos/experimento-nowcast-tendencia.md). Se sirve tal cual
    desde el JSON versionado; no recalcula nada por request. Si el archivo
    falta -- despliegue sin el artefacto -- responde 200 con disponible=false,
    mismo patron que /api/riesgo-nacional y /ira."""
    if not NOWCAST_DENGUE_PATH.exists():
        _cache_control(response, CACHE_TTL_COMPUTO)
        return {
            "disponible": False,
            "motivo": "El artefacto de prediccion de horizonte corto no esta generado en este despliegue.",
            "aviso": AVISO_HONESTIDAD_NOWCAST_DENGUE,
        }
    return _servir_artefacto(NOWCAST_DENGUE_PATH, AVISO_HONESTIDAD_NOWCAST_DENGUE)


NOWCAST_DENGUE_RETRO_PATH = NOWCAST_DENGUE_PATH.with_name("nowcast_dengue_retrospectivo.json")


@app.get("/api/nowcast-dengue/retrospectivo")
@limiter.limit(_limite_pesado)
def nowcast_dengue_retrospectivo(request: Request, response: Response):
    """Abanico h=1..8 que el modelo habria dado desde cada semana de la serie,
    con los datos disponibles hasta esa semana, para contrastarlo con lo
    observado. Precomputado por
    backend/ingestion/nowcast_retrospectivo_dengue.py (hasta 2024) y
    nowcast_tablero_dengue.py (desde 2025); va en un endpoint aparte porque
    pesa ~10 veces mas que /api/nowcast-dengue y solo lo pide la vista
    completa del panel."""
    if not NOWCAST_DENGUE_RETRO_PATH.exists():
        _cache_control(response, CACHE_TTL_COMPUTO)
        return {
            "disponible": False,
            "motivo": "El artefacto retrospectivo de la prediccion no esta generado en este despliegue.",
            "aviso": AVISO_HONESTIDAD_NOWCAST_DENGUE,
        }
    return _servir_artefacto(NOWCAST_DENGUE_RETRO_PATH, AVISO_HONESTIDAD_NOWCAST_DENGUE)


# Analisis descriptivo de clima y dengue (ADR 0023). Dos artefactos
# precomputados y versionados, servidos tal cual: no recalculan nada por
# request y no alimentan el pronostico de /api/nowcast-dengue.
CLIMA_DENGUE_POR_ANIO_PATH = Path(__file__).parent / "datos" / "clima_dengue_por_anio.json"
CLIMA_DENGUE_MULTIPAIS_PATH = Path(__file__).parent / "datos" / "clima_dengue_multipais.json"

AVISO_HONESTIDAD_CLIMA_DENGUE = (
    "Descripción de datos de 2014 a 2024: correlaciones entre anomalías y "
    "diferencias de desempeño del predictor por año, sin atribución de causa. "
    "No alimenta el pronóstico publicado."
)


def _servir_clima_dengue(response: Response, ruta: Path, motivo: str) -> dict | Response:
    """Contrato de los artefactos versionados: sin el archivo responde 200 con
    disponible=false (mismo patron que /api/nowcast-dengue)."""
    if not ruta.exists():
        _cache_control(response, CACHE_TTL_COMPUTO)
        return {"disponible": False, "motivo": motivo, "aviso": AVISO_HONESTIDAD_CLIMA_DENGUE}
    return _servir_artefacto(ruta, AVISO_HONESTIDAD_CLIMA_DENGUE)


@app.get("/api/clima-dengue/por-anio")
@limiter.limit(_limite_pesado)
def clima_dengue_por_anio(request: Request, response: Response):
    """Clima y dengue de El Salvador año por año (2014-2019 y 2021-2023):
    aporte del clima al pronóstico (A1), ciclo medio y desfase (A2), correlación
    entre la anomalía climática y el crecimiento a 4 semanas por año y agrupada
    (A3), perfil de cada año (A4), consistencia entre años (A5) y las series
    semanales usadas."""
    return _servir_clima_dengue(
        response,
        CLIMA_DENGUE_POR_ANIO_PATH,
        "El análisis de clima y dengue por año no está generado en este despliegue.",
    )


@app.get("/api/clima-dengue/multipais")
@limiter.limit(_limite_pesado)
def clima_dengue_multipais(request: Request, response: Response):
    """El Salvador frente a 18 países de las Américas (OpenDengue/OPS, 2014-2024):
    perfil de cada país (P1), señal regional y posición de El Salvador (P2),
    asociación clima-crecimiento por país (P3), ciclo medio (P4), corridas
    anteriores del clasificador (P5) y posiciones (P6). Va aparte del anterior
    porque pesa ~320 KB."""
    return _servir_clima_dengue(
        response,
        CLIMA_DENGUE_MULTIPAIS_PATH,
        "El análisis de El Salvador frente a otros países no está generado en este despliegue.",
    )


AVISO_HONESTIDAD_CASOS_DEPARTAMENTALES = (
    "Casos probables y confirmados desacumulados de boletines MINSAL "
    "(2018-2023, con huecos entre boletines). El color representa volumen "
    "acumulado en la ventana cargada."
)


@app.get("/api/casos-departamentales")
@limiter.limit(_limite_pesado)
def casos_departamentales(request: Request, response: Response):
    """Capa descriptiva del mapa (tarjeta 25) -- casos MINSAL desacumulados
    (tarjeta 22) sumados por departamento en toda la ventana cargada
    (2018-2023, sin 2020 ni 2024+ porque no hay boletín automatizable desde
    entonces). Se agrega el acumulado completo, no una sola semana: con
    87-93% de celdas departamento-semana en cero, una sola semana suele salir casi
    vacía y no representa bien la distribución real -- esto es una elección
    de presentación, no una decisión de equipo cerrada.

    RATE_LIMIT_HEAVY (no el limite global): agrega con GROUP BY + JOIN sobre
    toda la ventana cargada en cada request, igual de pesado que los
    endpoints /api/v1/* que ya tenian este umbral desde el PR #61."""
    clave = ("casos-departamentales",)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada
    try:
        with _conexion() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        r.nombre,
                        r.codigo,
                        sum(c.conteo) FILTER (WHERE c.clasificacion = 'probable') AS probable_total,
                        sum(c.conteo) FILTER (WHERE c.clasificacion = 'confirmado') AS confirmado_total,
                        count(DISTINCT c.anio || '-' || c.semana_epi) FILTER (WHERE c.clasificacion = 'probable') AS semanas_con_dato_probable,
                        min(c.anio) AS primer_anio,
                        max(c.anio) AS ultimo_anio
                    FROM regiones r
                    LEFT JOIN casos_epidemiologicos c
                        ON c.region_id = r.id
                        AND c.fuente_id = (SELECT id FROM fuentes_datos WHERE codigo = 'minsal_pdf')
                    WHERE r.nivel_admin = 1
                    GROUP BY r.nombre, r.codigo
                    ORDER BY r.nombre
                    """
                )
                filas = cursor.fetchall()
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Error de conexión a la base de datos"
        )

    return _cachear(clave, CACHE_TTL_HISTORICO, {
        "departamentos": [
            {
                "nombre": nombre,
                "codigo": codigo,
                "probable_total": int(probable_total) if probable_total is not None else 0,
                "confirmado_total": int(confirmado_total) if confirmado_total is not None else 0,
                "semanas_con_dato_probable": int(semanas_con_dato) if semanas_con_dato is not None else 0,
                "primer_anio": primer_anio,
                "ultimo_anio": ultimo_anio,
            }
            for nombre, codigo, probable_total, confirmado_total, semanas_con_dato, primer_anio, ultimo_anio in filas
        ],
        "aviso": AVISO_HONESTIDAD_CASOS_DEPARTAMENTALES,
    })


# ---------------------------------------------------------------------------
# Módulos descriptivos -- Módulo 1 (idoneidad biofísica Iv) y Módulo 2 (anomalía
# climática continua). Ver backend/api/idoneidad.py para las fórmulas y su
# procedencia (duplicadas literalmente desde
# backend/ingestion/validar_leadtime_idoneidad.py, experimento ya
# validado).
#
# La validación empírica descartó la tesis de "ventana de anticipación"
# (lead time) -- por eso estos endpoints NO exponen alerta binaria, NO
# exponen ningún campo de lead time, y NO usan lenguaje de anticipación en
# ningún lado. Solo Iv y un Z-score continuo (sigma), descriptivos.
# ---------------------------------------------------------------------------

AVISO_HONESTIDAD_IDONEIDAD = (
    "Índice de idoneidad biofísica (Iv) para Aedes aegypti, a partir de clima ERA5-Land "
    "(temperatura, precipitación a 2 semanas, humedad). Describe condición ambiental, "
    "no incidencia ni riesgo: los casos MINSAL y la presión epidemiológica se detienen "
    "en 2023, y el reanálisis ERA5 llega hasta unos 5 días antes de hoy. Una validación "
    "retrospectiva mostró que no anticipa de forma consistente el ascenso de casos; el "
    "componente de humedad es una estimación propia del equipo."
)


@app.get("/api/v1/spatial/current")
@limiter.limit(_limite_pesado)
def idoneidad_espacial_actual(request: Request, response: Response, week: int, year: int):
    """Índice de idoneidad biofísica (Iv) y anomalía climática continua
    (anomaly_sigma), por departamento, para la semana epidemiológica y año
    pedidos. Capa DESCRIPTIVA -- no hay campo de lead time ni de alerta
    binaria (ver AVISO_HONESTIDAD_IDONEIDAD y docstring del módulo
    idoneidad.py: esa tesis fue retirada tras validación empírica).

    El baseline de anomaly_sigma es leave-one-out sobre ANIOS_CLIMA (2014
    hasta el año en curso; ADR 0018). Excluye el propio año pedido, misma
    semana exacta, sin ventana de semanas vecinas. Departamentos con menos
    de 3 años de baseline disponible devuelven anomaly_sigma=null.
    """
    if not (1 <= week <= 53):
        raise HTTPException(status_code=422, detail="El parámetro 'week' debe estar entre 1 y 53.")

    clave = ("spatial-current", week, year)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada

    semanas_necesarias = [week] if week == 1 else [week - 1, week]

    try:
        with _conexion() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT codigo, nombre FROM regiones WHERE nivel_admin = 1 ORDER BY nombre")
                departamentos = cursor.fetchall()
            clima = cargar_clima_departamentos(conn, anios=ANIOS_CLIMA, semanas=semanas_necesarias)
    except Exception:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")

    serie_iv = calcular_serie_iv(clima)

    resultado = []
    for codigo, nombre in departamentos:
        serie_codigo = serie_iv.get(codigo, {})
        valor = serie_codigo.get(year, {}).get(week)
        if valor is None:
            resultado.append({
                "codigo": codigo,
                "nombre": nombre,
                "iv": None,
                "anomaly_sigma": None,
                "nota": "sin datos climáticos completos para esta semana/año en este departamento",
            })
            continue

        _, mediana, desv = calcular_baseline_semana(serie_codigo, anio_excluir=year, semana=week)
        sigma = calcular_sigma(valor, mediana, desv)
        resultado.append({
            "codigo": codigo,
            "nombre": nombre,
            "iv": round(valor, 4),
            "anomaly_sigma": round(sigma, 4) if sigma is not None else None,
        })

    return _cachear(clave, CACHE_TTL_COMPUTO, {
        "semana_epi": week,
        "anio": year,
        "departamentos": resultado,
        "aviso": AVISO_HONESTIDAD_IDONEIDAD,
    })


# ---------------------------------------------------------------------------
# Módulos descriptivos -- Módulo 3 (presión epidemiológica relativa). Ver
# backend/api/presion.py para la fórmula (cerrada por el coordinador)
# y su procedencia (mismo patrón de
# percentil leave-one-out que corrida_canal_endemico_nacional.py). Igual que
# M1/M2: calculado on-request, nada persistido, sin cambios de esquema.
# ---------------------------------------------------------------------------

AVISO_HONESTIDAD_PRESION = (
    "Percentil del conteo observado (MINSAL, desacumulado) dentro de la historia "
    "del propio departamento (años base 2018, 2019, 2021-2023; ventana ±1 semana, "
    "leave-one-out). Los cortes P50/P75 son deliberadamente sensibles: 'alta' puede "
    "aparecer en años de baja transmisión. 'probable' y 'confirmado' son series "
    "separadas."
)


@app.get("/api/v1/analisis/dengue")
@limiter.limit(_limite_pesado)
def dataset_analitico_dengue(request: Request, response: Response, year: int):
    """Dataset anual compartido para exploracion descriptiva de dengue.

    Agrega casos MINSAL, M1, M2 y M3 por departamento/semana reutilizando
    sus motores actuales. No persiste resultados ni modifica metodologia.
    """
    if year not in ANIOS_ANALISIS_DENGUE:
        disponibles = ", ".join(str(anio) for anio in ANIOS_ANALISIS_DENGUE)
        raise HTTPException(
            status_code=422,
            detail=f"El parametro 'year' debe ser uno de: {disponibles}.",
        )

    clave = ("analisis-dengue", year)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada

    try:
        with _conexion() as conn:
            respuesta = construir_dataset_dengue(conn, anio=year)
    except Exception:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")

    respuesta["avisos"] = {
        "idoneidad": AVISO_HONESTIDAD_IDONEIDAD,
        "presion": AVISO_HONESTIDAD_PRESION,
    }
    return _cachear(clave, CACHE_TTL_HISTORICO, respuesta)


@app.get("/api/v1/analisis/dengue/procedencia")
@limiter.limit(_limite_pesado)
def procedencia_analitica_dengue(request: Request, response: Response, year: int, week: int, dept: str, serie: str):
    """Trazabilidad almacenada de una observacion departamental de dengue."""
    if year not in ANIOS_ANALISIS_DENGUE:
        disponibles = ", ".join(str(anio) for anio in ANIOS_ANALISIS_DENGUE)
        raise HTTPException(
            status_code=422,
            detail=f"El parametro 'year' debe ser uno de: {disponibles}.",
        )
    if not (1 <= week <= 53):
        raise HTTPException(
            status_code=422,
            detail="El parámetro 'week' debe estar entre 1 y 53.",
        )
    if serie not in SERIES_PRESION:
        raise HTTPException(
            status_code=422,
            detail="El parámetro 'serie' debe ser 'probable' o 'confirmado'.",
        )

    try:
        with _conexion() as conn:
            respuesta = cargar_procedencia_observacion(
                conn,
                anio=year,
                semana=week,
                departamento_codigo=dept,
                serie=serie,
            )
    except Exception:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")

    if respuesta is None:
        raise HTTPException(
            status_code=404,
            detail=f"No existe un departamento con código '{dept}'.",
        )
    _cache_control(response, CACHE_TTL_HISTORICO)
    return respuesta


@app.get("/api/v1/presion/current")
@limiter.limit(_limite_pesado)
def presion_espacial_actual(request: Request, response: Response, week: int, year: int):
    """Presión epidemiológica relativa (Módulo 3) por departamento, para la
    semana epidemiológica y año pedidos, en dos series separadas
    ('probable' y 'confirmado', nunca fusionadas). Estructura espejo de
    /api/v1/spatial/current. Capa DESCRIPTIVA -- ver
    AVISO_HONESTIDAD_PRESION y el docstring de presion.py.

    Celdas sin baseline suficiente (menos de 3 de los 4 años leave-one-out
    con observaciones en la ventana ±1) devuelven percentil=null con nota
    explícita -- nunca un valor inventado ni interpolado.
    """
    if not (1 <= week <= 53):
        raise HTTPException(status_code=422, detail="El parámetro 'week' debe estar entre 1 y 53.")

    clave = ("presion-current", week, year)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada

    # Solo la ventana ±1 de la semana pedida; el baseline necesita los años
    # base completos más el año descrito (si no es uno de ellos).
    semanas_necesarias = [w for w in (week - 1, week, week + 1) if w >= 1]
    anios_necesarios = sorted(set(ANIOS_BASE_PRESION) | {year})

    try:
        with _conexion() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT codigo, nombre FROM regiones WHERE nivel_admin = 1 ORDER BY nombre")
                departamentos = cursor.fetchall()
            casos = cargar_casos_departamentales(conn, anios=anios_necesarios, semanas=semanas_necesarias)
    except Exception:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")

    resultado = []
    for codigo, nombre in departamentos:
        fila = {"codigo": codigo, "nombre": nombre}
        for serie in SERIES_PRESION:
            fila[serie] = calcular_presion(casos.get(codigo, {}).get(serie, {}), anio=year, semana=week)
        resultado.append(fila)

    return _cachear(clave, CACHE_TTL_COMPUTO, {
        "semana_epi": week,
        "anio": year,
        "departamentos": resultado,
        "aviso": AVISO_HONESTIDAD_PRESION,
    })


@app.get("/api/v1/presion/temporal/{departamento_id}")
def presion_temporal_departamento(departamento_id: str, anio: int, response: Response):
    """Serie temporal de presión epidemiológica relativa (Módulo 3) de un
    departamento para `anio`, en las dos series separadas. Espejo de
    /api/v1/temporal/{departamento_id}. `departamento_id` es el `codigo`
    de `regiones` (ISO 3166-2:SV, ej. 'SV-SS')."""
    clave = ("presion-temporal", departamento_id, anio)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada

    anios_necesarios = sorted(set(ANIOS_BASE_PRESION) | {anio})

    try:
        with _conexion() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT codigo, nombre FROM regiones WHERE nivel_admin = 1 AND codigo = %s",
                    (departamento_id,),
                )
                fila_region = cursor.fetchone()
            if fila_region is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No existe un departamento con código '{departamento_id}'.",
                )
            casos_depto = cargar_casos_departamento(conn, codigo=departamento_id, anios=anios_necesarios)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")

    codigo, nombre = fila_region

    # Todas las semanas con alguna observación en cualquier año/serie -- las
    # semanas sin dato del propio `anio` salen con nota, no se omiten.
    todas_las_semanas = sorted({
        semana
        for series in casos_depto.values()
        for semanas in series.values()
        for semana in semanas
    })

    semanas_salida = []
    for semana in todas_las_semanas:
        fila = {"semana_epi": semana}
        for serie in SERIES_PRESION:
            fila[serie] = calcular_presion(casos_depto.get(serie, {}), anio=anio, semana=semana)
        semanas_salida.append(fila)

    return _cachear(clave, CACHE_TTL_HISTORICO, {
        "departamento_codigo": codigo,
        "departamento_nombre": nombre,
        "anio": anio,
        "semanas": semanas_salida,
        "aviso": AVISO_HONESTIDAD_PRESION,
    })


@app.get("/api/v1/temporal/{departamento_id}")
def idoneidad_temporal_departamento(departamento_id: str, anio: int, response: Response):
    """Serie temporal de un departamento (Módulos 1 y 2): banda histórica
    (P25/mediana/P75 de Iv por semana-del-año, leave-one-out excluyendo
    `anio`) vs. la serie real de `anio`, con anomaly_sigma continuo por
    semana. `departamento_id` es el `codigo` de `regiones` (ISO 3166-2:SV,
    ej. 'SV-SS') -- es el identificador estable que ya usa el resto de la
    API (ver /api/casos-departamentales), no el id numérico interno.

    Capa DESCRIPTIVA -- no hay `estimated_transmission_window_start` ni
    `season_shift_alert` (retirados, ver AVISO_HONESTIDAD_IDONEIDAD)."""
    clave = ("idoneidad-temporal", departamento_id, anio)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada

    try:
        with _conexion() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT codigo, nombre FROM regiones WHERE nivel_admin = 1 AND codigo = %s",
                    (departamento_id,),
                )
                fila_region = cursor.fetchone()
            if fila_region is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No existe un departamento con código '{departamento_id}'.",
                )
            clima_depto = cargar_clima_departamento(conn, codigo=departamento_id, anios=ANIOS_CLIMA)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")

    codigo, nombre = fila_region

    serie_iv = calcular_serie_iv({codigo: clima_depto})
    serie_codigo = serie_iv.get(codigo, {})

    todas_las_semanas = sorted({
        semana
        for semanas in serie_codigo.values()
        for semana in semanas
    })

    semanas_salida = []
    for semana in todas_las_semanas:
        pool, mediana, desv = calcular_baseline_semana(serie_codigo, anio_excluir=anio, semana=semana)
        iv_real = serie_codigo.get(anio, {}).get(semana)
        sigma = calcular_sigma(iv_real, mediana, desv) if iv_real is not None else None
        semanas_salida.append({
            "semana_epi": semana,
            "iv_real": round(iv_real, 4) if iv_real is not None else None,
            "p25_baseline": round(percentil(pool, 0.25), 4) if pool else None,
            "mediana_baseline": round(mediana, 4) if mediana is not None else None,
            "p75_baseline": round(percentil(pool, 0.75), 4) if pool else None,
            "anomaly_sigma": round(sigma, 4) if sigma is not None else None,
        })

    return _cachear(clave, CACHE_TTL_HISTORICO, {
        "departamento_codigo": codigo,
        "departamento_nombre": nombre,
        "anio": anio,
        "semanas": semanas_salida,
        "aviso": AVISO_HONESTIDAD_IDONEIDAD,
    })


# ---------------------------------------------------------------------------
# Infección Respiratoria Aguda (IRA) -- ADR 0011 (aceptado 2026-08-22).
# Ver backend/api/ira.py: NO es uno de los módulos descriptivos de dengue (M1-M4), es
# otro tipo_evento con su propia serie 'notificado', sin Iv/anomalía/presión
# calculados. Cargado por backend/ingestion/cargar_ira.py (2742 filas,
# 2018-2023 sin 2020, 14 departamentos).
# ---------------------------------------------------------------------------


@app.get("/api/ira/departamental")
@limiter.limit(_limite_pesado)
def ira_departamental(request: Request, response: Response):
    """Resumen por departamento del conteo notificado de IRA (total
    acumulado en la ventana cargada, semanas con dato, rango de años) --
    espejo de /api/casos-departamentales. Capa DESCRIPTIVA, ver
    AVISO_HONESTIDAD_IRA.

    RATE_LIMIT_HEAVY (no el limite global), mismo criterio que
    /api/casos-departamentales. El informe de rendimiento externo lo señaló
    como el más lento; medido con el seed, la consulta tarda ~2 ms con las
    páginas en memoria y ~160 ms cuando hay que leerlas de disco (la BD de
    Render tiene 256 MB). El cache de respuestas la evita salvo una vez por
    CACHE_TTL_HISTORICO."""
    clave = ("ira-departamental",)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada
    try:
        with _conexion() as conn:
            departamentos = cargar_ira_departamental(conn)
    except Exception:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")

    return _cachear(clave, CACHE_TTL_HISTORICO, {
        "departamentos": departamentos,
        "aviso": AVISO_HONESTIDAD_IRA,
    })


@app.get("/api/ira/temporal/{departamento_id}")
def ira_temporal_departamento(departamento_id: str, response: Response):
    """Serie semanal de IRA notificada de un departamento, por año
    (2018-2023, sin 2020). `departamento_id` es el `codigo` de `regiones`
    (ISO 3166-2:SV, ej. 'SV-SS'). Las semanas sin fila son huecos reales de
    la fuente MINSAL (boletín de vacaciones, tabla como imagen, corrección
    retroactiva excluida) -- se devuelven como ausentes, nunca como cero ni
    valor interpolado."""
    clave = ("ira-temporal", departamento_id)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada
    try:
        with _conexion() as conn:
            resultado = cargar_ira_departamento_temporal(conn, codigo=departamento_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")
    if resultado is None:
        raise HTTPException(
            status_code=404,
            detail=f"No existe un departamento con código '{departamento_id}'.",
        )
    nombre, serie = resultado

    anios = sorted(serie.keys())
    return _cachear(clave, CACHE_TTL_HISTORICO, {
        "departamento_codigo": departamento_id,
        "departamento_nombre": nombre,
        "anios": anios,
        "series": {
            str(anio): [[semana, valor] for semana, valor in sorted(semanas.items())]
            for anio, semanas in serie.items()
        },
        "aviso": AVISO_HONESTIDAD_IRA,
    })


def _serie_respiratoria_nacional(evento: str, response: Response) -> dict | Response:
    """Serie nacional del tablero de MINSAL (ADR 0021) para IRA o neumonías.
    Sin capturas cargadas responde 200 disponible=false: el seed del
    repositorio no trae el tablero."""
    clave = ("tablero-nacional", evento)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada
    try:
        with _conexion() as conn:
            semanas = cargar_serie_tablero_nacional(conn, EVENTOS_TABLERO[evento])
    except Exception as exc:
        return _degradar_consulta(
            exc, response, MOTIVO_TABLERO_AUSENTE, AVISO_TABLERO_RESPIRATORIO
        )

    if not semanas:
        return _respuesta_no_disponible(
            response, MOTIVO_TABLERO_AUSENTE, AVISO_TABLERO_RESPIRATORIO
        )

    return _cachear(clave, CACHE_TTL_HISTORICO, {
        "disponible": True,
        "evento": evento,
        "fuente": "minsal_tablero",
        "unidad": "conteo_notificado",
        "semanas": semanas,
        "aviso": AVISO_TABLERO_RESPIRATORIO,
    })


@app.get("/api/ira/nacional")
def ira_nacional(response: Response):
    """Serie semanal nacional de IRA notificada, del tablero de MINSAL desde
    2025. La semana 53 de 2025, que el tablero no publica, no tiene fila."""
    return _serie_respiratoria_nacional("ira", response)


@app.get("/api/neumonias/nacional")
def neumonias_nacional(response: Response):
    """Serie semanal nacional de neumonías notificadas, del tablero de MINSAL
    desde 2025. Mismo contrato que /api/ira/nacional."""
    return _serie_respiratoria_nacional("neumonias", response)


@app.get("/api/neumonias/departamental")
def neumonias_departamental(response: Response):
    """Resumen departamental de Neumonías notificadas. Capa descriptiva."""
    clave = ("neumonias-departamental",)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada
    try:
        with _conexion() as conn:
            departamentos = cargar_neumonias_departamental(conn)
    except Exception as exc:
        return _degradar_consulta(
            exc, response, MOTIVO_NEUMONIAS_AUSENTE, AVISO_HONESTIDAD_NEUMONIAS
        )

    return _cachear(clave, CACHE_TTL_HISTORICO, {
        "disponible": True,
        "departamentos": departamentos,
        "aviso": AVISO_HONESTIDAD_NEUMONIAS,
    })


@app.get("/api/neumonias/temporal/{departamento_id}")
def neumonias_temporal_departamento(departamento_id: str, response: Response):
    clave = ("neumonias-temporal", departamento_id)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada
    try:
        with _conexion() as conn:
            resultado = cargar_neumonias_departamento_temporal(conn, codigo=departamento_id)
    except Exception as exc:
        return _degradar_consulta(
            exc, response, MOTIVO_NEUMONIAS_AUSENTE, AVISO_HONESTIDAD_NEUMONIAS
        )
    if resultado is None:
        raise HTTPException(
            status_code=404,
            detail=f"No existe un departamento con código '{departamento_id}'.",
        )
    nombre, serie = resultado

    return _cachear(clave, CACHE_TTL_HISTORICO, {
        "disponible": True,
        "departamento_codigo": departamento_id,
        "departamento_nombre": nombre,
        "anios": sorted(serie.keys()),
        "series": {
            str(anio): [[semana, valor] for semana, valor in sorted(semanas.items())]
            for anio, semanas in serie.items()
        },
        "aviso": AVISO_HONESTIDAD_NEUMONIAS,
        "unidad": "conteo_notificado",
    })


@app.get("/api/neumonias/heatmap/{anio}")
def neumonias_heatmap(anio: int, response: Response):
    """Matriz departamento × semana. Celdas ausentes son huecos, no ceros."""
    if anio not in ANIOS_NEUMONIAS:
        raise HTTPException(
            status_code=400,
            detail=f"año {anio} fuera de la ventana cargada {ANIOS_NEUMONIAS}",
        )
    clave = ("neumonias-heatmap", anio)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada
    try:
        with _conexion() as conn:
            departamentos = cargar_heatmap_neumonias(conn, anio)
    except Exception as exc:
        return _degradar_consulta(
            exc, response, MOTIVO_NEUMONIAS_AUSENTE, AVISO_HONESTIDAD_NEUMONIAS
        )

    return _cachear(clave, CACHE_TTL_HISTORICO, {
        "disponible": True,
        "anio": anio,
        "unidad": "conteo_notificado",
        "departamentos": departamentos,
        "aviso": AVISO_HONESTIDAD_NEUMONIAS,
    })


@app.get("/api/respiratorios/virus")
def respiratorios_virus(response: Response):
    """Catálogo de series disponibles (virus × métrica × unidad). Nacional."""
    clave = ("virus-catalogo",)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada
    try:
        with _conexion() as conn:
            series = listar_virus(conn)
    except Exception as exc:
        return _degradar_consulta(
            exc, response, MOTIVO_VIRUS_AUSENTE, AVISO_HONESTIDAD_VIRUS
        )

    if not series:
        return _respuesta_no_disponible(
            response, MOTIVO_VIRUS_AUSENTE, AVISO_HONESTIDAD_VIRUS
        )

    return _cachear(clave, CACHE_TTL_HISTORICO, {
        "disponible": True,
        "series": series,
        "aviso": AVISO_HONESTIDAD_VIRUS,
        "granularidad": "nacional",
    })


@app.get("/api/respiratorios/temporal")
def respiratorios_temporal(response: Response, virus: str, metrica: str = "detecciones"):
    """Serie nacional semanal de un virus y una métrica (detecciones|positividad|muestras_analizadas|muestras_positivas)."""
    permitidas = {"detecciones", "positividad", "muestras_analizadas", "muestras_positivas"}
    if metrica not in permitidas:
        raise HTTPException(status_code=400, detail=f"metrica debe ser una de {sorted(permitidas)}")
    clave = ("virus-temporal", virus, metrica)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada
    try:
        with _conexion() as conn:
            serie, unidad = serie_virus(conn, virus=virus, metrica=metrica)
    except Exception as exc:
        return _degradar_consulta(
            exc, response, MOTIVO_VIRUS_AUSENTE, AVISO_HONESTIDAD_VIRUS
        )
    if not serie:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No hay serie disponible para virus='{virus}' y metrica='{metrica}'. "
                "Consulte GET /api/respiratorios/virus para las combinaciones cargadas."
            ),
        )

    return _cachear(clave, CACHE_TTL_HISTORICO, {
        "disponible": True,
        "virus": virus,
        "metrica": metrica,
        "unidad": unidad,
        "granularidad": "nacional",
        "anios": sorted(serie.keys()),
        "series": {
            str(anio): [[semana, valor] for semana, valor in sorted(semanas.items())]
            for anio, semanas in serie.items()
        },
        "aviso": AVISO_HONESTIDAD_VIRUS,
    })


@app.get("/api/respiratorios/semana/{anio}/{semana}")
def respiratorios_semana(anio: int, semana: int, response: Response):
    if semana < 1 or semana > 53:
        raise HTTPException(status_code=400, detail="semana epidemiológica fuera de 1-53")
    clave = ("virus-semana", anio, semana)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada
    try:
        with _conexion() as conn:
            filas = semana_virus(conn, anio=anio, semana=semana)
    except Exception as exc:
        return _degradar_consulta(
            exc, response, MOTIVO_VIRUS_AUSENTE, AVISO_HONESTIDAD_VIRUS
        )

    return _cachear(clave, CACHE_TTL_HISTORICO, {
        "disponible": True,
        "anio": anio,
        "semana": semana,
        "observaciones": filas,
        "aviso": AVISO_HONESTIDAD_VIRUS,
        "granularidad": "nacional",
    })


@app.get("/api/v1/vigilancia/integridad")
@limiter.limit(_limite_pesado)
def vigilancia_integridad(
    request: Request,
    response: Response,
    week: int | None = None,
    year: int | None = None,
):
    """Integridad de la vigilancia (Módulo 4): completitud geográfica,
    cuadre aritmético del boletín y antigüedad por serie. Capa DESCRIPTIVA
    de la calidad del dato -- ver AVISO_HONESTIDAD_VIGILANCIA.

    `week` y `year` van juntos (vista por semana para el mapa). Sin
    parámetros: resumen anual de completitud + antigüedad por serie.
    Nada se persiste; se calcula on-request desde tablas existentes.
    """
    if (week is None) != (year is None):
        raise HTTPException(
            status_code=422,
            detail="Los parámetros 'week' y 'year' deben enviarse juntos.",
        )
    if week is not None and not (1 <= week <= 53):
        raise HTTPException(
            status_code=422,
            detail="El parámetro 'week' debe estar entre 1 y 53.",
        )

    # `antiguedad` depende de date.today(): el cache de 15 minutos puede
    # desfasarla en el borde de una SE, lo mismo que ADR 0019 ya acepta para
    # el Cache-Control de este endpoint.
    clave = ("vigilancia-integridad", week, year)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada
    try:
        with _conexion() as conn:
            cuerpo = construir_integridad(conn, week=week, year=year)
    except Exception:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")

    return _cachear(clave, CACHE_TTL_COMPUTO, cuerpo)


@app.get("/api/respiratorios/cobertura")
def respiratorios_cobertura(response: Response):
    """Semanas con dato en Postgres + notas de la exploración. Distinto de M4."""
    clave = ("respiratorios-cobertura",)
    if (cacheada := _desde_cache(clave)) is not None:
        return cacheada
    try:
        with _conexion() as conn:
            cobertura = cargar_cobertura(conn)
    except Exception as exc:
        return _degradar_consulta(
            exc, response, MOTIVO_COBERTURA_AUSENTE, AVISO_COBERTURA
        )

    cobertura["disponible"] = True
    return _cachear(clave, CACHE_TTL_HISTORICO, cobertura)


# ---------------------------------------------------------------------------
# Alertas de campo (ADR 0013, ADR 0015). Decisiones humanas persistidas:
# no se calculan desde M1–M3 ni desde el clasificador retirado.
# GET público por defecto: activa=TRUE y etiqueta IS NULL. POST/PATCH
# exigen Bearer contra ALERTAS_TOKEN. Sin DELETE.
# ---------------------------------------------------------------------------


def _autorizar_escritura_alertas(authorization: str | None) -> None:
    error = comprobar_token_escritura(authorization)
    if error is not None:
        codigo, detalle = error
        raise HTTPException(status_code=codigo, detail=detalle)


def _alertas_http_error(exc: BaseException) -> None:
    status = 503 if _es_fallo_conexion(exc) else 500
    raise HTTPException(
        status_code=status,
        detail="Error de conexión a la base de datos",
    )


@app.get("/api/alertas")
def alertas_publicas(
    response: Response,
    tipo: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    incluir_inactivas: bool = False,
    incluir_etiquetadas: bool = False,
    departamento: str | None = None,
):
    """Lista alertas. Sin parámetros extra: activa=TRUE y etiqueta IS NULL.

    Filtros opcionales combinados con AND: tipo, desde/hasta (solapamiento
    de vigencia), incluir_inactivas, incluir_etiquetadas, departamento
    (nacionales más las que lo incluyen, ADR 0022).
    """
    if departamento is not None and departamento not in DEPARTAMENTOS_ALERTA:
        raise HTTPException(
            status_code=422,
            detail="El parámetro 'departamento' debe ser un código ISO 3166-2 de El Salvador (SV-AH..SV-US).",
        )
    if tipo is not None and tipo not in TIPOS_ALERTA:
        raise HTTPException(
            status_code=422,
            detail="El parámetro 'tipo' debe ser 'dengue' o 'respiratorio'.",
        )
    try:
        with _conexion() as conn:
            cuerpo = consultar_alertas_publicas(
                conn,
                tipo=tipo,
                desde=desde,
                hasta=hasta,
                incluir_inactivas=incluir_inactivas,
                incluir_etiquetadas=incluir_etiquetadas,
                departamento=departamento,
            )
    except Exception as exc:
        # Contrato propio ({aviso, ultima_revision, alertas}); no se degrada
        # a {disponible:false} como los endpoints respiratorios. Solo se
        # distingue fallo de conexión (503) del resto (500).
        _alertas_http_error(exc)

    _cache_control(response, CACHE_TTL_ALERTAS)
    return cuerpo


@app.get("/api/alertas/feed.xml")
def alertas_feed(request: Request):
    """Feed Atom con las alertas activas sin etiqueta (mismo criterio que el GET público)."""
    try:
        with _conexion() as conn:
            cuerpo = consultar_alertas_publicas(conn)
    except Exception as exc:
        _alertas_http_error(exc)

    sitio = os.environ.get("SITIO_PUBLICO", "https://epi-aetheris.dev")
    xml = construir_feed_atom(
        cuerpo["alertas"],
        cuerpo["ultima_revision"],
        sitio=sitio,
        api_url=str(request.url),
    )
    return Response(
        content=xml,
        media_type="application/atom+xml",
        headers={"Cache-Control": f"public, max-age={CACHE_TTL_ALERTAS}"},
    )


@app.post("/api/alertas", status_code=201)
@limiter.limit(RATE_LIMIT_WRITE)
def alertas_crear(
    request: Request,
    cuerpo: AlertaCrear,
    response: Response,
    authorization: str | None = Header(default=None),
):
    """Crea una alerta redactada por el equipo. Exige Bearer ALERTAS_TOKEN."""
    _autorizar_escritura_alertas(authorization)
    response.headers["Cache-Control"] = "no-store"
    try:
        with _conexion() as conn:
            creada = crear_alerta(conn, cuerpo)
            conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        _alertas_http_error(exc)
    return creada


@app.patch("/api/alertas/{alerta_id}")
@limiter.limit(RATE_LIMIT_WRITE)
def alertas_parchear(
    alerta_id: int,
    request: Request,
    cuerpo: AlertaParche,
    response: Response,
    authorization: str | None = Header(default=None),
):
    """Edita una alerta. Como mínimo puede poner activa=false. Sin DELETE."""
    _autorizar_escritura_alertas(authorization)
    response.headers["Cache-Control"] = "no-store"
    if not cuerpo.model_dump(exclude_unset=True):
        raise HTTPException(
            status_code=422,
            detail="El cuerpo debe incluir al menos un campo a modificar.",
        )
    try:
        with _conexion() as conn:
            actualizada = parchear_alerta(conn, alerta_id, cuerpo)
            if actualizada is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No existe una alerta con id {alerta_id}.",
                )
            conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        _alertas_http_error(exc)
    return actualizada


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
