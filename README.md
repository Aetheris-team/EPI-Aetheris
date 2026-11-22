# EPI-Aetheris

Sitio de vigilancia epidemiológica descriptiva de El Salvador. Permite consultar
datos públicos agregados de dengue, eventos respiratorios y clima, junto con el
archivo de alertas y la predicción de dengue desde la última semana observada.

## Generar el sitio

Desde la raíz del repositorio, con Docker y Docker Compose:

```bash
./scripts/exportar-datos-estaticos.sh
docker compose up -d --build
```

Abre [http://localhost:8401](http://localhost:8401). El primer comando restaura el
volcado versionado en una base temporal y calcula los archivos públicos en
`web/public/datos/`. Usa los JSON ya calculados para clima-dengue y predicciones.
El exportador termina y limpia sus contenedores antes del arranque del sitio.
`docker compose stop` detiene el servidor web.

## Compilar o publicar sin un contenedor web

Después de generar los datos, usa Node.js 24 y pnpm 9.15.9 desde `web/`:

```bash
cd web
corepack enable
pnpm install --frozen-lockfile
pnpm build
pnpm preview
```

Publica el contenido de `web/dist/` en la raíz de un alojamiento estático.
El sitio usa rutas de directorio como `/dengue` y un `404.html` para rutas
desconocidas. Configura el servidor para resolver esas rutas con sus
`index.html`. El workflow **Sitio estático** entrega el mismo directorio
como artefacto `sitio-estatico`. El artefacto contiene las páginas, gráficos,
archivos JSON, feed Atom y recursos que usa el navegador.

## Corte y fuentes

La fecha de corte corresponde a la ingesta más reciente del volcado. Cada serie
conserva su propia última semana observada, fuente y valores faltantes. Consulta
el corte y la cobertura en `/estado` o en `/datos/corte.json`. Para publicar otro
corte, actualiza primero el volcado de fuentes públicas y los artefactos
precalculados que correspondan, repite la exportación y recompila.

La edición es de solo lectura. Las alertas se presentan como registros
históricos. Las vistas de consulta, filtros, exportaciones y gráficos funcionan
con los archivos del sitio. El servidor de producción necesita únicamente esos
archivos. La configuración actual está en el [ADR 0028](docs/adr/0028-edicion-estatica.md).

## Código

- `web/` contiene Astro, TypeScript, Tailwind y ECharts.
- `backend/api/` contiene las consultas y los módulos de cálculo que reutiliza
  el exportador.
- `db/migrations/` y `db/seed/` contienen el esquema y el volcado versionado.
- `docs/biblioteca/` contiene los documentos que publica Astro.
