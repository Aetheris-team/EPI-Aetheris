"""
Modelo estructural del tablero: identificacion de la semana que sale de la ventana
(docs/experimentos/experimento-nowcast-estructural.md, protocolo del 2026-10-03).

Si la serie fuese el promedio causal de k semanas de conteos crudos x, el cambio semanal seria
(x(t+1) - x(t+1-k)) / k. El termino que sale de la ventana solo se puede usar si los datos lo
determinan. Este script mide cuanto: para cada k, la cota optimista (programa lineal con
tolerancia de redondeo de 0,5 y conteos no negativos) del error que deja sin identificar la suma
de las h semanas mas antiguas de la ventana.

E0a. OpenDengue 2024 con el crudo de 2023 como ancla (descriptiva).
E0b. Tablero 2025 y 2026, pasado libre (compuerta).

No calcula pronosticos. Solo datos hasta 2026-S37. Lee Postgres; no consulta el sitio de MINSAL.

Uso:
    cd backend/ingestion
    POSTGRES_HOST=localhost python analisis_nowcast_estructural.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.optimize import linprog

from analisis_nowcast_forma_serie import TOL, anio_serie, cargar

KS = range(2, 13)
KS_COMPUERTA = range(4, 10)
H = 4
FRACCION_MOVIMIENTO = 0.25
ORIGENES_2026 = range(20, 38)
ORIGENES_2025 = range(20, 52)

RAIZ = Path(__file__).resolve().parents[2] / "docs" / "agentes" / "mejora-predictor" / "resultados-nuevos"
SALIDA = RAIZ / "estructural_identificacion.json"


# ------------------------------------------------------- programa lineal

def sistema(y: np.ndarray, k: int, pasado: np.ndarray | None = None):
    """Restricciones del promedio causal de k semanas.

    Variables: las k - 1 semanas previas a y[0] y luego las n de y, en ese orden. `pasado` tiene
    k - 1 valores, de la mas antigua a la mas reciente; NaN deja la semana libre y no negativa.
    Las semanas de y con NaN no restringen.
    """
    n = len(y)
    nv = (k - 1) + n
    filas, cotas = [], []
    for t in range(n):
        if np.isnan(y[t]):
            continue
        fila = np.zeros(nv)
        fila[t : t + k] = 1.0 / k
        filas.append(fila)
        cotas.append(y[t] + TOL)
        filas.append(-fila)
        cotas.append(-(y[t] - TOL))
    A = np.array(filas) if filas else np.zeros((0, nv))
    b = np.array(cotas)
    limites = []
    for i in range(k - 1):
        v = np.nan if pasado is None else pasado[i]
        limites.append((0.0, None) if np.isnan(v) else (float(v), float(v)))
    limites += [(0.0, None)] * n
    return A, b, limites


def factible(y: np.ndarray, k: int, pasado: np.ndarray | None = None) -> bool:
    A, b, limites = sistema(y, k, pasado)
    res = linprog(np.zeros(A.shape[1]), A_ub=A, b_ub=b, bounds=limites, method="highs")
    return res.status == 0


def rango_suma(y: np.ndarray, k: int, posiciones: list[int], pasado: np.ndarray | None = None):
    """Minimo y maximo de la suma de x en `posiciones` sobre todo x que reproduce y; None si no hay."""
    A, b, limites = sistema(y, k, pasado)
    c = np.zeros(A.shape[1])
    c[posiciones] = 1.0
    bajo = linprog(c, A_ub=A, b_ub=b, bounds=limites, method="highs")
    alto = linprog(-c, A_ub=A, b_ub=b, bounds=limites, method="highs")
    if bajo.status != 0 or alto.status != 0:
        return None
    return float(bajo.fun), float(-alto.fun)


def error_identificacion(y: np.ndarray, k: int, h: int = H, pasado: np.ndarray | None = None) -> float | None:
    """(max S - min S) / (2 k y(t)), con S la suma de las h semanas mas antiguas de la ventana en t = ultimo dato.

    Es la mitad del ancho del rango del termino que sale de la ventana en el pronostico a h semanas,
    relativa al nivel. Definido solo para k >= h.
    """
    if k < h or not np.isfinite(y[-1]) or y[-1] <= 0:
        return None
    n = len(y)
    r = rango_suma(y, k, list(range(n - 1, n - 1 + h)), pasado)
    if r is None:
        return None
    return (r[1] - r[0]) / (2.0 * k * float(y[-1]))


# ---------------------------------------------------------------- magnitud

def mediana_movimiento(series: list[np.ndarray], h: int = H) -> float:
    """Mediana de |y(t+h) - y(t)| / y(t) sobre los pares dentro de cada serie con dato en los dos extremos."""
    valores = []
    for y in series:
        for t in range(len(y) - h):
            if np.isfinite(y[t]) and np.isfinite(y[t + h]) and y[t] > 0:
                valores.append(abs(y[t + h] - y[t]) / y[t])
    return float(np.median(valores))


# ------------------------------------------------------------------- E0a

def pasados_2023(od: dict, k: int) -> dict[str, np.ndarray | None]:
    """Las k - 1 semanas de 2023 anteriores a 2024-S1, en tres variantes (P, P', L)."""
    crudo = np.array([od[(2023, s)] for s in range(52 - k + 2, 53)], dtype=float)
    liberado = crudo.copy()
    liberado[liberado == 0] = np.nan
    return {"P": crudo, "P_prima": liberado, "L": None}


def e0a(od: dict) -> list[dict]:
    y = anio_serie(od, 2024, 52)
    assert np.all(np.isfinite(y)), "OpenDengue 2024 debe tener las 52 semanas"
    filas = []
    for k in KS:
        fila = {"k": k, "variantes": {}}
        for nombre, pasado in pasados_2023(od, k).items():
            ok = factible(y, k, pasado)
            r = {"factible": ok}
            if ok:
                e = error_identificacion(y, k, H, pasado)
                r["e_id_h4"] = None if e is None else round(e, 4)
            fila["variantes"][nombre] = r
        filas.append(fila)
    return filas


# ------------------------------------------------------------------- E0b

def serie_anio(tablero: dict, anio: int) -> np.ndarray:
    y = anio_serie(tablero, anio)
    y = y[:52] if anio == 2025 else y[:37]
    assert np.all(np.isfinite(y)), f"{anio}: faltan semanas"
    return y


def barrido_origenes(y: np.ndarray, k: int, origenes) -> dict:
    valores = []
    for o in origenes:
        e = error_identificacion(y[:o], k)
        if e is not None:
            valores.append(e)
    if not valores:
        return {"origenes": 0, "e_id_mediana": None, "e_id_minimo": None, "e_id_maximo": None}
    return {
        "origenes": len(valores),
        "e_id_mediana": round(float(np.median(valores)), 4),
        "e_id_minimo": round(float(np.min(valores)), 4),
        "e_id_maximo": round(float(np.max(valores)), 4),
    }


def e0b(tablero: dict) -> dict:
    y25, y26 = serie_anio(tablero, 2025), serie_anio(tablero, 2026)
    m4 = mediana_movimiento([y25, y26])
    filas = []
    for k in KS:
        f25, f26 = factible(y25, k), factible(y26, k)
        fila = {"k": k, "factible_2025": f25, "factible_2026": f26}
        if f26 and k >= H:
            fila["origenes_2026"] = barrido_origenes(y26, k, ORIGENES_2026)
        if f25 and k >= H:
            fila["origenes_2025"] = barrido_origenes(y25, k, ORIGENES_2025)
        filas.append(fila)
    return {"m4": round(m4, 4), "umbral": round(FRACCION_MOVIMIENTO * m4, 4), "por_k": filas}


def compuerta(resultado_e0b: dict) -> dict:
    """G = k de 4 a 9 factibles en los dos anios; se supera si algun k de G tiene la mediana de e_id en 2026 <= umbral."""
    umbral = resultado_e0b["umbral"]
    en_g, pasan = [], []
    for fila in resultado_e0b["por_k"]:
        if fila["k"] not in KS_COMPUERTA:
            continue
        if not (fila["factible_2025"] and fila["factible_2026"]):
            continue
        en_g.append(fila["k"])
        mediana = fila["origenes_2026"]["e_id_mediana"]
        if mediana is not None and mediana <= umbral:
            pasan.append(fila["k"])
    return {"G": en_g, "k_que_pasan": pasan, "superada": bool(pasan), "umbral": umbral}


def main() -> None:
    tablero, od = cargar()
    assert max(a * 100 + s for a, s in tablero) <= 202637, "hay semanas posteriores a 2026-S37"
    print(f"tablero: {len(tablero)} semanas; OpenDengue: {len(od)} semanas")
    b = e0b(tablero)
    resultado = {"E0a": e0a(od), "E0b": b, "compuerta": compuerta(b)}
    SALIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"compuerta superada: {resultado['compuerta']['superada']} (k: {resultado['compuerta']['k_que_pasan']})")
    print(f"escrito {SALIDA}")


if __name__ == "__main__":
    main()
