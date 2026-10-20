# Despliegue en Render

Decisión tomada 2026-08-22, para tener una URL pública antes del video demo
(2026-09-05) y la Expo Técnica (2026-09-29). Investigación de costo-beneficio
comparó Render, Railway, Fly.io y Vercel; Render ganó por encajar directo con
el `docker-compose.yml` existente (Blueprint declara los 3 servicios como
IaC), tener el mejor historial de uptime reciente de las opciones evaluadas,
y no requerir administración manual de Postgres (a diferencia de Fly.io). El
plan de pago (~$14/mes, Starter + Basic-256mb) se eligió desde el día 1 en
vez del tier gratuito: el free tier de Render duerme el backend a los 15 min
de inactividad (cold start ~1 min, malo para una demo en vivo) y su Postgres
gratis expira a los 30 días -- la ventana de trabajo hasta la Expo supera eso.

Railway quedó descartado por su historial de incidentes (5 publicados desde
noviembre 2025, incluyendo un corte de ~8h en mayo 2026) frente a una fecha
fija no negociable. Fly.io quedó descartado por exigir Postgres
self-managed sin backups automáticos en su tier barato -- carga operativa
que no conviene meter en las semanas de video/expo. Vercel + Render
(separando frontend de backend/DB) es una alternativa igual de válida al
mismo costo total (~$14/mes, Vercel Hobby es gratis para este tráfico) --
se descartó solo por preferencia de una sola cuenta/dashboard, no por un
problema técnico.

Esto es un despliegue para demo, no para producción con usuarios reales
-- no cambia el statuto del proyecto sobre APIs de datos de pago (ver
AGENTS.md), que sigue aplicando a las fuentes (MINSAL/OpenDengue/Open-Meteo),
no a la infraestructura de hosting.

## Qué declara `render.yaml`

Blueprint con dos recursos (base y backend), en la región `oregon` (misma región =
red privada entre backend y base):

- `epi-aetheris-db` -- Postgres 15 gestionado, plan `basic-256mb`.
- `epi-aetheris-backend` -- FastAPI vía Docker (`backend/Dockerfile.render`,
  contexto = raíz del repo para incluir `db/aplicar_migraciones.py` y
  `db/migrations/`). `preDeployCommand` corre `python db/aplicar_migraciones.py`
  antes de conmutar tráfico. CMD de producción sin `--reload`.

Las variables de Postgres (`POSTGRES_HOST/PORT/DB/USER/PASSWORD`) se
inyectan automáticamente al backend vía `fromDatabase`. `CORS_ALLOWED_ORIGINS`
está fija a los dominios propios: el sitio canónico `https://epi-aetheris.dev`
y su variante con `www`. El sitio se publica como sitio estático
`aetheris-nitor` desde el repo aetheris-nitor, fuera de este blueprint, con
`PUBLIC_API_URL=https://api.epi-aetheris.dev`. Los valores que rigen en
producción son los del panel de Render; `render.yaml` solo los documenta, así
que un cambio aquí hay que repetirlo allí.

## Primer despliegue (pasos manuales, una sola vez)

Render, a diferencia de la imagen oficial de Postgres en docker-compose, no
tiene un hook `docker-entrypoint-initdb.d` que auto-aplique
`db/migrations/*.sql` sobre una base gestionada recién creada. El
`preDeployCommand` solo aplica lo *pendiente* contra una tabla
`schema_migrations` que todavía no existe en una base vacía, así que el
primer deploy del backend fallará ese paso hasta terminar lo siguiente.

1. En el dashboard de Render, conectar el Blueprint a este repo (rama
   `main`) -- esto crea los 3 servicios. El backend fallará
   `preDeployCommand` / healthcheck hasta el paso 3, porque la base está
   vacía.
2. Copiar la **External Connection String** de `epi-aetheris-db` (dashboard
   → esa base → "Connect" → External).
3. Desde el host (no dentro de ningún contenedor), aplicar el DDL, registrar
   las migraciones y cargar el seed:

   ```bash
   export POSTGRES_HOST=<host externo de Render>
   export POSTGRES_PORT=<puerto externo>
   export POSTGRES_USER=aetheris_user
   export POSTGRES_DB=epi_aetheris
   export POSTGRES_PASSWORD=<password del dashboard>
   CONN="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"

   # La base gestionada nace vacia: hay que correr el DDL. --bootstrap solo
   # crea schema_migrations y marca archivos como ya aplicados, no ejecuta SQL.
   for f in db/migrations/[0-9]*.sql; do
     psql "$CONN" -v ON_ERROR_STOP=1 -f "$f"
   done
   python db/aplicar_migraciones.py --bootstrap

   # -X: no leer ~/.psqlrc. --single-transaction + ON_ERROR_STOP: si algo
   # falla, rollback de toda la carga, no un seed a medias.
   # El dump hace SELECT pg_catalog.set_config('search_path', '', false)
   # y eso PERSISTE en la sesion psql: un segundo -f en la misma invocacion
   # (psql ... -f seed.sql -f otra.sql) no encuentra tablas en public
   # a menos que esa otra cosa use nombres calificados public.* o ejecute
   # SET search_path TO public. Por eso el seed va en su propia invocacion.
   psql "$CONN" -X --single-transaction -v ON_ERROR_STOP=1 -q -f db/seed/seed_datos_reales.sql
   ```

   El seed versionado ya no incluye `ALTER TABLE ... DISABLE/ENABLE TRIGGER
   ALL` (issue #82). `pg_dump --disable-triggers` las emite por defecto y
   `aetheris_user` en el Postgres gestionado de Render no es superuser, así
   que esas líneas abortaban la carga. El generador `db/generar_seed.sh`
   las filtra; no hace falta un `grep -v` a mano. Las FK se validan igual:
   el dump ordena las tablas por dependencia.

   `--bootstrap` crea `schema_migrations` y registra qué migraciones ya
   corrieron (ver ADR 0009). A partir de aquí el `preDeployCommand` puede
   aplicar lo nuevo. Forzar un Manual Deploy del backend para que pase el
   healthcheck.
4. Verificar en el dashboard que `CORS_ALLOWED_ORIGINS` (env var del
   backend) incluya el origen del sitio y que `PUBLIC_API_URL` (env var del
   frontend) apunte a la API. Tras cambiar `PUBLIC_API_URL` hay que
   redesplegar el frontend: se embebe en build-time y un cambio de env var
   sin rebuild no tiene efecto.
5. Confirmar `GET /health` del backend y que `/dengue` cargue el mapa con
   datos reales -- si el mapa muestra "sin dato" en todo, lo más probable
   es el paso 4 (frontend compilado apuntando al `PUBLIC_API_URL` viejo).

## Cambios de esquema después del primer despliegue

Agregar un archivo nuevo en `db/migrations/` (ADR aceptado en `docs/adr/`
antes de escribirlo) y mergear a `main`. El `preDeployCommand` del backend
(`python db/aplicar_migraciones.py`) corre contra las mismas `POSTGRES_*`
del servicio, antes de conmutar tráfico. Si la migración falla, el deploy
no avanza y sigue viva la versión anterior.

Con los roles de base separados (ADR 0024, punto E), el runner lee
`DATABASE_URL_MIGRACIONES` (rol propietario) y, si falta, `DATABASE_URL` y
luego `POSTGRES_*`; la API usa `DATABASE_URL` (rol `epi_app`, sin permiso para
alterar el esquema ni la auditoría) y, si falta, `POSTGRES_*`. Los pasos para
activarlo en Render están en `docs/seguridad/roles-de-base-de-datos.md`.

No hace falta exportar `MIGRACIONES_POSTGRES_HOST`: el runner lee
`POSTGRES_HOST` (y el resto de `POSTGRES_*`). Desde el host, contra
docker-compose, `POSTGRES_HOST=db` se trata como `localhost` porque ese
nombre solo resuelve dentro de `aetheris_network`.

Para aplicar una migración a Render *sin* esperar un deploy (p. ej. un
hotfix), el mismo comando desde el host con las variables del paso 3:

```bash
python db/aplicar_migraciones.py
```

## Mover la base a Neon (ADR 0026)

Solo después de aceptar el ADR 0026. Se hace una vez, en una ventana de
mantenimiento de unos 30 minutos, mientras el backend sigue en el plan Starter:
así el `preDeployCommand` y la Shell siguen disponibles para comprobar el
cambio antes de bajar de plan.

Requisitos en la máquina desde la que se corre: Docker y este repositorio en
`main`. Todos los comandos usan la imagen `postgres:15` (mismas herramientas
que la versión del servidor) y la imagen de producción del backend, así que no
hace falta instalar `psql` ni un entorno de Python.

### 1. Preparar Neon

1. Crear un proyecto en la región AWS `us-west-2` (Oregón) con Postgres 15 y
   una base `epi_aetheris`, propiedad del rol que crea Neon (el propietario del
   esquema).
2. En la configuración del cómputo, fijar mínimo y máximo en 0.25 CU.
3. En "Connect", con la base `epi_aetheris` y el rol propietario, desactivar
   "Connection pooling" y copiar la cadena **directa** (el host no lleva
   `-pooler`). Debe terminar en `?sslmode=require` (Neon puede añadir
   `&channel_binding=require`; se deja).

### 2. Medir la base de Render

En la Shell del servicio `epi-aetheris-backend`:

```
python - <<'PY'
import os, psycopg2
c = psycopg2.connect(host=os.environ["POSTGRES_HOST"], dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"])
cur = c.cursor()
cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
print(cur.fetchone()[0])
PY
```

Tiene que quedar holgadamente por debajo del almacenamiento del plan Free de
Neon. Si no, parar aquí.

### 3. Abrir un acceso temporal a la base de Render

`render.yaml` deja la base sin acceso externo (`ipAllowList: []`). En el panel,
base `epi-aetheris-db`, sección de acceso (Networking / Access Control), añadir
la IP pública de esta máquina con `/32`. Se quita en el paso 6.

Después, en una terminal de esta máquina (las URL se leen sin eco y no quedan
en el historial):

```bash
# Fuera del repositorio: el volcado contiene datos de cuentas (ADR 0024).
mkdir -p ~/respaldos-epi && chmod 700 ~/respaldos-epi

read -rs RENDER_URL; echo       # External Database URL de epi-aetheris-db + ?sslmode=require
read -rs NEON_OWNER_URL; echo   # cadena directa del propietario en Neon (paso 1)
export RENDER_URL NEON_OWNER_URL

# Filas por tabla y estado de la cadena de auditoría: se comparan antes y después.
export CONTEO="SELECT table_name, (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM public.%I', table_name), false, true, '')))[1]::text FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY 1;"
export AUDITORIA="SELECT auditoria_verificar(), (SELECT encode(hash, 'hex') FROM auditoria ORDER BY id DESC LIMIT 1), (SELECT last_value FROM auditoria_id_seq);"
export PRIVILEGIOS="SELECT has_table_privilege('epi_app', 'auditoria', p) FROM unnest(ARRAY['UPDATE', 'DELETE', 'TRUNCATE', 'INSERT']) AS p;"
# El runner y el script del rol leen la URL del propietario de esta variable.
export DATABASE_URL_MIGRACIONES="$NEON_OWNER_URL"

pg() {
  docker run --rm -i -e RENDER_URL -e NEON_OWNER_URL -e CONTEO -e AUDITORIA -e PRIVILEGIOS \
    -v "$HOME/respaldos-epi:/respaldo" postgres:15 "$@"
}
```

### 4. Suspender el backend

Panel, servicio `epi-aetheris-backend`, Settings, Suspend. Desde aquí nadie
escribe en la base (sesiones, alertas, auditoría). El sitio estático sigue
arriba y los paneles de datos no cargan hasta el paso 10.

### 5. Volcar la base de Render

```bash
pg sh -c 'pg_dump --dbname="$RENDER_URL" --format=custom --no-owner --no-privileges --file=/respaldo/render-final.dump'
pg sh -c 'psql "$RENDER_URL" -X -A -t -c "$CONTEO"'     > ~/respaldos-epi/filas-render.txt
pg sh -c 'psql "$RENDER_URL" -X -A -t -c "$AUDITORIA"'  > ~/respaldos-epi/auditoria-render.txt
cat ~/respaldos-epi/auditoria-render.txt
```

El volcado incluye esquema y datos, también `schema_migrations`, así que la
base de destino no necesita `--bootstrap`. `--no-owner` y `--no-privileges`
dejan todo a nombre del propietario de Neon. Los permisos de `epi_app` se
vuelven a conceder en el paso 9.

La primera columna de `auditoria-render.txt` tiene que salir vacía: es el id de
la primera fila rota de la cadena y `NULL` significa que no hay ninguna. Si sale
un número, parar y seguir `docs/seguridad/respuesta-a-incidentes.md` antes de
mover nada.

### 6. Cerrar el acceso temporal

Quitar la IP añadida en el paso 3. La base de Render vuelve a no aceptar
conexiones externas.

### 7. Restaurar en Neon

```bash
pg sh -c 'pg_restore --dbname="$NEON_OWNER_URL" --no-owner --no-privileges --single-transaction --exit-on-error /respaldo/render-final.dump'
```

`--single-transaction` y `--exit-on-error`: si algo falla, no queda nada a
medias y se puede repetir sobre la misma base vacía. Si falla, leer el error.
No quitar `--exit-on-error` para forzar la carga.

pg_restore crea los disparadores después de cargar los datos. Por eso las filas
de `auditoria` entran tal cual, con sus hashes originales, sin volver a
encadenarse.

### 8. Comprobar la copia

```bash
pg sh -c 'psql "$NEON_OWNER_URL" -X -A -t -c "$CONTEO"'     > ~/respaldos-epi/filas-neon.txt
pg sh -c 'psql "$NEON_OWNER_URL" -X -A -t -c "$AUDITORIA"'  > ~/respaldos-epi/auditoria-neon.txt
diff ~/respaldos-epi/filas-render.txt ~/respaldos-epi/filas-neon.txt && echo "filas: iguales"
diff ~/respaldos-epi/auditoria-render.txt ~/respaldos-epi/auditoria-neon.txt && echo "auditoria: igual"
```

Los dos `diff` tienen que salir sin diferencias: las mismas filas por tabla, la
misma cabeza de la cadena de auditoría, la misma secuencia y ninguna fila rota.

Después, con la imagen de producción (construida desde la raíz del
repositorio), el runner tiene que responder `Nada pendiente`. El aviso
siguiente, `el rol de aplicacion no existe todavia`, es esperado hasta el paso 9:

```bash
docker build -f backend/Dockerfile.render -t epi-aetheris-api .
docker run --rm -e DATABASE_URL_MIGRACIONES epi-aetheris-api python db/aplicar_migraciones.py
```

### 9. Crear el rol de la API en Neon

```bash
docker run --rm -it -e DATABASE_URL_MIGRACIONES epi-aetheris-api python db/crear_rol_aplicacion.py
```

Pide la clave nueva dos veces: 24 caracteres o más, solo letras y números,
generada en el gestor de contraseñas. Al terminar imprime la forma de la URL.
`DATABASE_URL` es esa URL con la clave, el host directo de Neon y
`?sslmode=require` al final.

Comprobar que `epi_app` no puede modificar la auditoría. Tiene que salir `f`,
`f`, `f`, `t` (UPDATE, DELETE, TRUNCATE, INSERT):

```bash
pg sh -c 'psql "$NEON_OWNER_URL" -X -A -t -c "$PRIVILEGIOS"'
```

### 10. Apuntar el backend a Neon

Servicio `epi-aetheris-backend`, pestaña Environment:

| Variable | Valor |
|---|---|
| `DATABASE_URL` | URL de `epi_app` en Neon (paso 9) |
| `DATABASE_URL_MIGRACIONES` | `NEON_OWNER_URL` |
| `POSTGRES_POOL_MIN` | `0` (ADR 0026, punto D) |

En Settings, vaciar Health Check Path (ADR 0026, punto E). Guardar y reanudar
el servicio (Resume). En los registros del deploy, el `preDeployCommand` tiene
que mostrar `Nada pendiente` y `privilegios del rol de aplicacion aplicados`.
Las `POSTGRES_*` siguen apuntando a Render, pero ya no se usan: la API lee
`DATABASE_URL` y el runner lee `DATABASE_URL_MIGRACIONES`.

### 11. Verificar el sitio

- `GET https://api.epi-aetheris.dev/health` responde `ok`.
- `/alertas` y `/dengue` cargan datos; una cuenta de prueba inicia sesión.
- Los registros del backend no muestran `permission denied` ni errores de
  conexión.
- La API ya no usa la base de Render: en el panel de `epi-aetheris-db`, las
  conexiones activas bajan a cero. (En Neon, `pg_stat_activity` casi nunca
  muestra a `epi_app`, porque con `POSTGRES_POOL_MIN=0` cada conexión se cierra
  al terminar la petición.)

### 12. Bajar el backend a Free

Settings, Instance Type, Free. Si el panel no permite `preDeployCommand` en ese
plan, vaciarlo: desde ahí las migraciones se aplican desde el host con el
comando del paso 8, antes de mergear a `main` (ADR 0026, punto G).

Revisar el consumo de cómputo en el panel de Neon durante la primera semana. Si
se acerca a las 100 horas antes de fin de mes, algo mantiene despierta la base
(ADR 0026, punto E).

### 13. Borrar la base de Render

Tras una semana sin problemas, borrar `epi-aetheris-db` en el panel. Es lo que
deja de facturar y **no se puede deshacer**. `~/respaldos-epi/render-final.dump`
es su última copia. Después, el cambio de `render.yaml` que describe el
ADR 0026.

### Reversión

Antes del paso 13, quitar `DATABASE_URL` y `DATABASE_URL_MIGRACIONES` del
servicio y volver al plan Starter: la API vuelve a las `POSTGRES_*` de Render.
Lo escrito en Neon desde el paso 10 (sesiones, alertas, auditoría) no existe en
Render. Si hay algo que conservar, se repiten los pasos 4 a 8 en sentido
contrario, sobre una base de Render vacía.

### Copia semanal (ADR 0026, punto H)

Cada semana y antes de cada migración, con `NEON_OWNER_URL` exportada y la
función `pg` del paso 3 definidas en la terminal:

```bash
pg sh -c 'pg_dump --dbname="$NEON_OWNER_URL" --format=custom --no-owner --no-privileges --file=/respaldo/neon-$(date +%F).dump'
```

Guardar la copia cifrada y fuera del repositorio. Para restaurarla, el comando
del paso 7 sobre una base vacía, y después la comprobación del paso 8.
