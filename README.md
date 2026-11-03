# EPI-Aetheris

Sistema descriptivo de vigilancia epidemiológica para El Salvador: dengue y
eventos respiratorios (IRA, neumonías, virus) por departamento, con alertas,
análisis y predicción a corto plazo a partir de datos públicos de MINSAL.
Esta es la versión preparada para alojarse en Dockyard: se levanta con un solo
comando y trae sus datos reales incluidos.

| Dato | Valor |
|---|---|
| Proyecto | EPI-Aetheris |
| Equipo responsable | Equipo 4 |
| Interfaz web | http://localhost:8401 |
| Usuarios de prueba | No hay: el sitio es público y las cuentas están apagadas |

## Inicio rápido

Requisitos: Docker con Docker Compose y conexión a internet en la primera
compilación (descarga dependencias y fuentes).

```bash
docker compose up -d --build
```

La primera vez tarda unos minutos en compilar. Después, el sitio abre en
http://localhost:8401 con los datos ya cargados.

Para apagarlo: `docker compose stop`. Para borrar también los datos y volver a
empezar: `docker compose down -v`.

## Cómo está armado

Tres servicios en `docker-compose.yml`; solo se publica el puerto 8401 (rango
del Equipo 4: 8401–8409).

| Servicio | Imagen | Qué hace |
|---|---|---|
| `db` | `db/Dockerfile` (PostgreSQL 15) | Crea el esquema con `db/migrations/` y carga el volcado de datos reales de `db/seed/` (ADR 0010) en el primer arranque. No publica puerto |
| `backend` | `backend/Dockerfile` (FastAPI) | API en el puerto 8000 interno. Espera a que la base esté lista |
| `web` | `web/Dockerfile` (Astro → nginx) | Sirve el sitio compilado en el 8401 y reenvía `/api` al backend, así el navegador usa un solo origen |

El volcado no trae las series nacionales del tablero de MINSAL de 2025–2026
(ADR 0021); se cargan con `backend/ingestion/cargar_minsal_tablero.py`.

`.env.example` documenta las variables. Todas tienen un valor por defecto en el
compose, así que el archivo `.env` es opcional.

## Estructura

```
backend/api/       → API FastAPI (punto de entrada: api/main.py:app; endpoints en api/rutas/)
backend/ingestion/ → pipeline de ingesta y experimentos de validación (no entra en la imagen)
web/               → frontend Astro + Tailwind + ECharts; nginx.conf sirve el sitio compilado
db/                → Dockerfile de la base, migraciones (migrations/) y volcado de datos (seed/)
docs/adr/          → Architecture Decision Records
docs/biblioteca/   → documentos públicos de /biblioteca
docs/experimentos/ → experimentos firmados que respaldan un ADR
docs/seguridad/    → respuesta a incidentes y roles de base de datos
```

## Desarrollo sin Docker

- API: en `backend/`, `pip install -r requirements.txt -r requirements-dev.txt`
  y `uvicorn api.main:app --reload` (necesita una base Postgres y las variables
  `POSTGRES_*`).
- Frontend: en `web/`, `pnpm install && pnpm dev` (http://localhost:4321). En
  ese modo llama a la API en `http://localhost:8000`, o en la que indique
  `PUBLIC_API_URL`.

Las instrucciones para agentes y el contexto técnico están en `AGENTS.md`.
