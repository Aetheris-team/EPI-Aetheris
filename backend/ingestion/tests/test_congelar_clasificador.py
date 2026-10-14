"""El artefacto congelado del clasificador retirado (ADR 0025) coincide con lo
que el modelo versionado predice hoy. Si alguien reentrena el modelo o
regenera el dataset sin volver a correr congelar_clasificador.py, este test
falla. No necesita Postgres; sí requirements-ingesta.txt."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from congelar_clasificador import SALIDA, congelar  # noqa: E402


def test_el_artefacto_versionado_coincide_con_el_modelo():
    versionado = json.loads(SALIDA.read_text(encoding="utf-8"))
    assert congelar() == versionado


def test_una_fila_por_semana():
    semanas = json.loads(SALIDA.read_text(encoding="utf-8"))["semanas"]
    claves = [(f["anio"], f["semana_epi"]) for f in semanas]
    assert len(claves) == len(set(claves)) == 250
