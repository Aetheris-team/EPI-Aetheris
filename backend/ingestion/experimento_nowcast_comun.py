"""
Piezas compartidas por los experimentos de mejora del predictor de dengue
(docs/experimentos/experimento-nowcast-insumos.md, -rangos.md y -recorte.md,
fijados el 2026-10-02).

Reutiliza la serie, el WIS, la cobertura y la calibracion CQR-r de los scripts
del ADR 0020 sin modificarlos. Lo nuevo:

  - features por grupo (para la ablacion y para la regresion lineal);
  - una cadena forward-chaining que, ademas de los cuantiles del origen,
    conserva las predicciones del conjunto de calibracion, para que las capas
    de calibracion se calculen sobre una misma corrida;
  - capas sobre los cuantiles en log1p: CQR-r simetrica (la publicada),
    asimetrica, conformal adaptativa, sesgo reciente y peso por desempeno
    reciente;
  - metricas por conjunto de filas.

Todo usa solo pares con fecha objetivo anterior a la del origen; las capas
secuenciales lo comprueban con una asercion sobre las fechas reales.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, timedelta
from math import ceil

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import QuantileRegressor

from experimento_nowcast_calibracion import ALPHAS, MIN_CAL, MIN_PROPER, _ajustes_cqr_r
from experimento_nowcast_corto_plazo import (
    ANIO_EXCLUIDO,
    CADENCIA_REAJUSTE,
    CUANTILES,
    HGBR_KW,
    IDX_MEDIANA,
    N_LAGS,
    PARES_INTERVALO,
    VARIABLES_CLIMA,
    Serie,
    cobertura,
    wis,
)
from nowcast_estimacion_dengue import ALCANCE_HISTORIA, IDX_B50, IDX_B95, N_CAL

GRUPOS_M0 = ("rezagos", "resumenes", "estacionalidad", "clima", "oni", "anio")
SEMILLA_MUTACION = 12345
TOPE_FACTOR = 4.0


# --- features ---------------------------------------------------------------


def features_grupos(serie: Serie, t: int, h: int, grupos: tuple[str, ...] = GRUPOS_M0,
                    z: np.ndarray | None = None) -> np.ndarray | None:
    """Vector de features en el origen t para predecir t+h, con los grupos
    pedidos en el orden de `features_en` del ADR 0020. Con todos los grupos y
    `z = None` devuelve exactamente el vector de M0.

    Devuelve None si no hay historia (t < N_LAGS), si algun rezago es NaN
    (hueco en la serie) o si falta clima en el origen. La regla del clima se
    aplica aunque el grupo no se use, para que todas las variantes predigan
    sobre los mismos origenes. `z` permite pasar una serie de insumo distinta
    de `serie.z` (ceros repartidos)."""
    if t < N_LAGS:
        return None
    if z is None:
        z = serie.z
    ventana = z[t - N_LAGS + 1: t + 1]
    if np.isnan(ventana).any():
        return None
    partes: list[np.ndarray] = []
    if "rezagos" in grupos:
        partes.append(ventana[::-1])
    if "resumenes" in grupos:
        partes.append(np.array([z[t - 3: t + 1].mean(), z[t - 7: t + 1].mean(), z[t] - z[t - 4]]))
    if "estacionalidad" in grupos:
        doy_obj = serie.doy[t + h] if (t + h) < serie.T else serie.doy[t]
        harm = []
        for k in (1, 2, 3):
            ang = 2 * np.pi * k * doy_obj / 365.25
            harm += [np.sin(ang), np.cos(ang)]
        partes.append(np.array(harm))
    clima_feat = []
    for var in VARIABLES_CLIMA:
        v = serie.clima[var][t - 3: t + 1]
        if np.any(np.isnan(v)):
            return None
        clima_feat.append(float(v.mean()))
    if "clima" in grupos:
        partes.append(np.array(clima_feat))
    if "oni" in grupos:
        oni_t = serie.oni[t]
        partes.append(np.array([0.0 if np.isnan(oni_t) else oni_t]))
    if "anio" in grupos:
        anio_obj = serie.anio[t + h] if (t + h) < serie.T else serie.anio[t]
        partes.append(np.array([float(anio_obj)]))
    return np.concatenate(partes)


def serie_ceros_repartidos(serie: Serie) -> tuple[np.ndarray, np.ndarray]:
    """Serie de insumo con cada semana de OpenDengue (hasta 2024) con 0 casos
    y la siguiente reemplazadas por su promedio. Devuelve (z_insumo, ceros),
    con `ceros` los indices de las semanas con 0. La serie original no cambia."""
    casos = serie.casos.copy()
    ceros = np.flatnonzero((serie.anio <= 2024) & (serie.casos == 0))
    for k in ceros:
        if k + 1 < len(casos) and np.isfinite(casos[k + 1]):
            prom = (serie.casos[k] + serie.casos[k + 1]) / 2.0
            casos[k] = prom
            casos[k + 1] = prom
    return np.log1p(casos), ceros


def features_ceros_repartidos(serie: Serie, z_insumo: np.ndarray, ceros: frozenset[int],
                              t: int, h: int, grupos: tuple[str, ...] = GRUPOS_M0) -> np.ndarray | None:
    """Features sobre la serie repartida. En un origen que es la propia semana
    con 0 la siguiente no se conoce: el rezago z[t] toma el valor de t-1, para
    no usar informacion posterior al origen."""
    if t in ceros and t >= 1:
        z_local = z_insumo.copy()
        z_local[t] = z_insumo[t - 1]
        return features_grupos(serie, t, h, grupos, z_local)
    return features_grupos(serie, t, h, grupos, z_insumo)


# --- pares y ajuste ---------------------------------------------------------


def pares(serie: Serie, origen: int, h: int, construir, y: np.ndarray | None = None,
          anios_excluidos: frozenset[int] = frozenset({ANIO_EXCLUIDO}),
          anio_min: int = ALCANCE_HISTORIA, permitir_fuga: bool = False):
    """Como `pares_entrenamiento` del ADR 0020 con el hueco como ausencia:
    (X, Y, idx_objetivo) con objetivo estrictamente anterior al origen, fuera de
    los anios excluidos y con Y finito. `y` es la serie objetivo en log1p
    (por defecto `serie.z`)."""
    if y is None:
        y = serie.z
    f_corte = serie.fecha[origen]
    X, Y, idx = [], [], []
    for t in range(serie.T):
        tgt = t + h
        if tgt >= serie.T:
            break
        if not permitir_fuga and serie.fecha[tgt] >= f_corte:
            continue
        if serie.anio[tgt] in anios_excluidos or serie.anio[tgt] < anio_min:
            continue
        if not np.isfinite(y[tgt]):
            continue
        x = construir(t, h)
        if x is None:
            continue
        X.append(x)
        Y.append(y[tgt])
        idx.append(tgt)
    return np.array(X), np.array(Y), np.array(idx, dtype=int)


def ajustar_hgbr(X: np.ndarray, Y: np.ndarray) -> list:
    return [HistGradientBoostingRegressor(quantile=float(q), **HGBR_KW).fit(X, Y) for q in CUANTILES]


class _Lineal:
    """Regresion cuantilica lineal con estandarizacion ajustada en el
    entrenamiento propio (L0 del experimento de recorte)."""

    ALPHA = 1e-3

    def __init__(self, X: np.ndarray, Y: np.ndarray) -> None:
        self.mu = X.mean(axis=0)
        self.sd = X.std(axis=0)
        self.sd[self.sd == 0] = 1.0
        Xs = (X - self.mu) / self.sd
        self.modelos = [QuantileRegressor(quantile=float(q), alpha=self.ALPHA, solver="highs").fit(Xs, Y)
                        for q in CUANTILES]

    def predecir(self, X: np.ndarray) -> np.ndarray:
        Xs = (np.atleast_2d(X) - self.mu) / self.sd
        return np.column_stack([m.predict(Xs) for m in self.modelos])


def ajustar_lineal(X: np.ndarray, Y: np.ndarray) -> _Lineal:
    return _Lineal(X, Y)


def _predecir(modelos, X: np.ndarray) -> np.ndarray:
    """(n, 23) en log, sin ordenar."""
    if isinstance(modelos, _Lineal):
        return modelos.predecir(X)
    X = np.atleast_2d(X)
    return np.column_stack([m.predict(X) for m in modelos])


# --- cadena enriquecida -----------------------------------------------------


@dataclass
class Reajuste:
    origen: int
    cal_q: np.ndarray      # (n_cal, 23) log, ordenado por fila
    cal_y: np.ndarray      # (n_cal,) log
    cal_idx: np.ndarray    # indices objetivo de los pares de calibracion
    idx_entrenamiento: np.ndarray  # todos los objetivos usados (asercion anti-fuga)


@dataclass
class Prediccion:
    origen: int
    qz: np.ndarray         # (23,) log, ordenado, modelo del entrenamiento propio
    reajuste: Reajuste


def cadena_enriquecida(serie: Serie, origenes: list[int], h: int, construir, ajustar=ajustar_hgbr,
                       y: np.ndarray | None = None, n_cal: int = N_CAL,
                       anios_excluidos: frozenset[int] = frozenset({ANIO_EXCLUIDO}),
                       mutar: bool = False) -> dict[int, Prediccion | None]:
    """Replica `cadena` del experimento de mejora (mismos pares, misma
    cadencia, mismo split con los n_cal pares mas recientes) y conserva lo
    necesario para calibrar despues. Con `construir` = features de M0,
    `ajustar_hgbr` y `n_cal = 52` reproduce los cuantiles publicados.

    `mutar` permuta las etiquetas en cada reajuste (control de mutacion, semilla
    del experimento original)."""
    rng = np.random.default_rng(SEMILLA_MUTACION)
    out: dict[int, Prediccion | None] = {}
    estado: tuple | None = None
    ultimo = -10_000
    for o in origenes:
        if estado is None or o - ultimo >= CADENCIA_REAJUSTE:
            X, Y, idx = pares(serie, o, h, construir, y, anios_excluidos)
            minimo = MIN_PROPER + MIN_CAL if n_cal == N_CAL else MIN_PROPER + n_cal
            if len(Y) < minimo:
                out[o] = None
                continue
            assert max(serie.fecha[k] for k in idx) < serie.fecha[o], f"fuga en origen {o}"
            orden = np.argsort([serie.fecha[k] for k in idx])
            X, Y, idx = X[orden], Y[orden], idx[orden]
            if mutar:
                Y = Y[rng.permutation(len(Y))]
            tr, ca = slice(0, len(Y) - n_cal), slice(len(Y) - n_cal, None)
            modelos = ajustar(X[tr], Y[tr])
            cal_q = np.sort(_predecir(modelos, X[ca]), axis=1)
            estado = (modelos, Reajuste(o, cal_q, Y[ca], idx[ca], idx))
            ultimo = o
        x = construir(o, h)
        if x is None:
            out[o] = None
            continue
        modelos, reaj = estado
        out[o] = Prediccion(o, np.sort(_predecir(modelos, x)[0]), reaj)
    return out


# --- capas de calibracion ---------------------------------------------------


def factores_simetricos(cal_q: np.ndarray, cal_y: np.ndarray) -> np.ndarray:
    """R0: la CQR-r publicada (winsorizacion al p90, factor en [0, 4])."""
    return _ajustes_cqr_r(cal_q, cal_y)


def _scores_lados(cal_q: np.ndarray, cal_y: np.ndarray, j: int) -> tuple[np.ndarray, np.ndarray]:
    lo, hi = PARES_INTERVALO[j]
    m = cal_q[:, IDX_MEDIANA]
    semi_lo = np.maximum(m - cal_q[:, lo], 1e-3)
    semi_hi = np.maximum(cal_q[:, hi] - m, 1e-3)
    return np.maximum((m - cal_y) / semi_lo, 0.0), np.maximum((cal_y - m) / semi_hi, 0.0)


def nivel_conformal(e: np.ndarray, nivel_nominal: float, winsor: bool = True) -> float:
    """Cuantil conformal de un vector de scores al nivel pedido, con la misma
    winsorizacion al p90 y el mismo tope que la capa publicada."""
    n = len(e)
    if winsor:
        e = np.minimum(e, np.quantile(e, 0.90))
    nivel = min(ceil((n + 1) * nivel_nominal) / n, 1.0)
    f = np.max(e) if nivel >= 1.0 else np.quantile(e, nivel, method="higher")
    return float(np.clip(f, 0.0, TOPE_FACTOR))


def factores_asimetricos(cal_q: np.ndarray, cal_y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """R1: un factor por lado, cada uno al nivel 1 - alpha/2 de su score."""
    f_lo = np.zeros(len(PARES_INTERVALO))
    f_hi = np.zeros(len(PARES_INTERVALO))
    for j in range(len(PARES_INTERVALO)):
        e_lo, e_hi = _scores_lados(cal_q, cal_y, j)
        f_lo[j] = nivel_conformal(e_lo, 1.0 - ALPHAS[j] / 2.0)
        f_hi[j] = nivel_conformal(e_hi, 1.0 - ALPHAS[j] / 2.0)
    return f_lo, f_hi


def factores_adaptativos(cal_q: np.ndarray, cal_y: np.ndarray, alphas_t: np.ndarray) -> np.ndarray:
    """R3: los scores de R0 leidos al nivel 1 - alpha_t por intervalo."""
    fac = np.zeros(len(PARES_INTERVALO))
    for j in range(len(PARES_INTERVALO)):
        e_lo, e_hi = _scores_lados(cal_q, cal_y, j)
        fac[j] = nivel_conformal(np.maximum(e_lo, e_hi), 1.0 - alphas_t[j])
    return fac


def aplicar_factores(qz: np.ndarray, f_lo: np.ndarray, f_hi: np.ndarray | None = None) -> np.ndarray:
    """Estira cada semiancho por su factor (en log) y devuelve el vector natural
    ordenado con piso 0. Con `f_hi = None` el factor es simetrico."""
    if f_hi is None:
        f_hi = f_lo
    m = qz[IDX_MEDIANA]
    qc = qz.copy()
    for j, (lo, hi) in enumerate(PARES_INTERVALO):
        qc[lo] = m - f_lo[j] * (m - qz[lo])
        qc[hi] = m + f_hi[j] * (qz[hi] - m)
    return np.clip(np.expm1(np.sort(qc)), 0.0, None)


def actualizar_alpha(alpha_t: float, alpha: float, err: float, gamma: float) -> float:
    """Un paso del conformal adaptativo: alpha_{t+1} = alpha_t + gamma (alpha - err)."""
    return float(np.clip(alpha_t + gamma * (alpha - err), 0.001, 0.5))


def fuera_del_intervalo(y: float, q_nat: np.ndarray, j: int) -> float:
    lo, hi = PARES_INTERVALO[j]
    q = np.sort(q_nat)
    return float(y < q[lo] or y > q[hi])


# --- capas de corto plazo ---------------------------------------------------


def desplazar(q_nat: np.ndarray, delta_log: float) -> np.ndarray:
    """Desplaza los 23 cuantiles en log1p y vuelve a escala natural."""
    return np.clip(np.expm1(np.log1p(np.sort(q_nat)) + delta_log), 0.0, None)


def sesgo_reciente(medianas: np.ndarray, ys: np.ndarray, k: int, minimo: int = 4) -> float:
    """Promedio de log1p(mediana) - log1p(y) sobre los ultimos k pares (ya
    ordenados por fecha objetivo). Devuelve 0 con menos de `minimo` pares."""
    if len(ys) < minimo:
        return 0.0
    m = np.asarray(medianas[-k:], dtype=float)
    yy = np.asarray(ys[-k:], dtype=float)
    return float(np.mean(np.log1p(m) - np.log1p(yy)))


def mezcla_log(q_a: np.ndarray, q_b: np.ndarray, w: float) -> np.ndarray:
    return np.clip(np.expm1(np.sort(w * np.log1p(q_a) + (1 - w) * np.log1p(q_b))), 0.0, None)


PESOS = (0.0, 0.25, 0.5, 0.75, 1.0)


def peso_reciente(q_m0: list[np.ndarray], q_t: list[np.ndarray], ys: list[float], k: int,
                  minimo: int = 8) -> float:
    """Peso de M0 en la mezcla con T que minimiza el WIS medio sobre los
    ultimos k pares conocidos; empates al mas cercano a 0,5; 0,5 con menos de
    `minimo` pares."""
    if len(ys) < minimo:
        return 0.5
    q_m0, q_t, ys = q_m0[-k:], q_t[-k:], ys[-k:]
    costo = [np.mean([wis(y, mezcla_log(a, b, w)) for y, a, b in zip(ys, q_m0, q_t)]) for w in PESOS]
    mejor = min(costo)
    candidatos = [w for w, c in zip(PESOS, costo) if c <= mejor + 1e-12]
    return min(candidatos, key=lambda w: abs(w - 0.5))


def pares_conocidos(fechas_obj: list[date], fecha_origen: date, semanas: int = 52) -> list[int]:
    """Indices (en el orden dado) de los pares cuyo objetivo es anterior al
    origen y cae dentro de las ultimas `semanas`. Comprueba la condicion
    anti-fuga sobre las fechas reales."""
    desde = fecha_origen - timedelta(days=7 * semanas)
    out = [i for i, f in enumerate(fechas_obj) if desde <= f < fecha_origen]
    assert all(fechas_obj[i] < fecha_origen for i in out)
    return out


# --- metricas ---------------------------------------------------------------


def metricas(y: np.ndarray, qs: np.ndarray, anios: np.ndarray, wis_ref: np.ndarray | None = None) -> dict:
    """WIS, cobertura, sesgo y, con `wis_ref`, skill agrupado y por anio."""
    y = np.asarray(y, dtype=float)
    qs = np.asarray(qs, dtype=float)
    anios = np.asarray(anios, dtype=int)
    if len(y) == 0:
        vacio = {"n": 0, "wis": float("nan"), "wis_por_anio": {}, "cobertura_50": float("nan"),
                 "cobertura_95": float("nan"), "cobertura_95_por_anio": {}, "bajo_mediana": float("nan")}
        if wis_ref is not None:
            vacio.update({"wis_referencia": float("nan"), "skill_agrupado": float("nan"), "skill_por_anio": {},
                          "skill_medio": float("nan"), "anios_ganados": 0})
        return vacio
    w = np.array([wis(yy, q) for yy, q in zip(y, qs)])
    out = {
        "n": int(len(y)),
        "wis": float(w.mean()),
        "wis_por_anio": {int(a): float(w[anios == a].mean()) for a in sorted(set(anios.tolist()))},
        "cobertura_50": float(cobertura(y, qs, *IDX_B50)),
        "cobertura_95": float(cobertura(y, qs, *IDX_B95)),
        "cobertura_95_por_anio": {int(a): float(cobertura(y[anios == a], qs[anios == a], *IDX_B95))
                                  for a in sorted(set(anios.tolist()))},
        "bajo_mediana": float(np.mean(y < np.sort(qs, axis=1)[:, IDX_MEDIANA])),
    }
    if wis_ref is not None:
        wr = np.asarray(wis_ref, dtype=float)
        por_anio = {int(a): float(1 - w[anios == a].mean() / wr[anios == a].mean())
                    for a in sorted(set(anios.tolist()))}
        out.update({
            "wis_referencia": float(wr.mean()),
            "skill_agrupado": float(1 - w.mean() / wr.mean()),
            "skill_por_anio": por_anio,
            "skill_medio": float(np.mean(list(por_anio.values()))),
            "anios_ganados": int(sum(v > 0 for v in por_anio.values())),
        })
    return out


def en_banda(v: float, banda: tuple[float, float]) -> bool:
    return banda[0] <= v <= banda[1]


# --- referencias con historia recortada -------------------------------------
#
# Las del experimento de mejora (publicada con `excluir` vacio; limpia con las
# semanas afectadas), generalizadas a un conjunto de anios excluidos de la
# historia. Con `anios_excluidos = {2020}` coinciden con `mej.referencia`.


def _residuos_ref(serie: Serie, o: int, h: int, excluir: frozenset[int], anios_excluidos: frozenset[int],
                  anio_min: int) -> np.ndarray:
    corte = serie.fecha[o]
    d = np.array([serie.z[t + h] - serie.z[t] for t in range(serie.T - h)
                  if serie.fecha[t + h] < corte
                  and serie.anio[t + h] not in anios_excluidos
                  and serie.anio[t + h] >= anio_min
                  and t not in excluir and t + h not in excluir])
    return d[np.isfinite(d)]


def _pool_ref(serie: Serie, anio_obj: int, semana_obj: int, excluir: frozenset[int],
              anios_excluidos: frozenset[int], anio_min: int) -> np.ndarray:
    m = ((serie.anio < anio_obj) & (serie.anio >= anio_min)
         & ~np.isin(serie.anio, list(anios_excluidos))
         & (np.abs(serie.semana - semana_obj) <= 1) & np.isfinite(serie.casos))
    if excluir:
        m[list(excluir)] = False
    return serie.casos[m]


def referencia(nombre: str, serie: Serie, o: int, h: int, excluir: frozenset[int] = frozenset(),
               anios_excluidos: frozenset[int] = frozenset({ANIO_EXCLUIDO}),
               anio_min: int = ALCANCE_HISTORIA) -> np.ndarray:
    """persistencia_rw, climatologia_estacional o persistencia_estacional, en
    escala natural, con la historia que queda tras excluir semanas y anios."""
    tgt = o + h
    if nombre == "persistencia_rw":
        d = _residuos_ref(serie, o, h, excluir, anios_excluidos, anio_min)
        return np.clip(np.expm1(serie.z[o] + np.quantile(d, CUANTILES)), 0, None)
    p_t = _pool_ref(serie, int(serie.anio[tgt]), int(serie.semana[tgt]), excluir, anios_excluidos, anio_min)
    if nombre == "climatologia_estacional":
        if len(p_t) < 3:
            return np.full(len(CUANTILES), serie.casos[o])
        return np.clip(np.quantile(p_t, CUANTILES), 0, None)
    d = _residuos_ref(serie, o, h, excluir, anios_excluidos, anio_min)
    p_o = _pool_ref(serie, int(serie.anio[o]), int(serie.semana[o]), excluir, anios_excluidos, anio_min)
    ajuste = np.log1p(np.median(p_t)) - np.log1p(np.median(p_o)) if len(p_o) >= 3 and len(p_t) >= 3 else 0.0
    return np.clip(np.expm1(serie.z[o] + ajuste + np.quantile(d - np.median(d), CUANTILES)), 0, None)


# --- copia versionada ---------------------------------------------------------


def redondear(obj, decimales: int = 3):
    """Redondea los flotantes de una estructura anidada (para la copia
    versionada de los resultados; la salida local conserva la precision)."""
    if isinstance(obj, float):
        return round(obj, decimales)
    if isinstance(obj, dict):
        return {k: redondear(v, decimales) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redondear(v, decimales) for v in obj]
    return obj


def copia_versionada(origen, destino) -> None:
    import json
    from pathlib import Path
    datos = json.loads(Path(origen).read_text(encoding="utf-8"))
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    Path(destino).write_text(json.dumps(redondear(datos), ensure_ascii=False, separators=(",", ":")) + "\n",
                             encoding="utf-8")
