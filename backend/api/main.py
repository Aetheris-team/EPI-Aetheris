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
from psycopg2 import OperationalError
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
from .conexion_db import parametros_conexion
from .respuestas import (
    CACHE_TTL_COMPUTO,
    CACHE_TTL_HISTORICO,
    cache_control as _cache_control,
    cachear as _cachear,
    desde_cache as _desde_cache,
    fallo_base_datos as _fallo_base_datos,
)
from .vigilancia import construir_integridad
from .rutas import alertas as _rutas_alertas
from .rutas import dengue as _rutas_dengue
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


app.include_router(
    _rutas_dengue.crear_router(
        limiter=limiter,
        abrir_conexion=_abrir_conexion,
        limite_pesado=RATE_LIMIT_HEAVY,
    )
)


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
@limiter.limit(RATE_LIMIT_HEAVY)
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
    except Exception as exc:
        _fallo_base_datos(exc)

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
@limiter.limit(RATE_LIMIT_HEAVY)
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
    except Exception as exc:
        _fallo_base_datos(exc)

    respuesta["avisos"] = {
        "idoneidad": AVISO_HONESTIDAD_IDONEIDAD,
        "presion": AVISO_HONESTIDAD_PRESION,
    }
    return _cachear(clave, CACHE_TTL_HISTORICO, respuesta)


@app.get("/api/v1/analisis/dengue/procedencia")
@limiter.limit(RATE_LIMIT_HEAVY)
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
    except Exception as exc:
        _fallo_base_datos(exc)

    if respuesta is None:
        raise HTTPException(
            status_code=404,
            detail=f"No existe un departamento con código '{dept}'.",
        )
    _cache_control(response, CACHE_TTL_HISTORICO)
    return respuesta


@app.get("/api/v1/presion/current")
@limiter.limit(RATE_LIMIT_HEAVY)
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
    except Exception as exc:
        _fallo_base_datos(exc)

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
    except Exception as exc:
        _fallo_base_datos(exc)

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
    except Exception as exc:
        _fallo_base_datos(exc)

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


@app.get("/api/v1/vigilancia/integridad")
@limiter.limit(RATE_LIMIT_HEAVY)
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
    except Exception as exc:
        _fallo_base_datos(exc)

    return _cachear(clave, CACHE_TTL_COMPUTO, cuerpo)


app.include_router(
    _rutas_respiratorio.crear_router(
        limiter=limiter,
        abrir_conexion=_abrir_conexion,
        limite_pesado=RATE_LIMIT_HEAVY,
    )
)
app.include_router(
    _rutas_alertas.crear_router(
        limiter=limiter,
        abrir_conexion=_abrir_conexion,
        limite_escritura=RATE_LIMIT_WRITE,
    )
)


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
