"""
Congela las salidas del clasificador de riesgo nacional retirado (ADR 0025).

El clasificador ya no se entrena ni se extiende, pero /prediccion sigue
mostrando lo que predijo y por qué se retiró. Servirlo en vivo obligaba a
cargar scikit-learn y joblib en la imagen de la API para deserializar un
modelo que no cambia. Este script corre el modelo una sola vez sobre cada
semana del dataset de modelado y escribe el resultado en
backend/api/datos/riesgo_nacional_congelado.json, que el endpoint
GET /api/riesgo-nacional sirve tal cual.

Mismo cálculo que hacía el endpoint: la fila del dataset por (anio,
semana_epi), predict + predict_proba sobre `columnas_feature`, y las
probabilidades redondeadas a 4 decimales en el orden de `clases`. La
procedencia guarda el SHA-256 del modelo y del dataset para poder comprobar
de qué artefactos salió el archivo.

Requiere requirements-ingesta.txt (scikit-learn, joblib).

Uso (desde backend/ingestion/):
    python3 congelar_clasificador.py
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import joblib

RAIZ = Path(__file__).parent
DATASET = RAIZ / "data" / "interim" / "dataset_modelado" / "dataset_modelado.csv"
MODELO = RAIZ / "data" / "interim" / "modelo" / "clasificador_riesgo_nacional_v1.joblib"
METRICAS = RAIZ / "data" / "interim" / "modelo" / "metricas_modelo.json"
SALIDA = RAIZ.parent / "api" / "datos" / "riesgo_nacional_congelado.json"


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def congelar(dataset: Path = DATASET, modelo: Path = MODELO, metricas: Path = METRICAS) -> dict:
    with open(dataset, newline="", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    # joblib deserializa con pickle: solo se carga el modelo versionado que
    # produjo entrenar_clasificador.py, nunca un archivo de terceros. Que la
    # API ya no lo cargue es otra razón de este script (ADR 0025).
    paquete = joblib.load(modelo)
    clasificador = paquete["modelo"]
    columnas = paquete["columnas_feature"]
    clases = paquete["clases"]

    X = [[float(fila[c]) for c in columnas] for fila in filas]
    predichas = clasificador.predict(X)
    probabilidades = clasificador.predict_proba(X)

    semanas = []
    for fila, etiqueta, probas in zip(filas, predichas, probabilidades):
        por_clase = dict(zip(clasificador.classes_, probas.tolist()))
        semanas.append({
            "anio": int(fila["anio"]),
            "semana_epi": int(fila["semana_epi"]),
            "etiqueta_predicha": str(etiqueta),
            "etiqueta_real": fila["etiqueta_riesgo"],
            "probabilidades": {clase: round(por_clase.get(clase, 0.0), 4) for clase in clases},
            "casos_observados": float(fila["casos"]),
        })

    return {
        "procedencia": {
            "script": "backend/ingestion/congelar_clasificador.py",
            "modelo": MODELO.relative_to(RAIZ.parent.parent).as_posix(),
            "modelo_sha256": _sha256(modelo),
            "dataset": DATASET.relative_to(RAIZ.parent.parent).as_posix(),
            "dataset_sha256": _sha256(dataset),
        },
        "metricas_modelo": json.loads(metricas.read_text(encoding="utf-8")) if metricas.exists() else None,
        "semanas": semanas,
    }


def main() -> None:
    artefacto = congelar()
    SALIDA.write_text(json.dumps(artefacto, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(artefacto['semanas'])} semanas -> {SALIDA} ({SALIDA.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
