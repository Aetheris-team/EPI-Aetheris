"""
Fase 2/3 de la mejora del predictor para la serie del tablero: el cambio de anio
(docs/experimentos/experimento-nowcast-cambio-anio.md, protocolo del 2026-10-03,
commiteado antes de escribir este script).

  --control    controles de reproduccion (q_T y q_C_R0 guardados) y conteos por tramo;
               se detiene si fallan.
  --parte-a    el salto del cambio de anio en la serie mixta, contra la historia
               (descriptiva, sin predictor).
  --parte-b    cobertura de C, M0 y T por tramo de semana objetivo (FA, V, R) en la
               historia (2019, 2021 a 2024) y criterio B1, B2, B3.
  --parte-c    regla de ensanchamiento por calendario, solo para el tramo que cumpla B.

Todo sale de cuantiles de M0 guardados en rangos.json: no reentrena nada. Ninguna
decision usa semanas objetivo desde 2026-S38 (prueba prospectiva congelada).

Uso:
    cd backend/ingestion
    POSTGRES_HOST=localhost nice -n 10 ../.venv/bin/python experimento_nowcast_cambio_anio.py --control
    POSTGRES_HOST=localhost nice -n 10 ../.venv/bin/python experimento_nowcast_cambio_anio.py --parte-a
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np

import experimento_nowcast_banda_riesgo as br
import experimento_nowcast_mejora as mej
import experimento_nowcast_peso_horizonte as ph
import experimento_nowcast_tablero as tab
import experimento_nowcast_tendencia_seleccion as sel
from experimento_nowcast_corto_plazo import IDX_MEDIANA, Serie
from nowcast_estimacion_dengue import HORIZONTES, IDX_B50, IDX_B95

from db import get_connection

# --- parametros fijados en el protocolo -------------------------------------

ANIOS_VALIDACION = ph.ANIOS_VALIDACION  # 2019, 2021, 2022, 2023
ANIOS_HISTORIA = ANIOS_VALIDACION + (2024,)
W_VIGENTE = ph.W_VIGENTE
GRUPOS = {**sel.GRUPOS, "todos": tuple(HORIZONTES)}
SEMANAS_FA = (1, 2, 3)
TRAMOS = ("FA", "V", "R")
MODELOS = ("C", "M0", "T")
# parte A
CAMBIOS_A = tuple(range(2015, 2027))  # 2014 a 2015 ... 2025 a 2026
ANIOS_NULA = tuple(range(2015, 2026))
SEMANAS_PRE = (47, 48, 49, 50)
SEMANAS_POST = (1, 2, 3)
VENTANA_NULA = (4, 38)  # semana de inicio de la ventana de 9 semanas, dentro de 4 a 46
PERCENTIL_FUERA = 0.99
# parte B
B1_COBERTURA_MAX = 0.85
B2_P_MAX = 0.10
B3_LADO_MIN = 0.75
N_PERMUTACIONES = 2000
SEMILLA = 20261003
# parte C
F_GRILLA = (1.25, 1.5, 2.0)
COBERTURA_OBJETIVO = 0.93
COSTO_WIS_MAX = 1.005
WIS_TRAMO_H1_MAX = 1.05
INICIO_PROSPECTIVA = "2026-09-20"

RAIZ = Path(__file__).resolve().parents[2] / "docs" / "agentes" / "mejora-predictor" / "resultados-nuevos"
SALIDA = RAIZ / "cambio_anio.json"


# --- parte A: el salto del cambio de anio --------------------------------------


def indice_semanas(serie: Serie) -> dict[tuple[int, int], int]:
    return {(int(a), int(w)): k for k, (a, w) in enumerate(zip(serie.anio, serie.semana))}


def media_semanas(casos: np.ndarray, idx: dict, anio: int, semanas: tuple[int, ...]) -> float:
    ks = [idx.get((anio, w)) for w in semanas]
    if any(k is None for k in ks):
        return float("nan")
    v = casos[ks]
    return float(np.mean(v)) if np.all(np.isfinite(v)) else float("nan")


def estadistico_d(casos: np.ndarray, idx: dict, anio: int) -> float:
    """log1p(media de las semanas 1 a 3 del anio) menos log1p(media de las semanas
    47 a 50 del anio anterior)."""
    pre = media_semanas(casos, idx, anio - 1, SEMANAS_PRE)
    post = media_semanas(casos, idx, anio, SEMANAS_POST)
    return float(np.log1p(post) - np.log1p(pre))


def referencia_nula(casos: np.ndarray, idx: dict, anios: tuple[int, ...]) -> np.ndarray:
    """Misma forma que D (cuatro semanas, hueco de dos, tres semanas), con las nueve
    semanas dentro de las semanas 4 a 46 de un mismo anio."""
    out = []
    for a in anios:
        for w in range(VENTANA_NULA[0], VENTANA_NULA[1] + 1):
            pre = media_semanas(casos, idx, a, tuple(range(w, w + 4)))
            post = media_semanas(casos, idx, a, tuple(range(w + 6, w + 9)))
            d = np.log1p(post) - np.log1p(pre)
            if np.isfinite(d):
                out.append(d)
    return np.array(out)


def percentil(valor: float, ref: np.ndarray) -> float:
    return float(np.mean(ref <= valor))


def parte_a(serie: Serie, reglas: sel.Reglas) -> dict:
    idx = indice_semanas(serie)
    out: dict = {}
    for nombre, casos in (("cruda", serie.casos), ("historia_T", reglas.s.casos)):
        ref = referencia_nula(casos, idx, ANIOS_NULA)
        filas = {}
        for a in CAMBIOS_A:
            d = estadistico_d(casos, idx, a)
            filas[a] = {"D": d, "percentil": percentil(d, ref) if np.isfinite(d) else None}
        previos = [filas[a]["D"] for a in CAMBIOS_A if a < 2026 and np.isfinite(filas[a]["D"])]
        pct = [filas[a]["percentil"] for a in CAMBIOS_A if a < 2026 and filas[a]["percentil"] is not None]
        d26 = filas[2026]["D"]
        fuera = bool(np.isfinite(d26) and d26 > max(previos) and filas[2026]["percentil"] > PERCENTIL_FUERA)
        out[nombre] = {
            "cambios": filas, "n_referencia": int(len(ref)),
            "referencia_p05_p50_p95": [float(x) for x in np.quantile(ref, [0.05, 0.5, 0.95])],
            "positivos_2015_2025": int(sum(d > 0 for d in previos)),
            "negativos_2015_2025": int(sum(d < 0 for d in previos)),
            "mediana_percentiles_2015_2025": float(np.median(pct)),
            "maximo_D_2015_2025": float(max(previos)),
            "fuera_de_lo_visto_2026": fuera,
        }
        print(f"\nParte A, serie {nombre}: referencia nula n = {len(ref)}, "
              f"p05/p50/p95 = {np.round(out[nombre]['referencia_p05_p50_p95'], 2).tolist()}")
        for a in CAMBIOS_A:
            f = filas[a]
            p = "s/d" if f["percentil"] is None else f"{f['percentil']:.2f}"
            print(f"  {a - 1} a {a}: D = {f['D']:+.3f}  percentil {p}")
        print(f"  signos 2015-2025: {out[nombre]['positivos_2015_2025']} positivos, {out[nombre]['negativos_2015_2025']} negativos; "
              f"mediana de percentiles {out[nombre]['mediana_percentiles_2015_2025']:.2f}; "
              f"2026 fuera de lo visto: {fuera}")
    return out


# --- tramos y datos de la historia ---------------------------------------------


def mascaras_tramos(semana: np.ndarray, fecha: list[date]) -> dict[str, np.ndarray]:
    """FA: semana epidemiologica 1 a 3. V: marca de vacaciones. R: ninguna de las dos."""
    fa = np.isin(semana, SEMANAS_FA)
    v = np.array([mej.marca_vacaciones(f) == 1.0 for f in fecha], dtype=bool)
    return {"FA": fa, "V": v, "R": ~fa & ~v}


def _bloque(serie: Serie, nombre: str, h: int, o: np.ndarray, y: np.ndarray, q_m0: np.ndarray, q_t: np.ndarray) -> dict:
    q_m0, q_t = np.sort(q_m0, axis=1), np.sort(q_t, axis=1)
    q_c = np.array([ph.mezcla(m, t, W_VIGENTE) for m, t in zip(q_m0, q_t)])
    tgt = o + h
    return {"h": np.full(len(o), h), "tgt": tgt, "anio": serie.anio[tgt], "semana": serie.semana[tgt],
            "fecha": [serie.fecha[k] for k in tgt], "bloque": np.array([nombre] * len(o)),
            "y": y, "M0": q_m0, "T": q_t, "C": np.sort(q_c, axis=1)}


def pares_de(serie: Serie, reglas: sel.Reglas, val: dict, b: dict, bloque: str) -> dict:
    """Pares origen-horizonte de un bloque: 'val' (2019, 2021 a 2023), 'H1' (2024) o 'H2'
    (2025 a 2026-S37), con los cuantiles de M0, T y C."""
    partes = []
    for h in HORIZONTES:
        if bloque == "val":
            for a in ANIOS_VALIDACION:
                d = val[h].get(a)
                if d is not None:
                    partes.append(_bloque(serie, bloque, h, d["o"], d["y"], d["q_m0"], d["q_t"]))
        else:
            d = b[bloque][h]
            q_t = np.array([reglas.cuantiles(int(o), h, *sel.VIGENTE) for o in d["o"]])
            partes.append(_bloque(serie, bloque, h, d["o"], d["y"], d["q_m0"], q_t))
    return concatenar(partes)


def concatenar(partes: list[dict]) -> dict:
    out = {}
    for k in partes[0]:
        out[k] = (sum((p[k] for p in partes), []) if isinstance(partes[0][k], list)
                  else np.concatenate([p[k] for p in partes]))
    return out


def mascara_horizontes(P: dict, hs: tuple[int, ...]) -> np.ndarray:
    return np.isin(P["h"], hs)


# --- parte B: cobertura por tramo ------------------------------------------------


def lados_fallo(y: np.ndarray, q: np.ndarray) -> tuple[int, int]:
    """(fallos por arriba, fallos por abajo) del rango del 95 %."""
    return int(np.sum(y > q[:, IDX_B95[1]])), int(np.sum(y < q[:, IDX_B95[0]]))


def metricas_modelo(P: dict, modelo: str, m: np.ndarray) -> dict:
    n = int(m.sum())
    if n == 0:
        return {"n_pares": 0}
    y, q = P["y"][m], P[modelo][m]
    arriba, abajo = lados_fallo(y, q)
    cob50 = np.mean((y >= q[:, IDX_B50[0]]) & (y <= q[:, IDX_B50[1]]))
    err = np.abs(np.log1p(q[:, IDX_MEDIANA]) - np.log1p(y))
    return {"n_pares": n, "n_semanas": int(len(np.unique(P["tgt"][m]))),
            "cob95": float(ph.dentro95(y, q).mean()), "cob50": float(cob50),
            "arriba": arriba, "abajo": abajo, "error_mediana": float(err.mean())}


def p_permutacion(cubre: np.ndarray, tgt: np.ndarray, anio: np.ndarray, mascara: np.ndarray,
                  semilla: int, n_perm: int = N_PERMUTACIONES) -> dict:
    """Prueba a una cola: cobertura agrupada del tramo contra la de sortear, en cada anio,
    tantas semanas objetivo como tiene el tramo. p = fraccion de sorteos con cobertura
    menor o igual que la observada."""
    observada = float(cubre[mascara].mean())
    semanas = np.unique(tgt)
    suma = np.array([cubre[tgt == s].sum() for s in semanas], float)
    cuenta = np.array([(tgt == s).sum() for s in semanas], float)
    anio_s = np.array([anio[tgt == s][0] for s in semanas])
    en_tramo = np.array([mascara[tgt == s].any() for s in semanas])
    por_anio = {int(a): (np.flatnonzero(anio_s == a), int(en_tramo[anio_s == a].sum())) for a in np.unique(anio_s)}
    rng = np.random.default_rng(semilla)
    cob = np.empty(n_perm)
    for i in range(n_perm):
        tot, n = 0.0, 0.0
        for pos, k in por_anio.values():
            if k:
                elegidas = rng.choice(pos, size=k, replace=False)
                tot += suma[elegidas].sum()
                n += cuenta[elegidas].sum()
        cob[i] = tot / n
    return {"cob_observada": observada, "p": float(np.mean(cob <= observada + 1e-12)),
            "cob_permutada_media": float(cob.mean()), "n_permutaciones": n_perm,
            "semanas_del_tramo_por_anio": {a: k for a, (_, k) in por_anio.items()}}


def condiciones_b(cob: float, p_ajustado: float, arriba: int, abajo: int) -> dict:
    fallos = arriba + abajo
    lado = None if fallos == 0 else ("arriba" if arriba >= abajo else "abajo")
    parte = None if fallos == 0 else max(arriba, abajo) / fallos
    b1 = bool(cob <= B1_COBERTURA_MAX)
    b2 = bool(p_ajustado <= B2_P_MAX)
    b3 = bool(parte is not None and parte >= B3_LADO_MIN)
    return {"B1": b1, "B2": b2, "B3": b3, "cumple": b1 and b2 and b3, "lado": lado, "parte_del_lado": parte}


def _celda(m: dict) -> str:
    if m["n_pares"] == 0:
        return "sin pares"
    return f"{m['cob95']:.3f} ({m['n_pares']}; {m['n_semanas']}; {m['arriba']}/{m['abajo']})"


def parte_b(P: dict) -> dict:
    masc = mascaras_tramos(P["semana"], P["fecha"])
    out: dict = {"tramos_n_pares": {t: int(masc[t].sum()) for t in TRAMOS}, "tabla": {}}
    for modelo in MODELOS:
        out["tabla"][modelo] = {}
        for g, hs in GRUPOS.items():
            mh = mascara_horizontes(P, hs)
            fila = {t: metricas_modelo(P, modelo, masc[t] & mh) for t in TRAMOS}
            r = fila["R"].get("error_mediana")
            for t in ("FA", "V"):
                if r and fila[t].get("error_mediana") is not None:
                    fila[t]["razon_error_vs_R"] = fila[t]["error_mediana"] / r
            out["tabla"][modelo][g] = fila
    print("\nParte B, cobertura del 95 % (pares; semanas) por modelo, tramo y grupo de horizontes")
    for modelo in MODELOS:
        for g in GRUPOS:
            f = out["tabla"][modelo][g]
            cel = [f"{t}: {_celda(f[t])}" for t in TRAMOS]
            print(f"  {modelo:>2} {g:>5}  " + "  ".join(cel))
    cubre = ph.dentro95(P["y"], P["C"])
    ps, perm = {}, {}
    for i, t in enumerate(("FA", "V")):
        perm[t] = p_permutacion(cubre, P["tgt"], P["anio"], masc[t], SEMILLA + i)
        ps[t] = perm[t]["p"]
    ajustados = br.holm(ps)
    out["decision_C"] = {}
    for t in ("FA", "V"):
        m = out["tabla"]["C"]["todos"][t]
        out["decision_C"][t] = {**condiciones_b(m["cob95"], ajustados[t], m["arriba"], m["abajo"]),
                                "cob95": m["cob95"], "p_crudo": ps[t], "p_holm": ajustados[t],
                                "permutacion": perm[t]}
        print(f"  decision C, tramo {t}: cob95 {m['cob95']:.3f}, p {ps[t]:.3f} (Holm {ajustados[t]:.3f}), "
              f"fallos {m['arriba']}/{m['abajo']} -> {json.dumps({k: out['decision_C'][t][k] for k in ('B1', 'B2', 'B3', 'cumple')})}")
    out["tramos_que_cumplen"] = [t for t in ("FA", "V") if out["decision_C"][t]["cumple"]]
    print("  tramos que cumplen B:", out["tramos_que_cumplen"] or "ninguno")
    return out


# --- parte C: ensanchamiento por calendario ----------------------------------------


def ensanchar(q: np.ndarray, f: float, lado: str) -> np.ndarray:
    """Aleja de la mediana, en log1p, los cuantiles de un lado; la mediana y el otro
    lado no cambian."""
    q = np.sort(np.atleast_2d(np.asarray(q, float)), axis=1)
    z = np.log1p(q)
    zm = z[:, IDX_MEDIANA: IDX_MEDIANA + 1]
    out = z.copy()
    if lado == "arriba":
        out[:, IDX_MEDIANA + 1:] = zm + f * (z[:, IDX_MEDIANA + 1:] - zm)
    elif lado == "abajo":
        out[:, :IDX_MEDIANA] = zm + f * (z[:, :IDX_MEDIANA] - zm)
    else:
        raise ValueError(f"lado desconocido: {lado}")
    return np.clip(np.expm1(out), 0.0, None)


def elegir_f(cob_por_f: dict[float, float]) -> float | None:
    """El menor f con cobertura agrupada del tramo de al menos COBERTURA_OBJETIVO."""
    for f in sorted(cob_por_f):
        if cob_por_f[f] >= COBERTURA_OBJETIVO:
            return f
    return None


def _con_regla(P: dict, mascara: np.ndarray, f: float, lado: str) -> np.ndarray:
    q = P["C"].copy()
    if mascara.any():
        q[mascara] = ensanchar(P["C"][mascara], f, lado)
    return q


def _resumen(P: dict, mascara: np.ndarray, q_cand: np.ndarray) -> dict:
    y = P["y"]
    w_c, w_k = sel.wis_lista(y, P["C"]), sel.wis_lista(y, q_cand)
    m = mascara
    return {"n_tramo": int(m.sum()),
            "cob95_C": float(ph.dentro95(y[m], P["C"][m]).mean()) if m.any() else None,
            "cob95_candidata": float(ph.dentro95(y[m], q_cand[m]).mean()) if m.any() else None,
            "razon_wis_tramo": float(w_k[m].mean() / w_c[m].mean()) if m.any() else None,
            "razon_wis_todos": float(w_k.mean() / w_c.mean())}


def parte_c(P_val: dict, P_h1: dict, P_h2: dict, decision_b: dict) -> dict:
    tramos = decision_b["tramos_que_cumplen"]
    if not tramos:
        print("\nParte C: ningún tramo cumple B; no se corre (protocolo).")
        return {"corre": False, "motivo": "ningun tramo cumple B1, B2 y B3"}
    out: dict = {"corre": True, "tramos": {}}
    for t in tramos:
        lado = decision_b["decision_C"][t]["lado"]
        m_val = mascaras_tramos(P_val["semana"], P_val["fecha"])[t]
        cob_f = {}
        for f in F_GRILLA:
            q = _con_regla(P_val, m_val, f, lado)
            cob_f[f] = float(ph.dentro95(P_val["y"][m_val], q[m_val]).mean())
        f_sel = elegir_f(cob_f)
        res: dict = {"lado": lado, "cobertura_por_f_validacion": {str(k): v for k, v in cob_f.items()},
                     "f": f_sel, "candidata": False}
        print(f"\nParte C, tramo {t}, lado {lado}: cobertura por f en la validación {cob_f}; f = {f_sel}")
        if f_sel is not None:
            r_val = _resumen(P_val, m_val, _con_regla(P_val, m_val, f_sel, lado))
            m1 = mascaras_tramos(P_h1["semana"], P_h1["fecha"])[t]
            r_h1 = _resumen(P_h1, m1, _con_regla(P_h1, m1, f_sel, lado))
            m2 = mascaras_tramos(P_h2["semana"], P_h2["fecha"])[t]
            r_h2 = _resumen(P_h2, m2, _con_regla(P_h2, m2, f_sel, lado))
            cond_b = bool(r_val["razon_wis_todos"] <= COSTO_WIS_MAX)
            cond_c = bool(r_h1["cob95_candidata"] >= r_h1["cob95_C"] and r_h1["razon_wis_tramo"] <= WIS_TRAMO_H1_MAX)
            res.update({"validacion": r_val, "H1": r_h1, "H2_dentro_de_muestra": r_h2,
                        "a_existe_f": True, "b_costo": cond_b, "c_H1": cond_c, "candidata": bool(cond_b and cond_c)})
            print(f"  validación {r_val}\n  H1 {r_h1}\n  H2 (dentro de muestra) {r_h2}\n  candidata: {res['candidata']}")
        out["tramos"][t] = res
    return out


# --- controles y ejecucion ------------------------------------------------------------


def controles(serie: Serie, reglas: sel.Reglas, b: dict, P: dict) -> dict:
    ctrl = sel.controles(serie, b)
    masc = mascaras_tramos(P["semana"], P["fecha"])
    n_pares = {t: int(masc[t].sum()) for t in TRAMOS}
    n_semanas = {t: int(len(np.unique(P["tgt"][masc[t]]))) for t in TRAMOS}
    por_anio_fa = {int(a): int(len(np.unique(P["tgt"][masc["FA"] & (P["anio"] == a)]))) for a in ANIOS_HISTORIA}
    ok = bool(ctrl["pasa"] and all(n_pares[t] > 0 for t in TRAMOS))
    out = {"reproduccion_fase1": ctrl, "pares_por_tramo": n_pares, "semanas_por_tramo": n_semanas,
           "semanas_FA_por_anio": por_anio_fa, "pasa": ok}
    print(f"controles: reproducción de q_T/q_C_R0 {ctrl['pasa']} (dif T {ctrl['dif_max_T']:.2e}, C {ctrl['dif_max_C']:.2e}) | "
          f"pares {n_pares} | semanas {n_semanas} | FA por año {por_anio_fa} -> {'OK' if ok else 'FALLAN'}")
    return out


def _a_json(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _guardar(clave: str, valor: dict) -> None:
    previo = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {}
    previo[clave] = valor
    SALIDA.write_text(json.dumps(previo, default=_a_json, ensure_ascii=False), encoding="utf-8")
    print(f"-> {SALIDA} [{clave}]")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modo = ap.add_mutually_exclusive_group(required=True)
    for nombre in ("control", "parte-a", "parte-b", "parte-c"):
        modo.add_argument(f"--{nombre}", action="store_true")
    args = ap.parse_args()
    conn = get_connection()
    try:
        serie = tab.cargar_serie_mixta(conn)
    finally:
        conn.close()
    reglas = sel.Reglas(sel.historia(serie, sel.K_BASE))
    b = sel.cargar_b(serie)
    assert max(serie.fecha[int(o) + h] for h in HORIZONTES for o in b["H2"][h]["o"]).isoformat() < INICIO_PROSPECTIVA, \
        "hay objetivos de la ventana prospectiva"
    assert serie.fecha[-1].isoformat() < INICIO_PROSPECTIVA, "la serie incluye semanas de la ventana prospectiva"
    val = ph.datos_validacion(serie, reglas)
    P_val, P_h1 = pares_de(serie, reglas, val, b, "val"), pares_de(serie, reglas, val, b, "H1")
    P_hist = concatenar([P_val, P_h1])
    ctrl = controles(serie, reglas, b, P_hist)
    if args.control:
        _guardar("control", ctrl)
        return
    if not ctrl["pasa"]:
        raise SystemExit("los controles fallan: el experimento se detiene (protocolo)")
    if args.parte_a:
        _guardar("parte_a", parte_a(serie, reglas))
        return
    if args.parte_b:
        _guardar("parte_b", parte_b(P_hist))
        return
    guardado = json.loads(SALIDA.read_text(encoding="utf-8"))
    P_h2 = pares_de(serie, reglas, val, b, "H2")
    _guardar("parte_c", parte_c(P_val, P_h1, P_h2, guardado["parte_b"]))


if __name__ == "__main__":
    main()
