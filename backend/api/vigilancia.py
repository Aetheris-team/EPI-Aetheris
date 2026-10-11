"""
Integridad y confianza de la vigilancia -- Modulo 4 (M4) de los modulos descriptivos.

Responde: "que tan completo, cuadrado y reciente es el dato de vigilancia
que estamos mostrando", no "que tan alta es la transmision". Es 100%
descriptivo de la calidad del dato. NO es un clasificador, NO predice,
NO se combina en un indice opaco.

Formula cerrada por el coordinador el 2026-09-08 (ADR 0019):

  - Tres metricas separadas, nunca fusionadas en un numero unico.
  - completitud: n/14 departamentos con fila en casos_epidemiologicos
    para (anio, semana_epi, clasificacion), nivel_admin=1. Solo dengue
    MINSAL (probable/confirmado). Un hueco es ausencia, no un cero.
  - cuadre: expone validacion_cuadra y la magnitud de la discrepancia
    ya almacenadas en boletines_procesados. M4 no recalcula la suma.
  - antiguedad: semanas epidemiologicas (PAHO/CDC, libreria epiweeks)
    entre "hoy" y la ultima SE con dato, por serie. No es latencia de
    reporte: boletines_procesados no guarda fecha de publicacion.

Nada se persiste: todo se calcula on-request desde tablas existentes,
mismo patron que M1/M2/M3. Sin cambios de esquema.
"""

from __future__ import annotations

from datetime import date

from epiweeks import Week

N_DEPARTAMENTOS = 14
SEMANAS_NOMINALES = 52
SERIES_COMPLETITUD = ("probable", "confirmado")

SERIES_ANTIGUEDAD = (
    "dengue_minsal_departamental",
    "dengue_opendengue_nacional",
    "dengue_tablero_nacional",
    "clima",
    "ira",
    "neumonias",
    "ira_tablero_nacional",
    "neumonias_tablero_nacional",
    "virus_respiratorios",
)

AVISO_HONESTIDAD_VIGILANCIA = (
    "Integridad de la vigilancia: tres hechos verificables sobre la calidad "
    "del dato (completitud geográfica de la tabla departamental, cuadre "
    "aritmético del boletín y antigüedad de cada serie). Describe qué tan "
    "completo y reciente es el dato disponible, NO la transmisión ni el "
    "riesgo. Las tres métricas se muestran por separado: no hay un índice "
    "compuesto. Un departamento sin fila esa semana es un hueco real, no "
    "un cero ni un departamento seguro."
)

CAMPOS_PROHIBIDOS = {
    "indice",
    "indice_compuesto",
    "score",
    "confianza",
    "riesgo",
    "alerta",
    "alert",
    "lead_time",
    "lead_time_weeks",
}


# --- Logica de calculo (funciones puras, sin acceso a datos) --------------


def completitud_semana(
    catalogo: list[tuple[str, str]],
    presentes: set[str],
) -> dict:
    """n/esperado departamentos con fila esa semana-serie.

    `catalogo` es la lista (codigo, nombre) de regiones nivel_admin=1.
    `presentes` son los codigos con al menos una fila en
    casos_epidemiologicos para el (anio, semana_epi, clasificacion)
    pedido. Un codigo ausente es un hueco, nunca un cero.
    """
    esperado = len(catalogo)
    n = sum(1 for codigo, _ in catalogo if codigo in presentes)
    return {
        "n": n,
        "esperado": esperado,
        "ratio": round(n / esperado, 4) if esperado else None,
        "departamentos": [
            {
                "codigo": codigo,
                "nombre": nombre,
                "presente": codigo in presentes,
            }
            for codigo, nombre in catalogo
        ],
    }


def completitud_anual(
    semanas_n: dict[int, int],
    semanas_nominales: int = SEMANAS_NOMINALES,
    esperado: int = N_DEPARTAMENTOS,
) -> dict:
    """Agregado anual: cuantas semanas tienen los `esperado` departamentos.

    `semanas_n` mapea semana_epi -> n departamentos con fila. Las semanas
    que no aparecen son huecos (no se convierten en n=0). El denominador
    nominal es 52, el mismo que usa el recuento de cobertura respiratoria;
    no se inventa una semana 53 vacia.
    """
    completas = sum(1 for n in semanas_n.values() if n == esperado)
    return {
        "semanas_completas": completas,
        "semanas_con_dato": len(semanas_n),
        "semanas_nominales": semanas_nominales,
    }


def discrepancia(suma: int | None, publicado: int | None) -> int | None:
    """Diferencia suma departamental menos total nacional publicado.

    None si falta alguno de los dos lados: no se fabrica un 0.
    """
    if suma is None or publicado is None:
        return None
    return int(suma) - int(publicado)


def cuadre_boletin(boletin: dict | None) -> dict:
    """Expone el cuadre ya almacenado. No recalcula la suma de 14.

    `boletin` es None cuando no hay fila en boletines_procesados para esa
    (anio, semana_archivo): el cuadre queda en null, no en false.
    """
    if boletin is None:
        return {
            "cuadra": None,
            "estado": None,
            "nombre_archivo": None,
            "probable": {
                "suma_departamental": None,
                "total_nacional_publicado": None,
                "discrepancia": None,
            },
            "confirmado": {
                "suma_departamental": None,
                "total_nacional_publicado": None,
                "discrepancia": None,
            },
        }

    suma_p = boletin.get("suma_departamental_probable")
    pub_p = boletin.get("total_nacional_publicado_probable")
    suma_c = boletin.get("suma_departamental_confirmado")
    pub_c = boletin.get("total_nacional_publicado_confirmado")
    return {
        "cuadra": boletin.get("validacion_cuadra"),
        "estado": boletin.get("estado"),
        "nombre_archivo": boletin.get("nombre_archivo"),
        "probable": {
            "suma_departamental": suma_p,
            "total_nacional_publicado": pub_p,
            "discrepancia": discrepancia(suma_p, pub_p),
        },
        "confirmado": {
            "suma_departamental": suma_c,
            "total_nacional_publicado": pub_c,
            "discrepancia": discrepancia(suma_c, pub_c),
        },
    }


def antiguedad_serie(
    ultima: tuple[int, int] | None,
    hoy: date,
) -> dict:
    """Semanas epidemiologicas (PAHO/CDC) entre la ultima SE con dato y hoy.

    Usa epiweeks.Week, no aritmetica ISO. Si la serie no tiene ninguna
    fila, semanas queda None -- no se convierte en 0.
    """
    if ultima is None:
        return {
            "ultima_anio": None,
            "ultima_semana_epi": None,
            "semanas": None,
        }
    anio, semana = ultima
    actual = Week.fromdate(hoy)
    ultima_w = Week(int(anio), int(semana))
    semanas = (actual.startdate() - ultima_w.startdate()).days // 7
    return {
        "ultima_anio": int(anio),
        "ultima_semana_epi": int(semana),
        "semanas": int(semanas),
    }


# --- Acceso a datos -------------------------------------------------------


def cargar_catalogo_departamentos(conn) -> list[tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT codigo, nombre
            FROM regiones
            WHERE nivel_admin = 1
            ORDER BY nombre
            """
        )
        return [(codigo, nombre) for codigo, nombre in cur.fetchall()]


def cargar_presentes_semana(
    conn, anio: int, semana: int
) -> dict[str, set[str]]:
    """clasificacion -> set de codigos departamentales con fila esa SE."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.clasificacion, r.codigo
            FROM casos_epidemiologicos c
            JOIN regiones r ON r.id = c.region_id
            JOIN tipos_evento t ON t.id = c.tipo_evento_id
            JOIN fuentes_datos f ON f.id = c.fuente_id
            WHERE r.nivel_admin = 1
              AND t.codigo = 'dengue'
              AND f.codigo = 'minsal_pdf'
              AND c.clasificacion IN ('probable', 'confirmado')
              AND c.anio = %s
              AND c.semana_epi = %s
            GROUP BY c.clasificacion, r.codigo
            """,
            (anio, semana),
        )
        filas = cur.fetchall()
    out: dict[str, set[str]] = {serie: set() for serie in SERIES_COMPLETITUD}
    for clasificacion, codigo in filas:
        out.setdefault(clasificacion, set()).add(codigo)
    return out


def cargar_conteos_anuales(conn) -> dict[tuple[int, str], dict[int, int]]:
    """(anio, clasificacion) -> {semana_epi: n departamentos}."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.anio, c.clasificacion, c.semana_epi,
                   count(DISTINCT r.codigo)
            FROM casos_epidemiologicos c
            JOIN regiones r ON r.id = c.region_id
            JOIN tipos_evento t ON t.id = c.tipo_evento_id
            JOIN fuentes_datos f ON f.id = c.fuente_id
            WHERE r.nivel_admin = 1
              AND t.codigo = 'dengue'
              AND f.codigo = 'minsal_pdf'
              AND c.clasificacion IN ('probable', 'confirmado')
            GROUP BY c.anio, c.clasificacion, c.semana_epi
            """
        )
        filas = cur.fetchall()
    out: dict[tuple[int, str], dict[int, int]] = {}
    for anio, clasificacion, semana, n in filas:
        out.setdefault((int(anio), clasificacion), {})[int(semana)] = int(n)
    return out


def cargar_boletin_semana(conn, anio: int, semana: int) -> dict | None:
    """Fila de boletines_procesados para (anio, semana_archivo).

    Si hay republicaciones, gana la de `version` mayor (mismo criterio
    de precedencia que el parser). None si no hay boletín esa semana.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT nombre_archivo, estado, validacion_cuadra,
                   suma_departamental_probable,
                   total_nacional_publicado_probable,
                   suma_departamental_confirmado,
                   total_nacional_publicado_confirmado
            FROM boletines_procesados
            WHERE anio = %s AND semana_archivo = %s
            ORDER BY version DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            (anio, semana),
        )
        fila = cur.fetchone()
    if fila is None:
        return None
    (
        nombre_archivo,
        estado,
        validacion_cuadra,
        suma_p,
        pub_p,
        suma_c,
        pub_c,
    ) = fila
    return {
        "nombre_archivo": nombre_archivo,
        "estado": estado,
        "validacion_cuadra": validacion_cuadra,
        "suma_departamental_probable": suma_p,
        "total_nacional_publicado_probable": pub_p,
        "suma_departamental_confirmado": suma_c,
        "total_nacional_publicado_confirmado": pub_c,
    }


# Una sola consulta en vez de una por serie (antes eran nueve viajes a
# Postgres por request). anio * 100 + semana_epi ordena igual que
# (anio, semana_epi) porque semana_epi <= 53, así que su max es la misma fila
# que daba ORDER BY anio DESC, semana_epi DESC LIMIT 1. Los JOIN internos no
# descartan filas: region_id, tipo_evento_id y fuente_id son NOT NULL con FK.
# Cada serie conserva los filtros que tenía: solo la departamental exige
# nivel_admin = 1 y la de OpenDengue no filtra por tipo de evento.
_SQL_ULTIMAS_SE = """
    WITH casos AS (
        SELECT t.codigo AS evento,
               f.codigo AS fuente,
               r.nivel_admin,
               max(c.anio * 100 + c.semana_epi) AS ultima
        FROM casos_epidemiologicos c
        JOIN regiones r ON r.id = c.region_id
        JOIN tipos_evento t ON t.id = c.tipo_evento_id
        JOIN fuentes_datos f ON f.id = c.fuente_id
        WHERE f.codigo IN ('minsal_pdf', 'opendengue_v1_3', 'minsal_tablero')
        GROUP BY t.codigo, f.codigo, r.nivel_admin
    )
    SELECT 'dengue_minsal_departamental', max(ultima) FROM casos
        WHERE evento = 'dengue' AND fuente = 'minsal_pdf' AND nivel_admin = 1
    UNION ALL
    SELECT 'dengue_opendengue_nacional', max(ultima) FROM casos
        WHERE fuente = 'opendengue_v1_3'
    UNION ALL
    SELECT 'dengue_tablero_nacional', max(ultima) FROM casos
        WHERE evento = 'dengue' AND fuente = 'minsal_tablero'
    UNION ALL
    SELECT 'ira', max(ultima) FROM casos
        WHERE evento = 'ira' AND fuente = 'minsal_pdf'
    UNION ALL
    SELECT 'neumonias', max(ultima) FROM casos
        WHERE evento = 'neumonia' AND fuente = 'minsal_pdf'
    UNION ALL
    SELECT 'ira_tablero_nacional', max(ultima) FROM casos
        WHERE evento = 'ira' AND fuente = 'minsal_tablero'
    UNION ALL
    SELECT 'neumonias_tablero_nacional', max(ultima) FROM casos
        WHERE evento = 'neumonia' AND fuente = 'minsal_tablero'
    UNION ALL
    SELECT 'clima', max(anio * 100 + semana_epi) FROM variables_ambientales
    UNION ALL
    SELECT 'virus_respiratorios', max(anio * 100 + semana_epi)
        FROM vigilancia_virus_respiratorios
"""


def cargar_ultimas_se(conn) -> dict[str, tuple[int, int] | None]:
    """Ultima (anio, semana_epi) con dato, por serie de antiguedad. None
    si la serie no tiene ninguna fila."""
    with conn.cursor() as cur:
        cur.execute(_SQL_ULTIMAS_SE)
        filas = cur.fetchall()
    ultimas: dict[str, tuple[int, int] | None] = {}
    for serie, ultima in filas:
        ultimas[serie] = None if ultima is None else divmod(int(ultima), 100)
    return {serie: ultimas.get(serie) for serie in SERIES_ANTIGUEDAD}


def construir_integridad(
    conn,
    *,
    week: int | None = None,
    year: int | None = None,
    hoy: date | None = None,
) -> dict:
    """Ensambla la respuesta de M4. `hoy` se inyecta en tests."""
    referencia = hoy or date.today()
    antiguedad = {
        serie: antiguedad_serie(ultima, referencia)
        for serie, ultima in cargar_ultimas_se(conn).items()
    }

    cuerpo: dict = {
        "aviso": AVISO_HONESTIDAD_VIGILANCIA,
        "antiguedad": antiguedad,
    }

    if week is not None and year is not None:
        catalogo = cargar_catalogo_departamentos(conn)
        presentes = cargar_presentes_semana(conn, year, week)
        cuerpo["semana_epi"] = week
        cuerpo["anio"] = year
        cuerpo["completitud"] = {
            serie: completitud_semana(catalogo, presentes.get(serie, set()))
            for serie in SERIES_COMPLETITUD
        }
        cuerpo["cuadre"] = cuadre_boletin(
            cargar_boletin_semana(conn, year, week)
        )
        return cuerpo

    conteos = cargar_conteos_anuales(conn)
    anios = sorted({anio for anio, _ in conteos})
    cuerpo["resumen_anual"] = [
        {
            "anio": anio,
            **{
                serie: completitud_anual(conteos.get((anio, serie), {}))
                for serie in SERIES_COMPLETITUD
            },
        }
        for anio in anios
    ]
    return cuerpo
