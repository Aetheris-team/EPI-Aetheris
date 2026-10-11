
import pytest

from api.cuentas import cli, servicio

from .conftest_http import ConexionCompartida

@pytest.fixture
def conn(conn):
    """La CLI confirma su transacción; aquí el commit no hace nada y el fixture
    base deshace todo al terminar."""
    return ConexionCompartida(conn)


@pytest.fixture
def entorno(monkeypatch, config):
    import base64

    def b64(b):
        return base64.urlsafe_b64encode(b).decode()

    monkeypatch.setenv("AUTH_PEPPERS", f"1:{b64(b'a' * 32)}")
    monkeypatch.setenv("AUTH_CLAVES_CIFRADO", f"1:{b64(b'b' * 32)}")
    monkeypatch.setenv("AUTH_ORIGEN_CANONICO", "https://epi-aetheris.dev")
    monkeypatch.setenv("AUTH_HIBP", "false")

def test_crear_admin_imprime_el_enlace_una_vez(conn, entorno, capsys):
    assert cli.main(["crear-admin", "--correo", "primera@ejemplo.org"], conn=conn) == 0
    salida = capsys.readouterr().out
    enlace = [l for l in salida.splitlines() if "#t=" in l][0]
    assert enlace.startswith("https://epi-aetheris.dev/cuenta/aceptar#t=")
    token = enlace.split("#t=")[1]
    info = servicio.ver_invitacion(conn, token)
    assert info["roles"] == ["administrador"] and info["correo"] == "primera@ejemplo.org"
    with conn.cursor() as cur:
        cur.execute("SELECT actor_tipo FROM auditoria WHERE accion = 'invitacion_creada' ORDER BY id DESC LIMIT 1")
        assert cur.fetchone()[0] == "sistema"
        # El enlace no queda en ninguna tabla.
        cur.execute("SELECT count(*) FROM auditoria WHERE detalle::text LIKE %s", (f"%{token}%",))
        assert cur.fetchone()[0] == 0

def test_crear_admin_con_correo_ya_registrado(conn, entorno, crear_usuario, capsys):
    crear_usuario()
    assert cli.main(["crear-admin", "--correo", "persona1@ejemplo.org"], conn=conn) == 1
    assert "Ya existe" in capsys.readouterr().err

def test_restablecer_factores_por_consola(conn, config, entorno, crear_usuario, capsys):
    uid = crear_usuario(roles=("publicador",))
    assert cli.main(["restablecer-factores", "--correo", "persona1@ejemplo.org", "--motivo", "Perdió el teléfono"], conn=conn) == 0
    with conn.cursor() as cur:
        cur.execute("SELECT estado FROM usuarios WHERE id = %s", (uid,))
        assert cur.fetchone()[0] == "invitado"
        cur.execute("SELECT actor_tipo FROM auditoria WHERE accion = 'factores_restablecidos' ORDER BY id DESC LIMIT 1")
        assert cur.fetchone()[0] == "sistema"

def test_restablecer_factores_de_un_administrador_por_consola_no_necesita_aprobacion(conn, entorno, crear_usuario):
    # Es la salida cuando no hay otro administrador que apruebe: la consola exige acceso a la base.
    uid = crear_usuario(roles=("administrador",))
    assert cli.main(["restablecer-factores", "--correo", "persona1@ejemplo.org", "--motivo", "Único administrador, sin quien apruebe"], conn=conn) == 0
    with conn.cursor() as cur:
        cur.execute("SELECT actor_tipo FROM auditoria WHERE accion = 'factores_restablecidos' AND objeto_id = %s", (uid,))
        assert cur.fetchone()[0] == "sistema"

def test_restablecer_factores_cuenta_inexistente(conn, entorno, capsys):
    assert cli.main(["restablecer-factores", "--correo", "nadie@ejemplo.org", "--motivo", "x"], conn=conn) == 1

def test_verificar_auditoria(conn, entorno, capsys):
    assert cli.main(["verificar-auditoria"], conn=conn) == 0
    assert "íntegra" in capsys.readouterr().out
