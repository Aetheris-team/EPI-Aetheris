"""Pruebas de las funciones puras de experimento_nowcast_cambio_anio.py: asignacion de
tramos, estadistico D y su referencia nula, permutacion, condiciones B, ensanchamiento y
eleccion de f. No necesitan Postgres."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import experimento_nowcast_cambio_anio as ca  # noqa: E402

IDX_MED = ca.IDX_MEDIANA
FORMA = np.linspace(-1.0, 1.0, 23)


def _q(centro: float, escala: float) -> np.ndarray:
    return np.expm1(np.log1p(centro) + escala * FORMA)


# --- tramos ------------------------------------------------------------------------


def test_tramos_fa_v_y_resto():
    semana = np.array([1, 2, 3, 4, 52, 13, 20])
    fecha = [date(2026, 1, 4), date(2026, 1, 11), date(2026, 1, 18), date(2026, 1, 25),
             date(2025, 12, 21), date(2026, 3, 29), date(2026, 5, 17)]
    m = ca.mascaras_tramos(semana, fecha)
    assert m["FA"].tolist() == [True, True, True, False, False, False, False]
    # la semana 1 de 2026 empieza el 4 de enero: no toca el 20 dic a 2 ene, es FA y no V
    assert m["V"].tolist() == [False, False, False, False, True, True, False]
    assert m["R"].tolist() == [False, False, False, True, False, False, True]


def test_una_semana_puede_ser_fa_y_v_y_r_la_excluye():
    # semana 1 de 2014 (MMWR): empieza el 29 de diciembre de 2013 y toca el fin de anio
    m = ca.mascaras_tramos(np.array([1]), [date(2013, 12, 29)])
    assert m["FA"][0] and m["V"][0] and not m["R"][0]


# --- parte A ----------------------------------------------------------------------------


def _serie_dos_anios(valor_pre: float, valor_post: float):
    """Anio 2000 con 52 semanas de valor_pre y anio 2001 con 52 de valor_post."""
    casos = np.concatenate([np.full(52, valor_pre), np.full(52, valor_post)])
    anio = np.repeat([2000, 2001], 52)
    semana = np.tile(np.arange(1, 53), 2)
    idx = {(int(a), int(w)): k for k, (a, w) in enumerate(zip(anio, semana))}
    return casos, idx


def test_estadistico_d_con_cociente_conocido():
    casos, idx = _serie_dos_anios(100.0, 200.0)
    assert ca.estadistico_d(casos, idx, 2001) == pytest.approx(np.log1p(200.0) - np.log1p(100.0))


def test_estadistico_d_es_nan_si_falta_una_semana():
    casos, idx = _serie_dos_anios(100.0, 200.0)
    casos[idx[(2000, 48)]] = np.nan
    assert np.isnan(ca.estadistico_d(casos, idx, 2001))
    del idx[(2001, 3)]
    assert np.isnan(ca.estadistico_d(casos, idx, 2001))


def test_referencia_nula_usa_ventanas_dentro_de_las_semanas_4_a_46():
    casos, idx = _serie_dos_anios(100.0, 200.0)
    ref = ca.referencia_nula(casos, idx, (2000, 2001))
    # inicios 4 a 38: 35 ventanas por anio, todas planas (D = 0) dentro de cada anio
    assert len(ref) == 70 and np.allclose(ref, 0.0)
    # una ventana no cruza de un anio al otro: ninguna D vale el salto entre 2000 y 2001
    assert not np.any(np.isclose(ref, np.log1p(200.0) - np.log1p(100.0)))


def test_referencia_nula_detecta_un_escalon_dentro_del_anio():
    casos, idx = _serie_dos_anios(100.0, 100.0)
    casos[idx[(2000, 20)]:idx[(2000, 53 - 1)] + 1] = 300.0
    ref = ca.referencia_nula(casos, idx, (2000,))
    assert ref.max() > 0.5 and ref.min() == pytest.approx(0.0)


def test_percentil():
    ref = np.arange(1.0, 101.0)
    assert ca.percentil(50.0, ref) == 0.5
    assert ca.percentil(0.0, ref) == 0.0 and ca.percentil(1000.0, ref) == 1.0


# --- parte B ----------------------------------------------------------------------------


def _pares_sinteticos(anios=(2019, 2021, 2022, 2023, 2024), semanas=40, horizontes=8):
    """Cada semana objetivo tiene `horizontes` pares; devuelve (cubre, tgt, anio)."""
    tgt, anio = [], []
    k = 0
    for a in anios:
        for _ in range(semanas):
            tgt += [k] * horizontes
            anio += [a] * horizontes
            k += 1
    return np.ones(len(tgt), bool), np.array(tgt), np.array(anio)


def test_permutacion_con_todo_cubierto_da_p_uno():
    cubre, tgt, anio = _pares_sinteticos()
    mascara = np.isin(tgt % 40, (0, 1, 2))
    r = ca.p_permutacion(cubre, tgt, anio, mascara, semilla=1, n_perm=200)
    assert r["cob_observada"] == 1.0 and r["p"] == 1.0
    assert set(r["semanas_del_tramo_por_anio"].values()) == {3}


def test_permutacion_detecta_un_tramo_que_falla_siempre():
    cubre, tgt, anio = _pares_sinteticos()
    mascara = np.isin(tgt % 40, (0, 1, 2))
    cubre[mascara] = False
    r = ca.p_permutacion(cubre, tgt, anio, mascara, semilla=1, n_perm=500)
    assert r["cob_observada"] == 0.0 and r["p"] <= 0.01 and r["cob_permutada_media"] > 0.9


def test_permutacion_es_reproducible_con_la_semilla():
    cubre, tgt, anio = _pares_sinteticos()
    mascara = np.isin(tgt % 40, (0, 1, 2))
    cubre[np.flatnonzero(mascara)[:30]] = False
    a = ca.p_permutacion(cubre, tgt, anio, mascara, semilla=7, n_perm=300)
    b = ca.p_permutacion(cubre, tgt, anio, mascara, semilla=7, n_perm=300)
    assert a == b


@pytest.mark.parametrize("cob, p, arriba, abajo, cumple", [
    (0.80, 0.05, 9, 1, True),    # las tres condiciones
    (0.90, 0.05, 9, 1, False),   # cobertura sobre 0,85
    (0.80, 0.30, 9, 1, False),   # no distinguible de semanas al azar
    (0.80, 0.05, 6, 4, False),   # fallos repartidos entre los dos lados
    (0.80, 0.05, 0, 0, False),   # sin fallos no hay lado
])
def test_condiciones_b(cob, p, arriba, abajo, cumple):
    assert ca.condiciones_b(cob, p, arriba, abajo)["cumple"] is cumple


def test_condiciones_b_informa_el_lado():
    assert ca.condiciones_b(0.8, 0.01, 2, 8)["lado"] == "abajo"
    assert ca.condiciones_b(0.8, 0.01, 8, 2)["lado"] == "arriba"


def test_lados_de_fallo():
    q = np.tile(_q(100.0, 0.3), (3, 1))
    y = np.array([q[0, ca.IDX_B95[1]] + 1.0, q[0, ca.IDX_B95[0]] - 0.5, 100.0])
    assert ca.lados_fallo(y, q) == (1, 1)


# --- parte C ----------------------------------------------------------------------------


def test_ensanchar_con_f_uno_devuelve_los_mismos_cuantiles():
    q = _q(120.0, 0.4)
    for lado in ("arriba", "abajo"):
        assert np.allclose(ca.ensanchar(q, 1.0, lado)[0], q)


def test_ensanchar_no_toca_la_mediana_ni_el_otro_lado_y_conserva_el_orden():
    q = _q(120.0, 0.4)
    arr = ca.ensanchar(q, 1.5, "arriba")[0]
    assert arr[IDX_MED] == pytest.approx(q[IDX_MED]) and np.allclose(arr[:IDX_MED], q[:IDX_MED])
    assert np.all(arr[IDX_MED + 1:] > q[IDX_MED + 1:]) and np.all(np.diff(arr) >= 0)
    aba = ca.ensanchar(q, 1.5, "abajo")[0]
    assert aba[IDX_MED] == pytest.approx(q[IDX_MED]) and np.allclose(aba[IDX_MED + 1:], q[IDX_MED + 1:])
    assert np.all(aba[:IDX_MED] < q[:IDX_MED]) and np.all(np.diff(aba) >= 0) and aba.min() >= 0.0


def test_ensanchar_rechaza_un_lado_desconocido():
    with pytest.raises(ValueError):
        ca.ensanchar(_q(10.0, 0.2), 1.5, "centro")


def test_elegir_f_toma_el_menor_que_llega_al_objetivo():
    assert ca.elegir_f({1.25: 0.90, 1.5: 0.94, 2.0: 0.97}) == 1.5
    assert ca.elegir_f({1.25: 0.90, 1.5: 0.92, 2.0: 0.925}) is None
    assert ca.elegir_f({2.0: 0.99, 1.25: 0.93}) == 1.25
