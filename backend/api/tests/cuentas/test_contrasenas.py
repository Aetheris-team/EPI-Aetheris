import pytest

from api.cuentas import contrasenas
from api.cuentas.config import ConfigCuentas


def test_hash_y_verificacion(config):
    hash_, version = contrasenas.hashear(config, "una clave bastante larga")
    assert version == 2
    assert hash_.startswith("$argon2id$")
    assert contrasenas.verificar(config, "una clave bastante larga", hash_, version)
    assert not contrasenas.verificar(config, "otra clave bastante larga", hash_, version)


def test_normalizacion_nfkc(config):
    # "ﬁ" (ligadura) y "fi" son la misma contraseña tras NFKC.
    hash_, version = contrasenas.hashear(config, "ﬁnal de la historia")
    assert contrasenas.verificar(config, "final de la historia", hash_, version)


def test_cuenta_inexistente_no_verifica(config):
    assert not contrasenas.verificar(config, "lo que sea que ponga", None, None)


def test_pimienta_desconocida_no_verifica(config):
    hash_, _ = contrasenas.hashear(config, "una clave bastante larga")
    assert not contrasenas.verificar(config, "una clave bastante larga", hash_, 99)


def test_hash_cambia_con_la_pimienta(config):
    hash_, version = contrasenas.hashear(config, "una clave bastante larga")
    otra = ConfigCuentas(
        pimientas={2: b"\x09" * 32}, version_pimienta=2, claves_cifrado=config.claves_cifrado,
        version_cifrado=1, origen_canonico=config.origen_canonico, rp_id=config.rp_id,
    )
    assert not contrasenas.verificar(otra, "una clave bastante larga", hash_, version)


def test_requiere_rehash_si_cambia_la_pimienta_vigente(config):
    hash_, _ = contrasenas.hashear(config, "una clave bastante larga")
    assert contrasenas.requiere_rehash(config, hash_, 1)
    assert not contrasenas.requiere_rehash(config, hash_, 2)


@pytest.mark.parametrize(
    "clave,fragmento",
    [
        ("corta", "al menos 12"),
        ("x" * 129, "no puede pasar de 128"),
        ("aaaaaaaaaaaaaaaa", "repite"),
    ],
)
def test_politica_rechaza(clave, fragmento):
    with pytest.raises(contrasenas.ContrasenaInvalida, match=fragmento):
        contrasenas.validar_politica(clave)


def test_politica_rechaza_datos_personales():
    with pytest.raises(contrasenas.ContrasenaInvalida, match="nombre"):
        contrasenas.validar_politica("MariaLopez-2026-clave", datos_personales=("marialopez",))


def test_politica_acepta_frase_larga():
    assert contrasenas.validar_politica("correcto caballo bateria grapa") == "correcto caballo bateria grapa"


def test_hibp_detecta_sufijo():
    # SHA-1 de "password" = 5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8
    def consulta(prefijo):
        assert prefijo == "5BAA6"
        return "0000000000000000000000000000000000A:0\r\n1E4C9B93F3F0682250B6CF8331B7EE68FD8:3861493\r\n"

    assert contrasenas.esta_filtrada("password", consulta)


def test_hibp_ignora_relleno():
    def consulta(prefijo):
        return "1E4C9B93F3F0682250B6CF8331B7EE68FD8:0\r\n"

    assert not contrasenas.esta_filtrada("password", consulta)


def test_hibp_sin_servicio_no_bloquea():
    def consulta(prefijo):
        raise TimeoutError

    assert not contrasenas.esta_filtrada("password", consulta)


# --- Tope de concurrencia, espera máxima y presupuesto por minuto -------------------------

@pytest.fixture
def limpio(monkeypatch):
    """Estado del límite en cero, sin depender de otras pruebas ni del reloj."""
    monkeypatch.setattr(contrasenas, "_en_curso", 0)
    monkeypatch.setattr(contrasenas, "_fichas", float(contrasenas.RAFAGA_MAX))
    monkeypatch.setattr(contrasenas, "COLA_MAX", 2)
    monkeypatch.setattr(contrasenas, "ESPERA_MAX_S", 0.3)
    monkeypatch.setattr(contrasenas, "POR_MINUTO_MAX", 0)


class _HasherFalso:
    """PasswordHasher usa __slots__ y no deja reemplazar verify."""

    def __init__(self, verificar):
        self.verify = verificar


def _retener_turnos(monkeypatch, config, cuantos):
    """Lanza `cuantos` verificaciones que se quedan dentro del cálculo hasta que
    se suelte el evento. Devuelve (soltar, hilos)."""
    import threading

    dentro = threading.Semaphore(0)
    soltar = threading.Event()

    def lento(*_a, **_k):
        dentro.release()
        soltar.wait(5)
        return False

    monkeypatch.setattr(contrasenas, "_hasher", _HasherFalso(lento))
    hilos = [
        threading.Thread(target=lambda: contrasenas.verificar(config, "x" * 14, "$argon2id$h", 2))
        for _ in range(cuantos)
    ]
    return soltar, dentro, hilos


def test_lo_que_no_cabe_en_la_cola_se_rechaza_sin_esperar(limpio, monkeypatch, config):
    import time

    monkeypatch.setattr(contrasenas, "ESPERA_MAX_S", 30.0)
    hash_, version = contrasenas.hashear(config, "una clave bastante larga")
    capacidad = contrasenas.PARALELAS + contrasenas.COLA_MAX
    soltar, dentro, hilos = _retener_turnos(monkeypatch, config, capacidad)
    for h in hilos:
        h.start()
    for _ in range(contrasenas.PARALELAS):
        assert dentro.acquire(timeout=3)
    # Los dos primeros calculan y el resto espera en la cola: está llena.
    while contrasenas._en_curso < capacidad:
        time.sleep(0.01)
    inicio = time.monotonic()
    with pytest.raises(contrasenas.Saturado) as info:
        contrasenas.verificar(config, "una clave bastante larga", hash_, version)
    assert time.monotonic() - inicio < 0.5
    assert info.value.espera_s >= 1
    with pytest.raises(contrasenas.Saturado):
        contrasenas.comprobar_cupo()
    soltar.set()
    for h in hilos:
        h.join(5)
    assert contrasenas._en_curso == 0
    contrasenas.comprobar_cupo()  # vuelve a haber cupo


def test_la_espera_por_un_turno_tiene_tope(limpio, monkeypatch, config):
    import time

    monkeypatch.setattr(contrasenas, "COLA_MAX", 10)
    soltar, dentro, hilos = _retener_turnos(monkeypatch, config, contrasenas.PARALELAS)
    for h in hilos:
        h.start()
    for _ in range(contrasenas.PARALELAS):
        assert dentro.acquire(timeout=3)
    inicio = time.monotonic()
    with pytest.raises(contrasenas.Saturado):
        contrasenas.verificar(config, "una clave bastante larga", None, None)
    transcurrido = time.monotonic() - inicio
    assert 0.25 <= transcurrido < 1.5
    soltar.set()
    for h in hilos:
        h.join(5)
    assert contrasenas._en_curso == 0


def test_presupuesto_global_con_rafaga_y_recarga(limpio, monkeypatch, config):
    reloj = {"t": 1000.0}
    monkeypatch.setattr(contrasenas.time, "monotonic", lambda: reloj["t"])
    monkeypatch.setattr(contrasenas, "_ultima_recarga", reloj["t"])
    monkeypatch.setattr(contrasenas, "POR_MINUTO_MAX", 60)  # una por segundo
    monkeypatch.setattr(contrasenas, "RAFAGA_MAX", 3)
    monkeypatch.setattr(contrasenas, "_fichas", 3.0)
    monkeypatch.setattr(contrasenas, "_hasher", _HasherFalso(lambda *_a, **_k: False))
    for _ in range(3):
        assert not contrasenas.verificar(config, "una clave bastante larga", "$argon2id$h", 2)
    with pytest.raises(contrasenas.Saturado) as info:
        contrasenas.verificar(config, "una clave bastante larga", "$argon2id$h", 2)
    assert info.value.espera_s == 2  # falta una ficha entera a una por segundo
    reloj["t"] += 1.5
    assert not contrasenas.verificar(config, "una clave bastante larga", "$argon2id$h", 2)
    with pytest.raises(contrasenas.Saturado):
        contrasenas.verificar(config, "una clave bastante larga", "$argon2id$h", 2)
    reloj["t"] += 600  # nunca pasa de la ráfaga
    for _ in range(3):
        contrasenas.verificar(config, "una clave bastante larga", "$argon2id$h", 2)
    with pytest.raises(contrasenas.Saturado):
        contrasenas.verificar(config, "una clave bastante larga", "$argon2id$h", 2)


def test_cuenta_inexistente_gasta_el_mismo_turno_y_presupuesto(limpio, monkeypatch, config):
    monkeypatch.setattr(contrasenas, "POR_MINUTO_MAX", 2)
    monkeypatch.setattr(contrasenas, "_fichas", 2.0)
    monkeypatch.setattr(contrasenas, "RAFAGA_MAX", 2)
    assert not contrasenas.verificar(config, "una clave bastante larga", None, None)
    assert not contrasenas.verificar(config, "una clave bastante larga", None, None)
    with pytest.raises(contrasenas.Saturado):
        contrasenas.verificar(config, "una clave bastante larga", None, None)


def test_un_rechazo_no_gasta_presupuesto_ni_deja_cuenta_abierta(limpio, monkeypatch, config):
    monkeypatch.setattr(contrasenas, "_en_curso", contrasenas.PARALELAS + contrasenas.COLA_MAX)
    antes = contrasenas._fichas
    with pytest.raises(contrasenas.Saturado):
        contrasenas.verificar(config, "una clave bastante larga", None, None)
    assert contrasenas._fichas >= antes
    assert contrasenas._en_curso == contrasenas.PARALELAS + contrasenas.COLA_MAX
