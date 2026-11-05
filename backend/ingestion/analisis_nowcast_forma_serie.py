"""
Analisis descriptivo: que filtro produce la forma de la serie semanal de
sospechosos del tablero de MINSAL (docs/experimentos/analisis-forma-serie-tablero.md,
plan del 2026-10-03).

A. Factibilidad de un promedio movil causal de k semanas (tres variantes de
   inicio de serie) con tolerancia de redondeo de 0,5.
B. Factibilidad de un promedio exponencial.
C. Perfil de saltos semanales frente a OpenDengue crudo y filtrado.
D. Reproduccion de los umbrales del corredor endemico con cuartiles de
   OpenDengue.

Solo datos hasta 2026-S37. Lee Postgres (fuentes minsal_tablero y
opendengue_v1_3); no consulta el sitio de MINSAL.

Uso:
    cd backend/ingestion
    POSTGRES_HOST=localhost python analisis_nowcast_forma_serie.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.optimize import linprog

from db import get_connection

TOL = 0.5
KS = range(2, 13)
ALFAS = [round(a, 2) for a in np.arange(0.05, 0.96, 0.05)]

RAIZ = Path(__file__).resolve().parents[2] / "docs" / "agentes" / "mejora-predictor" / "resultados-nuevos"
ENTRADA_CORREDOR = RAIZ / "corredor_tablero.json"
SALIDA = RAIZ / "forma_serie_tablero.json"


# ---------------------------------------------------------------- datos

def cargar() -> tuple[dict[tuple[int, int], float], dict[tuple[int, int], float]]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.anio, c.semana_epi, c.conteo
                FROM casos_epidemiologicos c
                JOIN fuentes_datos f ON f.id = c.fuente_id
                JOIN tipos_evento t ON t.id = c.tipo_evento_id
                WHERE f.codigo = 'minsal_tablero' AND t.codigo = 'dengue'
                  AND c.clasificacion = 'sospechoso'
                ORDER BY 1, 2
                """
            )
            tablero = {(a, s): float(n) for a, s, n in cur.fetchall()}
            cur.execute(
                """
                SELECT c.anio, c.semana_epi, c.conteo
                FROM casos_epidemiologicos c
                JOIN fuentes_datos f ON f.id = c.fuente_id
                WHERE f.codigo = 'opendengue_v1_3'
                ORDER BY 1, 2
                """
            )
            od = {(a, s): float(n) for a, s, n in cur.fetchall()}
    finally:
        conn.close()
    return tablero, od


def anio_serie(d: dict, anio: int, n: int = 53) -> np.ndarray:
    return np.array([d.get((anio, s), np.nan) for s in range(1, n + 1)])


def contigua(d: dict, anios: list[int]) -> tuple[np.ndarray, list[tuple[int, int]]]:
    claves = sorted(k for k in d if k[0] in anios)
    return np.array([d[k] for k in claves]), claves


# ---------------------------------------------------------- filtros directos

def prom_movil(x: np.ndarray, k: int, modo: str = "causal") -> np.ndarray:
    y = np.full(len(x), np.nan)
    for t in range(len(x)):
        if modo == "causal":
            a, b = max(0, t - k + 1), t + 1
        else:
            h = k // 2
            a, b = max(0, t - h), min(len(x), t + h + 1)
        y[t] = np.mean(x[a:b])
    return y


def ewma(x: np.ndarray, alfa: float) -> np.ndarray:
    y = np.empty(len(x))
    y[0] = x[0]
    for t in range(1, len(x)):
        y[t] = alfa * x[t] + (1 - alfa) * y[t - 1]
    return y


# ------------------------------------------------------------------ A y B

def factible_pm(y: np.ndarray, k: int, variante: str, observado: np.ndarray | None = None) -> dict:
    """Minimiza el maximo semanal x sujeto a |promedio_k(x) - y| <= TOL, x >= 0.

    variante W1: ventana expansiva al inicio. W2/W3: ventana completa con k-1
    semanas previas libres. `observado` marca las semanas con valor publicado
    (W3 deja una semana desconocida).
    """
    n = len(y)
    previas = 0 if variante == "W1" else k - 1
    nv = previas + n  # variables x, mas M al final
    if observado is None:
        observado = np.ones(n, dtype=bool)
    A, b = [], []
    for t in range(n):
        if not observado[t]:
            continue
        fila = np.zeros(nv + 1)
        pos = previas + t
        if variante == "W1":
            ini = max(0, pos - k + 1)
        else:
            ini = pos - k + 1
        ventana = pos - ini + 1
        fila[ini : pos + 1] = 1.0 / ventana
        A.append(fila.copy())
        b.append(y[t] + TOL)
        A.append(-fila)
        b.append(-(y[t] - TOL))
    for j in range(nv):  # x_j <= M
        fila = np.zeros(nv + 1)
        fila[j] = 1.0
        fila[nv] = -1.0
        A.append(fila)
        b.append(0.0)
    c = np.zeros(nv + 1)
    c[nv] = 1.0
    res = linprog(c, A_ub=np.array(A), b_ub=np.array(b), bounds=[(0, None)] * (nv + 1), method="highs")
    if res.status != 0:
        return {"factible": False, "max_x": None}
    return {"factible": True, "max_x": float(res.x[nv])}


def factible_ewma(y: np.ndarray, alfa: float) -> dict:
    """Variables: y verdadero (y +- TOL). x_t = (yv_t - (1-alfa) yv_{t-1}) / alfa >= 0.

    En t=0 el estado previo es libre y no negativo. Minimiza el maximo de x."""
    n = len(y)
    nv = n + 1  # yv_{-1}, yv_0..yv_{n-1}
    A, b = [], []
    for t in range(n):
        # -x_t <= 0  ->  -(yv_t - (1-alfa) yv_{t-1})/alfa <= 0
        fila = np.zeros(nv + 1)
        fila[t + 1] = -1.0 / alfa
        fila[t] = (1 - alfa) / alfa
        A.append(fila.copy())
        b.append(0.0)
        # x_t <= M
        fila2 = np.zeros(nv + 1)
        fila2[t + 1] = 1.0 / alfa
        fila2[t] = -(1 - alfa) / alfa
        fila2[nv] = -1.0
        A.append(fila2)
        b.append(0.0)
    c = np.zeros(nv + 1)
    c[nv] = 1.0
    bounds = [(0, None)] + [(max(0.0, v - TOL), v + TOL) for v in y] + [(0, None)]
    res = linprog(c, A_ub=np.array(A), b_ub=np.array(b), bounds=bounds, method="highs")
    if res.status != 0:
        return {"factible": False, "max_x": None}
    return {"factible": True, "max_x": float(res.x[nv])}


def razon_referencia(od: dict, tipo: str, par: float) -> float:
    """Mayor cociente max(crudo) / max(filtrado) en un anio de OpenDengue 2014-2023."""
    anios = list(range(2014, 2024))
    x, claves = contigua(od, anios)
    y = prom_movil(x, int(par)) if tipo == "pm" else ewma(x, par)
    mejor = 0.0
    for a in anios:
        idx = [i for i, kk in enumerate(claves) if kk[0] == a]
        mejor = max(mejor, float(np.max(x[idx]) / np.max(y[idx])))
    return mejor


def analisis_a_b(tablero: dict, od: dict) -> dict:
    series = {}
    for a in (2025, 2026):
        v = anio_serie(tablero, a)
        series[str(a)] = v[~np.isnan(v)]
    # W3: contigua 2025-S1..2026-S37 con 2025-S53 desconocida
    conj, obs = [], []
    for a in (2025, 2026):
        top = 53 if a == 2025 else 37
        for s in range(1, top + 1):
            v = tablero.get((a, s))
            conj.append(0.0 if v is None else v)
            obs.append(v is not None)
    conj = np.array(conj)
    obs = np.array(obs)

    salida = {"promedio_movil": [], "exponencial": []}
    for k in KS:
        ref = razon_referencia(od, "pm", k)
        fila = {"k": k, "razon_referencia": round(ref, 3), "variantes": {}}
        for var, datos in (
            ("W1_2025", ("W1", series["2025"], None)),
            ("W1_2026", ("W1", series["2026"], None)),
            ("W2_2025", ("W2", series["2025"], None)),
            ("W2_2026", ("W2", series["2026"], None)),
            ("W3_conjunta", ("W3", conj, obs)),
        ):
            tipo, y, o = datos
            r = factible_pm(y, k, "W1" if tipo == "W1" else "W2", o)
            if r["factible"]:
                r["razon_max_x_sobre_max_y"] = round(r["max_x"] / float(np.max(y)), 3)
                r["plausible"] = bool(r["razon_max_x_sobre_max_y"] <= ref)
            else:
                r["plausible"] = False
            r["max_x"] = None if r["max_x"] is None else round(r["max_x"], 1)
            fila["variantes"][var] = r
        salida["promedio_movil"].append(fila)
    for alfa in ALFAS:
        ref = razon_referencia(od, "ewma", alfa)
        fila = {"alfa": alfa, "razon_referencia": round(ref, 3), "variantes": {}}
        for var, y in (("2025", series["2025"]), ("2026", series["2026"])):
            r = factible_ewma(y, alfa)
            if r["factible"]:
                r["razon_max_x_sobre_max_y"] = round(r["max_x"] / float(np.max(y)), 3)
                r["plausible"] = bool(r["razon_max_x_sobre_max_y"] <= ref)
            else:
                r["plausible"] = False
            r["max_x"] = None if r["max_x"] is None else round(r["max_x"], 1)
            fila["variantes"][var] = r
        salida["exponencial"].append(fila)
    return salida


# ---------------------------------------------------------------------- C

def perfil(y: np.ndarray) -> dict:
    y = y[~np.isnan(y)]
    d = np.abs(np.diff(np.log(np.maximum(y, 1.0))))
    return {
        "semanas": int(len(d)),
        "prop_sobre_0_15": round(float(np.mean(d > 0.15)), 3),
        "prop_sobre_0_30": round(float(np.mean(d > 0.30)), 3),
        "semanas_sobre_0_30": int(np.sum(d > 0.30)),
        "maximo": round(float(np.max(d)), 3),
    }


def analisis_c(tablero: dict, od: dict) -> dict:
    out = {}
    t25 = anio_serie(tablero, 2025)[:52]
    t26 = anio_serie(tablero, 2026)[:37]
    out["tablero_2025"] = perfil(t25)
    out["tablero_2026"] = perfil(t26)
    out["tablero_2026_sin_S1_S4"] = perfil(t26[4:])
    out["opendengue_2024"] = perfil(anio_serie(od, 2024)[:52])
    anios = list(range(2014, 2024))
    x, claves = contigua(od, anios)
    por_filtro = {}
    for nombre, y in [("crudo", x)] + [(f"causal_k{k}", prom_movil(x, k)) for k in range(3, 9)]:
        por_anio = {}
        for a in anios:
            idx = [i for i, kk in enumerate(claves) if kk[0] == a]
            por_anio[str(a)] = perfil(y[idx][:37])  # mismas 37 semanas que 2026
        n03 = [v["semanas_sobre_0_30"] for v in por_anio.values()]
        por_filtro[nombre] = {
            "por_anio": por_anio,
            "semanas_sobre_0_30_max": max(n03),
            "semanas_sobre_0_30_mediana": float(np.median(n03)),
        }
    out["opendengue_2014_2023"] = por_filtro
    return out


# ---------------------------------------------------------------------- D

def analisis_d(od: dict) -> dict:
    umbrales = json.loads(ENTRADA_CORREDOR.read_text(encoding="utf-8"))["umbrales"]
    anios = sorted({a for a, _ in od})
    resultados = {}
    for anio_umbral, fines in (("2025", [2022, 2023, 2024]), ("2026", [2023, 2024])):
        thr = np.array([[umbrales[anio_umbral][str(s)][i] for s in range(1, 53) if str(s) in umbrales[anio_umbral]]
                        for i in range(3)])
        semanas = [s for s in range(1, 53) if str(s) in umbrales[anio_umbral]]
        mejores = []
        transf = [("crudo", 1)] + [(m, k) for m in ("causal", "centrado") for k in range(2, 11)]
        for modo, k in transf:
            T = {}
            for a in anios:
                x = anio_serie(od, a)
                T[a] = (x if modo == "crudo" else prom_movil(x[~np.isnan(x)], k, "causal" if modo == "causal" else "centrado"))
                T[a] = np.concatenate([T[a], np.full(53 - len(T[a]), np.nan)])
            for ini in range(2014, 2023):
                for fin in fines:
                    if fin - ini < 2:
                        continue
                    for excl in (None, 2020):
                        ys = [a for a in range(ini, fin + 1) if a != excl]
                        if len(ys) < 3:
                            continue
                        M = np.array([T[a][[s - 1 for s in semanas]] for a in ys])
                        q = np.nanpercentile(M, [25, 50, 75], axis=0)
                        err = float(np.mean(np.abs(np.log((q + 1) / (thr + 1)))))
                        if np.isfinite(err):
                            mejores.append((err, modo, k, ini, fin, excl))
        mejores.sort(key=lambda r: r[0])
        resultados[anio_umbral] = {
            "combinaciones": len(mejores),
            "mejores": [
                {"error_log_medio": round(e, 4), "transformacion": m, "k": k, "anios": f"{i}-{f}", "excluye_2020": ex is not None}
                for e, m, k, i, f, ex in mejores[:5]
            ],
            "reproduce": bool(mejores and mejores[0][0] < 0.03),
        }
    return resultados


def main() -> None:
    tablero, od = cargar()
    assert max(a * 100 + s for a, s in tablero) <= 202637, "hay semanas posteriores a 2026-S37"
    print(f"tablero: {len(tablero)} semanas; OpenDengue: {len(od)} semanas")
    resultado = {
        "A_B_factibilidad": analisis_a_b(tablero, od),
        "C_perfil_de_saltos": analisis_c(tablero, od),
        "D_umbrales_corredor": analisis_d(od),
    }
    SALIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"escrito {SALIDA}")


if __name__ == "__main__":
    main()
