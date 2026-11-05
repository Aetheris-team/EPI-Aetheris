"""
El Salvador frente a 18 paises de las Americas
(docs/experimentos/analisis-clima-dengue-multipais.md, protocolo del 2026-10-03).

Analisis exploratorio, sin pronosticos y sin decision de modelado:

P1. Perfil de cada pais.
P2. Senal regional: replicacion de la correlacion de El Salvador con la senal de 18 paises, con
    intervalos, estabilidad y subconjunto centroamericano.
P3. Asociacion semanal entre la anomalia climatica y el crecimiento a 4 semanas, por pais.
P4. Ciclo medio de casos y clima, por pais.
P5. Corridas anteriores del clasificador (lectura).
P6. Posicion de El Salvador (derivada).

Reutiliza las funciones de analisis_clima_por_anio.py. Casos: Temporal_extract_PAHO_V1_3.csv
(OpenDengue, no versionado). Clima: cache de Open-Meteo de experimento_multipais.py (no versionado).
Lee Postgres solo para el ONI. No consulta ningun sitio externo.

Uso:
    cd backend/ingestion
    POSTGRES_HOST=localhost python analisis_clima_multipais.py
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np

import analisis_clima_por_anio as base
from db import get_connection
from experimento_multipais import CENTROIDES

ANIOS_ANUALES = tuple(range(2014, 2025))
ANIOS = base.ANIOS
H = base.H
SEMANAS_MINIMAS_ANIO = 45
CASOS_MINIMOS_ANIO = 100
PARES_MINIMOS = 30
ANIOS_EVALUABLES_MINIMOS = 5
UMBRAL_COBERTURA_CLIMA = 0.9
BAJA_INCIDENCIA = 5.0
PAISES_EXTENSOS = ("BRAZIL", "MEXICO", "UNITED STATES OF AMERICA", "COLOMBIA", "BOLIVIA")
CENTROAMERICA = ("GUATEMALA", "HONDURAS", "NICARAGUA", "COSTA RICA", "PANAMA", "EL SALVADOR")
MAPA_VARIABLES = {
    "temperature_2m_mean": "temp_media",
    "temperature_2m_max": "temp_max",
    "temperature_2m_min": "temp_min",
    "precipitation_sum": "precipitation_sum",
    "precipitation_hours": "precipitation_hours",
    "relative_humidity_2m_mean": "humedad_relativa_media",
    "dew_point_2m_mean": "punto_rocio",
}
ACUMULATIVAS = ("precipitation_sum", "precipitation_hours")
VARIABLES = base.VARIABLES
REMUESTREOS = base.REMUESTREOS

VERIFICACION = {
    "correlacion_media_pares": (0.453, 0.0015),
    "primer_componente": (0.518, 0.0015),
    "EL SALVADOR": (0.280, 0.0015),
    "COLOMBIA": (0.952, 0.0015),
    "GUATEMALA": (0.908, 0.0015),
    "HONDURAS": (0.868, 0.0015),
    "oni": (0.517, 0.015),
}

RAIZ_DATOS = Path(__file__).resolve().parent / "data"
RAIZ_RESULTADOS = Path(__file__).resolve().parents[2] / "docs" / "agentes" / "mejora-predictor" / "resultados-nuevos"
CSV_CASOS = RAIZ_DATOS / "raw" / "opendengue" / "Temporal_extract_PAHO_V1_3.csv"
CACHE_CLIMA = RAIZ_DATOS / "interim" / "experimento_multipais" / "clima_multipais.json"
CORRIDAS_ANTERIORES = {
    "A": ("solo El Salvador, entrenando con los otros paises", "resultados_el-salvador.json"),
    "B": ("regional", "resultados_regional.json"),
    "C": ("regional con ONI", "resultados_regional_oni.json"),
}
ENTRADA_A3 = RAIZ_RESULTADOS / "clima_por_anio.json"
SALIDA = RAIZ_RESULTADOS / "clima_multipais.json"

LIMITACIONES = [
    "Un punto de clima por pais; para paises extensos no representa el territorio.",
    "La definicion de caso de las series de la OPS no es la misma en todos los paises; la fuente solo indica Total.",
    "Once anios anuales: las correlaciones con la senal regional tienen intervalos amplios.",
    "La serie de El Salvador de 2024 es un promedio de varias semanas hecho en origen; 2020 y 2024 quedan fuera del analisis semanal.",
    "La semana del anio se calcula por fecha de inicio y puede diferir en una de la numeracion epidemiologica de cada pais.",
    "El clima diario se agrega con la zona horaria de El Salvador para todos los paises.",
    "Las corridas anteriores del clasificador (P5) se citan sin recalcular.",
]


# ------------------------------------------------------------------ casos

def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def leer_casos(ruta: Path) -> dict[str, dict[date, tuple[int, float]]]:
    """pais -> {fecha de inicio: (Year, dengue_total)} de las filas Admin0 semanales de 2014 a 2024."""
    salida: dict[str, dict[date, tuple[int, float]]] = defaultdict(dict)
    with open(ruta, encoding="utf-8", errors="replace") as f:
        for fila in csv.DictReader(f):
            if fila["S_res"] != "Admin0" or fila["T_res"] != "Week":
                continue
            try:
                anio = int(fila["Year"])
                valor = float(fila["dengue_total"])
                inicio = date.fromisoformat(fila["calendar_start_date"])
            except (ValueError, TypeError):
                continue
            if anio in ANIOS_ANUALES:
                salida[fila["adm_0_name"]][inicio] = (anio, valor)
    return dict(salida)


def paises_completos(casos: dict) -> list[str]:
    """Paises con al menos 45 semanas en cada uno de los 11 anios, en orden alfabetico."""
    completos = []
    for pais, semanas in casos.items():
        por_anio = defaultdict(int)
        for anio, _ in semanas.values():
            por_anio[anio] += 1
        if all(por_anio[a] >= SEMANAS_MINIMAS_ANIO for a in ANIOS_ANUALES):
            completos.append(pais)
    return sorted(completos)


def totales_anuales(semanas: dict) -> np.ndarray:
    total = defaultdict(float)
    for anio, valor in semanas.values():
        total[anio] += valor
    return np.array([total[a] for a in ANIOS_ANUALES], dtype=float)


def semana_del_anio_fecha(fechas) -> np.ndarray:
    """Semana del anio por fecha de inicio: min((dia del anio - 1) // 7 + 1, 52)."""
    doy = np.array([f.timetuple().tm_yday for f in fechas], dtype=int)
    return np.minimum((doy - 1) // 7 + 1, 52)


@dataclass
class Pais:
    nombre: str
    fecha: np.ndarray
    anio: np.ndarray
    sem: np.ndarray
    casos: np.ndarray
    clima: dict
    oni: np.ndarray


def rejilla(semanas: dict[date, tuple[int, float]]) -> dict:
    """Rejilla semanal por fecha de inicio; las semanas ausentes quedan como NaN."""
    fechas = sorted(semanas)
    f0 = fechas[0]
    n = (fechas[-1] - f0).days // 7 + 1
    casos = np.full(n, np.nan)
    anio = np.zeros(n, dtype=int)
    fecha = np.empty(n, dtype=object)
    presente = np.zeros(n, dtype=bool)
    for f in fechas:
        i = (f - f0).days // 7
        if presente[i]:
            raise ValueError(f"dos semanas caen en la misma celda de la rejilla: {f}")
        presente[i] = True
        casos[i] = semanas[f][1]
        anio[i] = semanas[f][0]
        fecha[i] = f
    for i in range(n):
        if not presente[i]:
            fecha[i] = f0 + timedelta(days=7 * i)
            anio[i] = fecha[i].year
    return {"fecha": fecha, "anio": anio, "casos": casos, "sem": semana_del_anio_fecha(fecha)}


# ------------------------------------------------------------------ clima

def cargar_clima(ruta: Path, paises: list[str]) -> dict[str, dict[str, dict[str, float]]]:
    """pais -> variable -> {fecha ISO: valor}. El orden de las ubicaciones es el de `paises`; se comprueba contra el centroide."""
    bruto = json.loads(ruta.read_text(encoding="utf-8"))
    diario: dict[str, dict[str, dict[str, float]]] = {p: defaultdict(dict) for p in paises}
    for _modelo, respuestas in bruto.items():
        if len(respuestas) != len(paises):
            raise ValueError(f"el cache trae {len(respuestas)} ubicaciones y hay {len(paises)} paises")
        for pais, resp in zip(paises, respuestas):
            lat, lon = CENTROIDES[pais]
            if abs(resp["latitude"] - lat) > 0.5 or abs(resp["longitude"] - lon) > 0.5:
                raise ValueError(f"{pais}: la ubicacion del cache no coincide con su centroide")
            d = resp["daily"]
            tiempos = d["time"]
            suma_nula = [v is None for v in d["precipitation_sum"]] if "precipitation_sum" in d else None
            for nombre_api, valores in d.items():
                if nombre_api == "time":
                    continue
                nombre = MAPA_VARIABLES[nombre_api]
                for i, f in enumerate(tiempos):
                    v = valores[i]
                    if v is None:
                        continue
                    if nombre_api == "precipitation_hours" and suma_nula is not None and suma_nula[i]:
                        continue
                    diario[pais][nombre][f] = float(v)
    return diario


def clima_semanal(diario_pais: dict[str, dict[str, float]], fechas) -> dict[str, np.ndarray]:
    """Suma (lluvia) o media de los 7 dias desde el inicio de cada semana, con al menos 5 dias con dato."""
    salida = {}
    for var in base.VARIABLES_CLIMA:
        serie = diario_pais.get(var, {})
        col = np.full(len(fechas), np.nan)
        for i, f0 in enumerate(fechas):
            vals = [serie[(f0 + timedelta(days=k)).isoformat()] for k in range(7) if (f0 + timedelta(days=k)).isoformat() in serie]
            if len(vals) >= 5:
                col[i] = sum(vals) if var in ACUMULATIVAS else sum(vals) / len(vals)
        salida[var] = col
    return salida


def cargar_oni(conn) -> tuple[list[date], list[float], dict[int, float]]:
    """ONI semanal de la base: fechas de inicio, valores y media por anio epidemiologico."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT s.fecha_inicio, va.anio, va.valor
        FROM variables_ambientales va
        JOIN regiones r ON r.id = va.region_id
        JOIN semanas_epidemiologicas s ON s.anio = va.anio AND s.semana_epi = va.semana_epi
        WHERE r.codigo = 'SV' AND va.variable = 'oni_anom'
        ORDER BY s.fecha_inicio
        """
    )
    filas = cur.fetchall()
    fechas = [f for f, _, _ in filas]
    valores = [float(v) for _, _, v in filas]
    por_anio: dict[int, list[float]] = defaultdict(list)
    for _, a, v in filas:
        por_anio[int(a)].append(float(v))
    return fechas, valores, {a: float(np.mean(v)) for a, v in por_anio.items()}


def oni_en_fechas(fechas_oni: list[date], valores_oni: list[float], fechas) -> np.ndarray:
    """ONI de la ultima semana de la base con inicio anterior o igual a cada fecha (arrastre hacia adelante)."""
    salida = np.full(len(fechas), np.nan)
    for i, f in enumerate(fechas):
        j = bisect.bisect_right(fechas_oni, f) - 1
        if j >= 0:
            salida[i] = valores_oni[j]
    return salida


def construir_pais(nombre: str, semanas: dict, diario_pais: dict, fechas_oni, valores_oni) -> Pais:
    g = rejilla(semanas)
    return Pais(
        nombre, g["fecha"], g["anio"], g["sem"], g["casos"],
        clima_semanal(diario_pais, g["fecha"]), oni_en_fechas(fechas_oni, valores_oni, g["fecha"]),
    )


# ------------------------------------------------------------ construccion

def serie_z(casos: np.ndarray) -> np.ndarray:
    """log1p del promedio de 4 semanas que terminan en t; los ceros cuentan como ceros."""
    return np.log1p(base.media_ventana(casos))


def variables_disponibles(p: Pais) -> list[str]:
    en = np.isin(p.anio, ANIOS)
    return [v for v in base.VARIABLES_CLIMA if np.isfinite(p.clima[v][en]).mean() >= UMBRAL_COBERTURA_CLIMA]


# ----------------------------------------------------------------------- P1

def perfil(p: Pais, totales: np.ndarray, z: np.ndarray) -> dict:
    en = np.isin(p.anio, ANIOS)
    casos = p.casos[en & np.isfinite(p.casos)]
    clim_z = base.climatologia(z, p.sem, p.anio)
    semanas_por_anio = {str(a): int(np.isfinite(p.casos[p.anio == a]).sum()) for a in ANIOS_ANUALES}
    log_totales = np.log1p(totales)
    return {
        "centroide": list(CENTROIDES[p.nombre]),
        "semanas_por_anio": semanas_por_anio,
        "total_anual": {str(a): float(t) for a, t in zip(ANIOS_ANUALES, totales)},
        "casos_semanales_medios": round(float(casos.mean()), 3),
        "fraccion_semanas_cero": round(float((casos == 0).mean()), 4),
        "r2_estacional": round(base.r2_armonicos(np.where(en, z, np.nan), p.sem), 4),
        "semana_del_maximo": int(np.nanargmax(clim_z)) + 1,
        "desviacion_log_total_anual": round(float(np.std(log_totales)), 4),
        "cociente_maximo_mediana": round(float(totales.max() / np.median(totales)), 3) if np.median(totales) > 0 else None,
        "baja_incidencia": bool(casos.mean() < BAJA_INCIDENCIA),
        "pais_extenso": p.nombre in PAISES_EXTENSOS,
        "variables_climaticas": variables_disponibles(p),
    }


# ----------------------------------------------------------------------- P2

def anomalia_anual(totales: np.ndarray) -> np.ndarray:
    """log1p del total anual estandarizado dentro de cada pais (filas: paises, columnas: anios)."""
    L = np.log1p(totales)
    return (L - L.mean(axis=1, keepdims=True)) / L.std(axis=1, keepdims=True)


def senal_regional(totales: np.ndarray) -> dict:
    Z = anomalia_anual(totales)
    senal = Z.mean(axis=0)
    n = len(Z)
    r_con = np.array([base.pearson(Z[i], senal) for i in range(n)])
    r_otros = np.array([base.pearson(Z[i], np.delete(Z, i, axis=0).mean(axis=0)) for i in range(n)])
    C = np.corrcoef(Z)
    iu = np.triu_indices(n, 1)
    _, s, _ = np.linalg.svd(Z, full_matrices=False)
    return {
        "Z": Z, "senal": senal, "r_con_senal": r_con, "r_con_otros": r_otros, "matriz": C,
        "correlacion_media_pares": float(C[iu].mean()), "primer_componente": float(s[0] ** 2 / np.sum(s**2)),
    }


def ic_senal(Z: np.ndarray, senal: np.ndarray, remuestreos: int = REMUESTREOS) -> list[list[float | None]]:
    """Intervalo del 95 % de la correlacion de cada pais con la senal: bootstrap sobre los anios."""
    rng = np.random.default_rng([base.SEMILLA, 0])
    idx = rng.integers(0, Z.shape[1], size=(remuestreos, Z.shape[1]))
    return [base.intervalo(base.correlaciones_filas(Z[i][idx], senal[idx])) for i in range(len(Z))]


def estabilidad(totales: np.ndarray, paises: list[str], objetivo: str = "EL SALVADOR") -> dict:
    i = paises.index(objetivo)
    sin_anio = {}
    for k, a in enumerate(ANIOS_ANUALES):
        cols = [c for c in range(totales.shape[1]) if c != k]
        sin_anio[str(a)] = round(float(senal_regional(totales[:, cols])["r_con_senal"][i]), 4)
    sin_pais = {}
    for j, p in enumerate(paises):
        if p == objetivo:
            continue
        filas = [c for c in range(len(paises)) if c != j]
        r = senal_regional(totales[filas])["r_con_senal"][filas.index(i)]
        sin_pais[p] = round(float(r), 4)
    return {
        "sin_cada_anio": sin_anio, "sin_cada_pais": sin_pais,
        "minimo": min(list(sin_anio.values()) + list(sin_pais.values())),
        "maximo": max(list(sin_anio.values()) + list(sin_pais.values())),
    }


def centroamerica(totales: np.ndarray, paises: list[str]) -> dict:
    Z = anomalia_anual(totales)
    presentes = [p for p in CENTROAMERICA if p in paises]
    sub = Z[[paises.index(p) for p in presentes]]
    salida = {}
    for k, p in enumerate(presentes):
        otros = np.delete(sub, k, axis=0).mean(axis=0)
        salida[p] = round(base.pearson(sub[k], otros), 4)
    return salida


def sensibilidad_sin_paises(totales: np.ndarray, paises: list[str], excluir: list[str]) -> dict:
    """Senal regional recalculada sin los paises `excluir`."""
    idx = [i for i, p in enumerate(paises) if p not in excluir]
    nombres = [paises[i] for i in idx]
    s = senal_regional(totales[idx])
    r = {p: round(float(s["r_con_senal"][k]), 4) for k, p in enumerate(nombres)}
    return {
        "excluidos": sorted(excluir), "r_con_senal": r, "posicion": posiciones_de_menor_a_mayor(r),
        "correlacion_media_pares": round(s["correlacion_media_pares"], 4),
        "primer_componente": round(s["primer_componente"], 4),
    }


def posiciones_de_menor_a_mayor(valores: dict[str, float | None]) -> dict[str, int]:
    validos = {k: v for k, v in valores.items() if v is not None and np.isfinite(v)}
    orden = sorted(validos, key=lambda k: validos[k])
    return {k: i + 1 for i, k in enumerate(orden)}


def p2(totales: np.ndarray, paises: list[str], oni_anual: dict[int, float]) -> dict:
    s = senal_regional(totales)
    ic = ic_senal(s["Z"], s["senal"])
    r_oni = base.pearson(s["senal"], np.array([oni_anual[a] for a in ANIOS_ANUALES]))
    cols9 = [k for k, a in enumerate(ANIOS_ANUALES) if a in ANIOS]
    s9 = senal_regional(totales[:, cols9])
    por_pais = {}
    for i, p in enumerate(paises):
        por_pais[p] = {
            "r_con_senal": round(float(s["r_con_senal"][i]), 4),
            "ic95": ic[i],
            "r_con_otros": round(float(s["r_con_otros"][i]), 4),
            "r_con_senal_9_anios": round(float(s9["r_con_senal"][i]), 4),
            "r_con_otros_9_anios": round(float(s9["r_con_otros"][i]), 4),
            "anomalia_anual": {str(a): round(float(v), 4) for a, v in zip(ANIOS_ANUALES, s["Z"][i])},
        }
    return {
        "correlacion_media_pares": round(s["correlacion_media_pares"], 4),
        "primer_componente": round(s["primer_componente"], 4),
        "correlacion_senal_oni": round(float(r_oni), 4),
        "correlacion_media_pares_9_anios": round(s9["correlacion_media_pares"], 4),
        "primer_componente_9_anios": round(s9["primer_componente"], 4),
        "senal_regional": {str(a): round(float(v), 4) for a, v in zip(ANIOS_ANUALES, s["senal"])},
        "por_pais": por_pais,
        "matriz_correlaciones": {"paises": paises, "valores": [[round(float(x), 4) for x in fila] for fila in s["matriz"]]},
        "posicion_r_con_senal": posiciones_de_menor_a_mayor({p: por_pais[p]["r_con_senal"] for p in paises}),
        "posicion_r_con_senal_9_anios": posiciones_de_menor_a_mayor({p: por_pais[p]["r_con_senal_9_anios"] for p in paises}),
        "estabilidad_el_salvador": estabilidad(totales, paises),
        "centroamerica": centroamerica(totales, paises),
        "centroamerica_9_anios": centroamerica(totales[:, cols9], paises),
    }


def verificar(resultado_p2: dict) -> None:
    """Se detiene si la replicacion no coincide con las cifras del experimento anterior."""
    por_pais = resultado_p2["por_pais"]
    medidas = {
        "correlacion_media_pares": resultado_p2["correlacion_media_pares"],
        "primer_componente": resultado_p2["primer_componente"],
        "oni": resultado_p2["correlacion_senal_oni"],
        **{p: por_pais[p]["r_con_senal"] for p in ("EL SALVADOR", "COLOMBIA", "GUATEMALA", "HONDURAS")},
    }
    for nombre, (esperado, tolerancia) in VERIFICACION.items():
        if abs(medidas[nombre] - esperado) > tolerancia:
            raise SystemExit(f"la replicacion no coincide en {nombre}: {medidas[nombre]} contra {esperado}")
    if resultado_p2["posicion_r_con_senal"]["EL SALVADOR"] != 1:
        raise SystemExit("El Salvador no es el pais con menor correlacion con la senal")


# ----------------------------------------------------------------------- P3

def datos_pais_anio(p: Pais, g: np.ndarray, anio_obj: int, variables: list[str]) -> dict:
    t = base.pares_del_anio(p.anio, anio_obj)
    gan = (g - base.climatologia(g, p.sem, p.anio, anio_obj)[p.sem - 1])[t]
    x = {v: base.media_ventana(base.anomalia(p.clima[v], p.sem, p.anio, anio_obj))[t] for v in variables}
    x["oni"] = p.oni[t]
    ok = np.isfinite(gan)
    for v in x.values():
        ok &= np.isfinite(v)
    return {"g": gan[ok], "x": {k: v[ok] for k, v in x.items()}}


def etiqueta_consistencia(rs: list[float], ic_agrupado: list, evaluables: int) -> dict:
    positivos = sum(r > 0 for r in rs)
    negativos = sum(r < 0 for r in rs)
    excluye = ic_agrupado[0] is not None and (ic_agrupado[0] > 0 or ic_agrupado[1] < 0)
    mismo_signo = max(positivos, negativos) >= evaluables - 1
    return {
        "anios_positivos": positivos, "anios_negativos": negativos,
        "consistente": bool(mismo_signo and excluye),
    }


def asociaciones_pais(p: Pais, indice: int, remuestreos: int = REMUESTREOS) -> dict:
    z = serie_z(p.casos)
    g = base.crecimiento(z, p.anio)
    variables = variables_disponibles(p)
    todas = variables + ["oni"]
    datos, indices = {}, {}
    for a in ANIOS:
        total = float(np.nansum(p.casos[p.anio == a]))
        if total < CASOS_MINIMOS_ANIO:
            continue
        d = datos_pais_anio(p, g, a, variables)
        if len(d["g"]) < PARES_MINIMOS:
            continue
        rng = np.random.default_rng([base.SEMILLA, indice + 1, a])
        datos[a] = d
        indices[a] = base.indices_bloques(len(d["g"]), base.BLOQUE, remuestreos, rng)
    evaluables = sorted(datos)
    salida = {"anios_evaluables": evaluables, "estimacion": len(evaluables) >= ANIOS_EVALUABLES_MINIMOS, "variables": variables}
    if not salida["estimacion"]:
        return salida
    salida["pares"] = {str(a): len(datos[a]["g"]) for a in evaluables}
    por_variable = {}
    for var in todas:
        por_anio, rs = {}, []
        for a in evaluables:
            x, y, idx = datos[a]["x"][var], datos[a]["g"], indices[a]
            r = base.pearson(x, y)
            por_anio[str(a)] = {"r": round(r, 4), "ic95": base.intervalo(base.correlaciones_filas(x[idx], y[idx]))}
            rs.append(r)
        x_all = np.concatenate([datos[a]["x"][var] for a in evaluables])
        y_all = np.concatenate([datos[a]["g"] for a in evaluables])
        X = np.hstack([datos[a]["x"][var][indices[a]] for a in evaluables])
        Y = np.hstack([datos[a]["g"][indices[a]] for a in evaluables])
        agrupado = {"r": round(base.pearson(x_all, y_all), 4), "ic95": base.intervalo(base.correlaciones_filas(X, Y))}
        por_variable[var] = {
            "por_anio": por_anio, "agrupado": agrupado,
            **etiqueta_consistencia([v for v in rs if np.isfinite(v)], agrupado["ic95"], len(evaluables)),
        }
    salida["por_variable"] = por_variable
    return salida


# ----------------------------------------------------------------------- P4

def ciclo_medio(p: Pais, z: np.ndarray) -> dict:
    en = np.isin(p.anio, ANIOS)
    clim_z = base.climatologia(z, p.sem, p.anio)
    salida = {
        "casos": {"r2_estacional": round(base.r2_armonicos(np.where(en, z, np.nan), p.sem), 4),
                  "climatologia": [round(float(c), 4) for c in clim_z]},
        "variables": {},
    }
    for var in variables_disponibles(p):
        v = p.clima[var]
        clim_v = base.climatologia(v, p.sem, p.anio)
        por_desfase = {d: base.pearson(clim_v, np.roll(clim_z, -d)) for d in base.DESPLAZAMIENTOS}
        mejor = max(por_desfase, key=lambda d: por_desfase[d] if np.isfinite(por_desfase[d]) else -2.0)
        salida["variables"][var] = {
            "r2_estacional": round(base.r2_armonicos(np.where(en, v, np.nan), p.sem), 4),
            "desfase_mejor_semanas": int(mejor),
            "correlacion_en_el_mejor": round(por_desfase[mejor], 4),
            "en_el_borde": bool(mejor == max(base.DESPLAZAMIENTOS)),
            "climatologia": [round(float(c), 4) for c in clim_v],
        }
    return salida


# ----------------------------------------------------------------------- P5

def corridas_anteriores(carpeta: Path) -> dict:
    """Resumen por corrida y anio de los resultados guardados del clasificador (sin recalcular)."""
    salida = {}
    for clave, (descripcion, archivo) in CORRIDAS_ANTERIORES.items():
        ruta = carpeta / archivo
        if not ruta.exists():
            salida[clave] = {"descripcion": descripcion, "disponible": False}
            continue
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        anios = {}
        for anio, corridas in datos.items():
            m = [c["modelo"] for c in corridas]
            b = [c["climatologica"] for c in corridas]
            anios[anio] = {
                "soporte_alto": int(m[0]["n_alto_real"]),
                "f1_modelo": round(float(np.mean([x["f1_macro"] for x in m])), 4),
                "recall_alto_modelo": round(float(np.mean([x["recall_alto"] for x in m])), 4),
                "f1_climatologia": round(float(np.mean([x["f1_macro"] for x in b])), 4),
                "recall_alto_climatologia": round(float(np.mean([x["recall_alto"] for x in b])), 4),
                "semillas_que_superan": int(sum(bool(c["supera"]) for c in corridas)),
                "semillas": len(corridas),
            }
        salida[clave] = {
            "descripcion": descripcion, "disponible": True, "anios": anios,
            "anios_con_mayoria_que_supera": sum(v["semillas_que_superan"] * 2 > v["semillas"] for v in anios.values()),
            "anios_total": len(anios),
        }
    return salida


# ----------------------------------------------------------------------- P6

def posicion_el_salvador(resultado: dict) -> dict:
    metricas = {
        "r_con_senal": {p: v["r_con_senal"] for p, v in resultado["P2"]["por_pais"].items()},
        "r_con_otros": {p: v["r_con_otros"] for p, v in resultado["P2"]["por_pais"].items()},
        "desviacion_log_total_anual": {p: v["desviacion_log_total_anual"] for p, v in resultado["P1"].items()},
        "r2_estacional_casos": {p: v["r2_estacional"] for p, v in resultado["P1"].items()},
    }
    for var in ("precipitation_sum", "oni"):
        metricas[f"r_agrupado_{var}"] = {
            p: v["por_variable"][var]["agrupado"]["r"]
            for p, v in resultado["P3"].items()
            if v.get("estimacion") and var in v["por_variable"]
        }
    salida = {}
    for nombre, valores in metricas.items():
        pos = posiciones_de_menor_a_mayor(valores)
        salida[nombre] = {
            "posicion_de_menor_a_mayor": pos.get("EL SALVADOR"), "paises": len(pos),
            "valor": valores.get("EL SALVADOR"),
        }
    return salida


# ------------------------------------------------------------------- main

def calcular(casos: dict, paises: list[str], diario: dict, oni: tuple, carpeta_corridas: Path,
             a3: dict | None = None, remuestreos: int = REMUESTREOS) -> dict:
    fechas_oni, valores_oni, oni_anual = oni
    totales = np.array([totales_anuales(casos[p]) for p in paises])
    objetos = {p: construir_pais(p, casos[p], diario[p], fechas_oni, valores_oni) for p in paises}
    p1, p3, p4 = {}, {}, {}
    for i, nombre in enumerate(paises):
        obj = objetos[nombre]
        z = serie_z(obj.casos)
        p1[nombre] = perfil(obj, totales[i], z)
        p3[nombre] = asociaciones_pais(obj, i, remuestreos)
        p4[nombre] = ciclo_medio(obj, z)
    resultado = {"P1": p1, "P2": p2(totales, paises, oni_anual), "P3": p3, "P4": p4, "P5": corridas_anteriores(carpeta_corridas)}
    baja = [p for p in paises if p1[p]["baja_incidencia"]]
    resultado["P2"]["sin_baja_incidencia"] = sensibilidad_sin_paises(totales, paises, baja)
    resultado["P6"] = posicion_el_salvador(resultado)
    if a3 is not None:
        resultado["referencia_el_salvador_base_de_datos"] = {
            "descripcion": "Asociacion de El Salvador con la serie de la base de datos (ceros como faltantes), analisis-clima-dengue-por-anio.md",
            "agrupado": a3["A3"]["agrupado"], "consistencia": a3["A5"],
        }
    return resultado


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=CSV_CASOS)
    ap.add_argument("--clima", type=Path, default=CACHE_CLIMA)
    ap.add_argument("--salida", type=Path, default=SALIDA)
    args = ap.parse_args()

    casos = leer_casos(args.csv)
    paises = paises_completos(casos)
    assert len(paises) == 18, f"se esperaban 18 paises y hay {len(paises)}"
    assert all(p in CENTROIDES for p in paises)
    diario = cargar_clima(args.clima, paises)
    conn = get_connection()
    try:
        oni = cargar_oni(conn)
    finally:
        conn.close()
    a3 = json.loads(ENTRADA_A3.read_text(encoding="utf-8")) if ENTRADA_A3.exists() else None
    resultado = calcular(casos, paises, diario, oni, args.csv.parent.parent.parent / "interim" / "experimento_multipais", a3)
    verificar(resultado["P2"])
    resultado = {
        "parametros": {
            "anios_anuales": list(ANIOS_ANUALES), "anios_semanales": list(ANIOS), "horizonte": H, "ventana": base.VENTANA,
            "suavizado": base.SUAVIZADO, "bloque": base.BLOQUE, "remuestreos": REMUESTREOS, "semilla": base.SEMILLA,
            "casos_minimos_anio": CASOS_MINIMOS_ANIO, "pares_minimos": PARES_MINIMOS,
            "anios_evaluables_minimos": ANIOS_EVALUABLES_MINIMOS,
        },
        "entradas": {
            "casos": {"archivo": args.csv.name, "sha256": sha256(args.csv)},
            "clima": {"archivo": args.clima.name, "sha256": sha256(args.clima)},
            "paises": paises,
        },
        "limitaciones": LIMITACIONES,
        **resultado,
    }
    args.salida.write_text(
        json.dumps(base.limpio(resultado), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8"
    )
    pos = resultado["P2"]["posicion_r_con_senal"]["EL SALVADOR"]
    print(f"replicacion verificada; El Salvador ocupa el puesto {pos} de {len(paises)} (de menor a mayor)")
    print(f"escrito {args.salida}")


if __name__ == "__main__":
    main()
