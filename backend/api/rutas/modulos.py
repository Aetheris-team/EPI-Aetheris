"""Rutas de los módulos descriptivos de dengue y del dataset analítico.

- M1, idoneidad biofísica (Iv), y M2, anomalía climática continua
  (backend/api/idoneidad.py; ADR 0018 para la ventana climática).
- M3, presión epidemiológica relativa (backend/api/presion.py; fórmula
  cerrada por la coordinación el 2026-08-21).
- M4, integridad de la vigilancia (backend/api/vigilancia.py; ADR 0019).
- El dataset analítico de dengue y su procedencia (backend/api/analisis.py).

Todo se calcula en cada petición desde tablas existentes; nada se persiste.
Ninguno expone alerta binaria ni lenguaje de anticipación.
"""

from contextlib import AbstractContextManager
from typing import Callable

from fastapi import APIRouter, HTTPException, Request, Response

from ..analisis import (
    ANIOS_ANALISIS_DENGUE,
    cargar_procedencia_observacion,
    construir_dataset_dengue,
)
from ..idoneidad import (
    ANIOS_CLIMA,
    calcular_baseline_semana,
    calcular_serie_iv,
    calcular_sigma,
    cargar_clima_departamento,
    cargar_clima_departamentos,
    percentil,
)
from ..presion import (
    ANIOS_BASE as ANIOS_BASE_PRESION,
    SERIES as SERIES_PRESION,
    calcular_presion,
    cargar_casos_departamentales,
    cargar_casos_departamento,
)
from ..respuestas import (
    CACHE_TTL_COMPUTO,
    CACHE_TTL_HISTORICO,
    cache_control,
    cachear,
    desde_cache,
    fallo_base_datos,
)
from ..vigilancia import construir_integridad


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


def crear_router(
    *,
    limiter,
    abrir_conexion: Callable[[], AbstractContextManager],
    limite_pesado: str,
) -> APIRouter:
    """`limite_pesado` es RATE_LIMIT_HEAVY de main.py."""
    router = APIRouter()

    @router.get("/api/v1/spatial/current")
    @limiter.limit(limite_pesado)
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
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada

        semanas_necesarias = [week] if week == 1 else [week - 1, week]

        try:
            with abrir_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT codigo, nombre FROM regiones WHERE nivel_admin = 1 ORDER BY nombre")
                    departamentos = cursor.fetchall()
                clima = cargar_clima_departamentos(conn, anios=ANIOS_CLIMA, semanas=semanas_necesarias)
        except Exception as exc:
            fallo_base_datos(exc)

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

        return cachear(clave, CACHE_TTL_COMPUTO, {
            "semana_epi": week,
            "anio": year,
            "departamentos": resultado,
            "aviso": AVISO_HONESTIDAD_IDONEIDAD,
        })


    @router.get("/api/v1/analisis/dengue")
    @limiter.limit(limite_pesado)
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
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada

        try:
            with abrir_conexion() as conn:
                respuesta = construir_dataset_dengue(conn, anio=year)
        except Exception as exc:
            fallo_base_datos(exc)

        respuesta["avisos"] = {
            "idoneidad": AVISO_HONESTIDAD_IDONEIDAD,
            "presion": AVISO_HONESTIDAD_PRESION,
        }
        return cachear(clave, CACHE_TTL_HISTORICO, respuesta)


    @router.get("/api/v1/analisis/dengue/procedencia")
    @limiter.limit(limite_pesado)
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
            with abrir_conexion() as conn:
                respuesta = cargar_procedencia_observacion(
                    conn,
                    anio=year,
                    semana=week,
                    departamento_codigo=dept,
                    serie=serie,
                )
        except Exception as exc:
            fallo_base_datos(exc)

        if respuesta is None:
            raise HTTPException(
                status_code=404,
                detail=f"No existe un departamento con código '{dept}'.",
            )
        cache_control(response, CACHE_TTL_HISTORICO)
        return respuesta


    @router.get("/api/v1/presion/current")
    @limiter.limit(limite_pesado)
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
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada

        # Solo la ventana ±1 de la semana pedida; el baseline necesita los años
        # base completos más el año descrito (si no es uno de ellos).
        semanas_necesarias = [w for w in (week - 1, week, week + 1) if w >= 1]
        anios_necesarios = sorted(set(ANIOS_BASE_PRESION) | {year})

        try:
            with abrir_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT codigo, nombre FROM regiones WHERE nivel_admin = 1 ORDER BY nombre")
                    departamentos = cursor.fetchall()
                casos = cargar_casos_departamentales(conn, anios=anios_necesarios, semanas=semanas_necesarias)
        except Exception as exc:
            fallo_base_datos(exc)

        resultado = []
        for codigo, nombre in departamentos:
            fila = {"codigo": codigo, "nombre": nombre}
            for serie in SERIES_PRESION:
                fila[serie] = calcular_presion(casos.get(codigo, {}).get(serie, {}), anio=year, semana=week)
            resultado.append(fila)

        return cachear(clave, CACHE_TTL_COMPUTO, {
            "semana_epi": week,
            "anio": year,
            "departamentos": resultado,
            "aviso": AVISO_HONESTIDAD_PRESION,
        })


    @router.get("/api/v1/presion/temporal/{departamento_id}")
    def presion_temporal_departamento(departamento_id: str, anio: int, response: Response):
        """Serie temporal de presión epidemiológica relativa (Módulo 3) de un
        departamento para `anio`, en las dos series separadas. Espejo de
        /api/v1/temporal/{departamento_id}. `departamento_id` es el `codigo`
        de `regiones` (ISO 3166-2:SV, ej. 'SV-SS')."""
        clave = ("presion-temporal", departamento_id, anio)
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada

        anios_necesarios = sorted(set(ANIOS_BASE_PRESION) | {anio})

        try:
            with abrir_conexion() as conn:
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
            fallo_base_datos(exc)

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

        return cachear(clave, CACHE_TTL_HISTORICO, {
            "departamento_codigo": codigo,
            "departamento_nombre": nombre,
            "anio": anio,
            "semanas": semanas_salida,
            "aviso": AVISO_HONESTIDAD_PRESION,
        })


    @router.get("/api/v1/temporal/{departamento_id}")
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
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada

        try:
            with abrir_conexion() as conn:
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
            fallo_base_datos(exc)

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

        return cachear(clave, CACHE_TTL_HISTORICO, {
            "departamento_codigo": codigo,
            "departamento_nombre": nombre,
            "anio": anio,
            "semanas": semanas_salida,
            "aviso": AVISO_HONESTIDAD_IDONEIDAD,
        })


    @router.get("/api/v1/vigilancia/integridad")
    @limiter.limit(limite_pesado)
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
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada
        try:
            with abrir_conexion() as conn:
                cuerpo = construir_integridad(conn, week=week, year=year)
        except Exception as exc:
            fallo_base_datos(exc)

        return cachear(clave, CACHE_TTL_COMPUTO, cuerpo)

    return router
