# EPI-Aetheris

Sistema descriptivo de vigilancia epidemiológica para El Salvador,
contenedorizado y reproducible a costo cero. Piloto con dengue y eventos
respiratorios (IRA, neumonías, virus); arquitectura agnóstica al tipo de
evento y región. Sitio público: https://epi-aetheris.dev

## Stack

- **Backend:** FastAPI + psycopg2 (PostgreSQL raw SQL)
- **Frontend:** Astro 7 + TypeScript + Tailwind 4 + ECharts (se desarrolla en aetheris-nitor; ver abajo)
- **Base de datos:** PostgreSQL 15
- **Infra:** Docker Compose (`db` y `backend` por defecto; `web`, `mailpit` y `e2e` bajo perfiles)

## Requisitos

- Docker + Docker Compose
- Git

## Clonar

```bash
git clone git@github.com:aetheris-team/EPI-Aetheris.git
cd EPI-Aetheris
```

## Inicio rápido

```bash
cp .env.example .env
docker compose up -d
```

- API: http://localhost:8000
- DB: localhost:5432

El frontend no arranca con `docker compose up`. Se levanta desde `web/` con `pnpm install && pnpm dev` (http://localhost:4321). Para usar el contenedor: `docker compose --profile web up -d web`.

La base queda poblada con datos reales desde el primer arranque (volcado versionado de casos/clima/boletines, `db/seed/`, ~4,4 MB — ver `docs/adr/0010-versionar-volcado-de-datos-reales.md`), sin depender de red ni de re-parsear los boletines. El volcado no trae todavía las series nacionales del tablero de MINSAL de 2025–2026 (ADR 0021); se cargan con `backend/ingestion/cargar_minsal_tablero.py`.

## Variables de entorno

La tabla cubre la base de datos; `.env.example` documenta el resto (CORS, rate limiting, alertas, cuentas). `docker compose` exige las tres primeras en `.env`: no tienen default.

| Variable | Descripción | Valor en `.env.example` |
|---|---|---|
| `POSTGRES_USER` | Usuario de BD | `aetheris_user` |
| `POSTGRES_PASSWORD` | Contraseña de BD | `aetheris_secure_password` |
| `POSTGRES_DB` | Nombre de la BD | `epi_aetheris` |
| `POSTGRES_HOST` | Host de la BD | `db` |
| `POSTGRES_PORT` | Puerto de la BD | `5432` |

## Estructura

```
backend/api/       → FastAPI app (punto de entrada: api/main.py:app; endpoints en api/rutas/)
backend/ingestion/ → pipeline de ingesta y experimentos de validación
                     (data/interim/modelo/: artefactos versionados del clasificador retirado, issue #72)
web/               → frontend Astro: copia sincronizada de aetheris-nitor (ver abajo)
db/migrations/     → schema SQL (cargado automáticamente al iniciar db)
db/seed/           → volcado de datos reales (ADR 0010)
docs/adr/          → Architecture Decision Records
docs/biblioteca/   → documentos públicos de /biblioteca
docs/experimentos/ → experimentos firmados que respaldan un ADR
docs/seguridad/    → respuesta a incidentes y roles de base de datos
docs/despliegue-render.md → despliegue del backend en Render
```

## Frontend y aetheris-nitor

El frontend se desarrolla en [aetheris-nitor](https://github.com/aetheris-team/aetheris-nitor), que es el sitio que se publica. Un workflow de ese repo copia `src/`, `tests/`, `public/` y la configuración a `web/` y abre aquí un PR (`chore/web-sincronizado-auto`). Los cambios al frontend van en aetheris-nitor: lo que se edite solo en `web/` se pierde en la siguiente sincronización. `docs/biblioteca/` no se sincroniza; cada repo tiene su copia.

Las instrucciones para agentes y el contexto técnico vigente están en `AGENTS.md`.
