"""Rutas de dengue a nivel de serie: casos nacionales y departamentales
(MINSAL, OpenDengue, tablero), la predicción de casos a corto plazo
(ADR 0020, ADR 0021), clima y dengue descriptivo (ADR 0023) y el
clasificador retirado, servido desde sus salidas congeladas (ADR 0025).

Los módulos descriptivos M1-M4 y el dataset analítico están en
api/rutas/modulos.py.
"""

import json
import threading
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Request, Response

from ..respuestas import (
    CACHE_TTL_COMPUTO,
    CACHE_TTL_HISTORICO,
    cache_control,
    cachear,
    desde_cache,
    fallo_base_datos,
)

# Salidas congeladas del clasificador retirado (ADR 0025), generadas por
# backend/ingestion/congelar_clasificador.py a partir del modelo y el dataset
# versionados en ingestion/data/interim/. La API ya no carga el modelo: sin
# scikit-learn ni joblib en la imagen.
RIESGO_NACIONAL_PATH = Path(__file__).parent.parent / "datos" / "riesgo_nacional_congelado.json"

AVISO_HONESTIDAD_RIESGO_NACIONAL = (
    "Clasificación entrenada sobre la serie nacional agregada de El Salvador. "
    "El mapa departamental es una capa descriptiva aparte (volumen de casos MINSAL); "
    "estos datos no alimentan ningún clasificador."
)


_riesgo_nacional_lock = threading.Lock()



_riesgo_nacional_cache = None



def _cargar_riesgo_nacional():
    """Devuelve el artefacto congelado, o None si no existe en este
    despliegue. Carga perezosa con double-checked locking (issue #71): en
    cold start dos requests no lo parsean a la vez."""
    global _riesgo_nacional_cache
    if _riesgo_nacional_cache is None:
        with _riesgo_nacional_lock:
            if _riesgo_nacional_cache is None:
                if not RIESGO_NACIONAL_PATH.exists():
                    return None
                datos = json.loads(RIESGO_NACIONAL_PATH.read_text(encoding="utf-8"))
                datos["por_semana"] = {(f["anio"], f["semana_epi"]): f for f in datos["semanas"]}
                _riesgo_nacional_cache = datos
    return _riesgo_nacional_cache



NOWCAST_DENGUE_PATH = Path(__file__).parent.parent / "datos" / "nowcast_dengue.json"



def _servir_artefacto(ruta: Path, aviso: str) -> Response:
    """Cuerpo de los artefactos versionados de backend/api/datos/: el JSON
    tal cual con `disponible` y `aviso` delante. Leerlo, parsearlo y volver a
    serializarlo costaba decenas de ms por request en los de 200-300 KB; la
    clave lleva el mtime para que un artefacto regenerado no se sirva viejo.
    Quien llama ya comprobó que el archivo existe."""
    clave = ("artefacto", str(ruta), ruta.stat().st_mtime_ns)
    if (cacheada := desde_cache(clave)) is not None:
        return cacheada
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return cachear(clave, CACHE_TTL_HISTORICO, {"disponible": True, "aviso": aviso, **datos})



AVISO_HONESTIDAD_NOWCAST_DENGUE = (
    "Prediccion estadistica de horizonte corto sobre la serie nacional de "
    "dengue: OpenDengue hasta 2024 y sospechosos del tablero de MINSAL desde "
    "2025. Se extiende desde la ultima semana publicada. Desde 2025 combina el "
    "modelo validado con una tendencia amortiguada y esta en prueba con las "
    "semanas publicadas desde 2026-S38."
)



NOWCAST_DENGUE_RETRO_PATH = NOWCAST_DENGUE_PATH.with_name("nowcast_dengue_retrospectivo.json")



# Analisis descriptivo de clima y dengue (ADR 0023). Dos artefactos
# precomputados y versionados, servidos tal cual: no recalculan nada por
# request y no alimentan el pronostico de /api/nowcast-dengue.
CLIMA_DENGUE_POR_ANIO_PATH = Path(__file__).parent.parent / "datos" / "clima_dengue_por_anio.json"



CLIMA_DENGUE_MULTIPAIS_PATH = Path(__file__).parent.parent / "datos" / "clima_dengue_multipais.json"



AVISO_HONESTIDAD_CLIMA_DENGUE = (
    "Descripción de datos de 2014 a 2024: correlaciones entre anomalías y "
    "diferencias de desempeño del predictor por año, sin atribución de causa. "
    "No alimenta el pronóstico publicado."
)



def _servir_clima_dengue(response: Response, ruta: Path, motivo: str) -> dict | Response:
    """Contrato de los artefactos versionados: sin el archivo responde 200 con
    disponible=false (mismo patron que /api/nowcast-dengue)."""
    if not ruta.exists():
        cache_control(response, CACHE_TTL_COMPUTO)
        return {"disponible": False, "motivo": motivo, "aviso": AVISO_HONESTIDAD_CLIMA_DENGUE}
    return _servir_artefacto(ruta, AVISO_HONESTIDAD_CLIMA_DENGUE)



AVISO_HONESTIDAD_CASOS_DEPARTAMENTALES = (
    "Casos probables y confirmados desacumulados de boletines MINSAL "
    "(2018-2023, con huecos entre boletines). El color representa volumen "
    "acumulado en la ventana cargada."
)


def crear_router(
    *,
    limiter,
    abrir_conexion: Callable[[], AbstractContextManager],
    limite_pesado: str,
) -> APIRouter:
    """`limite_pesado` es RATE_LIMIT_HEAVY de main.py."""
    router = APIRouter()

    @router.get("/api/casos-nacional")
    def casos_nacional(response: Response):
        """Serie semanal nacional de dengue: el total de OpenDengue
        (opendengue_v1_3) y, en las semanas posteriores a su ultima fila, los
        casos sospechosos del tablero de MINSAL (minsal_tablero, ADR 0021). Es la
        misma definicion de caso; el tablero publica cada semana como un promedio
        de varias. Cada fila lleva su `fuente` para que la UI distinga los dos
        tramos. La semana 53 de 2025, que el tablero no publica, no tiene fila.
        No es clasificacion de riesgo -- para eso ver /api/riesgo-nacional."""
        clave = ("casos-nacional",)
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada
        try:
            with abrir_conexion() as conn:
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
        except Exception as exc:
            fallo_base_datos(exc)

        return cachear(clave, CACHE_TTL_HISTORICO, [
            {
                "semana_inicio": fecha_inicio.isoformat(),
                "anio": anio,
                "semana_epi": semana_epi,
                "conteo": conteo,
                "fuente": fuente,
            }
            for fecha_inicio, anio, semana_epi, conteo, fuente in filas
        ])


    @router.get("/api/riesgo-nacional")
    @limiter.limit(limite_pesado)
    def riesgo_nacional(
        request: Request,
        response: Response,
        anio: int | None = None,
        semana: int | None = None,
    ):
        """Clasificación de riesgo NACIONAL del clasificador retirado para una
        semana epidemiológica dada (tarjetas 23/24/25). Sirve las salidas
        congeladas por congelar_clasificador.py (ADR 0025); el contrato es el
        mismo que cuando el modelo corría en cada request.

        Sin parámetros, devuelve la última semana disponible del dataset (fin
        de 2023, año de prueba de la tarjeta 24) -- el sistema no tiene forma
        de verificar en vivo lo que predice, no hay fuente departamental
        automatizable después de 2023.
        """
        artefacto = _cargar_riesgo_nacional()
        if artefacto is None:
            # Sin el artefacto (un checkout o una imagen que no lo trae) no es un
            # error del servidor: se responde 200 con disponible=false y el
            # frontend muestra un aviso explicito.
            cache_control(response, CACHE_TTL_COMPUTO)
            return {
                "disponible": False,
                "motivo": (
                    "El clasificador nacional historico no esta disponible en este "
                    "despliegue (falta el artefacto congelado del modelo)."
                ),
                "aviso": AVISO_HONESTIDAD_RIESGO_NACIONAL,
            }

        if anio is None or semana is None:
            fila = max(artefacto["semanas"], key=lambda f: (f["anio"], f["semana_epi"]))
        else:
            fila = artefacto["por_semana"].get((anio, semana))
            if fila is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No hay datos de modelado para año={anio}, semana={semana}.",
                )

        cache_control(response, CACHE_TTL_COMPUTO)
        return {
            "disponible": True,
            **fila,
            "metricas_modelo": artefacto["metricas_modelo"],
            "aviso": AVISO_HONESTIDAD_RIESGO_NACIONAL,
        }


    @router.get("/api/nowcast-dengue")
    @limiter.limit(limite_pesado)
    def nowcast_dengue(request: Request, response: Response):
        """Artefacto de prediccion de horizonte corto de dengue, precomputado por
        backend/ingestion/nowcast_tablero_dengue.py sobre la base de
        nowcast_estimacion_dengue.py (ADR 0020 y
        docs/experimentos/experimento-nowcast-tendencia.md). Se sirve tal cual
        desde el JSON versionado; no recalcula nada por request. Si el archivo
        falta -- despliegue sin el artefacto -- responde 200 con disponible=false,
        mismo patron que /api/riesgo-nacional y /ira."""
        if not NOWCAST_DENGUE_PATH.exists():
            cache_control(response, CACHE_TTL_COMPUTO)
            return {
                "disponible": False,
                "motivo": "El artefacto de prediccion de horizonte corto no esta generado en este despliegue.",
                "aviso": AVISO_HONESTIDAD_NOWCAST_DENGUE,
            }
        return _servir_artefacto(NOWCAST_DENGUE_PATH, AVISO_HONESTIDAD_NOWCAST_DENGUE)


    @router.get("/api/nowcast-dengue/retrospectivo")
    @limiter.limit(limite_pesado)
    def nowcast_dengue_retrospectivo(request: Request, response: Response):
        """Abanico h=1..8 que el modelo habria dado desde cada semana de la serie,
        con los datos disponibles hasta esa semana, para contrastarlo con lo
        observado. Precomputado por
        backend/ingestion/nowcast_retrospectivo_dengue.py (hasta 2024) y
        nowcast_tablero_dengue.py (desde 2025); va en un endpoint aparte porque
        pesa ~10 veces mas que /api/nowcast-dengue y solo lo pide la vista
        completa del panel."""
        if not NOWCAST_DENGUE_RETRO_PATH.exists():
            cache_control(response, CACHE_TTL_COMPUTO)
            return {
                "disponible": False,
                "motivo": "El artefacto retrospectivo de la prediccion no esta generado en este despliegue.",
                "aviso": AVISO_HONESTIDAD_NOWCAST_DENGUE,
            }
        return _servir_artefacto(NOWCAST_DENGUE_RETRO_PATH, AVISO_HONESTIDAD_NOWCAST_DENGUE)


    @router.get("/api/clima-dengue/por-anio")
    @limiter.limit(limite_pesado)
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


    @router.get("/api/clima-dengue/multipais")
    @limiter.limit(limite_pesado)
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


    @router.get("/api/casos-departamentales")
    @limiter.limit(limite_pesado)
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
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada
        try:
            with abrir_conexion() as conn:
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
        except Exception as exc:
            fallo_base_datos(exc)

        return cachear(clave, CACHE_TTL_HISTORICO, {
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

    return router
