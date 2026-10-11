# Roles de base de datos

**Estado:** Preparado (2026-10-11). Lo respalda el ADR 0024, punto E. Hasta que se sigan los pasos de este documento, la API y las migraciones siguen usando el usuario primario de Render, como hasta ahora.

## Qué cambia

Hoy la API y las migraciones se conectan con el mismo usuario de Render (`aetheris_user`), que es dueño de todo el esquema. Una vulnerabilidad en la API, por ejemplo una inyección SQL, podría reescribir o borrar la cadena de auditoría, apagar sus disparadores o alterar las tablas.

Después de este cambio hay dos roles:

| Rol | Quién lo usa | Qué puede |
|---|---|---|
| Propietario del esquema (`aetheris_user`, el usuario primario de Render) | Solo el `preDeployCommand` (`db/aplicar_migraciones.py`) y las órdenes manuales de mantenimiento | Todo el DDL: crear y alterar tablas, disparadores y funciones |
| `epi_app` | La API | Solo los privilegios de datos que el código usa, listados abajo |

Privilegios de `epi_app`, comprobados contra el código de `backend/api`:

| Tablas | Privilegios |
|---|---|
| `regiones`, `tipos_evento`, `fuentes_datos`, `semanas_epidemiologicas`, `casos_epidemiologicos`, `variables_ambientales`, `boletines_procesados`, `vigilancia_virus_respiratorios` | SELECT. La API no escribe datos epidemiológicos; las cargas las hace el propietario |
| `alertas`, `instituciones`, `usuarios`, `usuarios_roles`, `credenciales_clave`, `codigos_recuperacion`, `invitaciones`, `tokens_un_solo_uso`, `sesiones`, `desafios`, `correos_salientes` | SELECT, INSERT, UPDATE |
| `factores_autenticacion`, `intentos_ingreso` | SELECT, INSERT, UPDATE, DELETE. Son las únicas dos donde el código borra filas |
| `auditoria` | SELECT e INSERT. Sin UPDATE, DELETE, TRUNCATE ni REFERENCES |
| Secuencias de las tablas donde inserta | USAGE. `auditoria_id_seq` la usa el disparador que encadena la auditoría |
| Esquema `public` | USAGE, sin CREATE |

El rol no es superusuario, no crea bases ni roles, y no puede ejecutar `aplicar_privilegios_roles()`. No es dueño de ninguna tabla, así que no puede quitar ni desactivar los disparadores de la auditoría ni cambiar las funciones que calculan la cadena. Tampoco puede leer `schema_migrations`.

Las tablas de sesiones, tokens y desafíos caducados no se borran hoy en ningún punto del código, por eso `epi_app` no tiene DELETE sobre ellas. Cuando se escriba la limpieza de caducados, la migración que la añada debe conceder ese DELETE en `aplicar_privilegios_roles()`.

## Lo que esta separación no cubre

- Una inyección SQL todavía puede leer y modificar las tablas de cuentas, porque la API las necesita. Puede, por ejemplo, insertar una fila en `usuarios_roles`. Lo que ya no puede es borrar ese rastro de la auditoría ni cambiar el esquema. El hash de cabeza que se envía cada semana a los administradores (ADR 0024) detecta una reescritura completa de la cadena.
- El `preDeployCommand` corre con las variables de entorno del servicio, así que `DATABASE_URL_MIGRACIONES` también existe en el entorno del proceso de la API. Quien consiga ejecutar código arbitrario dentro del servicio, no solo SQL, puede leerla. Reducir ese riesgo exige mover las migraciones a un servicio aparte (un cron job de Render con su propio entorno) y queda fuera de este cambio.
- No se crea un tercer rol de solo lectura para las rutas públicas. Aislaría las tablas de cuentas de una inyección en una ruta pública, pero obliga a mantener dos grupos de conexiones y a decidir en cada ruta cuál usar, con riesgo de errores en un cambio que ya toca todo el acceso a datos. Las rutas públicas usan consultas parametrizadas y no hay hoy ningún hallazgo que lo exija. Se reconsidera si aparece una ruta pública con SQL dinámico o cuando se abran las cuentas al público. Para análisis ad hoc y copias se usa el propietario.

## Antes de empezar

1. El cambio de código ya está desplegado en `main` (incluye la migración `0018` y el script `db/crear_rol_aplicacion.py`). Antes de desplegarlo, nada de lo de abajo funciona.
2. Prepara una clave de al menos 24 caracteres, solo letras y números, generada en el gestor de contraseñas. Va dentro de una URL, por eso no lleva símbolos. No la escribas en ningún archivo, chat ni terminal compartida.
3. Ten a mano la URL interna de la base: Dashboard, base `epi-aetheris-db`, pestaña Info, campo Internal Database URL. Tiene la forma `postgresql://aetheris_user:<clave>@<host interno>/<base>`.

## Pasos en Render, en este orden

El orden importa: cada paso es reversible y ninguno deja a la API sin base si se sigue tal cual.

### Paso 1. Desplegar la migración.

Merge del cambio a `main` y deploy normal del backend. Revisa en los registros del deploy que la migración `0018_roles_de_base.sql` figure como aplicada y que aparezca el mensaje `el rol de aplicacion no existe todavia`. Hasta aquí no cambia nada para quien usa el sitio.

### Paso 2. Comprobar que el usuario primario puede crear roles.

En el panel del servicio `epi-aetheris-backend`, pestaña Shell, ejecuta:

```
python - <<'PY'
import os, psycopg2
c = psycopg2.connect(host=os.environ["POSTGRES_HOST"], dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"])
cur = c.cursor()
cur.execute("SELECT rolsuper, rolcreaterole FROM pg_roles WHERE rolname = current_user")
print(cur.fetchone())
PY
```

Si la segunda columna es `True` (o la primera), sigue. Si ambas son `False`, ve a la sección "Si el usuario no puede crear roles" y no sigas.

### Paso 3. Crear el rol.

En la misma Shell:

```
python db/crear_rol_aplicacion.py
```

Pide la clave dos veces sin mostrarla. Al terminar imprime `Rol epi_app: creado. Privilegios aplicados.` y la forma de la URL, con `<CLAVE>` en lugar de la clave. Si falla algo, el script no deja el rol a medias: no concede nada hasta que el rol existe y la función de privilegios está disponible.

### Paso 4. Declarar la URL del propietario.

Servicio `epi-aetheris-backend`, pestaña Environment, añade `DATABASE_URL_MIGRACIONES` con la Internal Database URL del paso previo (la del usuario primario). Guarda con deploy. Este paso no cambia el comportamiento: la API sigue en las variables `POSTGRES_*` y el runner usa el mismo usuario de siempre. Es obligatorio hacerlo antes del paso 5; si se invierte el orden, el runner intentaría migrar con `epi_app`, fallaría y el deploy se detendría (la versión anterior seguiría viva).

### Paso 5. Poner a la API en el rol de aplicación.

Añade `DATABASE_URL` con la forma `postgresql://epi_app:<CLAVE>@<mismo host interno>:5432/<base>` y la clave del paso 3. Guarda con deploy. En los registros del deploy debe aparecer `privilegios del rol de aplicacion aplicados`.

### Paso 6. Verificar.

- `GET /health`, `GET /api/alertas` y una página del sitio que cargue datos (`/dengue`) responden bien.
- Los registros del servicio no muestran `permission denied`.
- En la Shell, para ver con qué usuario está conectada la API (el resultado debe incluir `epi_app` y ninguna conexión de la API con `aetheris_user`, salvo la de la Shell misma):

```
python - <<'PY'
import os, psycopg2
c = psycopg2.connect(host=os.environ["POSTGRES_HOST"], dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"])
cur = c.cursor()
cur.execute("SELECT usename, count(*) FROM pg_stat_activity WHERE datname = current_database() GROUP BY 1")
print(cur.fetchall())
cur.execute("SELECT has_table_privilege('epi_app','auditoria','UPDATE'), has_table_privilege('epi_app','auditoria','DELETE'), has_table_privilege('epi_app','auditoria','TRUNCATE'), has_table_privilege('epi_app','auditoria','INSERT')")
print(cur.fetchone())
PY
```

La segunda línea debe ser `(False, False, False, True)`.

### Paso 7. Limpieza, después de unos días sin errores.

Cuando el rol de aplicación lleve una semana funcionando, abre un cambio que quite `POSTGRES_USER` y `POSTGRES_PASSWORD` del bloque `fromDatabase` de `render.yaml` y de las variables del servicio. Así el entorno de la API deja de contener la clave del usuario primario por duplicado. `POSTGRES_HOST`, `POSTGRES_DB` y `POSTGRES_PORT` pueden quedar. Antes de hacerlo, confirma que `DATABASE_URL_MIGRACIONES` está definida, porque el runner la usa en lugar de esas dos variables.

## Reversión

- Si tras el paso 5 hay errores `permission denied` o la API no responde: borra la variable `DATABASE_URL` (o déjala vacía) y guarda con deploy. La API vuelve a las variables `POSTGRES_*` sin tocar nada más. Es la reversión normal y tarda lo que un deploy.
- Si se define `DATABASE_URL` pero se olvidó `DATABASE_URL_MIGRACIONES`, el deploy se detiene en el preDeploy con `permission denied for table schema_migrations`. Define la segunda variable o borra la primera.
- Para quitar el rol por completo, conectado como propietario: `REVOKE ALL ON ALL TABLES IN SCHEMA public FROM epi_app; REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM epi_app; REVOKE ALL ON SCHEMA public FROM epi_app; REVOKE CONNECT ON DATABASE <base> FROM epi_app; DROP ROLE epi_app;`. Después de borrar el rol, el runner imprime de nuevo el aviso de que el rol no existe, sin error.
- La migración `0018` no tiene `down` (ADR 0009). Solo define una función y, si el rol existe, concede privilegios; dejarla no daña nada.

## Rotación de la clave

Genera otra clave en el gestor, vuelve a correr `python db/crear_rol_aplicacion.py` en la Shell (detecta que el rol existe y solo cambia la clave) y actualiza `DATABASE_URL` en el panel. Hay una ventana corta entre ambos pasos en la que la API falla al abrir conexiones nuevas; hazlo en un momento de poco tráfico.

## Si el usuario no puede crear roles

Esto no se pudo comprobar desde el repositorio: depende del plan y de la versión de la base en Render. Si el paso 2 muestra que el usuario primario no tiene `CREATEROLE`:

1. No improvises con otro método: el rol no se puede crear sin ese atributo.
2. Pregunta a soporte de Render si se puede habilitar la creación de roles en la base `epi-aetheris-db` o si ofrecen usuarios adicionales en ese plan.
3. Mientras tanto la protección de los disparadores queda como riesgo aceptado, como ya prevé el ADR 0024, y el hash de cabeza semanal sigue siendo el control que detecta la manipulación.

## Cómo probarlo en local

La prueba `backend/api/tests/test_roles_base.py` crea una base y un rol temporales con nombre aleatorio, aplica las migraciones, comprueba la matriz de privilegios, que `epi_app` no puede modificar la auditoría ni el esquema, y ejecuta la suite de cuentas y la de alertas conectada con ese rol. Se omite si el Postgres de pruebas no permite crear bases y roles.

Para usar el rol a mano en el entorno de desarrollo (docker compose):

```
python db/crear_rol_aplicacion.py        # con las POSTGRES_* del .env apuntando a localhost
```

y en el `.env`: `DATABASE_URL=postgresql://epi_app:<clave>@db:5432/epi_aetheris`. Si defines `DATABASE_URL` en el `.env`, define también `DATABASE_URL_MIGRACIONES` antes de correr el runner desde el host, o este usará el rol de la API y se detendrá.

## Mantenimiento

Una tabla nueva queda sin acceso para `epi_app`. La migración que la crea debe incluir un `CREATE OR REPLACE FUNCTION aplicar_privilegios_roles()` con la tabla añadida a la lista que le corresponde (con el mínimo de privilegios que el código necesite) y actualizar la matriz de `test_roles_base.py`. Esa prueba falla si hay una tabla sin clasificar. El runner vuelve a llamar la función en cada despliegue, así que los privilegios nuevos llegan sin otro paso manual.
