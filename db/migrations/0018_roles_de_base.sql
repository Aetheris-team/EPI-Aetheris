-- ============================================================================
-- EPI-Aetheris — Migración 0018
-- Respalda: ADR 0024, punto E (roles de base de datos separados)
--
-- Separa dos roles:
--   * propietario del esquema (hoy el usuario que crea Render): crea y altera
--     tablas, disparadores y funciones. Lo usa solo el preDeployCommand.
--   * epi_app: el rol con el que se conecta la API. Solo recibe los privilegios
--     de datos que el código usa. No puede crear ni alterar objetos, ni
--     desactivar disparadores, ni modificar ni borrar la auditoría.
--
-- Esta migración NO crea el rol epi_app ni su contraseña: un CREATE ROLE con
-- contraseña no puede vivir en un archivo versionado, y en Render el rol se
-- crea una vez a mano (docs/seguridad/roles-de-base-de-datos.md). La migración
-- define la función aplicar_privilegios_roles(), que concede lo necesario si
-- el rol ya existe y no hace nada (solo un aviso) si todavía no existe. El
-- runner de migraciones la vuelve a llamar en cada despliegue, de modo que el
-- orden en que se cree el rol y se despliegue no importa.
--
-- La función revoca todo antes de conceder, así que es idempotente y también
-- corrige cualquier privilegio que se haya concedido a mano de más.
--
-- Convención: una tabla o secuencia nueva no queda accesible para epi_app
-- hasta que una migración la agregue a esta función con CREATE OR REPLACE
-- FUNCTION. La prueba backend/api/tests/test_roles_base.py falla si existe una
-- tabla que la función no clasifica.
-- ============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION aplicar_privilegios_roles(p_app TEXT DEFAULT 'epi_app')
RETURNS BOOLEAN AS $$
DECLARE
    -- Tablas de datos epidemiológicos: la API solo las lee. Las cargas
    -- (db/seed, backend/ingestion) las hace el propietario.
    solo_lectura  TEXT[] := ARRAY[
        'regiones', 'tipos_evento', 'fuentes_datos', 'semanas_epidemiologicas',
        'casos_epidemiologicos', 'variables_ambientales', 'boletines_procesados',
        'vigilancia_virus_respiratorios'
    ];
    -- Tablas que la API lee, inserta y actualiza, pero nunca borra.
    lectura_escritura TEXT[] := ARRAY[
        'alertas', 'instituciones', 'usuarios', 'usuarios_roles',
        'credenciales_clave', 'codigos_recuperacion', 'invitaciones',
        'tokens_un_solo_uso', 'sesiones', 'desafios', 'correos_salientes',
        'aprobaciones_administrativas'
    ];
    -- Además se borran filas: intentos_ingreso (se limpia el contador tras un
    -- ingreso correcto) y factores_autenticacion (se descarta el TOTP sin
    -- confirmar antes de generar uno nuevo).
    con_borrado TEXT[] := ARRAY['factores_autenticacion', 'intentos_ingreso'];
    -- Solo inserción y lectura. Nunca UPDATE, DELETE ni TRUNCATE.
    solo_insercion TEXT[] := ARRAY['auditoria'];
    -- Secuencias de las tablas en las que la API inserta. USAGE basta para
    -- nextval(); auditoria_id_seq la usa el disparador auditoria_encadenar.
    secuencias TEXT[] := ARRAY[
        'alertas_id_seq', 'instituciones_id_seq', 'usuarios_roles_id_seq',
        'codigos_recuperacion_id_seq', 'correos_salientes_id_seq',
        'auditoria_id_seq'
    ];
    t TEXT;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = p_app) THEN
        RAISE NOTICE 'El rol % no existe todavía: no se concede nada. Créalo y vuelve a desplegar (docs/seguridad/roles-de-base-de-datos.md).', p_app;
        RETURN FALSE;
    END IF;

    -- Nadie crea objetos en public salvo el propietario (en Postgres 15 ya es
    -- así por defecto; se fija para bases creadas con valores anteriores).
    EXECUTE 'REVOKE CREATE ON SCHEMA public FROM PUBLIC';
    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', p_app);
    EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', p_app);
    EXECUTE format('REVOKE CREATE ON SCHEMA public FROM %I', p_app);
    EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', p_app);

    -- Una tabla de las listas que todavía no existe (la crea una migración
    -- posterior o de otra rama) se omite; el runner repite esta función
    -- después de cada migración y le llegan sus privilegios entonces.
    FOREACH t IN ARRAY solo_lectura LOOP
        IF to_regclass(format('public.%I', t)) IS NOT NULL THEN
            EXECUTE format('GRANT SELECT ON %I TO %I', t, p_app);
        END IF;
    END LOOP;
    FOREACH t IN ARRAY lectura_escritura LOOP
        IF to_regclass(format('public.%I', t)) IS NOT NULL THEN
            EXECUTE format('GRANT SELECT, INSERT, UPDATE ON %I TO %I', t, p_app);
        END IF;
    END LOOP;
    FOREACH t IN ARRAY con_borrado LOOP
        IF to_regclass(format('public.%I', t)) IS NOT NULL THEN
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO %I', t, p_app);
        END IF;
    END LOOP;
    FOREACH t IN ARRAY solo_insercion LOOP
        IF to_regclass(format('public.%I', t)) IS NOT NULL THEN
            EXECUTE format('GRANT SELECT, INSERT ON %I TO %I', t, p_app);
        END IF;
    END LOOP;
    FOREACH t IN ARRAY secuencias LOOP
        IF to_regclass(format('public.%I', t)) IS NOT NULL THEN
            EXECUTE format('GRANT USAGE ON SEQUENCE %I TO %I', t, p_app);
        END IF;
    END LOOP;

    -- Las funciones de la auditoría (auditoria_verificar y las de los
    -- disparadores) conservan el EXECUTE que Postgres da a PUBLIC; son de
    -- invocador, así que no amplían lo que el rol puede leer o escribir.
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Solo el propietario concede privilegios; el rol de la API no necesita llamarla.
REVOKE EXECUTE ON FUNCTION aplicar_privilegios_roles(TEXT) FROM PUBLIC;

COMMENT ON FUNCTION aplicar_privilegios_roles(TEXT) IS
    'Concede a epi_app los privilegios mínimos de la API si el rol existe. Idempotente. ADR 0024, punto E.';

DO $$ BEGIN PERFORM aplicar_privilegios_roles(); END $$;

COMMIT;
