"""
Analisis descriptivo: donde fallan los rangos de la prediccion publicada (C)
en 2026 (docs/experimentos/analisis-cobertura-2026.md, plan del 2026-10-03).

Lee las predicciones ya guardadas por experimento_nowcast_rangos.py (fase B,
capa R0) y, por tramo de semanas objetivo (S1-S3, S19-S22, resto), reporta
cobertura, lado de los fallos y el error de la mediana de C, M0 y T. No corre
ningun modelo ni consulta Postgres.

Uso:
    cd backend/ingestion
    python analisis_nowcast_cobertura_2026.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

CUANTILES = np.array(
    [0.01, 0.025, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50,
     0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.975, 0.99]
)
IDX_MEDIANA = 11
IDX_B50 = (6, 16)
IDX_B95 = (1, 21)
HORIZONTES = range(1, 9)
ANIOS = (2025, 2026)
TRAMOS = {"S1-S3": range(1, 4), "S19-S22": range(19, 23)}

RAIZ = Path(__file__).resolve().parents[2] / "docs" / "agentes" / "mejora-predictor" / "resultados-nuevos"
ENTRADA = RAIZ / "rangos.json"
SALIDA = RAIZ / "cobertura_2026.json"


def tramo(semana: int) -> str:
    for nombre, semanas in TRAMOS.items():
        if semana in semanas:
            return nombre
    return "resto"


def nivel_pit(y: float, q: np.ndarray) -> float:
    """Nivel del cuantil en que cae y, interpolado; 0 o 1 fuera de los extremos."""
    q = np.sort(q)
    if y < q[0]:
        return 0.0
    if y > q[-1]:
        return 1.0
    return float(np.interp(y, q, CUANTILES))


def lado(y: float, q: np.ndarray, idx: tuple[int, int]) -> str:
    q = np.sort(q)
    if y < q[idx[0]]:
        return "abajo"  # lo observado quedo por debajo del rango: se predijo de mas
    if y > q[idx[1]]:
        return "arriba"  # lo observado quedo por encima: se predijo de menos
    return "dentro"


def error_mediana(q: np.ndarray, y: float) -> float:
    """log1p(mediana) - log1p(y): positivo = se predijo de mas."""
    return float(np.log1p(np.sort(q)[IDX_MEDIANA]) - np.log1p(y))


def filas(datos: dict) -> list[dict]:
    out = []
    for h in HORIZONTES:
        for f in datos["detalle"][f"B_h{h}"]:
            if f["anio"] not in ANIOS:
                continue
            y = float(f["y"])
            qc, q0, qt = (np.array(f[k], dtype=float) for k in ("q_C_R0", "q_R0", "q_T"))
            out.append({
                "h": h, "anio": f["anio"], "semana": f["semana"], "origen": f["origen"], "y": y,
                "tramo": tramo(f["semana"]),
                "mediana_C": float(np.sort(qc)[IDX_MEDIANA]),
                "b95_C": [float(np.sort(qc)[IDX_B95[0]]), float(np.sort(qc)[IDX_B95[1]])],
                "lado_95": lado(y, qc, IDX_B95), "lado_50": lado(y, qc, IDX_B50),
                "pit_C": nivel_pit(y, qc),
                "err_C": error_mediana(qc, y), "err_M0": error_mediana(q0, y), "err_T": error_mediana(qt, y),
            })
    return out


def resumir(fs: list[dict]) -> dict:
    if not fs:
        return {"n": 0}
    l95 = [f["lado_95"] for f in fs]
    return {
        "n": len(fs),
        "cobertura_95": round(float(np.mean([x == "dentro" for x in l95])), 3),
        "cobertura_50": round(float(np.mean([f["lado_50"] == "dentro" for f in fs])), 3),
        "fuera_95_arriba": int(sum(x == "arriba" for x in l95)),
        "fuera_95_abajo": int(sum(x == "abajo" for x in l95)),
        "pit_medio": round(float(np.mean([f["pit_C"] for f in fs])), 3),
        "error_mediana_C": round(float(np.mean([f["err_C"] for f in fs])), 3),
        "error_mediana_M0": round(float(np.mean([f["err_M0"] for f in fs])), 3),
        "error_mediana_T": round(float(np.mean([f["err_T"] for f in fs])), 3),
    }


def main() -> None:
    datos = json.loads(ENTRADA.read_text(encoding="utf-8"))
    fs = filas(datos)
    tabla: dict = {}
    for anio in ANIOS:
        tabla[anio] = {}
        for h in HORIZONTES:
            fa = [f for f in fs if f["anio"] == anio and f["h"] == h]
            tabla[anio][h] = {"todas": resumir(fa)}
            for t in list(TRAMOS) + ["resto"]:
                tabla[anio][h][t] = resumir([f for f in fa if f["tramo"] == t])

    print("Cobertura del 95 % de C por tramo de semanas objetivo (n entre parentesis);"
          " fuera arriba/abajo; error medio de la mediana en log1p C | M0 | T")
    for anio in ANIOS:
        print(f"\n{anio}")
        for h in HORIZONTES:
            celdas = []
            for t in ["todas"] + list(TRAMOS) + ["resto"]:
                r = tabla[anio][h][t]
                if not r["n"]:
                    celdas.append(f"{t}: -")
                    continue
                celdas.append(f"{t}: {r['cobertura_95']:.2f} ({r['n']}) {r['fuera_95_arriba']}/{r['fuera_95_abajo']}"
                              f" [{r['error_mediana_C']:+.2f} | {r['error_mediana_M0']:+.2f} | {r['error_mediana_T']:+.2f}]")
            print(f"  h={h}  " + "   ".join(celdas))

    fuera_2026 = [f for f in fs if f["anio"] == 2026 and f["lado_95"] != "dentro"]
    print(f"\nFallos del 95 % en 2026: {len(fuera_2026)} de {sum(f['anio'] == 2026 for f in fs)} predicciones")
    por_semana: dict = {}
    for f in fuera_2026:
        por_semana.setdefault(f["semana"], []).append(f"h{f['h']}{'+' if f['lado_95'] == 'arriba' else '-'}")
    for s in sorted(por_semana):
        print(f"  S{s:>2}: {' '.join(por_semana[s])}")

    salida = {
        "fuente": "rangos.json, fase B, capa R0 (metodo publicado)",
        "tramos": {k: list(v) for k, v in TRAMOS.items()},
        "por_anio_horizonte_tramo": tabla,
        "fallos_95_2026_por_semana": {int(s): v for s, v in sorted(por_semana.items())},
        "detalle": fs,
    }
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"\n-> {SALIDA}")


if __name__ == "__main__":
    main()
