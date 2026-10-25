"""Pruebas de analisis_clima_multipais.py: lectura de casos y clima, rejilla semanal, senal regional,
estabilidad, asociaciones por pais, ciclo medio, lectura de corridas anteriores y posiciones.
No necesitan Postgres ni los archivos de datos."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analisis_clima_multipais as mp  # noqa: E402
import analisis_clima_por_anio as base  # noqa: E402


def _ar1(rng, n, rho=0.9, escala=1.0):
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = rho * x[i - 1] + rng.normal(0, escala)
    return x


def _pais(nombre="EL SALVADOR", beta=0.0, semilla=0, nivel=5000.0, solo_lluvia=False):
    """Pais sintetico: 11 anios semanales desde 2014-01-05, temp_media con anomalia AR(1) y crecimiento
    de los casos proporcional a la suma de las anomalias de las 4 semanas previas."""
    rng = np.random.default_rng(semilla)
    fechas = [date(2014, 1, 5) + timedelta(days=7 * i) for i in range(0, 572)]
    fechas = [f for f in fechas if f.year <= 2024]
    n = len(fechas)
    anio = np.array([f.year for f in fechas])
    sem = mp.semana_del_anio_fecha(fechas)
    ang = 2 * np.pi * (sem - 1) / 52.0
    anomalia = _ar1(rng, n, 0.9, 0.3)
    acumulado = np.zeros(n)
    for t in range(1, n):
        acumulado[t] = 0.8 * acumulado[t - 1] + beta * anomalia[t - 4 if t >= 4 else 0] / 4.0
    casos = np.round(nivel * np.exp(0.8 * np.sin(ang - 1.0) + acumulado))
    clima = {v: 10 + rng.normal(0, 1, n) for v in base.VARIABLES_CLIMA}
    clima["temp_media"] = 25 + 3 * np.sin(ang) + anomalia
    if solo_lluvia:
        for v in base.VARIABLES_CLIMA:
            if v not in mp.ACUMULATIVAS:
                clima[v] = np.full(n, np.nan)
    oni = _ar1(rng, n, 0.97, 0.05)
    return mp.Pais(nombre, np.array(fechas, dtype=object), anio, sem, casos, clima, oni)


# --------------------------------------------------------------- lectura

def test_semana_del_anio_por_fecha():
    s = mp.semana_del_anio_fecha([date(2020, 1, 1), date(2020, 1, 8), date(2020, 12, 31)])
    assert list(s) == [1, 2, 52]


def test_rejilla_deja_faltantes_y_usa_el_anio_de_la_fuente():
    semanas = {
        date(2020, 1, 5): (2020, 10.0),
        date(2020, 1, 12): (2020, 11.0),
        date(2020, 1, 26): (2020, 13.0),
    }
    g = mp.rejilla(semanas)
    assert len(g["casos"]) == 4
    assert np.isnan(g["casos"][2]) and g["casos"][3] == 13.0
    assert g["fecha"][2] == date(2020, 1, 19) and g["anio"][2] == 2020


def test_rejilla_rechaza_dos_semanas_en_la_misma_celda():
    with pytest.raises(ValueError):
        mp.rejilla({date(2020, 1, 5): (2020, 1.0), date(2020, 1, 6): (2020, 2.0)})


def _csv(tmp_path, filas):
    ruta = tmp_path / "pais.csv"
    cab = "adm_0_name,calendar_start_date,Year,dengue_total,S_res,T_res\n"
    ruta.write_text(cab + "\n".join(filas) + "\n", encoding="utf-8")
    return ruta


def test_leer_casos_filtra_admin0_semana_y_anios(tmp_path):
    ruta = _csv(tmp_path, [
        "A,2016-01-03,2016,5,Admin0,Week",
        "A,2016-01-03,2016,9,Admin0,Year",
        "A,2016-01-10,2016,7,Admin1,Week",
        "A,2013-12-29,2013,3,Admin0,Week",
        "A,2016-01-17,2016,x,Admin0,Week",
        "B,2024-12-29,2024,2,Admin0,Week",
    ])
    c = mp.leer_casos(ruta)
    assert c["A"] == {date(2016, 1, 3): (2016, 5.0)}
    assert c["B"] == {date(2024, 12, 29): (2024, 2.0)}


def test_paises_completos_exige_45_semanas_en_los_11_anios():
    def pais(semanas_por_anio):
        d = {}
        for a, n in semanas_por_anio.items():
            for k in range(n):
                d[date(a, 1, 1) + timedelta(days=7 * k)] = (a, 1.0)
        return d

    completo = pais({a: 46 for a in mp.ANIOS_ANUALES})
    corto = pais({**{a: 46 for a in mp.ANIOS_ANUALES}, 2019: 44})
    assert mp.paises_completos({"ZETA": completo, "ALFA": completo, "CORTO": corto}) == ["ALFA", "ZETA"]


def test_totales_anuales():
    semanas = {date(2014, 1, 5): (2014, 2.0), date(2014, 1, 12): (2014, 3.0), date(2015, 1, 4): (2015, 7.0)}
    t = mp.totales_anuales(semanas)
    assert t[0] == 5.0 and t[1] == 7.0 and t[2] == 0.0 and len(t) == 11


# ----------------------------------------------------------------- clima

def test_clima_semanal_suma_media_y_minimo_de_5_dias():
    f0 = date(2020, 1, 5)
    dias = [(f0 + timedelta(days=k)).isoformat() for k in range(7)]
    diario = {
        "precipitation_sum": {d: 2.0 for d in dias},
        "temp_media": {d: 20.0 + k for k, d in enumerate(dias)},
        "temp_max": {d: 30.0 for d in dias[:4]},
    }
    c = mp.clima_semanal(diario, [f0])
    assert c["precipitation_sum"][0] == 14.0
    assert c["temp_media"][0] == pytest.approx(23.0)
    assert np.isnan(c["temp_max"][0])
    assert np.isnan(c["punto_rocio"][0])


def _cache(tmp_path, paises, lat_desplazada=0.0, horas_con_suma_nula=False):
    def resp(pais, con_lluvia):
        lat, lon = mp.CENTROIDES[pais]
        tiempos = ["2020-01-01", "2020-01-02"]
        daily = {"time": tiempos}
        if con_lluvia:
            daily["precipitation_sum"] = [None, 3.0] if horas_con_suma_nula else [1.0, 3.0]
            daily["precipitation_hours"] = [0.0, 5.0]
        else:
            daily["temperature_2m_mean"] = [20.0, 21.0]
        return {"latitude": lat + lat_desplazada, "longitude": lon, "daily": daily}

    bruto = {"era5_land": [resp(p, False) for p in paises], "era5": [resp(p, True) for p in paises]}
    ruta = tmp_path / "clima.json"
    ruta.write_text(json.dumps(bruto), encoding="utf-8")
    return ruta


def test_cargar_clima_mapea_nombres_y_aplica_la_guarda_de_horas(tmp_path):
    paises = ["EL SALVADOR", "GUATEMALA"]
    d = mp.cargar_clima(_cache(tmp_path, paises, horas_con_suma_nula=True), paises)
    assert d["EL SALVADOR"]["temp_media"]["2020-01-02"] == 21.0
    assert "2020-01-01" not in d["EL SALVADOR"]["precipitation_hours"]
    assert d["GUATEMALA"]["precipitation_hours"]["2020-01-02"] == 5.0


def test_cargar_clima_rechaza_ubicaciones_que_no_coinciden(tmp_path):
    paises = ["EL SALVADOR", "GUATEMALA"]
    with pytest.raises(ValueError):
        mp.cargar_clima(_cache(tmp_path, paises, lat_desplazada=3.0), paises)
    with pytest.raises(ValueError):
        mp.cargar_clima(_cache(tmp_path, paises), paises[:1])


def test_oni_arrastra_hacia_adelante_y_es_nan_antes_del_inicio():
    fechas_oni = [date(2020, 1, 5), date(2020, 2, 2)]
    o = mp.oni_en_fechas(fechas_oni, [0.5, 1.5], [date(2019, 12, 29), date(2020, 1, 12), date(2020, 3, 1)])
    assert np.isnan(o[0]) and o[1] == 0.5 and o[2] == 1.5


# ------------------------------------------------------------ senal regional

def _matriz_totales(rng, n_paises=6, correlacion_negativa=True):
    comun = rng.normal(size=11)
    filas = [comun + 0.2 * rng.normal(size=11) for _ in range(n_paises - 1)]
    filas.append(-comun + 0.2 * rng.normal(size=11) if correlacion_negativa else rng.normal(size=11))
    return np.exp(np.array(filas)) * 100


def test_senal_regional_el_pais_opuesto_tiene_la_menor_correlacion():
    t = _matriz_totales(np.random.default_rng(0))
    s = mp.senal_regional(t)
    assert np.argmin(s["r_con_senal"]) == 5
    assert s["r_con_otros"][5] < 0 < s["r_con_otros"][0]
    assert s["matriz"].shape == (6, 6) and np.allclose(np.diag(s["matriz"]), 1.0)
    assert 0 < s["primer_componente"] <= 1


def test_senal_regional_formula_contra_calculo_directo():
    t = _matriz_totales(np.random.default_rng(1))
    L = np.log1p(t)
    Z = (L - L.mean(1, keepdims=True)) / L.std(1, keepdims=True)
    senal = Z.mean(0)
    s = mp.senal_regional(t)
    assert s["r_con_senal"][2] == pytest.approx(np.corrcoef(Z[2], senal)[0, 1])
    assert s["r_con_otros"][2] == pytest.approx(np.corrcoef(Z[2], np.delete(Z, 2, 0).mean(0))[0, 1])
    iu = np.triu_indices(6, 1)
    assert s["correlacion_media_pares"] == pytest.approx(np.corrcoef(Z)[iu].mean())


def test_primer_componente_es_1_si_todos_los_paises_son_iguales():
    fila = np.exp(np.random.default_rng(2).normal(size=11)) * 100
    s = mp.senal_regional(np.vstack([fila, fila * 2, fila * 3]))
    assert s["primer_componente"] > 0.95


def test_intervalo_de_la_senal_contiene_la_correlacion():
    t = _matriz_totales(np.random.default_rng(3))
    s = mp.senal_regional(t)
    ic = mp.ic_senal(s["Z"], s["senal"], remuestreos=300)
    for i in range(6):
        assert ic[i][0] is None or ic[i][0] - 0.2 <= s["r_con_senal"][i] <= ic[i][1] + 0.2
    assert mp.ic_senal(s["Z"], s["senal"], 100) == mp.ic_senal(s["Z"], s["senal"], 100)


def test_estabilidad_incluye_cada_anio_y_cada_otro_pais():
    t = _matriz_totales(np.random.default_rng(4))
    paises = ["EL SALVADOR", "P1", "P2", "P3", "P4", "P5"]
    e = mp.estabilidad(t, paises)
    assert sorted(e["sin_cada_anio"]) == [str(a) for a in mp.ANIOS_ANUALES]
    assert sorted(e["sin_cada_pais"]) == ["P1", "P2", "P3", "P4", "P5"]
    todos = list(e["sin_cada_anio"].values()) + list(e["sin_cada_pais"].values())
    assert e["minimo"] == min(todos) and e["maximo"] == max(todos)


def test_centroamerica_usa_solo_los_paises_presentes():
    t = _matriz_totales(np.random.default_rng(5), 4)
    r = mp.centroamerica(t, ["EL SALVADOR", "GUATEMALA", "HONDURAS", "BRAZIL"])
    assert sorted(r) == ["EL SALVADOR", "GUATEMALA", "HONDURAS"]


def test_sensibilidad_sin_paises_recalcula_la_senal():
    t = _matriz_totales(np.random.default_rng(6))
    paises = ["EL SALVADOR", "P1", "P2", "P3", "P4", "P5"]
    r = mp.sensibilidad_sin_paises(t, paises, ["P5"])
    assert r["excluidos"] == ["P5"] and "P5" not in r["r_con_senal"] and len(r["r_con_senal"]) == 5
    directo = mp.senal_regional(t[:5])
    assert r["r_con_senal"]["EL SALVADOR"] == pytest.approx(directo["r_con_senal"][0], abs=1e-4)
    assert r["posicion"]["EL SALVADOR"] in range(1, 6)


def test_posiciones_de_menor_a_mayor_ignoran_none_y_nan():
    pos = mp.posiciones_de_menor_a_mayor({"a": 0.5, "b": None, "c": -0.2, "d": float("nan")})
    assert pos == {"c": 1, "a": 2}


def _p2_falso(**cambios):
    por_pais = {p: {"r_con_senal": v} for p, v in
                {"EL SALVADOR": 0.28, "COLOMBIA": 0.952, "GUATEMALA": 0.908, "HONDURAS": 0.868}.items()}
    r = {"correlacion_media_pares": 0.453, "primer_componente": 0.518, "correlacion_senal_oni": 0.52,
         "por_pais": por_pais, "posicion_r_con_senal": {"EL SALVADOR": 1}}
    r.update(cambios)
    return r


def test_verificar_acepta_la_replicacion_y_se_detiene_si_no_coincide():
    mp.verificar(_p2_falso())
    with pytest.raises(SystemExit):
        mp.verificar(_p2_falso(correlacion_media_pares=0.46))
    with pytest.raises(SystemExit):
        mp.verificar(_p2_falso(posicion_r_con_senal={"EL SALVADOR": 2}))
    malo = _p2_falso()
    malo["por_pais"]["COLOMBIA"]["r_con_senal"] = 0.9
    with pytest.raises(SystemExit):
        mp.verificar(malo)


# ----------------------------------------------------------------------- P3

def test_asociacion_por_pais_recupera_el_signo_plantado():
    p = _pais(beta=4.0, semilla=5)
    a = mp.asociaciones_pais(p, 0, remuestreos=150)
    assert a["estimacion"] and len(a["anios_evaluables"]) >= 8
    f = a["por_variable"]["temp_media"]
    assert f["agrupado"]["r"] > 0.2
    assert f["anios_positivos"] >= 7
    assert "oni" in a["por_variable"] and "punto_rocio" in a["por_variable"]


def test_sin_efecto_ninguna_variable_es_consistente():
    a = mp.asociaciones_pais(_pais(beta=0.0, semilla=6), 0, remuestreos=150)
    assert not any(f["consistente"] for f in a["por_variable"].values())


def test_pais_con_pocos_casos_no_tiene_estimacion():
    p = _pais(nivel=1.0, semilla=7)
    a = mp.asociaciones_pais(p, 0, remuestreos=50)
    assert not a["estimacion"]
    assert "por_variable" not in a


def test_anio_con_menos_de_100_casos_no_es_evaluable():
    p = _pais(beta=2.0, semilla=8)
    p.casos[p.anio == 2019] = 0.0
    a = mp.asociaciones_pais(p, 0, remuestreos=50)
    assert 2019 not in a["anios_evaluables"]


def test_pais_sin_clima_de_superficie_solo_tiene_lluvia_y_oni():
    p = _pais(beta=2.0, semilla=9, solo_lluvia=True)
    assert mp.variables_disponibles(p) == ["precipitation_sum", "precipitation_hours"]
    a = mp.asociaciones_pais(p, 0, remuestreos=50)
    assert sorted(a["por_variable"]) == ["oni", "precipitation_hours", "precipitation_sum"]


def test_etiqueta_de_consistencia_con_menos_de_9_anios():
    ic = [0.05, 0.3]
    assert mp.etiqueta_consistencia([0.3] * 5 + [-0.1], ic, 6)["consistente"]
    assert not mp.etiqueta_consistencia([0.3] * 4 + [-0.1] * 2, ic, 6)["consistente"]
    assert not mp.etiqueta_consistencia([0.3] * 6, [-0.05, 0.3], 6)["consistente"]
    assert not mp.etiqueta_consistencia([0.3] * 6, [None, None], 6)["consistente"]


def test_2024_no_entra_en_las_asociaciones():
    p = _pais(beta=3.0, semilla=10)
    antes = mp.asociaciones_pais(p, 0, remuestreos=50)
    m = p.anio == 2024
    p.casos[m] = 99999.0
    for v in p.clima:
        p.clima[v][m] = 1e6
    p.oni[m] = 50.0
    assert mp.asociaciones_pais(p, 0, remuestreos=50) == antes


def test_2020_solo_entra_como_rezago_del_inicio_de_2021():
    p = _pais(beta=3.0, semilla=10)
    antes = mp.asociaciones_pais(p, 0, remuestreos=50)["por_variable"]["temp_media"]["por_anio"]
    m = p.anio == 2020
    p.casos[m] = 99999.0
    despues = mp.asociaciones_pais(p, 0, remuestreos=50)["por_variable"]["temp_media"]["por_anio"]
    assert antes["2021"] != despues["2021"]
    assert abs(antes["2019"]["r"] - despues["2019"]["r"]) < 0.05


# ----------------------------------------------------------------------- P4

def test_ciclo_medio_encuentra_el_desfase_entre_lluvia_y_casos():
    p = _pais(semilla=11)
    ang = 2 * np.pi * (p.sem - 1) / 52.0
    desfase = 6
    for v in base.VARIABLES_CLIMA:
        p.clima[v] = 20 + 3 * np.sin(ang)
    p.casos[:] = np.round(np.exp(5 + 0.8 * np.sin(2 * np.pi * (p.sem - 1 - desfase) / 52.0)))
    c = mp.ciclo_medio(p, mp.serie_z(p.casos))
    f = c["variables"]["precipitation_sum"]
    assert desfase <= f["desfase_mejor_semanas"] <= desfase + 3
    assert f["r2_estacional"] == pytest.approx(1.0, abs=1e-6)
    assert len(f["climatologia"]) == 52 and len(c["casos"]["climatologia"]) == 52
    assert not f["en_el_borde"]


# --------------------------------------------------------------------- perfil

def test_perfil_cuenta_semanas_ceros_y_marcas():
    p = _pais("BRAZIL", semilla=12, nivel=2.0)
    totales = np.array([np.nansum(p.casos[p.anio == a]) for a in mp.ANIOS_ANUALES])
    f = mp.perfil(p, totales, mp.serie_z(p.casos))
    assert f["pais_extenso"] and f["baja_incidencia"]
    assert f["semanas_por_anio"]["2014"] == int((p.anio == 2014).sum())
    assert 0 <= f["fraccion_semanas_cero"] <= 1
    assert f["total_anual"]["2019"] == pytest.approx(totales[5])
    assert 1 <= f["semana_del_maximo"] <= 52


# --------------------------------------------------------------------- P5/P6

def _corrida(supera, n_alto=10):
    return {"semilla": 0, "supera": supera,
            "modelo": {"f1_macro": 0.3, "recall_alto": 0.1, "n_alto_real": n_alto},
            "climatologica": {"f1_macro": 0.2, "recall_alto": 0.0, "n_alto_real": n_alto}}


def test_corridas_anteriores_resume_por_anio(tmp_path):
    for _clave, (_d, archivo) in mp.CORRIDAS_ANTERIORES.items():
        if archivo == "resultados_regional.json":
            continue
        (tmp_path / archivo).write_text(json.dumps({"2019": [_corrida(True), _corrida(False), _corrida(True)],
                                                    "2020": [_corrida(False)]}), encoding="utf-8")
    r = mp.corridas_anteriores(tmp_path)
    assert not r["B"]["disponible"]
    a = r["A"]
    assert a["anios"]["2019"]["semillas_que_superan"] == 2 and a["anios"]["2019"]["semillas"] == 3
    assert a["anios"]["2019"]["soporte_alto"] == 10
    assert a["anios_con_mayoria_que_supera"] == 1 and a["anios_total"] == 2


def test_posicion_de_el_salvador():
    r = {
        "P2": {"por_pais": {"EL SALVADOR": {"r_con_senal": 0.28, "r_con_otros": 0.2}, "X": {"r_con_senal": 0.5, "r_con_otros": 0.4}}},
        "P1": {"EL SALVADOR": {"desviacion_log_total_anual": 1.0, "r2_estacional": 0.2},
               "X": {"desviacion_log_total_anual": 0.5, "r2_estacional": 0.6}},
        "P3": {"EL SALVADOR": {"estimacion": True, "por_variable": {"precipitation_sum": {"agrupado": {"r": -0.17}}, "oni": {"agrupado": {"r": 0.0}}}},
               "X": {"estimacion": False}},
    }
    pos = mp.posicion_el_salvador(r)
    assert pos["r_con_senal"] == {"posicion_de_menor_a_mayor": 1, "paises": 2, "valor": 0.28}
    assert pos["desviacion_log_total_anual"]["posicion_de_menor_a_mayor"] == 2
    assert pos["r_agrupado_precipitation_sum"]["paises"] == 1


# ------------------------------------------------------------- de punta a punta

def test_calcular_de_punta_a_punta_con_datos_sinteticos(tmp_path):
    paises = ["EL SALVADOR", "GUATEMALA", "HONDURAS", "NICARAGUA"]
    casos, diario = {}, {}
    for k, nombre in enumerate(paises):
        p = _pais(nombre, beta=2.0, semilla=20 + k)
        casos[nombre] = {f: (int(a), float(c)) for f, a, c in zip(p.fecha, p.anio, p.casos)}
        diario[nombre] = {}
        for v in base.VARIABLES_CLIMA:
            serie = {}
            for i, f in enumerate(p.fecha):
                for d in range(7):
                    serie[(f + timedelta(days=d)).isoformat()] = float(p.clima[v][i]) / (7 if v in mp.ACUMULATIVAS else 1)
            diario[nombre][v] = serie
    p0 = _pais(semilla=30)
    oni = ([f for f in p0.fecha], [float(x) for x in p0.oni], {a: float(np.mean(p0.oni[p0.anio == a])) for a in mp.ANIOS_ANUALES})
    r = mp.calcular(casos, paises, diario, oni, tmp_path, a3={"A3": {"agrupado": {}}, "A5": {}}, remuestreos=40)
    assert set(r) == {"P1", "P2", "P3", "P4", "P5", "P6", "referencia_el_salvador_base_de_datos"}
    assert sorted(r["P1"]) == sorted(paises)
    assert r["P2"]["posicion_r_con_senal"]["EL SALVADOR"] in (1, 2, 3, 4)
    assert r["P3"]["EL SALVADOR"]["estimacion"]
    assert sorted(r["P2"]["centroamerica_9_anios"]) == ["EL SALVADOR", "GUATEMALA", "HONDURAS", "NICARAGUA"]
    assert "excluidos" in r["P2"]["sin_baja_incidencia"]
    assert len(r["P4"]["GUATEMALA"]["variables"]["temp_media"]["climatologia"]) == 52
    json.dumps(base.limpio(r), allow_nan=False)
