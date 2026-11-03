"""Pruebas de independencia y formulas de la Via 3.

``VIA_TRES_MUTACION_FUGA=1`` introduce la semana objetivo en sus propios
predictores solo dentro de la prueba correspondiente. Sirve para demostrar
que la guarda falla ante una contaminacion deliberada sin alterar el runner.
"""

from __future__ import annotations

import copy
import math
import os
import sys
import unittest
from pathlib import Path


INGESTION = Path(__file__).resolve().parent.parent
RAIZ_REPO = INGESTION.parent.parent
SEED = Path(
    os.environ.get(
        "VIA_TRES_SEED_SQL",
        RAIZ_REPO / "db" / "seed" / "seed_datos_reales.sql",
    )
)
sys.path.insert(0, str(INGESTION))

import validar_via_menos_uno as base  # noqa: E402
import validar_via_tres as via  # noqa: E402


MUTACION_FUGA = os.environ.get("VIA_TRES_MUTACION_FUGA") == "1"


def _snapshot(filas, manifiesto):
    columnas = via.columnas_predictores(manifiesto)
    return tuple(
        (
            fila["anio"],
            fila["semana"],
            fila["etiqueta"],
            tuple(fila[columna] for columna in columnas),
        )
        for fila in filas
    )


def _dataset(datos, manifiesto, anios=None, *, contaminar=False):
    etiquetas = base.construir_etiquetas(datos, manifiesto, anios)
    return via.construir_dataset(
        datos,
        etiquetas,
        manifiesto,
        incluir_semana_objetivo=contaminar,
    )[0]


class ViaTresTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifiesto = via.cargar_manifesto()
        cls.datos = base.cargar_datos(SEED, cls.manifiesto)
        (
            cls.etiquetas,
            cls.dataset,
            cls.descartes,
            cls.firma,
        ) = via.preparar(cls.datos, cls.manifiesto)

    def test_fuente_y_firma_previa_coinciden_con_manifiesto(self):
        self.assertEqual(
            base.sha256(SEED), self.manifiesto["fuente"]["seed_sha256"]
        )
        self.assertEqual(
            via.validar_firma_previa(self.firma, self.manifiesto),
            "1d95d43f21a4a3826598c98e8db310552b579608d3f82d04de482cf7b904d253",
        )

    def test_reemplaza_21_rezagos_por_siete_features(self):
        columnas = via.columnas_predictores(self.manifiesto)
        self.assertEqual(len(columnas), 7)
        self.assertEqual(columnas, self.manifiesto["predictores"]["columnas"])
        self.assertFalse(any("_lag" in columna for columna in columnas))
        self.assertFalse(any("media_movil" in columna for columna in columnas))

    def test_firma_de_folds_conserva_la_via_menos_uno(self):
        clases = self.manifiesto["evaluacion"]["clases"]
        for anio_externo in self.manifiesto["folds_externos"]:
            train, test = base.construir_fold(
                self.dataset, anio_externo, self.manifiesto
            )
            estado, _marcas = base.estado_fold(train, test, clases)
            base.validar_firma_fold(
                anio_externo, train, test, estado, self.manifiesto
            )

    def test_semana_objetivo_no_entra_en_sus_features(self):
        clave = (2022, 20)
        datos_alterados = copy.deepcopy(self.datos)
        for variable in datos_alterados.clima[clave]:
            datos_alterados.clima[clave][variable] += 1_000_000
        etiquetas = {clave: self.etiquetas[clave]}
        original = via.construir_dataset(
            self.datos,
            etiquetas,
            self.manifiesto,
            incluir_semana_objetivo=MUTACION_FUGA,
        )[0]
        alterado = via.construir_dataset(
            datos_alterados,
            etiquetas,
            self.manifiesto,
            incluir_semana_objetivo=MUTACION_FUGA,
        )[0]
        self.assertEqual(
            _snapshot(original, self.manifiesto),
            _snapshot(alterado, self.manifiesto),
        )

    def test_clima_previo_si_modifica_features(self):
        clave = (2022, 20)
        anterior = base.claves_anteriores(self.datos, clave, 1)[0]
        datos_alterados = copy.deepcopy(self.datos)
        datos_alterados.clima[anterior]["temp_media"] += 3.0
        original = via.construir_dataset(
            self.datos, {clave: self.etiquetas[clave]}, self.manifiesto
        )[0]
        alterado = via.construir_dataset(
            datos_alterados, {clave: self.etiquetas[clave]}, self.manifiesto
        )[0]
        self.assertNotEqual(
            _snapshot(original, self.manifiesto),
            _snapshot(alterado, self.manifiesto),
        )

    def test_casos_del_externo_no_modifican_entrenamiento(self):
        anio_externo = 2022
        datos_alterados = copy.deepcopy(self.datos)
        for semana in datos_alterados.serie[anio_externo]:
            datos_alterados.serie[anio_externo][semana] += 1_000_000
        original = _dataset(
            self.datos, self.manifiesto, [2018, 2019, 2021, 2022]
        )
        alterado = _dataset(
            datos_alterados, self.manifiesto, [2018, 2019, 2021, 2022]
        )
        train_original = base.construir_fold(
            original, anio_externo, self.manifiesto
        )[0]
        train_alterado = base.construir_fold(
            alterado, anio_externo, self.manifiesto
        )[0]
        self.assertEqual(
            _snapshot(train_original, self.manifiesto),
            _snapshot(train_alterado, self.manifiesto),
        )

    def test_datos_posteriores_no_modifican_fold(self):
        anio_externo = 2022
        datos_alterados = copy.deepcopy(self.datos)
        for anio in (2023, 2024):
            for semana in datos_alterados.serie[anio]:
                datos_alterados.serie[anio][semana] += 1_000_000
        for clave, variables in datos_alterados.clima.items():
            if clave[0] > anio_externo:
                for variable in variables:
                    variables[variable] -= 1_000_000
        original = _dataset(self.datos, self.manifiesto)
        alterado = _dataset(datos_alterados, self.manifiesto)
        fold_original = base.construir_fold(
            original, anio_externo, self.manifiesto
        )
        fold_alterado = base.construir_fold(
            alterado, anio_externo, self.manifiesto
        )
        self.assertEqual(
            _snapshot(fold_original[0], self.manifiesto),
            _snapshot(fold_alterado[0], self.manifiesto),
        )
        self.assertEqual(
            _snapshot(fold_original[1], self.manifiesto),
            _snapshot(fold_alterado[1], self.manifiesto),
        )

    def test_faltante_previo_excluye_fila_sin_imputar(self):
        clave = (2022, 20)
        datos_alterados = copy.deepcopy(self.datos)
        anterior = base.claves_anteriores(datos_alterados, clave, 4)[3]
        del datos_alterados.clima[anterior]["precipitation_hours"]
        dataset, descartes = via.construir_dataset(
            datos_alterados, {clave: self.etiquetas[clave]}, self.manifiesto
        )
        self.assertEqual(dataset, [])
        self.assertEqual(descartes[clave], "sin_historia_climatica")

    def test_grados_dia_respetan_umbral_y_tope(self):
        clave = (2022, 20)
        anteriores = base.claves_anteriores(self.datos, clave, 8)
        features = via.calcular_features(self.datos, anteriores)
        esperado = sum(
            7.0
            * max(min(self.datos.clima[anterior]["temp_media"], 35.0) - 16.0, 0.0)
            for anterior in anteriores[:4]
        )
        self.assertAlmostEqual(features["grados_dia_desarrollo_4s"], esperado)

    def test_pulso_seco_humedo_usa_lag1_contra_lags_2_a_4(self):
        clave = (2022, 20)
        anteriores = base.claves_anteriores(self.datos, clave, 8)
        lluvia = [
            self.datos.clima[anterior]["precipitation_sum"]
            for anterior in anteriores[:4]
        ]
        esperado = max(lluvia[0] - sum(lluvia[1:]) / 3.0, 0.0)
        features = via.calcular_features(self.datos, anteriores)
        self.assertAlmostEqual(features["pulso_seco_humedo_1s"], esperado)

    def test_racha_termica_es_constante_y_se_reporta_sin_ocultarla(self):
        resumen = self.firma["features"]["racha_termica_transmision_8s"]
        self.assertEqual(resumen["min"], 8.0)
        self.assertEqual(resumen["max"], 8.0)
        self.assertEqual(resumen["valores_unicos"], 1)

    def test_todas_las_features_son_finitas(self):
        for fila in self.dataset:
            for columna in via.columnas_predictores(self.manifiesto):
                self.assertTrue(math.isfinite(float(fila[columna])))

    def test_no_se_inventa_conteo_de_dias_lluviosos(self):
        no_disponible = self.manifiesto["predictores"]["no_disponible"]
        self.assertIn("dias_con_lluvia_sobre_umbral", no_disponible)
        self.assertFalse(
            any(
                "dias_lluvia" in columna
                for columna in via.columnas_predictores(self.manifiesto)
            )
        )

    def test_configuracion_y_semillas_estan_fijas(self):
        self.assertEqual(
            via.configuracion_modelo(self.manifiesto),
            {"n_estimators": 300, "class_weight": "balanced", "n_jobs": -1},
        )
        self.assertEqual(
            self.manifiesto["modelo"]["semillas_estabilidad"], list(range(10))
        )
        self.assertEqual(self.manifiesto["modelo"]["decision"], "predict_argmax")
        self.assertEqual(
            self.manifiesto["modelo"]["seleccion_interna"],
            "ninguna_configuracion_unica_congelada",
        )

    def test_las_cuatro_referencias_siguen_obligatorias(self):
        self.assertEqual(
            self.manifiesto["evaluacion"]["referencias"],
            [
                "climatologica",
                "constante_mayoritaria",
                "siempre_alto",
                "persistencia",
            ],
        )
        train, test = base.construir_fold(self.dataset, 2022, self.manifiesto)
        observadas = base.referencias(train, test, self.datos, self.manifiesto)
        self.assertEqual(list(observadas), self.manifiesto["evaluacion"]["referencias"])

    def test_solo_2022_es_evaluable_y_no_tiene_alto_en_train(self):
        evaluables = []
        for anio in self.manifiesto["folds_externos"]:
            firma = self.firma["folds"][str(anio)]
            if firma["distribucion_test"]["alto"]:
                evaluables.append(anio)
                self.assertEqual(firma["distribucion_train"]["alto"], 0)
        self.assertEqual(evaluables, [2022])


if __name__ == "__main__":
    unittest.main()
