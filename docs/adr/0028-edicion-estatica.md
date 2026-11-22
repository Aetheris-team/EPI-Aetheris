# 0028 - Edición estática de solo lectura

**Estado:** Aceptado

## Contexto

El volcado versionado del ADR 0010 ya reúne los datos de los boletines de
MINSAL, OpenDengue y Open-Meteo. Los artefactos precalculados reúnen las series
de clima y dengue, la predicción nacional y su retrospectiva. Astro compila
las páginas como HTML estático, pero el navegador consultaba FastAPI para
cargar los conjuntos de datos y el sitio dependía de una base en ejecución.

## Decisión

- La edición usa archivos JSON del mismo origen y un feed Atom estático.
  `compose.exportacion.yml` arranca un PostgreSQL y un FastAPI temporales para
  exportar desde el volcado versionado. Los contratos públicos de lectura
  conservan las fórmulas, la unidad de cada serie, la procedencia y los huecos.
- El manifiesto `datos/corte.json` indica la fecha de la ingesta más reciente,
  la huella de los archivos exportados y la última semana observada de cada
  serie. La antigüedad del módulo M4 usa esa fecha como referencia.
- Las consultas por semana se agrupan por año. La procedencia de los
  boletines se agrupa por año y departamento. El navegador selecciona la
  semana, serie o filtro dentro del archivo correspondiente.
- Las páginas de alertas presentan un corte histórico. Esta edición retira
  las rutas web de alta de alertas, cuentas y administración. El exportador
  consume únicamente lecturas públicas del conjunto versionado.
- El servidor web entrega `web/dist/`. En Docker, el Compose de ejecución
  declara únicamente nginx en el puerto de Dockyard. El alojamiento también
  puede servir los archivos directamente desde su raíz.

## Consecuencias

Publicar un corte nuevo requiere preparar sus archivos y recompilar. El CI
verifica el despliegue con el servicio web como único contenedor. La caché del
service worker distingue el corte por su huella y prioriza las respuestas del
alojamiento cuando hay conexión. La edición ofrece consulta histórica dentro
de las coberturas publicadas en `/estado`.
