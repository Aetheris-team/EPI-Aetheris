"""
Fase 3 de la mejora del predictor para la serie del tablero: banda de riesgo,
un limite alto del 97,5 % cuyo factor depende del regimen de crecimiento
(docs/experimentos/experimento-nowcast-banda-riesgo.md, protocolo del
2026-10-03, commiteado antes de escribir este script).

  --control        controles de reproduccion y de sanidad; se detiene si fallan.
  --parte-a        L0, L1 y L2 con calibracion hacia adelante sobre M0 en
                   OpenDengue (objetivos 2019, 2021-2024).
  --extension-e1   L1p y L2p (scores de los 8 horizontes acumulados). Solo si el
                   protocolo lo pide: ni L1 ni L2 pasan y a una solo le falla el
                   ensanchamiento.
  --parte-b        capa elegida con tabla fija ajustada en A, aplicada a C en el
                   tablero (2025 a 2026-S37, dentro de muestra).
  --diagnostico    cifras exploratorias sobre la parte A (no decide): distribucion de
                   los scores, cota de un factor optimo visto dentro de muestra y
                   excedencias por tamano de la mediana.

Todo sale de cuantiles guardados en rangos.json: no reentrena nada. Ninguna
decision usa semanas objetivo desde 2026-S38 (prueba prospectiva congelada).

Uso:
    cd backend/ingestion
    POSTGRES_HOST=localhost nice -n 10 ../.venv/bin/python experimento_nowcast_banda_riesgo.py --control
    POSTGRES_HOST=localhost nice -n 10 ../.venv/bin/python experimento_nowcast_banda_riesgo.py --parte-a
"""

from __future__ import annotations

import argparse
import json
from math import ceil
from pathlib import Path

import numpy as np

import experimento_nowcast_tablero as tab
import experimento_nowcast_tendencia_seleccion as sel
from experimento_nowcast_corto_plazo import IDX_MEDIANA, Serie, cobertura
from nowcast_estimacion_dengue import IDX_B50, IDX_B95

from db import get_connection

# --- parametros fijados en el protocolo -------------------------------------

HORIZONTES = tuple(range(1, 9))
I_MED, I_Q975, I_Q99 = IDX_MEDIANA, 21, 22
NIVEL = 0.975
N_MIN = 40
K_SUAVIZADO = 7
SEMANAS_CRECIMIENTO = 3
MIN_CRECIMIENTOS = 52
EPS_SEMIANCHO = 1e-3
BARAJADOS = 200
SEMILLA = 0
ALTO = 2  # etiqueta del tercio de crecimiento alto

# parte A
COB_ALTO_MIN = 0.95
COB_TOTAL = (0.96, 0.99)
HORIZ_MEJOR_MIN = 5  # de 8
ANIOS_OK_MIN = 4  # de 5
ENSANCH_MAX = 2.0
RAZON_L2_L1 = 0.98
PERCENTIL_BARAJADO = 10
# parte B
B_COB_TOTAL = (0.95, 0.99)
B_RAZON_MAX = 1.03
INICIO_PROSPECTIVA = "2026-09-20"
TOL_COBERTURA = 0.005

RAIZ = Path(__file__).resolve().parents[2] / "docs" / "agentes" / "mejora-predictor" / "resultados-nuevos"
RANGOS = RAIZ / "rangos.json"
SALIDA = RAIZ / "banda_riesgo.json"


# --- regimen de crecimiento ---------------------------------------------------


def etiquetas_desde_z(z: np.ndarray) -> np.ndarray:
    """Tercio de crecimiento (0 cae, 1 plano, 2 sube) de cada semana: g_t =
    z_t - z_(t-3) frente a los percentiles 33,3 y 66,7 de los g con indice menor
    o igual a t. Usa solo datos hasta t. -1 si g_t no es finito o hay menos de
    MIN_CRECIMIENTOS valores previos."""
    T = len(z)
    g = np.full(T, np.nan)
    g[SEMANAS_CRECIMIENTO:] = z[SEMANAS_CRECIMIENTO:] - z[:-SEMANAS_CRECIMIENTO]
    etiq = np.full(T, -1, dtype=int)
    for t in range(T):
        if not np.isfinite(g[t]):
            continue
        previos = g[: t + 1]
        previos = previos[np.isfinite(previos)]
        if len(previos) < MIN_CRECIMIENTOS:
            continue
        c1, c2 = np.quantile(previos, [1 / 3, 2 / 3])
        etiq[t] = 0 if g[t] <= c1 else (1 if g[t] <= c2 else 2)
    return etiq


def etiquetas_regimen(serie: Serie) -> np.ndarray:
    return etiquetas_desde_z(sel.historia(serie, K_SUAVIZADO).z)


# --- factor conforme y limites -------------------------------------------------


def factor_conforme(s: np.ndarray) -> float:
    """Cuantil conforme de nivel min(ceil((n+1)*0,975)/n; 1) de los scores, con la
    convencion de CQR-r (maximo si el nivel llega a 1, method='higher' si no), y
    piso de 1: el limite de riesgo nunca queda bajo el limite central."""
    n = len(s)
    nivel = min(ceil(round((n + 1) * NIVEL, 9)) / n, 1.0)
    f = float(np.max(s)) if nivel >= 1.0 else float(np.quantile(s, nivel, method="higher"))
    return max(f, 1.0)


def puntaje(y: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Score de cada par: cuantos semianchos superiores por encima de la mediana
    quedo y, en log1p."""
    l, m, u = np.log1p(y), np.log1p(q[:, I_MED]), np.log1p(q[:, I_Q975])
    return (l - m) / np.maximum(u - m, EPS_SEMIANCHO)


def limites(q: np.ndarray, f: np.ndarray) -> dict[str, np.ndarray]:
    """Limites del 97,5 % y del 99 % en casos: m + f * (cuantil - m) en log1p."""
    m = np.log1p(q[:, I_MED])
    return {
        "l975": np.expm1(m + f * (np.log1p(q[:, I_Q975]) - m)),
        "l99": np.expm1(m + f * (np.log1p(q[:, I_Q99]) - m)),
    }


def pinball(y: np.ndarray, lim: np.ndarray, tau: float) -> np.ndarray:
    d = y - lim
    return np.where(d >= 0, tau * d, (tau - 1.0) * d)


# --- datos guardados -----------------------------------------------------------


def cargar_bloque(serie: Serie, etiq: np.ndarray, prefijo: str, clave_q: str) -> dict[str, np.ndarray]:
    """Filas de A_h* o B_h* en columnas, ordenadas por (h, origen). Se descartan las
    filas con y o cuantiles no finitos o sin etiqueta de regimen, para todas las
    capas por igual."""
    detalle = json.loads(RANGOS.read_text(encoding="utf-8"))["detalle"]
    idx = {str(f): i for i, f in enumerate(serie.fecha)}
    cols: dict[str, list] = {k: [] for k in ("h", "o", "y", "anio", "q", "lab")}
    for h in HORIZONTES:
        filas = sorted(((idx[f["origen"]], f) for f in detalle[f"{prefijo}_h{h}"]), key=lambda p: p[0])
        for o, f in filas:
            q = np.sort(np.array(f[clave_q], float))
            if not np.isfinite(f["y"]) or not np.all(np.isfinite(q)) or etiq[o] < 0:
                continue
            assert abs(serie.casos[o + h] - f["y"]) < 1e-9, f"y distinto en {f['origen']} h {h}"
            cols["h"].append(h)
            cols["o"].append(o)
            cols["y"].append(f["y"])
            cols["anio"].append(f["anio"])
            cols["q"].append(q)
            cols["lab"].append(int(etiq[o]))
    b = {k: np.array(v) for k, v in cols.items()}
    b["tgt"] = b["o"] + b["h"]
    b["s"] = puntaje(b["y"], b["q"])
    ultimo = max(serie.fecha[int(t)] for t in b["tgt"]).isoformat()
    assert ultimo < INICIO_PROSPECTIVA, f"hay objetivos de la ventana prospectiva ({ultimo})"
    return b


def preparar(b: dict[str, np.ndarray]) -> dict:
    """Pares pasados de cada fila (indices) por horizonte y acumulados, y la marca
    de fila evaluable (al menos N_MIN pares pasados del mismo horizonte)."""
    n = len(b["y"])
    por_h, todos = [], []
    for i in range(n):
        pasado = b["tgt"] < b["o"][i]
        por_h.append(np.flatnonzero(pasado & (b["h"] == b["h"][i])))
        todos.append(np.flatnonzero(pasado))
    ev = np.array([len(p) >= N_MIN for p in por_h])
    return {"por_h": por_h, "todos": todos, "evaluable": ev}


def calcular_factores(b: dict, prep: dict, capa: str, lab: np.ndarray | None = None):
    """Factor f de cada fila y marca de 'uso su factor propio' (no el de reserva).
    capa: L1, L2 (pares del mismo horizonte) o L1p, L2p (pares de los 8 horizontes)."""
    lab = b["lab"] if lab is None else lab
    pares = prep["todos"] if capa.endswith("p") else prep["por_h"]
    regimen = capa.startswith("L2")
    n = len(b["y"])
    f = np.ones(n)
    propio = np.zeros(n, bool)
    for i in range(n):
        idx = pares[i]
        if len(idx) < N_MIN:
            continue
        f[i] = factor_conforme(b["s"][idx])
        propio[i] = True
        if regimen:
            idx_r = idx[lab[idx] == lab[i]]
            if len(idx_r) >= N_MIN:
                f[i] = factor_conforme(b["s"][idx_r])
            else:
                propio[i] = False
    return f, propio


# --- metricas ---------------------------------------------------------------------


def metricas(b: dict, ev: np.ndarray, lim: dict, ref: dict) -> dict:
    """Cobertura, pinball y ensanchamiento de un limite frente a la referencia L0,
    sobre las filas `ev`."""
    y, h, anio, reg = b["y"][ev], b["h"][ev], b["anio"][ev], b["lab"][ev]
    q = b["q"][ev]
    l, r = lim["l975"][ev], ref["l975"][ev]
    p, p0 = pinball(y, l, NIVEL), pinball(y, r, NIVEL)
    cub = y <= l
    out: dict = {
        "n": int(ev.sum()),
        "cob_total": float(cub.mean()),
        "excedencias_total": int((~cub).sum()),
        "cob_por_h": {int(k): float(cub[h == k].mean()) for k in HORIZONTES if (h == k).any()},
        "cob_por_regimen": {
            int(k): {"n": int((reg == k).sum()), "excedencias": int((~cub[reg == k]).sum()),
                     "cob": float(cub[reg == k].mean())}
            for k in (0, 1, 2) if (reg == k).any()
        },
        "pinball_suma": float(p.sum()),
        "razon_pinball": float(p.sum() / p0.sum()) if p0.sum() > 0 else None,
    }
    rh = {int(k): float(p[h == k].sum() / p0[h == k].sum()) for k in HORIZONTES if (h == k).any() and p0[h == k].sum() > 0}
    ra = {int(k): float(p[anio == k].sum() / p0[anio == k].sum()) for k in sorted(set(anio)) if p0[anio == k].sum() > 0}
    out["razon_pinball_por_h"], out["razon_pinball_por_anio"] = rh, ra
    out["horizontes_mejores"] = int(sum(v < 1.0 for v in rh.values()))
    out["anios_ok"] = int(sum(v <= 1.0 for v in ra.values()))
    out["n_anios"] = len(ra)
    den = q[:, I_Q975] - q[:, I_MED]
    ok = den > 1e-9
    out["ensanch_media_filas"] = float(np.mean((l[ok] - q[ok, I_MED]) / den[ok]))
    out["ensanch_razon_sumas"] = float((l[ok] - q[ok, I_MED]).sum() / den[ok].sum())
    out["ensanch_filas_excluidas"] = int((~ok).sum())
    l9, r9 = lim["l99"][ev], ref["l99"][ev]
    p9, p90 = pinball(y, l9, 0.99), pinball(y, r9, 0.99)
    out["nivel_99"] = {"cob_total": float((y <= l9).mean()),
                       "razon_pinball": float(p9.sum() / p90.sum()) if p90.sum() > 0 else None}
    return out


def cobertura_central_por_regimen(b: dict, ev: np.ndarray) -> dict:
    """Cobertura del intervalo central del 95 % guardado, por regimen (brecha de partida)."""
    y, reg, q = b["y"][ev], b["lab"][ev], b["q"][ev]
    dentro = (y >= q[:, IDX_B95[0]]) & (y <= q[:, IDX_B95[1]])
    return {int(k): {"n": int((reg == k).sum()), "cob95": float(dentro[reg == k].mean())}
            for k in (0, 1, 2) if (reg == k).any()}


def perdidas_por_origen(b: dict, ev: np.ndarray, lim: dict) -> dict[int, dict[int, float]]:
    out: dict[int, dict[int, float]] = {}
    perd = pinball(b["y"], lim["l975"], NIVEL)
    for i in np.flatnonzero(ev):
        out.setdefault(int(b["o"][i]), {})[int(b["h"][i])] = float(perd[i])
    return out


def dm_origenes(p_x: dict, p_y: dict) -> dict | None:
    """Diebold-Mariano sobre la diferencia de pinball sumada en los 8 horizontes por
    origen (solo origenes con los 8 evaluables); Newey-West de rezago 7 y HLN, h = 8."""
    origenes = sorted(o for o in p_x if len(p_x[o]) == len(HORIZONTES) and o in p_y)
    d = np.array([sum(p_x[o].values()) - sum(p_y[o].values()) for o in origenes])
    return sel.dm(d, max(HORIZONTES))


def holm(ps: dict[str, float]) -> dict[str, float]:
    orden = sorted(ps, key=ps.get)
    out, previo = {}, 0.0
    for rango, k in enumerate(orden):
        previo = max(previo, min(1.0, (len(ps) - rango) * ps[k]))
        out[k] = previo
    return out


def condiciones(m: dict) -> dict[str, bool]:
    alto = m["cob_por_regimen"].get(ALTO)
    return {
        "cob_tercio_alto": bool(alto and alto["cob"] >= COB_ALTO_MIN),
        "cob_total": COB_TOTAL[0] <= m["cob_total"] <= COB_TOTAL[1],
        "pinball": bool(m["razon_pinball"] is not None and m["razon_pinball"] <= 1.0
                        and m["horizontes_mejores"] >= HORIZ_MEJOR_MIN),
        "anios": m["anios_ok"] >= ANIOS_OK_MIN,
        "ensanchamiento": m["ensanch_media_filas"] <= ENSANCH_MAX,
    }


# --- parte A y extension E1 ---------------------------------------------------------


def barajar(b: dict, prep: dict, ev: np.ndarray, capa_regimen: str, capa_base: str, lim_base: dict) -> dict:
    """Control negativo: la misma permutacion de etiquetas entre los origenes para los
    8 horizontes. Devuelve la razon de pinball de la capa por regimen contra la base."""
    rng = np.random.default_rng(SEMILLA)
    origenes = np.unique(b["o"])
    etiq_o = {int(o): int(b["lab"][b["o"] == o][0]) for o in origenes}
    valores = np.array([etiq_o[int(o)] for o in origenes])
    base = pinball(b["y"], lim_base["l975"], NIVEL)[ev].sum()
    razones = []
    for _ in range(BARAJADOS):
        nuevo = dict(zip(origenes, rng.permutation(valores)))
        lab = np.array([nuevo[o] for o in b["o"]])
        f, _p = calcular_factores(b, prep, capa_regimen, lab)
        razones.append(pinball(b["y"], limites(b["q"], f)["l975"], NIVEL)[ev].sum() / base)
    razones = np.array(razones)
    return {"razones": razones, "p10": float(np.percentile(razones, PERCENTIL_BARAJADO)),
            "mediana": float(np.median(razones))}


def evaluar_familia(b: dict, prep: dict, capas: tuple[str, str], etiqueta: str) -> dict:
    """capas = (global, por regimen): ('L1', 'L2') o ('L1p', 'L2p')."""
    ev = prep["evaluable"]
    g, r = capas
    ref = limites(b["q"], np.ones(len(b["y"])))
    lims, propios = {}, {}
    for c in capas:
        f, propio = calcular_factores(b, prep, c)
        lims[c], propios[c] = limites(b["q"], f), propio
    res: dict = {"filas_evaluables": int(ev.sum()), "capas": {},
                 "cobertura_central_95_por_regimen": cobertura_central_por_regimen(b, ev)}
    res["capas"]["L0"] = metricas(b, ev, ref, ref)
    for c in capas:
        m = metricas(b, ev, lims[c], ref)
        m["fraccion_factor_propio"] = float(propios[c][ev].mean())
        m["condiciones"] = condiciones(m)
        m["pasa"] = bool(all(m["condiciones"].values()))
        res["capas"][c] = m
    pe = {c: perdidas_por_origen(b, ev, lims[c]) for c in capas}
    pe["L0"] = perdidas_por_origen(b, ev, ref)
    dms = {f"{g}_vs_L0": dm_origenes(pe[g], pe["L0"]), f"{r}_vs_L0": dm_origenes(pe[r], pe["L0"]),
           f"{r}_vs_{g}": dm_origenes(pe[r], pe[g])}
    ps = {k: v["p"] for k, v in dms.items() if v}
    aj = holm(ps)
    for k, v in dms.items():
        if v:
            v["p_holm"] = aj[k]
    res["diebold_mariano"] = dms
    # L2 contra L1 y control de barajado
    p_g = pinball(b["y"], lims[g]["l975"], NIVEL)[ev].sum()
    p_r = pinball(b["y"], lims[r]["l975"], NIVEL)[ev].sum()
    baraj = barajar(b, prep, ev, r, g, lims[g])
    razon_rg = float(p_r / p_g)
    res["regimen_vs_global"] = {
        "razon_pinball": razon_rg, "barajado_p10": baraj["p10"], "barajado_mediana": baraj["mediana"],
        "fraccion_barajados_mejores_o_iguales": float((baraj["razones"] <= razon_rg).mean()),
        "aporta": bool(razon_rg < RAZON_L2_L1 and razon_rg < baraj["p10"]),
    }
    pasan = [c for c in capas if res["capas"][c]["pasa"]]
    if g in pasan and r in pasan:
        res["elegida"] = r if res["regimen_vs_global"]["aporta"] else g
    elif pasan:
        res["elegida"] = pasan[0]
    else:
        res["elegida"] = None
    # solo el ensanchamiento incumplido, en alguna de las dos (condicion de la extension E1)
    res["solo_falla_ensanchamiento"] = [
        c for c in capas
        if [k for k, v in res["capas"][c]["condiciones"].items() if not v] == ["ensanchamiento"]
    ]
    print(f"\n[{etiqueta}] filas evaluables: {int(ev.sum())}")
    for c in ("L0",) + tuple(capas):
        m = res["capas"][c]
        alto = m["cob_por_regimen"].get(ALTO, {})
        print(f"  {c:4s} cob {m['cob_total']:.3f} | tercio alto {alto.get('cob', float('nan')):.3f} "
              f"(n {alto.get('n')}, exced. {alto.get('excedencias')}) | razón pinball {m['razon_pinball']:.3f} "
              f"| h mejores {m['horizontes_mejores']}/8 | años ok {m['anios_ok']}/{m['n_anios']} "
              f"| ensanch {m['ensanch_media_filas']:.2f} | propio {m.get('fraccion_factor_propio', float('nan')):.2f}"
              + (f" | pasa {m['pasa']} {[k for k, v in m['condiciones'].items() if not v]}" if c != "L0" else ""))
    print(f"  {r}/{g}: razón {razon_rg:.3f}, barajado p10 {baraj['p10']:.3f}, aporta {res['regimen_vs_global']['aporta']}")
    print(f"  elegida: {res['elegida']} | solo falla ensanchamiento: {res['solo_falla_ensanchamiento']}")
    return res


def tabla_fija(bA: dict, capa: str) -> dict:
    """Factores ajustados una sola vez con todos los pares de A: por horizonte (L1) o
    por horizonte y regimen (L2); un solo horizonte agrupado en las capas con p."""
    agrupado = capa.endswith("p")
    regimen = capa.startswith("L2")
    tabla = {}
    for h in (0,) if agrupado else HORIZONTES:
        base = np.ones(len(bA["y"]), bool) if agrupado else bA["h"] == h
        f_g = factor_conforme(bA["s"][base])
        for r in (0, 1, 2) if regimen else (None,):
            if r is None:
                tabla[(h, None)] = f_g
                continue
            sr = bA["s"][base & (bA["lab"] == r)]
            tabla[(h, r)] = factor_conforme(sr) if len(sr) >= N_MIN else f_g
    return tabla


def aplicar_tabla(b: dict, tabla: dict, capa: str) -> np.ndarray:
    agrupado, regimen = capa.endswith("p"), capa.startswith("L2")
    return np.array([tabla[(0 if agrupado else int(h), int(r) if regimen else None)]
                     for h, r in zip(b["h"], b["lab"])])


def parte_b(serie: Serie, etiq: np.ndarray, capa: str, bA: dict) -> dict:
    tabla = tabla_fija(bA, capa)
    res: dict = {"capa": capa, "tabla": {f"{k[0]}_{k[1]}": v for k, v in tabla.items()}, "modelos": {}}
    print(f"\n[parte B] capa {capa}, tabla fija ajustada en A (dentro de muestra en 2025-2026-S37)")
    for nombre, clave in (("C", "q_C_R0"), ("M0", "q_R0")):
        bB = cargar_bloque(serie, etiq, "B", clave)
        ev = bB["anio"] >= 2025
        ref = limites(bB["q"], np.ones(len(bB["y"])))
        f = aplicar_tabla(bB, tabla, capa)
        m = metricas(bB, ev, limites(bB["q"], f), ref)
        m["cobertura_central_95_por_regimen"] = cobertura_central_por_regimen(bB, ev)
        pe_x, pe_y = perdidas_por_origen(bB, ev, limites(bB["q"], f)), perdidas_por_origen(bB, ev, ref)
        m["diebold_mariano_vs_L0"] = dm_origenes(pe_x, pe_y)
        # descriptivo: la misma capa con calibracion hacia adelante dentro de B
        prep = preparar(bB)
        ev_w = ev & prep["evaluable"]
        fw, propio = calcular_factores(bB, prep, capa)
        mw = metricas(bB, ev_w, limites(bB["q"], fw), ref)
        mw["fraccion_factor_propio"] = float(propio[ev_w].mean())
        res["modelos"][nombre] = {"tabla_fija": m, "hacia_adelante_descriptivo": mw,
                                  "L0": metricas(bB, ev, ref, ref)}
        if nombre == "C":
            m["condiciones"] = {
                "cob_total": B_COB_TOTAL[0] <= m["cob_total"] <= B_COB_TOTAL[1],
                "ensanchamiento": m["ensanch_media_filas"] <= ENSANCH_MAX,
                "pinball": bool(m["razon_pinball"] is not None and m["razon_pinball"] <= B_RAZON_MAX),
            }
            m["aplicable"] = bool(all(m["condiciones"].values()))
        alto = m["cob_por_regimen"].get(ALTO, {})
        print(f"  {nombre}: cob {m['cob_total']:.3f} | tercio alto {alto.get('cob', float('nan')):.3f} (n {alto.get('n')}) "
              f"| razón pinball {m['razon_pinball']:.3f} | ensanch {m['ensanch_media_filas']:.2f}"
              + (f" | aplicable {m['aplicable']} {[k for k, v in m['condiciones'].items() if not v]}" if nombre == "C" else "")
              + f" | L0 cob {res['modelos'][nombre]['L0']['cob_total']:.3f}"
              + f" | hacia adelante: cob {mw['cob_total']:.3f}, razón {mw['razon_pinball']:.3f}, propio {mw['fraccion_factor_propio']:.2f}")
    return res


# --- controles -----------------------------------------------------------------------


def controles(serie: Serie, etiq: np.ndarray) -> dict:
    guardado = json.loads(RANGOS.read_text(encoding="utf-8"))
    detalle = guardado["detalle"]
    out: dict = {"cobertura": [], "ok": True}
    for prefijo, clave_q, tablas, clave_tabla, filtro in (
        ("A", "q_R0", guardado["fase_A"]["tablas"], "R0", lambda f: True),
        ("B", "q_C_R0", guardado["fase_B"]["tablas"], "C_R0", lambda f: f["anio"] >= 2025),
    ):
        for h in HORIZONTES:
            filas = [f for f in detalle[f"{prefijo}_h{h}"] if filtro(f)]
            y = np.array([f["y"] for f in filas], float)
            qs = np.array([f[clave_q] for f in filas], float)
            ref = tablas[str(h)][clave_tabla]
            c50 = float(cobertura(y, qs, *IDX_B50))
            c95 = float(cobertura(y, qs, *IDX_B95))
            d = max(abs(c50 - ref["cobertura_50"]), abs(c95 - ref["cobertura_95"]))
            ok = d <= TOL_COBERTURA and len(filas) == ref["n"]
            out["cobertura"].append({"bloque": prefijo, "h": h, "n": len(filas), "n_guardado": ref["n"],
                                     "dif_max": d, "ok": ok})
            out["ok"] &= ok
    # L2 con todas las filas en un mismo regimen reproduce L1
    bA = cargar_bloque(serie, etiq, "A", "q_R0")
    prep = preparar(bA)
    f1, _ = calcular_factores(bA, prep, "L1")
    f2, _ = calcular_factores(bA, prep, "L2", np.zeros(len(bA["y"]), int))
    out["l2_un_regimen_igual_l1"] = bool(np.array_equal(f1, f2))
    out["ok"] &= out["l2_un_regimen_igual_l1"]
    # las etiquetas no usan datos posteriores: truncar la serie no las cambia
    z = sel.historia(serie, K_SUAVIZADO).z
    corte = int(0.8 * len(z))
    out["etiquetas_causales"] = bool(np.array_equal(etiquetas_desde_z(z)[:corte], etiquetas_desde_z(z[:corte])))
    out["ok"] &= out["etiquetas_causales"]
    print("controles: cobertura guardada vs recalculada, diferencia máxima",
          f"{max(c['dif_max'] for c in out['cobertura']):.4f}", "| n iguales:", all(c["n"] == c["n_guardado"] for c in out["cobertura"]))
    print("  L2 con un régimen = L1:", out["l2_un_regimen_igual_l1"], "| etiquetas causales:", out["etiquetas_causales"])
    print("  CONTROLES", "OK" if out["ok"] else "FALLAN")
    return out


def diagnostico(serie: Serie, etiq: np.ndarray) -> dict:
    """Exploratorio, despues de ver la parte A. No es un candidato ni decide nada."""
    b = cargar_bloque(serie, etiq, "A", "q_R0")
    prep = preparar(b)
    ev = prep["evaluable"]
    n = len(b["y"])
    ref = limites(b["q"], np.ones(n))
    out: dict = {}
    s = b["s"]
    out["scores_cuantiles_50_90_975_99_max"] = [float(v) for v in np.quantile(s, [0.5, 0.9, 0.975, 0.99, 1.0])]
    f1, _ = calcular_factores(b, prep, "L1")
    out["factor_l1_por_h"] = {int(h): {"p10": float(np.quantile(f1[ev & (b["h"] == h)], 0.1)),
                                       "mediana": float(np.median(f1[ev & (b["h"] == h)])),
                                       "max": float(f1[ev & (b["h"] == h)].max())} for h in (1, 4, 8)}
    # cota: factor al nivel dado de los scores de TODAS las filas evaluables (no causal)
    cota = {}
    for nivel in (0.975, 0.95, 0.90):
        for nombre, por_regimen in (("global_por_h", False), ("por_h_y_regimen", True)):
            f = np.ones(n)
            for h in HORIZONTES:
                for r in (0, 1, 2) if por_regimen else (None,):
                    msk = b["h"] == h if r is None else (b["h"] == h) & (b["lab"] == r)
                    f[msk] = max(1.0, float(np.quantile(s[ev & msk], nivel)))
            m = metricas(b, ev, limites(b["q"], f), ref)
            cota[f"{nombre}_nivel_{nivel}"] = {k: m[k] for k in ("cob_total", "razon_pinball", "ensanch_media_filas",
                                                                  "anios_ok", "horizontes_mejores")}
            cota[f"{nombre}_nivel_{nivel}"]["cob_tercio_alto"] = m["cob_por_regimen"][ALTO]["cob"]
    out["cota_dentro_de_muestra"] = cota
    # excedencias de L0 por tercio del tamano de la mediana
    y, med, lim = b["y"][ev], b["q"][ev, I_MED], ref["l975"][ev]
    perd = pinball(y, lim, NIVEL)
    cortes = np.quantile(med, [1 / 3, 2 / 3])
    tam = {}
    for nombre, msk in (("baja", med <= cortes[0]), ("media", (med > cortes[0]) & (med <= cortes[1])), ("alta", med > cortes[1])):
        exc = msk & (y > lim)
        tam[nombre] = {"n": int(msk.sum()), "excedencias": int(exc.sum()), "tasa": float(exc.sum() / msk.sum()),
                       "parte_pinball": float(perd[msk].sum() / perd.sum()),
                       "y_sobre_mediana_en_excedencias": float(np.median(y[exc] / med[exc]))}
    out["excedencias_por_tamano_mediana"] = {"cortes_casos": [float(c) for c in cortes], **tam}
    for k, v in cota.items():
        print(f"  cota {k:34s} cob {v['cob_total']:.3f} (alto {v['cob_tercio_alto']:.3f}) razón pinball {v['razon_pinball']:.3f} ensanch {v['ensanch_media_filas']:.2f}")
    print("  excedencias por tamaño:", {k: (v["excedencias"], round(v["tasa"], 3), round(v["parte_pinball"], 2)) for k, v in tam.items()})
    return out


# --- ejecucion -------------------------------------------------------------------------


def _guardar(clave: str, valor: dict) -> None:
    previo = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {}
    previo[clave] = valor
    SALIDA.write_text(json.dumps(previo, default=_a_json, ensure_ascii=False), encoding="utf-8")
    print(f"-> {SALIDA} [{clave}]")


def _a_json(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modo = ap.add_mutually_exclusive_group(required=True)
    for nombre in ("control", "parte-a", "extension-e1", "parte-b", "diagnostico"):
        modo.add_argument(f"--{nombre}", action="store_true")
    args = ap.parse_args()
    conn = get_connection()
    try:
        serie = tab.cargar_serie_mixta(conn)
    finally:
        conn.close()
    etiq = etiquetas_regimen(serie)
    print(f"serie mixta: {serie.T} semanas; etiquetas de régimen: "
          f"{ {int(k): int((etiq == k).sum()) for k in (-1, 0, 1, 2)} }")
    ctrl = controles(serie, etiq)
    if args.control:
        _guardar("control", ctrl)
        return
    if not ctrl["ok"]:
        raise SystemExit("los controles fallan: el experimento se detiene (protocolo)")

    if args.diagnostico:
        _guardar("exploratorio", diagnostico(serie, etiq))
        return

    if args.parte_a or args.extension_e1:
        bA = cargar_bloque(serie, etiq, "A", "q_R0")
        prep = preparar(bA)
        if args.parte_a:
            res = evaluar_familia(bA, prep, ("L1", "L2"), "parte A")
            res["extension_e1_requerida"] = bool(res["elegida"] is None and res["solo_falla_ensanchamiento"])
            print(f"  extensión E1 requerida: {res['extension_e1_requerida']}")
            _guardar("parte_a", res)
        else:
            previo = json.loads(SALIDA.read_text(encoding="utf-8")).get("parte_a")
            assert previo and previo["extension_e1_requerida"], "el protocolo no pide la extensión E1"
            _guardar("extension_e1", evaluar_familia(bA, prep, ("L1p", "L2p"), "extensión E1"))
        return

    guardado = json.loads(SALIDA.read_text(encoding="utf-8"))
    capa = (guardado.get("extension_e1") or {}).get("elegida") or guardado["parte_a"]["elegida"]
    if capa is None:
        raise SystemExit("ninguna capa elegida en la parte A: la parte B no corre (protocolo)")
    bA = cargar_bloque(serie, etiq, "A", "q_R0")
    _guardar("parte_b", parte_b(serie, etiq, capa, bA))


if __name__ == "__main__":
    main()
