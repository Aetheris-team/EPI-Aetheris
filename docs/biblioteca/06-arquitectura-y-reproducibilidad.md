---
titulo: "Arquitectura y reproducibilidad"
descripcion: "Servicios Docker, volcado de datos reales versionado y un comando para levantar el sistema: git clone y docker compose up."
orden: 6
categoria: "Cómo funciona"
---

EPI-Aetheris se replica con el repositorio y Docker. No hay API de datos de pago en el núcleo, no hay SaaS obligatorio y el costo de replicación para un tercero tiende a cero.

## Servicios

`docker-compose.yml` declara una red (`aetheris_network`) y contenedores de nombre fijo. `docker compose up` levanta solo `db` y `backend`; el resto va bajo perfiles:

| Servicio | Qué es | Puerto | Arranque |
|---|---|---|---|
| `db` | PostgreSQL 15 | 5432 | por defecto |
| `backend` | FastAPI + `psycopg2` (sin ORM). Entrada: `backend/api/main.py`; endpoints en `backend/api/rutas/` | 8000 (`/health`; `/docs` solo en local) | por defecto |
| `web` | Astro + TypeScript + Tailwind + ECharts + Leaflet | 4321 | perfil `web` |
| `mailpit` | Bandeja de correo de desarrollo para las cuentas | 8025 | perfil `cuentas` |
| `e2e` | Pruebas Playwright del frontend | — | perfil `test` |

El esquema se carga desde `db/migrations/*.sql` **una sola vez**, sobre volumen vacío (`docker-entrypoint-initdb.d`). En el mismo arranque se monta `db/seed/seed_datos_reales.sql`: un volcado `pg_dump --data-only` de las tablas de hechos (ADR 0010). Quien clona obtiene el sistema **con datos reales**, no un cascarón vacío.

Hardware de referencia: 4 GB de RAM, CPU de dos núcleos x86-64, ~10 GB de disco.

## Cómo levantarlo

```bash
cp .env.example .env   # completar POSTGRES_* ; no commitear .env
docker compose up --build                       # db + backend
docker compose --profile web up -d web          # opcional: el sitio en contenedor
```

La API queda en `http://localhost:8000` y el sitio, con el perfil `web` o con `pnpm dev`, en `http://localhost:4321`. El CORS del backend local admite ese origen y el `4322`.

Fuera de Docker (desarrollo):

- Backend: `cd backend && pip install -r requirements.txt && uvicorn api.main:app --reload` (virtualenv).
- Web: `cd web && pnpm install && pnpm dev` (pnpm vía Corepack, v9; no `npm`).

Los datos crudos e intermedios (`backend/ingestion/data/raw/`, `.../interim/`) no se versionan. El volcado en `db/seed/` es la excepción deliberada que hace cierta la promesa de un comando.

## Qué incluye el volcado

Foto en texto plano (~4,4 MB), sin PDF crudos. **No** incluye todavía las series del tablero de MINSAL (2025–2026, ADR 0021): se cargan con `backend/ingestion/cargar_minsal_tablero.py` a partir de capturas que no se versionan. Tablas de hechos: `semanas_epidemiologicas`, `boletines_procesados`, `casos_epidemiologicos`, `variables_ambientales`, y desde la foto del 1 de septiembre de 2026 también `vigilancia_virus_respiratorios` e IRA/neumonías (2.742 / 2.749 filas más 3.028 de vigilancia viral).

**No** incluye `regiones`, `tipos_evento` ni `fuentes_datos`: esas tres las siembran las propias migraciones. Tampoco `schema_migrations`: esa tabla la crea el runner de migraciones, no `initdb`.

Es una foto fija. Regenerarla es manual (`db/generar_seed.sh`) cuando el equipo decide que vale una imagen más reciente. El script post-procesa los `DISABLE/ENABLE TRIGGER ALL` de `pg_dump` porque en el Postgres gestionado de Render el rol de la aplicación no es superuser.

## Migraciones en una base que ya existe

`docker-entrypoint-initdb.d` no vuelve a correr sobre un volumen con datos. Para ese caso está `db/aplicar_migraciones.py` (ADR 0009):

```bash
python db/aplicar_migraciones.py --bootstrap   # una vez: registra lo ya aplicado
python db/aplicar_migraciones.py               # aplica solo archivos nuevos
```

Corre desde el host contra `localhost:5432`. Sin rollback: una migración mala se corrige con otra migración. Todo cambio de esquema exige un ADR aceptado **antes** de escribir el SQL.

## Stack

- **Backend:** Python, FastAPI, scikit-learn (el clasificador retirado; no se extiende), `pdfplumber`, `epiweeks` (semanas PAHO/CDC, no ISO 8601).
- **Frontend:** Astro, TypeScript, Tailwind CSS v4, ECharts, Leaflet. Sin React ni Vue. Se desarrolla en el repositorio `aetheris-nitor`; `web/` es una copia que se sincroniza desde ahí.
- **Dominio en español:** tablas, columnas, comentarios.

Contenido de esta Biblioteca: Markdown con frontmatter en `docs/biblioteca/`, colección de Astro en `web/src/content.config.ts`. Los registros de decisiones de arquitectura (`docs/adr/`) no se renderizan aquí.

## Despliegue público

El entorno de demostración vive en **Render**. `render.yaml` declara Postgres 15 gestionado y el backend Docker con `preDeployCommand: python db/aplicar_migraciones.py`, ambos en la región `oregon` y con red privada entre API y base. El sitio estático de Astro (`pnpm build`, publica `dist/`) se despliega aparte, desde el repositorio `aetheris-nitor`, y se sirve por CDN.

`main` es la rama que Render despliega para el backend. Integra solo desde `dev`. Las ramas de trabajo abren PR contra `dev`.

Al publicar una versión nueva del frontend hay que subir `VERSION` en `web/public/sw.js` para invalidar el shell cacheado del service worker.
