"""Topes de tamaño de los modelos de alertas (sin base de datos)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.alertas import (
    LARGO_BLOQUE,
    LARGO_LINEA,
    LARGO_TEXTO,
    LARGO_TITULO,
    AlertaCrear,
    AlertaParche,
)

BASE = {
    "tipo": "dengue",
    "nivel": "informativo",
    "titulo": "t",
    "contexto": "c",
    "indicaciones": "i",
    "fuente": "f",
    "autor": "a",
    "vigente_desde": "2026-01-01",
}

CAMPOS_CON_TOPE = [
    ("titulo", LARGO_TITULO),
    ("contexto", LARGO_TEXTO),
    ("indicaciones", LARGO_TEXTO),
    ("fuente", LARGO_LINEA),
    ("autor", LARGO_LINEA),
    ("signos_alarma", LARGO_BLOQUE),
    ("criterios_referencia", LARGO_BLOQUE),
    ("que_notificar", LARGO_BLOQUE),
    ("definicion_caso", LARGO_BLOQUE),
    ("contacto_vigilancia", LARGO_LINEA),
]


@pytest.mark.parametrize("campo,tope", CAMPOS_CON_TOPE)
def test_crear_acepta_el_tope_y_rechaza_uno_mas(campo, tope):
    AlertaCrear(**{**BASE, campo: "x" * tope})
    with pytest.raises(ValidationError):
        AlertaCrear(**{**BASE, campo: "x" * (tope + 1)})


@pytest.mark.parametrize("campo,tope", CAMPOS_CON_TOPE)
def test_parche_acepta_el_tope_y_rechaza_uno_mas(campo, tope):
    AlertaParche(**{campo: "x" * tope})
    with pytest.raises(ValidationError):
        AlertaParche(**{campo: "x" * (tope + 1)})


def test_departamentos_no_admite_mas_de_catorce_elementos():
    with pytest.raises(ValidationError):
        AlertaCrear(**{**BASE, "departamentos": ["SV-AH"] * 15})
    with pytest.raises(ValidationError):
        AlertaParche(departamentos=["SV-AH"] * 15)


def test_una_alerta_normal_sigue_siendo_valida():
    alerta = AlertaCrear(**{**BASE, "departamentos": ["SV-AH", "SV-SS"]})
    assert alerta.departamentos == ["SV-AH", "SV-SS"]
