"""
Fase 2 (linea D) de la mejora del predictor para la serie del tablero: peso de
M0 por tramo de horizonte en la mezcla C
(docs/experimentos/experimento-nowcast-peso-horizonte.md, protocolo del
2026-10-03, commiteado antes de escribir este script).

  --control        controles de reproduccion (q_T y q_C_R0 guardados) y de identidad
                   de la mezcla; se detiene si fallan.
  --validacion     puntaje de cada peso por tramo con 2019, 2021, 2022 y 2023 (objetivo
                   en la historia suavizada) y regla de cambio.
  --confirmacion   lo elegido en la validacion, contra C con peso 0,5, en 2024 (H1) y en
                   2025 a 2026-S37 (H2, dentro de muestra).
  --extension-e1   centro y ancho por separado, solo para los tramos que el protocolo
                   senala.
  --exploratorio-e1  la misma variante para los tramos que fallaron solo la cobertura en
                   H2 (posterior a la confirmacion; no es la extension firmada).

Todo sale de cuantiles de M0 guardados en rangos.json: no reentrena nada. Ninguna
decision usa semanas objetivo desde 2026-S38 (prueba prospectiva congelada).

Uso:
    cd backend/ingestion
    POSTGRES_HOST=localhost nice -n 10 ../.venv/bin/python experimento_nowcast_peso_horizonte.py --control
    POSTGRES_HOST=localhost nice -n 10 ../.venv/bin/python experimento_nowcast_peso_horizonte.py --validacion
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

import numpy as np

import experimento_nowcast_mejora as mej
import experimento_nowcast_tablero as tab
import experimento_nowcast_tendencia_seleccion as sel
from experimento_nowcast_corto_plazo import IDX_MEDIANA, Serie
from nowcast_estimacion_dengue import HORIZONTES, IDX_B50, IDX_B95

from db import get_connection

# --- parametros fijados en el protocolo -------------------------------------

PESOS = (0.0, 0.25, 0.5, 0.75, 1.0)  # peso de M0
W_VIGENTE = 0.5
GRUPOS = sel.GRUPOS  # h1-2, h3-4, h5-8
ANIOS_VALIDACION = (2019, 2021, 2022, 2023)  # 2018 no tiene M0 y 2020 se excluye
MEJORA_MINIMA = 0.005
ANIOS_MEJOR_MIN = 3  # de 4
COBERTURA_TOLERANCIA = 0.03
RAZON_H2_MAX = 0.99
INICIO_PROSPECTIVA = "2026-09-20"

RAIZ = Path(__file__).resolve().parents[2] / "docs" / "agentes" / "mejora-predictor" / "resultados-nuevos"
RANGOS = RAIZ / "rangos.json"
SALIDA = RAIZ / "peso_m0_por_horizonte.json"

Politica = Callable[[np.ndarray, np.ndarray], np.ndarray]  # (q_m0, q_t) -> q


# --- mezclas ---------------------------------------------------------------------


def mezcla(q_m0: np.ndarray, q_t: np.ndarray, w: float) -> np.ndarray:
    return mej._mezcla(q_m0, q_t, w)


def mezcla_centro_ancho(q_m0: np.ndarray, q_t: np.ndarray, w_centro: float, w_ancho: float) -> np.ndarray:
    """Centro (mediana) con el peso w_centro y desviaciones respecto a la mediana,
    en log1p, con w_ancho. Con w_centro = w_ancho es la mezcla simple."""
    lm, lt = np.log1p(np.sort(q_m0)), np.log1p(np.sort(q_t))
    centro = w_centro * lm[IDX_MEDIANA] + (1 - w_centro) * lt[IDX_MEDIANA]
    desv = w_ancho * (lm - lm[IDX_MEDIANA]) + (1 - w_ancho) * (lt - lt[IDX_MEDIANA])
    return np.clip(np.expm1(np.sort(centro + desv)), 0, None)


def politica_peso(w: float) -> Politica:
    return lambda m, t: mezcla(m, t, w)


def politica_e1(w_centro: float) -> Politica:
    return lambda m, t: mezcla_centro_ancho(m, t, w_centro, W_VIGENTE)


# --- datos ---------------------------------------------------------------------------


def datos_validacion(serie: Serie, reglas: sel.Reglas) -> dict[int, dict[int, dict]]:
    """h -> anio -> {o, y (en la historia suavizada), q_m0, q_t, q_ref}."""
    detalle = json.loads(RANGOS.read_text(encoding="utf-8"))["detalle"]
    idx = {str(f): i for i, f in enumerate(serie.fecha)}
    s7 = reglas.s
    out: dict[int, dict[int, dict]] = {}
    for h in HORIZONTES:
        filas: dict[int, list] = {}
        for f in detalle[f"A_h{h}"]:
            o = idx[f["origen"]]
            a = int(serie.anio[o + h])
            if a in ANIOS_VALIDACION and sel.origen_ok(serie, o, h):
                filas.setdefault(a, []).append((o, np.sort(np.array(f["q_R0"], float))))
        out[h] = {}
        for a, lista in filas.items():
            lista.sort(key=lambda p: p[0])
            os_ = np.array([o for o, _ in lista])
            out[h][a] = {
                "o": os_,
                "y": s7.casos[os_ + h],
                "q_m0": np.array([q for _, q in lista]),
                "q_t": np.array([reglas.cuantiles(int(o), h, *sel.VIGENTE) for o in os_]),
                "q_ref": np.array([reglas.cuantiles(int(o), h, 0.0, sel.V_REF) for o in os_]),
            }
    return out


def dentro95(y: np.ndarray, q: np.ndarray) -> np.ndarray:
    q = np.sort(q, axis=1)
    return (y >= q[:, IDX_B95[0]]) & (y <= q[:, IDX_B95[1]])


# --- validacion y regla de cambio ---------------------------------------------------


def puntajes(val: dict, hs: tuple[int, ...], politicas: dict[str, Politica]) -> dict[str, dict]:
    """Por politica: puntaje promedio de 1 - WIS/WIS(referencia) sobre los horizontes
    `hs` y los anios de validacion (WIS promediado dentro de cada anio), puntaje por
    anio y cobertura del 95 % agrupada."""
    res = {}
    for k, fn in politicas.items():
        por_anio, dentro = {}, []
        for a in ANIOS_VALIDACION:
            sk = []
            for h in hs:
                d = val[h].get(a)
                if d is None:
                    continue
                q = np.array([fn(m, t) for m, t in zip(d["q_m0"], d["q_t"])])
                w = sel.wis_lista(d["y"], q)
                w_ref = sel.wis_lista(d["y"], d["q_ref"])
                sk.append(1 - w.mean() / w_ref.mean())
                dentro += list(dentro95(d["y"], q))
            por_anio[a] = float(np.mean(sk))
        res[k] = {"puntaje": float(np.mean(list(por_anio.values()))), "por_anio": por_anio,
                  "cob95": float(np.mean(dentro))}
    return res


def decidir(res: dict[str, dict], vigente: str) -> dict:
    """Mejor politica admisible (cobertura no mas de 0,03 bajo la vigente) y regla de cambio;
    senala si aplica la extension E1 (mejor sin restriccion pasa la regla pero es inadmisible
    y la mejor admisible no la pasa)."""
    cob_min = res[vigente]["cob95"] - COBERTURA_TOLERANCIA
    adm = [k for k in res if res[k]["cob95"] >= cob_min]

    def regla(k: str) -> dict:
        ganancia = res[k]["puntaje"] - res[vigente]["puntaje"]
        anios = sum(res[k]["por_anio"][a] > res[vigente]["por_anio"][a] for a in ANIOS_VALIDACION)
        return {"ganancia": ganancia, "anios_en_que_supera": int(anios),
                "pasa": bool(k != vigente and ganancia >= MEJORA_MINIMA and anios >= ANIOS_MEJOR_MIN)}

    mejor_adm = max(adm, key=lambda k: res[k]["puntaje"])
    mejor_libre = max(res, key=lambda k: res[k]["puntaje"])
    r_adm, r_libre = regla(mejor_adm), regla(mejor_libre)
    return {"admisibles": adm, "mejor_admisible": mejor_adm, "regla_admisible": r_adm,
            "mejor_sin_restriccion": mejor_libre, "regla_sin_restriccion": r_libre,
            "e1_aplica": bool(r_libre["pasa"] and mejor_libre not in adm and not r_adm["pasa"])}


def validacion(serie: Serie, reglas: sel.Reglas) -> dict:
    val = datos_validacion(serie, reglas)
    print("validación: pares origen-horizonte por año:",
          {a: sum(len(val[h][a]["o"]) for h in HORIZONTES if a in val[h]) for a in ANIOS_VALIDACION})
    out: dict = {}
    politicas = {f"{w}": politica_peso(w) for w in PESOS}
    for g, hs in {**GRUPOS, "todos": HORIZONTES}.items():
        res = puntajes(val, tuple(hs), politicas)
        dec = decidir(res, f"{W_VIGENTE}") if g != "todos" else None
        out[g] = {"horizontes": list(hs), "pesos": res, "decision": dec}
        print(f"\ntramo {g} (h = {list(hs)}): puntaje, cobertura 95 % y puntaje por año")
        for k, r in res.items():
            print(f"   w = {k:>4}: {r['puntaje']:+.4f}  cob {r['cob95']:.3f}  " +
                  " ".join(f"{a}: {x:+.3f}" for a, x in r["por_anio"].items()))
        if dec:
            ra = dec["regla_admisible"]
            print(f"   mejor admisible: w = {dec['mejor_admisible']}, ganancia {ra['ganancia']:+.4f}, "
                  f"supera en {ra['anios_en_que_supera']} de 4 años, regla de cambio: {'SI' if ra['pasa'] else 'no'}"
                  f" | mejor sin restricción: w = {dec['mejor_sin_restriccion']} | E1 aplica: {dec['e1_aplica']}")
    return out


# --- confirmacion en H1 y H2 ------------------------------------------------------------


PoliticaH = Callable[[int, np.ndarray, np.ndarray], np.ndarray]  # (h, q_m0, q_t) -> q


def confirmar(reglas: sel.Reglas, b: dict, hs: tuple[int, ...], cand: PoliticaH) -> dict:
    """Politica candidata contra C con peso 0,5 en H1 y H2, sobre los horizontes `hs`,
    con T sola y M0 sola como contexto."""
    res = {}
    for nombre in ("H1", "H2"):
        por_h, razones, dc, dv = {}, [], [], []
        for h in hs:
            d = b[nombre][h]
            q_t = np.array([reglas.cuantiles(int(o), h, *sel.VIGENTE) for o in d["o"]])
            q_ref = np.array([reglas.cuantiles(int(o), h, 0.0, sel.V_REF) for o in d["o"]])
            q_c = np.array([cand(h, m, t) for m, t in zip(d["q_m0"], q_t)])
            q_0 = np.array([mezcla(m, t, W_VIGENTE) for m, t in zip(d["q_m0"], q_t)])
            w_c, w_0 = sel.wis_lista(d["y"], q_c), sel.wis_lista(d["y"], q_0)
            w_ref = sel.wis_lista(d["y"], q_ref)
            razones.append(float(w_c.mean() / w_0.mean()))
            dc += list(dentro95(d["y"], q_c))
            dv += list(dentro95(d["y"], q_0))
            por_h[h] = {
                "n": len(d["y"]), "wis_candidata": float(w_c.mean()), "wis_C_vigente": float(w_0.mean()),
                "wis_T_sola": float(sel.wis_lista(d["y"], q_t).mean()),
                "wis_M0_sola": float(sel.wis_lista(d["y"], d["q_m0"]).mean()), "wis_referencia": float(w_ref.mean()),
                "razon_wis": razones[-1], "skill_candidata": float(1 - w_c.mean() / w_ref.mean()),
                "skill_C_vigente": float(1 - w_0.mean() / w_ref.mean()),
                "cob50_candidata": float(np.mean((d["y"] >= np.sort(q_c, axis=1)[:, IDX_B50[0]]) &
                                                 (d["y"] <= np.sort(q_c, axis=1)[:, IDX_B50[1]]))),
                "cob95_candidata": float(dentro95(d["y"], q_c).mean()), "cob95_C_vigente": float(dentro95(d["y"], q_0).mean()),
                "dm_candidata_menos_vigente": sel.dm(w_c - w_0, h),
            }
        res[nombre] = {"por_h": por_h, "razon_media": float(np.mean(razones)),
                       "cob95_candidata": float(np.mean(dc)), "cob95_vigente": float(np.mean(dv))}
    res["b_wis"] = bool(res["H1"]["razon_media"] < 1 and res["H2"]["razon_media"] <= RAZON_H2_MAX)
    res["c_cobertura"] = bool(res["H2"]["cob95_candidata"] >= res["H2"]["cob95_vigente"] - COBERTURA_TOLERANCIA)
    return res


def imprimir(titulo: str, conf: dict) -> None:
    print(f"\n{titulo}")
    for nombre in ("H1", "H2"):
        r = conf[nombre]
        print(f"  {nombre}: razón media de WIS {r['razon_media']:.3f}, cobertura 95 % {r['cob95_candidata']:.3f} "
              f"(C vigente {r['cob95_vigente']:.3f})")
        for h, x in r["por_h"].items():
            p = x["dm_candidata_menos_vigente"]
            print(f"    h{h}: n {x['n']:>3} WIS {x['wis_candidata']:>6.2f} vs C {x['wis_C_vigente']:>6.2f} "
                  f"(T {x['wis_T_sola']:>6.2f}, M0 {x['wis_M0_sola']:>6.2f}) razón {x['razon_wis']:.3f}"
                  + (f", DM p {p['p']:.2f}" if p else ""))
    print(f"  (b) WIS menor en H1 y ≤ {RAZON_H2_MAX} en H2: {conf['b_wis']} | (c) cobertura: {conf['c_cobertura']}")


def confirmacion(reglas: sel.Reglas, b: dict, guardado: dict) -> dict:
    out: dict = {"tramos": {}, "candidatas": {}}
    pesos_c = {}
    for g, hs in GRUPOS.items():
        dec = guardado["validacion"][g]["decision"]
        w = float(dec["mejor_admisible"])
        regla = dec["regla_admisible"]["pasa"]
        if w == W_VIGENTE:
            print(f"\ntramo {g}: la mejor admisible es 0,5, nada que confirmar")
            out["candidatas"][g] = {"peso": W_VIGENTE, "a_regla_de_cambio": False, "candidata": False}
            continue
        conf = confirmar(reglas, b, tuple(hs), lambda h, m, t, w=w: mezcla(m, t, w))
        imprimir(f"Confirmación del tramo {g}, w = {w} (regla de cambio en la validación: {'SI' if regla else 'no'})", conf)
        cand = bool(regla and conf["b_wis"] and conf["c_cobertura"])
        out["tramos"][g] = conf
        out["candidatas"][g] = {"peso": w, "a_regla_de_cambio": bool(regla), "b_wis": conf["b_wis"],
                                "c_cobertura": conf["c_cobertura"], "candidata": cand}
        if cand:
            pesos_c[g] = w
    print("\nCandidatas:", json.dumps(out["candidatas"], ensure_ascii=False))
    # C_h completo con los pesos de los tramos candidatos (el resto en 0,5)
    por_h = {h: pesos_c.get(g, W_VIGENTE) for g, hs in GRUPOS.items() for h in hs}
    out["pesos_C_h"] = {int(h): w for h, w in por_h.items()}
    if pesos_c:
        out["C_h_completo"] = confirmar(reglas, b, HORIZONTES, lambda h, m, t: mezcla(m, t, por_h[h]))
        imprimir(f"C_h completo, pesos {out['pesos_C_h']}", out["C_h_completo"])
    else:
        print("ningún tramo es candidato: C_h completo es C")
    return out


def _correr_e1(reglas: sel.Reglas, val: dict, b: dict, g: str, w: float) -> dict:
    """Centro con el peso w y ancho con 0,5 en el tramo g: validacion y, si pasa la regla de
    cambio, confirmacion en H1 y H2."""
    hs = tuple(GRUPOS[g])
    res = puntajes(val, hs, {f"{W_VIGENTE}": politica_peso(W_VIGENTE), f"centro{w}": politica_e1(w)})
    dec = decidir(res, f"{W_VIGENTE}")
    pasa = dec["mejor_admisible"] != f"{W_VIGENTE}" and dec["regla_admisible"]["pasa"]
    print(f"\nE1, tramo {g}: centro con w = {w}, ancho con 0,5: puntaje {res[f'centro{w}']['puntaje']:+.4f} "
          f"(0,5: {res[f'{W_VIGENTE}']['puntaje']:+.4f}), cobertura {res[f'centro{w}']['cob95']:.3f}, "
          f"regla de cambio: {'SI' if pasa else 'no'}")
    item: dict = {"w_centro": w, "validacion": res, "decision": dec, "candidata": False}
    if pasa:
        conf = confirmar(reglas, b, hs, lambda h, m, t, w=w: mezcla_centro_ancho(m, t, w, W_VIGENTE))
        imprimir(f"Confirmación E1, tramo {g}", conf)
        item["confirmacion"] = conf
        item["candidata"] = bool(conf["b_wis"] and conf["c_cobertura"])
    return item


def extension_e1(reglas: sel.Reglas, serie: Serie, b: dict, guardado: dict) -> dict:
    tramos = [g for g in GRUPOS if guardado["validacion"][g]["decision"]["e1_aplica"]]
    if not tramos:
        print("ningún tramo cumple la condición de la extensión E1: no se corre")
        return {"corrida": False}
    val = datos_validacion(serie, reglas)
    return {"corrida": True, "tramos": {
        g: _correr_e1(reglas, val, b, g, float(guardado["validacion"][g]["decision"]["mejor_sin_restriccion"]))
        for g in tramos}}


def exploratorio_e1(reglas: sel.Reglas, serie: Serie, b: dict, guardado: dict) -> dict:
    """Exploratorio, despues de ver la confirmacion: la misma variante E1 para los tramos que
    ganaron en WIS en H1 y H2 y fallaron solo la cobertura en H2. La condicion de la extension
    firmada miraba la validacion, y ahi el peso era admisible; por eso esto no es la extension."""
    cands = guardado["confirmacion"]["candidatas"]
    tramos = [g for g, c in cands.items() if c.get("b_wis") and c.get("c_cobertura") is False]
    if not tramos:
        print("ningún tramo falló solo por cobertura en H2")
        return {"corrida": False}
    val = datos_validacion(serie, reglas)
    items = {g: _correr_e1(reglas, val, b, g, float(cands[g]["peso"])) for g in tramos}
    out: dict = {"corrida": True, "rotulo": "exploratorio, posterior a la confirmacion", "tramos": items}
    # C_h completo: tramos con E1 candidata con centro y ancho separados, tramos candidatos con
    # la mezcla simple y el resto en 0,5
    e1 = {g for g, it in items.items() if it["candidata"]}
    simples = {g: float(c["peso"]) for g, c in cands.items() if c.get("candidata")}

    def politica(h: int, m: np.ndarray, t: np.ndarray) -> np.ndarray:
        g = next(k for k, hs in GRUPOS.items() if h in hs)
        if g in e1:
            return mezcla_centro_ancho(m, t, float(cands[g]["peso"]), W_VIGENTE)
        return mezcla(m, t, simples.get(g, W_VIGENTE))

    out["C_h_completo"] = confirmar(reglas, b, HORIZONTES, politica)
    out["tramos_e1"], out["tramos_mezcla_simple"] = sorted(e1), simples
    imprimir(f"C_h completo exploratorio (E1 en {sorted(e1)}, mezcla simple {simples})", out["C_h_completo"])
    return out


# --- controles ---------------------------------------------------------------------------


def controles(serie: Serie, reglas: sel.Reglas, b: dict) -> dict:
    ctrl = sel.controles(serie, b)
    val = datos_validacion(serie, reglas)
    dif_m0, dif_t, dif_e1, filas = 0.0, 0.0, 0.0, 0
    for h in HORIZONTES:
        for d in val[h].values():
            for m, t in zip(d["q_m0"], d["q_t"]):
                dif_m0 = max(dif_m0, float(np.max(np.abs(mezcla(m, t, 1.0) - m))))
                dif_t = max(dif_t, float(np.max(np.abs(mezcla(m, t, 0.0) - t))))
                dif_e1 = max(dif_e1, float(np.max(np.abs(mezcla_centro_ancho(m, t, 0.25, 0.25) - mezcla(m, t, 0.25)))))
                filas += 1
    ok = bool(ctrl["pasa"] and dif_m0 < 1e-9 and dif_t < 1e-9 and dif_e1 < 1e-9)
    out = {"reproduccion_fase1": ctrl, "filas_identidad": filas, "dif_w1_vs_M0": dif_m0, "dif_w0_vs_T": dif_t,
           "dif_e1_igual_peso_vs_mezcla": dif_e1, "pasa": ok}
    print(f"controles: reproducción de q_T/q_C_R0 {ctrl['pasa']} (dif T {ctrl['dif_max_T']:.2e}, C {ctrl['dif_max_C']:.2e}) | "
          f"w = 1 vs M0 {dif_m0:.1e} | w = 0 vs T {dif_t:.1e} | E1 con pesos iguales vs mezcla {dif_e1:.1e} -> "
          f"{'OK' if ok else 'FALLAN'}")
    return out


# --- ejecucion ------------------------------------------------------------------------------


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
    for nombre in ("control", "validacion", "confirmacion", "extension-e1", "exploratorio-e1"):
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
    ctrl = controles(serie, reglas, b)
    if args.control:
        _guardar("control", ctrl)
        return
    if not ctrl["pasa"]:
        raise SystemExit("los controles fallan: el experimento se detiene (protocolo)")
    if args.validacion:
        _guardar("validacion", validacion(serie, reglas))
        return
    guardado = json.loads(SALIDA.read_text(encoding="utf-8"))
    if args.confirmacion:
        _guardar("confirmacion", confirmacion(reglas, b, guardado))
    elif args.exploratorio_e1:
        _guardar("exploratorio_e1", exploratorio_e1(reglas, serie, b, guardado))
    else:
        _guardar("extension_e1", extension_e1(reglas, serie, b, guardado))


if __name__ == "__main__":
    main()
