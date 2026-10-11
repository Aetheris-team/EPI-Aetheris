"""Contraseñas: normalización, hash con Argon2id y pimienta, y consulta de
filtraciones.

La contraseña se normaliza (NFKC), se pasa por HMAC-SHA256 con la pimienta
vigente y el resultado se entrega a Argon2id. Quien robe solo la base no puede
probar contraseñas sin la pimienta, que vive en el entorno de Render.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
import unicodedata
import urllib.request
from contextlib import contextmanager
from typing import Callable

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import ConfigCuentas

LARGO_MIN = 12
LARGO_MAX = 128

# Parámetros de OWASP para Argon2id: 19 MiB, 2 iteraciones, 1 hilo.
_hasher = PasswordHasher(
    time_cost=2, memory_cost=19456, parallelism=1, hash_len=32, salt_len=16, type=Type.ID
)

# Con 19 MiB por hash, un grupo de peticiones de ingreso simultáneas agota la
# memoria del servicio. Se calculan de dos en dos.
PARALELAS = 2
_semaforo = threading.BoundedSemaphore(PARALELAS)


def _entero_env(nombre: str, defecto: int) -> int:
    try:
        return max(0, int(os.getenv(nombre, str(defecto))))
    except ValueError:
        return defecto


# Cada petición que espera su turno ocupa un hilo del grupo compartido con el
# resto de la API y una conexión del pool de Postgres. Sin tope, quien reparta
# intentos entre muchas IP llena ambos y deja sin servicio las lecturas
# públicas. Por eso la espera es corta y la cola, pequeña: lo que no cabe se
# rechaza al instante con 503 y Retry-After (ADR 0024).
COLA_MAX = _entero_env("AUTH_HASH_COLA", 2)
ESPERA_MAX_S = float(_entero_env("AUTH_HASH_ESPERA_S", 2))
# Tope global de hashes por minuto en este proceso, sea cual sea la IP de
# origen, con una ráfaga corta. Acota la CPU que puede consumir el ingreso:
# el límite por IP y el de cuenta no lo hacen cuando los intentos vienen de
# muchas IP y correos. La ráfaga es corta para que el cupo no se gaste de
# golpe y deje al proceso sin CPU para el resto de la API.
POR_MINUTO_MAX = _entero_env("AUTH_HASH_POR_MINUTO", 120)
RAFAGA_MAX = _entero_env("AUTH_HASH_RAFAGA", 10)

_cerrojo = threading.Lock()
_en_curso = 0
_fichas = float(RAFAGA_MAX)
_ultima_recarga = time.monotonic()


class Saturado(RuntimeError):
    """No hay cupo para calcular otro hash ahora. No cuenta como intento fallido."""

    def __init__(self, espera_s: float):
        super().__init__("Verificación de contraseñas saturada")
        self.espera_s = max(1, int(espera_s))


def _recargar(ahora: float) -> None:
    global _fichas, _ultima_recarga
    if POR_MINUTO_MAX:
        _fichas = min(float(RAFAGA_MAX), _fichas + (ahora - _ultima_recarga) * POR_MINUTO_MAX / 60)
    _ultima_recarga = ahora


def _comprobar_hueco(ahora: float) -> None:
    """Lanza Saturado si el tope de cola o el presupuesto de hashes están
    agotados. Se llama con el cerrojo tomado."""
    _recargar(ahora)
    if _en_curso >= PARALELAS + COLA_MAX:
        raise Saturado(ESPERA_MAX_S)
    if POR_MINUTO_MAX and _fichas < 1:
        raise Saturado((1 - _fichas) * 60 / POR_MINUTO_MAX + 1)


def comprobar_cupo() -> None:
    """Rechazo barato antes de abrir conexión ni consultar nada. No reserva
    nada: la reserva real ocurre al calcular el hash."""
    with _cerrojo:
        _comprobar_hueco(time.monotonic())


@contextmanager
def _turno():
    """Reserva un turno de cálculo o lanza Saturado sin esperar más de
    ESPERA_MAX_S."""
    global _en_curso, _fichas
    with _cerrojo:
        _comprobar_hueco(time.monotonic())
        _en_curso += 1
    try:
        if not _semaforo.acquire(timeout=ESPERA_MAX_S):
            raise Saturado(ESPERA_MAX_S)
        try:
            with _cerrojo:
                _fichas -= 1
            yield
        finally:
            _semaforo.release()
    finally:
        with _cerrojo:
            _en_curso -= 1


# Hash de una contraseña que nadie conoce. Se verifica contra él cuando la
# cuenta no existe, para que el tiempo de respuesta no delate qué correos
# tienen cuenta.
_HASH_FICTICIO = _hasher.hash(hashlib.sha256(b"epi-aetheris-sin-cuenta").hexdigest())


class ContrasenaInvalida(ValueError):
    """La contraseña no cumple la política. El mensaje se puede mostrar."""


def normalizar(contrasena: str) -> str:
    return unicodedata.normalize("NFKC", contrasena)


def validar_politica(contrasena: str, *, datos_personales: tuple[str, ...] = ()) -> str:
    """Devuelve la contraseña normalizada o lanza ContrasenaInvalida.

    La política es de longitud y de rechazo de lo evidente; no exige mezclas de
    símbolos, que empujan a patrones previsibles."""
    normal = normalizar(contrasena)
    if len(normal) < LARGO_MIN:
        raise ContrasenaInvalida(f"La contraseña debe tener al menos {LARGO_MIN} caracteres.")
    if len(normal) > LARGO_MAX:
        raise ContrasenaInvalida(f"La contraseña no puede pasar de {LARGO_MAX} caracteres.")
    if len(set(normal)) < 5:
        raise ContrasenaInvalida("La contraseña repite demasiado los mismos caracteres.")
    bajas = normal.lower()
    for dato in datos_personales:
        dato = dato.strip().lower()
        if len(dato) >= 4 and dato in bajas:
            raise ContrasenaInvalida("La contraseña no puede contener tu nombre ni tu correo.")
    return normal


def _prehash(normal: str, pimienta: bytes) -> str:
    return hmac.new(pimienta, normal.encode("utf-8"), hashlib.sha256).hexdigest()


def hashear(config: ConfigCuentas, contrasena: str) -> tuple[str, int]:
    """Devuelve (hash, versión de pimienta)."""
    normal = normalizar(contrasena)
    with _turno():
        return _hasher.hash(_prehash(normal, config.pimienta_vigente)), config.version_pimienta


def verificar(config: ConfigCuentas, contrasena: str, hash_guardado: str | None, version: int | None) -> bool:
    """Compara en tiempo comparable exista o no la cuenta."""
    normal = normalizar(contrasena)
    pimienta = config.pimientas.get(version) if version is not None else None
    with _turno():
        if hash_guardado is None or pimienta is None:
            try:
                _hasher.verify(_HASH_FICTICIO, _prehash(normal, config.pimienta_vigente))
            except (VerificationError, InvalidHashError):
                pass
            return False
        try:
            return _hasher.verify(hash_guardado, _prehash(normal, pimienta))
        except VerifyMismatchError:
            return False
        except (VerificationError, InvalidHashError):
            return False


def requiere_rehash(config: ConfigCuentas, hash_guardado: str, version: int) -> bool:
    """Hay que volver a calcular el hash tras un ingreso correcto cuando cambió
    la pimienta vigente o los parámetros de Argon2."""
    return version != config.version_pimienta or _hasher.check_needs_rehash(hash_guardado)


# --- Contraseñas filtradas (Have I Been Pwned, rangos) --------------------

def _consultar_rango(prefijo: str) -> str:
    peticion = urllib.request.Request(
        f"https://api.pwnedpasswords.com/range/{prefijo}",
        headers={"Add-Padding": "true", "User-Agent": "epi-aetheris-cuentas"},
    )
    with urllib.request.urlopen(peticion, timeout=3) as respuesta:  # noqa: S310 - URL fija
        return respuesta.read().decode("ascii")


def esta_filtrada(contrasena: str, consulta: Callable[[str], str] = _consultar_rango) -> bool:
    """True si la contraseña aparece en filtraciones conocidas.

    Solo salen los primeros 5 caracteres del SHA-1 (k-anonimato) y la
    respuesta lleva relleno para que su tamaño no revele nada. Si el servicio
    no responde se acepta la contraseña: la política de longitud sigue
    aplicando y el alta no puede depender de un tercero."""
    sha1 = hashlib.sha1(normalizar(contrasena).encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    prefijo, sufijo = sha1[:5], sha1[5:]
    try:
        cuerpo = consulta(prefijo)
    except Exception:
        return False
    for linea in cuerpo.splitlines():
        candidato, _, repeticiones = linea.partition(":")
        if candidato.strip() == sufijo and repeticiones.strip() not in ("", "0"):
            return True
    return False
