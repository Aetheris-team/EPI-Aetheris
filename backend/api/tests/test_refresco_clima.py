"""POST /internal/clima/refrescar: autenticación y encolado (ADR 0027)."""

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import main
from api import rutas

RUTA = "/internal/clima/refrescar"
TOKEN = "token-de-prueba"


class RefrescoClimaTest(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)
        main.limiter.reset()

    def _post(self, cabeceras=None):
        return self.cliente.post(RUTA, headers=cabeceras or {})

    def test_sin_token_configurado_503(self):
        with patch.dict(os.environ, {"CLIMA_REFRESCO_TOKEN": ""}):
            self.assertEqual(self._post().status_code, 503)

    def test_token_ausente_o_incorrecto_401_y_no_encola(self):
        with patch.dict(os.environ, {"CLIMA_REFRESCO_TOKEN": TOKEN}), patch.object(
            rutas.clima, "ejecutar_refresco_clima"
        ) as ejecutar:
            self.assertEqual(self._post().status_code, 401)
            otro = {"Authorization": "Bearer otro"}
            self.assertEqual(self._post(otro).status_code, 401)
        ejecutar.assert_not_called()

    def test_token_correcto_202_y_encola(self):
        with patch.dict(os.environ, {"CLIMA_REFRESCO_TOKEN": TOKEN}), patch.object(
            rutas.clima, "ejecutar_refresco_clima"
        ) as ejecutar:
            r = self._post({"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.headers["Cache-Control"], "no-store")
        ejecutar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
