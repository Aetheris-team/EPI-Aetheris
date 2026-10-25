"""Pruebas de las funciones puras de experimento_nowcast_peso_horizonte.py: identidades
de la mezcla, regla de cambio con admisibilidad por cobertura, condicion de la extension
E1 y puntaje de una validacion sintetica. No necesitan Postgres."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import experimento_nowcast_peso_horizonte as ph  # noqa: E402

IDX_MED = ph.IDX_MEDIANA
FORMA = np.linspace(-1.0, 1.0, 23)


def _q(centro: float, escala: float) -> np.ndarray:
    return np.expm1(np.log1p(centro) + escala * FORMA)


def test_mezcla_en_los_extremos_devuelve_cada_modelo():
    m, t = _q(300.0, 0.4), _q(100.0, 0.2)
    assert np.allclose(ph.mezcla(m, t, 1.0), m) and np.allclose(ph.mezcla(m, t, 0.0), t)


def test_centro_ancho_con_pesos_iguales_es_la_mezcla_simple():
    m, t = _q(300.0, 0.4), _q(100.0, 0.2)
    for w in (0.0, 0.25, 0.5, 1.0):
        assert np.allclose(ph.mezcla_centro_ancho(m, t, w, w), ph.mezcla(m, t, w))


def test_centro_ancho_separa_mediana_y_ancho():
    m, t = _q(300.0, 0.4), _q(100.0, 0.2)
    q = ph.mezcla_centro_ancho(m, t, 0.0, 0.5)
    assert q[IDX_MED] == pytest.approx(t[IDX_MED])  # el centro es el de T
    ancho_mezcla = np.log1p(ph.mezcla(m, t, 0.5)) - np.log1p(ph.mezcla(m, t, 0.5)[IDX_MED])
    assert np.allclose(np.log1p(q) - np.log1p(q[IDX_MED]), ancho_mezcla)  # el ancho es el de la mezcla


def _res(puntaje: float, anios: tuple, cob: float) -> dict:
    return {"puntaje": puntaje, "por_anio": dict(zip(ph.ANIOS_VALIDACION, anios)), "cob95": cob}


def test_decidir_cambia_si_gana_en_puntaje_y_anios_con_cobertura_admisible():
    res = {"0.5": _res(0.10, (0.1, 0.1, 0.1, 0.1), 0.90),
           "0.25": _res(0.12, (0.12, 0.13, 0.12, 0.11), 0.89)}
    d = ph.decidir(res, "0.5")
    assert d["mejor_admisible"] == "0.25" and d["regla_admisible"]["pasa"] and not d["e1_aplica"]


@pytest.mark.parametrize("candidato, esperado", [
    (_res(0.103, (0.11, 0.11, 0.11, 0.09), 0.90), False),  # ganancia menor a 0,005
    (_res(0.12, (0.15, 0.15, 0.09, 0.09), 0.90), False),   # solo supera en 2 de 4 anios
    (_res(0.12, (0.13, 0.13, 0.11, 0.11), 0.90), True),
])
def test_regla_de_cambio(candidato, esperado):
    d = ph.decidir({"0.5": _res(0.10, (0.1, 0.1, 0.1, 0.1), 0.90), "0.25": candidato}, "0.5")
    assert d["regla_admisible"]["pasa"] is esperado


def test_extension_e1_cuando_el_mejor_pasa_la_regla_pero_la_cobertura_lo_excluye():
    res = {"0.5": _res(0.10, (0.1, 0.1, 0.1, 0.1), 0.90),
           "0.0": _res(0.20, (0.2, 0.2, 0.2, 0.2), 0.82),   # gana, pero 0,08 menos de cobertura
           "0.25": _res(0.101, (0.1, 0.1, 0.1, 0.1), 0.88)}  # admisible, no pasa la regla
    d = ph.decidir(res, "0.5")
    assert d["mejor_admisible"] == "0.25" and not d["regla_admisible"]["pasa"]
    assert d["mejor_sin_restriccion"] == "0.0" and d["regla_sin_restriccion"]["pasa"] and d["e1_aplica"]
    # si el peso intermedio tambien pasa la regla, no hay extension
    res["0.25"] = _res(0.15, (0.15, 0.15, 0.15, 0.15), 0.88)
    assert not ph.decidir(res, "0.5")["e1_aplica"]


def _validacion_sintetica() -> dict:
    n = 12
    d = {"o": np.arange(n), "y": np.full(n, 100.0), "q_t": np.tile(_q(100.0, 0.1), (n, 1)),
         "q_m0": np.tile(_q(300.0, 0.1), (n, 1)), "q_ref": np.tile(_q(90.0, 0.5), (n, 1))}
    return {h: {a: d for a in ph.ANIOS_VALIDACION} for h in ph.HORIZONTES}


def test_puntaje_baja_con_el_peso_del_modelo_malo():
    val = _validacion_sintetica()
    res = ph.puntajes(val, (1, 2), {f"{w}": ph.politica_peso(w) for w in ph.PESOS})
    p = [res[f"{w}"]["puntaje"] for w in ph.PESOS]
    assert all(a > b for a, b in zip(p, p[1:]))  # T acierta, M0 no: mas M0, menos puntaje
    assert res["0.0"]["cob95"] == 1.0 and res["1.0"]["cob95"] == 0.0
