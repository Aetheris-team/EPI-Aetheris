"""
Experimento: brotes sin precedente en la historia y una familia que extrapola
(docs/experimentos/experimento-nowcast-recorte.md, fijado 2026-10-02).

  - Validacion normal (historia completa): M0 y L0 (regresion cuantilica
    lineal sobre las mismas variables, misma calibracion) con objetivos en
    2019, 2021-2024.
  - Recorte: para 2019, 2022 y 2024, se excluyen de los objetivos de
    entrenamiento los anios con total anual mayor o igual que el del anio de
    prueba; las referencias usan la misma historia recortada.
  - Tablero (solo si L0 pasa la validacion normal): L0 y la mezcla C con L0,
    objetivos de 2025-S1 a 2026-S37.

Uso:
    cd backend/ingestion
    POSTGRES_HOST=localhost nice -n 10 python experimento_nowcast_recorte.py
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
from experimento_nowcast_corto_plazo import ANIO_EXCLUIDO, Serie, wis
from nowcast_estimacion_dengue import ALCANCE_HISTORIA
from nowcast_estimacion_dengue import HORIZONTES as HORIZONTES_TODOS

from db import get_connection

HORIZONTES = list(HORIZONTES_TODOS)
LIMITE_ORIGENES: int | None = None  # --humo
PROCESOS = 4
ANIOS_RECORTE = (2019, 2022, 2024)
ANIOS_SIN_PRECEDENTE = (2019, 2022)
EXCLUSION_ESPERADA = {2019: {2014, 2015}, 2022: {2014, 2015, 2019}, 2024: {2014, 2015, 2016, 2019, 2022}}
MODELOS = {"M0": com.ajustar_hgbr, "L0": com.ajustar_lineal}
H_DECISIVOS = (4, 8)
MIN_ANIOS = 4
BANDA_95, BANDA_50 = (0.85, 0.99), (0.35, 0.65)
SEMANAS_PICO = 8
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


def totales_anuales(serie: Serie) -> dict[int, float]:
    return {int(a): float(np.nansum(serie.casos[serie.anio == a])) for a in range(2014, 2025)}


def anios_excluidos_para(serie: Serie, anio_prueba: int) -> frozenset[int]:
    tot = totales_anuales(serie)
    excl = {a for a, v in tot.items() if a < anio_prueba and v >= tot[anio_prueba]}
    return frozenset(excl | {ANIO_EXCLUIDO})


def origenes_recorte(serie: Serie, h: int, anio_prueba: int) -> list[int]:
    return [o for o in range(serie.T - h)
            if serie.anio[o] != ANIO_EXCLUIDO and serie.anio[o] >= ALCANCE_HISTORIA
            and serie.anio[o + h] == anio_prueba and np.isfinite(serie.casos[o + h])
            and com.features_grupos(serie, o, h) is not None]


def _tarea(args: tuple) -> dict:
    serie, fase, modelo, h, anio_prueba, mutar = args
    return _con_cache(f"recorte_{fase}_{modelo}_h{h}_{anio_prueba}_{'mut' if mutar else 'normal'}",
                      lambda: _calcular(serie, fase, modelo, h, anio_prueba, mutar))


def _calcular(serie: Serie, fase: str, modelo: str, h: int, anio_prueba, mutar: bool) -> dict:
    threadpool_limits(1)
    tab._instalar_parches()
    afect = mej.semanas_afectadas(serie)
    construir = lambda t, hh: com.features_grupos(serie, t, hh)  # noqa: E731
    if fase == "validacion":
        origenes = mej.origenes_de(serie, h, mej.ANIOS_VALIDACION)[:LIMITE_ORIGENES]
        excl = frozenset({ANIO_EXCLUIDO})
    elif fase == "recorte":
        origenes = origenes_recorte(serie, h, anio_prueba)[:LIMITE_ORIGENES]
        excl = anios_excluidos_para(serie, anio_prueba)
    else:
        origenes = mej.origenes_de(serie, h, mej.ANIOS_CONFIRMACION)[:LIMITE_ORIGENES]
        excl = frozenset({ANIO_EXCLUIDO})
    cad = com.cadena_enriquecida(serie, origenes, h, construir, ajustar=MODELOS[modelo],
                                 anios_excluidos=excl, mutar=mutar)
    prom = ten.historia_promediada(serie) if fase == "tablero" else None
    filas = []
    for o in origenes:
        p = cad[o]
        if p is None:
            continue
        # asercion sobre los indices reales: ningun objetivo en un anio excluido
        assert not any(serie.anio[k] in excl for k in p.reajuste.idx_entrenamiento)
        q = com.aplicar_factores(p.qz, com.factores_simetricos(p.reajuste.cal_q, p.reajuste.cal_y))
        y = float(serie.casos[o + h])
        f = {"origen": str(serie.fecha[o]), "anio": int(serie.anio[o + h]), "semana": int(serie.semana[o + h]),
             "y": y, "q": q.tolist(), "wis": wis(y, q)}
        if not mutar:
            for n in REFERENCIAS:
                f[f"wis_limpia_{n}"] = wis(y, com.referencia(n, serie, o, h, afect, excl))
                f[f"wis_pub_{n}"] = wis(y, com.referencia(n, serie, o, h, frozenset(), excl))
                if fase == "recorte":
                    f[f"wis_limpia_completa_{n}"] = wis(y, mej.referencia(n, serie, o, h, afect))
            if fase == "tablero":
                rs = ten.cuantiles_regla(prom, o, h, 0.0)
                qt = ten.cuantiles_regla(prom, o, h, ten.PHI)
                f["wis_suavizada"] = wis(y, rs) if rs is not None else None
                f["q_C"] = com.mezcla_log(q, qt, ten.PESO_M0).tolist() if qt is not None else None
        filas.append(f)
    return {"fase": fase, "modelo": modelo, "h": h, "anio_prueba": anio_prueba, "mutar": mutar,
            "filas": filas, "sin_prediccion": len(origenes) - len(filas),
            "anios_excluidos": sorted(excl), "n_origenes": len(origenes)}


def _decisiva(filas: list[dict], familia: str) -> str:
    return min(REFERENCIAS, key=lambda n: np.mean([f[f"wis_{familia}_{n}"] for f in filas]))


def _tabla(filas: list[dict], clave_ref: str, clave_q: str = "q") -> dict:
    ok = [f for f in filas if f.get(clave_ref) is not None and f.get(clave_q) is not None]
    return com.metricas(np.array([f["y"] for f in ok]), np.array([f[clave_q] for f in ok]),
                        np.array([f["anio"] for f in ok]), np.array([f[clave_ref] for f in ok]))


def _saturacion(filas: list[dict]) -> dict:
    """Cociente mediana / observado en las semanas de mayor conteo."""
    pico = sorted(filas, key=lambda f: -f["y"])[:SEMANAS_PICO]
    coc = [np.sort(f["q"])[com.IDX_MEDIANA] / f["y"] for f in pico if f["y"] > 0]
    return {"n": len(coc), "cociente_medio": round(float(np.mean(coc)), 3) if coc else None,
            "semanas": [f["origen"] for f in pico]}


def _imprimir(titulo: str, tabla: dict, con_anios: bool = True) -> None:
    print(f"\n{titulo}")
    print(f"{'h':>2} {'modelo':<6}{'n':>5}{'WIS':>8}{'WIS ref':>8}{'skill':>7}{'medio':>7}{'gana':>5}"
          f"{'cob50':>7}{'cob95':>7}{'bajo':>6}  por anio")
    for h, porm in tabla.items():
        for m, r in porm.items():
            anios = " ".join(f"{a}:{s:+.2f}" for a, s in r["skill_por_anio"].items()) if con_anios else ""
            print(f"{h:>2} {m:<6}{r['n']:>5}{r['wis']:>8.1f}{r['wis_referencia']:>8.1f}{r['skill_agrupado']:>+7.2f}"
                  f"{r['skill_medio']:>+7.2f}{r['anios_ganados']:>5}{r['cobertura_50']:>7.2f}{r['cobertura_95']:>7.2f}"
                  f"{r['bajo_mediana']:>6.2f}  {anios}")


def _reproduce(res: dict) -> dict:
    previo = json.loads((PREVIOS / "mejora_validacion.json").read_text(encoding="utf-8"))["detalle"]
    n, dif = 0, 0.0
    for h in HORIZONTES:
        guardado = {f["origen"]: np.array(f["q_M0"]) for f in previo[str(h)]["filas"]}
        for f in res[("validacion", "M0", h, None, False)]["filas"]:
            g = guardado.get(f["origen"])
            if g is not None:
                n += 1
                dif = max(dif, float(np.max(np.abs(g - np.array(f["q"])))))
    return {"comparadas": n, "diferencia_maxima": dif}


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
    tot = totales_anuales(serie)
    print("totales anuales:", {a: int(v) for a, v in tot.items()})
    for y in ANIOS_RECORTE:
        excl = anios_excluidos_para(serie, y) - {ANIO_EXCLUIDO}
        assert excl == EXCLUSION_ESPERADA[y], f"recorte de {y}: {sorted(excl)} no coincide con el protocolo"
        exp.verificar_sin_fuga(serie, origenes_recorte(serie, 4, y), 4, ALCANCE_HISTORIA)
        print(f"recorte {y}: excluye {sorted(excl)}; maximo anual que queda "
              f"{int(max(v for a, v in tot.items() if a < y and a not in excl and a != ANIO_EXCLUIDO))}")

    tareas = [(serie, "validacion", m, h, None, False) for m in MODELOS for h in HORIZONTES]
    tareas.append((serie, "validacion", "L0", 4, None, True))
    tareas += [(serie, "recorte", m, h, y, False) for y in ANIOS_RECORTE for m in MODELOS for h in HORIZONTES]
    with ProcessPoolExecutor(max_workers=PROCESOS) as ex:
        res = {(r["fase"], r["modelo"], r["h"], r["anio_prueba"], r["mutar"]): r for r in ex.map(_tarea, tareas)}

    controles = {"m0_reproduce_validacion": _reproduce(res)}
    print(f"M0 contra el experimento de mejora (validacion): {controles['m0_reproduce_validacion']}")
    if controles["m0_reproduce_validacion"]["diferencia_maxima"] != 0.0:
        raise SystemExit("M0 no reproduce los cuantiles publicados: revisar antes de leer resultados.")
    w_l0 = np.mean([f["wis"] for f in res[("validacion", "L0", 4, None, False)]["filas"]])
    w_mut = np.mean([f["wis"] for f in res[("validacion", "L0", 4, None, True)]["filas"]])
    controles["mutacion_L0_h4"] = {"wis": float(w_l0), "wis_mutado": float(w_mut), "empeora": bool(w_mut > w_l0)}
    print(f"control de mutacion L0 (h = 4): WIS {w_l0:.1f} -> {w_mut:.1f} con etiquetas permutadas")

    # --- validacion normal ---------------------------------------------------
    tablas_v = {"limpia": {}, "pub": {}}
    for h in HORIZONTES:
        for familia in tablas_v:
            dec = _decisiva(res[("validacion", "M0", h, None, False)]["filas"], familia)
            tablas_v[familia][h] = {m: {"referencia": dec, **_tabla(res[("validacion", m, h, None, False)]["filas"], f"wis_{familia}_{dec}")}
                                    for m in MODELOS}
    _imprimir("Validacion normal 2019, 2021-2024, contra la persistencia limpia", tablas_v["limpia"])
    _imprimir("Validacion normal, contra la referencia publicada", tablas_v["pub"])
    cond_l0 = {}
    for h in H_DECISIVOS:
        r, r0 = tablas_v["limpia"][h]["L0"], tablas_v["limpia"][h]["M0"]
        cond_l0[h] = {"skill_medio_positivo": r["skill_medio"] > 0, "gana_4_de_5": r["anios_ganados"] >= MIN_ANIOS,
                      "cobertura_en_banda": com.en_banda(r["cobertura_95"], BANDA_95) and com.en_banda(r["cobertura_50"], BANDA_50),
                      "no_peor_que_M0": r["wis"] <= r0["wis"]}
    pasa_l0 = all(all(c.values()) for c in cond_l0.values())
    print(f"L0 en la validacion normal: {'pasa' if pasa_l0 else 'no pasa'} {cond_l0}")

    # --- recorte -------------------------------------------------------------
    tablas_r = {"limpia_recortada": {}, "limpia_completa": {}, "pub_recortada": {}}
    saturacion = {}
    for y in ANIOS_RECORTE:
        for familia, clave in (("limpia_recortada", "limpia"), ("limpia_completa", "limpia_completa"), ("pub_recortada", "pub")):
            tablas_r[familia][y] = {}
            for h in HORIZONTES:
                dec = _decisiva(res[("recorte", "M0", h, y, False)]["filas"], clave)
                tablas_r[familia][y][h] = {m: {"referencia": dec, **_tabla(res[("recorte", m, h, y, False)]["filas"], f"wis_{clave}_{dec}")}
                                           for m in MODELOS}
        saturacion[y] = {h: {m: _saturacion(res[("recorte", m, h, y, False)]["filas"]) for m in MODELOS} for h in HORIZONTES}
        saturacion[y]["validacion_normal"] = {h: {m: _saturacion([f for f in res[("validacion", m, h, None, False)]["filas"] if f["anio"] == y])
                                                  for m in MODELOS} for h in HORIZONTES}
        _imprimir(f"Recorte {y} (excluye {res[('recorte', 'M0', 4, y, False)]['anios_excluidos']}), contra la persistencia limpia recortada",
                  tablas_r["limpia_recortada"][y])
        _imprimir(f"Recorte {y}, contra la persistencia limpia con la historia completa", tablas_r["limpia_completa"][y])
        for h in H_DECISIVOS:
            print(f"  saturacion en el pico de {y}, h = {h}: "
                  + ", ".join(f"{m} {saturacion[y][h][m]['cociente_medio']} (historia completa "
                              f"{saturacion[y]['validacion_normal'][h][m]['cociente_medio']})" for m in MODELOS))
    veredicto_r = {}
    for m in MODELOS:
        por = {y: {h: tablas_r["limpia_recortada"][y][h][m]["skill_agrupado"] for h in H_DECISIVOS} for y in ANIOS_SIN_PRECEDENTE}
        veredicto_r[m] = {"skill": por, "robustez_sostenida": all(v > 0 for d in por.values() for v in d.values())}
        # nan > 0 es False: un anio sin predicciones no sostiene nada
        print(f"{m}: robustez ante brotes sin precedente {'sostenida' if veredicto_r[m]['robustez_sostenida'] else 'no sostenida'} {por}")
    supera = {y: {h: tablas_r["limpia_recortada"][y][h]["L0"]["wis"] < tablas_r["limpia_recortada"][y][h]["M0"]["wis"]
                  for h in H_DECISIVOS} for y in ANIOS_SIN_PRECEDENTE}
    l0_supera = all(v for d in supera.values() for v in d.values())
    print(f"L0 supera a M0 sin precedente: {l0_supera} {supera}")

    salida = {
        "controles": controles, "totales_anuales": tot,
        "validacion": {"tablas": tablas_v, "L0": {"condiciones": cond_l0, "pasa": pasa_l0}},
        "recorte": {"tablas": tablas_r, "saturacion": saturacion, "veredicto": veredicto_r,
                    "L0_supera_a_M0": {"por_anio": supera, "supera": l0_supera},
                    "anios_excluidos": {y: res[("recorte", "M0", 4, y, False)]["anios_excluidos"] for y in ANIOS_RECORTE},
                    "sin_prediccion": {f"{m}_{y}_h{h}": res[("recorte", m, h, y, False)]["sin_prediccion"]
                                       for y in ANIOS_RECORTE for m in MODELOS for h in HORIZONTES}},
    }

    # --- tablero, solo si L0 paso ----------------------------------------------
    if pasa_l0:
        tareas_t = [(serie, "tablero", m, h, None, False) for m in MODELOS for h in HORIZONTES]
        with ProcessPoolExecutor(max_workers=PROCESOS) as ex:
            res_t = {(r["modelo"], r["h"]): r for r in ex.map(_tarea, tareas_t)}
        tablas_t = {h: {f"{m}": _tabla(res_t[(m, h)]["filas"], "wis_suavizada") for m in MODELOS}
                    | {f"C_{m}": _tabla(res_t[(m, h)]["filas"], "wis_suavizada", "q_C") for m in MODELOS} for h in HORIZONTES}
        _imprimir("Tablero 2025-S1 a 2026-S37, contra la persistencia suavizada", tablas_t)
        cond_t = {h: {"wis_no_mayor_que_C": tablas_t[h]["C_L0"]["wis"] <= tablas_t[h]["C_M0"]["wis"],
                      "cob95": tablas_t[h]["C_L0"]["cobertura_95"] >= 0.85,
                      "skill_positivo": tablas_t[h]["C_L0"]["skill_agrupado"] > 0} for h in H_DECISIVOS}
        cumple_t = all(all(c.values()) for c in cond_t.values())
        print(f"C con L0 en el tablero: {'cumple' if cumple_t else 'no cumple'} {cond_t}")
        salida["tablero"] = {"tablas": tablas_t, "condiciones": cond_t, "cumple": cumple_t,
                             "detalle": {f"{m}_h{h}": r for (m, h), r in res_t.items()}}
    else:
        print("L0 no paso la validacion normal: el tablero no se mira.")
    salida["detalle"] = {f"{fase}_{m}_h{h}_{y}": r for (fase, m, h, y, mut), r in res.items() if not mut}

    DIR.mkdir(parents=True, exist_ok=True)
    out = DIR / ("recorte_humo.json" if LIMITE_ORIGENES else "recorte.json")
    out.write_text(json.dumps(salida, default=str), encoding="utf-8")
    if LIMITE_ORIGENES:
        print(f"-> {out}")
        return
    com.copia_versionada(out, DIR_VERSIONADO / "recorte.json")  # flotantes redondeados a 3 decimales
    print(f"-> {out} y {DIR_VERSIONADO / 'recorte.json'}")


if __name__ == "__main__":
    main()
