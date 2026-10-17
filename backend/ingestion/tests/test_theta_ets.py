"""Pruebas de las funciones puras de experimento_nowcast_theta_ets.py: ETS y Theta contra
implementaciones independientes, casos exactos (series lineales y constantes), causalidad, cuantiles
contra `Reglas`, regla de cambio, elegibilidad y confirmacion. No necesitan Postgres."""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import experimento_nowcast_mejora as mej  # noqa: E402
import experimento_nowcast_theta_ets as te  # noqa: E402
import experimento_nowcast_tendencia_seleccion as sel  # noqa: E402
from experimento_nowcast_corto_plazo import ANIO_EXCLUIDO, Serie, wis  # noqa: E402

HS = te.HORIZONTES
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


def _z_aleatoria(n: int = 120, semilla: int = 1, huecos: tuple[int, ...] = ()) -> np.ndarray:
    z = 4.0 + np.cumsum(np.random.default_rng(semilla).normal(0.0, 0.2, n))
    for k in huecos:
        z[k] = np.nan
    return z


# --- ETS ------------------------------------------------------------------------------


def _ets_a_mano(z, alfa, beta, phi):
    """Implementacion independiente: listas de nivel y pendiente, una semana a la vez."""
    nivel, pend = [z[0]], [0.0]
    for t in range(1, len(z)):
        if np.isfinite(z[t]):
            l_nuevo = alfa * z[t] + (1 - alfa) * (nivel[-1] + phi * pend[-1])
            b_nuevo = beta * (l_nuevo - nivel[-1]) + (1 - beta) * phi * pend[-1]
        else:
            l_nuevo, b_nuevo = nivel[-1] + phi * pend[-1], phi * pend[-1]
        nivel.append(l_nuevo)
        pend.append(b_nuevo)
    return np.array([[nivel[t] + pend[t] * sum(phi ** i for i in range(1, h + 1)) for h in HS] for t in range(len(z))])


@pytest.mark.parametrize("alfa, beta, phi", [(0.4, 0.2, 0.8), (0.8, 0.6, 0.9), (1.0, 1.0, 0.95), (0.6, 1.0, 0.8)])
def test_ets_coincide_con_la_implementacion_independiente(alfa, beta, phi):
    z = _z_aleatoria(huecos=(50, 51, 90))
    assert np.allclose(te.medianas_ets(z, alfa, beta, phi), _ets_a_mano(z, alfa, beta, phi), rtol=0, atol=1e-12)


def test_ets_con_alfa_y_beta_uno_es_t_con_pendiente_de_una_semana():
    z = _z_aleatoria()
    mu = te.medianas_ets(z, 1.0, 1.0, 0.8)
    f = te.factores_amortiguados(0.8)
    for t in range(1, len(z)):
        assert np.allclose(mu[t], z[t] + (z[t] - z[t - 1]) * f, rtol=0, atol=1e-12)


def test_ets_sin_amortiguar_sigue_una_serie_lineal():
    z = 2.0 + 0.1 * np.arange(60)
    mu = te.medianas_ets(z, 1.0, 1.0, 1.0)
    for t in range(1, 60):
        assert np.allclose(mu[t], z[t] + 0.1 * np.array(HS), atol=1e-12)


def test_ets_serie_constante_es_constante():
    mu = te.medianas_ets(np.full(40, 3.3), 0.6, 0.4, 0.9)
    assert np.allclose(mu, 3.3)


def test_ets_semana_sin_dato_avanza_el_estado_sin_actualizarlo():
    z = _z_aleatoria(60)
    z_h = z.copy()
    z_h[30] = np.nan
    mu, mu_h = te.medianas_ets(z, 0.7, 0.5, 0.9), te.medianas_ets(z_h, 0.7, 0.5, 0.9)
    assert np.array_equal(mu[:30], mu_h[:30]) and np.all(np.isfinite(mu_h))
    # la pendiente de la semana sin dato es phi veces la anterior y el nivel avanza con ella
    f = te.factores_amortiguados(0.9)

    def estado(t):
        pend = (mu_h[t, 1] - mu_h[t, 0]) / (f[1] - f[0])
        return mu_h[t, 0] - pend * f[0], pend

    n29, b29 = estado(29)
    n30, b30 = estado(30)
    assert b30 == pytest.approx(0.9 * b29) and n30 == pytest.approx(n29 + 0.9 * b29)


# --- Theta ----------------------------------------------------------------------------


def _pendiente_a_mano(z, ele):
    out = np.full(len(z), np.nan)
    minimo = max(3, int(np.ceil(ele / 2)))
    for t in range(len(z)):
        idx = [i for i in range(max(0, t - ele + 1), t + 1) if np.isfinite(z[i])]
        if len(idx) >= minimo:
            out[t] = np.polyfit(idx, z[idx], 1)[0]
    return out


@pytest.mark.parametrize("ele", [6, 8, 12, 26])
def test_pendiente_ols_coincide_con_polyfit_y_respeta_el_minimo(ele):
    z = _z_aleatoria(80, huecos=(20, 21, 22, 23, 60))
    mia, ref = te.pendiente_ols(z, ele), _pendiente_a_mano(z, ele)
    assert np.array_equal(np.isnan(mia), np.isnan(ref))
    assert np.allclose(mia[~np.isnan(mia)], ref[~np.isnan(ref)], rtol=0, atol=1e-10)


def test_pendiente_ols_de_una_recta_es_su_pendiente():
    z = 1.0 + 0.25 * np.arange(50)
    assert np.allclose(te.pendiente_ols(z, 8)[10:], 0.25)


def test_nivel_ses_con_alfa_uno_es_la_serie_y_se_congela_sin_dato():
    z = _z_aleatoria(40, huecos=(10,))
    nivel = te.nivel_ses(z, 1.0)
    assert np.array_equal(nivel[:10], z[:10]) and nivel[10] == z[9] and nivel[11] == z[11]


def _theta_a_mano(z, alfa, ele):
    nivel = [z[0]]
    for t in range(1, len(z)):
        nivel.append(alfa * z[t] + (1 - alfa) * nivel[-1] if np.isfinite(z[t]) else nivel[-1])
    b = _pendiente_a_mano(z, ele)
    return np.array([[nivel[t] + b[t] / 2 * (h - 1 + 1 / alfa) for h in HS] for t in range(len(z))])


@pytest.mark.parametrize("alfa, ele", [(0.3, 6), (0.7, 12), (1.0, 26), (0.5, 8)])
def test_theta_coincide_con_la_implementacion_independiente(alfa, ele):
    z = _z_aleatoria(150, huecos=(70, 71))
    mia, ref = te.medianas_theta(z, alfa, ele), _theta_a_mano(z, alfa, ele)
    assert np.array_equal(np.isnan(mia), np.isnan(ref))
    assert np.allclose(mia[~np.isnan(mia)], ref[~np.isnan(ref)], rtol=0, atol=1e-10)


def test_theta_con_alfa_uno_es_nivel_mas_media_pendiente_por_h():
    z = _z_aleatoria(60)
    mu = te.medianas_theta(z, 1.0, 6)
    b = te.pendiente_ols(z, 6)
    for t in range(6, 60):
        assert np.allclose(mu[t], z[t] + b[t] / 2 * np.array(HS), atol=1e-12)


@pytest.mark.parametrize("alfa", [0.3, 0.6, 1.0])
def test_theta_en_serie_lineal_da_la_mitad_de_la_pendiente_menos_el_retraso(alfa):
    pend = 0.07
    z = 1.0 + pend * np.arange(400)
    mu = te.medianas_theta(z, alfa, 12)
    esperado = z[-1] + pend * np.array(HS) / 2 - pend * (1 - alfa) / (2 * alfa)
    assert np.allclose(mu[-1], esperado, atol=1e-9)


# --- causalidad ---------------------------------------------------------------------------


@pytest.mark.parametrize("fn", [lambda z: te.medianas_ets(z, 0.6, 0.4, 0.9), lambda z: te.medianas_theta(z, 0.5, 12)])
def test_la_mediana_de_un_origen_no_usa_el_futuro(fn):
    z = _z_aleatoria(150, huecos=(40,))
    completo = fn(z)
    for t in (30, 77, 120):
        alterada = z.copy()
        alterada[t + 1:] = np.random.default_rng(9).normal(10.0, 3.0, len(z) - t - 1)
        assert np.array_equal(fn(alterada)[: t + 1], completo[: t + 1], equal_nan=True)
        assert np.array_equal(fn(z[: t + 1])[t], completo[t], equal_nan=True)


# --- cuantiles ------------------------------------------------------------------------------


def test_rejillas_del_protocolo():
    assert len(te.REJILLA_ETS) == 60 and len(te.REJILLA_THETA) == 25
    assert (1.0, 1.0, 0.8) in te.REJILLA_ETS
    assert te.VIGENTE == (0.8, 3) and te.PESO_M0 == 0.5


def test_ets_alfa_beta_uno_reproduce_reglas_con_pendiente_de_una_semana():
    s = _serie_sintetica()
    rm, reglas = te.ReglasMu(s), sel.Reglas(s)
    comprobados = 0
    for h in HS:
        for o in range(200, s.T - h, 7):
            assert np.allclose(rm.cuantiles(o, h, "ets", (1.0, 1.0, 0.8)), reglas.cuantiles(o, h, 0.8, 1), rtol=0, atol=1e-9)
            comprobados += 1
    assert comprobados > 100


def test_los_errores_excluyen_2020_antes_de_2014_y_pares_sin_dato():
    s = _serie_sintetica(huecos=(400,))
    rm = te.ReglasMu(s)
    for h in (1, 4, 8):
        ts, d = rm._errores("ets", (0.6, 0.4, 0.9), h)
        assert np.all(s.anio[ts + h] >= te.ALCANCE_HISTORIA) and not np.any(s.anio[ts + h] == ANIO_EXCLUIDO)
        assert 400 not in ts and 400 - h not in ts and np.all(np.isfinite(d))


@pytest.mark.parametrize("familia, cfg", [("ets", (0.6, 0.4, 0.9)), ("theta", (0.5, 12))])
def test_los_cuantiles_de_un_origen_no_usan_el_futuro(familia, cfg):
    s = _serie_sintetica()
    o, h = 450, 4
    q = te.ReglasMu(s).cuantiles(o, h, familia, cfg)
    futuro = s.z.copy()
    futuro[o + 1:] = np.random.default_rng(5).normal(9.0, 2.0, s.T - o - 1)
    q2 = te.ReglasMu(replace(s, z=futuro)).cuantiles(o, h, familia, cfg)
    assert np.array_equal(q, q2)


def test_cuantiles_ordenados_y_no_negativos():
    s = _serie_sintetica()
    rm = te.ReglasMu(s)
    for fam, cfg in (("ets", (0.8, 0.6, 0.95)), ("theta", (0.9, 26))):
        q = rm.cuantiles(500, 8, fam, cfg)
        assert np.all(np.diff(q) >= 0) and q.min() >= 0 and len(q) == 23


def test_la_familia_desconocida_se_rechaza():
    with pytest.raises(ValueError):
        te.ReglasMu(_serie_sintetica(50)).matriz("arima", (1,))


def test_promedio_log1p():
    a, b = _q(100.0, 0.2), _q(400.0, 0.4)
    assert np.allclose(te.promedio_log1p([a, a, a]), a)
    assert np.allclose(np.log1p(te.promedio_log1p([a, b])), (np.log1p(a) + np.log1p(b)) / 2)
    tres = te.promedio_log1p([a, b, a])
    assert np.allclose(np.log1p(tres), (2 * np.log1p(a) + np.log1p(b)) / 3) and np.all(np.diff(tres) >= 0)


def test_skills_base_de_la_referencia_es_cero():
    s = _serie_sintetica()
    reglas = sel.Reglas(s)
    orig = sel.origenes_validacion(s)
    w_ref = te.referencia_validacion(reglas, orig, s)
    sk = te.skills_base(lambda o, h: reglas.cuantiles(o, h, 0.0, sel.V_REF), orig, s, w_ref)
    assert all(abs(sk[h][a]) < 1e-12 for h in HS for a in sel.ANIOS_VALIDACION)
    sk_t = te.skills_base(te.fn_t(reglas), orig, s, w_ref)
    sk_sel = sel.skills_validacion(reglas, orig, te.VIGENTE)
    assert max(abs(sk_t[h][a] - sk_sel[h][a]) for h in HS for a in sel.ANIOS_VALIDACION) < te.TOL_SKILL


# --- regla de cambio ---------------------------------------------------------------------------


def _sk(valor_por_anio: dict[int, float]) -> dict:
    return {h: dict(valor_por_anio) for h in HS}


T_BASE = _sk({2018: 0.10, 2019: 0.10, 2021: 0.10, 2022: 0.10, 2023: 0.10})


def test_regla_de_cambio_pasa_con_ganancia_y_tres_anios():
    sk = {(1,): _sk({2018: 0.12, 2019: 0.12, 2021: 0.12, 2022: 0.09, 2023: 0.09})}  # +0,012 y 3 anios
    e = te.elegir_familia(sk, T_BASE)
    assert e["pasa_regla_de_cambio"] and e["anios_en_que_supera"] == 3 and e["mejor"] == [1]


def test_regla_de_cambio_exige_ganancia_minima():
    sk = {(1,): _sk({a: 0.104 for a in sel.ANIOS_VALIDACION})}  # +0,004 en los cinco anios
    e = te.elegir_familia(sk, T_BASE)
    assert not e["pasa_regla_de_cambio"] and e["anios_en_que_supera"] == 5


def test_regla_de_cambio_exige_tres_anios():
    sk = {(1,): _sk({2018: 0.20, 2019: 0.20, 2021: 0.09, 2022: 0.09, 2023: 0.09})}  # +0,034 pero 2 anios
    e = te.elegir_familia(sk, T_BASE)
    assert not e["pasa_regla_de_cambio"] and e["anios_en_que_supera"] == 2


def test_regla_de_cambio_no_pasa_si_la_familia_es_peor_que_t():
    sk = {(1,): _sk({a: 0.05 for a in sel.ANIOS_VALIDACION}), (2,): _sk({a: 0.08 for a in sel.ANIOS_VALIDACION})}
    e = te.elegir_familia(sk, T_BASE)
    assert e["mejor"] == [2] and e["ganancia"] < 0 and not e["pasa_regla_de_cambio"] and e["configuraciones_que_superan_a_T"] == 0


# --- extension E1 -------------------------------------------------------------------------------------


def test_rejillas_de_la_extension():
    assert len(te.REJILLA_ETS_E1) == 60 and len(te.REJILLA_THETA_E1) == 15
    assert not set(te.REJILLA_ETS_E1) & set(te.REJILLA_ETS) and not set(te.REJILLA_THETA_E1) & set(te.REJILLA_THETA)
    assert {c[2] for c in te.REJILLA_ETS_E1} == {0.5, 0.6, 0.7} and {c[1] for c in te.REJILLA_THETA_E1} == {3, 4, 5}


def test_la_extension_sustituye_con_margen_sobre_la_original_y_regla_frente_a_t():
    orig = _sk({2018: 0.12, 2019: 0.12, 2021: 0.12, 2022: 0.12, 2023: 0.12})  # +0,02 sobre T
    ext = {(9,): _sk({2018: 0.14, 2019: 0.14, 2021: 0.14, 2022: 0.14, 2023: 0.10})}  # +0,02 sobre la original en 4 anios
    d = te.decidir_extension(ext, orig, T_BASE)
    assert d["sustituye"] and d["anios_sobre_la_original"] == 4 and d["mejor_extension"] == [9]


def test_la_extension_no_sustituye_sin_margen_o_sin_anios():
    orig = _sk({a: 0.12 for a in sel.ANIOS_VALIDACION})
    poco = {(9,): _sk({a: 0.123 for a in sel.ANIOS_VALIDACION})}  # +0,003: menos que el margen
    assert not te.decidir_extension(poco, orig, T_BASE)["sustituye"]
    pocos_anios = {(9,): _sk({2018: 0.30, 2019: 0.30, 2021: 0.10, 2022: 0.10, 2023: 0.10})}  # +0,04 pero 2 anios
    d = te.decidir_extension(pocos_anios, orig, T_BASE)
    assert not d["sustituye"] and d["anios_sobre_la_original"] == 2


def test_la_extension_exige_la_regla_de_cambio_frente_a_t_aunque_supere_a_la_original():
    orig = _sk({a: 0.05 for a in sel.ANIOS_VALIDACION})  # peor que T
    ext = {(9,): _sk({a: 0.08 for a in sel.ANIOS_VALIDACION})}  # mejor que la original, peor que T
    d = te.decidir_extension(ext, orig, T_BASE)
    assert d["ganancia_sobre_la_original"] > 0.005 and d["anios_sobre_la_original"] == 5
    assert not d["frente_a_T"]["pasa_regla_de_cambio"] and not d["sustituye"]


# --- confirmacion y elegibilidad ------------------------------------------------------------------


def _conjunto(n: int = 14, semilla: int = 2) -> dict:
    rng = np.random.default_rng(semilla)
    out = {}
    for h in HS:
        y = rng.uniform(80.0, 160.0, n)
        out[h] = {"o": np.arange(n), "y": y, "q_m0": np.array([_q(100.0, 0.4)] * n),
                  "wis_ref_guardado": np.array([wis(float(v), _q(100.0, 0.5)) for v in y])}
    return out


def test_confirmar_c_con_la_misma_base_da_razon_uno():
    b = {"H1": _conjunto(), "H2": _conjunto(semilla=4)}
    fn = lambda o, h: _q(110.0, 0.3)
    conf = te.confirmar_c(fn, fn, b)
    for nombre in ("H1", "H2"):
        assert conf[nombre]["razon_media_C"] == 1.0 and conf[nombre]["razon_media_base_vs_T"] == 1.0
        assert conf[nombre]["cob95_Cp"] == conf[nombre]["cob95_C"]
        assert all(f["dm_Cp_menos_C"] is None for f in conf[nombre]["por_h"].values())  # perdida identica


def test_confirmar_c_mide_la_razon_y_las_coberturas():
    b = {"H1": _conjunto(), "H2": _conjunto(semilla=4)}
    q_t, q_b = _q(60.0, 0.3), _q(140.0, 0.3)  # con M0 en 100, la base acerca C a los datos (80 a 160)
    conf = te.confirmar_c(lambda o, h: q_b, lambda o, h: q_t, b)
    d = b["H2"][3]
    w_c = np.mean([wis(float(y), mej._mezcla(m, q_t, 0.5)) for y, m in zip(d["y"], d["q_m0"])])
    w_cp = np.mean([wis(float(y), mej._mezcla(m, q_b, 0.5)) for y, m in zip(d["y"], d["q_m0"])])
    assert conf["H2"]["por_h"][3]["razon_C"] == pytest.approx(w_cp / w_c)
    assert conf["H2"]["por_h"][3]["razon_C"] < 1 and conf["H2"]["razon_media_C"] < 1
    assert conf["H2"]["por_h"][3]["Cp"]["wis"] == pytest.approx(w_cp)
    assert 0.0 <= conf["H2"]["cob95_Cp"] <= 1.0 and conf["H2"]["razon_media_por_grupo"].keys() == sel.GRUPOS.keys()


def _conf(r1, r2, cob_cp, cob_c):
    return {"H1": {"razon_media_C": r1}, "H2": {"razon_media_C": r2, "cob95_Cp": cob_cp, "cob95_C": cob_c}}


@pytest.mark.parametrize("pasa_a, r1, r2, cp, c, esperado", [
    (True, 0.98, 0.97, 0.90, 0.91, True),
    (True, 1.00, 0.97, 0.90, 0.91, False),    # H1 no mejora
    (True, 0.98, 1.001, 0.90, 0.91, False),   # H2 no mejora
    (True, 0.98, 0.97, 0.87, 0.91, False),    # cobertura 0,04 abajo
    (True, 0.98, 0.97, 0.88, 0.91, True),     # cobertura 0,03 abajo: dentro de la tolerancia
    (False, 0.90, 0.90, 0.95, 0.91, False),   # no pasa la regla de cambio
    (None, 0.98, 0.97, 0.90, 0.91, True),     # promedio de bases: sin regla de seleccion
    (None, 0.98, 1.02, 0.90, 0.91, False),
])
def test_elegibilidad(pasa_a, r1, r2, cp, c, esperado):
    assert te.elegible(pasa_a, _conf(r1, r2, cp, c))["elegible"] is esperado


def test_holm_entre_todas_las_comparaciones():
    def res(p):
        por_h = {h: {"dm_Cp_menos_C": {"p": p}} for h in HS}
        return {"H1": {"por_h": por_h}, "H2": {"por_h": por_h}}
    b_res = {"ets": {"confirmacion": res(0.001)}, "theta": {"confirmacion": res(0.5)}}
    h = te.holm_dm(b_res, {"confirmacion": res(0.04)})
    assert len(h["p_crudo"]) == 48
    assert h["p_holm"]["ets_H1_h1"] == pytest.approx(0.048) and h["p_holm"]["theta_H1_h1"] == 1.0
    assert all(h["p_holm"][k] >= h["p_crudo"][k] for k in h["p_crudo"])
