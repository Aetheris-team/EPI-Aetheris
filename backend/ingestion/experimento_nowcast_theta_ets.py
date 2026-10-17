"""
Fase 2B de la mejora del predictor para la serie del tablero: suavizado exponencial
con tendencia amortiguada (ETS) y Theta como base de C, en lugar de T
(docs/experimentos/experimento-nowcast-theta-ets.md, protocolo del 2026-10-03,
commiteado antes de escribir este script).

Cada base da una mediana por origen y horizonte; los cuantiles son los de T (mediana mas
cuantiles empiricos de los errores de los pares con objetivo anterior al origen, desde
ALCANCE_HISTORIA y sin 2020). M0 sale de rangos.json: no se reentrena nada.

  --control   controles previos: ETS(1, 1, 0,8) reproduce T con pendiente de una semana y
              T vigente reproduce lo guardado en rangos.json.
  --parte-a   elegir la configuracion de cada familia con la historia hasta 2023.
  --extension-e1  extension de la rejilla hacia el borde donde cayo el optimo de A (anadida
              despues de correr A y antes de B, ver el protocolo).
  --parte-b   confirmacion en 2024 (H1) y en 2025 a 2026-S37 (H2, dentro de muestra) de las
              configuraciones finales, puestas en lugar de T dentro de C.
  --parte-c   promedio de las bases T, ETS y Theta (exploratorio) y Holm de todas las
              comparaciones de Diebold-Mariano.

Ninguna decision usa semanas objetivo desde 2026-S38 (prueba prospectiva congelada).

Uso:
    cd backend/ingestion
    POSTGRES_HOST=localhost nice -n 10 ../.venv/bin/python experimento_nowcast_theta_ets.py --control
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

import numpy as np

import experimento_nowcast_mejora as mej
import experimento_nowcast_tablero as tab
import experimento_nowcast_tendencia as ten
import experimento_nowcast_tendencia_seleccion as sel
from experimento_nowcast_corto_plazo import ANIO_EXCLUIDO, CUANTILES, Serie, cobertura
from nowcast_estimacion_dengue import ALCANCE_HISTORIA, HORIZONTES, IDX_B50, IDX_B95

from db import get_connection

# --- parametros fijados en el protocolo -------------------------------------

VIGENTE = sel.VIGENTE  # (phi, v) de T: (0,8; 3)
K_BASE = sel.K_BASE
PESO_M0 = ten.PESO_M0
REJILLA_ETS = [(a, be, ph) for a in (0.4, 0.6, 0.8, 1.0) for be in (0.2, 0.4, 0.6, 0.8, 1.0) for ph in (0.8, 0.9, 0.95)]
REJILLA_THETA = [(a, ele) for a in (0.3, 0.5, 0.7, 0.9, 1.0) for ele in (6, 8, 12, 16, 26)]
REJILLA_ETS_E1 = [(a, be, ph) for a in (0.4, 0.6, 0.8, 1.0) for be in (0.2, 0.4, 0.6, 0.8, 1.0) for ph in (0.5, 0.6, 0.7)]
REJILLA_THETA_E1 = [(a, ele) for a in (0.3, 0.5, 0.7, 0.9, 1.0) for ele in (3, 4, 5)]
MIN_ERRORES = 30
COBERTURA_95_TOLERANCIA = 0.03
TOL_ETS_T1 = 1e-9
TOL_SKILL = 1e-12
GRUPOS = sel.GRUPOS
FAMILIAS = ("ets", "theta")

RAIZ = Path(__file__).resolve().parents[2] / "docs" / "agentes" / "mejora-predictor" / "resultados-nuevos"
SALIDA = RAIZ / "theta_ets.json"


# --- medianas de las bases ----------------------------------------------------------


def factores_amortiguados(phi: float) -> np.ndarray:
    """phi + phi^2 + ... + phi^h para h = 1 a 8."""
    return np.cumsum([phi ** i for i in range(1, len(HORIZONTES) + 1)])


def medianas_ets(z: np.ndarray, alfa: float, beta: float, phi: float) -> np.ndarray:
    """ETS con tendencia aditiva amortiguada sobre z (log1p). Devuelve una matriz (T, 8) con la
    mediana a h = 1 a 8 semanas desde cada t, usando solo z[:t + 1]. Inicio: nivel = z[0],
    pendiente 0. En una semana sin dato el estado avanza sin actualizarse."""
    f = factores_amortiguados(phi)
    mu = np.full((len(z), len(HORIZONTES)), np.nan)
    nivel, pend = float(z[0]), 0.0
    mu[0] = nivel + pend * f
    for t in range(1, len(z)):
        previo = nivel + phi * pend
        if np.isfinite(z[t]):
            nuevo = alfa * z[t] + (1 - alfa) * previo
            pend = beta * (nuevo - nivel) + (1 - beta) * phi * pend
            nivel = nuevo
        else:
            nivel, pend = previo, phi * pend
        mu[t] = nivel + pend * f
    return mu


def nivel_ses(z: np.ndarray, alfa: float) -> np.ndarray:
    """Suavizado exponencial simple causal; en una semana sin dato el nivel no cambia."""
    nivel = np.empty(len(z))
    nivel[0] = z[0]
    for t in range(1, len(z)):
        nivel[t] = alfa * z[t] + (1 - alfa) * nivel[t - 1] if np.isfinite(z[t]) else nivel[t - 1]
    return nivel


def pendiente_ols(z: np.ndarray, ele: int) -> np.ndarray:
    """Pendiente de la recta de minimos cuadrados de z sobre las ultimas `ele` semanas, con las
    semanas que tienen dato y exigiendo al menos max(3, ele / 2) de ellas."""
    minimo = max(3, int(np.ceil(ele / 2)))
    out = np.full(len(z), np.nan)
    for t in range(len(z)):
        i0 = max(0, t - ele + 1)
        x = np.arange(i0, t + 1, dtype=float)
        y = z[i0: t + 1]
        ok = np.isfinite(y)
        if ok.sum() >= minimo:
            xc = x[ok] - x[ok].mean()
            out[t] = float(xc @ (y[ok] - y[ok].mean()) / (xc @ xc))
    return out


def medianas_theta(z: np.ndarray, alfa: float, ele: int) -> np.ndarray:
    """Theta (forma de Hyndman y Billah): nivel por suavizado simple mas deriva igual a la mitad
    de la pendiente local; mediana a h semanas = nivel + (pendiente / 2) * (h - 1 + 1 / alfa)."""
    h = np.array(HORIZONTES, dtype=float)
    return nivel_ses(z, alfa)[:, None] + (pendiente_ols(z, ele)[:, None] / 2.0) * (h[None, :] - 1 + 1 / alfa)


# --- cuantiles a partir de una mediana -------------------------------------------------


class ReglasMu:
    """Como `sel.Reglas`, para bases que dan una matriz de medianas (T, 8). Un par (t, t + h) sirve
    para los errores de un origen si su objetivo cae antes del origen, es de ALCANCE_HISTORIA o
    despues, no es de 2020 y tiene dato tanto el origen del par como el objetivo. El par con
    origen en la primera semana no entra: su pendiente inicial es 0 por construccion y no es un
    pronostico (con ETS(1, 1, phi) esto deja los mismos pares que T con pendiente de una semana)."""

    def __init__(self, s: Serie):
        self.s = s
        self._mu: dict[tuple, np.ndarray] = {}
        self._err: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}
        self._q: dict[tuple, np.ndarray] = {}

    def matriz(self, familia: str, cfg: tuple) -> np.ndarray:
        clave = (familia, cfg)
        if clave not in self._mu:
            if familia == "ets":
                self._mu[clave] = medianas_ets(self.s.z, *cfg)
            elif familia == "theta":
                self._mu[clave] = medianas_theta(self.s.z, *cfg)
            else:
                raise ValueError(f"familia desconocida: {familia}")
        return self._mu[clave]

    def _errores(self, familia: str, cfg: tuple, h: int):
        clave = (familia, cfg, h)
        if clave not in self._err:
            s = self.s
            ts = np.arange(1, s.T - h)
            d = s.z[ts + h] - self.matriz(familia, cfg)[ts, h - 1]
            ok = ((s.anio[ts + h] >= ALCANCE_HISTORIA) & (s.anio[ts + h] != ANIO_EXCLUIDO)
                  & np.isfinite(d) & np.isfinite(s.z[ts]))
            self._err[clave] = (ts[ok], d[ok])
        return self._err[clave]

    def cuantiles(self, o: int, h: int, familia: str, cfg: tuple) -> np.ndarray:
        clave = (o, h, familia, cfg)
        if clave not in self._q:
            centro = self.matriz(familia, cfg)[o, h - 1]
            assert np.isfinite(centro), f"origen {o} sin mediana"
            ts, d = self._errores(familia, cfg, h)
            n = int(np.searchsorted(ts, o - h, side="left"))  # t + h < o
            assert n >= MIN_ERRORES, f"origen {o}, h {h}: solo {n} errores"
            self._q[clave] = np.clip(np.expm1(centro + np.quantile(d[:n], CUANTILES)), 0, None)
        return self._q[clave]


BaseFn = Callable[[int, int], np.ndarray]


def fn_ets_theta(rm: ReglasMu, familia: str, cfg: tuple) -> BaseFn:
    return lambda o, h: rm.cuantiles(int(o), h, familia, cfg)


def fn_t(reglas_t: sel.Reglas) -> BaseFn:
    return lambda o, h: reglas_t.cuantiles(int(o), h, *VIGENTE)


def promedio_log1p(qs: list[np.ndarray]) -> np.ndarray:
    """Promedio por cuantil, en log1p, con peso igual."""
    return np.clip(np.expm1(np.mean([np.log1p(q) for q in qs], axis=0)), 0, None)


def fn_promedio(fns: list[BaseFn]) -> BaseFn:
    return lambda o, h: promedio_log1p([f(o, h) for f in fns])


# --- parte A: elegir con la historia hasta 2023 ---------------------------------------------


def referencia_validacion(reglas_t: sel.Reglas, orig: dict, s: Serie) -> dict:
    """WIS de la persistencia suavizada (v = 3, sin pendiente) en cada par de la validacion."""
    return {h: {a: sel.wis_lista(s.casos[os_ + h], np.array([reglas_t.cuantiles(int(o), h, 0.0, sel.V_REF) for o in os_]))
                for a, os_ in orig[h].items()} for h in HORIZONTES}


def skills_base(fn: BaseFn, orig: dict, s: Serie, w_ref: dict) -> dict[int, dict[int, float]]:
    """skill[h][anio] = 1 - WIS(base) / WIS(persistencia suavizada), con el WIS promediado dentro de
    cada anio. El objetivo es la propia historia suavizada."""
    out: dict[int, dict[int, float]] = {}
    for h in HORIZONTES:
        out[h] = {}
        for a, os_ in orig[h].items():
            w = sel.wis_lista(s.casos[os_ + h], np.array([fn(int(o), h) for o in os_]))
            out[h][a] = float(1 - w.mean() / w_ref[h][a].mean())
    return out


def elegir_familia(sk: dict, sk_t: dict) -> dict:
    """La mejor configuracion de la familia y si cumple la regla de cambio frente a T vigente."""
    puntajes = {cfg: sel.promedio(x, HORIZONTES) for cfg, x in sk.items()}
    mejor = max(puntajes, key=puntajes.get)
    p_t = sel.promedio(sk_t, HORIZONTES)
    anio_t, anio_m = sel.por_anio(sk_t, HORIZONTES), sel.por_anio(sk[mejor], HORIZONTES)
    anios = int(sum(anio_m[a] > anio_t[a] for a in sel.ANIOS_VALIDACION))
    ganancia = puntajes[mejor] - p_t
    return {"mejor": list(mejor), "puntaje_mejor": puntajes[mejor], "puntaje_T": p_t, "ganancia": float(ganancia),
            "anios_en_que_supera": anios, "por_anio_mejor": anio_m, "por_anio_T": anio_t,
            "configuraciones_que_superan_a_T": int(sum(p > p_t for p in puntajes.values())),
            "pasa_regla_de_cambio": bool(ganancia >= sel.MEJORA_MINIMA and anios >= sel.ANIOS_MEJOR_MIN)}


def parte_a(serie: Serie) -> dict:
    s7 = sel.historia(serie, K_BASE)
    reglas_t, rm = sel.Reglas(s7), ReglasMu(s7)
    orig = sel.origenes_validacion(serie)
    pares = sum(len(x) for h in orig.values() for x in h.values())
    w_ref = referencia_validacion(reglas_t, orig, s7)
    sk_t = skills_base(fn_t(reglas_t), orig, s7, w_ref)
    print(f"validacion: {pares} pares origen-horizonte; T vigente {VIGENTE}: puntaje {sel.promedio(sk_t, HORIZONTES):+.4f}")
    salida: dict = {"T_vigente": {"cfg": list(VIGENTE), "puntaje": sel.promedio(sk_t, HORIZONTES),
                                  "por_anio": sel.por_anio(sk_t, HORIZONTES)}, "familias": {}}
    for fam, rejilla in (("ets", REJILLA_ETS), ("theta", REJILLA_THETA)):
        sk = {cfg: skills_base(fn_ets_theta(rm, fam, cfg), orig, s7, w_ref) for cfg in rejilla}
        e = elegir_familia(sk, sk_t)
        puntajes = {cfg: sel.promedio(x, HORIZONTES) for cfg, x in sk.items()}
        top = sorted(puntajes, key=puntajes.get, reverse=True)[:5]
        print(f"\n{fam}: {len(rejilla)} configuraciones, {e['configuraciones_que_superan_a_T']} superan a T")
        for cfg in top:
            print(f"   {cfg}: {puntajes[cfg]:+.4f}")
        print(f"   mejor {tuple(e['mejor'])}: puntaje {e['puntaje_mejor']:+.4f} (T {e['puntaje_T']:+.4f}, ganancia {e['ganancia']:+.4f}), "
              f"supera a T en {e['anios_en_que_supera']} de 5 anios; regla de cambio: {'SI' if e['pasa_regla_de_cambio'] else 'no'}")
        print("   por anio, mejor / T: " + " ".join(f"{a}:{e['por_anio_mejor'][a]:+.3f}/{e['por_anio_T'][a]:+.3f}" for a in sel.ANIOS_VALIDACION))
        salida["familias"][fam] = {"puntajes": {"|".join(map(str, c)): p for c, p in puntajes.items()}, "eleccion": e}
    return salida


# --- extension E1: rejilla extendida hacia el borde -------------------------------------------


def decidir_extension(sk_ext: dict, sk_orig: dict, sk_t: dict) -> dict:
    """La mejor configuracion de la extension sustituye a la mejor original solo si supera a esta
    en MEJORA_MINIMA de puntaje y en ANIOS_MEJOR_MIN anios, y cumple por si sola la regla de
    cambio frente a T."""
    puntajes = {cfg: sel.promedio(x, HORIZONTES) for cfg, x in sk_ext.items()}
    mejor = max(puntajes, key=puntajes.get)
    frente_a_t = elegir_familia({mejor: sk_ext[mejor]}, sk_t)
    anio_o, anio_e = sel.por_anio(sk_orig, HORIZONTES), sel.por_anio(sk_ext[mejor], HORIZONTES)
    ganancia = puntajes[mejor] - sel.promedio(sk_orig, HORIZONTES)
    anios = int(sum(anio_e[a] > anio_o[a] for a in sel.ANIOS_VALIDACION))
    return {"mejor_extension": list(mejor), "puntaje_extension": puntajes[mejor], "ganancia_sobre_la_original": float(ganancia),
            "anios_sobre_la_original": anios, "frente_a_T": frente_a_t,
            "configuraciones_de_la_extension_que_superan_a_la_original": int(sum(p > sel.promedio(sk_orig, HORIZONTES) for p in puntajes.values())),
            "sustituye": bool(frente_a_t["pasa_regla_de_cambio"] and ganancia >= sel.MEJORA_MINIMA and anios >= sel.ANIOS_MEJOR_MIN)}


def extension_e1(serie: Serie, a: dict) -> dict:
    s7, reglas_t, rm = _contexto(serie)
    orig = sel.origenes_validacion(serie)
    w_ref = referencia_validacion(reglas_t, orig, s7)
    sk_t = skills_base(fn_t(reglas_t), orig, s7, w_ref)
    out: dict = {"familias": {}, "final": {}}
    for fam, rejilla in (("ets", REJILLA_ETS_E1), ("theta", REJILLA_THETA_E1)):
        e = a["familias"][fam]["eleccion"]
        cfg_o = tuple(e["mejor"])
        sk_o = skills_base(fn_ets_theta(rm, fam, cfg_o), orig, s7, w_ref)
        sk = {cfg: skills_base(fn_ets_theta(rm, fam, cfg), orig, s7, w_ref) for cfg in rejilla}
        d = decidir_extension(sk, sk_o, sk_t)
        puntajes = {cfg: sel.promedio(x, HORIZONTES) for cfg, x in sk.items()}
        top = sorted(puntajes, key=puntajes.get, reverse=True)[:5]
        print(f"\n{fam}: original {cfg_o} puntaje {e['puntaje_mejor']:+.4f} (T {e['puntaje_T']:+.4f}); extension {len(rejilla)} configuraciones")
        for cfg in top:
            print(f"   {cfg}: {puntajes[cfg]:+.4f}")
        print(f"   mejor de la extension {tuple(d['mejor_extension'])}: gana {d['ganancia_sobre_la_original']:+.4f} a la original en "
              f"{d['anios_sobre_la_original']} de 5 anios; frente a T: ganancia {d['frente_a_T']['ganancia']:+.4f}, "
              f"{d['frente_a_T']['anios_en_que_supera']} anios, regla {'SI' if d['frente_a_T']['pasa_regla_de_cambio'] else 'no'} "
              f"-> {'SUSTITUYE' if d['sustituye'] else 'se queda la original'}")
        final = (d["frente_a_T"] | {"mejor": d["mejor_extension"]}) if d["sustituye"] else e
        out["familias"][fam] = {"puntajes": {"|".join(map(str, c)): p for c, p in puntajes.items()}, **d}
        out["final"][fam] = {"cfg": list(final["mejor"]), "origen": "extension" if d["sustituye"] else "rejilla original",
                             "pasa_regla_de_cambio": bool(final["pasa_regla_de_cambio"])}
        print(f"   configuracion final de {fam}: {tuple(out['final'][fam]['cfg'])} ({out['final'][fam]['origen']}), "
              f"regla de cambio {'SI' if out['final'][fam]['pasa_regla_de_cambio'] else 'no'}")
    return out


# --- parte B y C: confirmacion fuera de la seleccion ----------------------------------------


def confirmar_c(fn_base: BaseFn, fn_t_: BaseFn, b: dict) -> dict:
    """C' (M0 y la base, peso 0,5) contra C (M0 y T) en H1 y H2, por horizonte, con las razones de
    WIS, las coberturas y la prueba de Diebold-Mariano; mas la base contra T."""
    res: dict = {}
    for nombre in ("H1", "H2"):
        por_h, razones_c, dentro = {}, {}, {"Cp": 0, "C": 0, "n": 0}
        for h in HORIZONTES:
            d = b[nombre][h]
            y = d["y"]
            q_b = np.array([fn_base(int(o), h) for o in d["o"]])
            q_t = np.array([fn_t_(int(o), h) for o in d["o"]])
            q_c = np.array([mej._mezcla(m, t, PESO_M0) for m, t in zip(d["q_m0"], q_t)])
            q_cp = np.array([mej._mezcla(m, x, PESO_M0) for m, x in zip(d["q_m0"], q_b)])
            w = {k: sel.wis_lista(y, q) for k, q in (("base", q_b), ("T", q_t), ("C", q_c), ("Cp", q_cp))}
            w_ref = float(np.mean(d["wis_ref_guardado"]))
            qs = {"base": q_b, "T": q_t, "C": q_c, "Cp": q_cp}
            fila = {"n": len(y), "razon_C": float(w["Cp"].mean() / w["C"].mean()),
                    "razon_base_vs_T": float(w["base"].mean() / w["T"].mean()),
                    "dm_Cp_menos_C": sel.dm(w["Cp"] - w["C"], h)}
            for k, q in qs.items():
                qq = np.sort(q, axis=1)
                dentro95 = (y >= qq[:, IDX_B95[0]]) & (y <= qq[:, IDX_B95[1]])
                fila[k] = {"wis": float(w[k].mean()), "skill": float(1 - w[k].mean() / w_ref),
                           "cob50": cobertura(y, q, *IDX_B50), "cob95": float(dentro95.mean()), "dentro95": int(dentro95.sum())}
            for k in ("Cp", "C"):
                dentro[k] += fila[k]["dentro95"]
            dentro["n"] += len(y)
            razones_c[h] = fila["razon_C"]
            por_h[h] = fila
        res[nombre] = {"por_h": por_h, "razon_media_C": float(np.mean(list(razones_c.values()))),
                       "razon_media_por_grupo": {g: float(np.mean([razones_c[h] for h in hs])) for g, hs in GRUPOS.items()},
                       "cob95_Cp": dentro["Cp"] / dentro["n"], "cob95_C": dentro["C"] / dentro["n"],
                       "razon_media_base_vs_T": float(np.mean([por_h[h]["razon_base_vs_T"] for h in HORIZONTES]))}
    return res


def elegible(pasa_a: bool | None, conf: dict) -> dict:
    """Condiciones (a), (b) y (c) del protocolo. pasa_a es None para el promedio de bases, que no
    tiene regla de seleccion propia."""
    b_ok = conf["H1"]["razon_media_C"] < 1 and conf["H2"]["razon_media_C"] < 1
    c_ok = conf["H2"]["cob95_Cp"] >= conf["H2"]["cob95_C"] - COBERTURA_95_TOLERANCIA
    return {"a_regla_de_cambio": pasa_a, "b_razon_menor_que_1_en_H1_y_H2": bool(b_ok), "c_cobertura_95": bool(c_ok),
            "elegible": bool((pasa_a is not False) and b_ok and c_ok)}


def imprimir_confirmacion(titulo: str, conf: dict, el: dict) -> None:
    print(f"\n{titulo}")
    for nombre in ("H1", "H2"):
        r = conf[nombre]
        grupos = " ".join(f"{g} {v:.3f}" for g, v in r["razon_media_por_grupo"].items())
        print(f"  {nombre}: razon media de WIS contra C {r['razon_media_C']:.3f} ({grupos}); base contra T {r['razon_media_base_vs_T']:.3f}; "
              f"cobertura 95 {r['cob95_Cp']:.3f} contra {r['cob95_C']:.3f}")
        print("     razon por h: " + " ".join(f"h{h}:{r['por_h'][h]['razon_C']:.3f}" for h in HORIZONTES))
    print(f"  elegibilidad: a {el['a_regla_de_cambio']}, b {el['b_razon_menor_que_1_en_H1_y_H2']}, c {el['c_cobertura_95']} "
          f"-> {'ELEGIBLE' if el['elegible'] else 'no elegible'}")


def _contexto(serie: Serie):
    s7 = sel.historia(serie, K_BASE)
    reglas_t, rm = sel.Reglas(s7), ReglasMu(s7)
    return s7, reglas_t, rm


def parte_b(serie: Serie, b: dict, final: dict) -> dict:
    _, reglas_t, rm = _contexto(serie)
    out = {}
    for fam in FAMILIAS:
        e = final[fam]
        cfg = tuple(e["cfg"])
        conf = confirmar_c(fn_ets_theta(rm, fam, cfg), fn_t(reglas_t), b)
        el = elegible(e["pasa_regla_de_cambio"], conf)
        imprimir_confirmacion(f"{fam} {cfg} ({e['origen']}) en lugar de T dentro de C" + ("" if e["pasa_regla_de_cambio"] else " (no pasa la regla de cambio: descripcion)"), conf, el)
        out[fam] = {"cfg": list(cfg), "origen": e["origen"], "confirmacion": conf, "elegibilidad": el}
    return out


def holm_dm(b_res: dict, c_res: dict) -> dict:
    """Holm entre todas las comparaciones de Diebold-Mariano: ETS, Theta y el promedio de bases,
    en H1 y en H2, por horizonte."""
    ps = {}
    for nombre, res in (("ets", b_res["ets"]["confirmacion"]), ("theta", b_res["theta"]["confirmacion"]), ("promedio", c_res["confirmacion"])):
        for conjunto in ("H1", "H2"):
            for h, fila in res[conjunto]["por_h"].items():
                dm_ = fila["dm_Cp_menos_C"]
                if dm_ is not None:
                    ps[f"{nombre}_{conjunto}_h{h}"] = dm_["p"]
    orden = sorted(ps, key=ps.get)
    out, previo = {}, 0.0
    for rango, k in enumerate(orden):
        previo = max(previo, min(1.0, (len(ps) - rango) * ps[k]))
        out[k] = previo
    return {"p_crudo": ps, "p_holm": out}


def parte_c(serie: Serie, b: dict, final: dict, b_res: dict) -> dict:
    _, reglas_t, rm = _contexto(serie)
    fns = [fn_t(reglas_t)] + [fn_ets_theta(rm, fam, tuple(final[fam]["cfg"])) for fam in FAMILIAS]
    conf = confirmar_c(fn_promedio(fns), fn_t(reglas_t), b)
    el = elegible(None, conf)
    imprimir_confirmacion("Promedio de T, ETS y Theta (exploratorio) en lugar de T dentro de C", conf, el)
    res = {"confirmacion": conf, "elegibilidad": el}
    h = holm_dm(b_res, res)
    menor = sorted(h["p_holm"].items(), key=lambda kv: kv[1])[:5]
    print("\nDiebold-Mariano contra C, menores p con Holm (de %d comparaciones): " % len(h["p_crudo"])
          + ", ".join(f"{k} crudo {h['p_crudo'][k]:.3f} Holm {v:.3f}" for k, v in menor))
    res["dm_holm"] = h
    return res


# --- controles ------------------------------------------------------------------------------


def controles(serie: Serie, b: dict) -> dict:
    ctrl_sel = sel.controles(serie, b)
    s7, reglas_t, rm = _contexto(serie)
    orig = sel.origenes_validacion(serie)
    hueco = int(np.flatnonzero(~np.isfinite(serie.casos))[0])
    pares = [(int(o), h) for h in HORIZONTES for os_ in orig[h].values() for o in os_]
    pares += [(int(o), h) for nombre in ("H1", "H2") for h in HORIZONTES for o in b[nombre][h]["o"]]
    dif, filas = 0.0, 0
    for o, h in pares:
        if o >= hueco:  # despues del hueco de 2025-S53 los conjuntos de errores de T y de ETS difieren
            continue
        dif = max(dif, float(np.max(np.abs(rm.cuantiles(o, h, "ets", (1.0, 1.0, 0.8)) - reglas_t.cuantiles(o, h, 0.8, 1)))))
        filas += 1
    w_ref = referencia_validacion(reglas_t, orig, s7)
    sk_mio = skills_base(fn_t(reglas_t), orig, s7, w_ref)
    sk_sel = sel.skills_validacion(reglas_t, orig, VIGENTE)
    dif_sk = max(abs(sk_mio[h][a] - sk_sel[h][a]) for h in HORIZONTES for a in sel.ANIOS_VALIDACION)
    return {"seleccion": ctrl_sel, "filas_ets_vs_t_v1": filas, "dif_max_ets_vs_t_v1": dif, "dif_max_skill_T": float(dif_sk),
            "pasa": bool(ctrl_sel["pasa"] and filas > 0 and dif <= TOL_ETS_T1 and dif_sk <= TOL_SKILL)}


# --- principal -------------------------------------------------------------------------------


def _leer() -> dict:
    return json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {}


def _guardar(clave: str, valor) -> None:
    datos = _leer()
    datos[clave] = valor
    SALIDA.write_text(json.dumps(datos, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"-> {SALIDA} ({clave})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modo = ap.add_mutually_exclusive_group(required=True)
    for m in ("control", "parte-a", "extension-e1", "parte-b", "parte-c"):
        modo.add_argument(f"--{m}", action="store_true")
    args = ap.parse_args()
    previo = _leer()
    if not args.control and not previo.get("control", {}).get("pasa"):
        raise SystemExit("Falta el control (--control) o no pasa: no se barre nada.")
    if args.extension_e1 and "parte_a" not in previo:
        raise SystemExit("Falta la parte A (--parte-a).")
    if args.parte_b and "extension_e1" not in previo:
        raise SystemExit("Falta la extension E1 (--extension-e1): B usa la configuracion final.")
    if args.parte_c and "parte_b" not in previo:
        raise SystemExit("Falta la parte B.")
    conn = get_connection()
    try:
        serie = tab.cargar_serie_mixta(conn)
    finally:
        conn.close()
    print(f"serie mixta: {serie.T} semanas, {serie.fecha[0]} a {serie.fecha[-1]}")
    b = sel.cargar_b(serie)
    assert max(serie.fecha[int(o) + h] for h in HORIZONTES for o in b["H2"][h]["o"]).isoformat() < ten.INICIO_PRUEBA.isoformat(), \
        "hay objetivos de la ventana prospectiva"
    if args.control:
        ctrl = controles(serie, b)
        print("controles:", json.dumps(ctrl, ensure_ascii=False, default=str))
        _guardar("control", ctrl)
        if not ctrl["pasa"]:
            raise SystemExit("Los controles no pasan: revisar antes de seguir.")
    elif args.parte_a:
        _guardar("parte_a", parte_a(serie))
    elif args.extension_e1:
        _guardar("extension_e1", extension_e1(serie, previo["parte_a"]))
    elif args.parte_b:
        _guardar("parte_b", parte_b(serie, b, previo["extension_e1"]["final"]))
    else:
        _guardar("parte_c", parte_c(serie, b, previo["extension_e1"]["final"], previo["parte_b"]))


if __name__ == "__main__":
    main()
