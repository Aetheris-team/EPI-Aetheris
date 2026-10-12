"""Roles de base de datos separados (ADR 0024, punto E; migración 0018).

Crea una base temporal y un rol de aplicación temporal en el Postgres de las
pruebas, aplica todas las migraciones como propietario y comprueba, conectado
como ese rol, que:

* no puede modificar ni borrar la auditoría, ni alterar el esquema, ni apagar
  los disparadores que la protegen;
* sí puede todo lo que hace la API, ejecutando la suite de cuentas y la de
  alertas con ese rol.

Los roles son globales al servidor, así que los nombres llevan un sufijo
aleatorio y se eliminan al terminar. La contraseña se genera en cada corrida y
no se escribe en ningún archivo. Sin Postgres con permiso para crear bases y
roles (fuera de CI) las pruebas se omiten.
"""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest
from psycopg2 import sql

_RAIZ = Path(__file__).resolve().parents[3]
_MIGRACIONES = _RAIZ / "db" / "migrations"
_BACKEND = _RAIZ / "backend"

PRIVILEGIOS = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")

_SELECT = {"SELECT"}
_ESCRIBE = {"SELECT", "INSERT", "UPDATE"}
_BORRA = {"SELECT", "INSERT", "UPDATE", "DELETE"}
# Cada tabla del esquema debe estar aquí: una tabla nueva sin clasificar hace
# fallar la prueba y obliga a decidir qué privilegios recibe la API.
ESPERADO: dict[str, set[str]] = {
    "regiones": _SELECT,
    "tipos_evento": _SELECT,
    "fuentes_datos": _SELECT,
    "semanas_epidemiologicas": _SELECT,
    "casos_epidemiologicos": _SELECT,
    "variables_ambientales": _SELECT,
    "boletines_procesados": _SELECT,
    "vigilancia_virus_respiratorios": _SELECT,
    "alertas": _ESCRIBE,
    "instituciones": _ESCRIBE,
    "usuarios": _ESCRIBE,
    "usuarios_roles": _ESCRIBE,
    "credenciales_clave": _ESCRIBE,
    "codigos_recuperacion": _ESCRIBE,
    "invitaciones": _ESCRIBE,
    "tokens_un_solo_uso": _ESCRIBE,
    "sesiones": _ESCRIBE,
    "desafios": _ESCRIBE,
    "correos_salientes": _ESCRIBE,
    "factores_autenticacion": _BORRA,
    "intentos_ingreso": _BORRA,
    "auditoria": {"SELECT", "INSERT"},
    # La crea la migración de aprobaciones administrativas (rama
    # fix/restablecer-factor-doble-aprobacion). Se comprueba solo si existe;
    # al integrarse las dos ramas pasa a ser obligatoria.
    "aprobaciones_administrativas": _ESCRIBE,
}
OPCIONALES = {"aprobaciones_administrativas"}


def _conectar(base: str, usuario: str | None = None, clave: str | None = None):
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=base,
        user=usuario or os.getenv("POSTGRES_USER", "aetheris_user"),
        password=clave if clave is not None else os.getenv("POSTGRES_PASSWORD", "aetheris_ci_password"),
        connect_timeout=3,
    )


def _archivos_migracion() -> list[Path]:
    return [
        p for p in sorted(_MIGRACIONES.glob("*.sql"))
        if re.match(r"^\d{4}_.+\.sql$", p.name) and p.stat().st_size > 0
    ]


@pytest.fixture(scope="module")
def entorno():
    """Base temporal con todas las migraciones y el rol de aplicación creado."""
    try:
        admin = _conectar(os.getenv("POSTGRES_DB", "epi_aetheris"))
    except psycopg2.OperationalError:
        if os.getenv("CI"):
            raise
        pytest.skip("Sin Postgres para las pruebas de roles")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute("SELECT rolcreaterole AND rolcreatedb OR rolsuper FROM pg_roles WHERE rolname = current_user")
        if not cur.fetchone()[0]:
            admin.close()
            if os.getenv("CI"):
                pytest.fail("El usuario de CI debe poder crear bases y roles")
            pytest.skip("El usuario de pruebas no puede crear bases ni roles")

    sufijo = secrets.token_hex(4)
    base = f"epi_roles_{sufijo}"
    rol = f"epi_app_{sufijo}"
    clave = secrets.token_urlsafe(24)
    creada_base = creado_rol = False
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(base)))
            creada_base = True
            cur.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(rol), sql.Literal(clave))
            )
            creado_rol = True

        propietario = _conectar(base)
        propietario.autocommit = True
        try:
            with propietario.cursor() as cur:
                for archivo in _archivos_migracion():
                    cur.execute(archivo.read_text())
        finally:
            propietario.close()

        yield {"base": base, "rol": rol, "clave": clave}
    finally:
        with admin.cursor() as cur:
            if creada_base:
                cur.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(base)))
            if creado_rol:
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(rol)))
        admin.close()


@pytest.fixture(scope="module")
def con_privilegios(entorno):
    """Aplica los privilegios como lo hace el runner de migraciones."""
    propietario = _conectar(entorno["base"])
    try:
        with propietario.cursor() as cur:
            cur.execute("SELECT aplicar_privilegios_roles(%s)", (entorno["rol"],))
            assert cur.fetchone()[0] is True
        propietario.commit()
    finally:
        propietario.close()
    return entorno


@pytest.fixture
def app(con_privilegios):
    """Conexión como el rol de aplicación. Todo se deshace al terminar."""
    conexion = _conectar(con_privilegios["base"], con_privilegios["rol"], con_privilegios["clave"])
    try:
        yield conexion
    finally:
        conexion.rollback()
        conexion.close()


def _denegado(conexion, consulta: str, *args) -> str:
    """Ejecuta `consulta` y devuelve el mensaje del error de privilegios."""
    with conexion.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege) as exc:
            cur.execute(consulta, args or None)
    conexion.rollback()
    return str(exc.value)


# --- el rol inexistente no rompe la migración -----------------------------------

def test_sin_el_rol_la_funcion_avisa_y_no_concede_nada(entorno):
    propietario = _conectar(entorno["base"])
    try:
        with propietario.cursor() as cur:
            cur.execute("SELECT aplicar_privilegios_roles('rol_que_no_existe_jamas')")
            assert cur.fetchone()[0] is False
    finally:
        propietario.rollback()
        propietario.close()


# --- matriz de privilegios -------------------------------------------------------

def test_cada_tabla_esta_clasificada(con_privilegios):
    propietario = _conectar(con_privilegios["base"])
    try:
        with propietario.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            existentes = {f[0] for f in cur.fetchall()}
    finally:
        propietario.close()
    faltan = set(ESPERADO) - OPCIONALES - existentes
    sin_clasificar = existentes - set(ESPERADO)
    assert not faltan and not sin_clasificar, (
        "Tablas sin clasificar en db/migrations/0018 y en esta prueba, o clasificadas y ausentes: "
        f"{sorted(sin_clasificar | faltan)}"
    )


def test_matriz_de_privilegios_de_tablas(app):
    with app.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        existentes = {f[0] for f in cur.fetchall()}
        for tabla, permitidos in ESPERADO.items():
            if tabla not in existentes:
                continue
            for priv in PRIVILEGIOS:
                cur.execute("SELECT has_table_privilege(current_user, %s, %s)", (f"public.{tabla}", priv))
                assert cur.fetchone()[0] == (priv in permitidos), f"{priv} sobre {tabla}"


def test_el_rol_no_es_superusuario_ni_crea_nada(app):
    with app.cursor() as cur:
        cur.execute(
            "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication "
            "FROM pg_roles WHERE rolname = current_user"
        )
        assert cur.fetchone() == (False, False, False, False, False)
        cur.execute("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
        assert cur.fetchone()[0] is False


# --- la auditoría no se puede reescribir ----------------------------------------

def test_auditoria_acepta_insercion_y_lectura(app):
    with app.cursor() as cur:
        cur.execute(
            "INSERT INTO auditoria (categoria, actor_tipo, accion) VALUES ('sistema', 'sistema', 'prueba_roles')"
        )
        cur.execute("SELECT auditoria_verificar()")
        assert cur.fetchone()[0] is None
        cur.execute("SELECT count(*) FROM auditoria WHERE accion = 'prueba_roles'")
        assert cur.fetchone()[0] == 1


@pytest.mark.parametrize(
    "consulta",
    [
        "UPDATE auditoria SET accion = 'otra'",
        "DELETE FROM auditoria",
        "TRUNCATE auditoria",
        "TRUNCATE auditoria, usuarios CASCADE",
    ],
)
def test_auditoria_no_se_modifica_ni_se_borra(app, consulta):
    # El mensaje debe ser el de privilegios de tabla, no el de la excepción del
    # disparador: el rol ni siquiera llega a ejecutar el disparador.
    assert "permission denied for table" in _denegado(app, consulta)


# --- el esquema no se altera ------------------------------------------------------

@pytest.mark.parametrize(
    "consulta, fragmento",
    [
        ("CREATE TABLE intruso (id int)", "permission denied for schema public"),
        ("CREATE FUNCTION f() RETURNS int AS 'SELECT 1' LANGUAGE sql", "permission denied for schema public"),
        ("ALTER TABLE usuarios ADD COLUMN x int", "must be owner"),
        ("DROP TABLE auditoria", "must be owner"),
        ("DROP TABLE alertas", "must be owner"),
        ("DROP TRIGGER auditoria_sin_cambios ON auditoria", "must be owner"),
        ("DROP TRIGGER auditoria_sin_truncar ON auditoria", "must be owner"),
        ("DROP TRIGGER auditoria_encadenado ON auditoria", "must be owner"),
        ("ALTER TABLE auditoria DISABLE TRIGGER ALL", "must be owner"),
        ("ALTER TABLE auditoria DISABLE TRIGGER auditoria_sin_cambios", "must be owner"),
        ("ALTER TABLE auditoria ENABLE REPLICA TRIGGER auditoria_sin_cambios", "must be owner"),
        ("CREATE OR REPLACE FUNCTION auditoria_inmutable() RETURNS trigger AS 'BEGIN RETURN NULL; END;' LANGUAGE plpgsql",
         "permission denied for schema public"),
        ("DROP FUNCTION auditoria_contenido_hash(bytea,bigint,timestamptz,text,text,uuid,uuid,text,text,text,jsonb,text)",
         "must be owner"),
        ("ALTER SEQUENCE auditoria_id_seq RESTART WITH 1", "must be owner"),
        ("SET session_replication_role = replica", "permission denied"),
        ("SELECT aplicar_privilegios_roles()", "permission denied for function"),
    ],
)
def test_el_esquema_no_se_altera(app, consulta, fragmento):
    assert fragmento in _denegado(app, consulta)


def test_no_puede_leer_el_registro_de_migraciones_ni_crear_el_suyo(app):
    # schema_migrations la crea el runner, no una migración; si existiera, la API tampoco debería leerla.
    assert "permission denied for schema public" in _denegado(app, "CREATE TABLE schema_migrations (x int)")


# --- lo que la API necesita --------------------------------------------------------

def test_flujo_de_escritura_de_cuentas_con_el_rol_de_aplicacion(app):
    """Un recorrido mínimo, sin Argon2 ni correo, de lo que hace la API."""
    with app.cursor() as cur:
        cur.execute(
            "INSERT INTO usuarios (correo, nombre_visible, estado, correo_verificado_en, terminos_version, "
            "terminos_aceptados_en) VALUES ('p@ejemplo.org', 'Persona Prueba', 'activo', now(), 'v1', now()) "
            "RETURNING id"
        )
        uid = cur.fetchone()[0]
        cur.execute("INSERT INTO usuarios_roles (usuario_id, rol) VALUES (%s, 'publicador') RETURNING id", (uid,))
        cur.execute("UPDATE usuarios_roles SET revocado_en = now() WHERE usuario_id = %s", (uid,))
        cur.execute(
            "INSERT INTO factores_autenticacion (usuario_id, tipo, etiqueta, totp_secreto_cifrado, totp_clave_version) "
            "VALUES (%s, 'totp', 'Teléfono', '\\x00', 1)", (uid,),
        )
        cur.execute("DELETE FROM factores_autenticacion WHERE usuario_id = %s", (uid,))
        cur.execute("INSERT INTO correos_salientes (plantilla, destinatario) VALUES ('x', 'p@ejemplo.org') RETURNING id")
        cur.execute("SELECT pg_advisory_xact_lock(1)")
        cur.execute("INSERT INTO instituciones (nombre, tipo) VALUES ('Inst', 'otro') RETURNING id")
        cur.execute(
            "INSERT INTO alertas (tipo, nivel, titulo, contexto, indicaciones, fuente, autor, vigente_desde) "
            "VALUES ('dengue', 'informativo', 't', 'c', 'i', 'f', 'a', current_date) RETURNING id"
        )
        cur.execute("SELECT count(*) FROM casos_epidemiologicos")
    # Las tablas de datos son de solo lectura para la API.
    assert "permission denied for table" in _denegado(app, "DELETE FROM casos_epidemiologicos")
    assert "permission denied for table" in _denegado(app, "INSERT INTO regiones (codigo, nombre) VALUES ('x', 'y')")
    # Y la API no borra usuarios ni alertas.
    assert "permission denied for table" in _denegado(app, "DELETE FROM usuarios")
    assert "permission denied for table" in _denegado(app, "DELETE FROM alertas")


@pytest.mark.parametrize(
    "objetivos, api_por_url",
    [
        (["api/tests/cuentas"], False),
        (["api/tests/test_cuentas_integracion.py"], False),
        (["api/tests/test_endpoints_alertas.py"], True),
    ],
    ids=["suite_de_cuentas", "integracion_de_cuentas", "alertas_por_database_url"],
)
def test_suites_reales_con_el_rol_de_aplicacion(con_privilegios, objetivos, api_por_url):
    """Corre las suites existentes conectadas como el rol de aplicación.

    Las suites de cuentas leen POSTGRES_* y deshacen sus cambios con rollback,
    así que basta apuntarlas a la base temporal con las credenciales del rol.
    La de alertas prepara y limpia sus filas con DELETE (el rol de la API no
    borra alertas) y llama a la API, así que ahí las POSTGRES_* siguen siendo
    las del propietario y la API recibe el rol por DATABASE_URL, que es la
    ruta que usa producción.
    """
    host = os.getenv("POSTGRES_HOST", "localhost")
    puerto = os.getenv("POSTGRES_PORT", "5432")
    entorno = {**os.environ, "POSTGRES_DB": con_privilegios["base"], "RATE_LIMIT_ENABLED": "false",
               # Si la ejecución anidada no encuentra la base falla en vez de omitirse.
               "CI": "1"}
    entorno.pop("DATABASE_URL", None)
    if api_por_url:
        entorno["DATABASE_URL"] = (
            f"postgresql://{con_privilegios['rol']}:{con_privilegios['clave']}@{host}:{puerto}/{con_privilegios['base']}"
        )
    else:
        entorno["POSTGRES_USER"] = con_privilegios["rol"]
        entorno["POSTGRES_PASSWORD"] = con_privilegios["clave"]
    resultado = subprocess.run(
        [sys.executable, "-m", "pytest", *objetivos, "-q", "-p", "no:cacheprovider"],
        cwd=_BACKEND, env=entorno, capture_output=True, text=True, timeout=600,
    )
    cola = "\n".join(resultado.stdout.splitlines()[-25:])
    assert resultado.returncode == 0, f"{cola}\n{resultado.stderr[-1500:]}"
    resumen = resultado.stdout.strip().splitlines()[-1]
    assert " passed" in resumen and "skipped" not in resumen, resumen


# --- resolución de la conexión y runner de migraciones ---------------------------

def _cargar_runner():
    import importlib.util

    spec = importlib.util.spec_from_file_location("aplicar_migraciones", _RAIZ / "db" / "aplicar_migraciones.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


_VARIABLES = ("DATABASE_URL", "DATABASE_URL_MIGRACIONES", "POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER",
              "POSTGRES_PASSWORD", "POSTGRES_PORT")


@pytest.fixture
def entorno_limpio(monkeypatch):
    for nombre in _VARIABLES:
        monkeypatch.delenv(nombre, raising=False)
    return monkeypatch


def test_api_sin_database_url_usa_postgres_(entorno_limpio):
    from api.conexion_db import parametros_conexion

    entorno_limpio.setenv("POSTGRES_USER", "u")
    entorno_limpio.setenv("POSTGRES_DB", "d")
    assert parametros_conexion()["user"] == "u"
    entorno_limpio.setenv("DATABASE_URL", "   ")  # vacía o en blanco cuenta como no definida
    assert "dsn" not in parametros_conexion()
    entorno_limpio.setenv("DATABASE_URL", "postgresql://app@h/d")
    assert parametros_conexion() == {"dsn": "postgresql://app@h/d"}


def test_runner_prefiere_la_url_de_migraciones(entorno_limpio):
    runner = _cargar_runner()
    entorno_limpio.setenv("POSTGRES_USER", "u")
    assert runner._parametros_conexion()["user"] == "u"
    entorno_limpio.setenv("DATABASE_URL", "postgresql://app@h/d")
    assert runner._parametros_conexion() == {"dsn": "postgresql://app@h/d"}
    entorno_limpio.setenv("DATABASE_URL_MIGRACIONES", "postgresql://dueno@h/d")
    assert runner._parametros_conexion() == {"dsn": "postgresql://dueno@h/d"}
    entorno_limpio.setenv("DATABASE_URL_MIGRACIONES", "")
    assert runner._parametros_conexion() == {"dsn": "postgresql://app@h/d"}


def _correr_runner(con_privilegios, **variables):
    entorno = {k: v for k, v in os.environ.items() if k not in _VARIABLES}
    entorno.update(variables)
    return subprocess.run(
        [sys.executable, str(_RAIZ / "db" / "aplicar_migraciones.py")],
        cwd=_RAIZ, env=entorno, capture_output=True, text=True, timeout=120,
    )


def test_runner_con_cada_rol(con_privilegios):
    """El propietario aplica los privilegios; con el rol de la API el runner se detiene."""
    host = os.getenv("POSTGRES_HOST", "localhost")
    puerto = os.getenv("POSTGRES_PORT", "5432")
    base = con_privilegios["base"]
    url_app = f"postgresql://{con_privilegios['rol']}:{con_privilegios['clave']}@{host}:{puerto}/{base}"
    url_dueno = (
        f"postgresql://{os.getenv('POSTGRES_USER', 'aetheris_user')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'aetheris_ci_password')}@{host}:{puerto}/{base}"
    )
    propietario = _conectar(base)
    propietario.autocommit = True
    try:
        # schema_migrations la crea el runner con --bootstrap (ADR 0009).
        siembra = subprocess.run(
            [sys.executable, str(_RAIZ / "db" / "aplicar_migraciones.py"), "--bootstrap"],
            cwd=_RAIZ, env={**{k: v for k, v in os.environ.items() if k not in _VARIABLES},
                            "DATABASE_URL_MIGRACIONES": url_dueno},
            capture_output=True, text=True, timeout=120,
        )
        assert siembra.returncode == 0, siembra.stderr

        como_dueno = _correr_runner(con_privilegios, DATABASE_URL_MIGRACIONES=url_dueno, DATABASE_URL=url_app)
        assert como_dueno.returncode == 0, como_dueno.stderr
        assert "AVISO" not in como_dueno.stdout
        assert "rol de aplicacion" in como_dueno.stdout

        # Sin DATABASE_URL_MIGRACIONES el runner cae en DATABASE_URL, que es el rol
        # de la API: ni siquiera lee schema_migrations. El despliegue se detiene
        # en vez de seguir sin migrar, y la versión anterior sigue viva.
        como_app = _correr_runner(con_privilegios, DATABASE_URL=url_app)
        assert como_app.returncode != 0
        assert "permission denied for table schema_migrations" in como_app.stderr
    finally:
        with propietario.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS schema_migrations")
        propietario.close()


def test_script_que_crea_y_rota_el_rol(con_privilegios):
    """db/crear_rol_aplicacion.py crea el rol con los privilegios mínimos y rota su clave."""
    base = con_privilegios["base"]
    rol = f"{con_privilegios['rol']}_s"
    clave1, clave2 = secrets.token_hex(16), secrets.token_hex(16)

    def correr(clave, *extra):
        entorno = {k: v for k, v in os.environ.items() if k not in _VARIABLES}
        entorno.update(EPI_APP_CLAVE=clave, POSTGRES_DB=base,
                       POSTGRES_HOST=os.getenv("POSTGRES_HOST", "localhost"),
                       POSTGRES_USER=os.getenv("POSTGRES_USER", "aetheris_user"),
                       POSTGRES_PASSWORD=os.getenv("POSTGRES_PASSWORD", "aetheris_ci_password"),
                       POSTGRES_PORT=os.getenv("POSTGRES_PORT", "5432"))
        return subprocess.run(
            [sys.executable, str(_RAIZ / "db" / "crear_rol_aplicacion.py"), "--rol", rol, *extra],
            cwd=_RAIZ, env=entorno, capture_output=True, text=True, timeout=120,
        )

    try:
        primera = correr(clave1)
        assert primera.returncode == 0, primera.stderr
        assert "creado" in primera.stdout and clave1 not in primera.stdout + primera.stderr
        assert f"postgresql://{rol}:<CLAVE>@" in primera.stdout

        conexion = _conectar(base, rol, clave1)
        try:
            with conexion.cursor() as cur:
                cur.execute("SELECT has_table_privilege(current_user, 'auditoria', 'UPDATE'), "
                            "has_table_privilege(current_user, 'auditoria', 'INSERT')")
                assert cur.fetchone() == (False, True)
        finally:
            conexion.close()

        segunda = correr(clave2)
        assert segunda.returncode == 0 and "clave rotada" in segunda.stdout
        with pytest.raises(psycopg2.OperationalError):
            _conectar(base, rol, clave1)
        _conectar(base, rol, clave2).close()

        corta = correr("corta")
        assert corta.returncode != 0 and "al menos" in corta.stderr
    finally:
        propietario = _conectar(base)
        propietario.autocommit = True
        try:
            with propietario.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (rol,))
                if cur.fetchone():
                    cur.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(rol)))
                    cur.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(rol)))
        finally:
            propietario.close()


def test_script_con_propietario_sin_superusuario(entorno):
    """Render da un propietario con CREATEROLE pero sin superusuario.

    Postgres rechaza ALTER ROLE ... NOSUPERUSER a quien no es superusuario, así
    que el script no puede nombrar esos atributos: los fija el CREATE ROLE.
    """
    sufijo = secrets.token_hex(4)
    base = f"epi_prop_{sufijo}"
    propietario_rol = f"epi_prop_{sufijo}"
    rol = f"epi_app_{sufijo}_p"
    clave_prop, clave_app = secrets.token_hex(16), secrets.token_hex(16)
    admin = _conectar(os.getenv("POSTGRES_DB", "epi_aetheris"))
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE ROLE {} LOGIN CREATEROLE CREATEDB PASSWORD {}").format(
                    sql.Identifier(propietario_rol), sql.Literal(clave_prop)
                )
            )
            cur.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(base), sql.Identifier(propietario_rol)
                )
            )
        propietario = _conectar(base, propietario_rol, clave_prop)
        propietario.autocommit = True
        try:
            with propietario.cursor() as cur:
                cur.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
                assert cur.fetchone()[0] is False
                for archivo in _archivos_migracion():
                    cur.execute(archivo.read_text())
        finally:
            propietario.close()

        entorno_script = {k: v for k, v in os.environ.items() if k not in _VARIABLES}
        entorno_script.update(
            EPI_APP_CLAVE=clave_app, POSTGRES_DB=base,
            POSTGRES_HOST=os.getenv("POSTGRES_HOST", "localhost"),
            POSTGRES_PORT=os.getenv("POSTGRES_PORT", "5432"),
            POSTGRES_USER=propietario_rol, POSTGRES_PASSWORD=clave_prop,
        )
        corrida = subprocess.run(
            [sys.executable, str(_RAIZ / "db" / "crear_rol_aplicacion.py"), "--rol", rol],
            cwd=_RAIZ, env=entorno_script, capture_output=True, text=True, timeout=120,
        )
        assert corrida.returncode == 0, corrida.stderr
        assert "creado" in corrida.stdout

        conexion = _conectar(base, rol, clave_app)
        try:
            with conexion.cursor() as cur:
                cur.execute(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
                assert cur.fetchone() == (False, False, False, False, False)
                cur.execute("SELECT has_table_privilege(current_user, 'auditoria', 'UPDATE'), "
                            "has_table_privilege(current_user, 'auditoria', 'INSERT')")
                assert cur.fetchone() == (False, True)
        finally:
            conexion.close()

        rotacion = subprocess.run(
            [sys.executable, str(_RAIZ / "db" / "crear_rol_aplicacion.py"), "--rol", rol],
            cwd=_RAIZ, env=entorno_script, capture_output=True, text=True, timeout=120,
        )
        assert rotacion.returncode == 0 and "clave rotada" in rotacion.stdout, rotacion.stderr
    finally:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(base)))
            for nombre in (rol, propietario_rol):
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(nombre)))
        admin.close()
