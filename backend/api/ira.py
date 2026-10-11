"""
Endpoints descriptivos para Infección Respiratoria Aguda (IRA), ADR 0011
(aceptado 2026-08-22, clasificacion='notificado').

Deliberadamente NO es uno de los modulos descriptivos de dengue (M1-M4): IRA es otro
tipo_evento, sin Iv/anomalia/presion calculados -- eso son formulas
cerradas para dengue especificamente y no hay decision del coordinador para extenderlas a IRA. Esto es solo la
serie observada, igual de descriptiva que /api/casos-departamentales.

Fuente: backend/ingestion/cargar_ira.py cargo 2742 filas "seguras" (sin
`nota`, span de 1 semana, sin correcciones negativas) el 2026-08-22. Los
huecos reales (boletines de vacaciones, tablas como imagen, correcciones
retroactivas excluidas) NO
estan en la tabla: una semana sin fila es un hueco real de la fuente, no
un cero. Nada se persiste aqui; todo se lee on-request de
casos_epidemiologicos, mismo patron que idoneidad.py y presion.py.
"""

from __future__ import annotations

from collections import defaultdict

ANIOS_IRA = [2018, 2019, 2021, 2022, 2023]  # 2020 ausente del corpus, ver AGENTS.md

AVISO_HONESTIDAD_IRA = (
    "Infección Respiratoria Aguda (IRA), boletines MINSAL 2018-2023 (sin 2020). "
    "Conteo semanal notificado por departamento, sin desagregación probable/confirmado. "
    "Los huecos (semanas sin fila) son ausencias reales de la fuente, nunca ceros interpolados."
)


def cargar_ira_departamental(conn) -> list[dict]:
    """Resumen por departamento: total notificado, semanas con dato, rango
    de años. Mismo patrón que /api/casos-departamentales (main.py) pero
    filtrando clasificacion='notificado' en vez de probable/confirmado."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                r.nombre,
                r.codigo,
                sum(c.conteo) AS notificado_total,
                count(*) AS semanas_con_dato,
                min(c.anio) AS primer_anio,
                max(c.anio) AS ultimo_anio
            FROM regiones r
            LEFT JOIN casos_epidemiologicos c
                ON c.region_id = r.id
                AND c.clasificacion = 'notificado'
                AND c.tipo_evento_id = (SELECT id FROM tipos_evento WHERE codigo = 'ira')
            WHERE r.nivel_admin = 1
            GROUP BY r.nombre, r.codigo
            ORDER BY r.nombre
            """
        )
        filas = cur.fetchall()

    return [
        {
            "nombre": nombre,
            "codigo": codigo,
            "notificado_total": int(notificado_total) if notificado_total is not None else 0,
            "semanas_con_dato": int(semanas_con_dato) if semanas_con_dato is not None else 0,
            "primer_anio": primer_anio,
            "ultimo_anio": ultimo_anio,
        }
        for nombre, codigo, notificado_total, semanas_con_dato, primer_anio, ultimo_anio in filas
    ]


def cargar_ira_departamento_temporal(
    conn, codigo: str
) -> tuple[str, dict[int, dict[int, float]]] | None:
    """(nombre del departamento, anio -> semana -> conteo). None si el
    código no existe en `regiones`. Dict vacío (no None) si el departamento
    existe pero no tiene ninguna fila IRA. El nombre sale de la misma
    consulta que resuelve el código, así el endpoint no vuelve a pedirlo."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, nombre FROM regiones WHERE nivel_admin = 1 AND codigo = %s",
            (codigo,),
        )
        fila_region = cur.fetchone()
        if fila_region is None:
            return None
        region_id, nombre = fila_region

        cur.execute(
            """
            SELECT anio, semana_epi, conteo
            FROM casos_epidemiologicos
            WHERE region_id = %s AND clasificacion = 'notificado'
              AND tipo_evento_id = (SELECT id FROM tipos_evento WHERE codigo = 'ira')
            ORDER BY anio, semana_epi
            """,
            (region_id,),
        )
        filas = cur.fetchall()

    serie: dict[int, dict[int, float]] = defaultdict(dict)
    for anio, semana, conteo in filas:
        serie[anio][semana] = float(conteo)
    return nombre, dict(serie)
