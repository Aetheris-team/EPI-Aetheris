"""
Clima y dengue anio por anio (docs/experimentos/analisis-clima-dengue-por-anio.md, protocolo del 2026-10-03).

Analisis exploratorio, sin pronosticos y sin decision de modelado:

A1. Aporte del clima, del ONI y del anio al skill del predictor, por anio (lectura de insumos.json).
A2. Parte estacional del clima y de los casos; desfase entre los ciclos.
A3. Correlacion entre la anomalia climatica y la anomalia del crecimiento a 4 semanas, por anio.
A4. Perfil de cada anio.
A5. Consistencia entre anios (derivada de A3).

Casos: OpenDengue nacional 'total', anios 2014-2019 y 2021-2023. Solo datos hasta 2024 en la base; no
mira ninguna semana de 2026-S38 en adelante. Lee Postgres; no consulta el sitio de MINSAL.

Uso:
    cd backend/ingestion
    POSTGRES_HOST=localhost python analisis_clima_por_anio.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from db import get_connection
from experimento_nowcast_corto_plazo import VARIABLES_CLIMA, Serie, cargar_serie

ANIOS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023)
VARIABLES = tuple(VARIABLES_CLIMA) + ("oni",)
H = 4
VENTANA = 4
SUAVIZADO = 5
BLOQUE = 8
REMUESTREOS = 2000
SEMILLA = 20261003
DESPLAZAMIENTOS = range(0, 17)
ARMONICOS = 3
ANIOS_MISMO_SIGNO = 8

RAIZ = Path(__file__).resolve().parents[2] / "docs" / "agentes" / "mejora-predictor" / "resultados-nuevos"
ENTRADA_INSUMOS = RAIZ / "insumos.json"
SALIDA = RAIZ / "clima_por_anio.json"


# ------------------------------------------------------------ construccion

def semana_del_anio(semana: np.ndarray) -> np.ndarray:
    """Semana del anio de 1 a 52; la 53 se pliega a la 52."""
    return np.minimum(semana, 52)


def media_ventana(x: np.ndarray, n: int = VENTANA) -> np.ndarray:
    """Media de las n posiciones que terminan en t, entre las que tienen dato; NaN si no hay ninguna."""
    salida = np.full(len(x), np.nan)
    for t in range(len(x)):
        tramo = x[max(0, t - n + 1) : t + 1]
        valido = tramo[np.isfinite(tramo)]
        if len(valido):
            salida[t] = valido.mean()
    return salida


def serie_z(casos: np.ndarray) -> np.ndarray:
    """log1p del promedio de 4 semanas; las semanas con 0 (vacaciones sin notificar) cuentan como faltantes."""
    crudo = np.where(casos > 0, casos, np.nan)
    return np.log1p(media_ventana(crudo))


def crecimiento(z: np.ndarray, anio: np.ndarray, h: int = H) -> np.ndarray:
    """g(t) = z(t + h) - z(t); NaN si t y t + h no son del mismo anio o falta un extremo."""
    g = np.full(len(z), np.nan)
    for t in range(len(z) - h):
        if anio[t] == anio[t + h]:
            g[t] = z[t + h] - z[t]
    return g


def suavizar_circular(base: np.ndarray, ancho: int = SUAVIZADO) -> np.ndarray:
    """Media movil circular centrada de `ancho` semanas que ignora las semanas sin dato."""
    n = len(base)
    mitad = ancho // 2
    salida = np.full(n, np.nan)
    for i in range(n):
        tramo = base[[(i + d) % n for d in range(-mitad, mitad + 1)]]
        valido = tramo[np.isfinite(tramo)]
        if len(valido):
            salida[i] = valido.mean()
    return salida


def climatologia(valores: np.ndarray, sem: np.ndarray, anio: np.ndarray, excluir: int | None = None) -> np.ndarray:
    """52 valores: media de la misma semana del anio sobre los anios de analisis salvo `excluir`, suavizada."""
    usar = [a for a in ANIOS if a != excluir]
    mascara = np.isin(anio, usar) & np.isfinite(valores)
    base = np.full(52, np.nan)
    for w in range(1, 53):
        sel = mascara & (sem == w)
        if sel.any():
            base[w - 1] = valores[sel].mean()
    return suavizar_circular(base)


def anomalia(valores: np.ndarray, sem: np.ndarray, anio: np.ndarray, excluir: int) -> np.ndarray:
    """Valor menos la climatologia de los otros anios, semana a semana."""
    return valores - climatologia(valores, sem, anio, excluir)[sem - 1]


def pares_del_anio(anio: np.ndarray, anio_obj: int, h: int = H) -> np.ndarray:
    """Origenes t del anio con t + h tambien en el anio."""
    return np.array([t for t in range(len(anio) - h) if anio[t] == anio_obj and anio[t + h] == anio_obj], dtype=int)


# ------------------------------------------------------------- estadisticos

def limpio(o):
    """Cambia por None los numeros no finitos, para que el JSON sea valido en el navegador."""
    if isinstance(o, dict):
        return {k: limpio(v) for k, v in o.items()}
    if isinstance(o, list):
        return [limpio(v) for v in o]
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def pearson(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def indices_bloques(n: int, bloque: int, remuestreos: int, rng: np.random.Generator) -> np.ndarray:
    """Indices del bootstrap de bloques moviles: (remuestreos, n)."""
    bloque = min(bloque, n)
    cuantos = -(-n // bloque)
    inicios = rng.integers(0, n - bloque + 1, size=(remuestreos, cuantos))
    idx = (inicios[:, :, None] + np.arange(bloque)).reshape(remuestreos, -1)
    return idx[:, :n]


def correlaciones_filas(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Pearson por fila de dos matrices (B, N); NaN si una fila es constante."""
    xc = x - x.mean(axis=1, keepdims=True)
    yc = y - y.mean(axis=1, keepdims=True)
    denominador = np.sqrt((xc**2).sum(axis=1) * (yc**2).sum(axis=1))
    with np.errstate(invalid="ignore", divide="ignore"):
        return (xc * yc).sum(axis=1) / denominador


def intervalo(replicas: np.ndarray) -> list[float | None]:
    valido = replicas[np.isfinite(replicas)]
    if len(valido) < 0.9 * len(replicas):
        return [None, None]
    return [round(float(np.percentile(valido, 2.5)), 4), round(float(np.percentile(valido, 97.5)), 4)]


def r2_armonicos(valores: np.ndarray, sem: np.ndarray, n_armonicos: int = ARMONICOS) -> float:
    """R2 de una regresion con intercepto y n armonicos anuales sobre las filas con dato."""
    ok = np.isfinite(valores)
    y = valores[ok]
    ang = 2 * np.pi * (sem[ok] - 1) / 52.0
    cols = [np.ones(len(y))]
    for k in range(1, n_armonicos + 1):
        cols += [np.sin(k * ang), np.cos(k * ang)]
    X = np.column_stack(cols)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    sse = float(((y - X @ coef) ** 2).sum())
    sst = float(((y - y.mean()) ** 2).sum())
    return 1.0 - sse / sst if sst > 0 else float("nan")


# ----------------------------------------------------------------------- A1

def aporte_clima(insumos: dict) -> dict:
    """Aporte por anio = skill(I0) - skill(variante), validacion, persistencia limpia. Positivo: el rasgo ayuda."""
    tablas = insumos["fases"]["validacion"]["tablas"]["limpia"]
    salida = {}
    for h, por_variante in tablas.items():
        s0 = por_variante["I0"]["skill_por_anio"]
        fila = {"skill_I0": s0}
        for nombre, variante in (("clima", "I2"), ("oni", "I1"), ("clima_y_oni", "I3"), ("anio", "I4")):
            s = por_variante[variante]["skill_por_anio"]
            aporte = {a: round(s0[a] - s[a], 4) for a in s0}
            fila[nombre] = {"por_anio": aporte, "anios_a_favor": sum(v > 0 for v in aporte.values()), "anios": len(aporte)}
        salida[h] = fila
    return salida


# ----------------------------------------------------------------------- A2

def estacionalidad(serie: Serie, z: np.ndarray) -> dict:
    sem = semana_del_anio(serie.semana)
    en_analisis = np.isin(serie.anio, ANIOS)
    clim_z = climatologia(z, sem, serie.anio)
    filas = {}
    for var in VARIABLES_CLIMA:
        v = serie.clima[var]
        clim_v = climatologia(v, sem, serie.anio)
        por_desfase = {}
        for d in DESPLAZAMIENTOS:
            por_desfase[d] = pearson(clim_v, np.roll(clim_z, -d))
        mejor = max(por_desfase, key=lambda d: por_desfase[d] if np.isfinite(por_desfase[d]) else -2.0)
        filas[var] = {
            "r2_estacional": round(r2_armonicos(np.where(en_analisis, v, np.nan), sem), 4),
            "desfase_mejor_semanas": int(mejor),
            "correlacion_en_el_mejor": round(por_desfase[mejor], 4),
            "correlacion_por_desfase": {str(d): round(r, 4) for d, r in por_desfase.items()},
            "climatologia": [round(float(c), 4) for c in clim_v],
        }
    return {
        "casos_r2_estacional": round(r2_armonicos(np.where(en_analisis, z, np.nan), sem), 4),
        "casos_climatologia": [round(float(c), 4) for c in clim_z],
        "por_variable": filas,
    }


# ----------------------------------------------------------------------- A3

def datos_del_anio(serie: Serie, z: np.ndarray, g: np.ndarray, anio_obj: int) -> dict:
    """Pares (anomalia climatica en t, anomalia de g) del anio, con las mismas filas para las 8 variables."""
    sem = semana_del_anio(serie.semana)
    t = pares_del_anio(serie.anio, anio_obj)
    gan = (g - climatologia(g, sem, serie.anio, anio_obj)[sem - 1])[t]
    x = {}
    for var in VARIABLES_CLIMA:
        x[var] = media_ventana(anomalia(serie.clima[var], sem, serie.anio, anio_obj))[t]
    x["oni"] = serie.oni[t]
    ok = np.isfinite(gan)
    for v in x.values():
        ok &= np.isfinite(v)
    return {"t": t[ok], "g": gan[ok], "x": {k: v[ok] for k, v in x.items()}}


def asociaciones(serie: Serie, z: np.ndarray, g: np.ndarray, remuestreos: int = REMUESTREOS) -> dict:
    por_anio, indices = {}, {}
    for anio_obj in ANIOS:
        d = datos_del_anio(serie, z, g, anio_obj)
        n = len(d["g"])
        assert n >= 20, f"{anio_obj}: solo {n} pares"
        rng = np.random.default_rng([SEMILLA, anio_obj])
        idx = indices_bloques(n, BLOQUE, remuestreos, rng)
        indices[anio_obj] = (d, idx)
        fila = {"pares": n}
        for var in VARIABLES:
            x, y = d["x"][var], d["g"]
            fila[var] = {
                "r": round(pearson(x, y), 4),
                "ic95": intervalo(correlaciones_filas(x[idx], y[idx])),
            }
        por_anio[str(anio_obj)] = fila
    agrupado = {"pares": int(sum(len(indices[a][0]["g"]) for a in ANIOS))}
    for var in VARIABLES:
        x = np.concatenate([indices[a][0]["x"][var] for a in ANIOS])
        y = np.concatenate([indices[a][0]["g"] for a in ANIOS])
        X = np.hstack([indices[a][0]["x"][var][indices[a][1]] for a in ANIOS])
        Y = np.hstack([indices[a][0]["g"][indices[a][1]] for a in ANIOS])
        agrupado[var] = {"r": round(pearson(x, y), 4), "ic95": intervalo(correlaciones_filas(X, Y))}
    return {"por_anio": por_anio, "agrupado": agrupado}


# ----------------------------------------------------------------------- A4

def perfiles(serie: Serie, z: np.ndarray) -> dict:
    sem = semana_del_anio(serie.semana)
    filas = {}
    for anio_obj in ANIOS:
        en = serie.anio == anio_obj
        zz = np.where(en, z, np.nan)
        pico = int(np.nanargmax(zz))
        fila = {
            "casos_totales": float(serie.casos[en].sum()),
            "semana_del_pico": int(sem[pico]),
            "valor_del_pico": round(float(np.expm1(z[pico])), 2),
            "oni_medio": round(float(np.nanmean(serie.oni[en])), 4),
        }
        for var in VARIABLES_CLIMA:
            v = serie.clima[var]
            an = anomalia(v, sem, serie.anio, anio_obj)
            fila[var] = {
                "media": round(float(np.nanmean(v[en])), 4),
                "anomalia_media": round(float(np.nanmean(an[en])), 4),
            }
        filas[str(anio_obj)] = fila
    totales = np.array([filas[str(a)]["casos_totales"] for a in ANIOS])
    spearman = {}
    for var in VARIABLES_CLIMA:
        rho = spearmanr(totales, [filas[str(a)][var]["anomalia_media"] for a in ANIOS]).statistic
        spearman[var] = round(float(rho), 4)
    spearman["oni"] = round(float(spearmanr(totales, [filas[str(a)]["oni_medio"] for a in ANIOS]).statistic), 4)
    return {"por_anio": filas, "spearman_total_vs_anomalia_media": spearman, "n": len(ANIOS)}


# ----------------------------------------------------------------------- A5

def consistencia(a3: dict) -> dict:
    filas = {}
    for var in VARIABLES:
        rs = [a3["por_anio"][str(a)][var]["r"] for a in ANIOS]
        ics = [a3["por_anio"][str(a)][var]["ic95"] for a in ANIOS]
        positivos = sum(r > 0 for r in rs)
        negativos = sum(r < 0 for r in rs)
        excluyen = sum(ic[0] is not None and (ic[0] > 0 or ic[1] < 0) for ic in ics)
        ic_pool = a3["agrupado"][var]["ic95"]
        pool_excluye = ic_pool[0] is not None and (ic_pool[0] > 0 or ic_pool[1] < 0)
        mismo_signo = max(positivos, negativos) >= ANIOS_MISMO_SIGNO
        filas[var] = {
            "anios_positivos": positivos,
            "anios_negativos": negativos,
            "anios_con_ic_sin_cero": excluyen,
            "r_minimo": min(rs),
            "r_maximo": max(rs),
            "consistente": bool(mismo_signo and pool_excluye),
        }
    return filas


# ---------------------------------------------------------------- series

def exportar_series(serie: Serie, z: np.ndarray) -> dict:
    """Entradas semanales por anio para dibujar: casos (promedio de 4 semanas) y clima con su anomalia."""
    sem = semana_del_anio(serie.semana)
    salida = {}
    for anio_obj in ANIOS:
        en = np.where(serie.anio == anio_obj)[0]
        fila = {
            "semana": [int(s) for s in serie.semana[en]],
            "casos_4sem": [None if not np.isfinite(z[t]) else round(float(np.expm1(z[t])), 2) for t in en],
        }
        for var in VARIABLES_CLIMA:
            v = serie.clima[var]
            an = anomalia(v, sem, serie.anio, anio_obj)
            fila[var] = {
                "valor": [round(float(v[t]), 3) for t in en],
                "anomalia": [round(float(an[t]), 3) for t in en],
            }
        fila["oni"] = [round(float(serie.oni[t]), 3) for t in en]
        salida[str(anio_obj)] = fila
    return salida


# ------------------------------------------------------------------- main

def calcular(serie: Serie, insumos: dict, remuestreos: int = REMUESTREOS) -> dict:
    z = serie_z(serie.casos)
    g = crecimiento(z, serie.anio)
    a3 = asociaciones(serie, z, g, remuestreos)
    return {
        "parametros": {
            "anios": list(ANIOS),
            "horizonte": H,
            "ventana": VENTANA,
            "suavizado": SUAVIZADO,
            "bloque": BLOQUE,
            "remuestreos": remuestreos,
            "semilla": SEMILLA,
        },
        "A1": aporte_clima(insumos),
        "A2": estacionalidad(serie, z),
        "A3": a3,
        "A4": perfiles(serie, z),
        "A5": consistencia(a3),
        "series": exportar_series(serie, z),
    }


def main() -> None:
    insumos = json.loads(ENTRADA_INSUMOS.read_text(encoding="utf-8"))
    conn = get_connection()
    try:
        serie = cargar_serie(conn)
    finally:
        conn.close()
    assert int(serie.anio.max()) <= 2024, "la base trae anios posteriores a 2024"
    for anio_obj in ANIOS:
        assert int((serie.anio == anio_obj).sum()) >= 52, f"{anio_obj}: faltan semanas"
    resultado = calcular(serie, insumos)
    SALIDA.write_text(
        json.dumps(limpio(resultado), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8"
    )
    consistentes = [v for v, f in resultado["A5"].items() if f["consistente"]]
    print(f"variables consistentes: {consistentes or 'ninguna'}")
    print(f"escrito {SALIDA}")


if __name__ == "__main__":
    main()
