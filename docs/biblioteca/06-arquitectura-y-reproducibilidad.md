---
titulo: "Arquitectura y reproducibilidad"
descripcion: "Servicios Docker, volcado de datos reales versionado y un comando para levantar el sistema: git clone y docker compose up."
orden: 6
categoria: "Cómo funciona"
---

EPI-Aetheris se replica con el repositorio y Docker. No hay API de datos de pago en el núcleo, no hay SaaS obligatorio y el costo de replicación para un tercero tiende a cero.

## Servicios

`docker-compose.yml` declara tres servicios y publica un solo puerto, el **8401**. Así el sistema puede alojarse junto a otros proyectos en la misma máquina sin chocar con ellos:

| Servicio | Qué es | Puerto |
|---|---|---|
| `db` | PostgreSQL 15 con el esquema y los datos dentro de su imagen (`db/Dockerfile`) | interno |
| `backend` | FastAPI + `psycopg2` (sin ORM). Entrada: `backend/api/main.py`; endpoints en `backend/api/rutas/` | interno (8000) |
| `web` | Sitio de Astro + TypeScript + Tailwind + ECharts compilado y servido por nginx, que reenvía `/api` al backend | 8401 |

El esquema se carga desde `db/migrations/*.sql` **una sola vez**, sobre volumen vacío (`docker-entrypoint-initdb.d`). En el mismo arranque se carga `db/seed/seed_datos_reales.sql`: un volcado `pg_dump --data-only` de las tablas de hechos (ADR 0010). Quien clona obtiene el sistema **con datos reales**, no un cascarón vacío.

Hardware de referencia: 4 GB de RAM, CPU de dos núcleos x86-64, ~10 GB de disco.

## Cómo levantarlo

```bash
docker compose up -d --build
```

El sitio queda en `http://localhost:8401` y la API en el mismo origen, bajo `/api`. Todas las variables tienen valor por defecto; `.env.example` las documenta (no commitear `.env`).

Fuera de Docker (desarrollo):

- Backend: `cd backend && pip install -r requirements.txt && uvicorn api.main:app --reload` (virtualenv).
- Web: `cd web && pnpm install && pnpm dev` (pnpm vía Corepack, v9; no `npm`).

Los datos crudos (boletines en PDF, capturas del tablero) no se versionan. El volcado en `db/seed/` es la excepción deliberada que hace cierta la promesa de un comando. El pipeline que los procesa no viaja en esta versión del sitio: vive en el repositorio original del proyecto.

## Qué incluye el volcado

Foto en texto plano (~5,7 MB), sin PDF crudos. Incluye la serie nacional del tablero de MINSAL (2025–2026, ADR 0021). Tablas de hechos: `semanas_epidemiologicas`, `boletines_procesados`, `casos_epidemiologicos`, `variables_ambientales`, y desde la foto del 1 de septiembre de 2026 también `vigilancia_virus_respiratorios` e IRA/neumonías (2.742 / 2.749 filas más 3.028 de vigilancia viral).

**No** incluye `regiones`, `tipos_evento` ni `fuentes_datos`: esas tres las siembran las propias migraciones. Tampoco `schema_migrations`: esa tabla la crea el runner de migraciones, no `initdb`.

Es una foto fija. Regenerarla es manual (`db/generar_seed.sh`) cuando el equipo decide que vale una imagen más reciente. El script post-procesa los `DISABLE/ENABLE TRIGGER ALL` de `pg_dump` para que el volcado se pueda cargar también con un rol que no sea superuser.

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

## Alojamiento

Esta versión se aloja en **Dockyard**, la plataforma local donde el docente enciende y apaga los proyectos de la especialidad. Dockyard ejecuta el mismo `docker compose up -d` desde la carpeta del proyecto, así que lo que funciona con ese comando en una carpeta recién clonada funciona allí.

`main` es la rama que se entrega. Integra solo desde `dev`. Las ramas de trabajo abren PR contra `dev`.

Al publicar una versión nueva del frontend hay que subir `VERSION` en `web/public/sw.js` para invalidar el shell cacheado del service worker.
