"""Validacion forward-chaining limpia de la Via -1.

Este modulo implementa exclusivamente el protocolo de evaluacion aprobado
para la Via -1. Lee el volcado SQL
canonico, no se conecta a PostgreSQL, no modifica produccion y solo escribe
artefactos bajo ``backend/ingestion/data/interim/via_menos_uno/``.

Uso local desde la raiz del repositorio::

    python3 backend/ingestion/validar_via_menos_uno.py

Uso reproducible con la imagen del backend::

    docker compose run --no-deps --rm \
      -v ./db:/workspace/db:ro backend \
      python ingestion/validar_via_menos_uno.py \
      --seed-sql /workspace/db/seed/seed_datos_reales.sql

El manifiesto versionado es la unica fuente de parametros de la corrida. El
script rechaza un seed cuyo SHA-256 no coincida con el congelado.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_recall_fscore_support,
    roc_auc_score,
)


RAIZ_INGESTION = Path(__file__).resolve().parent
RAIZ_REPO = RAIZ_INGESTION.parent.parent
MANIFESTO_CONGELADO = RAIZ_INGESTION / "via_menos_uno_manifesto_congelado.json"
SEED_DEFAULT = RAIZ_REPO / "db" / "seed" / "seed_datos_reales.sql"
SALIDA = RAIZ_INGESTION / "data" / "interim" / "via_menos_uno"

Clave = tuple[int, int]


def suma_ingenua(valores: Iterable[float]) -> float:
    """Suma de izquierda a derecha, sin compensar el redondeo.

    Desde Python 3.12 sum() compensa el error en floats y cambia los últimos
    bits del resultado, lo que alteraría las firmas y features congeladas. Lo
    congelado debe depender de los datos, no de la versión del intérprete.
    """
    total: float = 0
    for valor in valores:
        total += valor
    return total


class ErrorProtocolo(RuntimeError):
    """La fuente o la ejecucion contradice el manifiesto aprobado."""


@dataclass(frozen=True)
class SemanaCalendario:
    anio: int
    semana: int
    fecha_inicio: date
    fecha_fin: date


@dataclass
class DatosFuente:
    serie: dict[int, dict[int, float]]
    clima: dict[Clave, dict[str, float]]
    calendario: dict[Clave, SemanaCalendario]
    orden_calendario: tuple[Clave, ...]
    indice_calendario: dict[Clave, int]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ResultadoEtiqueta:
    anio: int
    semana: int
    casos: float
    historia: tuple[int, ...]
    n_observaciones: int
    n_anios: int
    corte_inferior: float | None
    corte_superior: float | None
    etiqueta: str | None
    motivo: str | None
    pool_claves: tuple[Clave, ...]


def sha256(ruta: Path) -> str:
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def cargar_manifesto() -> dict[str, Any]:
    manifiesto = json.loads(MANIFESTO_CONGELADO.read_text(encoding="utf-8"))
    if manifiesto.get("version_manifesto") != 1:
        raise ErrorProtocolo("Version de manifiesto no soportada")
    return manifiesto


def _bloque_copy(texto: str, tabla: str) -> list[str]:
    prefijo = f"COPY public.{tabla} "
    lineas = texto.splitlines()
    inicio: int | None = None
    for indice, linea in enumerate(lineas):
        if linea.startswith(prefijo):
            inicio = indice + 1
            continue
        if inicio is not None and linea == r"\.":
            return lineas[inicio:indice]
    raise ErrorProtocolo(f"No se encontro un bloque COPY completo para {tabla}")


def cargar_datos(seed_sql: Path, manifiesto: dict[str, Any]) -> DatosFuente:
    hash_observado = sha256(seed_sql)
    hash_esperado = manifiesto["fuente"]["seed_sha256"]
    if hash_observado != hash_esperado:
        raise ErrorProtocolo(
            "El SHA-256 del seed no coincide con el manifiesto congelado: "
            f"esperado={hash_esperado}, observado={hash_observado}"
        )

    texto = seed_sql.read_text(encoding="utf-8")

    calendario: dict[Clave, SemanaCalendario] = {}
    for linea in _bloque_copy(texto, "semanas_epidemiologicas"):
        campos = linea.split("\t")
        semana = SemanaCalendario(
            anio=int(campos[0]),
            semana=int(campos[1]),
            fecha_inicio=date.fromisoformat(campos[2]),
            fecha_fin=date.fromisoformat(campos[3]),
        )
        clave = (semana.anio, semana.semana)
        if clave in calendario:
            raise ErrorProtocolo(f"Semana duplicada en calendario: {clave}")
        calendario[clave] = semana

    orden_calendario = tuple(
        sorted(calendario, key=lambda clave: calendario[clave].fecha_inicio)
    )
    indice_calendario = {clave: indice for indice, clave in enumerate(orden_calendario)}

    serie: dict[int, dict[int, float]] = defaultdict(dict)
    regiones_casos: set[str] = set()
    fuentes_casos: set[str] = set()
    eventos_casos: set[str] = set()
    anio_minimo = int(manifiesto["fuente"]["casos"]["anio_historia_minimo"])
    for linea in _bloque_copy(texto, "casos_epidemiologicos"):
        campos = linea.split("\t")
        if campos[5] != manifiesto["fuente"]["casos"]["clasificacion"]:
            continue
        anio, semana = int(campos[3]), int(campos[4])
        if anio < anio_minimo:
            continue
        if semana in serie[anio]:
            raise ErrorProtocolo(f"Caso nacional total duplicado: {(anio, semana)}")
        serie[anio][semana] = float(campos[6])
        regiones_casos.add(campos[1])
        eventos_casos.add(campos[2])
        fuentes_casos.add(campos[7])

    if not serie:
        raise ErrorProtocolo("El seed no contiene la serie nacional total")
    if any(len(valores) != 1 for valores in (regiones_casos, eventos_casos, fuentes_casos)):
        raise ErrorProtocolo(
            "Las filas con clasificacion total no identifican una sola region, evento y fuente"
        )

    variables = tuple(manifiesto["predictores"]["variables"])
    excluidas = set(manifiesto["fuente"]["clima"]["excluir_variables"])
    lineas_clima = _bloque_copy(texto, "variables_ambientales")
    regiones_nacionales = {
        campos[1]
        for linea in lineas_clima
        if (campos := linea.split("\t"))[4] in excluidas
    }
    if len(regiones_nacionales) != 1:
        raise ErrorProtocolo(
            "No se pudo identificar de forma univoca la region nacional mediante oni_anom"
        )

    por_region: dict[tuple[int, int, str], dict[str, float]] = defaultdict(dict)
    for linea in lineas_clima:
        campos = linea.split("\t")
        region, variable = campos[1], campos[4]
        if variable not in variables or region in regiones_nacionales:
            continue
        clave_variable = (int(campos[2]), int(campos[3]), variable)
        if region in por_region[clave_variable]:
            raise ErrorProtocolo(
                f"Clima departamental duplicado: {clave_variable}, region_id={region}"
            )
        por_region[clave_variable][region] = float(campos[5])

    clima: dict[Clave, dict[str, float]] = defaultdict(dict)
    grupos_incompletos: list[tuple[int, int, str, int]] = []
    for (anio, semana, variable), valores_por_region in por_region.items():
        if len(valores_por_region) != 14:
            grupos_incompletos.append((anio, semana, variable, len(valores_por_region)))
            continue
        clima[(anio, semana)][variable] = float(
            suma_ingenua(valores_por_region.values()) / len(valores_por_region)
        )

    claves_sin_calendario = {
        (anio, semana)
        for anio, semanas in serie.items()
        for semana in semanas
        if (anio, semana) not in calendario
    }
    claves_sin_calendario.update(clave for clave in clima if clave not in calendario)
    if claves_sin_calendario:
        muestra = sorted(claves_sin_calendario)[:5]
        raise ErrorProtocolo(f"Hay datos sin semana de calendario: {muestra}")

    return DatosFuente(
        serie={anio: dict(semanas) for anio, semanas in serie.items()},
        clima={clave: dict(valores) for clave, valores in clima.items()},
        calendario=calendario,
        orden_calendario=orden_calendario,
        indice_calendario=indice_calendario,
        metadata={
            "region_id_casos": next(iter(regiones_casos)),
            "tipo_evento_id_casos": next(iter(eventos_casos)),
            "fuente_id_casos": next(iter(fuentes_casos)),
            "region_id_nacional_clima": next(iter(regiones_nacionales)),
            "grupos_clima_incompletos": grupos_incompletos,
            "anios_casos": sorted(serie),
            "anios_clima": sorted({anio for anio, _semana in clima}),
        },
    )


def percentil_lineal_inclusivo(valores: Sequence[float], p: float) -> float:
    if not valores:
        raise ValueError("No se puede calcular un percentil sin observaciones")
    ordenados = sorted(float(valor) for valor in valores)
    if len(ordenados) == 1:
        return ordenados[0]
    posicion = p * (len(ordenados) - 1)
    inferior = int(posicion)
    superior = min(inferior + 1, len(ordenados) - 1)
    fraccion = posicion - inferior
    return ordenados[inferior] + (ordenados[superior] - ordenados[inferior]) * fraccion


def historia_permitida(
    serie: dict[int, dict[int, float]],
    anio_objetivo: int,
    manifiesto: dict[str, Any],
) -> tuple[int, ...]:
    minimo = int(manifiesto["fuente"]["casos"]["anio_historia_minimo"])
    excluidos = set(manifiesto["exclusiones"]["anios"])
    return tuple(
        anio
        for anio in sorted(serie)
        if minimo <= anio < anio_objetivo and anio not in excluidos
    )


def etiquetar_anio(
    serie: dict[int, dict[int, float]],
    anio_objetivo: int,
    manifiesto: dict[str, Any],
    historia: Sequence[int] | None = None,
) -> dict[Clave, ResultadoEtiqueta]:
    """Etiqueta un anio sin consultar ningun anio igual o posterior.

    ``historia`` existe para auditorias y pruebas de mutacion. El camino de
    ejecucion siempre usa ``historia_permitida``.
    """

    if anio_objetivo not in serie:
        return {}
    historia_real = tuple(
        historia
        if historia is not None
        else historia_permitida(serie, anio_objetivo, manifiesto)
    )
    ventana = int(manifiesto["etiqueta"]["ventana_semanas"])
    piso_obs = int(manifiesto["etiqueta"]["piso_observaciones"])
    piso_anios = int(manifiesto["etiqueta"]["piso_anios"])
    p_inferior, p_superior = manifiesto["etiqueta"]["percentiles"]

    salida: dict[Clave, ResultadoEtiqueta] = {}
    for semana, casos in sorted(serie[anio_objetivo].items()):
        pool_valores: list[float] = []
        pool_claves: list[Clave] = []
        anios_presentes = 0
        for anio_historia in historia_real:
            claves_anio = [
                (anio_historia, semana_vecina)
                for semana_vecina in range(semana - ventana, semana + ventana + 1)
                if semana_vecina >= 1 and semana_vecina in serie.get(anio_historia, {})
            ]
            if claves_anio:
                anios_presentes += 1
                pool_claves.extend(claves_anio)
                pool_valores.extend(serie[anio][sem] for anio, sem in claves_anio)

        if len(pool_valores) < piso_obs or anios_presentes < piso_anios:
            resultado = ResultadoEtiqueta(
                anio=anio_objetivo,
                semana=semana,
                casos=casos,
                historia=historia_real,
                n_observaciones=len(pool_valores),
                n_anios=anios_presentes,
                corte_inferior=None,
                corte_superior=None,
                etiqueta=None,
                motivo="sin_suficiencia_etiqueta",
                pool_claves=tuple(pool_claves),
            )
        else:
            corte_inferior = percentil_lineal_inclusivo(pool_valores, float(p_inferior))
            corte_superior = percentil_lineal_inclusivo(pool_valores, float(p_superior))
            etiqueta = (
                "alto"
                if casos > corte_superior
                else "medio"
                if casos > corte_inferior
                else "bajo"
            )
            resultado = ResultadoEtiqueta(
                anio=anio_objetivo,
                semana=semana,
                casos=casos,
                historia=historia_real,
                n_observaciones=len(pool_valores),
                n_anios=anios_presentes,
                corte_inferior=corte_inferior,
                corte_superior=corte_superior,
                etiqueta=etiqueta,
                motivo=None,
                pool_claves=tuple(pool_claves),
            )
        salida[(anio_objetivo, semana)] = resultado
    return salida


def construir_etiquetas(
    datos: DatosFuente,
    manifiesto: dict[str, Any],
    anios: Iterable[int] | None = None,
) -> dict[Clave, ResultadoEtiqueta]:
    anios_requeridos = anios or manifiesto["etiqueta"]["anios_diagnostico"]
    salida: dict[Clave, ResultadoEtiqueta] = {}
    for anio in anios_requeridos:
        salida.update(etiquetar_anio(datos.serie, int(anio), manifiesto))
    return salida


def claves_anteriores(datos: DatosFuente, clave: Clave, cantidad: int) -> tuple[Clave, ...] | None:
    indice = datos.indice_calendario.get(clave)
    if indice is None or indice < cantidad:
        return None
    claves = datos.orden_calendario[indice - cantidad : indice]
    secuencia = (*claves, clave)
    for anterior, siguiente in zip(secuencia, secuencia[1:]):
        fecha_anterior = datos.calendario[anterior].fecha_inicio
        fecha_siguiente = datos.calendario[siguiente].fecha_inicio
        if fecha_siguiente - fecha_anterior != timedelta(days=7):
            return None
    return tuple(reversed(claves))


def columnas_predictores(manifiesto: dict[str, Any]) -> list[str]:
    columnas: list[str] = []
    for variable in manifiesto["predictores"]["variables"]:
        columnas.extend(
            f"{variable}_lag{int(lag)}" for lag in manifiesto["predictores"]["lags"]
        )
        columnas.extend(
            f"{variable}_media_movil{int(ventana)}"
            for ventana in manifiesto["predictores"]["medias_moviles"]
        )
    return columnas


def construir_dataset(
    datos: DatosFuente,
    etiquetas: dict[Clave, ResultadoEtiqueta],
    manifiesto: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[Clave, str]]:
    filas: list[dict[str, Any]] = []
    descartes: dict[Clave, str] = {}
    variables = tuple(manifiesto["predictores"]["variables"])
    lags = tuple(int(valor) for valor in manifiesto["predictores"]["lags"])
    ventanas = tuple(int(valor) for valor in manifiesto["predictores"]["medias_moviles"])
    max_historia = max((*lags, *ventanas))

    for clave, resultado in sorted(etiquetas.items()):
        if resultado.etiqueta is None:
            descartes[clave] = resultado.motivo or "sin_etiqueta"
            continue
        anteriores = claves_anteriores(datos, clave, max_historia)
        if anteriores is None:
            descartes[clave] = "sin_historia_climatica"
            continue
        if any(
            variable not in datos.clima.get(clave_anterior, {})
            for clave_anterior in anteriores
            for variable in variables
        ):
            descartes[clave] = "sin_historia_climatica"
            continue

        features: dict[str, float] = {}
        for variable in variables:
            for lag in lags:
                features[f"{variable}_lag{lag}"] = datos.clima[anteriores[lag - 1]][variable]
            for ventana in ventanas:
                valores = [datos.clima[clave_anterior][variable] for clave_anterior in anteriores[:ventana]]
                features[f"{variable}_media_movil{ventana}"] = float(suma_ingenua(valores) / ventana)

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


def construir_fold(
    filas: Sequence[dict[str, Any]],
    anio_externo: int,
    manifiesto: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    objetivos = set(int(anio) for anio in manifiesto["etiqueta"]["anios_objetivo"])
    excluidos = set(int(anio) for anio in manifiesto["exclusiones"]["anios"])
    train = [
        fila
        for fila in filas
        if fila["anio"] in objetivos
        and fila["anio"] < anio_externo
        and fila["anio"] not in excluidos
    ]
    test = [fila for fila in filas if fila["anio"] == anio_externo]
    return sorted(train, key=lambda fila: (fila["anio"], fila["semana"])), sorted(
        test, key=lambda fila: (fila["anio"], fila["semana"])
    )


def distribucion(etiquetas: Iterable[str], clases: Sequence[str]) -> dict[str, int]:
    conteo = Counter(etiquetas)
    return {clase: int(conteo[clase]) for clase in clases}


def estado_fold(
    train: Sequence[dict[str, Any]],
    test: Sequence[dict[str, Any]],
    clases: Sequence[str],
) -> tuple[str, list[str]]:
    clases_train = {fila["etiqueta"] for fila in train}
    if len(clases_train) < 2:
        estado = "no_entrenable"
    elif len(clases_train) < len(clases):
        estado = "entrenable_con_clase_ausente"
    else:
        estado = "entrenable"
    marcas: list[str] = []
    if not any(fila["etiqueta"] == "alto" for fila in test):
        marcas.append("recall_alto_no_evaluable")
    return estado, marcas


def validar_firma_fold(
    anio_externo: int,
    train: Sequence[dict[str, Any]],
    test: Sequence[dict[str, Any]],
    estado: str,
    manifiesto: dict[str, Any],
) -> None:
    clases = manifiesto["evaluacion"]["clases"]
    esperada = manifiesto["firma_esperada"][str(anio_externo)]
    observada_train = distribucion((fila["etiqueta"] for fila in train), clases)
    alto_externo = sum(fila["etiqueta"] == "alto" for fila in test)
    if observada_train != esperada["entrenamiento"]:
        raise ErrorProtocolo(
            f"Fold {anio_externo}: distribucion de entrenamiento distinta de la firma: "
            f"esperada={esperada['entrenamiento']}, observada={observada_train}"
        )
    if alto_externo != esperada["alto_externo"] or estado != esperada["estado"]:
        raise ErrorProtocolo(
            f"Fold {anio_externo}: estado o soporte externo distinto de la firma congelada"
        )


def _moda(
    valores: Iterable[str],
    orden: Sequence[str],
    desempate_preferido: str | None = None,
) -> str:
    conteo = Counter(valores)
    if not conteo:
        raise ValueError("No existe moda para una coleccion vacia")
    maximo = max(conteo.values())
    empatadas = {clase for clase, cantidad in conteo.items() if cantidad == maximo}
    if desempate_preferido in empatadas:
        return str(desempate_preferido)
    return next(clase for clase in orden if clase in empatadas)


def referencias(
    train: Sequence[dict[str, Any]],
    test: Sequence[dict[str, Any]],
    datos: DatosFuente,
    manifiesto: dict[str, Any],
) -> dict[str, list[str | None]]:
    orden = manifiesto["evaluacion"]["orden_desempate"]
    por_semana: dict[int, list[str]] = defaultdict(list)
    for fila in train:
        por_semana[int(fila["semana"])].append(fila["etiqueta"])
    moda_global = _moda((fila["etiqueta"] for fila in train), orden)

    climatologica = [
        _moda(por_semana[fila["semana"]], orden, moda_global)
        if por_semana[fila["semana"]]
        else moda_global
        for fila in test
    ]
    mayoritaria = [moda_global for _fila in test]
    siempre_alto = ["alto" for _fila in test]

    etiquetas_por_clave = {(fila["anio"], fila["semana"]): fila["etiqueta"] for fila in test}
    persistencia: list[str | None] = []
    for fila in test:
        clave = (fila["anio"], fila["semana"])
        indice = datos.indice_calendario[clave]
        clave_anterior = datos.orden_calendario[indice - 1] if indice > 0 else None
        if clave_anterior is None or clave_anterior[0] != fila["anio"]:
            persistencia.append(None)
        else:
            persistencia.append(etiquetas_por_clave.get(clave_anterior))

    return {
        "climatologica": climatologica,
        "constante_mayoritaria": mayoritaria,
        "siempre_alto": siempre_alto,
        "persistencia": persistencia,
    }


def metricas_clasificacion(
    y_real: Sequence[str],
    y_pred: Sequence[str],
    clases: Sequence[str],
    puntaje_alto: Sequence[float] | None = None,
) -> dict[str, Any]:
    if not y_real or len(y_real) != len(y_pred):
        raise ValueError("Las metricas requieren vectores no vacios y alineados")
    precision, recall, f1_clase, soporte = precision_recall_fscore_support(
        y_real, y_pred, labels=clases, zero_division=0
    )
    soporte_alto = sum(valor == "alto" for valor in y_real)
    aciertos_alto = sum(
        real == "alto" and predicho == "alto" for real, predicho in zip(y_real, y_pred)
    )
    falsos_positivos_alto = sum(
        real != "alto" and predicho == "alto" for real, predicho in zip(y_real, y_pred)
    )
    salida: dict[str, Any] = {
        "f1_macro": float(
            f1_score(y_real, y_pred, labels=clases, average="macro", zero_division=0)
        ),
        "recall_alto": (
            float(recall[clases.index("alto")]) if soporte_alto > 0 else None
        ),
        "aciertos_alto": int(aciertos_alto),
        "soporte_alto": int(soporte_alto),
        "falsos_positivos_alto": int(falsos_positivos_alto),
        "por_clase": {
            clase: {
                "precision": float(precision[indice]),
                "recall": float(recall[indice]),
                "f1": float(f1_clase[indice]),
                "soporte": int(soporte[indice]),
            }
            for indice, clase in enumerate(clases)
        },
        "matriz_confusion": confusion_matrix(y_real, y_pred, labels=clases).tolist(),
        "distribucion_real": distribucion(y_real, clases),
        "distribucion_predicha": distribucion(y_pred, clases),
        "auc_roc_alto": None,
        "precision_recall_alto": None,
    }

    real_binario = np.array([valor == "alto" for valor in y_real], dtype=int)
    if puntaje_alto is not None and len(set(real_binario.tolist())) == 2:
        puntajes = np.asarray(puntaje_alto, dtype=float)
        curva_precision, curva_recall, umbrales = precision_recall_curve(
            real_binario, puntajes
        )
        salida["auc_roc_alto"] = float(roc_auc_score(real_binario, puntajes))
        salida["precision_recall_alto"] = {
            "average_precision": float(average_precision_score(real_binario, puntajes)),
            "precision": curva_precision.tolist(),
            "recall": curva_recall.tolist(),
            "umbrales": umbrales.tolist(),
        }
    return salida


def metricas_referencias(
    y_real: Sequence[str],
    predicciones: dict[str, list[str | None]],
    clases: Sequence[str],
) -> dict[str, Any]:
    salida: dict[str, Any] = {}
    for nombre, valores in predicciones.items():
        indices = [indice for indice, valor in enumerate(valores) if valor is not None]
        reales = [y_real[indice] for indice in indices]
        predichos = [str(valores[indice]) for indice in indices]
        puntajes = [1.0 if valor == "alto" else 0.0 for valor in predichos]
        salida[nombre] = {
            "filas_evaluadas": len(indices),
            "filas_excluidas": len(valores) - len(indices),
            "metricas": metricas_clasificacion(reales, predichos, clases, puntajes),
        }
    return salida


def configuracion_modelo(manifiesto: dict[str, Any]) -> dict[str, Any]:
    modelo = manifiesto["modelo"]
    return {
        "n_estimators": int(modelo["n_estimators"]),
        "class_weight": modelo["class_weight"],
    }


def _matrices(
    filas: Sequence[dict[str, Any]], columnas: Sequence[str]
) -> tuple[np.ndarray, np.ndarray]:
    X = np.asarray([[float(fila[columna]) for columna in columnas] for fila in filas])
    y = np.asarray([fila["etiqueta"] for fila in filas])
    return X, y


def _criterio(
    modelo: dict[str, Any],
    referencias_fold: dict[str, Any],
) -> dict[str, Any]:
    clima = referencias_fold["climatologica"]["metricas"]
    constante = referencias_fold["constante_mayoritaria"]["metricas"]
    siempre_alto = referencias_fold["siempre_alto"]["metricas"]
    if modelo["recall_alto"] is None:
        return {
            "estado": "recall_alto_no_evaluable",
            "supera_climatologica": None,
            "veto_constantes": bool(
                constante["f1_macro"] > modelo["f1_macro"]
                or siempre_alto["f1_macro"] > modelo["f1_macro"]
            ),
            "exito": None,
        }
    supera = bool(
        clima["recall_alto"] is not None
        and modelo["f1_macro"] > clima["f1_macro"]
        and modelo["recall_alto"] > clima["recall_alto"]
    )
    veto = bool(
        constante["f1_macro"] > modelo["f1_macro"]
        or siempre_alto["f1_macro"] > modelo["f1_macro"]
    )
    return {
        "estado": "evaluable",
        "supera_climatologica": supera,
        "veto_constantes": veto,
        "exito": bool(supera and not veto),
    }


def _resumen_estabilidad(resultados_semilla: dict[str, Any]) -> dict[str, Any]:
    metricas = [resultado["metricas"] for resultado in resultados_semilla.values()]
    f1 = [resultado["f1_macro"] for resultado in metricas]
    recalls = [
        resultado["recall_alto"]
        for resultado in metricas
        if resultado["recall_alto"] is not None
    ]
    exitos = [
        resultado["criterio"]["exito"]
        for resultado in resultados_semilla.values()
        if resultado["criterio"]["exito"] is not None
    ]
    return {
        "n_semillas": len(metricas),
        "f1_macro": {
            "min": float(min(f1)),
            "media": float(suma_ingenua(f1) / len(f1)),
            "max": float(max(f1)),
        },
        "recall_alto": (
            {
                "min": float(min(recalls)),
                "media": float(suma_ingenua(recalls) / len(recalls)),
                "max": float(max(recalls)),
            }
            if recalls
            else None
        ),
        "exito_en_semillas_evaluables": int(sum(valor is True for valor in exitos)),
        "semillas_evaluables": len(exitos),
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
    estado, marcas = estado_fold(train, test, clases)
    validar_firma_fold(anio_externo, train, test, estado, manifiesto)

    y_real = [fila["etiqueta"] for fila in test]
    pred_referencias = referencias(train, test, datos, manifiesto)
    met_referencias = metricas_referencias(y_real, pred_referencias, clases)
    filas_prediccion: list[dict[str, Any]] = []

    resultado: dict[str, Any] = {
        "anio_externo": anio_externo,
        "estado": estado,
        "marcas": marcas,
        "anios_entrenamiento": sorted({fila["anio"] for fila in train}),
        "n_train": len(train),
        "n_test": len(test),
        "distribucion_train": distribucion((fila["etiqueta"] for fila in train), clases),
        "distribucion_test": distribucion(y_real, clases),
        "referencias": met_referencias,
        "semillas": {},
        "estabilidad": None,
    }

    semillas_estabilidad = [int(valor) for valor in manifiesto["modelo"]["semillas_estabilidad"]]
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
                    **{f"pred_{nombre}": valores[indice] or "" for nombre, valores in pred_referencias.items()},
                }
            )
        return resultado, filas_prediccion

    X_train, y_train = _matrices(train, columnas)
    X_test, _y_test = _matrices(test, columnas)
    config = configuracion_modelo(manifiesto)
    for semilla in semillas:
        modelo = RandomForestClassifier(random_state=semilla, **config)
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
        metricas = metricas_clasificacion(
            y_real, pred_modelo, clases, probabilidades["alto"]
        )
        criterio = _criterio(metricas, met_referencias)
        resultado["semillas"][str(semilla)] = {
            "tipo": "estabilidad" if semilla in semillas_estabilidad else "referencia_historica",
            "metricas": metricas,
            "criterio": criterio,
        }
        for indice, fila in enumerate(test):
            filas_prediccion.append(
                {
                    "anio_externo": anio_externo,
                    "semilla": semilla,
                    "tipo_semilla": (
                        "estabilidad" if semilla in semillas_estabilidad else "referencia_historica"
                    ),
                    "anio": fila["anio"],
                    "semana": fila["semana"],
                    "etiqueta_real": fila["etiqueta"],
                    "pred_modelo": pred_modelo[indice],
                    "p_bajo": probabilidades["bajo"][indice],
                    "p_medio": probabilidades["medio"][indice],
                    "p_alto": probabilidades["alto"][indice],
                    **{f"pred_{nombre}": valores[indice] or "" for nombre, valores in pred_referencias.items()},
                }
            )
    resultado["estabilidad"] = _resumen_estabilidad(
        {
            str(semilla): resultado["semillas"][str(semilla)]
            for semilla in semillas_estabilidad
        }
    )
    return resultado, filas_prediccion


def ejecutar(
    datos: DatosFuente,
    manifiesto: dict[str, Any],
) -> tuple[
    dict[Clave, ResultadoEtiqueta],
    list[dict[str, Any]],
    dict[Clave, str],
    dict[str, Any],
    list[dict[str, Any]],
]:
    etiquetas = construir_etiquetas(datos, manifiesto)
    anios_objetivo = set(int(anio) for anio in manifiesto["etiqueta"]["anios_objetivo"])
    etiquetas_objetivo = {
        clave: resultado for clave, resultado in etiquetas.items() if clave[0] in anios_objetivo
    }
    dataset, descartes = construir_dataset(datos, etiquetas_objetivo, manifiesto)
    resultados: dict[str, Any] = {"folds": {}}
    predicciones: list[dict[str, Any]] = []
    for anio_externo in manifiesto["folds_externos"]:
        train, test = construir_fold(dataset, int(anio_externo), manifiesto)
        resultado_fold, filas_prediccion = evaluar_fold(
            int(anio_externo), train, test, datos, manifiesto
        )
        resultados["folds"][str(anio_externo)] = resultado_fold
        predicciones.extend(filas_prediccion)
    resultados["conclusion_estructural"] = {
        "folds_con_alto_en_train_y_test": 0,
        "test_final_intacto_y_evaluable": False,
        "interpretacion": "validacion_forward_chaining_exploratoria",
    }
    return etiquetas, dataset, descartes, resultados, predicciones


def _escribir_csv(ruta: Path, filas: Sequence[dict[str, Any]], columnas: Sequence[str]) -> None:
    with ruta.open("w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        escritor.writeheader()
        escritor.writerows(filas)


def escribir_artefactos(
    seed_sql: Path,
    manifiesto: dict[str, Any],
    datos: DatosFuente,
    etiquetas: dict[Clave, ResultadoEtiqueta],
    dataset: list[dict[str, Any]],
    descartes: dict[Clave, str],
    resultados: dict[str, Any],
    predicciones: list[dict[str, Any]],
) -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)

    filas_etiquetas = []
    for resultado in etiquetas.values():
        fila = asdict(resultado)
        fila["historia"] = ",".join(str(anio) for anio in resultado.historia)
        fila["pool_claves"] = ",".join(f"{anio}-SE{semana:02d}" for anio, semana in resultado.pool_claves)
        filas_etiquetas.append(fila)
    _escribir_csv(
        SALIDA / "etiquetas.csv",
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

    columnas_features = columnas_predictores(manifiesto)
    filas_dataset = []
    for fila in dataset:
        serializada = dict(fila)
        serializada["historia"] = ",".join(str(anio) for anio in fila["historia"])
        filas_dataset.append(serializada)
    _escribir_csv(
        SALIDA / "dataset.csv",
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
            *columnas_features,
        ],
    )

    _escribir_csv(
        SALIDA / "predicciones.csv",
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

    (SALIDA / "metricas.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    roles = {
        str(anio): {
            "train_anios": resultados["folds"][str(anio)]["anios_entrenamiento"],
            "n_train": resultados["folds"][str(anio)]["n_train"],
            "n_test": resultados["folds"][str(anio)]["n_test"],
            "estado": resultados["folds"][str(anio)]["estado"],
        }
        for anio in manifiesto["folds_externos"]
    }
    manifiesto_ejecucion = {
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "comando": " ".join(sys.argv),
        "manifiesto_congelado": manifiesto,
        "hashes": {
            "seed_sql_sha256": sha256(seed_sql),
            "script_sha256": sha256(Path(__file__).resolve()),
            "manifiesto_congelado_sha256": sha256(MANIFESTO_CONGELADO),
        },
        "rutas": {
            "seed_sql": str(seed_sql.resolve()),
            "script": str(Path(__file__).resolve()),
            "salida": str(SALIDA.resolve()),
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
            "predictores": len(columnas_features),
            "columnas_predictores": columnas_features,
            "descartes": {
                motivo: sum(valor == motivo for valor in descartes.values())
                for motivo in sorted(set(descartes.values()))
            },
        },
        "roles": roles,
    }
    (SALIDA / "manifiesto_ejecucion.json").write_text(
        json.dumps(manifiesto_ejecucion, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lineas_log = [
        "VIA -1 — VALIDACION FORWARD-CHAINING LIMPIA",
        f"generado_utc={manifiesto_ejecucion['generado_utc']}",
        f"seed_sha256={manifiesto_ejecucion['hashes']['seed_sql_sha256']}",
        f"script_sha256={manifiesto_ejecucion['hashes']['script_sha256']}",
        f"dataset={len(dataset)} filas, {len(columnas_features)} predictores",
    ]
    for anio in manifiesto["folds_externos"]:
        fold = resultados["folds"][str(anio)]
        estabilidad = fold["estabilidad"]
        resumen = "sin modelo" if estabilidad is None else (
            f"F1 macro {estabilidad['f1_macro']['min']:.3f}.."
            f"{estabilidad['f1_macro']['max']:.3f}"
        )
        lineas_log.append(
            f"fold={anio} estado={fold['estado']} train={fold['n_train']} "
            f"test={fold['n_test']} {resumen}"
        )
    lineas_log.extend(
        [
            "test_final_intacto_y_evaluable=false",
            "interpretacion=validacion_forward_chaining_exploratoria",
        ]
    )
    (SALIDA / "ejecucion.log").write_text("\n".join(lineas_log) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed-sql",
        type=Path,
        default=SEED_DEFAULT,
        help=f"Volcado canonico (default: {SEED_DEFAULT})",
    )
    args = parser.parse_args()
    if not args.seed_sql.is_file():
        raise SystemExit(f"No existe el seed: {args.seed_sql}")

    manifiesto = cargar_manifesto()
    datos = cargar_datos(args.seed_sql, manifiesto)
    etiquetas, dataset, descartes, resultados, predicciones = ejecutar(datos, manifiesto)
    escribir_artefactos(
        args.seed_sql,
        manifiesto,
        datos,
        etiquetas,
        dataset,
        descartes,
        resultados,
        predicciones,
    )

    print(f"OK: Via -1 ejecutada con {len(dataset)} filas y 21 predictores.")
    for anio in manifiesto["folds_externos"]:
        fold = resultados["folds"][str(anio)]
        print(
            f"  {anio}: {fold['estado']} — train={fold['n_train']}, test={fold['n_test']}, "
            f"alto externo={fold['distribucion_test']['alto']}"
        )
    print("Conclusion: validacion forward-chaining exploratoria; no existe test intacto y evaluable.")
    print(f"Artefactos: {SALIDA}")


if __name__ == "__main__":
    main()
