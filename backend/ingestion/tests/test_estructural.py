"""Pruebas de analisis_nowcast_estructural.py: el programa lineal del promedio causal de k semanas,
el rango de la suma de las semanas que salen de la ventana, el error de identificacion, la magnitud
de comparacion, la compuerta y la ausencia de fuga del futuro. No necesitan Postgres."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analisis_nowcast_estructural as est  # noqa: E402


def _pm(x: np.ndarray, k: int) -> np.ndarray:
    """Promedio causal de k semanas de x; los k - 1 primeros valores de x son el pasado."""
    return np.array([x[t : t + k].mean() for t in range(len(x) - k + 1)])


def _crudo(n: int, k: int, semilla: int = 0) -> np.ndarray:
    rng = np.random.default_rng(semilla)
    base = 100 + 40 * np.sin(np.linspace(0, 3, n + k - 1))
    return np.maximum(0, np.round(base + rng.normal(0, 25, n + k - 1)))


# ------------------------------------------------------- programa lineal

def test_factible_con_el_pasado_verdadero_fijo():
    k = 5
    x = _crudo(30, k)
    y = _pm(x, k)
    assert est.factible(y, k, x[: k - 1])


def test_factible_con_el_pasado_libre():
    k = 5
    x = _crudo(30, k, 1)
    assert est.factible(_pm(x, k), k, None)


def test_pasado_fijo_incompatible_es_infactible():
    # con 10 y 10 de pasado, la ventana de 3 semanas no puede promediar 0
    assert not est.factible(np.array([0.0, 0.0, 0.0]), 3, np.array([10.0, 10.0]))


def test_serie_que_no_cabe_en_ninguna_ventana_es_infactible():
    # y1 = 0 y y3 = 0 fuerzan x1 = x2 = 0 y x0 = x1 = 0, luego y2 no puede ser 100
    assert not est.factible(np.array([100.0, 0.0, 100.0, 0.0]), 3, None)


def test_semana_sin_dato_no_restringe():
    y = np.array([100.0, np.nan, 100.0, 100.0])
    assert est.factible(y, 3, None)


def test_la_ventana_termina_en_la_semana_de_y():
    # con k = 2 y pasado fijo en 100, y0 = 150 exige x0 = 200
    A, b, limites = est.sistema(np.array([150.0]), 2, np.array([100.0]))
    assert A.shape == (2, 2)
    assert np.allclose(A[0], [0.5, 0.5])
    assert limites[0] == (100.0, 100.0)
    r = est.rango_suma(np.array([150.0]), 2, [1], np.array([100.0]))
    assert r[0] == pytest.approx(200.0 - 2 * est.TOL, abs=1e-6)
    assert r[1] == pytest.approx(200.0 + 2 * est.TOL, abs=1e-6)


# ------------------------------------------------------- rango de la suma

def test_el_rango_contiene_la_suma_verdadera_con_pasado_libre():
    k, n = 6, 40
    x = _crudo(n, k, 2)
    y = _pm(x, k)
    posiciones = list(range(n - 1, n - 1 + 4))
    verdadera = x[posiciones].sum()
    bajo, alto = est.rango_suma(y, k, posiciones, None)
    assert bajo - 1e-6 <= verdadera <= alto + 1e-6
    assert alto - bajo > 0


def test_el_ancla_fija_estrecha_el_rango_frente_al_pasado_libre():
    k, n = 6, 12
    x = _crudo(n, k, 3)
    y = _pm(x, k)
    posiciones = list(range(n - 1, n - 1 + 4))
    libre = est.rango_suma(y, k, posiciones, None)
    anclado = est.rango_suma(y, k, posiciones, x[: k - 1])
    assert anclado[1] - anclado[0] < libre[1] - libre[0]
    assert anclado[0] - 1e-6 <= x[posiciones].sum() <= anclado[1] + 1e-6


def test_el_rango_es_none_si_no_hay_solucion():
    assert est.rango_suma(np.array([0.0, 0.0, 0.0]), 3, [2], np.array([10.0, 10.0])) is None


def test_error_de_identificacion_usa_la_formula_del_protocolo():
    k, n = 5, 25
    x = _crudo(n, k, 4)
    y = _pm(x, k)
    bajo, alto = est.rango_suma(y, k, list(range(n - 1, n + 3)), None)
    esperado = (alto - bajo) / (2 * k * y[-1])
    assert est.error_identificacion(y, k) == pytest.approx(esperado)


def test_error_de_identificacion_no_se_define_con_ventana_menor_que_h():
    y = np.array([50.0, 60.0, 70.0, 80.0])
    assert est.error_identificacion(y, 3) is None
    assert est.error_identificacion(y, 4) is not None


def test_error_de_identificacion_none_con_nivel_no_positivo():
    assert est.error_identificacion(np.array([5.0, 0.0]), 4) is None


def test_el_error_no_depende_de_lo_posterior_al_origen():
    k = 6
    x = _crudo(40, k, 5)
    y = _pm(x, k)
    o = 30
    a = est.error_identificacion(y[:o], k)
    y2 = y.copy()
    y2[o:] = 9999.0
    assert est.error_identificacion(y2[:o], k) == a
    assert est.barrido_origenes(y2, k, range(o, o + 1)) == est.barrido_origenes(y, k, range(o, o + 1))


def test_con_conteos_pequenos_la_no_negatividad_aprieta_el_rango():
    # un nivel casi nulo deja poco margen: el error relativo baja frente a un nivel alto de igual forma
    k, n = 6, 30
    chico = np.full(n, 1.0)
    grande = np.full(n, 200.0)
    assert est.rango_suma(chico, k, list(range(n - 1, n + 3)), None)[1] < est.rango_suma(
        grande, k, list(range(n - 1, n + 3)), None
    )[1]


# ---------------------------------------------------------------- magnitud

def test_mediana_movimiento():
    y = np.array([100.0, 100.0, 100.0, 100.0, 100.0, 200.0])
    # pares (0, 4) y (1, 5): 0 y 1,0
    assert est.mediana_movimiento([y]) == pytest.approx(0.5)


def test_mediana_movimiento_no_cruza_series_ni_toma_nan():
    a = np.array([100.0, np.nan, 100.0, 100.0, 100.0, 200.0])
    b = np.array([50.0, 50.0, 50.0, 50.0, 100.0])
    # a: (0,4)=0 ; (1,5) descartado por NaN ; b: (0,4)=1,0 -> mediana de {0, 1,0}
    assert est.mediana_movimiento([a, b]) == pytest.approx(0.5)


# ---------------------------------------------------------------- compuerta

def _fila(k, f25, f26, mediana):
    fila = {"k": k, "factible_2025": f25, "factible_2026": f26}
    if f26:
        fila["origenes_2026"] = {"e_id_mediana": mediana}
    return fila


def test_compuerta_superada_si_algun_k_de_g_cabe_bajo_el_umbral():
    e0b = {"umbral": 0.04, "por_k": [_fila(3, True, True, 0.01), _fila(4, True, True, 0.2), _fila(7, True, True, 0.03)]}
    c = est.compuerta(e0b)
    assert c["G"] == [4, 7]
    assert c["k_que_pasan"] == [7]
    assert c["superada"]


def test_compuerta_no_superada_con_umbral_excedido_o_k_fuera_de_g():
    e0b = {
        "umbral": 0.04,
        "por_k": [_fila(5, True, True, 0.5), _fila(6, True, False, None), _fila(8, False, True, 0.0), _fila(10, True, True, 0.0)],
    }
    c = est.compuerta(e0b)
    assert c["G"] == [5]
    assert not c["superada"]


def test_compuerta_umbral_inclusivo():
    e0b = {"umbral": 0.04, "por_k": [_fila(6, True, True, 0.04)]}
    assert est.compuerta(e0b)["superada"]


# ---------------------------------------------------------------- E0a y E0b

def _od_sintetico():
    x = _crudo(52 + 60, 7, 6)
    od = {}
    for i, s in enumerate(range(1, 53)):
        od[(2023, s)] = float(x[i])
    y = _pm(x[52 - 6 :], 7)
    for s in range(1, 53):
        od[(2024, s)] = float(np.round(y[s - 1]))
    return od


def test_pasados_2023_libera_los_ceros():
    od = {(2023, s): 10.0 for s in range(1, 53)}
    od[(2023, 51)] = 0.0
    od[(2023, 52)] = 0.0
    p = est.pasados_2023(od, 4)
    assert list(p["P"]) == [10.0, 0.0, 0.0]
    assert np.isnan(p["P_prima"][1]) and np.isnan(p["P_prima"][2]) and p["P_prima"][0] == 10.0
    assert p["L"] is None


def test_e0a_la_serie_construida_con_el_ancla_es_factible_en_su_k():
    od = _od_sintetico()
    filas = {f["k"]: f for f in est.e0a(od)}
    assert filas[7]["variantes"]["L"]["factible"]
    assert filas[7]["variantes"]["P_prima"]["factible"] or filas[7]["variantes"]["P"]["factible"]
    # el ancla estrecha el rango: e_id con pasado fijo no supera al de pasado libre
    f7 = filas[7]["variantes"]
    if f7["P"]["factible"]:
        assert f7["P"]["e_id_h4"] <= f7["L"]["e_id_h4"] + 1e-9


def _tablero_sintetico():
    x = _crudo(52 + 37, 7, 7)
    y25 = np.round(_pm(x[:58], 7))[:52]
    y26 = np.round(_pm(x[52:], 7))[:37]
    t = {(2025, s): float(v) for s, v in enumerate(y25, 1)}
    t.update({(2026, s): float(v) for s, v in enumerate(y26, 1)})
    return t


def test_e0b_estructura_y_compuerta_de_punta_a_punta():
    r = est.e0b(_tablero_sintetico())
    assert r["m4"] > 0
    assert r["umbral"] == pytest.approx(round(est.FRACCION_MOVIMIENTO * r["m4"], 4), abs=1e-4)
    assert [f["k"] for f in r["por_k"]] == list(est.KS)
    for f in r["por_k"]:
        if f["k"] < est.H:
            assert "origenes_2026" not in f
        elif f["factible_2026"]:
            assert f["origenes_2026"]["origenes"] == len(est.ORIGENES_2026)
    c = est.compuerta(r)
    assert set(c["k_que_pasan"]) <= set(c["G"])


def test_serie_anio_exige_semanas_completas():
    t = {(2026, s): 10.0 for s in range(1, 37)}
    with pytest.raises(AssertionError):
        est.serie_anio(t, 2026)
