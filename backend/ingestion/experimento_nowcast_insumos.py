"""
Experimento: que aportan a M0 el clima, el ONI, el anio y el tratamiento de
los ceros (docs/experimentos/experimento-nowcast-insumos.md, fijado 2026-10-02).

Seis variantes de M0 que solo difieren en el insumo:

  I0  M0 sin cambios (control; debe reproducir los cuantiles publicados)
  I1  sin ONI
  I2  sin las siete medias de clima
  I3  sin clima ni ONI
  I4  sin el anio de la semana objetivo
  I5  ceros de OpenDengue repartidos con la semana siguiente, solo como insumo

Dos fases en una invocacion: validacion (objetivos 2019, 2021-2024; decide) y
serie del tablero (2025-S1 a 2026-S37; se reporta, con la mezcla C construida
con cada variante). Ninguna semana objetivo desde 2026-S38 entra.

Uso:
    cd backend/ingestion
    POSTGRES_HOST=localhost nice -n 10 python experimento_nowcast_insumos.py
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

import experimento_nowcast_comun as com
import experimento_nowcast_corto_plazo as exp
import experimento_nowcast_mejora as mej
import experimento_nowcast_tablero as tab
import experimento_nowcast_tendencia as ten
from experimento_nowcast_corto_plazo import Serie, wis
from nowcast_estimacion_dengue import ALCANCE_HISTORIA
from nowcast_estimacion_dengue import HORIZONTES as HORIZONTES_TODOS

from db import get_connection

HORIZONTES = list(HORIZONTES_TODOS)
LIMITE_ORIGENES: int | None = None  # --humo: pocos origenes, solo para probar el script

PROCESOS = 4
H_DECISIVOS = (4, 8)
UMBRAL_S = 0.03
MIN_ANIOS = 4
BANDA_95 = (0.85, 0.99)
BANDA_50 = (0.35, 0.65)
VARIANTES: dict[str, dict] = {
    "I0": {"grupos": com.GRUPOS_M0, "ceros": False},
    "I1": {"grupos": tuple(g for g in com.GRUPOS_M0 if g != "oni"), "ceros": False},
    "I2": {"grupos": tuple(g for g in com.GRUPOS_M0 if g != "clima"), "ceros": False},
    "I3": {"grupos": tuple(g for g in com.GRUPOS_M0 if g not in ("clima", "oni")), "ceros": False},
    "I4": {"grupos": tuple(g for g in com.GRUPOS_M0 if g != "anio"), "ceros": False},
    "I5": {"grupos": com.GRUPOS_M0, "ceros": True},
}
FASES = {"validacion": mej.ANIOS_VALIDACION, "tablero": mej.ANIOS_CONFIRMACION}
REFERENCIAS = mej.REFERENCIAS

DIR = Path(__file__).parent / "data" / "interim" / "nowcast"
DIR_VERSIONADO = Path(__file__).resolve().parents[2] / "docs" / "agentes" / "mejora-predictor" / "resultados-nuevos"
PREVIOS = Path(__file__).resolve().parents[2] / "docs" / "agentes" / "mejora-predictor" / "resultados-previos" / "nowcast"


CACHE = DIR / "cache"


def _con_cache(nombre: str, calcular):
    """Reutiliza el resultado de una tarea ya calculada (mismo codigo, mismos
    datos). Para rehacer una corrida desde cero, borrar DIR / "cache"."""
    if LIMITE_ORIGENES:
        return calcular()
    ruta = CACHE / f"{nombre}.json"
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    r = calcular()
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(r, default=str), encoding="utf-8")
    tmp.replace(ruta)
    return r


def constructor(serie: Serie, variante: str):
    v = VARIANTES[variante]
    if v["ceros"]:
        z_ins, ceros = com.serie_ceros_repartidos(serie)
        ceros = frozenset(int(k) for k in ceros)
        return (lambda t, h: com.features_ceros_repartidos(serie, z_ins, ceros, t, h, v["grupos"])), z_ins
    return (lambda t, h: com.features_grupos(serie, t, h, v["grupos"])), None


def _tarea_modelo(args: tuple) -> dict:
    serie, variante, h, fase, mutar = args
    return _con_cache(f"insumos_{variante}_h{h}_{fase}_{'mut' if mutar else 'normal'}",
                      lambda: _calcular_modelo(serie, variante, h, fase, mutar))


def _calcular_modelo(serie: Serie, variante: str, h: int, fase: str, mutar: bool) -> dict:
    threadpool_limits(1)
    origenes = mej.origenes_de(serie, h, FASES[fase])[:LIMITE_ORIGENES]
    construir, z_ins = constructor(serie, variante)
    cad = com.cadena_enriquecida(serie, origenes, h, construir, y=z_ins, mutar=mutar)
    filas = []
    for o in origenes:
        p = cad[o]
        if p is None:
            continue
        fac = com.factores_simetricos(p.reajuste.cal_q, p.reajuste.cal_y)
        q = com.aplicar_factores(p.qz, fac)
        y = float(serie.casos[o + h])
        filas.append({"origen": str(serie.fecha[o]), "anio": int(serie.anio[o + h]),
                      "semana": int(serie.semana[o + h]), "y": y, "q": q.tolist(), "wis": wis(y, q)})
    return {"variante": variante, "h": h, "fase": fase, "mutar": mutar, "filas": filas,
            "sin_prediccion": len(origenes) - len(filas)}


def _tarea_referencias(args: tuple) -> dict:
    serie, h, fase = args
    return _con_cache(f"insumos_referencias_h{h}_{fase}", lambda: _calcular_referencias(serie, h, fase))


def _calcular_referencias(serie: Serie, h: int, fase: str) -> dict:
    threadpool_limits(1)
    tab._instalar_parches()
    afect = mej.semanas_afectadas(serie)
    prom = ten.historia_promediada(serie)
    origenes = mej.origenes_de(serie, h, FASES[fase])[:LIMITE_ORIGENES]
    filas = {}
    for o in origenes:
        y = float(serie.casos[o + h])
        f = {"y": y}
        for n in REFERENCIAS:
            f[f"wis_pub_{n}"] = wis(y, mej.referencia(n, serie, o, h))
            f[f"wis_limpia_{n}"] = wis(y, mej.referencia(n, serie, o, h, afect))
        if fase == "tablero":
            rs = ten.cuantiles_regla(prom, o, h, 0.0)
            qt = ten.cuantiles_regla(prom, o, h, ten.PHI)
            f["wis_suavizada"] = wis(y, rs) if rs is not None else None
            f["q_T"] = qt.tolist() if qt is not None else None
        filas[str(serie.fecha[o])] = f
    return {"h": h, "fase": fase, "filas": filas}


def _decisiva(refs: dict, familia: str, origenes: list[str]) -> str:
    return min(REFERENCIAS, key=lambda n: np.mean([refs[o][f"wis_{familia}_{n}"] for o in origenes]))


def _skill(wis_m: float, wis_r: float) -> float:
    return float(1 - wis_m / wis_r)


def _tabla(filas: list[dict], refs: dict, clave_ref: str, clave_q: str = "q") -> dict:
    ok = [f for f in filas if refs[f["origen"]].get(clave_ref) is not None]
    y = np.array([f["y"] for f in ok])
    qs = np.array([f[clave_q] for f in ok])
    anios = np.array([f["anio"] for f in ok])
    wr = np.array([refs[f["origen"]][clave_ref] for f in ok])
    return com.metricas(y, qs, anios, wr)


def _reproduce_publicado(res: dict, fase: str) -> dict:
    """Compara I0 con los cuantiles de M0 guardados por el experimento de
    mejora. Devuelve el numero de predicciones comparadas, la diferencia maxima
    por cuantil, la diferencia relativa maxima de la mediana y el primer origen
    con diferencia."""
    archivo = PREVIOS / ("mejora_validacion.json" if fase == "validacion" else "mejora_confirmacion.json")
    previo = json.loads(archivo.read_text(encoding="utf-8"))["detalle"]
    n, dif, dif_med, primero = 0, 0.0, 0.0, None
    for h in HORIZONTES:
        guardado = {f["origen"]: np.array(f["q_M0"]) for f in previo[str(h)]["filas"]}
        for f in sorted(res[("I0", h, fase, False)]["filas"], key=lambda f: f["origen"]):
            g = guardado.get(f["origen"])
            if g is None:
                continue
            n += 1
            d = float(np.max(np.abs(g - np.array(f["q"]))))
            if d > 0 and primero is None:
                primero = f["origen"]
            dif = max(dif, d)
            dif_med = max(dif_med, abs(f["q"][11] - g[11]) / max(g[11], 1.0))
    return {"comparadas": n, "diferencia_maxima": dif, "diferencia_relativa_mediana": float(dif_med),
            "primer_origen_distinto": primero}


def _imprimir(titulo: str, tabla: dict) -> None:
    print(f"\n{titulo}")
    print(f"{'h':>2} {'var':<4}{'n':>5}{'WIS':>8}{'WIS ref':>8}{'skill':>7}{'medio':>7}{'gana':>5}"
          f"{'cob50':>7}{'cob95':>7}{'bajo':>6}  skill por anio")
    for h, porv in tabla.items():
        for v, r in porv.items():
            anios = " ".join(f"{a}:{s:+.2f}" for a, s in r["skill_por_anio"].items())
            print(f"{h:>2} {v:<4}{r['n']:>5}{r['wis']:>8.1f}{r['wis_referencia']:>8.1f}{r['skill_agrupado']:>+7.2f}"
                  f"{r['skill_medio']:>+7.2f}{r['anios_ganados']:>5}{r['cobertura_50']:>7.2f}{r['cobertura_95']:>7.2f}"
                  f"{r['bajo_mediana']:>6.2f}  {anios}")


def main() -> None:
    global HORIZONTES, LIMITE_ORIGENES
    if "--humo" in sys.argv:
        HORIZONTES, LIMITE_ORIGENES = [4, 8], 12
        print("modo humo: solo h = 4 y 8, 12 origenes; los resultados no valen")
    conn = get_connection()
    try:
        serie = tab.cargar_serie_mixta(conn)
    finally:
        conn.close()
    print(f"serie mixta: {serie.T} semanas, {serie.fecha[0]} a {serie.fecha[-1]}")
    tab._instalar_parches()
    exp.verificar_sin_fuga(serie, mej.origenes_de(serie, 4, mej.ANIOS_VALIDACION), 4, ALCANCE_HISTORIA)

    tareas_ref = [(serie, h, fase) for fase in FASES for h in HORIZONTES]
    tareas_mod = [(serie, v, h, fase, False) for fase in FASES for v in VARIANTES for h in HORIZONTES]
    tareas_mod.append((serie, "I3", 4, "validacion", True))
    with ProcessPoolExecutor(max_workers=PROCESOS) as ex:
        refs_lista = list(ex.map(_tarea_referencias, tareas_ref))
        res_lista = list(ex.map(_tarea_modelo, tareas_mod))
    refs = {(r["h"], r["fase"]): r["filas"] for r in refs_lista}
    res = {(r["variante"], r["h"], r["fase"], r["mutar"]): r for r in res_lista}

    # control: I0 reproduce lo publicado
    controles = {}
    for fase in FASES:
        c = _reproduce_publicado(res, fase)
        controles[f"i0_reproduce_{fase}"] = c
        print(f"I0 contra el experimento de mejora ({fase}): {c['comparadas']} predicciones, "
              f"diferencia maxima {c['diferencia_maxima']:.3f} (mediana, relativa: "
              f"{c['diferencia_relativa_mediana']:.4f}; primer origen distinto: {c['primer_origen_distinto']})")
        # en la validacion la reproduccion debe ser exacta; en el tablero se
        # reporta (enmienda del 2026-10-02: la semilla no trae ONI de 2025-2026)
        if fase == "validacion" and c["diferencia_maxima"] != 0.0:
            raise SystemExit("I0 no reproduce los cuantiles publicados: revisar antes de leer resultados.")
    w_i3 = np.mean([f["wis"] for f in res[("I3", 4, "validacion", False)]["filas"]])
    w_mut = np.mean([f["wis"] for f in res[("I3", 4, "validacion", True)]["filas"]])
    controles["mutacion_I3_h4"] = {"wis": float(w_i3), "wis_mutado": float(w_mut), "empeora": bool(w_mut > w_i3)}
    print(f"control de mutacion I3 (h = 4): WIS {w_i3:.1f} -> {w_mut:.1f} con etiquetas permutadas")

    salida = {"controles": controles, "fases": {}}
    # --- validacion ------------------------------------------------------
    tablas = {"limpia": {}, "pub": {}}
    for h in HORIZONTES:
        rf = refs[(h, "validacion")]
        origenes = [f["origen"] for f in res[("I0", h, "validacion", False)]["filas"]]
        for familia in tablas:
            dec = _decisiva(rf, familia, origenes)
            tablas[familia][h] = {v: {"referencia": dec, **_tabla(res[(v, h, "validacion", False)]["filas"], rf, f"wis_{familia}_{dec}")}
                                  for v in VARIANTES}
    _imprimir("Validacion 2019, 2021-2024, contra la referencia limpia", tablas["limpia"])
    _imprimir("Validacion, contra la referencia publicada", tablas["pub"])

    # skill contra I0 y veredictos
    contra_i0 = {}
    for h in HORIZONTES:
        w0 = {f["origen"]: f["wis"] for f in res[("I0", h, "validacion", False)]["filas"]}
        contra_i0[h] = {}
        for v in VARIANTES:
            fv = res[(v, h, "validacion", False)]["filas"]
            s = _skill(np.mean([f["wis"] for f in fv]), np.mean([w0[f["origen"]] for f in fv]))
            por_anio = {}
            for a in mej.ANIOS_VALIDACION:
                fa = [f for f in fv if f["anio"] == a]
                if not fa:
                    continue
                por_anio[a] = _skill(np.mean([f["wis"] for f in fa]), np.mean([w0[f["origen"]] for f in fa]))
            contra_i0[h][v] = {"skill_vs_I0": s, "por_anio": por_anio,
                               "anios_mejor_que_I0": int(sum(x > 0 for x in por_anio.values())),
                               "anios_peor_que_I0": int(sum(x < 0 for x in por_anio.values()))}
    print("\nSkill de cada variante contra I0 (validacion, agrupado):")
    print(f"{'h':>2}" + "".join(f"{v:>8}" for v in VARIANTES))
    for h in HORIZONTES:
        print(f"{h:>2}" + "".join(f"{contra_i0[h][v]['skill_vs_I0']:>+8.3f}" for v in VARIANTES))

    veredictos = {}
    for v in ("I1", "I2", "I3", "I4"):
        c = {h: contra_i0[h][v] for h in H_DECISIVOS}
        aporta = all(c[h]["skill_vs_I0"] <= -UMBRAL_S and c[h]["anios_peor_que_I0"] >= MIN_ANIOS for h in H_DECISIVOS)
        estorba = all(c[h]["skill_vs_I0"] >= UMBRAL_S and c[h]["anios_mejor_que_I0"] >= MIN_ANIOS for h in H_DECISIVOS)
        veredictos[v] = "aporta" if aporta else "estorba" if estorba else "sin efecto medible"
        print(f"{v}: el insumo {veredictos[v]}")
    cond = {}
    for h in H_DECISIVOS:
        r, r0 = tablas["limpia"][h]["I5"], tablas["limpia"][h]["I0"]
        cond[h] = {"skill_medio_positivo": r["skill_medio"] > 0, "gana_4_de_5": r["anios_ganados"] >= MIN_ANIOS,
                   "cobertura_en_banda": com.en_banda(r["cobertura_95"], BANDA_95) and com.en_banda(r["cobertura_50"], BANDA_50),
                   "no_peor_que_I0": r["wis"] <= r0["wis"]}
    pasa_i5 = all(all(c.values()) for c in cond.values())
    veredictos["I5"] = {"condiciones": cond, "pasa_validacion": pasa_i5}
    print(f"I5: {'pasa' if pasa_i5 else 'no pasa'} la validacion {cond}")
    salida["fases"]["validacion"] = {"tablas": tablas, "contra_I0": contra_i0, "veredictos": veredictos,
                                     "sin_prediccion": {f"{v}_h{h}": res[(v, h, 'validacion', False)]["sin_prediccion"]
                                                        for v in VARIANTES for h in HORIZONTES}}

    # --- tablero -------------------------------------------------------------
    tab_m0, tab_c, contra_c0 = {}, {}, {}
    for h in HORIZONTES:
        rf = refs[(h, "tablero")]
        tab_m0[h], tab_c[h] = {}, {}
        for v in VARIANTES:
            fv = [dict(f) for f in res[(v, h, "tablero", False)]["filas"] if rf[f["origen"]].get("q_T") is not None]
            for f in fv:
                f["q_C"] = mej._mezcla(np.array(f["q"]), np.array(rf[f["origen"]]["q_T"]), ten.PESO_M0).tolist()
            tab_m0[h][v] = _tabla(fv, rf, "wis_suavizada")
            tab_c[h][v] = _tabla(fv, rf, "wis_suavizada", "q_C")
            tab_c[h][v]["wis_C_por_origen"] = {f["origen"]: wis(f["y"], np.array(f["q_C"])) for f in fv}
        w_c0 = tab_c[h]["I0"]["wis_C_por_origen"]
        contra_c0[h] = {v: _skill(np.mean(list(tab_c[h][v]["wis_C_por_origen"].values())),
                                  np.mean([w_c0[o] for o in tab_c[h][v]["wis_C_por_origen"]])) for v in VARIANTES}
        for v in VARIANTES:
            del tab_c[h][v]["wis_C_por_origen"]
    _imprimir("Tablero 2025-S1 a 2026-S37, M0 con cada insumo, contra la persistencia suavizada", tab_m0)
    _imprimir("Tablero, mezcla C con cada insumo, contra la persistencia suavizada", tab_c)
    print("\nSkill de C con cada variante contra C con I0 (tablero, agrupado):")
    print(f"{'h':>2}" + "".join(f"{v:>8}" for v in VARIANTES))
    for h in HORIZONTES:
        print(f"{h:>2}" + "".join(f"{contra_c0[h][v]:>+8.3f}" for v in VARIANTES))
    cond_t = {h: {"wis_no_mayor_que_C": tab_c[h]["I5"]["wis"] <= tab_c[h]["I0"]["wis"],
                  "cobertura_95": tab_c[h]["I5"]["cobertura_95"] >= 0.85,
                  "skill_positivo": tab_c[h]["I5"]["skill_agrupado"] > 0} for h in H_DECISIVOS}
    cumple_t = pasa_i5 and all(all(c.values()) for c in cond_t.values())
    print(f"I5 en el tablero: {'cumple' if cumple_t else 'no cumple'} {cond_t} (solo decide si paso la validacion)")
    salida["fases"]["tablero"] = {"tablas_M0": tab_m0, "tablas_C": tab_c, "C_contra_C_I0": contra_c0,
                                  "I5_condiciones": cond_t, "I5_cumple": bool(cumple_t),
                                  "sin_prediccion": {f"{v}_h{h}": res[(v, h, 'tablero', False)]["sin_prediccion"]
                                                     for v in VARIANTES for h in HORIZONTES}}
    salida["detalle"] = {f"{v}_h{h}_{fase}": r for (v, h, fase, m), r in res.items() if not m}
    salida["detalle_referencias"] = {f"h{h}_{fase}": r for (h, fase), r in refs.items()}

    DIR.mkdir(parents=True, exist_ok=True)
    out = DIR / ("insumos_humo.json" if LIMITE_ORIGENES else "insumos.json")
    out.write_text(json.dumps(salida, default=str), encoding="utf-8")
    if LIMITE_ORIGENES:
        print(f"-> {out}")
        return
    com.copia_versionada(out, DIR_VERSIONADO / "insumos.json")  # flotantes redondeados a 3 decimales
    print(f"-> {out} y {DIR_VERSIONADO / 'insumos.json'}")


if __name__ == "__main__":
    main()
