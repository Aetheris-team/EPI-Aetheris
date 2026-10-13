"""Pruebas HTTP de /api/neumonias/* y /api/respiratorios/*. Se omiten si Postgres no responde."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

from dotenv import load_dotenv

API_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = API_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

load_dotenv(REPO_ROOT / ".env", override=False)
os.environ.setdefault("POSTGRES_HOST", "localhost")

sys.path.insert(0, str(BACKEND_DIR))

from api.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _db_disponible() -> bool:
    try:
        import psycopg2
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


class NeumoniasApiTest(unittest.TestCase):
    def setUp(self):
        if not _db_disponible():
            raise unittest.SkipTest("Postgres no disponible")
        self.client = TestClient(app)

    def test_departamental_tiene_aviso_y_14_deptos(self):
        r = self.client.get("/api/neumonias/departamental")
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertIn("aviso", cuerpo)
        self.assertIn("MINSAL", cuerpo["aviso"])
        self.assertEqual(len(cuerpo["departamentos"]), 14)
        self.assertNotIn("riesgo", cuerpo["aviso"].lower())

    def test_temporal_san_salvador(self):
        r = self.client.get("/api/neumonias/temporal/SV-SS")
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual(cuerpo["unidad"], "conteo_notificado")
        self.assertIn("2018", cuerpo["series"])
        self.assertEqual(cuerpo["series"]["2018"][0][0], 3)  # primer corte semanal usable SE3

    def test_temporal_codigo_invalido(self):
        r = self.client.get("/api/neumonias/temporal/XX-ZZ")
        self.assertEqual(r.status_code, 404)


class VirusApiTest(unittest.TestCase):
    def setUp(self):
        if not _db_disponible():
            raise unittest.SkipTest("Postgres no disponible")
        self.client = TestClient(app)

    def test_catalogo_distingue_unidades(self):
        r = self.client.get("/api/respiratorios/virus")
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual(cuerpo["granularidad"], "nacional")
        unidades = {s["unidad"] for s in cuerpo["series"]}
        self.assertIn("conteo", unidades)
        self.assertIn("porcentaje", unidades)

    def test_temporal_vsr_detecciones(self):
        r = self.client.get("/api/respiratorios/temporal", params={"virus": "vsr", "metrica": "detecciones"})
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual(cuerpo["unidad"], "conteo")
        self.assertEqual(cuerpo["metrica"], "detecciones")
        self.assertIn("MINSAL", cuerpo["aviso"])
        self.assertNotIn("causalidad", cuerpo["aviso"].lower())

    def test_temporal_serie_inexistente_404(self):
        r = self.client.get(
            "/api/respiratorios/temporal",
            params={"virus": "influenza", "metrica": "muestras_analizadas"},
        )
        self.assertEqual(r.status_code, 404)
        self.assertIn("No hay serie disponible", r.json()["detail"])

    def test_temporal_virus_desconocido_404(self):
        r = self.client.get(
            "/api/respiratorios/temporal",
            params={"virus": "no_existe", "metrica": "detecciones"},
        )
        self.assertEqual(r.status_code, 404)

    def test_semana_nacional(self):
        r = self.client.get("/api/respiratorios/semana/2023/25")
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        metricas = {o["metrica"] for o in cuerpo["observaciones"]}
        self.assertTrue(metricas <= {"muestras_analizadas", "muestras_positivas", "detecciones", "positividad"})

    def test_cobertura_no_es_m4(self):
        r = self.client.get("/api/respiratorios/cobertura")
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertIn("neumonias", cuerpo)
        self.assertNotIn("score", cuerpo)
        self.assertIn("52", cuerpo["aviso"])
        self.assertNotIn("M4", cuerpo["aviso"])


class HeatmapNeumoniasTest(unittest.TestCase):
    def setUp(self):
        if not _db_disponible():
            raise unittest.SkipTest("Postgres no disponible")
        self.client = TestClient(app)

    def test_heatmap_2023_14_deptos_hueco_no_cero(self):
        r = self.client.get("/api/neumonias/heatmap/2023")
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual(cuerpo["unidad"], "conteo_notificado")
        self.assertEqual(len(cuerpo["departamentos"]), 14)
        semanas = cuerpo["departamentos"][0]["semanas"]
        self.assertEqual(len(semanas), 52)
        # Al menos un hueco real (vacaciones): no se rellena con 0.
        hay_nulo = any(v is None for v in semanas.values())
        self.assertTrue(hay_nulo)

    def test_heatmap_anio_fuera_de_ventana(self):
        r = self.client.get("/api/neumonias/heatmap/2020")
        self.assertEqual(r.status_code, 400)


class SerieNacionalTableroTest(unittest.TestCase):
    def setUp(self):
        if not _db_disponible():
            raise unittest.SkipTest("Postgres no disponible")
        self.client = TestClient(app)

    def test_serie_nacional_del_tablero(self):
        for ruta in ("/api/ira/nacional", "/api/neumonias/nacional"):
            with self.subTest(ruta=ruta):
                r = self.client.get(ruta)
                self.assertEqual(r.status_code, 200)
                cuerpo = r.json()
                if not cuerpo["disponible"]:
                    # base cargada solo desde el seed, sin capturas del tablero
                    self.assertIn("tablero", cuerpo["motivo"])
                    continue
                self.assertEqual(cuerpo["fuente"], "minsal_tablero")
                self.assertEqual(cuerpo["unidad"], "conteo_notificado")
                semanas = cuerpo["semanas"]
                self.assertGreater(len(semanas), 0)
                fechas = [s["semana_inicio"] for s in semanas]
                self.assertEqual(fechas, sorted(set(fechas)))
                for s in semanas:
                    self.assertGreaterEqual(s["anio"], 2025)
                    self.assertTrue(1 <= s["semana_epi"] <= 53)
                    self.assertGreaterEqual(s["conteo"], 0)


class IraDepartamentalSinFilasTest(unittest.TestCase):
    """Contra Postgres: un departamento sin ninguna fila de IRA sale con
    semanas_con_dato=0. Se crea dentro de una transacción que se revierte,
    así que no deja rastro en la base."""

    def setUp(self):
        if not _db_disponible():
            raise unittest.SkipTest("Postgres no disponible")

    def test_departamento_sin_filas_reporta_cero_semanas(self):
        import psycopg2

        from api.ira import cargar_ira_departamental

        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            database=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            connect_timeout=3,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO regiones (codigo, nombre, nivel_admin) "
                    "VALUES ('ZZ-TEST', 'Prueba sin filas', 1)"
                )
            filas = {f["codigo"]: f for f in cargar_ira_departamental(conn)}
            self.assertEqual(filas["ZZ-TEST"]["semanas_con_dato"], 0)
            self.assertEqual(filas["ZZ-TEST"]["notificado_total"], 0)
            self.assertIsNone(filas["ZZ-TEST"]["primer_anio"])
        finally:
            conn.rollback()
            conn.close()
