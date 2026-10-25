"""Pruebas de experimento_nowcast_candidata_ets.py (K4): la formula de ETS y la de los cuantiles contra las
del experimento, sin fuga del futuro, criterio de confirmacion, Diebold-Mariano y Holm contra los de
los experimentos, y la evaluacion de punta a punta con una salida congelada sintetica. No necesitan
Postgres."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import experimento_nowcast_banda_riesgo as br  # noqa: E402
import experimento_nowcast_candidata_ets as k4  # noqa: E402
import experimento_nowcast_mejora as mej  # noqa: E402
import experimento_nowcast_tendencia_seleccion as sel  # noqa: E402
import experimento_nowcast_theta_ets as te  # noqa: E402
from experimento_nowcast_corto_plazo import Serie  # noqa: E402

HS = k4.HORIZONTES
FORMA = np.linspace(-1.0, 1.0, 23)


def _q(centro: float, escala: float) -> np.ndarray:
    return np.expm1(np.log1p(centro) + escala * FORMA)


def _serie_sintetica(semanas: int = 700, semilla: int = 3, huecos: tuple[int, ...] = ()) -> Serie:
    rng = np.random.default_rng(semilla)
    fecha = np.array([date(2013, 12, 29) + timedelta(days=7 * k) for k in range(semanas)], dtype=object)
    z = np.log(100.0) + np.cumsum(rng.normal(0.0, 0.15, semanas))
    casos = np.expm1(z)
    for k in huecos:
        casos[k] = np.nan
    return Serie(fecha=fecha, anio=np.array([f.year for f in fecha]), semana=np.arange(semanas) % 52 + 1,
                 doy=np.array([f.timetuple().tm_yday for f in fecha]), casos=casos, z=np.log1p(casos),
                 clima={}, oni=np.zeros(semanas))


# --- formulas -------------------------------------------------------------------------


def test_parametros_firmados():
    assert (k4.ALFA, k4.BETA, k4.PHI) == (0.8, 1.0, 0.8) and k4.PESO_C == 0.5
    assert (k4.RAZON_MAX, k4.MIN_HORIZONTES, k4.COBERTURA_TOLERANCIA) == (0.99, 5, 0.03)
    assert (k4.ALFA, k4.BETA, k4.PHI) in te.REJILLA_ETS


def test_ets_es_el_del_experimento():
    z = 4.0 + np.cumsum(np.random.default_rng(1).normal(0.0, 0.2, 200))
    z[80] = np.nan
    assert np.array_equal(k4.medianas_ets(z), te.medianas_ets(z, 0.8, 1.0, 0.8), equal_nan=True)


def test_mezcla_es_la_de_los_experimentos():
    m, t = _q(300.0, 0.4), _q(100.0, 0.2)
    for w in (0.0, 0.5, 1.0):
        assert np.allclose(k4.mezcla(m, t, w), mej._mezcla(m, t, w), rtol=0, atol=1e-12)


@pytest.mark.parametrize("huecos", [(), (400,)])
def test_los_cuantiles_son_los_del_experimento(huecos):
    s = _serie_sintetica(huecos=huecos)
    mu = k4.medianas_ets(s.z)
    rm = te.ReglasMu(s)
    comprobados = 0
    for h in HS:
        for o in range(150, s.T - h, 9):
            if not np.isfinite(s.z[o]):
                continue
            a, b = k4.cuantiles_ets(s, mu, o, h), rm.cuantiles(o, h, "ets", (0.8, 1.0, 0.8))
            assert np.allclose(a, b, rtol=0, atol=1e-9)
            comprobados += 1
    assert comprobados > 100


def test_los_cuantiles_no_usan_el_futuro():
    s = _serie_sintetica()
    o, h = 450, 4
    q = k4.cuantiles_ets(s, k4.medianas_ets(s.z), o, h)
    futuro = s.z.copy()
    futuro[o + 1:] = np.random.default_rng(5).normal(9.0, 2.0, s.T - o - 1)
    s2 = replace(s, z=futuro)
    assert np.array_equal(q, k4.cuantiles_ets(s2, k4.medianas_ets(s2.z), o, h))


def test_los_cuantiles_ordenados_y_sin_prediccion_si_faltan_errores():
    s = _serie_sintetica()
    mu = k4.medianas_ets(s.z)
    q = k4.cuantiles_ets(s, mu, 500, 8)
    assert len(q) == 23 and np.all(np.diff(q) >= 0) and q.min() >= 0
    assert k4.cuantiles_ets(s, mu, 20, 4) is None  # menos de 30 errores desde 2014


def test_origen_ok_pide_rezagos_y_objetivo_finitos():
    s = _serie_sintetica(huecos=(300,))
    assert k4.origen_ok(s, 400, 4)
    assert not k4.origen_ok(s, 303, 4)  # el hueco cae en las 6 semanas anteriores
    assert not k4.origen_ok(s, 296, 4)  # el hueco es el objetivo
    assert not k4.origen_ok(s, 3, 4)


# --- criterio ---------------------------------------------------------------------------


def _filas(q_c: np.ndarray, q_k: np.ndarray, y: float, n: int = 12) -> dict[int, list[dict]]:
    return {h: [{"origen": f"2026-09-{20 + i:02d}", "anio": 2026, "semana": 38, "y": y, "q_C": q_c, "q_K4": q_k,
                 "wis_ref_suavizada": 10.0} for i in range(n)] for h in HS}


def test_se_confirma_si_gana_en_todos_los_horizontes():
    # y cerca de la mediana de K4 y lejos de la de C
    res = k4.evaluar_filas(_filas(_q(300.0, 0.2), _q(100.0, 0.2), 100.0))
    d = k4.decidir(res)
    assert d["razon_media"] < 0.99 and d["confirmada"] and d["c2_mayoria_de_horizontes"] and d["c3_cobertura"]


def test_no_se_confirma_si_C_acierta_y_K4_no():
    d = k4.decidir(k4.evaluar_filas(_filas(_q(100.0, 0.2), _q(300.0, 0.2), 100.0)))
    assert d["razon_media"] > 1 and not d["confirmada"]


def test_la_razon_exige_ganar_al_menos_un_uno_por_ciento():
    # K4 igual a C: razon 1, pasa la mayoria? no (ningun horizonte menor que 1)
    d = k4.decidir(k4.evaluar_filas(_filas(_q(100.0, 0.2), _q(100.0, 0.2), 100.0)))
    assert d["razon_media"] == 1.0 and not d["c1_razon"] and not d["c2_mayoria_de_horizontes"] and not d["confirmada"]


def _res_con_razones(razones: dict[int, float], dentro_k: int = 12, dentro_c: int = 12, n: int = 12) -> dict:
    return {"por_h": {h: {"C": {"n": n, "dentro95": dentro_c, "razon_vs_C": 1.0},
                          "K4": {"n": n, "dentro95": dentro_k, "razon_vs_C": razones[h]}} for h in HS}}


def test_exige_al_menos_cinco_de_ocho_horizontes_con_razon_menor_que_uno():
    cinco = dict.fromkeys(HS, 1.0) | {1: 0.5, 2: 0.5, 3: 0.5, 4: 0.5, 5: 0.5}
    cuatro = dict.fromkeys(HS, 1.0) | {1: 0.3, 2: 0.3, 3: 0.3, 4: 0.3}
    assert k4.decidir(_res_con_razones(cinco))["c2_mayoria_de_horizontes"]
    d4 = k4.decidir(_res_con_razones(cuatro))
    assert d4["c1_razon"] and not d4["c2_mayoria_de_horizontes"] and not d4["confirmada"]


def test_la_cobertura_impide_la_confirmacion():
    todas = dict.fromkeys(HS, 0.9)
    assert k4.decidir(_res_con_razones(todas, dentro_k=11, dentro_c=12))["c3_cobertura"] is False  # 0,917 contra 1,0
    assert k4.decidir(_res_con_razones(todas, dentro_k=12, dentro_c=12))["confirmada"]


def test_dm_y_holm_coinciden_con_los_de_los_experimentos():
    d = np.random.default_rng(3).normal(-0.2, 1.0, 40)
    for h in (1, 4, 8):
        assert k4.dm(d, h) == sel.dm(d, h)
    assert k4.dm(d[:5], 2) is None
    ps = {"a": 0.001, "b": 0.02, "c": 0.5, "d": 0.04}
    assert k4.holm(ps) == br.holm(ps)


# --- evaluacion de punta a punta con una salida congelada sintetica ------------------------


def _salida_congelada(serie: Serie, commit: str) -> dict:
    rng = np.random.default_rng(11)
    detalle = {}
    for h in range(1, 9):
        filas = []
        for o in range(600, 620):
            m, t = _q(200.0 + rng.uniform(0, 50), 0.4), _q(100.0 + rng.uniform(0, 20), 0.2)
            filas.append({"origen": str(serie.fecha[o]), "objetivo": str(serie.fecha[o + h]), "anio": int(serie.anio[o + h]),
                          "semana": int(serie.semana[o + h]), "y": float(serie.casos[o + h]), "wis_ref_suavizada": 12.0,
                          "q_M0": m.tolist(), "q_T": t.tolist(), "q_C": k4.mezcla(m, t, 0.5).tolist()})
        detalle[str(h)] = {"h": h, "filas": filas}
    return {"commit_script": commit, "semanas_prueba": [str(serie.fecha[k]) for k in range(608, 628)],
            "confirmado": True, "detalle": detalle}


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    serie = _serie_sintetica()
    monkeypatch.setattr(k4.ten, "SALIDA_PRUEBA", tmp_path / "tendencia_prueba.json")
    monkeypatch.setattr(k4, "SALIDA_PRUEBA", tmp_path / "candidata_ets_prueba.json")
    monkeypatch.setattr(k4, "_script_sin_cambios", lambda: "a" * 40)
    return serie, tmp_path


def test_evaluar_se_niega_sin_la_evaluacion_congelada(entorno):
    serie, _ = entorno
    with pytest.raises(SystemExit, match="Falta la evaluacion congelada"):
        k4.evaluar(serie)


def test_evaluar_se_niega_si_la_congelada_declara_otro_commit(entorno):
    serie, tmp = entorno
    (tmp / "tendencia_prueba.json").write_text(json.dumps(_salida_congelada(serie, "b" * 40)), encoding="utf-8")
    with pytest.raises(SystemExit, match="declara el commit"):
        k4.evaluar(serie)


def test_evaluar_se_niega_con_cambios_sin_commit(tmp_path, monkeypatch):
    serie = _serie_sintetica()
    monkeypatch.setattr(k4.ten, "SALIDA_PRUEBA", tmp_path / "tendencia_prueba.json")
    monkeypatch.setattr(k4, "SALIDA_PRUEBA", tmp_path / "candidata_ets_prueba.json")
    (tmp_path / "tendencia_prueba.json").write_text(json.dumps(_salida_congelada(serie, k4.FIRMADO_COMMIT)), encoding="utf-8")

    def sucio():
        raise SystemExit("El script tiene cambios sin commit")
    monkeypatch.setattr(k4, "_script_sin_cambios", sucio)
    with pytest.raises(SystemExit, match="cambios sin commit"):
        k4.evaluar(serie)
    assert not (tmp_path / "candidata_ets_prueba.json").exists()


def test_evaluar_escribe_la_salida_una_sola_vez(entorno):
    serie, tmp = entorno
    (tmp / "tendencia_prueba.json").write_text(json.dumps(_salida_congelada(serie, k4.FIRMADO_COMMIT)), encoding="utf-8")
    k4.evaluar(serie)
    out = json.loads((tmp / "candidata_ets_prueba.json").read_text(encoding="utf-8"))
    assert set(out) >= {"resultado", "decision", "sin_cambio_de_anio", "dm_holm", "confirmada"}
    assert out["commit_script"] == "a" * 40 and out["commit_evaluacion_congelada"] == k4.FIRMADO_COMMIT
    assert set(out["decision"]["razones"]) == {str(h) for h in HS}
    with pytest.raises(SystemExit, match="ya se corrio"):
        k4.evaluar(serie)


def test_evaluar_rechaza_una_C_que_no_es_la_mezcla(entorno):
    serie, tmp = entorno
    sal = _salida_congelada(serie, k4.FIRMADO_COMMIT)
    sal["detalle"]["3"]["filas"][0]["q_C"] = _q(999.0, 0.1).tolist()
    (tmp / "tendencia_prueba.json").write_text(json.dumps(sal), encoding="utf-8")
    with pytest.raises(AssertionError, match="C guardada"):
        k4.evaluar(serie)
