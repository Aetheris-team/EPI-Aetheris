"""
Lectura de cobertura de la ingesta respiratoria.

No es M4 (integridad de vigilancia, `backend/api/vigilancia.py`). Solo cuenta
semanas con fila en Postgres y adjunta las notas ya documentadas en la
exploración de 264 PDF. Hueco ≠ cero.
"""

from __future__ import annotations

ANIOS = [2018, 2019, 2021, 2022, 2023]
SEMANAS_NOMINALES = 52

# Hechos de la corrida exploratoria sobre el corpus congelado 2018-2019 y
# 2021-2023, no umbrales nuevos.
# Si se incorporan 2020 o 2024+, regenerar estas constantes desde esa
# exploración; no reutilizar los recuentos de tablas-imagen / vacaciones.
NOTAS_NEUMONIAS = {
    "tablas_imagen": 25,
    "ausencia_vacacion": 18,
    "sin_texto_extraible": 4,
    "reimpresiones": ["SE34/2019_v2 = SE33/2019 (14 valores idénticos)"],
    "correcciones_negativas_excluidas": 23,
    "cortes_usables_exploracion": {"2018": 46, "2019": 22, "2021": 50, "2022": 48, "2023": 49},
    "nota_corpus": (
        "Constantes del corpus histórico congelado 2018-2019 y 2021-2023. "
        "Si se incorporan 2020 o 2024+, regenerarlas desde la nueva exploración."
    ),
}
NOTAS_VIRUS = {
    "tablas_imagen": 3,
    "sin_texto_extraible": 5,
    "covid_19_solo_en": 2023,
    "anio_2020_descargado": False,
    "granularidad": "nacional",
    "unidad": "muestras / detecciones / positividad (no casos clínicos)",
    "nota_corpus": (
        "Constantes del corpus histórico congelado 2018-2019 y 2021-2023. "
        "Si se incorporan 2020 o 2024+, regenerarlas desde la nueva exploración."
    ),
}
NOTAS_IRA = {
    "nota": "Misma ventana 2018-2023 sin 2020; tablas-imagen en 2019 temprana.",
}

AVISO_COBERTURA = (
    "Semanas con dato en la base frente a 52 nominales, más lo documentado "
    "por la exploración de 264 PDF. Semanas sin fila son huecos, nunca ceros."
)


def _conteos_notificado(conn) -> dict[str, dict[str, tuple[int, int]]]:
    """tipo_evento -> anio -> (semanas distintas con dato, filas), para IRA y
    neumonías de los boletines. Una consulta para los dos eventos en vez de
    dos por evento: las filas totales son la suma de las filas por año."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.codigo, c.anio, count(DISTINCT c.semana_epi), count(*)
            FROM casos_epidemiologicos c
            JOIN tipos_evento t ON t.id = c.tipo_evento_id
            WHERE c.clasificacion = 'notificado'
              AND t.codigo IN ('ira', 'neumonia')
              AND c.fuente_id = (SELECT id FROM fuentes_datos WHERE codigo = 'minsal_pdf')
            GROUP BY t.codigo, c.anio
            """
        )
        filas = cur.fetchall()
    out: dict[str, dict[str, tuple[int, int]]] = {"ira": {}, "neumonia": {}}
    for tipo, anio, semanas, n in filas:
        out[tipo][str(anio)] = (int(semanas), int(n))
    return out


def _conteos_virus(conn) -> dict[str, tuple[int, int]]:
    """anio -> (semanas distintas con dato, filas) de la vigilancia de virus."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT anio, count(DISTINCT semana_epi), count(*)
            FROM vigilancia_virus_respiratorios
            GROUP BY anio
            """
        )
        return {str(anio): (int(semanas), int(n)) for anio, semanas, n in cur.fetchall()}


def _bloque(conteos: dict[str, tuple[int, int]], notas: dict) -> dict:
    return {
        "filas_cargadas": sum(n for _, n in conteos.values()),
        "semanas_con_dato_por_anio": {
            str(a): conteos.get(str(a), (0, 0))[0] for a in ANIOS
        },
        "notas": notas,
    }


def cargar_cobertura(conn) -> dict:
    notificado = _conteos_notificado(conn)
    return {
        "aviso": AVISO_COBERTURA,
        "procedencia": "MINSAL, boletines epidemiológicos PDF 2018-2019 y 2021-2023",
        "anios": ANIOS,
        "semanas_nominales_por_anio": SEMANAS_NOMINALES,
        "ira": _bloque(notificado["ira"], NOTAS_IRA),
        "neumonias": _bloque(notificado["neumonia"], NOTAS_NEUMONIAS),
        "virus": _bloque(_conteos_virus(conn), NOTAS_VIRUS),
    }
