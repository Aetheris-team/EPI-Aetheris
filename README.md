# EPI-Aetheris

Sistema descriptivo de vigilancia epidemiológica para El Salvador,
contenedorizado y reproducible a costo cero. Piloto con dengue;
arquitectura agnóstica al tipo de evento y región.

## Stack

- **Backend:** FastAPI + psycopg2 (PostgreSQL raw SQL)
- **Frontend:** Astro 7 + TypeScript + Leaflet
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

La base queda poblada con datos reales desde el primer arranque (volcado versionado de casos/clima/boletines, `db/seed/`, ~4,4 MB — ver `docs/adr/0010-versionar-volcado-de-datos-reales.md`), sin depender de red ni de re-parsear los boletines.

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
backend/api/       → FastAPI app (punto de entrada: api/main.py:app)
backend/ingestion/ → pipeline de ingesta y experimentos de validación
                     (data/interim/modelo/: artefactos versionados del clasificador retirado, issue #72)
web/               → frontend Astro
db/migrations/     → schema SQL (cargado automáticamente al iniciar db)
db/seed/           → volcado de datos reales (ADR 0010)
docs/adr/          → Architecture Decision Records
```
