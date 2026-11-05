"""Pruebas de las funciones puras de experimento_nowcast_banda_riesgo.py: factor
conforme, etiquetas de regimen sin uso del futuro, piso del limite, pares pasados
de la calibracion hacia adelante y ajuste de Holm. No necesitan Postgres."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import experimento_nowcast_banda_riesgo as br  # noqa: E402


@pytest.mark.parametrize("n, esperado", [(39, 38.0), (40, 39.0), (80, 79.0), (118, 117.0), (119, 117.0), (250, 245.0)])
def test_factor_conforme_sigue_la_convencion_de_cqr_r(n, esperado):
    # scores 0, 1, ..., n-1: hasta n = 118 el nivel llega a 1 o 'higher' cae en el maximo;
    # desde 119 deja de ser el maximo (n = 119: el segundo mayor, n - 2 = 117)
    s = np.arange(n, dtype=float)
    assert br.factor_conforme(s) == esperado


def test_factor_conforme_tiene_piso_de_uno():
    assert br.factor_conforme(np.full(60, -3.0)) == 1.0
    assert br.factor_conforme(np.full(60, 0.4)) == 1.0


def test_limite_con_factor_uno_es_el_cuantil_guardado_y_crece_con_el_factor():
    q = np.tile(np.linspace(1.0, 100.0, 23), (3, 1))
    l1 = br.limites(q, np.ones(3))
    assert np.allclose(l1["l975"], q[:, br.I_Q975]) and np.allclose(l1["l99"], q[:, br.I_Q99])
    l2 = br.limites(q, np.full(3, 2.0))
    assert np.all(l2["l975"] > l1["l975"]) and np.all(l2["l99"] > l1["l99"])
    assert np.all(l2["l975"] >= q[:, br.I_MED])


def test_pinball_pesa_cada_lado():
    y = np.array([10.0, 10.0])
    lim = np.array([4.0, 16.0])
    p = br.pinball(y, lim, 0.975)
    assert p[0] == pytest.approx(0.975 * 6.0)  # y por encima del limite
    assert p[1] == pytest.approx(0.025 * 6.0)  # limite por encima de y


def _z_aleatoria(T: int = 220, semilla: int = 1) -> np.ndarray:
    return np.cumsum(np.random.default_rng(semilla).normal(0.0, 0.2, T)) + 5.0


def test_etiquetas_no_usan_el_futuro():
    z = _z_aleatoria()
    corte = 150
    base = br.etiquetas_desde_z(z)
    assert np.array_equal(base[:corte], br.etiquetas_desde_z(z[:corte]))
    # control negativo: cambiar el futuro a lo bestia no toca el pasado
    z2 = z.copy()
    z2[corte:] += np.linspace(0.0, 30.0, len(z) - corte)
    assert np.array_equal(base[:corte], br.etiquetas_desde_z(z2)[:corte])
    # y si se altera un dato anterior al corte, las etiquetas posteriores si cambian
    z3 = z.copy()
    z3[100:130] += 3.0
    assert not np.array_equal(base[:corte], br.etiquetas_desde_z(z3)[:corte])


def test_etiquetas_arranque_y_tercios():
    z = _z_aleatoria(T=400)
    e = br.etiquetas_desde_z(z)
    assert np.all(e[: br.MIN_CRECIMIENTOS + br.SEMANAS_CRECIMIENTO - 1] == -1)
    frac = [(e[100:] == k).mean() for k in (0, 1, 2)]
    assert all(0.2 < f < 0.5 for f in frac)
    # una subida fuerte y sostenida cae en el tercio alto
    z4 = np.concatenate([z, z[-1] + np.arange(1, 8) * 0.8])
    assert br.etiquetas_desde_z(z4)[-1] == br.ALTO


def test_etiquetas_dejan_menos_uno_donde_g_no_es_finito():
    z = _z_aleatoria()
    z[120] = np.nan
    e = br.etiquetas_desde_z(z)
    # g_t usa z_t y z_(t-3): el hueco en 120 invalida g_120 y g_123
    assert e[120] == -1 and e[123] == -1
    assert e[121] != -1 and e[122] != -1 and e[124] != -1


def _bloque_sintetico(n: int = 100) -> dict:
    o = np.arange(n)
    return {"h": np.ones(n, int), "o": o, "tgt": o + 1, "y": np.ones(n),
            "s": np.arange(n, dtype=float), "lab": np.arange(n) % 3}


def test_calibracion_usa_solo_pares_con_objetivo_anterior_al_origen():
    b = _bloque_sintetico()
    prep = br.preparar(b)
    f, propio = br.calcular_factores(b, prep, "L1")
    # fila i: pares j con j + 1 < i, es decir j <= i - 2, o sea i - 1 pares
    assert [len(prep["por_h"][i]) for i in (0, 1, 2, 60)] == [0, 0, 1, 59]
    assert not propio[:41].any() and propio[41:].all() and not prep["evaluable"][:41].any()
    assert np.all(f[:41] == 1.0)
    assert f[60] == 58.0  # maximo de los scores de los 59 pares pasados (0 a 58)


def test_regimen_usa_solo_pares_del_mismo_regimen_y_cae_a_la_reserva():
    b = _bloque_sintetico(n=200)
    b["s"] = (b["lab"] + 1) * 10.0 + 0.01 * np.arange(200)  # cada regimen tiene su escala
    prep = br.preparar(b)
    f_g, _ = br.calcular_factores(b, prep, "L1")
    f_r, propio = br.calcular_factores(b, prep, "L2")
    i = 150  # regimen 0; pares pasados 0..148, del regimen 0: 0, 3, ..., 147 (50 pares)
    assert propio[i] and f_r[i] == pytest.approx(10.0 + 0.01 * 147)
    assert f_g[i] > 30.0  # el global ve tambien los regimenes de escala mayor
    j = 60  # unos 20 pares por regimen: menos de N_MIN, usa el factor global
    assert not propio[j] and f_r[j] == f_g[j]
    # con todas las filas en un mismo regimen, L2 reproduce L1
    f_u, _ = br.calcular_factores(b, prep, "L2", np.zeros(200, int))
    assert np.array_equal(f_u, f_g)


def test_capa_agrupada_acumula_los_horizontes():
    n = 60
    o = np.concatenate([np.arange(n), np.arange(n)])
    h = np.concatenate([np.ones(n, int), np.full(n, 2)])
    b = {"h": h, "o": o, "tgt": o + h, "y": np.ones(2 * n), "s": np.arange(2 * n, dtype=float), "lab": np.zeros(2 * n, int)}
    prep = br.preparar(b)
    f_h, _ = br.calcular_factores(b, prep, "L1")
    f_p, propio_p = br.calcular_factores(b, prep, "L1p")
    # origen 30, horizonte 1: 29 pares del mismo horizonte (no evaluable) y 57 acumulados
    assert len(prep["por_h"][30]) == 29 and len(prep["todos"][30]) == 57
    assert propio_p[30] and not prep["evaluable"][30]
    # origen 55, horizonte 1: 54 pares propios (maximo 53) y 107 acumulados (maximo 112)
    assert f_h[55] == 53.0 and f_p[55] == 112.0


def test_holm():
    aj = br.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert aj == {"a": pytest.approx(0.03), "c": pytest.approx(0.06), "b": pytest.approx(0.06)}
