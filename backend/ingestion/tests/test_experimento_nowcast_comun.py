"""Pruebas de las piezas compartidas por los experimentos de mejora del
predictor (experimento_nowcast_comun.py). No necesitan Postgres."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import experimento_nowcast_comun as com  # noqa: E402
import experimento_nowcast_corto_plazo as exp  # noqa: E402
from experimento_nowcast_corto_plazo import CUANTILES, IDX_MEDIANA, PARES_INTERVALO, Serie  # noqa: E402


def _serie_sintetica(T: int = 420, semilla: int = 0, con_ceros: tuple[int, ...] = ()) -> Serie:
    rng = np.random.default_rng(semilla)
    fecha = np.array([date(2014, 1, 5) + timedelta(days=7 * k) for k in range(T)], dtype=object)
    anio = np.array([f.year for f in fecha], dtype=int)
    semana = np.array([min(int(f.isocalendar()[1]), 52) for f in fecha], dtype=int)
    doy = np.array([f.timetuple().tm_yday for f in fecha], dtype=int)
    base = 80 + 60 * np.sin(2 * np.pi * doy / 365.25)
    casos = rng.poisson(np.maximum(base, 5)).astype(float)
    for k in con_ceros:
        casos[k] = 0.0
    clima = {v: 20 + rng.normal(size=T) for v in exp.VARIABLES_CLIMA}
    oni = rng.normal(size=T) * 0.5
    return Serie(fecha, anio, semana, doy, casos, np.log1p(casos), clima, oni)


# --- features ---------------------------------------------------------------


def test_features_grupos_reproduce_features_en_de_m0():
    s = _serie_sintetica()
    for t, h in ((20, 1), (100, 4), (300, 8)):
        esperado = exp.features_en(s, t, h)
        obtenido = com.features_grupos(s, t, h)
        assert np.allclose(esperado, obtenido)
        assert len(obtenido) == 8 + 3 + 6 + 7 + 2


def test_features_grupos_quita_grupos_sin_cambiar_el_resto():
    s = _serie_sintetica()
    completo = com.features_grupos(s, 100, 4)
    sin_clima = com.features_grupos(s, 100, 4, tuple(g for g in com.GRUPOS_M0 if g != "clima"))
    assert len(sin_clima) == len(completo) - 7
    assert np.allclose(sin_clima, np.concatenate([completo[:17], completo[24:]]))
    sin_oni = com.features_grupos(s, 100, 4, tuple(g for g in com.GRUPOS_M0 if g != "oni"))
    assert len(sin_oni) == len(completo) - 1
    assert np.allclose(sin_oni, np.concatenate([completo[:24], completo[25:]]))
    solo = com.features_grupos(s, 100, 4, ("rezagos",))
    assert np.allclose(solo, completo[:8])


def test_features_grupos_exige_clima_aunque_no_lo_use():
    s = _serie_sintetica()
    s.clima["temp_media"][99] = np.nan
    assert com.features_grupos(s, 100, 4, ("rezagos",)) is None
    assert com.features_grupos(s, 100, 4) is None
    assert com.features_grupos(s, 110, 4, ("rezagos",)) is not None


def test_features_grupos_devuelve_none_con_hueco_en_rezagos():
    s = _serie_sintetica()
    s.z[95] = np.nan
    assert com.features_grupos(s, 100, 4) is None
    assert com.features_grupos(s, 104, 4) is not None


# --- ceros repartidos -------------------------------------------------------


def test_serie_ceros_repartidos_promedia_con_la_semana_siguiente():
    s = _serie_sintetica(con_ceros=(50,))
    z_ins, ceros = com.serie_ceros_repartidos(s)
    assert list(ceros) == [50]
    prom = (0.0 + s.casos[51]) / 2
    assert np.isclose(np.expm1(z_ins[50]), prom)
    assert np.isclose(np.expm1(z_ins[51]), prom)
    assert np.isclose(np.expm1(z_ins[49]), s.casos[49])
    assert s.casos[50] == 0.0  # la serie original no cambia


def test_features_ceros_repartidos_no_usa_la_semana_siguiente_en_el_origen_cero():
    s = _serie_sintetica(con_ceros=(50,))
    z_ins, ceros = com.serie_ceros_repartidos(s)
    ceros = frozenset(int(k) for k in ceros)
    x = com.features_ceros_repartidos(s, z_ins, ceros, 50, 4)
    assert np.isclose(x[0], z_ins[49])          # z[t] toma el valor de t-1
    x51 = com.features_ceros_repartidos(s, z_ins, ceros, 51, 4)
    assert np.isclose(x51[0], z_ins[51])        # en t = 51 ya se conoce la semana
    assert np.isclose(x51[1], z_ins[50])


# --- pares y cadena ---------------------------------------------------------


def test_pares_excluye_anios_y_objetivos_posteriores_al_origen():
    s = _serie_sintetica()
    construir = lambda t, h: com.features_grupos(s, t, h)  # noqa: E731
    o = 300
    X, Y, idx = com.pares(s, o, 4, construir, anios_excluidos=frozenset({2016}))
    assert len(Y) == len(idx) == len(X)
    assert max(s.fecha[k] for k in idx) < s.fecha[o]
    assert not any(s.anio[k] == 2016 for k in idx)
    X2, Y2, idx2 = com.pares(s, o, 4, construir, permitir_fuga=True)
    assert any(s.fecha[k] >= s.fecha[o] for k in idx2)


def test_cadena_enriquecida_lineal_respeta_cadencia_y_calibracion():
    s = _serie_sintetica(T=300)
    construir = lambda t, h: com.features_grupos(s, t, h)  # noqa: E731
    origenes = list(range(250, 262))
    cad = com.cadena_enriquecida(s, origenes, 2, construir, ajustar=com.ajustar_lineal)
    assert all(cad[o] is not None for o in origenes)
    # reajuste cada 2 origenes: los pares de calibracion cambian cada 2
    assert cad[250].reajuste is cad[251].reajuste
    assert cad[250].reajuste is not cad[252].reajuste
    r = cad[252].reajuste
    assert r.cal_q.shape == (com.N_CAL, len(CUANTILES))
    assert max(s.fecha[k] for k in r.idx_entrenamiento) < s.fecha[252]
    assert np.all(np.diff(cad[252].qz) >= 0)


def test_cadena_enriquecida_sin_pares_suficientes_devuelve_none():
    s = _serie_sintetica(T=200)
    construir = lambda t, h: com.features_grupos(s, t, h)  # noqa: E731
    cad = com.cadena_enriquecida(s, [100], 4, construir, ajustar=com.ajustar_lineal)
    assert cad[100] is None


# --- calibracion ------------------------------------------------------------


def _cal_sintetica(n: int = 52, semilla: int = 1):
    rng = np.random.default_rng(semilla)
    m = 4.0 + rng.normal(size=n) * 0.1
    ancho = np.abs(CUANTILES - 0.5) * 2  # de 0 en la mediana a ~1 en los extremos
    cal_q = m[:, None] + (CUANTILES[None, :] - 0.5) * 2.0 * 0.5
    cal_q = np.sort(cal_q, axis=1)
    return cal_q, m, rng


def test_factores_simetricos_coinciden_con_la_capa_publicada():
    cal_q, m, rng = _cal_sintetica()
    y = m + rng.normal(size=len(m)) * 0.3
    from experimento_nowcast_calibracion import _ajustes_cqr_r
    assert np.allclose(com.factores_simetricos(cal_q, y), _ajustes_cqr_r(cal_q, y))


def test_factores_asimetricos_estiran_solo_el_lado_que_falla():
    cal_q, m, rng = _cal_sintetica()
    y = m - np.abs(rng.normal(size=len(m))) * 0.8  # lo observado cae siempre por debajo
    f_lo, f_hi = com.factores_asimetricos(cal_q, y)
    assert f_hi.max() == 0.0
    assert f_lo.min() > 0.0
    q = com.aplicar_factores(np.log1p(np.linspace(50, 150, 23)), f_lo, f_hi)
    base = np.linspace(50, 150, 23)
    assert np.isclose(q[IDX_MEDIANA], base[IDX_MEDIANA])
    assert np.all(q[IDX_MEDIANA + 1:] <= base[IDX_MEDIANA + 1:] + 1e-9)


def test_aplicar_factores_con_factor_uno_es_identidad():
    qz = np.log1p(np.linspace(10, 90, 23))
    q = com.aplicar_factores(qz, np.ones(len(PARES_INTERVALO)))
    assert np.allclose(q, np.expm1(qz))


def test_nivel_conformal_respeta_tope_y_winsorizacion():
    e = np.array([0.1] * 50 + [100.0, 200.0])
    assert com.nivel_conformal(e, 0.99) <= com.TOPE_FACTOR
    assert com.nivel_conformal(e, 0.5) == pytest.approx(0.1)


def test_actualizar_alpha_sube_tras_fallo_y_queda_acotado():
    a = com.actualizar_alpha(0.05, 0.05, err=1.0, gamma=0.03)
    assert a < 0.05
    a2 = com.actualizar_alpha(0.05, 0.05, err=0.0, gamma=0.03)
    assert a2 > 0.05
    assert com.actualizar_alpha(0.0015, 0.05, 1.0, 0.03) == 0.001
    assert com.actualizar_alpha(0.49, 0.05, 0.0, 10.0) == 0.5


def test_fuera_del_intervalo():
    q = np.linspace(10, 100, 23)
    assert com.fuera_del_intervalo(5.0, q, 0) == 1.0
    assert com.fuera_del_intervalo(50.0, q, 0) == 0.0
    j_50 = PARES_INTERVALO.index((6, 16))
    assert com.fuera_del_intervalo(q[5], q, j_50) == 1.0


# --- capas de corto plazo ---------------------------------------------------


def test_sesgo_reciente_y_desplazar():
    med = np.array([110.0, 120.0, 130.0, 100.0])
    ys = np.array([100.0, 100.0, 100.0, 100.0])
    e = com.sesgo_reciente(med, ys, k=2)
    assert e == pytest.approx(np.mean(np.log1p([130.0, 100.0]) - np.log1p(100.0)))
    assert com.sesgo_reciente(med[:3], ys[:3], k=8, minimo=4) == 0.0
    q = np.linspace(50, 150, 23)
    assert np.allclose(com.desplazar(q, 0.0), q)
    assert np.all(com.desplazar(q, -0.2) < q)


def test_peso_reciente_elige_el_mejor_y_desempata_hacia_medio():
    y = [100.0] * 10
    q_bueno = [np.linspace(90, 110, 23)] * 10
    q_malo = [np.linspace(300, 400, 23)] * 10
    assert com.peso_reciente(q_bueno, q_malo, y, k=10) == 1.0
    assert com.peso_reciente(q_malo, q_bueno, y, k=10) == 0.0
    assert com.peso_reciente(q_bueno, q_bueno, y, k=10) == 0.5  # empate total
    assert com.peso_reciente(q_bueno, q_malo, y[:3], k=10) == 0.5  # pocos pares


def test_pares_conocidos_solo_anteriores_y_recientes():
    origen = date(2025, 6, 1)
    fechas = [origen - timedelta(days=7 * k) for k in (60, 10, 3, 0)] + [origen + timedelta(days=7)]
    idx = com.pares_conocidos(fechas, origen, semanas=52)
    assert idx == [1, 2]


# --- metricas ---------------------------------------------------------------


def test_metricas_coincide_con_wis_y_cobertura_del_adr():
    rng = np.random.default_rng(3)
    y = rng.uniform(50, 150, size=20)
    qs = np.sort(rng.uniform(40, 160, size=(20, 23)), axis=1)
    anios = np.array([2019] * 10 + [2021] * 10)
    ref = np.full(20, 30.0)
    m = com.metricas(y, qs, anios, ref)
    esperado = np.mean([exp.wis(yy, q) for yy, q in zip(y, qs)])
    assert m["wis"] == pytest.approx(esperado)
    assert m["skill_agrupado"] == pytest.approx(1 - esperado / 30.0)
    assert set(m["skill_por_anio"]) == {2019, 2021}
    assert 0 <= m["cobertura_50"] <= m["cobertura_95"] <= 1
    assert m["cobertura_95"] == pytest.approx(exp.cobertura(y, qs, 1, 21))


def test_referencia_coincide_con_la_del_experimento_de_mejora():
    import experimento_nowcast_mejora as mej
    s = _serie_sintetica(T=420, semilla=5)
    excluir = frozenset({30, 31, 200, 201})
    for nombre in mej.REFERENCIAS:
        for o, h in ((300, 4), (380, 8)):
            esperado = mej.referencia(nombre, s, o, h, excluir)
            obtenido = com.referencia(nombre, s, o, h, excluir)
            assert np.allclose(esperado, obtenido)
    # excluir un anio cambia la historia: menos residuos, otra referencia
    con = com.referencia("persistencia_rw", s, 380, 4, anios_excluidos=frozenset({2020, 2016}))
    sin = com.referencia("persistencia_rw", s, 380, 4)
    assert not np.allclose(con, sin)
