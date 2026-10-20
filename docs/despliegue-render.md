# Despliegue en Render

Decisión tomada 2026-08-22, para tener una URL pública antes del video demo
(2026-09-05) y la Expo Técnica (2026-09-29). Investigación de costo-beneficio
comparó Render, Railway, Fly.io y Vercel; Render ganó por encajar directo con
el `docker-compose.yml` existente (en ese momento el Blueprint declaraba
los 3 servicios como IaC; hoy el frontend se publica aparte, ver abajo),
tener el mejor historial de uptime reciente de las opciones evaluadas,
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
   `main`) -- esto crea la base y el backend; el sitio estático se crea
   aparte desde el repo aetheris-nitor. El backend fallará
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
