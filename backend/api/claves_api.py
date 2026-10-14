"""Claves de API para límites de peticiones más altos (ADR 0025).

La API sigue abierta sin clave. Quien manda una clave válida en la cabecera
``X-API-Key`` recibe un contador propio (no el de su IP) con los umbrales
``RATE_LIMIT_CLAVE_DEFAULT`` y ``RATE_LIMIT_CLAVE_HEAVY`` en lugar de los
anónimos. Está pensada para scripts y notebooks del equipo, no para el
navegador: la cabecera no figura en ``allow_headers`` de CORS, así que el
frontend no puede mandarla.

El entorno guarda el SHA-256 de cada clave, no la clave: ``API_CLAVES`` es una
lista ``nombre:sha256hex`` separada por comas. El nombre identifica el
contador y aparece en el log de slowapi cuando se supera un límite; nunca se
registra la clave.

slowapi solo resuelve límites dependientes de la clave en las rutas
decoradas, no en ``default_limits``. Por eso la validación ocurre en un
middleware ASGI por fuera de ``SlowAPIMiddleware``, que deja el nombre en un
``ContextVar``; la ``key_func`` y los proveedores de límite lo leen de ahí.
"""
import hashlib
import json
import re
import secrets
from contextvars import ContextVar

CABECERA_CLAVE = "x-api-key"

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_NOMBRE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

# Nombre de la clave válida del request en curso; None = anónimo.
clave_actual: ContextVar[str | None] = ContextVar("clave_api_actual", default=None)


def parsear_claves(valor: str | None) -> dict[str, str]:
    """``"nombre:sha256hex,..."`` -> {sha256hex: nombre}.

    Una entrada mal formada detiene el arranque: una clave que se ignora en
    silencio deja a su dueño con los límites anónimos sin pista del motivo.
    """
    claves: dict[str, str] = {}
    for entrada in (valor or "").split(","):
        entrada = entrada.strip()
        if not entrada:
            continue
        nombre, separador, huella = entrada.partition(":")
        nombre, huella = nombre.strip(), huella.strip().lower()
        if not separador or not _NOMBRE.match(nombre) or not _SHA256_HEX.match(huella):
            raise ValueError(
                "API_CLAVES mal formada: cada entrada es nombre:sha256hex "
                "(nombre con letras, dígitos, '.', '_' o '-'; 64 hex)."
            )
        if nombre in claves.values():
            raise ValueError(f"API_CLAVES repite el nombre {nombre!r}.")
        claves[huella] = nombre
    return claves


def identificar(clave: str, claves: dict[str, str]) -> str | None:
    """Nombre de la clave si es válida, None si no.

    Compara contra todas las huellas con ``compare_digest`` para no revelar
    por tiempo cuál coincide.
    """
    huella = hashlib.sha256(clave.encode("utf-8")).hexdigest()
    encontrada = None
    for registrada, nombre in claves.items():
        if secrets.compare_digest(huella, registrada):
            encontrada = nombre
    return encontrada


class ClaveApiMiddleware:
    """Valida ``X-API-Key`` y fija ``clave_actual`` para el resto del request.

    Sin cabecera: anónimo, límites por IP. Cabecera con clave desconocida:
    401, en vez de tratarla como anónima, para que un error de copia no se
    confunda con un 429 más.
    """

    def __init__(self, app, claves: dict[str, str]):
        self.app = app
        self.claves = claves

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        recibida = None
        for nombre, valor in scope.get("headers", []):
            if nombre == CABECERA_CLAVE.encode():
                recibida = valor.decode("latin-1").strip()
                break
        if recibida is None or recibida == "":
            await self.app(scope, receive, send)
            return
        nombre_clave = identificar(recibida, self.claves)
        if nombre_clave is None:
            await _responder_401(send)
            return
        token = clave_actual.set(nombre_clave)
        try:
            await self.app(scope, receive, send)
        finally:
            clave_actual.reset(token)


async def _responder_401(send) -> None:
    cuerpo = json.dumps({"detail": "Clave de API no válida."}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(cuerpo)).encode()),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": cuerpo})
