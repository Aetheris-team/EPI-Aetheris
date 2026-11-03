"""Validacion forward-chaining de la Via 3 con features mecanisticas.

La Via 3 conserva la fuente, la etiqueta, los folds, el modelo y el criterio
aprobados para la Via -1. Solo reemplaza los 21 rezagos climaticos crudos por
siete transformaciones predeclaradas con interpretacion biologica.

El modo ``--solo-preparar`` calcula la firma del dataset y de los folds sin
ajustar ningun modelo. La ejecucion completa se rechaza si esa firma no fue
congelada previamente en ``via_tres_manifesto_congelado.json``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier

import validar_via_menos_uno as base


RAIZ_INGESTION = Path(__file__).resolve().parent
RAIZ_REPO = RAIZ_INGESTION.parent.parent
MANIFESTO_CONGELADO = RAIZ_INGESTION / "via_tres_manifesto_congelado.json"
SEED_DEFAULT = RAIZ_REPO / "db" / "seed" / "seed_datos_reales.sql"
SALIDA_DEFAULT = RAIZ_INGESTION / "data" / "interim" / "via_tres"

Clave = base.Clave
DatosFuente = base.DatosFuente
ResultadoEtiqueta = base.ResultadoEtiqueta
ErrorProtocolo = base.ErrorProtocolo


def cargar_manifesto() -> dict[str, Any]:
    manifiesto = json.loads(MANIFESTO_CONGELADO.read_text(encoding="utf-8"))
    if manifiesto.get("version_manifesto") != 1 or manifiesto.get("via") != 3:
        raise ErrorProtocolo("Version o via de manifiesto no soportada")
    if manifiesto["predictores"]["estrategia"] != (
        "reemplazar_rezagos_crudos_por_siete_features_mecanisticas"
    ):
        raise ErrorProtocolo("La estrategia de predictores no es la congelada")
    return manifiesto


def columnas_predictores(manifiesto: dict[str, Any]) -> list[str]:
    columnas = [str(valor) for valor in manifiesto["predictores"]["columnas"]]
    if len(columnas) != 7 or len(set(columnas)) != len(columnas):
        raise ErrorProtocolo("La Via 3 requiere exactamente siete features unicas")
    return columnas


def _racha_termica(
    datos: DatosFuente,
    anteriores: Sequence[Clave],
    inferior: float = 17.8,
    superior: float = 34.6,
) -> float:
    racha = 0
    for clave in anteriores:
        temperatura = datos.clima[clave]["temp_media"]
        if inferior <= temperatura <= superior:
            racha += 1
        else:
            break
    return float(racha)


def _exceso_termico_humedo(temperatura: float, humedad: float) -> float:
    if temperatura > 34.6:
        return 0.0
    exceso = max(min(temperatura, 34.6) - 17.8, 0.0)
    return float(exceso * humedad / 100.0)


def calcular_features(
    datos: DatosFuente,
    anteriores: Sequence[Clave],
) -> dict[str, float]:
    if len(anteriores) < 8:
        raise ValueError("Se requieren ocho semanas anteriores consecutivas")
    cuatro = anteriores[:4]
    temperaturas = [datos.clima[clave]["temp_media"] for clave in cuatro]
    humedades = [datos.clima[clave]["humedad_relativa_media"] for clave in cuatro]
    precipitaciones = [datos.clima[clave]["precipitation_sum"] for clave in cuatro]

    return {
        "racha_termica_transmision_8s": _racha_termica(datos, anteriores[:8]),
        "grados_dia_desarrollo_4s": float(
            base.suma_ingenua(7.0 * max(min(temperatura, 35.0) - 16.0, 0.0) for temperatura in temperaturas)
        ),
        "semanas_optimas_temp_humedad_4s": float(
            base.suma_ingenua(
                27.0 <= temperatura <= 29.5 and humedad > 75.0
                for temperatura, humedad in zip(temperaturas, humedades)
            )
        ),
        "interaccion_termohigrometrica_4s": float(
            base.suma_ingenua(
                _exceso_termico_humedo(temperatura, humedad)
                for temperatura, humedad in zip(temperaturas, humedades)
            )
            / 4.0
        ),
        "amplitud_termica_media_4s": float(
            base.suma_ingenua(
                datos.clima[clave]["temp_max"] - datos.clima[clave]["temp_min"]
                for clave in cuatro
            )
            / 4.0
        ),
        "duracion_lluvia_4s": float(
            base.suma_ingenua(datos.clima[clave]["precipitation_hours"] for clave in cuatro)
        ),
        "pulso_seco_humedo_1s": float(
            max(precipitaciones[0] - base.suma_ingenua(precipitaciones[1:4]) / 3.0, 0.0)
        ),
    }


def construir_dataset(
    datos: DatosFuente,
    etiquetas: dict[Clave, ResultadoEtiqueta],
    manifiesto: dict[str, Any],
    *,
    incluir_semana_objetivo: bool = False,
) -> tuple[list[dict[str, Any]], dict[Clave, str]]:
    filas: list[dict[str, Any]] = []
    descartes: dict[Clave, str] = {}
    variables = tuple(manifiesto["predictores"]["variables"])
    historia_maxima = int(manifiesto["predictores"]["historia_maxima_semanas"])
    if historia_maxima != 8:
        raise ErrorProtocolo("La historia maxima congelada debe ser ocho semanas")

    for clave, resultado in sorted(etiquetas.items()):
        if resultado.etiqueta is None:
            descartes[clave] = resultado.motivo or "sin_etiqueta"
            continue
        anteriores = base.claves_anteriores(datos, clave, historia_maxima)
        if anteriores is None:
            descartes[clave] = "sin_historia_climatica"
            continue
        if incluir_semana_objetivo:
            anteriores = (clave, *anteriores[:-1])
        if any(
            variable not in datos.clima.get(clave_anterior, {})
            for clave_anterior in anteriores
            for variable in variables
        ):
            descartes[clave] = "sin_historia_climatica"
            continue

        features = calcular_features(datos, anteriores)
        if list(features) != columnas_predictores(manifiesto):
            raise ErrorProtocolo("El orden de features difiere del manifiesto")
        filas.append(
            {
                "anio": resultado.anio,
                "semana": resultado.semana,
                "casos": resultado.casos,
                "etiqueta": resultado.etiqueta,
                "historia": resultado.historia,
                "n_observaciones": resultado.n_observaciones,
                "n_anios": resultado.n_anios,
                "corte_inferior": resultado.corte_inferior,
                "corte_superior": resultado.corte_superior,
                **features,
            }
        )
    return filas, descartes


def _resumen_feature(valores: Sequence[float]) -> dict[str, float | int]:
    return {
        "min": float(min(valores)),
        "max": float(max(valores)),
        "media": float(base.suma_ingenua(valores) / len(valores)),
        "valores_unicos": len(set(valores)),
    }


def construir_firma_previa(
    dataset: Sequence[dict[str, Any]],
    descartes: dict[Clave, str],
    manifiesto: dict[str, Any],
) -> dict[str, Any]:
    clases = manifiesto["evaluacion"]["clases"]
    columnas = columnas_predictores(manifiesto)
    folds: dict[str, Any] = {}
    for anio_externo in manifiesto["folds_externos"]:
        train, test = base.construir_fold(dataset, int(anio_externo), manifiesto)
        estado, marcas = base.estado_fold(train, test, clases)
        base.validar_firma_fold(int(anio_externo), train, test, estado, manifiesto)
        folds[str(anio_externo)] = {
            "estado": estado,
            "marcas": marcas,
            "n_train": len(train),
            "n_test": len(test),
            "distribucion_train": base.distribucion(
                (fila["etiqueta"] for fila in train), clases
            ),
            "distribucion_test": base.distribucion(
                (fila["etiqueta"] for fila in test), clases
            ),
        }
    return {
        "filas": len(dataset),
        "columnas": columnas,
        "features": {
            columna: _resumen_feature([float(fila[columna]) for fila in dataset])
            for columna in columnas
        },
        "descartes": {
            motivo: sum(valor == motivo for valor in descartes.values())
            for motivo in sorted(set(descartes.values()))
        },
        "folds": folds,
    }


def hash_firma_previa(firma: dict[str, Any]) -> str:
    contenido = json.dumps(
        firma, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(contenido).hexdigest()


def validar_firma_previa(firma: dict[str, Any], manifiesto: dict[str, Any]) -> str:
    observado = hash_firma_previa(firma)
    esperado = manifiesto["firma_previa_sha256"]
    if esperado == "POR_CONGELAR_ANTES_DEL_PRIMER_MODELO":
        raise ErrorProtocolo(
            "La firma previa todavia no esta congelada; ejecute --solo-preparar"
        )
    if observado != esperado:
        raise ErrorProtocolo(
            "La firma previa difiere del manifiesto: "
            f"esperada={esperado}, observada={observado}"
        )
    return observado


def configuracion_modelo(manifiesto: dict[str, Any]) -> dict[str, Any]:
    modelo = manifiesto["modelo"]
    return {
        "n_estimators": int(modelo["n_estimators"]),
        "class_weight": modelo["class_weight"],
        "n_jobs": int(modelo["n_jobs"]),
    }


def evaluar_fold(
    anio_externo: int,
    train: Sequence[dict[str, Any]],
    test: Sequence[dict[str, Any]],
    datos: DatosFuente,
    manifiesto: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    clases = manifiesto["evaluacion"]["clases"]
    columnas = columnas_predictores(manifiesto)
    estado, marcas = base.estado_fold(train, test, clases)
    base.validar_firma_fold(anio_externo, train, test, estado, manifiesto)

    y_real = [fila["etiqueta"] for fila in test]
    pred_referencias = base.referencias(train, test, datos, manifiesto)
    met_referencias = base.metricas_referencias(y_real, pred_referencias, clases)
    filas_prediccion: list[dict[str, Any]] = []
    resultado: dict[str, Any] = {
        "anio_externo": anio_externo,
        "estado": estado,
        "marcas": marcas,
        "anios_entrenamiento": sorted({fila["anio"] for fila in train}),
        "n_train": len(train),
        "n_test": len(test),
        "distribucion_train": base.distribucion(
            (fila["etiqueta"] for fila in train), clases
        ),
        "distribucion_test": base.distribucion(y_real, clases),
        "referencias": met_referencias,
        "semillas": {},
        "estabilidad": None,
    }

    semillas_estabilidad = [
        int(valor) for valor in manifiesto["modelo"]["semillas_estabilidad"]
    ]
    semilla_referencia = int(manifiesto["modelo"]["semilla_referencia"])
    semillas = [*semillas_estabilidad, semilla_referencia]
    if estado == "no_entrenable":
        for indice, fila in enumerate(test):
            filas_prediccion.append(
                {
                    "anio_externo": anio_externo,
                    "semilla": "",
                    "tipo_semilla": "sin_modelo",
                    "anio": fila["anio"],
                    "semana": fila["semana"],
                    "etiqueta_real": fila["etiqueta"],
                    "pred_modelo": "",
                    "p_bajo": "",
                    "p_medio": "",
                    "p_alto": "",
                    **{
                        f"pred_{nombre}": valores[indice] or ""
                        for nombre, valores in pred_referencias.items()
                    },
                }
            )
        return resultado, filas_prediccion

    X_train, y_train = base._matrices(train, columnas)
    X_test, _y_test = base._matrices(test, columnas)
    for semilla in semillas:
        modelo = RandomForestClassifier(
            random_state=semilla, **configuracion_modelo(manifiesto)
        )
        modelo.fit(X_train, y_train)
        pred_modelo = modelo.predict(X_test).tolist()
        probabilidades_crudas = modelo.predict_proba(X_test)
        indice_clase = {clase: indice for indice, clase in enumerate(modelo.classes_)}
        probabilidades = {
            clase: (
                probabilidades_crudas[:, indice_clase[clase]].astype(float).tolist()
                if clase in indice_clase
                else [0.0] * len(test)
            )
            for clase in clases
        }
        metricas = base.metricas_clasificacion(
            y_real, pred_modelo, clases, probabilidades["alto"]
        )
        criterio = base._criterio(metricas, met_referencias)
        resultado["semillas"][str(semilla)] = {
            "tipo": (
                "estabilidad"
                if semilla in semillas_estabilidad
                else "referencia_historica"
            ),
            "metricas": metricas,
            "criterio": criterio,
        }
        for indice, fila in enumerate(test):
            filas_prediccion.append(
                {
                    "anio_externo": anio_externo,
                    "semilla": semilla,
                    "tipo_semilla": (
                        "estabilidad"
                        if semilla in semillas_estabilidad
                        else "referencia_historica"
                    ),
                    "anio": fila["anio"],
                    "semana": fila["semana"],
                    "etiqueta_real": fila["etiqueta"],
                    "pred_modelo": pred_modelo[indice],
                    "p_bajo": probabilidades["bajo"][indice],
                    "p_medio": probabilidades["medio"][indice],
                    "p_alto": probabilidades["alto"][indice],
                    **{
                        f"pred_{nombre}": valores[indice] or ""
                        for nombre, valores in pred_referencias.items()
                    },
                }
            )
    estabilidad = base._resumen_estabilidad(
        {
            str(semilla): resultado["semillas"][str(semilla)]
            for semilla in semillas_estabilidad
        }
    )
    exitos = [
        resultado["semillas"][str(semilla)]["criterio"]["exito"]
        for semilla in semillas_estabilidad
    ]
    estabilidad["exito_estable"] = (
        None if any(valor is None for valor in exitos) else all(exitos)
    )
    resultado["estabilidad"] = estabilidad
    return resultado, filas_prediccion


def preparar(
    datos: DatosFuente, manifiesto: dict[str, Any]
) -> tuple[
    dict[Clave, ResultadoEtiqueta],
    list[dict[str, Any]],
    dict[Clave, str],
    dict[str, Any],
]:
    etiquetas = base.construir_etiquetas(datos, manifiesto)
    objetivos = set(int(anio) for anio in manifiesto["etiqueta"]["anios_objetivo"])
    etiquetas_objetivo = {
        clave: resultado
        for clave, resultado in etiquetas.items()
        if clave[0] in objetivos
    }
    dataset, descartes = construir_dataset(datos, etiquetas_objetivo, manifiesto)
    firma = construir_firma_previa(dataset, descartes, manifiesto)
    return etiquetas, dataset, descartes, firma


def ejecutar(
    datos: DatosFuente,
    manifiesto: dict[str, Any],
    dataset: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resultados: dict[str, Any] = {"folds": {}}
    predicciones: list[dict[str, Any]] = []
    for anio_externo in manifiesto["folds_externos"]:
        train, test = base.construir_fold(dataset, int(anio_externo), manifiesto)
        resultado, filas_prediccion = evaluar_fold(
            int(anio_externo), train, test, datos, manifiesto
        )
        resultados["folds"][str(anio_externo)] = resultado
        predicciones.extend(filas_prediccion)

    evaluables = [
        fold
        for fold in resultados["folds"].values()
        if fold["distribucion_test"]["alto"] > 0
    ]
    exitos_estables = sum(
        fold["estabilidad"] is not None
        and fold["estabilidad"]["exito_estable"] is True
        for fold in evaluables
    )
    resultados["conclusion"] = {
        "folds_evaluables_recall_alto": len(evaluables),
        "folds_con_exito_estable": int(exitos_estables),
        "adoptar": False,
        "recomendacion": "no_adoptar_via_tres",
        "motivo_estructural": (
            "el_unico_fold_con_alto_externo_no_contiene_alto_en_entrenamiento"
        ),
        "interpretacion": manifiesto["interpretacion"],
    }
    return resultados, predicciones


def _escribir_csv(
    ruta: Path, filas: Sequence[dict[str, Any]], columnas: Sequence[str]
) -> None:
    with ruta.open("w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        escritor.writeheader()
        escritor.writerows(filas)


def escribir_artefactos(
    salida: Path,
    seed_sql: Path,
    manifiesto: dict[str, Any],
    datos: DatosFuente,
    etiquetas: dict[Clave, ResultadoEtiqueta],
    dataset: Sequence[dict[str, Any]],
    descartes: dict[Clave, str],
    firma: dict[str, Any],
    resultados: dict[str, Any],
    predicciones: Sequence[dict[str, Any]],
) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    filas_etiquetas: list[dict[str, Any]] = []
    for resultado in etiquetas.values():
        fila = asdict(resultado)
        fila["historia"] = ",".join(str(anio) for anio in resultado.historia)
        fila["pool_claves"] = ",".join(
            f"{anio}-SE{semana:02d}" for anio, semana in resultado.pool_claves
        )
        filas_etiquetas.append(fila)
    _escribir_csv(
        salida / "etiquetas.csv",
        filas_etiquetas,
        [
            "anio",
            "semana",
            "casos",
            "historia",
            "n_observaciones",
            "n_anios",
            "corte_inferior",
            "corte_superior",
            "etiqueta",
            "motivo",
            "pool_claves",
        ],
    )

    columnas = columnas_predictores(manifiesto)
    filas_dataset: list[dict[str, Any]] = []
    for fila in dataset:
        serializada = dict(fila)
        serializada["historia"] = ",".join(str(anio) for anio in fila["historia"])
        filas_dataset.append(serializada)
    _escribir_csv(
        salida / "dataset.csv",
        filas_dataset,
        [
            "anio",
            "semana",
            "casos",
            "etiqueta",
            "historia",
            "n_observaciones",
            "n_anios",
            "corte_inferior",
            "corte_superior",
            *columnas,
        ],
    )
    _escribir_csv(
        salida / "predicciones.csv",
        predicciones,
        [
            "anio_externo",
            "semilla",
            "tipo_semilla",
            "anio",
            "semana",
            "etiqueta_real",
            "pred_modelo",
            "p_bajo",
            "p_medio",
            "p_alto",
            "pred_climatologica",
            "pred_constante_mayoritaria",
            "pred_siempre_alto",
            "pred_persistencia",
        ],
    )
    (salida / "metricas.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (salida / "firma_previa.json").write_text(
        json.dumps(firma, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifiesto_ejecucion = {
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "comando": " ".join(sys.argv),
        "manifiesto_congelado": manifiesto,
        "hashes": {
            "seed_sql_sha256": base.sha256(seed_sql),
            "script_sha256": base.sha256(Path(__file__).resolve()),
            "manifiesto_congelado_sha256": base.sha256(MANIFESTO_CONGELADO),
            "firma_previa_sha256": hash_firma_previa(firma),
        },
        "rutas": {
            "seed_sql": str(seed_sql.resolve()),
            "script": str(Path(__file__).resolve()),
            "salida": str(salida.resolve()),
        },
        "entorno": {
            "python": sys.version.split()[0],
            "plataforma": platform.platform(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "fuente_observada": datos.metadata,
        "dataset": {
            "filas": len(dataset),
            "predictores": len(columnas),
            "columnas_predictores": columnas,
            "descartes": {
                motivo: sum(valor == motivo for valor in descartes.values())
                for motivo in sorted(set(descartes.values()))
            },
        },
    }
    (salida / "manifiesto_ejecucion.json").write_text(
        json.dumps(manifiesto_ejecucion, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lineas_log = [
        "VIA 3 — FEATURES CON MECANISMO BIOLOGICO",
        f"generado_utc={manifiesto_ejecucion['generado_utc']}",
        f"seed_sha256={manifiesto_ejecucion['hashes']['seed_sql_sha256']}",
        f"firma_previa_sha256={manifiesto_ejecucion['hashes']['firma_previa_sha256']}",
        f"dataset={len(dataset)} filas, {len(columnas)} predictores",
    ]
    for anio in manifiesto["folds_externos"]:
        fold = resultados["folds"][str(anio)]
        estabilidad = fold["estabilidad"]
        resumen = (
            "sin modelo"
            if estabilidad is None
            else (
                f"F1 macro {estabilidad['f1_macro']['min']:.3f}.."
                f"{estabilidad['f1_macro']['max']:.3f}"
            )
        )
        lineas_log.append(
            f"fold={anio} estado={fold['estado']} train={fold['n_train']} "
            f"test={fold['n_test']} {resumen}"
        )
    lineas_log.extend(
        [
            "recomendacion=no_adoptar_via_tres",
            "interpretacion=validacion_forward_chaining_exploratoria",
        ]
    )
    (salida / "ejecucion.log").write_text(
        "\n".join(lineas_log) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-sql", type=Path, default=SEED_DEFAULT)
    parser.add_argument("--salida", type=Path, default=SALIDA_DEFAULT)
    parser.add_argument("--solo-preparar", action="store_true")
    args = parser.parse_args()
    if not args.seed_sql.is_file():
        raise SystemExit(f"No existe el seed: {args.seed_sql}")

    manifiesto = cargar_manifesto()
    datos = base.cargar_datos(args.seed_sql, manifiesto)
    etiquetas, dataset, descartes, firma = preparar(datos, manifiesto)
    firma_sha256 = hash_firma_previa(firma)
    if args.solo_preparar:
        print(json.dumps(firma, ensure_ascii=False, indent=2))
        print(f"firma_previa_sha256={firma_sha256}")
        print("No se ajusto ningun modelo.")
        return

    validar_firma_previa(firma, manifiesto)
    resultados, predicciones = ejecutar(datos, manifiesto, dataset)
    escribir_artefactos(
        args.salida,
        args.seed_sql,
        manifiesto,
        datos,
        etiquetas,
        dataset,
        descartes,
        firma,
        resultados,
        predicciones,
    )
    print(f"OK: Via 3 ejecutada con {len(dataset)} filas y 7 predictores.")
    for anio in manifiesto["folds_externos"]:
        fold = resultados["folds"][str(anio)]
        print(
            f"  {anio}: {fold['estado']} — train={fold['n_train']}, "
            f"test={fold['n_test']}, alto externo={fold['distribucion_test']['alto']}"
        )
    print("Recomendacion: no adoptar la Via 3.")
    print(f"Artefactos: {args.salida}")


if __name__ == "__main__":
    main()
