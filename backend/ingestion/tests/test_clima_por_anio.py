"""Pruebas de analisis_clima_por_anio.py: construccion de z y g, climatologia sin el anio evaluado,
anomalias, bootstrap de bloques, armonicos, aporte del clima, consistencia, ausencia de fuga y de uso de
2024 en adelante. No necesitan Postgres."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analisis_clima_por_anio as cl  # noqa: E402
from experimento_nowcast_corto_plazo import Serie  # noqa: E402


def _ar1(rng, n, rho=0.9, escala=1.0):
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = rho * x[i - 1] + rng.normal(0, escala)
    return x


def _serie(beta_por_anio=None, semilla=0, anios=range(2014, 2025), con_semana_53=()):
    """Serie sintetica: temp_media = estacion + anomalia AR(1) y casos cuyo crecimiento a 4 semanas sigue
    beta * (suma de las anomalias de las 4 semanas previas). Las demas variables son ruido independiente."""
    rng = np.random.default_rng(semilla)
    beta_por_anio = beta_por_anio or {}
    fechas, anio, semana = [], [], []
    d = date(2014, 1, 5)
    for a in anios:
        for s in range(1, 54 if a in con_semana_53 else 53):
            fechas.append(d)
            anio.append(a)
            semana.append(s)
            d += timedelta(days=7)
    anio, semana = np.array(anio), np.array(semana)
    T = len(anio)
    ang = 2 * np.pi * (np.minimum(semana, 52) - 1) / 52.0
    anomalia = _ar1(rng, T, 0.9, 0.3)
    temp = 25 + 3 * np.sin(ang) + anomalia
    beta = np.array([beta_por_anio.get(int(a), 0.0) for a in anio])
    z = np.zeros(T)
    z[:] = np.log(5000) + 0.8 * np.sin(ang - 1.0)
    acumulado = np.zeros(T)
    for t in range(1, T):
        acumulado[t] = 0.8 * acumulado[t - 1] + beta[t] * anomalia[t - 4 if t >= 4 else 0] / 4.0
    casos = np.round(np.exp(z + acumulado))
    clima = {v: 10 + rng.normal(0, 1, T) for v in cl.VARIABLES_CLIMA}
    clima["temp_media"] = temp
    oni = _ar1(rng, T, 0.97, 0.05)
    doy = np.array([f.timetuple().tm_yday for f in fechas])
    return Serie(np.array(fechas, dtype=object), anio, semana, doy, casos, np.log1p(casos), clima, oni)


# ------------------------------------------------------------ construccion

def test_semana_53_se_pliega_a_la_52():
    assert list(cl.semana_del_anio(np.array([1, 52, 53]))) == [1, 52, 52]


def test_media_ventana_usa_las_semanas_con_dato_y_el_inicio_parcial():
    x = np.array([1.0, np.nan, 3.0, 5.0, 7.0, np.nan, np.nan, np.nan])
    m = cl.media_ventana(x, 4)
    assert m[0] == 1.0
    assert m[1] == 1.0
    assert m[2] == 2.0
    assert m[3] == 3.0
    assert m[4] == pytest.approx((3 + 5 + 7) / 3)
    assert m[7] == 7.0


def test_media_ventana_es_nan_sin_ningun_dato():
    x = np.array([np.nan, np.nan, np.nan, np.nan, np.nan])
    assert np.all(np.isnan(cl.media_ventana(x, 4)))


def test_serie_z_trata_los_ceros_como_faltantes():
    z = cl.serie_z(np.array([10.0, 0.0, 10.0, 10.0, 0.0]))
    assert z[3] == pytest.approx(np.log1p(10.0))
    assert z[4] == pytest.approx(np.log1p(10.0))
    assert np.isnan(cl.serie_z(np.array([0.0, 0.0]))[1])


def test_z_no_mira_el_futuro():
    casos = np.arange(1.0, 41.0)
    a = cl.serie_z(casos)
    b = casos.copy()
    b[25:] = 9999.0
    assert np.array_equal(a[:25], cl.serie_z(b)[:25], equal_nan=True)


def test_crecimiento_no_cruza_de_anio():
    anio = np.array([2021] * 6 + [2022] * 6)
    z = np.arange(12.0)
    g = cl.crecimiento(z, anio, 4)
    assert g[0] == 4.0 and g[1] == 4.0
    assert np.all(np.isnan(g[2:6]))
    assert g[6] == 4.0 and g[7] == 4.0
    assert np.all(np.isnan(g[8:]))


def test_pares_del_anio_tienen_origen_y_objetivo_en_el_anio():
    s = _serie()
    t = cl.pares_del_anio(s.anio, 2019)
    assert len(t) == 52 - cl.H
    assert np.all(s.anio[t] == 2019) and np.all(s.anio[t + cl.H] == 2019)


# --------------------------------------------------------- climatologia

def test_suavizado_circular_constante_y_envolvente():
    assert np.allclose(cl.suavizar_circular(np.full(52, 3.0)), 3.0)
    base = np.zeros(52)
    base[0] = 5.0
    s = cl.suavizar_circular(base)
    assert s[50] == pytest.approx(1.0) and s[51] == pytest.approx(1.0) and s[2] == pytest.approx(1.0)
    assert s[10] == 0.0


def test_suavizado_ignora_semanas_sin_dato():
    base = np.full(52, 2.0)
    base[10] = np.nan
    s = cl.suavizar_circular(base)
    assert np.allclose(s, 2.0)


def test_climatologia_sin_el_anio_evaluado_no_lo_usa():
    s = _serie()
    sem = cl.semana_del_anio(s.semana)
    v = np.full(len(sem), 10.0)
    v[s.anio == 2019] = 1000.0
    con = cl.climatologia(v, sem, s.anio)
    sin = cl.climatologia(v, sem, s.anio, excluir=2019)
    assert con[10] > 100
    assert np.allclose(sin, 10.0)


def test_climatologia_ignora_2020_y_2024():
    s = _serie()
    sem = cl.semana_del_anio(s.semana)
    v = np.full(len(sem), 10.0)
    base = cl.climatologia(v, sem, s.anio)
    v[(s.anio == 2020) | (s.anio == 2024)] = 5000.0
    assert np.array_equal(cl.climatologia(v, sem, s.anio), base)


def test_anomalia_de_una_serie_exactamente_estacional_es_cero():
    s = _serie()
    sem = cl.semana_del_anio(s.semana)
    v = 20 + 4 * np.sin(2 * np.pi * (sem - 1) / 52.0)
    an = cl.anomalia(v, sem, s.anio, 2019)
    assert np.nanmax(np.abs(an[np.isin(s.anio, cl.ANIOS)])) < 1.0
    # el suavizado de 5 semanas aplana la cresta de la onda: el residuo es pequeno frente a la amplitud
    assert np.nanstd(an[s.anio == 2019]) < 0.4


def test_con_semana_53_la_climatologia_tiene_52_valores():
    s = _serie(con_semana_53=(2015,))
    sem = cl.semana_del_anio(s.semana)
    assert len(cl.climatologia(s.casos.astype(float), sem, s.anio)) == 52


# ------------------------------------------------------------ estadisticos

def test_pearson_basico_y_constante():
    x = np.arange(10.0)
    assert cl.pearson(x, 2 * x + 1) == pytest.approx(1.0)
    assert cl.pearson(x, -x) == pytest.approx(-1.0)
    assert np.isnan(cl.pearson(x, np.ones(10)))
    assert np.isnan(cl.pearson(x[:2], x[:2]))


def test_indices_bloques_forma_rango_y_contiguidad():
    rng = np.random.default_rng(1)
    idx = cl.indices_bloques(45, 8, 100, rng)
    assert idx.shape == (100, 45)
    assert idx.min() >= 0 and idx.max() < 45
    assert np.all(np.diff(idx[:, :8], axis=1) == 1)


def test_indices_bloques_reproducibles_y_con_bloque_mayor_que_n():
    a = cl.indices_bloques(30, 8, 50, np.random.default_rng([cl.SEMILLA, 2019]))
    b = cl.indices_bloques(30, 8, 50, np.random.default_rng([cl.SEMILLA, 2019]))
    assert np.array_equal(a, b)
    c = cl.indices_bloques(5, 8, 10, np.random.default_rng(0))
    assert c.shape == (10, 5) and c.max() < 5


def test_correlaciones_por_fila_coinciden_con_pearson():
    rng = np.random.default_rng(2)
    x, y = rng.normal(size=(6, 40)), rng.normal(size=(6, 40))
    r = cl.correlaciones_filas(x, y)
    for i in range(6):
        assert r[i] == pytest.approx(cl.pearson(x[i], y[i]))


def test_intervalo_none_si_muchas_replicas_son_nan():
    assert cl.intervalo(np.array([np.nan] * 10)) == [None, None]
    ic = cl.intervalo(np.linspace(-1, 1, 101))
    assert ic[0] < -0.9 and ic[1] > 0.9


def test_r2_armonicos_onda_pura_y_ruido():
    sem = np.tile(np.arange(1, 53), 5)
    onda = 3 + 2 * np.sin(2 * np.pi * (sem - 1) / 52) + np.cos(4 * np.pi * (sem - 1) / 52)
    assert cl.r2_armonicos(onda, sem) == pytest.approx(1.0)
    ruido = np.random.default_rng(3).normal(size=len(sem))
    assert cl.r2_armonicos(ruido, sem) < 0.15
    assert np.isnan(cl.r2_armonicos(np.ones(len(sem)), sem))


def test_limpio_cambia_los_no_finitos_por_none():
    o = {"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": 2.0}}
    assert cl.limpio(o) == {"a": None, "b": [1.0, None], "c": {"d": 2.0}}
    json.dumps(cl.limpio(o), allow_nan=False)


# ----------------------------------------------------------------------- A1

def _insumos():
    def var(skills):
        return {"skill_por_anio": skills}

    return {
        "fases": {
            "validacion": {
                "tablas": {
                    "limpia": {
                        "4": {
                            "I0": var({"2019": 0.06, "2021": 0.04, "2022": -0.15}),
                            "I1": var({"2019": 0.05, "2021": 0.05, "2022": -0.16}),
                            "I2": var({"2019": 0.10, "2021": -0.03, "2022": -0.47}),
                            "I3": var({"2019": 0.11, "2021": -0.02, "2022": -0.50}),
                            "I4": var({"2019": 0.00, "2021": 0.01, "2022": -0.10}),
                        }
                    }
                }
            }
        }
    }


def test_aporte_clima_positivo_cuando_quitarlo_empeora():
    a = cl.aporte_clima(_insumos())["4"]
    assert a["clima"]["por_anio"] == {"2019": -0.04, "2021": 0.07, "2022": 0.32}
    assert a["clima"]["anios_a_favor"] == 2 and a["clima"]["anios"] == 3
    assert a["oni"]["por_anio"]["2019"] == pytest.approx(0.01)
    assert a["anio"]["por_anio"]["2019"] == pytest.approx(0.06)
    assert a["skill_I0"]["2022"] == -0.15


def test_aporte_clima_con_el_archivo_real_si_existe():
    if not cl.ENTRADA_INSUMOS.exists():
        pytest.skip("no esta insumos.json")
    a = cl.aporte_clima(json.loads(cl.ENTRADA_INSUMOS.read_text(encoding="utf-8")))
    assert sorted(a) == [str(h) for h in range(1, 9)]
    assert sorted(a["4"]["clima"]["por_anio"]) == ["2019", "2021", "2022", "2023", "2024"]


# ----------------------------------------------------------------------- A2

def test_estacionalidad_encuentra_el_desfase_y_el_r2_alto():
    s = _serie(semilla=4)
    sem = cl.semana_del_anio(s.semana)
    ang = 2 * np.pi * (sem - 1) / 52.0
    desfase = 6
    for v in cl.VARIABLES_CLIMA:
        s.clima[v] = 20 + 3 * np.sin(ang)
    casos = np.round(np.exp(5 + 0.8 * np.sin(2 * np.pi * (sem - 1 - desfase) / 52.0)))
    s.casos[:] = casos
    z = cl.serie_z(s.casos)
    e = cl.estacionalidad(s, z)
    f = e["por_variable"]["temp_media"]
    assert f["r2_estacional"] == pytest.approx(1.0, abs=1e-6)
    assert desfase <= f["desfase_mejor_semanas"] <= desfase + 3
    assert f["correlacion_en_el_mejor"] > 0.95
    assert len(f["climatologia"]) == 52 and len(e["casos_climatologia"]) == 52
    assert e["casos_r2_estacional"] > 0.9


# ----------------------------------------------------------------------- A3

def test_asociacion_recupera_el_signo_plantado_y_el_anio_invertido():
    betas = {a: 4.0 for a in cl.ANIOS}
    betas[2017] = -4.0
    s = _serie(betas, semilla=5)
    z = cl.serie_z(s.casos)
    g = cl.crecimiento(z, s.anio)
    a3 = cl.asociaciones(s, z, g, remuestreos=200)
    rs = {a: a3["por_anio"][str(a)]["temp_media"]["r"] for a in cl.ANIOS}
    assert rs[2017] < 0
    otros = [r for a, r in rs.items() if a != 2017]
    assert min(otros) > 0.05 and np.median(otros) > 0.5
    assert a3["por_anio"]["2019"]["pares"] > 30
    pooled = a3["agrupado"]["temp_media"]
    assert pooled["r"] > 0.1
    # ninguna variable de ruido aparece como consistente
    a5 = cl.consistencia(a3)
    assert a5["temp_media"]["anios_positivos"] == 8 and a5["temp_media"]["anios_negativos"] == 1
    assert a5["temp_media"]["consistente"]


def test_sin_efecto_plantado_ninguna_variable_es_consistente():
    s = _serie({}, semilla=6)
    z = cl.serie_z(s.casos)
    g = cl.crecimiento(z, s.anio)
    a5 = cl.consistencia(cl.asociaciones(s, z, g, remuestreos=200))
    assert not any(f["consistente"] for f in a5.values())


def test_bootstrap_reproducible_con_la_semilla():
    s = _serie({a: 2.0 for a in cl.ANIOS}, semilla=7)
    z = cl.serie_z(s.casos)
    g = cl.crecimiento(z, s.anio)
    a = cl.asociaciones(s, z, g, remuestreos=100)
    b = cl.asociaciones(s, z, g, remuestreos=100)
    assert a == b


def test_la_anomalia_de_g_no_usa_el_anio_evaluado():
    s = _serie({a: 2.0 for a in cl.ANIOS}, semilla=8)
    z = cl.serie_z(s.casos)
    g = cl.crecimiento(z, s.anio)
    d1 = cl.datos_del_anio(s, z, g, 2019)
    g2 = g.copy()
    g2[s.anio == 2019] += 7.0
    d2 = cl.datos_del_anio(s, z, g2, 2019)
    # sumar una constante al anio evaluado se traslada entero a su anomalia: la climatologia no lo ve
    assert np.allclose(d2["g"] - d1["g"], 7.0)


# ----------------------------------------------------------------------- A4

def test_perfiles_total_pico_y_spearman():
    s = _serie({}, semilla=9)
    sem = cl.semana_del_anio(s.semana)
    # un pico claro en la semana 30 de cada anio, mas alto cuanto mas reciente el anio
    s.casos[:] = 100.0
    for k, a in enumerate(cl.ANIOS):
        s.casos[(s.anio == a) & (sem == 30)] = 1000.0 * (k + 1)
        s.clima["temp_media"][s.anio == a] += k  # anomalia media crece con el anio
    z = cl.serie_z(s.casos)
    p = cl.perfiles(s, z)
    assert p["n"] == 9
    for a in cl.ANIOS:
        assert p["por_anio"][str(a)]["semana_del_pico"] in (30, 31, 32, 33)
    assert p["por_anio"]["2014"]["casos_totales"] == pytest.approx(s.casos[s.anio == 2014].sum())
    totales = [p["por_anio"][str(a)]["casos_totales"] for a in cl.ANIOS]
    assert totales == sorted(totales)
    assert p["spearman_total_vs_anomalia_media"]["temp_media"] == pytest.approx(1.0)


# ----------------------------------------------------------------------- A5

def _a3(rs, pool_ic):
    por_anio = {str(a): {"temp_media": {"r": r, "ic95": [r - 0.2, r + 0.2]}} for a, r in zip(cl.ANIOS, rs)}
    return {"por_anio": por_anio, "agrupado": {"temp_media": {"r": 0.2, "ic95": pool_ic}}}


def _consistencia_una_variable(rs, pool_ic):
    original = cl.VARIABLES
    cl.VARIABLES = ("temp_media",)
    try:
        return cl.consistencia(_a3(rs, pool_ic))["temp_media"]
    finally:
        cl.VARIABLES = original


def test_regla_de_consistencia_es_8_de_9_mas_intervalo_agrupado_sin_cero():
    ocho = [0.3] * 8 + [-0.1]
    assert _consistencia_una_variable(ocho, [0.05, 0.3])["consistente"]
    assert not _consistencia_una_variable(ocho, [-0.05, 0.3])["consistente"]
    siete = [0.3] * 7 + [-0.1, -0.1]
    assert not _consistencia_una_variable(siete, [0.05, 0.3])["consistente"]
    todos_negativos = [-0.3] * 9
    assert _consistencia_una_variable(todos_negativos, [-0.4, -0.05])["consistente"]


def test_consistencia_cuenta_anios_con_intervalo_sin_cero():
    f = _consistencia_una_variable([0.5, 0.5, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1], [0.0, 0.2])
    assert f["anios_con_ic_sin_cero"] == 2
    assert f["r_minimo"] == 0.1 and f["r_maximo"] == 0.5


# ---------------------------------------------------------- limites de datos

def test_2024_no_entra_en_ningun_resultado():
    s = _serie({a: 2.0 for a in cl.ANIOS}, semilla=10)
    base = cl.calcular(s, _insumos(), remuestreos=50)
    t24 = s.anio == 2024
    s.casos[t24] = 99999.0
    for v in cl.VARIABLES_CLIMA:
        s.clima[v][t24] = 1e6
    s.oni[t24] = 50.0
    assert cl.calcular(s, _insumos(), remuestreos=50) == base


def test_calcular_produce_json_valido_y_las_secciones():
    s = _serie({a: 1.0 for a in cl.ANIOS}, semilla=11)
    r = cl.calcular(s, _insumos(), remuestreos=50)
    assert set(r) == {"parametros", "A1", "A2", "A3", "A4", "A5", "series"}
    json.dumps(cl.limpio(r), allow_nan=False)
    assert sorted(r["series"]) == [str(a) for a in cl.ANIOS]
    una = r["series"]["2019"]
    assert len(una["semana"]) == len(una["casos_4sem"]) == len(una["oni"]) == 52
    assert len(una["temp_media"]["anomalia"]) == 52
