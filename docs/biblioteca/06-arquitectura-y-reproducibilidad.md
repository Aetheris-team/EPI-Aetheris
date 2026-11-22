---
titulo: "Arquitectura y reproducibilidad"
descripcion: "Cómo se generan los datos y se publica una edición estática de EPI-Aetheris."
orden: 6
---

EPI-Aetheris se reproduce con su código y el volcado de datos reales versionado.
La edición que se publica contiene HTML, JavaScript, CSS y archivos de datos.

## Preparación del corte

El exportador restaura el esquema desde `db/migrations/` y los datos desde
`db/seed/seed_datos_reales.sql` en un PostgreSQL temporal (ADR 0010). Las
consultas y los módulos existentes de FastAPI calculan las series y preservan
la procedencia de los boletines, la cobertura y los valores ausentes. Los
resultados de clima-dengue y de predicción se leen de
`backend/api/datos/`, donde ya están precalculados.

El corte registra la fecha de la ingesta más reciente del volcado. En
[Estado del servicio](/estado) aparecen su versión y la última semana que
publicó cada serie. La antigüedad se mide respecto de la fecha de corte.

## Compilación y servicio web

Desde la raíz del repositorio:

```bash
./scripts/exportar-datos-estaticos.sh
docker compose up -d --build
```

El sitio queda en [http://localhost:8401](http://localhost:8401). El Compose
de ejecución expone un único servicio web. La compilación también se puede
hacer con Node.js 24 y pnpm desde `web/`. El directorio `web/dist/` se puede
publicar directamente en un alojamiento estático.

## Actualización de datos

Para publicar otra edición, primero se actualiza el volcado y los artefactos
precalculados que correspondan. Se repiten la exportación y la compilación.
Cada versión conserva los datos públicos agregados y las fechas de sus
fuentes. Los avisos de campo se consultan en el
[archivo de alertas](/alertas/archivo).
