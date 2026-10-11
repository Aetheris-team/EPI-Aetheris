---
titulo: "Arquitectura y reproducibilidad"
descripcion: "Tres servicios Docker, volcado de datos reales versionado y un comando para levantar el sistema: git clone y docker compose up."
orden: 6
categoria: "Cómo funciona"
---

EPI-Aetheris se replica con el repositorio y Docker. No hay API de datos de pago en el núcleo, no hay SaaS obligatorio y el costo de replicación para un tercero tiende a cero.

## Tres servicios

`docker-compose.yml` declara una red (`aetheris_network`) y tres contenedores de nombre fijo:

| Servicio | Qué es | Puerto |
|---|---|---|
| `db` | PostgreSQL 15 | 5432 |
| `backend` | FastAPI + `psycopg2` (sin ORM). Entrada: `backend/api/main.py` | 8000 (`/health`; `/docs` solo en local) |
| `web` | Astro + TypeScript + Leaflet + Tailwind | 4321 |

El esquema se carga desde `db/migrations/*.sql` **una sola vez**, sobre volumen vacío (`docker-entrypoint-initdb.d`). En el mismo arranque se monta `db/seed/seed_datos_reales.sql`: un volcado `pg_dump --data-only` de las tablas de hechos (ADR 0010). Quien clona obtiene el sistema **con datos reales**, no un cascarón vacío.

Hardware de referencia: 4 GB de RAM, CPU de dos núcleos x86-64, ~10 GB de disco.

## Cómo levantarlo

```bash
cp .env.example .env   # completar POSTGRES_* ; no commitear .env
docker compose up --build
```

La API queda en `http://localhost:8000` y el sitio en `http://localhost:4321`. El CORS del backend local admite ese origen del frontend.

Fuera de Docker (desarrollo):

- Backend: `cd backend && pip install -r requirements.txt && uvicorn api.main:app --reload` (virtualenv).
- Web: `cd web && pnpm install && pnpm dev` (pnpm vía Corepack, v9; no `npm`).

Los datos crudos e intermedios (`backend/ingestion/data/raw/`, `.../interim/`) no se versionan. El volcado en `db/seed/` es la excepción deliberada que hace cierta la promesa de un comando.

## Qué incluye el volcado

Foto en texto plano (~4,4 MB), sin PDF crudos. Tablas de hechos: `semanas_epidemiologicas`, `boletines_procesados`, `casos_epidemiologicos`, `variables_ambientales`, y desde la foto del 1 de septiembre de 2026 también `vigilancia_virus_respiratorios` e IRA/neumonías (2.742 / 2.749 filas más 3.028 de vigilancia viral).

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
- **Frontend:** Astro, TypeScript, Tailwind CSS v4, Leaflet. Sin React ni Vue.
- **Dominio en español:** tablas, columnas, comentarios.

Contenido de esta Biblioteca: Markdown con frontmatter en `docs/biblioteca/`, colección de Astro en `web/src/content.config.ts`. Los registros de decisiones de arquitectura (`docs/adr/`) no se renderizan aquí.

## Despliegue público

El entorno de demostración vive en **Render** (`render.yaml`): Postgres 15 gestionado, backend Docker con `preDeployCommand: python db/aplicar_migraciones.py`, y el sitio estático de Astro (`pnpm build`, publica `dist/`). Región `oregon` para los tres, red privada entre API y base.

`main` es la rama que Render despliega. Integra solo desde `dev`. Las ramas de trabajo abren PR contra `dev`.

Al publicar una versión nueva del frontend hay que subir `VERSION` en `web/public/sw.js` para invalidar el shell cacheado del service worker.
