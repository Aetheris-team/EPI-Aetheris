"""Rutas de los eventos respiratorios: IRA (ADR 0011), neumonías, vigilancia
de virus respiratorios (ADR 0012), la serie nacional del tablero de MINSAL
(ADR 0021) y la cobertura del observatorio.

No son módulos descriptivos de dengue (M1-M4): cada evento es otro
tipo_evento con su propia serie 'notificado', sin Iv, anomalía ni presión.
"""

from contextlib import AbstractContextManager
from typing import Callable

from fastapi import APIRouter, HTTPException, Request, Response

from ..cobertura import AVISO_COBERTURA, cargar_cobertura
from ..ira import (
    AVISO_HONESTIDAD_IRA,
    cargar_ira_departamental,
    cargar_ira_departamento_temporal,
)
from ..neumonias import (
    ANIOS_NEUMONIAS,
    AVISO_HONESTIDAD_NEUMONIAS,
    cargar_heatmap_neumonias,
    cargar_neumonias_departamental,
    cargar_neumonias_departamento_temporal,
)
from ..respiratorios import (
    AVISO_HONESTIDAD_VIRUS,
    listar_virus,
    semana_virus,
    serie_virus,
)
from ..respuestas import (
    CACHE_TTL_HISTORICO,
    cachear,
    degradar_consulta,
    desde_cache,
    fallo_base_datos,
    respuesta_no_disponible,
)
from ..tablero import (
    AVISO_TABLERO_RESPIRATORIO,
    EVENTOS_TABLERO,
    MOTIVO_TABLERO_AUSENTE,
    cargar_serie_tablero_nacional,
)

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


def crear_router(
    *,
    limiter,
    abrir_conexion: Callable[[], AbstractContextManager],
    limite_pesado: str,
) -> APIRouter:
    """`limite_pesado` es RATE_LIMIT_HEAVY de main.py."""
    router = APIRouter()

    # IRA -- ADR 0011 (aceptado 2026-08-22). Cargado por
    # backend/ingestion/cargar_ira.py (2742 filas, 2018-2023 sin 2020, 14
    # departamentos).
    @router.get("/api/ira/departamental")
    @limiter.limit(limite_pesado)
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
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada
        try:
            with abrir_conexion() as conn:
                departamentos = cargar_ira_departamental(conn)
        except Exception as exc:
            fallo_base_datos(exc)

        return cachear(clave, CACHE_TTL_HISTORICO, {
            "departamentos": departamentos,
            "aviso": AVISO_HONESTIDAD_IRA,
        })

    @router.get("/api/ira/temporal/{departamento_id}")
    def ira_temporal_departamento(departamento_id: str, response: Response):
        """Serie semanal de IRA notificada de un departamento, por año
        (2018-2023, sin 2020). `departamento_id` es el `codigo` de `regiones`
        (ISO 3166-2:SV, ej. 'SV-SS'). Las semanas sin fila son huecos reales de
        la fuente MINSAL (boletín de vacaciones, tabla como imagen, corrección
        retroactiva excluida) -- se devuelven como ausentes, nunca como cero ni
        valor interpolado."""
        clave = ("ira-temporal", departamento_id)
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada
        try:
            with abrir_conexion() as conn:
                resultado = cargar_ira_departamento_temporal(conn, codigo=departamento_id)
        except Exception as exc:
            fallo_base_datos(exc)
        if resultado is None:
            raise HTTPException(
                status_code=404,
                detail=f"No existe un departamento con código '{departamento_id}'.",
            )
        nombre, serie = resultado

        anios = sorted(serie.keys())
        return cachear(clave, CACHE_TTL_HISTORICO, {
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
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada
        try:
            with abrir_conexion() as conn:
                semanas = cargar_serie_tablero_nacional(conn, EVENTOS_TABLERO[evento])
        except Exception as exc:
            return degradar_consulta(
                exc, response, MOTIVO_TABLERO_AUSENTE, AVISO_TABLERO_RESPIRATORIO
            )

        if not semanas:
            return respuesta_no_disponible(
                response, MOTIVO_TABLERO_AUSENTE, AVISO_TABLERO_RESPIRATORIO
            )

        return cachear(clave, CACHE_TTL_HISTORICO, {
            "disponible": True,
            "evento": evento,
            "fuente": "minsal_tablero",
            "unidad": "conteo_notificado",
            "semanas": semanas,
            "aviso": AVISO_TABLERO_RESPIRATORIO,
        })

    @router.get("/api/ira/nacional")
    def ira_nacional(response: Response):
        """Serie semanal nacional de IRA notificada, del tablero de MINSAL desde
        2025. La semana 53 de 2025, que el tablero no publica, no tiene fila."""
        return _serie_respiratoria_nacional("ira", response)

    @router.get("/api/neumonias/nacional")
    def neumonias_nacional(response: Response):
        """Serie semanal nacional de neumonías notificadas, del tablero de MINSAL
        desde 2025. Mismo contrato que /api/ira/nacional."""
        return _serie_respiratoria_nacional("neumonias", response)

    @router.get("/api/neumonias/departamental")
    def neumonias_departamental(response: Response):
        """Resumen departamental de Neumonías notificadas. Capa descriptiva."""
        clave = ("neumonias-departamental",)
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada
        try:
            with abrir_conexion() as conn:
                departamentos = cargar_neumonias_departamental(conn)
        except Exception as exc:
            return degradar_consulta(
                exc, response, MOTIVO_NEUMONIAS_AUSENTE, AVISO_HONESTIDAD_NEUMONIAS
            )

        return cachear(clave, CACHE_TTL_HISTORICO, {
            "disponible": True,
            "departamentos": departamentos,
            "aviso": AVISO_HONESTIDAD_NEUMONIAS,
        })

    @router.get("/api/neumonias/temporal/{departamento_id}")
    def neumonias_temporal_departamento(departamento_id: str, response: Response):
        clave = ("neumonias-temporal", departamento_id)
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada
        try:
            with abrir_conexion() as conn:
                resultado = cargar_neumonias_departamento_temporal(conn, codigo=departamento_id)
        except Exception as exc:
            return degradar_consulta(
                exc, response, MOTIVO_NEUMONIAS_AUSENTE, AVISO_HONESTIDAD_NEUMONIAS
            )
        if resultado is None:
            raise HTTPException(
                status_code=404,
                detail=f"No existe un departamento con código '{departamento_id}'.",
            )
        nombre, serie = resultado

        return cachear(clave, CACHE_TTL_HISTORICO, {
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

    @router.get("/api/neumonias/heatmap/{anio}")
    def neumonias_heatmap(anio: int, response: Response):
        """Matriz departamento × semana. Celdas ausentes son huecos, no ceros."""
        if anio not in ANIOS_NEUMONIAS:
            raise HTTPException(
                status_code=400,
                detail=f"año {anio} fuera de la ventana cargada {ANIOS_NEUMONIAS}",
            )
        clave = ("neumonias-heatmap", anio)
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada
        try:
            with abrir_conexion() as conn:
                departamentos = cargar_heatmap_neumonias(conn, anio)
        except Exception as exc:
            return degradar_consulta(
                exc, response, MOTIVO_NEUMONIAS_AUSENTE, AVISO_HONESTIDAD_NEUMONIAS
            )

        return cachear(clave, CACHE_TTL_HISTORICO, {
            "disponible": True,
            "anio": anio,
            "unidad": "conteo_notificado",
            "departamentos": departamentos,
            "aviso": AVISO_HONESTIDAD_NEUMONIAS,
        })

    @router.get("/api/respiratorios/virus")
    def respiratorios_virus(response: Response):
        """Catálogo de series disponibles (virus × métrica × unidad). Nacional."""
        clave = ("virus-catalogo",)
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada
        try:
            with abrir_conexion() as conn:
                series = listar_virus(conn)
        except Exception as exc:
            return degradar_consulta(
                exc, response, MOTIVO_VIRUS_AUSENTE, AVISO_HONESTIDAD_VIRUS
            )

        if not series:
            return respuesta_no_disponible(
                response, MOTIVO_VIRUS_AUSENTE, AVISO_HONESTIDAD_VIRUS
            )

        return cachear(clave, CACHE_TTL_HISTORICO, {
            "disponible": True,
            "series": series,
            "aviso": AVISO_HONESTIDAD_VIRUS,
            "granularidad": "nacional",
        })

    @router.get("/api/respiratorios/temporal")
    def respiratorios_temporal(response: Response, virus: str, metrica: str = "detecciones"):
        """Serie nacional semanal de un virus y una métrica (detecciones|positividad|muestras_analizadas|muestras_positivas)."""
        permitidas = {"detecciones", "positividad", "muestras_analizadas", "muestras_positivas"}
        if metrica not in permitidas:
            raise HTTPException(status_code=400, detail=f"metrica debe ser una de {sorted(permitidas)}")
        clave = ("virus-temporal", virus, metrica)
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada
        try:
            with abrir_conexion() as conn:
                serie, unidad = serie_virus(conn, virus=virus, metrica=metrica)
        except Exception as exc:
            return degradar_consulta(
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

        return cachear(clave, CACHE_TTL_HISTORICO, {
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

    @router.get("/api/respiratorios/semana/{anio}/{semana}")
    def respiratorios_semana(anio: int, semana: int, response: Response):
        if semana < 1 or semana > 53:
            raise HTTPException(status_code=400, detail="semana epidemiológica fuera de 1-53")
        clave = ("virus-semana", anio, semana)
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada
        try:
            with abrir_conexion() as conn:
                filas = semana_virus(conn, anio=anio, semana=semana)
        except Exception as exc:
            return degradar_consulta(
                exc, response, MOTIVO_VIRUS_AUSENTE, AVISO_HONESTIDAD_VIRUS
            )

        return cachear(clave, CACHE_TTL_HISTORICO, {
            "disponible": True,
            "anio": anio,
            "semana": semana,
            "observaciones": filas,
            "aviso": AVISO_HONESTIDAD_VIRUS,
            "granularidad": "nacional",
        })

    @router.get("/api/respiratorios/cobertura")
    def respiratorios_cobertura(response: Response):
        """Semanas con dato en Postgres + notas de la exploración. Distinto de M4."""
        clave = ("respiratorios-cobertura",)
        if (cacheada := desde_cache(clave)) is not None:
            return cacheada
        try:
            with abrir_conexion() as conn:
                cobertura = cargar_cobertura(conn)
        except Exception as exc:
            return degradar_consulta(
                exc, response, MOTIVO_COBERTURA_AUSENTE, AVISO_COBERTURA
            )

        cobertura["disponible"] = True
        return cachear(clave, CACHE_TTL_HISTORICO, cobertura)

    return router
