"""
Fase 1 de la mejora del predictor para la serie del tablero: elegir la
tendencia amortiguada con la historia suavizada hasta 2023 y recortar el
entrenamiento de M0 en 2023
(docs/experimentos/experimento-nowcast-tendencia-seleccion.md, protocolo del
2026-10-03, commiteado antes de escribir este script).

  --tendencia   partes A y B: rejilla de (phi, v) elegida con 2018-2023, confirmada
                en 2024 y en 2025-2026-S37, y sensibilidad al k del suavizado. No
                reentrena nada: los cuantiles de M0 salen de rangos.json.
  --m0-corte    parte C: M0 con pares de entrenamiento y calibracion de 2023 o
                antes, evaluado en 2025-2026-S37.
  --extension-v1  extension E1 del protocolo: la columna v = 1 de la rejilla, por
                haber quedado el optimo en el borde (v = 2).

Ninguna decision usa semanas objetivo desde 2026-S38 (prueba prospectiva
congelada).

Uso:
    cd backend/ingestion
    POSTGRES_HOST=localhost nice -n 10 ../.venv/bin/python experimento_nowcast_tendencia_seleccion.py --tendencia
    POSTGRES_HOST=localhost nice -n 10 ../.venv/bin/python experimento_nowcast_tendencia_seleccion.py --m0-corte
"""

from __future__ import annotations

import argparse
import copy
import json
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy import stats
from threadpoolctl import threadpool_limits

import experimento_nowcast_corto_plazo as exp
import experimento_nowcast_mejora as mej
import experimento_nowcast_tablero as tab
import experimento_nowcast_tendencia as ten
from experimento_nowcast_corto_plazo import ANIO_EXCLUIDO, CUANTILES, Serie, cobertura, wis
from nowcast_estimacion_dengue import ALCANCE_HISTORIA, HORIZONTES, IDX_B50, IDX_B95

from db import get_connection

# --- parametros fijados en el protocolo -------------------------------------

VIGENTE = (0.8, 3)  # (phi, v) del experimento firmado el 2026-09-27
K_BASE = 7
PHIS = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
VS = (2, 3, 4, 5, 6)
V_MAX = max(VS)
V_REF = 3  # la referencia es la persistencia suavizada con v = 3
ANIOS_VALIDACION = (2018, 2019, 2021, 2022, 2023)
ULTIMO_ANIO_SUAVIZADO = 2023
GRUPOS = {"h1-2": (1, 2), "h3-4": (3, 4), "h5-8": (5, 6, 7, 8)}
MEJORA_MINIMA = 0.005  # puntaje promedio sobre la vigente para cambiar
ANIOS_MEJOR_MIN = 3  # de 5
COBERTURA_95_TOLERANCIA = 0.03
KS = (1, 3, 5, 6, 7, 8, 9, 12)
UMBRAL_K = 0.03
CORTE_M0 = 2023
H_MEJOR_MIN = 6  # horizontes de 8 en que el corte debe ganar
RAZON_M0_MAX = 0.98
PROCESOS = 4
# rangos.json guarda cuantiles y WIS con 3 decimales (enmienda del protocolo)
TOL_T = 0.0005 + 1e-9
TOL_C = 0.003
TOL_WIS_REF = 0.0005 + 1e-9

RAIZ = Path(__file__).resolve().parents[2] / "docs" / "agentes" / "mejora-predictor" / "resultados-nuevos"
RANGOS = RAIZ / "rangos.json"
SALIDA_TENDENCIA = RAIZ / "seleccion_tendencia.json"
SALIDA_CORTE = RAIZ / "m0_corte_2023.json"
SALIDA_V1 = RAIZ / "seleccion_tendencia_v1.json"
BASE_E1 = (0.8, 2)  # la mejor de la rejilla original


# --- historia y regla --------------------------------------------------------


def historia(serie: Serie, k: int) -> Serie:
    """Cada semana hasta 2023 pasa a ser el promedio de las k semanas que
    terminan en ella (k = 1 deja la serie cruda). Desde 2024 no se toca."""
    s = copy.deepcopy(serie)
    x = serie.casos
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        prom = np.array([np.nanmean(x[max(0, t - k + 1): t + 1]) for t in range(len(x))])
    s.casos = np.where(serie.anio <= ULTIMO_ANIO_SUAVIZADO, prom, serie.casos)
    s.z = np.log1p(s.casos)
    return s


def mediana(s: Serie, t, h: int, phi: float, v: int):
    return s.z[t] + (s.z[t] - s.z[t - v]) / v * sum(phi ** i for i in range(1, h + 1))


class Reglas:
    """La regla de tendencia sobre una historia dada, con los errores por
    (h, phi, v) calculados una sola vez. Un objetivo de error es admisible para
    un origen si cae antes de el, de 2014 en adelante y no es de 2020."""

    def __init__(self, s: Serie):
        self.s = s
        self._err: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}
        self._q: dict[tuple, np.ndarray] = {}

    def _errores(self, h: int, phi: float, v: int):
        clave = (h, phi, v)
        if clave not in self._err:
            s = self.s
            ts = np.arange(v, s.T - h)
            d = s.z[ts + h] - mediana(s, ts, h, phi, v)
            ok = (s.anio[ts + h] >= ALCANCE_HISTORIA) & (s.anio[ts + h] != ANIO_EXCLUIDO) & np.isfinite(d)
            self._err[clave] = (ts[ok], d[ok])
        return self._err[clave]

    def cuantiles(self, o: int, h: int, phi: float, v: int) -> np.ndarray:
        clave = (o, h, phi, v)
        if clave not in self._q:
            centro = mediana(self.s, o, h, phi, v)
            assert np.isfinite(centro), f"origen {o} sin rezagos finitos"
            ts, d = self._errores(h, phi, v)
            n = int(np.searchsorted(ts, o - h, side="left"))  # t + h < o
            assert n >= 30, f"origen {o}, h {h}: solo {n} errores"
            self._q[clave] = np.clip(np.expm1(centro + np.quantile(d[:n], CUANTILES)), 0, None)
        return self._q[clave]


def origen_ok(serie: Serie, o: int, h: int) -> bool:
    return (o >= V_MAX and bool(np.isfinite(serie.casos[o + h]))
            and bool(np.all(np.isfinite(serie.z[o - V_MAX: o + 1]))))


def wis_lista(y: np.ndarray, q: np.ndarray) -> np.ndarray:
    return np.array([wis(float(a), b) for a, b in zip(y, q)])


# --- datos guardados de M0, T y C ----------------------------------------------


def cargar_b(serie: Serie) -> dict[str, dict[int, dict]]:
    """Los dos conjuntos fuera de la seleccion, por horizonte: H1 (objetivos de
    2024) y H2 (2025 a 2026-S37). Origenes y cuantiles de M0 salen de rangos.json."""
    detalle = json.loads(RANGOS.read_text(encoding="utf-8"))["detalle"]
    idx = {str(f): i for i, f in enumerate(serie.fecha)}
    out: dict[str, dict[int, dict]] = {"H1": {}, "H2": {}}
    for h in HORIZONTES:
        filas = {"H1": [], "H2": []}
        for f in detalle[f"B_h{h}"]:
            o = idx[f["origen"]]
            if not origen_ok(serie, o, h):
                continue
            assert abs(serie.casos[o + h] - f["y"]) < 1e-9, f"y distinto en {f['origen']} h {h}"
            if f["anio"] == 2024:
                filas["H1"].append((o, f))
            elif f["anio"] in (2025, 2026):
                filas["H2"].append((o, f))
        for nombre, lista in filas.items():
            lista.sort(key=lambda p: p[0])
            out[nombre][h] = {
                "o": np.array([p[0] for p in lista]),
                "y": np.array([p[1]["y"] for p in lista]),
                "q_m0": np.array([p[1]["q_R0"] for p in lista]),
                "q_t_guardado": np.array([p[1]["q_T"] for p in lista]),
                "q_c_guardado": np.array([p[1]["q_C_R0"] for p in lista]),
                "wis_ref_guardado": np.array([p[1]["wis_suavizada"] for p in lista]),
            }
    return out


# --- metricas -------------------------------------------------------------------


def resumen(y: np.ndarray, q: np.ndarray, w: np.ndarray, w_ref: np.ndarray) -> dict:
    return {"n": len(y), "wis": float(w.mean()), "wis_ref": float(w_ref.mean()),
            "skill": float(1 - w.mean() / w_ref.mean()),
            "cob50": cobertura(y, q, *IDX_B50), "cob95": cobertura(y, q, *IDX_B95)}


def dm(d: np.ndarray, h: int) -> dict | None:
    """Diebold-Mariano con varianza de largo plazo de Newey-West (rezagos h - 1)
    y correccion de Harvey-Leybourne-Newbold. d = perdida A - perdida B."""
    d = np.asarray(d, float)
    n = len(d)
    if n < 10:
        return None
    m = d.mean()
    e = d - m
    lag = h - 1
    lrv = float(e @ e) / n
    for j in range(1, lag + 1):
        lrv += 2 * (1 - j / (lag + 1)) * float(e[j:] @ e[:-j]) / n
    if lrv <= 0:
        return None
    est = m / np.sqrt(lrv / n) * np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    return {"n": n, "dif_media": float(m), "estadistico": float(est), "p": float(2 * stats.t.sf(abs(est), n - 1))}


def politica_uniforme(cfg: tuple[float, int]):
    return lambda h: cfg


def politica_tramos(por_grupo: dict[str, tuple[float, int]]):
    return lambda h: next(por_grupo[g] for g, hs in GRUPOS.items() if h in hs)


def evaluar_holdout(reglas: Reglas, ho: dict[int, dict], politica) -> dict[int, dict]:
    """q y WIS de una politica (h -> (phi, v)) en un conjunto fuera de seleccion,
    junto a la referencia oficial (persistencia suavizada, v = 3) y a M0."""
    out = {}
    for h, d in ho.items():
        phi, v = politica(h)
        q = np.array([reglas.cuantiles(o, h, phi, v) for o in d["o"]])
        q_ref = np.array([reglas.cuantiles(o, h, 0.0, V_REF) for o in d["o"]])
        out[h] = {"q": q, "w": wis_lista(d["y"], q), "w_ref": wis_lista(d["y"], q_ref)}
    return out


# --- controles ----------------------------------------------------------------


def controles(serie: Serie, b: dict) -> dict:
    s7 = historia(serie, K_BASE)
    igual_historia = bool(np.array_equal(s7.z, ten.historia_promediada(serie).z, equal_nan=True))
    reglas = Reglas(s7)
    dif_t, dif_c, dif_ref, filas = 0.0, 0.0, 0.0, 0
    for nombre in ("H1", "H2"):
        for h, d in b[nombre].items():
            for i, o in enumerate(d["o"]):
                qt = reglas.cuantiles(o, h, *VIGENTE)
                qc = mej._mezcla(d["q_m0"][i], qt, ten.PESO_M0)
                dif_t = max(dif_t, float(np.max(np.abs(qt - d["q_t_guardado"][i]))))
                dif_c = max(dif_c, float(np.max(np.abs(qc - d["q_c_guardado"][i]))))
                w_ref = wis(float(d["y"][i]), reglas.cuantiles(o, h, 0.0, V_REF))
                dif_ref = max(dif_ref, abs(w_ref - float(d["wis_ref_guardado"][i])))
                filas += 1
    return {"historia_k7_igual_a_tendencia": igual_historia, "filas_comparadas": filas,
            "dif_max_T": dif_t, "dif_max_C": dif_c, "dif_max_wis_referencia": dif_ref,
            "pasa": bool(igual_historia and dif_t <= TOL_T and dif_c <= TOL_C and dif_ref <= TOL_WIS_REF)}


# --- parte A: elegir con la historia hasta 2023 -----------------------------------


def origenes_validacion(serie: Serie) -> dict[int, dict[int, np.ndarray]]:
    return {h: {a: np.array([o for o in range(serie.T - h) if serie.anio[o + h] == a and origen_ok(serie, o, h)])
                for a in ANIOS_VALIDACION} for h in HORIZONTES}


def skills_validacion(reglas: Reglas, orig: dict, cfg: tuple[float, int]) -> dict[int, dict[int, float]]:
    """skill[h][anio] = 1 - WIS(cfg) / WIS(persistencia suavizada), con el WIS
    promediado dentro de cada anio. El objetivo es la propia historia suavizada."""
    s = reglas.s
    out: dict[int, dict[int, float]] = {}
    for h in HORIZONTES:
        out[h] = {}
        for a, os_ in orig[h].items():
            y = s.casos[os_ + h]
            w = wis_lista(y, np.array([reglas.cuantiles(o, h, *cfg) for o in os_]))
            w_ref = wis_lista(y, np.array([reglas.cuantiles(o, h, 0.0, V_REF) for o in os_]))
            out[h][a] = float(1 - w.mean() / w_ref.mean())
    return out


def promedio(sk: dict[int, dict[int, float]], hs, anios=ANIOS_VALIDACION) -> float:
    return float(np.mean([sk[h][a] for h in hs for a in anios]))


def por_anio(sk: dict[int, dict[int, float]], hs) -> dict[int, float]:
    return {a: float(np.mean([sk[h][a] for h in hs])) for a in ANIOS_VALIDACION}


def elegir(sk_por_cfg: dict, hs) -> tuple[tuple[float, int], dict]:
    """La mejor configuracion para los horizontes `hs` y si cumple la regla de
    cambio frente a la vigente."""
    puntajes = {cfg: promedio(sk, hs) for cfg, sk in sk_por_cfg.items()}
    mejor = max(puntajes, key=puntajes.get)
    anios_mejor = sum(por_anio(sk_por_cfg[mejor], hs)[a] > por_anio(sk_por_cfg[VIGENTE], hs)[a]
                      for a in ANIOS_VALIDACION)
    ganancia = puntajes[mejor] - puntajes[VIGENTE]
    regla = {"mejor": list(mejor), "puntaje_mejor": puntajes[mejor], "puntaje_vigente": puntajes[VIGENTE],
             "ganancia": ganancia, "anios_en_que_supera": int(anios_mejor),
             "pasa_regla_de_cambio": bool(mejor != VIGENTE and ganancia >= MEJORA_MINIMA
                                          and anios_mejor >= ANIOS_MEJOR_MIN)}
    return mejor, regla


def confirmar(reglas: Reglas, b: dict, politica, horizontes, contra: tuple[float, int] = VIGENTE) -> dict:
    """Politica candidata contra `contra` (por defecto la vigente), en H1 y en H2, sobre `horizontes`."""
    res = {}
    for nombre in ("H1", "H2"):
        ho = {h: b[nombre][h] for h in horizontes}
        cand = evaluar_holdout(reglas, ho, politica)
        vig = evaluar_holdout(reglas, ho, politica_uniforme(contra))
        por_h, razones, cob_c, cob_v = {}, [], [], []
        for h in horizontes:
            d, c, v = ho[h], cand[h], vig[h]
            q_c_cand = np.array([mej._mezcla(m, q, ten.PESO_M0) for m, q in zip(d["q_m0"], c["q"])])
            q_c_vig = np.array([mej._mezcla(m, q, ten.PESO_M0) for m, q in zip(d["q_m0"], v["q"])])
            w_c_cand, w_c_vig = wis_lista(d["y"], q_c_cand), wis_lista(d["y"], q_c_vig)
            razones.append(float(c["w"].mean() / v["w"].mean()))
            cob_c += list((d["y"] >= np.sort(c["q"], axis=1)[:, IDX_B95[0]]) & (d["y"] <= np.sort(c["q"], axis=1)[:, IDX_B95[1]]))
            cob_v += list((d["y"] >= np.sort(v["q"], axis=1)[:, IDX_B95[0]]) & (d["y"] <= np.sort(v["q"], axis=1)[:, IDX_B95[1]]))
            por_h[h] = {"candidata": resumen(d["y"], c["q"], c["w"], c["w_ref"]),
                        "vigente": resumen(d["y"], v["q"], v["w"], v["w_ref"]),
                        "razon_wis": razones[-1],
                        "dm_candidata_menos_vigente": dm(c["w"] - v["w"], h),
                        "C_candidata_wis": float(w_c_cand.mean()), "C_vigente_wis": float(w_c_vig.mean()),
                        "razon_wis_C": float(w_c_cand.mean() / w_c_vig.mean())}
        res[nombre] = {"por_h": por_h, "razon_media": float(np.mean(razones)),
                       "cob95_candidata": float(np.mean(cob_c)), "cob95_vigente": float(np.mean(cob_v))}
    return res


def imprimir_confirmacion(titulo: str, conf: dict) -> None:
    print(f"\n{titulo}")
    for nombre in ("H1", "H2"):
        r = conf[nombre]
        print(f"  {nombre}: razon media de WIS {r['razon_media']:.3f}, cobertura 95 candidata {r['cob95_candidata']:.3f}"
              f" vs vigente {r['cob95_vigente']:.3f}")
        for h, x in r["por_h"].items():
            p = x["dm_candidata_menos_vigente"]
            print(f"    h{h}: n {x['candidata']['n']:>3} WIS {x['candidata']['wis']:>7.2f} vs {x['vigente']['wis']:>7.2f}"
                  f" (razon {x['razon_wis']:.3f}, C {x['razon_wis_C']:.3f}); skill {x['candidata']['skill']:+.3f}"
                  f" vs {x['vigente']['skill']:+.3f}; DM p {p['p']:.2f}" if p else f"    h{h}: sin DM")


def parte_a(serie: Serie, b: dict) -> dict:
    s7 = historia(serie, K_BASE)
    reglas = Reglas(s7)
    orig = origenes_validacion(serie)
    sk = {(phi, v): skills_validacion(reglas, orig, (phi, v)) for phi in PHIS for v in VS}
    print(f"validacion: {sum(len(x) for h in orig.values() for x in h.values())} pares origen-horizonte, "
          f"{len(sk)} configuraciones")

    elecciones = {}
    todos, regla_comun = elegir(sk, HORIZONTES)
    elecciones["comun"] = {"cfg": list(todos), **regla_comun}
    por_grupo = {}
    for g, hs in GRUPOS.items():
        cfg_g, regla_g = elegir(sk, hs)
        por_grupo[g] = cfg_g
        elecciones[g] = {"cfg": list(cfg_g), **regla_g}

    print("\nPuntaje de validacion (skill medio sobre 2018-2023 y los 8 horizontes), vigente "
          f"{VIGENTE}: {promedio(sk[VIGENTE], HORIZONTES):+.4f}")
    print("   phi \\ v " + "".join(f"{v:>9}" for v in VS))
    for phi in PHIS:
        print(f"   {phi:>7.1f} " + "".join(f"{promedio(sk[(phi, v)], HORIZONTES):>+9.4f}" for v in VS))
    for nombre, e in elecciones.items():
        print(f"  {nombre}: mejor {tuple(e['mejor'])} puntaje {e['puntaje_mejor']:+.4f} (vigente {e['puntaje_vigente']:+.4f}), "
              f"gana {e['anios_en_que_supera']} de 5 anios, regla de cambio: {'SI' if e['pasa_regla_de_cambio'] else 'no'}")

    # confirmacion de lo elegido, aunque no pase la regla (se rotula)
    confirmaciones = {}
    if todos != VIGENTE:
        confirmaciones["comun"] = confirmar(reglas, b, politica_uniforme(todos), HORIZONTES)
        imprimir_confirmacion(f"Confirmacion de la comun {todos}", confirmaciones["comun"])
    for g, hs in GRUPOS.items():
        if por_grupo[g] != VIGENTE:
            confirmaciones[g] = confirmar(reglas, b, politica_uniforme(por_grupo[g]), hs)
            imprimir_confirmacion(f"Confirmacion del tramo {g} {por_grupo[g]}", confirmaciones[g])

    candidatas = {}
    for nombre, conf in confirmaciones.items():
        e = elecciones[nombre]
        b_ok = conf["H1"]["razon_media"] < 1 and conf["H2"]["razon_media"] < 1
        c_ok = conf["H2"]["cob95_candidata"] >= conf["H2"]["cob95_vigente"] - COBERTURA_95_TOLERANCIA
        candidatas[nombre] = {"cfg": e["cfg"], "a_regla_de_cambio": e["pasa_regla_de_cambio"], "b_wis_menor_en_H1_y_H2": bool(b_ok),
                              "c_cobertura_95": bool(c_ok),
                              "candidata": bool(e["pasa_regla_de_cambio"] and b_ok and c_ok)}
    print("\nCandidatas:", json.dumps(candidatas, ensure_ascii=False))
    return {"sk": {f"{phi}|{v}": {str(h): {str(a): x for a, x in d.items()} for h, d in sk[(phi, v)].items()}
                   for (phi, v) in sk},
            "puntaje_comun": {f"{phi}|{v}": promedio(sk[(phi, v)], HORIZONTES) for (phi, v) in sk},
            "elecciones": elecciones, "confirmaciones": confirmaciones, "candidatas": candidatas}


# --- extension E1: la columna v = 1 -----------------------------------------------------


def extension_v1(serie: Serie, b: dict) -> dict:
    reglas = Reglas(historia(serie, K_BASE))
    orig = origenes_validacion(serie)
    nuevas = [(phi, 1) for phi in PHIS]
    sk = {cfg: skills_validacion(reglas, orig, cfg) for cfg in nuevas + [BASE_E1, VIGENTE]}
    puntajes = {cfg: promedio(sk[cfg], HORIZONTES) for cfg in sk}
    print(f"Puntaje de validacion de v = 1 (base {BASE_E1}: {puntajes[BASE_E1]:+.4f}; vigente {VIGENTE}: {puntajes[VIGENTE]:+.4f})")
    for cfg in nuevas:
        print(f"   phi {cfg[0]:.1f}, v = 1: {puntajes[cfg]:+.4f}")
    mejor = max(nuevas, key=puntajes.get)
    ganancia = puntajes[mejor] - puntajes[BASE_E1]
    anios = sum(por_anio(sk[mejor], HORIZONTES)[a] > por_anio(sk[BASE_E1], HORIZONTES)[a] for a in ANIOS_VALIDACION)
    pasa = bool(ganancia >= MEJORA_MINIMA and anios >= ANIOS_MEJOR_MIN)
    print(f"mejor de v = 1: {mejor}, ganancia sobre {BASE_E1} {ganancia:+.4f}, supera en {anios} de 5 anios: "
          f"{'SUSTITUYE' if pasa else 'no sustituye'}")
    out: dict = {"puntajes": {f"{c[0]}|{c[1]}": p for c, p in puntajes.items()},
                 "skill_por_anio": {f"{c[0]}|{c[1]}": por_anio(sk[c], HORIZONTES) for c in sk},
                 "mejor": list(mejor), "ganancia_sobre_base": ganancia, "anios_en_que_supera": int(anios),
                 "sustituye_a_la_base": pasa}
    if pasa:
        out["contra_vigente"] = confirmar(reglas, b, politica_uniforme(mejor), HORIZONTES)
        out["contra_base"] = confirmar(reglas, b, politica_uniforme(mejor), HORIZONTES, contra=BASE_E1)
        imprimir_confirmacion(f"Confirmacion de {mejor} contra la vigente", out["contra_vigente"])
        imprimir_confirmacion(f"Confirmacion de {mejor} contra {BASE_E1}", out["contra_base"])
    return out


# --- parte B: sensibilidad al k -----------------------------------------------------


def parte_b(serie: Serie, b: dict, extra: dict[str, tuple[float, int]]) -> dict:
    """T vigente (y las candidatas de `extra`) con la historia suavizada con distintos k.
    El skill de los conjuntos fuera de seleccion es contra la referencia oficial
    (persistencia suavizada con k = K_BASE) para todos los k."""
    reglas7 = Reglas(historia(serie, K_BASE))
    ref7 = {nombre: {h: evaluar_holdout(reglas7, {h: b[nombre][h]}, politica_uniforme(VIGENTE))[h]["w_ref"]
                     for h in HORIZONTES} for nombre in ("H1", "H2")}
    orig = origenes_validacion(serie)
    out: dict = {"ks": list(KS), "configuraciones": {"vigente": list(VIGENTE), **{n: list(c) for n, c in extra.items()}}}
    base: dict = {}
    for nombre_cfg, cfg in {"vigente": VIGENTE, **extra}.items():
        base[nombre_cfg] = {}
        for k in KS:
            reglas = Reglas(historia(serie, k))
            fila: dict = {"holdout": {}}
            for nombre in ("H1", "H2"):
                ev = evaluar_holdout(reglas, b[nombre], politica_uniforme(cfg))
                fila["holdout"][nombre] = {h: resumen(b[nombre][h]["y"], ev[h]["q"], ev[h]["w"], ref7[nombre][h])
                                           for h in HORIZONTES}
            # validacion: el objetivo cambia con k, solo skill contra el mismo k
            fila["validacion_skill_medio"] = promedio(skills_validacion(reglas, orig, cfg), HORIZONTES)
            base[nombre_cfg][k] = fila
        # razones de WIS contra k = K_BASE, promedio sobre los horizontes
        for k in KS:
            for nombre in ("H1", "H2"):
                r = [base[nombre_cfg][k]["holdout"][nombre][h]["wis"] / base[nombre_cfg][K_BASE]["holdout"][nombre][h]["wis"]
                     for h in HORIZONTES]
                base[nombre_cfg][k][f"razon_wis_{nombre}"] = float(np.mean(r))
        out[nombre_cfg] = {str(k): v for k, v in base[nombre_cfg].items()}

        print(f"\nSensibilidad al k, {nombre_cfg} {cfg}: razon media de WIS contra k = {K_BASE}, cobertura 95 y skill")
        print(f"{'k':>3} {'val':>8} " + "".join(f"{x:>9}" for x in ("H1 razon", "H1 cob95", "H1 skill", "H2 razon", "H2 cob95", "H2 skill")))
        for k in KS:
            f = base[nombre_cfg][k]
            lin = []
            for nombre in ("H1", "H2"):
                hh = f["holdout"][nombre]
                lin += [f[f"razon_wis_{nombre}"], np.mean([hh[h]["cob95"] for h in HORIZONTES]),
                        np.mean([hh[h]["skill"] for h in HORIZONTES])]
            print(f"{k:>3} {f['validacion_skill_medio']:>+8.3f} " + "".join(f"{x:>9.3f}" for x in lin))
    v = base["vigente"]
    out["lectura"] = {
        "k6_k8_dentro_de_3pct_en_H2": bool(all(abs(v[k]["razon_wis_H2"] - 1) < UMBRAL_K for k in (6, 8))),
        "k1_dentro_de_3pct_en_H1_y_H2": bool(all(abs(v[1][f"razon_wis_{n}"] - 1) < UMBRAL_K for n in ("H1", "H2"))),
    }
    print("\nLectura fijada en el protocolo:", out["lectura"])
    return out


# --- parte C: M0 con el entrenamiento recortado --------------------------------------


def _tarea_m0(args: tuple) -> dict:
    serie, h, origenes, corte, una_vez = args
    threadpool_limits(1)
    tab._instalar_parches()
    original = tab.pares_sin_hueco

    def recortado(s, o, hh, anio_min, *a, **kw):
        X, Y, idx = original(s, o, hh, anio_min, *a, **kw)
        ok = s.anio[idx] <= corte
        assert (s.fecha[idx[ok]] < s.fecha[o]).all(), f"fuga en origen {o}"
        return X[ok], Y[ok], idx[ok]

    tab.pares_sin_hueco = recortado
    # con el corte ya no entran pares nuevos: basta un ajuste por horizonte
    mej.CADENCIA_REAJUSTE = 10 ** 9 if una_vez else exp.CADENCIA_REAJUSTE
    q = mej.cadena(serie, origenes, h, ("M0",))
    return {"h": h, "origenes": origenes, "q": [None if q[o] is None else q[o]["M0"].tolist() for o in origenes]}


def parte_c(serie: Serie, b: dict) -> dict:
    tab._instalar_parches()
    exp.verificar_sin_fuga(serie, [int(o) for o in b["H2"][4]["o"]], 4, ALCANCE_HISTORIA)

    # control: sin recorte y con la cadencia estandar, M0 reproduce q_R0 guardado
    # en los origenes que caen en una semana de reajuste (cada dos origenes)
    tareas = []
    for h in HORIZONTES:
        d = b["H2"][h]
        for p in (30, 50):
            for i in (p, p + 1):
                tareas.append((serie, h, [int(d["o"][i])], 9999, False))
    previo = {}
    with ProcessPoolExecutor(max_workers=PROCESOS) as ex:
        for r in ex.map(_tarea_m0, tareas):
            previo.setdefault(r["h"], []).append(r)
    ok_pares, coinciden = 0, 0
    for h, rs in previo.items():
        d = b["H2"][h]
        pos = {int(o): i for i, o in enumerate(d["o"])}
        difs = []
        for r in rs:
            o = r["origenes"][0]
            difs.append(float(np.max(np.abs(np.array(r["q"][0]) - d["q_m0"][pos[o]]))))
        for a in range(0, len(difs), 2):
            ok_pares += 1
            coinciden += min(difs[a], difs[a + 1]) <= TOL_T
    control = {"pares_de_origenes": ok_pares, "pares_con_un_origen_identico": int(coinciden)}
    print("\nControl sin recorte:", control)

    tareas = [(serie, h, [int(o) for o in b["H2"][h]["o"]], CORTE_M0, True) for h in HORIZONTES]
    with ProcessPoolExecutor(max_workers=PROCESOS) as ex:
        res = {r["h"]: r for r in ex.map(_tarea_m0, tareas)}

    s7 = historia(serie, K_BASE)
    reglas = Reglas(s7)
    out: dict = {"control_sin_recorte": control, "por_h": {}}
    razones, gana, razones_c = [], 0, []
    print(f"\nM0 con entrenamiento hasta {CORTE_M0}, objetivos 2025 a 2026-S37 (dentro de muestra)")
    for h in HORIZONTES:
        d = b["H2"][h]
        assert all(q is not None for q in res[h]["q"])
        q_corte = np.array(res[h]["q"])
        q_t = np.array([reglas.cuantiles(o, h, *VIGENTE) for o in d["o"]])
        q_ref = np.array([reglas.cuantiles(o, h, 0.0, V_REF) for o in d["o"]])
        w_ref = wis_lista(d["y"], q_ref)
        w_m0, w_corte = wis_lista(d["y"], d["q_m0"]), wis_lista(d["y"], q_corte)
        q_c = np.array([mej._mezcla(m, t, ten.PESO_M0) for m, t in zip(d["q_m0"], q_t)])
        q_c_corte = np.array([mej._mezcla(m, t, ten.PESO_M0) for m, t in zip(q_corte, q_t)])
        w_c, w_c_corte = wis_lista(d["y"], q_c), wis_lista(d["y"], q_c_corte)
        razones.append(float(w_corte.mean() / w_m0.mean()))
        razones_c.append(float(w_c_corte.mean() / w_c.mean()))
        gana += razones[-1] < 1
        out["por_h"][h] = {"M0": resumen(d["y"], d["q_m0"], w_m0, w_ref), "M0_corte": resumen(d["y"], q_corte, w_corte, w_ref),
                           "C": resumen(d["y"], q_c, w_c, w_ref), "C_corte": resumen(d["y"], q_c_corte, w_c_corte, w_ref),
                           "razon_wis_M0": razones[-1], "razon_wis_C": razones_c[-1],
                           "dm_M0_corte_menos_M0": dm(w_corte - w_m0, h)}
        r = out["por_h"][h]
        print(f"  h{h}: n {r['M0']['n']:>3}  M0 WIS {r['M0']['wis']:>7.2f} skill {r['M0']['skill']:+.3f}  "
              f"corte WIS {r['M0_corte']['wis']:>7.2f} skill {r['M0_corte']['skill']:+.3f} (razon {razones[-1]:.3f}, "
              f"cob95 {r['M0']['cob95']:.2f} -> {r['M0_corte']['cob95']:.2f});  C razon {razones_c[-1]:.3f}")
    out["horizontes_en_que_gana_el_corte"] = int(gana)
    out["razon_media_M0"] = float(np.mean(razones))
    out["razon_media_C"] = float(np.mean(razones_c))
    out["el_corte_es_ventaja"] = bool(gana >= H_MEJOR_MIN and np.mean(razones) < RAZON_M0_MAX)
    print(f"\nEl corte gana en {gana} de 8 horizontes, razon media de WIS {np.mean(razones):.3f} "
          f"(C {np.mean(razones_c):.3f}): {'VENTAJA' if out['el_corte_es_ventaja'] else 'no es ventaja'}")
    return out


# --- principal -------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--tendencia", action="store_true")
    modo.add_argument("--m0-corte", action="store_true")
    modo.add_argument("--extension-v1", action="store_true")
    args = ap.parse_args()
    conn = get_connection()
    try:
        serie = tab.cargar_serie_mixta(conn)
    finally:
        conn.close()
    print(f"serie mixta: {serie.T} semanas, {serie.fecha[0]} a {serie.fecha[-1]}")
    b = cargar_b(serie)
    print("orígenes H1/H2 por horizonte:", {h: (len(b["H1"][h]["o"]), len(b["H2"][h]["o"])) for h in HORIZONTES})
    assert max(serie.fecha[int(o) + h] for h in HORIZONTES for o in b["H2"][h]["o"]).isoformat() < "2026-09-20", \
        "hay objetivos de la ventana prospectiva"

    if args.extension_v1:
        resultado = extension_v1(serie, b)
        SALIDA_V1.write_text(json.dumps(resultado, default=str), encoding="utf-8")
        print(f"-> {SALIDA_V1}")
        return

    if args.m0_corte:
        resultado = parte_c(serie, b)
        SALIDA_CORTE.write_text(json.dumps(resultado, default=str), encoding="utf-8")
        print(f"-> {SALIDA_CORTE}")
        return

    ctrl = controles(serie, b)
    print("controles:", ctrl)
    if not ctrl["pasa"]:
        raise SystemExit("Los controles no reproducen lo guardado: revisar antes de seguir.")
    a = parte_a(serie, b)
    extra = {n: tuple(c["cfg"]) for n, c in a["candidatas"].items() if c["candidata"]}
    sens = parte_b(serie, b, extra)
    SALIDA_TENDENCIA.write_text(json.dumps({"controles": ctrl, "parte_a": a, "parte_b": sens}, default=str), encoding="utf-8")
    print(f"-> {SALIDA_TENDENCIA}")


if __name__ == "__main__":
    main()
