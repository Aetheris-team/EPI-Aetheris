"""key_func del rate limiter: de que valor de X-Forwarded-For sale la IP (issue #67).

El edge de Render ANEXA la IP real del cliente al final de X-Forwarded-For.
Tomar el primer valor deja que el cliente se bucketice como una IP distinta en
cada request (mandando la cabecera ya seteada) y evada el rate limiter.
"""
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from starlette.requests import Request  # noqa: E402

import api.main  # noqa: E402


def _request(xff: str | None = None) -> Request:
    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    return Request({"type": "http", "headers": headers, "client": ("10.9.9.9", 5555)})


def test_toma_el_ultimo_hop():
    assert api.main._client_ip(_request("1.2.3.4, 200.0.0.1")) == "200.0.0.1"


def test_un_primer_valor_falsificado_no_cambia_el_bucket():
    a = api.main._client_ip(_request("1.1.1.1, 200.0.0.1"))
    b = api.main._client_ip(_request("9.9.9.9, 200.0.0.1"))
    assert a == b == "200.0.0.1"


def test_sin_cabecera_cae_a_la_ip_del_socket():
    assert api.main._client_ip(_request()) == "10.9.9.9"


def test_cabecera_vacia_cae_a_la_ip_del_socket():
    assert api.main._client_ip(_request("   ")) == "10.9.9.9"


# Produccion: cliente -> Cloudflare de Render -> balanceador de Render -> Uvicorn.
# Con X-Forwarded-For = "<cliente>, <Cloudflare>" y profundidad 2 la IP es la
# del cliente; con la profundidad por defecto (1) seria la de Cloudflare.
CLIENTE = "143.105.123.126"
CLOUDFLARE = "172.71.146.5"


def test_profundidad_por_defecto_toma_la_ip_de_cloudflare(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_DEPTH", raising=False)
    assert api.main._client_ip(_request(f"{CLIENTE}, {CLOUDFLARE}")) == CLOUDFLARE


def test_profundidad_2_toma_la_ip_del_cliente_detras_de_cloudflare(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_DEPTH", "2")
    assert api.main._client_ip(_request(f"{CLIENTE}, {CLOUDFLARE}")) == CLIENTE


def test_profundidad_2_un_prefijo_falsificado_no_cambia_el_bucket(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_DEPTH", "2")
    a = api.main._client_ip(_request(f"1.1.1.1, {CLIENTE}, {CLOUDFLARE}"))
    b = api.main._client_ip(_request(f"9.9.9.9, 8.8.8.8, {CLIENTE}, {CLOUDFLARE}"))
    assert a == b == CLIENTE


def test_menos_saltos_que_la_profundidad_toma_el_primero(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_DEPTH", "2")
    assert api.main._client_ip(_request(CLIENTE)) == CLIENTE


@pytest.mark.parametrize("valor", ["", "abc", "0", "-3", "1.5"])
def test_profundidad_invalida_cae_a_1(monkeypatch, valor):
    monkeypatch.setenv("TRUSTED_PROXY_DEPTH", valor)
    assert api.main._client_ip(_request(f"{CLIENTE}, {CLOUDFLARE}")) == CLOUDFLARE
