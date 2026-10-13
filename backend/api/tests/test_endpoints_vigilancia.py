"""Pruebas de GET /api/v1/vigilancia/integridad (Modulo 4).

Usa FastAPI TestClient contra Postgres si esta disponible -- mismo patron
que test_endpoints_presion.py: se omite (no falla) si la base no esta
arriba. No afirma cifras del volcado: el contrato y las invariantes se
comprueban contra las funciones puras de vigilancia.py.
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

API_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = API_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

load_dotenv(REPO_ROOT / ".env", override=False)
os.environ.setdefault("POSTGRES_HOST", "localhost")

sys.path.insert(0, str(BACKEND_DIR))

from api.main import app  # noqa: E402
from api.vigilancia import (  # noqa: E402
    AVISO_HONESTIDAD_VIGILANCIA,
    CAMPOS_PROHIBIDOS,
    N_DEPARTAMENTOS,
    SERIES_ANTIGUEDAD,
    SERIES_COMPLETITUD,
    antiguedad_serie,
    completitud_semana,
    cuadre_boletin,
    cargar_boletin_semana,
    cargar_catalogo_departamentos,
    cargar_presentes_semana,
    cargar_ultimas_se,
)
from fastapi.testclient import TestClient  # noqa: E402


def _db_disponible() -> bool:
    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            database=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


def _conectar():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        connect_timeout=3,
    )


class IntegridadSemanalTest(unittest.TestCase):
    def setUp(self):
        if not _db_disponible():
            raise unittest.SkipTest(
                "Postgres no disponible en POSTGRES_HOST -- se omite la suite."
            )
        self.client = TestClient(app)

    def test_respuesta_ok_y_forma_esperada(self):
        r = self.client.get(
            "/api/v1/vigilancia/integridad",
            params={"week": 24, "year": 2019},
        )
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual(cuerpo["semana_epi"], 24)
        self.assertEqual(cuerpo["anio"], 2019)
        self.assertEqual(cuerpo["aviso"], AVISO_HONESTIDAD_VIGILANCIA)
        self.assertIn("completitud", cuerpo)
        self.assertIn("cuadre", cuerpo)
        self.assertIn("antiguedad", cuerpo)
        self.assertNotIn("resumen_anual", cuerpo)
        self.assertFalse(CAMPOS_PROHIBIDOS & cuerpo.keys())
        for serie in SERIES_COMPLETITUD:
            celda = cuerpo["completitud"][serie]
            self.assertEqual(celda["esperado"], N_DEPARTAMENTOS)
            self.assertEqual(len(celda["departamentos"]), N_DEPARTAMENTOS)
            self.assertEqual(
                celda["n"] + sum(1 for d in celda["departamentos"] if not d["presente"]),
                N_DEPARTAMENTOS,
            )
        for serie in SERIES_ANTIGUEDAD:
            self.assertIn(serie, cuerpo["antiguedad"])

    def test_completitud_coincide_con_el_motor_sobre_la_misma_carga(self):
        r = self.client.get(
            "/api/v1/vigilancia/integridad",
            params={"week": 24, "year": 2019},
        )
        cuerpo = r.json()
        with _conectar() as conn:
            catalogo = cargar_catalogo_departamentos(conn)
            presentes = cargar_presentes_semana(conn, 2019, 24)
        for serie in SERIES_COMPLETITUD:
            esperado = completitud_semana(catalogo, presentes.get(serie, set()))
            self.assertEqual(cuerpo["completitud"][serie], esperado)

    def test_cuadre_expone_el_boletin_almacenado_sin_recalcular(self):
        # SE30/2019 es el unico boletín del corpus con validacion_cuadra=false
        # (discrepancia real de MINSAL, no un fallo de parser).
        r = self.client.get(
            "/api/v1/vigilancia/integridad",
            params={"week": 30, "year": 2019},
        )
        cuerpo = r.json()
        with _conectar() as conn:
            esperado = cuadre_boletin(cargar_boletin_semana(conn, 2019, 30))
        self.assertEqual(cuerpo["cuadre"], esperado)
        self.assertIs(cuerpo["cuadre"]["cuadra"], False)
        self.assertIsNotNone(cuerpo["cuadre"]["probable"]["discrepancia"])
        self.assertIsNotNone(cuerpo["cuadre"]["confirmado"]["discrepancia"])

    def test_semana_sin_boletin_deja_cuadre_en_null(self):
        r = self.client.get(
            "/api/v1/vigilancia/integridad",
            params={"week": 53, "year": 2019},
        )
        cuerpo = r.json()
        self.assertIsNone(cuerpo["cuadre"]["cuadra"])
        self.assertIsNone(cuerpo["cuadre"]["probable"]["discrepancia"])

    def test_antiguedad_usa_el_motor_con_la_fecha_de_hoy(self):
        r = self.client.get(
            "/api/v1/vigilancia/integridad",
            params={"week": 1, "year": 2023},
        )
        cuerpo = r.json()
        hoy = date.today()
        with _conectar() as conn:
            ultimas = cargar_ultimas_se(conn)
        for serie, ultima in ultimas.items():
            self.assertEqual(
                cuerpo["antiguedad"][serie],
                antiguedad_serie(ultima, hoy),
            )

    def test_semana_invalida_devuelve_422(self):
        r = self.client.get(
            "/api/v1/vigilancia/integridad",
            params={"week": 0, "year": 2019},
        )
        self.assertEqual(r.status_code, 422)
        r2 = self.client.get(
            "/api/v1/vigilancia/integridad",
            params={"week": 54, "year": 2019},
        )
        self.assertEqual(r2.status_code, 422)

    def test_week_y_year_van_juntos(self):
        r = self.client.get(
            "/api/v1/vigilancia/integridad",
            params={"week": 24},
        )
        self.assertEqual(r.status_code, 422)
        r2 = self.client.get(
            "/api/v1/vigilancia/integridad",
            params={"year": 2019},
        )
        self.assertEqual(r2.status_code, 422)


class IntegridadResumenTest(unittest.TestCase):
    def setUp(self):
        if not _db_disponible():
            raise unittest.SkipTest(
                "Postgres no disponible en POSTGRES_HOST -- se omite la suite."
            )
        self.client = TestClient(app)

    def test_sin_parametros_devuelve_resumen_anual_y_antiguedad(self):
        r = self.client.get("/api/v1/vigilancia/integridad")
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual(cuerpo["aviso"], AVISO_HONESTIDAD_VIGILANCIA)
        self.assertIn("resumen_anual", cuerpo)
        self.assertIn("antiguedad", cuerpo)
        self.assertNotIn("completitud", cuerpo)
        self.assertNotIn("cuadre", cuerpo)
        self.assertFalse(CAMPOS_PROHIBIDOS & cuerpo.keys())
        self.assertGreater(len(cuerpo["resumen_anual"]), 0)
        for fila in cuerpo["resumen_anual"]:
            self.assertIn("anio", fila)
            for serie in SERIES_COMPLETITUD:
                celda = fila[serie]
                self.assertIn("semanas_completas", celda)
                self.assertIn("semanas_con_dato", celda)
                self.assertEqual(celda["semanas_nominales"], 52)
                self.assertLessEqual(
                    celda["semanas_completas"], celda["semanas_con_dato"]
                )
                self.assertLessEqual(celda["semanas_con_dato"], 53)

    def test_cache_control_de_computo(self):
        r = self.client.get("/api/v1/vigilancia/integridad")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("cache-control"), "public, max-age=900")


class CapaConfianzaEnFuenteTest(unittest.TestCase):
    def test_capa_confianza_queda_disponible_en_el_mapa(self):
        # Respaldo estructural del e2e: el artefacto shipped habilita la capa.
        mapa = (
            REPO_ROOT / "web" / "src" / "components" / "MapaDepartamentos.astro"
        ).read_text(encoding="utf-8")
        bloque = mapa.split("const capaConfianza: DefinicionCapa = {", 1)[1]
        bloque = bloque.split("const CAPAS:", 1)[0]
        self.assertIn("id: 'confianza'", bloque)
        self.assertIn("disponible: true", bloque)
        self.assertNotIn("próximamente", bloque.lower())
        self.assertIn("el boletín no cuadra", bloque)


if __name__ == "__main__":
    unittest.main()


# Las consultas por serie que cargar_ultimas_se hacía antes de juntarlas en
# una sola. Se conservan aquí como referencia: la consulta única tiene que
# devolver exactamente la misma (anio, semana_epi) que cada una de ellas.
_DESDE_CASOS = """
    FROM casos_epidemiologicos c
    JOIN regiones r ON r.id = c.region_id
    JOIN tipos_evento t ON t.id = c.tipo_evento_id
    JOIN fuentes_datos f ON f.id = c.fuente_id
"""
_ORDEN = " ORDER BY anio DESC, semana_epi DESC LIMIT 1"
_REFERENCIA_ULTIMAS_SE = {
    "dengue_minsal_departamental": "SELECT c.anio, c.semana_epi" + _DESDE_CASOS
    + " WHERE r.nivel_admin = 1 AND t.codigo = 'dengue' AND f.codigo = 'minsal_pdf'",
    "dengue_opendengue_nacional": "SELECT c.anio, c.semana_epi" + _DESDE_CASOS
    + " WHERE f.codigo = 'opendengue_v1_3'",
    "dengue_tablero_nacional": "SELECT c.anio, c.semana_epi" + _DESDE_CASOS
    + " WHERE t.codigo = 'dengue' AND f.codigo = 'minsal_tablero'",
    "clima": "SELECT anio, semana_epi FROM variables_ambientales",
    "ira": "SELECT c.anio, c.semana_epi" + _DESDE_CASOS
    + " WHERE t.codigo = 'ira' AND f.codigo = 'minsal_pdf'",
    "neumonias": "SELECT c.anio, c.semana_epi" + _DESDE_CASOS
    + " WHERE t.codigo = 'neumonia' AND f.codigo = 'minsal_pdf'",
    "ira_tablero_nacional": "SELECT c.anio, c.semana_epi" + _DESDE_CASOS
    + " WHERE t.codigo = 'ira' AND f.codigo = 'minsal_tablero'",
    "neumonias_tablero_nacional": "SELECT c.anio, c.semana_epi" + _DESDE_CASOS
    + " WHERE t.codigo = 'neumonia' AND f.codigo = 'minsal_tablero'",
    "virus_respiratorios": "SELECT anio, semana_epi FROM vigilancia_virus_respiratorios",
}


class UltimasSeTest(unittest.TestCase):
    def setUp(self):
        if not _db_disponible():
            raise unittest.SkipTest("Postgres no disponible")

    def test_consulta_unica_coincide_con_una_consulta_por_serie(self):
        conn = _conectar()
        try:
            ultimas = cargar_ultimas_se(conn)
            self.assertEqual(list(ultimas), list(SERIES_ANTIGUEDAD))
            for serie, sql in _REFERENCIA_ULTIMAS_SE.items():
                with conn.cursor() as cur:
                    cur.execute(sql + _ORDEN)
                    fila = cur.fetchone()
                esperado = None if fila is None else (int(fila[0]), int(fila[1]))
                self.assertEqual(ultimas[serie], esperado, serie)
        finally:
            conn.close()
