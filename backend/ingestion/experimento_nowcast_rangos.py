"""
Experimento: calibracion de los rangos y ajustes de corto plazo
(docs/experimentos/experimento-nowcast-rangos.md, fijado 2026-10-02).

Capas sobre los cuantiles que M0 ya produce, con informacion anterior al
origen:

  R0  CQR-r publicada (control)      R1  CQR-r asimetrica
  R2  CQR-r con 104 pares            R3  conformal adaptativo sobre R0
  R4  CQR-r sobre la mezcla C        (solo en el tablero)
  S1  correccion del sesgo reciente  C1  peso de la mezcla por desempeno reciente

Fase A (decide): M0 con objetivos en 2019, 2021-2024. Fase B (se mira una vez):
C con objetivos de 2025-S1 a 2026-S37, con 2024 como calentamiento de las
capas secuenciales. Ninguna semana objetivo desde 2026-S38 entra.

Uso:
    cd backend/ingestion
    POSTGRES_HOST=localhost nice -n 10 python experimento_nowcast_rangos.py
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
from experimento_nowcast_calibracion import ALPHAS
from experimento_nowcast_corto_plazo import Serie, wis
from nowcast_estimacion_dengue import ALCANCE_HISTORIA, N_CAL
from nowcast_estimacion_dengue import HORIZONTES as HORIZONTES_TODOS

from db import get_connection

HORIZONTES = list(HORIZONTES_TODOS)
LIMITE_ORIGENES: int | None = None  # --humo
PROCESOS = 4

GAMMA = 0.03
GAMMAS_SENS = (0.01, 0.10)
K_SESGO, BETA = 8, 1.0
SENS_SESGO = ((4, 1.0), (13, 1.0), (8, 0.5))
K_PESO = 26
SENS_PESO = (13, 52)
N_CAL_R2 = 104

H_DECISIVOS = (4, 8)
H_CORTOS = (1, 2, 3)
BANDA_95_A, BANDA_50_A, COSTO_A = (0.90, 0.99), (0.40, 0.60), 1.05
BANDA_50_B, COB95_B, COSTO_B = (0.35, 0.65), 0.85, 1.02
CAPAS_CAL = ("R0", "R1", "R2", "R3")
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


# --- capas secuenciales ------------------------------------------------------


def _r3(filas: list[dict], gamma: float, clave_q: str = "q_R0") -> list[np.ndarray]:
    """Conformal adaptativo: un nivel por intervalo que se mueve con los
    errores de R0 en los pares ya conocidos (objetivo anterior al origen)."""
    alphas = ALPHAS.copy()
    consumidos = 0
    out = []
    for i, f in enumerate(filas):
        while consumidos < i and filas[consumidos]["fecha_obj"] < f["fecha_origen"]:
            g = filas[consumidos]
            for j in range(len(alphas)):
                alphas[j] = com.actualizar_alpha(alphas[j], ALPHAS[j],
                                                 com.fuera_del_intervalo(g["y"], g[clave_q], j), gamma)
            consumidos += 1
        assert all(filas[k]["fecha_obj"] < f["fecha_origen"] for k in range(consumidos))
        out.append(com.aplicar_factores(f["qz"], com.factores_adaptativos(f["cal_q"], f["cal_y"], alphas)))
    return out


def _s1(filas: list[dict], clave_q: str, k: int, beta: float) -> list[np.ndarray]:
    fechas = [f["fecha_obj"] for f in filas]
    out = []
    for i, f in enumerate(filas):
        idx = com.pares_conocidos(fechas[:i], f["fecha_origen"])
        med = [filas[j][clave_q][com.IDX_MEDIANA] for j in idx]
        ys = [filas[j]["y"] for j in idx]
        out.append(com.desplazar(f[clave_q], -beta * com.sesgo_reciente(med, ys, k)))
    return out


def _c1(filas: list[dict], k: int) -> tuple[list[np.ndarray], list[float]]:
    fechas = [f["fecha_obj"] for f in filas]
    qs, ws = [], []
    for i, f in enumerate(filas):
        idx = com.pares_conocidos(fechas[:i], f["fecha_origen"])
        w = com.peso_reciente([filas[j]["q_R0"] for j in idx], [filas[j]["q_T"] for j in idx],
                              [filas[j]["y"] for j in idx], k)
        ws.append(w)
        qs.append(com.mezcla_log(f["q_R0"], f["q_T"], w))
    return qs, ws


# --- fases --------------------------------------------------------------------


def _base(serie: Serie, origenes: list[int], h: int, c52: dict, c104: dict) -> tuple[list[dict], int]:
    """Filas con los cuantiles de R0, R1 y R2 y lo necesario para las capas
    secuenciales; excluye los origenes que alguna cadena deja sin prediccion."""
    filas, excluidos = [], 0
    for o in origenes:
        p, p104 = c52.get(o), c104.get(o)
        if p is None or p104 is None:
            excluidos += 1
            continue
        r = p.reajuste
        f_lo, f_hi = com.factores_asimetricos(r.cal_q, r.cal_y)
        filas.append({
            "origen": str(serie.fecha[o]), "fecha_origen": serie.fecha[o], "fecha_obj": serie.fecha[o + h],
            "anio": int(serie.anio[o + h]), "semana": int(serie.semana[o + h]), "y": float(serie.casos[o + h]),
            "o": o, "qz": p.qz, "cal_q": r.cal_q, "cal_y": r.cal_y, "cal_idx": r.cal_idx,
            "q_R0": com.aplicar_factores(p.qz, com.factores_simetricos(r.cal_q, r.cal_y)),
            "q_R1": com.aplicar_factores(p.qz, f_lo, f_hi),
            "q_R2": com.aplicar_factores(p104.qz, com.factores_simetricos(p104.reajuste.cal_q, p104.reajuste.cal_y)),
        })
    return filas, excluidos


def _referencias(serie: Serie, filas: list[dict], h: int, afect: frozenset[int], prom: Serie | None) -> None:
    for f in filas:
        o = f["o"]
        for n in REFERENCIAS:
            f[f"wis_pub_{n}"] = wis(f["y"], mej.referencia(n, serie, o, h))
            f[f"wis_limpia_{n}"] = wis(f["y"], mej.referencia(n, serie, o, h, afect))
        if prom is not None:
            rs = ten.cuantiles_regla(prom, o, h, 0.0)
            f["wis_suavizada"] = wis(f["y"], rs) if rs is not None else None


def _tarea_a(args: tuple) -> dict:
    serie, h = args
    return _con_cache(f"rangos_A_h{h}", lambda: _calcular_a(serie, h))


def _calcular_a(serie: Serie, h: int) -> dict:
    threadpool_limits(1)
    tab._instalar_parches()
    origenes = mej.origenes_de(serie, h, mej.ANIOS_VALIDACION)[:LIMITE_ORIGENES]
    construir = lambda t, hh: com.features_grupos(serie, t, hh)  # noqa: E731
    c52 = com.cadena_enriquecida(serie, origenes, h, construir)
    c104 = com.cadena_enriquecida(serie, origenes, h, construir, n_cal=N_CAL_R2)
    filas, excluidos = _base(serie, origenes, h, c52, c104)
    _referencias(serie, filas, h, mej.semanas_afectadas(serie), None)
    for q, f in zip(_r3(filas, GAMMA), filas):
        f["q_R3"] = q
    for g in GAMMAS_SENS:
        for q, f in zip(_r3(filas, g), filas):
            f[f"q_R3_g{g}"] = q
    for q, f in zip(_s1(filas, "q_R0", K_SESGO, BETA), filas):
        f["q_S1"] = q
    for k, b in SENS_SESGO:
        for q, f in zip(_s1(filas, "q_R0", k, b), filas):
            f[f"q_S1_k{k}_b{b}"] = q
    return {"h": h, "fase": "A", "excluidos": excluidos, "filas": _limpiar(filas)}


def _tarea_b(args: tuple) -> dict:
    serie, h = args
    return _con_cache(f"rangos_B_h{h}", lambda: _calcular_b(serie, h))


def _calcular_b(serie: Serie, h: int) -> dict:
    threadpool_limits(1)
    tab._instalar_parches()
    calent = ten._origenes_en_fase(serie, h, mej.ANIOS_VALIDACION, (2024,))
    conf = mej.origenes_de(serie, h, mej.ANIOS_CONFIRMACION)[:LIMITE_ORIGENES]
    construir = lambda t, hh: com.features_grupos(serie, t, hh)  # noqa: E731
    c52 = {**com.cadena_enriquecida(serie, calent, h, construir),
           **com.cadena_enriquecida(serie, conf, h, construir)}
    c104 = {**com.cadena_enriquecida(serie, calent, h, construir, n_cal=N_CAL_R2),
            **com.cadena_enriquecida(serie, conf, h, construir, n_cal=N_CAL_R2)}
    prom = ten.historia_promediada(serie)
    filas, excluidos = _base(serie, calent + conf, h, c52, c104)
    con_t = []
    for f in filas:
        qt = ten.cuantiles_regla(prom, f["o"], h, ten.PHI)
        if qt is not None:
            f["q_T"] = qt
            con_t.append(f)
    filas = con_t
    _referencias(serie, filas, h, mej.semanas_afectadas(serie), prom)
    for q, f in zip(_r3(filas, GAMMA), filas):
        f["q_R3"] = q
    for g in GAMMAS_SENS:
        for q, f in zip(_r3(filas, g), filas):
            f[f"q_R3_g{g}"] = q
    # mezclas C con cada calibracion de M0
    for capa in list(CAPAS_CAL) + [f"R3_g{g}" for g in GAMMAS_SENS]:
        for f in filas:
            f[f"q_C_{capa}"] = com.mezcla_log(f[f"q_{capa}"], f["q_T"], ten.PESO_M0)
    # R4: CQR-r sobre la mezcla C, con los errores de C en los pares de calibracion
    cache: dict[int, np.ndarray] = {}
    for f in filas:
        clave = id(f["cal_q"])
        if clave not in cache:
            fac0 = com.factores_simetricos(f["cal_q"], f["cal_y"])
            c_cal, y_cal = [], []
            for fila_q, y, tgt in zip(f["cal_q"], f["cal_y"], f["cal_idx"]):
                qt = ten.cuantiles_regla(prom, int(tgt) - h, h, ten.PHI)
                if qt is None:
                    continue
                c_cal.append(np.log1p(com.mezcla_log(com.aplicar_factores(fila_q, fac0), qt, ten.PESO_M0)))
                y_cal.append(y)
            cache[clave] = com.factores_simetricos(np.array(c_cal), np.array(y_cal))
        f["q_C_R4"] = com.aplicar_factores(np.log1p(f["q_C_R0"]), cache[clave])
    for q, f in zip(_s1(filas, "q_C_R0", K_SESGO, BETA), filas):
        f["q_C_S1"] = q
    for k, b in SENS_SESGO:
        for q, f in zip(_s1(filas, "q_C_R0", k, b), filas):
            f[f"q_C_S1_k{k}_b{b}"] = q
    qs, ws = _c1(filas, K_PESO)
    for q, w, f in zip(qs, ws, filas):
        f["q_C_C1"], f["w_C1"] = q, w
    for k in SENS_PESO:
        for q, f in zip(_c1(filas, k)[0], filas):
            f[f"q_C_C1_k{k}"] = q
    return {"h": h, "fase": "B", "excluidos": excluidos, "filas": _limpiar(filas)}


def _limpiar(filas: list[dict]) -> list[dict]:
    """Deja solo lo serializable: cuantiles como listas, sin matrices."""
    out = []
    for f in filas:
        g = {}
        for k, v in f.items():
            if k in ("qz", "cal_q", "cal_y", "cal_idx", "fecha_origen", "fecha_obj", "o"):
                continue
            g[k] = v.tolist() if isinstance(v, np.ndarray) else v
        out.append(g)
    return out


# --- tablas y veredictos ---------------------------------------------------


def _decisiva(filas: list[dict], familia: str) -> str:
    return min(REFERENCIAS, key=lambda n: np.mean([f[f"wis_{familia}_{n}"] for f in filas]))


def _tabla(filas: list[dict], clave_q: str, clave_ref: str) -> dict:
    ok = [f for f in filas if f.get(clave_ref) is not None]
    return com.metricas(np.array([f["y"] for f in ok]), np.array([f[clave_q] for f in ok]),
                        np.array([f["anio"] for f in ok]), np.array([f[clave_ref] for f in ok]))


def _imprimir(titulo: str, tabla: dict) -> None:
    print(f"\n{titulo}")
    print(f"{'h':>2} {'capa':<10}{'n':>5}{'WIS':>8}{'WIS ref':>8}{'skill':>7}{'cob50':>7}{'cob95':>7}{'bajo':>6}"
          f"  cob95 por anio")
    for h, porc in tabla.items():
        for c, r in porc.items():
            anios = " ".join(f"{a}:{v:.2f}" for a, v in r["cobertura_95_por_anio"].items())
            print(f"{h:>2} {c:<10}{r['n']:>5}{r['wis']:>8.1f}{r['wis_referencia']:>8.1f}{r['skill_agrupado']:>+7.2f}"
                  f"{r['cobertura_50']:>7.2f}{r['cobertura_95']:>7.2f}{r['bajo_mediana']:>6.2f}  {anios}")


def _reproduce(filas_por_h: dict, archivo: str, clave_nueva: str, clave_previa: str, anios=None) -> dict:
    previo = json.loads((PREVIOS / archivo).read_text(encoding="utf-8"))["detalle"]
    n, dif, primero = 0, 0.0, None
    for h, filas in filas_por_h.items():
        guardado = {f["origen"]: np.array(f[clave_previa]) for f in previo[str(h)]["filas"]}
        for f in sorted(filas, key=lambda f: f["origen"]):
            if anios is not None and f["anio"] not in anios:
                continue
            g = guardado.get(f["origen"])
            if g is None:
                continue
            n += 1
            d = float(np.max(np.abs(g - np.array(f[clave_nueva]))))
            if d > 0 and primero is None:
                primero = f["origen"]
            dif = max(dif, d)
    return {"comparadas": n, "diferencia_maxima": dif, "primer_origen_distinto": primero}


def main() -> None:
    global HORIZONTES, LIMITE_ORIGENES
    if "--humo" in sys.argv:
        HORIZONTES, LIMITE_ORIGENES = [4, 8], 30
        print("modo humo: solo h = 4 y 8, 30 origenes; los resultados no valen")
    conn = get_connection()
    try:
        serie = tab.cargar_serie_mixta(conn)
    finally:
        conn.close()
    print(f"serie mixta: {serie.T} semanas, {serie.fecha[0]} a {serie.fecha[-1]}")
    tab._instalar_parches()
    exp.verificar_sin_fuga(serie, mej.origenes_de(serie, 4, mej.ANIOS_VALIDACION), 4, ALCANCE_HISTORIA)
    exp.verificar_sin_fuga(serie, mej.origenes_de(serie, 4, mej.ANIOS_CONFIRMACION), 4, ALCANCE_HISTORIA)

    with ProcessPoolExecutor(max_workers=PROCESOS) as ex:
        res = list(ex.map(_tarea_a, [(serie, h) for h in HORIZONTES]))
        res += list(ex.map(_tarea_b, [(serie, h) for h in HORIZONTES]))
    A = {r["h"]: r for r in res if r["fase"] == "A"}
    B = {r["h"]: r for r in res if r["fase"] == "B"}

    controles = {
        "m0_r0_reproduce_validacion": _reproduce({h: r["filas"] for h, r in A.items()}, "mejora_validacion.json", "q_R0", "q_M0"),
        "m0_r0_reproduce_confirmacion": _reproduce({h: r["filas"] for h, r in B.items()}, "mejora_confirmacion.json", "q_R0", "q_M0"),
        "c_r0_reproduce_tendencia_2024": _reproduce({h: r["filas"] for h, r in B.items()}, "tendencia_verificacion.json", "q_C_R0", "q_C", (2024,)),
        "c_r0_reproduce_tendencia_2025_2026": _reproduce({h: r["filas"] for h, r in B.items()}, "tendencia_verificacion.json", "q_C_R0", "q_C", (2025, 2026)),
        "excluidos_por_R2": {f"{fase}_h{h}": r["excluidos"] for fase, d in (("A", A), ("B", B)) for h, r in d.items()},
    }
    for k, v in controles.items():
        print(f"{k}: {v}")
    if controles["m0_r0_reproduce_validacion"]["diferencia_maxima"] != 0.0:
        raise SystemExit("M0 con R0 no reproduce la validacion publicada: revisar antes de leer resultados.")

    # --- fase A --------------------------------------------------------------
    capas_a = list(CAPAS_CAL) + [f"R3_g{g}" for g in GAMMAS_SENS] + ["S1"] + [f"S1_k{k}_b{b}" for k, b in SENS_SESGO]
    tablas_a = {}
    for h, r in A.items():
        dec = _decisiva(r["filas"], "limpia")
        tablas_a[h] = {c: {"referencia": dec, **_tabla(r["filas"], f"q_{c}", f"wis_limpia_{dec}")} for c in capas_a}
    _imprimir("Fase A, validacion 2019, 2021-2024, contra la persistencia limpia", tablas_a)
    veredicto_a = {}
    for c in ("R1", "R2", "R3"):
        cond = {h: {"cob95_en_banda": com.en_banda(tablas_a[h][c]["cobertura_95"], BANDA_95_A),
                    "cob50_en_banda": com.en_banda(tablas_a[h][c]["cobertura_50"], BANDA_50_A),
                    "costo_wis": tablas_a[h][c]["wis"] <= COSTO_A * tablas_a[h]["R0"]["wis"]} for h in H_DECISIVOS}
        veredicto_a[c] = {"condiciones": cond, "pasa": all(all(v.values()) for v in cond.values())}
        print(f"{c}: {'pasa' if veredicto_a[c]['pasa'] else 'no pasa'} {cond}")
    pasan = [c for c in ("R1", "R2", "R3") if veredicto_a[c]["pasa"]]
    elegida = min(pasan, key=lambda c: np.mean([tablas_a[h][c]["wis"] for h in H_DECISIVOS])) if pasan else None
    print(f"capa de calibracion elegida: {elegida or 'ninguna (resultado negativo)'}")
    h_cortos = [h for h in H_CORTOS if h in tablas_a]  # en modo humo faltan
    cond_s1 = {
        **{h: {"wis_menor_que_M0": tablas_a[h]["S1"]["wis"] < tablas_a[h]["R0"]["wis"],
               "skill_positivo": tablas_a[h]["S1"]["skill_agrupado"] > 0} for h in h_cortos},
        **{h: {"no_empeora": tablas_a[h]["S1"]["wis"] <= COSTO_B * tablas_a[h]["R0"]["wis"]} for h in H_DECISIVOS},
    }
    pasa_s1 = all(all(v.values()) for v in cond_s1.values())
    print(f"S1 sobre M0: {'pasa' if pasa_s1 else 'no pasa'} {cond_s1}")
    skill_vs_r0 = {h: {c: float(1 - tablas_a[h][c]["wis"] / tablas_a[h]["R0"]["wis"]) for c in capas_a} for h in A}

    # --- fase B --------------------------------------------------------------
    capas_b = [f"C_{c}" for c in CAPAS_CAL] + [f"C_R3_g{g}" for g in GAMMAS_SENS] + ["C_R4", "C_S1"] \
        + [f"C_S1_k{k}_b{b}" for k, b in SENS_SESGO] + ["C_C1"] + [f"C_C1_k{k}" for k in SENS_PESO] + ["R0", "T"]
    tablas_b = {}
    for h, r in B.items():
        filas = [f for f in r["filas"] if f["anio"] >= 2025]
        tablas_b[h] = {c: _tabla(filas, "q_T" if c == "T" else f"q_{c}", "wis_suavizada") for c in capas_b}
    _imprimir("Fase B, tablero 2025-S1 a 2026-S37, contra la persistencia suavizada", tablas_b)
    pesos = {h: {str(f["origen"]): f["w_C1"] for f in r["filas"] if f["anio"] >= 2025} for h, r in B.items()}
    print("\nPeso de M0 elegido por C1 (fraccion de origenes por valor, h = 4): "
          + ", ".join(f"{w}: {np.mean([v == w for v in pesos[4].values()]):.2f}" for w in com.PESOS))

    def _cumple_cal(c: str) -> dict:
        return {h: {"cob95_2025_y_2026": all(v >= COB95_B for v in tablas_b[h][c]["cobertura_95_por_anio"].values()),
                    "cob50_en_banda": com.en_banda(tablas_b[h][c]["cobertura_50"], BANDA_50_B),
                    "costo_wis": tablas_b[h][c]["wis"] <= COSTO_A * tablas_b[h]["C_R0"]["wis"],
                    "skill_positivo": tablas_b[h][c]["skill_agrupado"] > 0} for h in H_DECISIVOS}

    def _cumple_corto(c: str) -> dict:
        return {**{h: {"wis_menor_que_C": tablas_b[h][c]["wis"] < tablas_b[h]["C_R0"]["wis"],
                       "skill_positivo": tablas_b[h][c]["skill_agrupado"] > 0} for h in h_cortos},
                **{h: {"no_empeora": tablas_b[h][c]["wis"] <= COSTO_B * tablas_b[h]["C_R0"]["wis"],
                       "cob95": tablas_b[h][c]["cobertura_95"] >= COB95_B} for h in H_DECISIVOS}}

    veredicto_b = {}
    for c in ["C_R4"] + ([f"C_{elegida}"] if elegida else []):
        cond = _cumple_cal(c)
        veredicto_b[c] = {"condiciones": cond, "cumple": all(all(v.values()) for v in cond.values())}
        print(f"{c}: {'cumple' if veredicto_b[c]['cumple'] else 'no cumple'} {cond}")
    for c in ["C_C1"] + (["C_S1"] if pasa_s1 else []):
        cond = _cumple_corto(c)
        veredicto_b[c] = {"condiciones": cond, "cumple": all(all(v.values()) for v in cond.values())}
        print(f"{c}: {'cumple' if veredicto_b[c]['cumple'] else 'no cumple'} {cond}")
    if not pasa_s1:
        cond = _cumple_corto("C_S1")
        veredicto_b["C_S1_informativo"] = {"condiciones": cond, "cumple": all(all(v.values()) for v in cond.values()),
                                           "nota": "S1 no paso la fase A; no decide"}
        print(f"C_S1 (informativo, no paso la fase A): {cond}")
    skill_vs_c0 = {h: {c: float(1 - tablas_b[h][c]["wis"] / tablas_b[h]["C_R0"]["wis"]) for c in capas_b} for h in B}

    salida = {
        "controles": controles,
        "fase_A": {"tablas": tablas_a, "skill_vs_R0": skill_vs_r0, "veredicto_calibracion": veredicto_a,
                   "elegida": elegida, "S1": {"condiciones": cond_s1, "pasa": pasa_s1}},
        "fase_B": {"tablas": tablas_b, "skill_vs_C_R0": skill_vs_c0, "veredictos": veredicto_b, "pesos_C1": pesos},
        "detalle": {f"A_h{h}": r["filas"] for h, r in A.items()} | {f"B_h{h}": r["filas"] for h, r in B.items()},
    }
    DIR.mkdir(parents=True, exist_ok=True)
    out = DIR / ("rangos_humo.json" if LIMITE_ORIGENES else "rangos.json")
    out.write_text(json.dumps(salida, default=str), encoding="utf-8")
    if LIMITE_ORIGENES:
        print(f"-> {out}")
        return
    com.copia_versionada(out, DIR_VERSIONADO / "rangos.json")  # flotantes redondeados a 3 decimales
    print(f"-> {out} y {DIR_VERSIONADO / 'rangos.json'}")


if __name__ == "__main__":
    main()
