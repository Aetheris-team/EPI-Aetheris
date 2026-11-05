"""
Fase 4 de la mejora del predictor para la serie del tablero: tres candidatas
paralelas a C en la ventana de la prueba prospectiva congelada
(docs/experimentos/firma-candidatas-ventana-prospectiva.md).

  K1  C con peso 0,25 de M0 en h = 3 y 4.
  K2  C con la mediana de T en h = 1 y 2 (el ancho sigue siendo el de C).
  K3  C con T calculada con pendiente de 2 semanas, en todos los horizontes.

Las candidatas son funciones de los cuantiles de M0 y T de la prueba congelada
(experimento_nowcast_tendencia.py, commit FIRMADO_COMMIT); este script no
reentrena nada. Dos modos:

  --verificar   las tres candidatas sobre 2024 y 2025 a 2026-S37 (ya vistos, de
                rangos.json): debe reproducir las razones de WIS de la evidencia
                previa. Nunca mira una semana de prueba.
  --evaluar     la evaluacion firmada, una sola vez. Se niega a correr si la
                evaluacion congelada no existe o declara otro commit, si este
                script tiene cambios sin commit o si su salida ya existe.

Uso:
    cd backend/ingestion
    POSTGRES_HOST=localhost nice -n 10 ../.venv/bin/python experimento_nowcast_candidatas.py --verificar
    POSTGRES_HOST=localhost nice -n 10 ../.venv/bin/python experimento_nowcast_candidatas.py --evaluar
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Callable

import numpy as np
from scipy import stats

import experimento_nowcast_tablero as tab
import experimento_nowcast_tendencia as ten
from experimento_nowcast_corto_plazo import ANIO_EXCLUIDO, CUANTILES, IDX_MEDIANA, Serie, wis
from nowcast_estimacion_dengue import ALCANCE_HISTORIA, HORIZONTES, IDX_B50, IDX_B95

from db import get_connection

# --- parametros fijados en el protocolo -------------------------------------

FIRMADO_COMMIT = "40b6ebb78fe670222966a225438155b83ada876d"  # script de la prueba congelada
PHI = 0.8
PESO_C = 0.5  # peso de M0 en C
PESO_K1 = 0.25
V_C, V_K3 = 3, 2  # pendiente de T en C y en K3
HORIZONTES_K = {"K1": (3, 4), "K2": (1, 2), "K3": tuple(HORIZONTES)}
MIN_HORIZONTES = {"K1": 2, "K2": 2, "K3": 5}  # horizontes con razon < 1 (mas de la mitad)
RAZON_MAX = 0.99
COBERTURA_TOLERANCIA = 0.03
CANDIDATAS = ("K1", "K2", "K3")
V_MAX = 6  # rezagos de la pendiente que exige un origen valido (maximo de la rejilla de la Fase 1)
TOL_EVIDENCIA = 0.001  # las razones de la evidencia previa estan redondeadas a 3 decimales

# razon de WIS contra C, promedio de los horizontes que cambia (evidencia previa del protocolo)
EVIDENCIA = {"K1": {"H1": 0.904, "H2": 0.959}, "K2": {"H1": 0.981, "H2": 0.884}, "K3": {"H1": 0.979, "H2": 0.995}}

RAIZ = Path(__file__).resolve().parents[2] / "docs" / "agentes" / "mejora-predictor" / "resultados-nuevos"
RANGOS = RAIZ / "rangos.json"
SALIDA_VERIFICACION = RAIZ / "candidatas_verificacion.json"
SALIDA_PRUEBA = ten.DIR / "candidatas_prueba.json"


# --- formulas de las candidatas -------------------------------------------------


def mezcla(q_m0: np.ndarray, q_t: np.ndarray, w: float) -> np.ndarray:
    """Promedio por cuantil, en log1p, con peso w de M0."""
    return np.clip(np.expm1(np.sort(w * np.log1p(q_m0) + (1 - w) * np.log1p(q_t))), 0, None)


def mediana_de_t_ancho_de_c(q_m0: np.ndarray, q_t: np.ndarray) -> np.ndarray:
    """Mediana de T; distancia de cada cuantil a la mediana, en log1p, la de C."""
    lm, lt = np.log1p(np.sort(q_m0)), np.log1p(np.sort(q_t))
    desv = PESO_C * (lm - lm[IDX_MEDIANA]) + (1 - PESO_C) * (lt - lt[IDX_MEDIANA])
    return np.clip(np.expm1(np.sort(lt[IDX_MEDIANA] + desv)), 0, None)


def cuantiles_regla_v(s: Serie, o: int, h: int, phi: float, v: int) -> np.ndarray | None:
    """Como `ten.cuantiles_regla`, con pendiente de v semanas: mediana de la regla mas los
    cuantiles empiricos de sus errores en los pares con objetivo anterior al origen, desde
    ALCANCE_HISTORIA y sin 2020."""
    def mediana(t):
        return s.z[t] + (s.z[t] - s.z[t - v]) / v * sum(phi ** i for i in range(1, h + 1))

    centro = mediana(o)
    if not np.isfinite(centro):
        return None
    ts = np.arange(v, s.T - h)
    ok = ((s.fecha[ts + h] < s.fecha[o]) & (s.anio[ts + h] >= ALCANCE_HISTORIA)
          & (s.anio[ts + h] != ANIO_EXCLUIDO)).astype(bool)
    ts = ts[ok]
    d = s.z[ts + h] - mediana(ts)
    d = d[np.isfinite(d)]
    return np.clip(np.expm1(centro + np.quantile(d, CUANTILES)), 0, None)


def origen_ok(serie: Serie, o: int, h: int) -> bool:
    return (o >= V_MAX and bool(np.isfinite(serie.casos[o + h]))
            and bool(np.all(np.isfinite(serie.z[o - V_MAX: o + 1]))))


def cuantiles_candidatas(f: dict, h: int) -> dict[str, np.ndarray]:
    """Cuantiles de C, K1, K2, K3 y 'C por tramos' (K1 y K2 juntas) para una fila."""
    m, t, c = f["q_M0"], f["q_T"], f["q_C"]
    k1 = mezcla(m, t, PESO_K1) if h in HORIZONTES_K["K1"] else c
    k2 = mediana_de_t_ancho_de_c(m, t) if h in HORIZONTES_K["K2"] else c
    por_tramos = k1 if h in HORIZONTES_K["K1"] else (k2 if h in HORIZONTES_K["K2"] else c)
    return {"C": c, "K1": k1, "K2": k2, "K3": mezcla(m, f["q_T2"], PESO_C), "C_por_tramos": por_tramos}


# --- metricas y criterio --------------------------------------------------------


def dm(d: np.ndarray, h: int) -> dict | None:
    """Diebold-Mariano con varianza de largo plazo de Newey-West (rezagos h - 1) y correccion
    de Harvey-Leybourne-Newbold. d = perdida A - perdida B."""
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


def holm(ps: dict[str, float]) -> dict[str, float]:
    orden = sorted(ps, key=ps.get)
    out, previo = {}, 0.0
    for rango, k in enumerate(orden):
        previo = max(previo, min(1.0, (len(ps) - rango) * ps[k]))
        out[k] = previo
    return out


MODELOS = ("C", "K1", "K2", "K3", "C_por_tramos")


def evaluar_filas(filas_por_h: dict[int, list[dict]], filtro: Callable[[dict], bool] = lambda f: True) -> dict:
    """Por horizonte y modelo: n, WIS, cobertura del 50 y 95 %, skill contra la persistencia
    suavizada y razon de WIS contra C; mas Diebold-Mariano de cada candidata contra C."""
    out: dict = {"por_h": {}, "dm": {}}
    for h in sorted(filas_por_h):
        filas = sorted((f for f in filas_por_h[h] if filtro(f)), key=lambda f: f["origen"])
        if not filas:
            continue
        y = np.array([f["y"] for f in filas])
        q = {m: np.array([cuantiles_candidatas(f, h)[m] for f in filas]) for m in MODELOS}
        w = {m: np.array([wis(float(a), b) for a, b in zip(y, q[m])]) for m in MODELOS}
        w_ref = float(np.mean([f["wis_ref_suavizada"] for f in filas]))
        fila_h = {}
        for m in MODELOS:
            qs = np.sort(q[m], axis=1)
            dentro95 = (y >= qs[:, IDX_B95[0]]) & (y <= qs[:, IDX_B95[1]])
            dentro50 = (y >= qs[:, IDX_B50[0]]) & (y <= qs[:, IDX_B50[1]])
            fila_h[m] = {"n": len(y), "wis": float(w[m].mean()), "razon_vs_C": float(w[m].mean() / w["C"].mean()),
                         "skill": float(1 - w[m].mean() / w_ref), "cob50": float(dentro50.mean()),
                         "cob95": float(dentro95.mean()), "dentro95": int(dentro95.sum())}
        out["por_h"][h] = fila_h
        for k in CANDIDATAS:
            if h in HORIZONTES_K[k]:
                out["dm"][f"{k}_h{h}"] = dm(w[k] - w["C"], h)
    return out


def decidir(res: dict) -> dict:
    """Las tres condiciones del protocolo para cada candidata."""
    out = {}
    for k in CANDIDATAS:
        hs = [h for h in HORIZONTES_K[k] if h in res["por_h"]]
        razones = {h: res["por_h"][h][k]["razon_vs_C"] for h in hs}
        n = sum(res["por_h"][h]["C"]["n"] for h in hs)
        cob_k = sum(res["por_h"][h][k]["dentro95"] for h in hs) / n
        cob_c = sum(res["por_h"][h]["C"]["dentro95"] for h in hs) / n
        razon_media = float(np.mean(list(razones.values())))
        c1 = razon_media <= RAZON_MAX
        c2 = sum(r < 1 for r in razones.values()) >= MIN_HORIZONTES[k]
        c3 = cob_k >= cob_c - COBERTURA_TOLERANCIA
        out[k] = {"razon_media": razon_media, "razones": razones, "cob95_candidata": cob_k, "cob95_C": cob_c,
                  "c1_razon": bool(c1), "c2_mayoria_de_horizontes": bool(c2), "c3_cobertura": bool(c3),
                  "confirmada": bool(c1 and c2 and c3)}
    return out


def razon_media_por_tramos(res: dict) -> dict:
    """Razon de WIS de 'C por tramos' contra C, promedio de los horizontes 1 a 4."""
    r = [res["por_h"][h]["C_por_tramos"]["razon_vs_C"] for h in (1, 2, 3, 4) if h in res["por_h"]]
    return {"horizontes_1_a_4": float(np.mean(r)) if r else None,
            "todos": float(np.mean([res["por_h"][h]["C_por_tramos"]["razon_vs_C"] for h in res["por_h"]]))}


def holm_dm(res: dict) -> dict:
    ps = {k: v["p"] for k, v in res["dm"].items() if v is not None}
    return holm(ps) if ps else {}


def imprimir(titulo: str, res: dict, dec: dict) -> None:
    print(f"\n{titulo}")
    print(f"{'h':>2} {'modelo':<13}{'n':>4}{'WIS':>9}{'razon':>8}{'skill':>8}{'cob50':>7}{'cob95':>7}")
    for h, porm in res["por_h"].items():
        for m, r in porm.items():
            print(f"{h:>2} {m:<13}{r['n']:>4}{r['wis']:>9.2f}{r['razon_vs_C']:>8.3f}{r['skill']:>+8.2f}"
                  f"{r['cob50']:>7.2f}{r['cob95']:>7.2f}")
    for k, d in dec.items():
        print(f"  {k}: razon media {d['razon_media']:.3f}, razones por h {({h: round(v, 3) for h, v in d['razones'].items()})}, "
              f"cob95 {d['cob95_candidata']:.3f} contra {d['cob95_C']:.3f} -> "
              f"{'CONFIRMADA' if d['confirmada'] else 'no confirmada'} "
              f"(razon {d['c1_razon']}, mayoria {d['c2_mayoria_de_horizontes']}, cobertura {d['c3_cobertura']})")


# --- verificacion (solo semanas ya vistas) ----------------------------------------


def filas_b(serie: Serie, prom: Serie) -> dict[str, dict[int, list[dict]]]:
    """H1 (objetivos de 2024) y H2 (2025 a 2026-S37): M0 de rangos.json, T y T con pendiente
    de 2 semanas sobre la historia promediada."""
    detalle = json.loads(RANGOS.read_text(encoding="utf-8"))["detalle"]
    idx = {str(f): i for i, f in enumerate(serie.fecha)}
    out: dict[str, dict[int, list[dict]]] = {"H1": {h: [] for h in HORIZONTES}, "H2": {h: [] for h in HORIZONTES}}
    for h in HORIZONTES:
        for f in detalle[f"B_h{h}"]:
            o = idx[f["origen"]]
            if not origen_ok(serie, o, h):
                continue
            bloque = "H1" if f["anio"] == 2024 else ("H2" if f["anio"] in (2025, 2026) else None)
            if bloque is None:
                continue
            assert abs(serie.casos[o + h] - f["y"]) < 1e-9, f"y distinto en {f['origen']} h {h}"
            assert serie.fecha[o + h].isoformat() < ten.INICIO_PRUEBA.isoformat(), "objetivo de la ventana de prueba"
            q_m0 = np.sort(np.array(f["q_R0"], float))
            q_t = cuantiles_regla_v(prom, o, h, PHI, V_C)
            q_t2 = cuantiles_regla_v(prom, o, h, PHI, V_K3)
            out[bloque][h].append({"origen": f["origen"], "anio": int(serie.anio[o + h]), "semana": int(serie.semana[o + h]),
                                   "y": float(f["y"]), "q_M0": q_m0, "q_T": q_t, "q_C": mezcla(q_m0, q_t, PESO_C),
                                   "q_T2": q_t2, "wis_ref_suavizada": float(f["wis_suavizada"])})
    return out


def verificar(serie: Serie) -> None:
    prom = ten.historia_promediada(serie)
    b = filas_b(serie, prom)
    salida: dict = {"evidencia_previa": EVIDENCIA, "bloques": {}}
    coincide = True
    for nombre in ("H1", "H2"):
        res = evaluar_filas(b[nombre])
        dec = decidir(res)
        imprimir(f"Verificacion {nombre} ({'2024' if nombre == 'H1' else '2025 a 2026-S37, dentro de muestra'}), referencia: persistencia suavizada",
                 res, dec)
        for k in CANDIDATAS:
            esperado = EVIDENCIA[k][nombre]
            obtenido = dec[k]["razon_media"]
            ok = abs(obtenido - esperado) <= TOL_EVIDENCIA
            coincide &= ok
            print(f"  evidencia previa {k} {nombre}: esperado {esperado:.3f}, obtenido {obtenido:.4f} -> {'OK' if ok else 'NO COINCIDE'}")
        salida["bloques"][nombre] = {"resultado": res, "decision": dec, "c_por_tramos": razon_media_por_tramos(res)}
        print(f"  C por tramos, razon media h 1 a 4: {salida['bloques'][nombre]['c_por_tramos']['horizontes_1_a_4']:.3f}")
    salida["coincide_con_la_evidencia_previa"] = bool(coincide)
    SALIDA_VERIFICACION.write_text(json.dumps(salida, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"-> {SALIDA_VERIFICACION}")
    if not coincide:
        raise SystemExit("La verificacion no reproduce la evidencia previa: revisar antes de firmar.")


# --- evaluacion firmada ---------------------------------------------------------------


def _script_sin_cambios() -> str:
    ruta = Path(__file__).resolve()
    estado = subprocess.run(["git", "status", "--porcelain", "--", str(ruta)], capture_output=True, text=True,
                            cwd=ruta.parent, check=True).stdout.strip()
    if estado:
        raise SystemExit("El script tiene cambios sin commit: la evaluacion usa el metodo firmado.")
    return subprocess.run(["git", "log", "-1", "--format=%H", "--", str(ruta)], capture_output=True, text=True,
                          cwd=ruta.parent, check=True).stdout.strip()


def evaluar(serie: Serie) -> None:
    if SALIDA_PRUEBA.exists():
        raise SystemExit(f"La evaluacion ya se corrio ({SALIDA_PRUEBA}); se mira una sola vez.")
    if not ten.SALIDA_PRUEBA.exists():
        raise SystemExit(f"Falta la evaluacion congelada ({ten.SALIDA_PRUEBA}); se corre primero.")
    congelada = json.loads(ten.SALIDA_PRUEBA.read_text(encoding="utf-8"))
    if congelada.get("commit_script") != FIRMADO_COMMIT:
        raise SystemExit(f"La evaluacion congelada declara el commit {congelada.get('commit_script')}, no {FIRMADO_COMMIT}.")
    commit = _script_sin_cambios()
    prom = ten.historia_promediada(serie)
    idx = {str(f): i for i, f in enumerate(serie.fecha)}
    filas_por_h: dict[int, list[dict]] = {}
    for h in HORIZONTES:
        filas = []
        for f in congelada["detalle"][str(h)]["filas"]:
            m, t = np.array(f["q_M0"], float), np.array(f["q_T"], float)
            c = np.array(f["q_C"], float)
            assert np.max(np.abs(mezcla(m, t, PESO_C) - c)) < 1e-6, "C guardada no es la mezcla de M0 y T"
            q_t2 = cuantiles_regla_v(prom, idx[f["origen"]], h, PHI, V_K3)
            assert q_t2 is not None, f"T con pendiente de 2 semanas sin prediccion en {f['origen']} h {h}"
            filas.append({"origen": f["origen"], "anio": f["anio"], "semana": f["semana"], "y": f["y"], "q_M0": m,
                          "q_T": t, "q_C": c, "q_T2": q_t2, "wis_ref_suavizada": f["wis_ref_suavizada"]})
        filas_por_h[h] = filas
    print(f"pares: {sum(len(v) for v in filas_por_h.values())}; semanas de prueba {congelada['semanas_prueba'][0]} a "
          f"{congelada['semanas_prueba'][-1]}; script {commit[:10]}")
    res = evaluar_filas(filas_por_h)
    dec = decidir(res)
    imprimir("Prueba, referencia: persistencia suavizada", res, dec)
    sin_cambio = evaluar_filas(filas_por_h, lambda f: 4 <= f["semana"] <= 49)
    dec_sin = decidir(sin_cambio)
    imprimir("Sensibilidad: sin semanas objetivo de la 50 a la 3", sin_cambio, dec_sin)
    ajustados = holm_dm(res)
    print("\nDiebold-Mariano contra C (p crudo, Holm):")
    for k, v in res["dm"].items():
        if v is not None:
            print(f"  {k}: dif media {v['dif_media']:+.3f}, p {v['p']:.3f}, Holm {ajustados.get(k, float('nan')):.3f}")
    confirmadas = [k for k, d in dec.items() if d["confirmada"]]
    print(f"\ncandidatas confirmadas: {confirmadas or 'ninguna'}")
    SALIDA_PRUEBA.write_text(json.dumps({
        "commit_script": commit, "commit_evaluacion_congelada": congelada["commit_script"],
        "semanas_prueba": congelada["semanas_prueba"], "resultado": res, "decision": dec,
        "c_por_tramos": razon_media_por_tramos(res), "sin_cambio_de_anio": sin_cambio, "decision_sin_cambio_de_anio": dec_sin,
        "dm_holm": ajustados, "confirmadas": confirmadas, "c_confirmada": congelada.get("confirmado"),
    }, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"-> {SALIDA_PRUEBA}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--verificar", action="store_true")
    modo.add_argument("--evaluar", action="store_true")
    args = ap.parse_args()
    conn = get_connection()
    try:
        serie = tab.cargar_serie_mixta(conn)
    finally:
        conn.close()
    print(f"serie mixta: {serie.T} semanas, {serie.fecha[0]} a {serie.fecha[-1]}")
    if args.verificar:
        verificar(serie)
    else:
        evaluar(serie)


if __name__ == "__main__":
    main()
