---
titulo: "De dónde salen los datos"
descripcion: "MINSAL (boletines y tablero), OpenDengue, Open-Meteo y NOAA ONI: ventanas, licencias, procedencia y cómo se citan en el esquema."
orden: 4
categoria: "Datos y método"
---

Todo conteo y toda variable ambiental en EPI-Aetheris sale de una fuente pública, citable, con `fuente_id` en el esquema. Esta página resume procedencia, ventanas y licencias para un lector externo.

## MINSAL — boletines epidemiológicos

**Qué es.** PDF semanales de `salud.gob.sv` (WordPress Download Manager), fuente citada VIGEPES. 14 departamentos. **264 archivos** en la ventana parseable **2018–2023**. 2020 no se descargó para la rama departamental (subregistro por covid y riesgo de extracción). A partir de 2024 el dashboard `boletin.salud.gob.sv` está bloqueado por Cloudflare Bot Management: no hay fuente departamental automatizable. Revisado a mano, el tablero de MINSAL tampoco publica dengue por departamento: la serie departamental termina en 2023.

**Cobertura real.** No son 52/52 semanas con tabla departamental. Boletines de Semana Santa, Fiestas Agostinas y Fin de Año no publican esa tabla. Algunos boletines de semana normal tampoco (por ejemplo SE18/2023). La cobertura efectiva ronda **~49/52 semanas por año** (48/52 en 2023). 2018 y 2019 además tienen semanas "no elaboradas" según nota oficial de MINSAL.

**Dos familias de tabla**, detectadas por documento — nunca por año:

- Familia A: columnas Probable / Confirmado / Tasa × 100.000.
- Familia B: Probable (semana actual) / Confirmado (semana − 1), sin tasa.

Probable y confirmado son **acumulados desde SE1** hasta la semana que declara el encabezado, y además corresponden a **semanas distintas** dentro de la misma fila. El pipeline desacumula por diferencias entre boletines consecutivos. Un hueco no se reparte; una diferencia negativa (corrección retroactiva de MINSAL, 19 en el corpus, magnitud −1 o −2) se registra aparte y se excluye de la serie.

Otras reglas de la fuente, verificadas al leer los PDF:

- El año impreso dentro del documento no es fiable; el año se toma del nombre de archivo y del índice.
- Celda en blanco = **0**, no dato ausente.
- La fila "Otros países" existe y a veces entra en el total impreso, a veces no: el validador prueba ambas convenciones por boletín.
- Republicaciones `_v2`…`_v4` son el mismo boletín; gana la versión más alta (ADR 0004).

Los mismos PDF publican **IRA**, **neumonías** (conteo notificado departamental) y la tabla nacional de **vigilancia laboratorial** de influenza / VSR / SARS-CoV-2.

Desde 2025, IRA y neumonías tienen además una serie nacional tomada del tablero de MINSAL (ADR 0021), que el observatorio respiratorio muestra aparte de la departamental. En neumonías, la suma de los departamentos de los boletines promedia entre 500 y 780 casos por semana según el año, y el tablero publica entre 130 y 430 en 2025 y 2026; no se ha comprobado si las dos fuentes usan la misma definición.

**Licencia / uso.** Publicación oficial del Ministerio de Salud de El Salvador. El proyecto los usa como dato agregado de vigilancia, sin republicar los PDF (los crudos no se versionan).

## MINSAL — tablero de vigilancia

**Qué es.** Desde 2024 MINSAL publica sus cifras en un tablero web (`boletin.salud.gob.sv`) en lugar de los boletines en PDF. Las cifras salen de capturas HAR que una persona guarda desde el navegador; ningún script hace peticiones al sitio (ADR 0021), así que actualizar la serie exige una captura nueva.

**Qué carga el sistema.** Series **nacionales** de 2025 y de 2026 hasta la última semana capturada: sospechosos y confirmados de dengue, y notificados de IRA y neumonías. No hay datos por departamento ni de 2024. Los sospechosos se guardan con `clasificacion = 'sospechoso'` (el nombre de la fuente) y `fuente_id = minsal_tablero`; tienen la misma definición y escala que el total de OpenDengue (5.833 casos en 2025).

**Trampas.** La serie tiene forma de promedio de varias semanas: cambia despacio y una subida tarda en verse completa. La semana 53 de 2025 no aparece publicada y queda sin dato.

## OpenDengue

**Qué es.** `opendengue.org`, extracto `Spatial_extract_V1_3.csv` (~2,8 millones de filas), distribución en Figshare con DOI y licencia, versión 1.3. Para El Salvador, Admin0 (nacional) es semanal desde 2013/2014; Admin1 (departamento) es **mensual y solo 2000–2009** — no se usa para series semanales.

**Qué carga el sistema.** Las 574 filas semanales nacionales, 2014–2024, `clasificacion = 'total'` (ADR 0005). Desde 2025 la serie nacional sigue con los casos sospechosos del tablero de MINSAL (ADR 0021). El campo `case_definition_standardised` vale `'Total'` en el 100 % de las 574 filas semanales de Admin0: OpenDengue no separa probable/confirmado a esta resolución. Insertar ese agregado como `confirmado` mezclaría una cifra de definición propia con la confirmación de laboratorio de MINSAL.

La semana se resuelve por coincidencia exacta de `calendar_start_date` contra `semanas_epidemiologicas.fecha_inicio` (domingo a sábado, PAHO/CDC), no recalculando con `epiweeks` sobre el CSV.

**2020.** La serie nacional **incluye 2020**, con nota. Es deliberado: la exclusión de 2020 gobierna la ventana departamental de comparación, no esta serie.

Las cifras no coinciden al peso con el total MINSAL (2018: 8.448 cargados vs. 8.443 del boletín SE52; 2022: 16.542 vs. 16.529). La diferencia se documenta; no se fuerza a cuadrar, porque la definición de caso no es la misma.

## Open-Meteo

**Qué es.** API gratuita alojada (`archive-api.open-meteo.com`). El self-hosting se evaluó y se descartó: recortar la grilla global no está documentado de forma usable y el volumen (decenas o cientos de GB) excede el hardware del proyecto.

**Modelo por variable** (enmienda del 7 de agosto de 2026; ADR 0006):

| Variables | Modelo | Resolución |
|---|---|---|
| Temperatura máx/mín/media, humedad relativa media, punto de rocío | `era5_land` | 0,1° (~11 km); 14/14 celdas distintas |
| Precipitación acumulada y horas de lluvia | `era5` | 0,25°; 13/14 celdas (La Libertad y San Salvador comparten celda, aceptado) |

`era5_land` no sirve precipitación en la implementación de Open-Meteo. **`best_match` y `era5_seamless` están prohibidos**: mezclan grilla sin decir qué modelo produjo cada variable.

Agregación diaria → semanal: media para las variables de estado, suma para las de precipitación. Semana epidemiológica con `timezone=America/El_Salvador`. Coordenadas: punto representativo del polígono departamental (ADR 0003), no el centro de celda que devuelve la API.

**Uso no comercial.** Los términos de Open-Meteo listan de forma explícita investigación pública en instituciones públicas y contenido educativo. El perfil del proyecto (institución educativa pública, feria técnica, sin publicidad ni suscripciones) entra en ese uso.

**Volumen cargado.** 64.876 filas en el volcado actual: 7 variables × 14 departamentos, de 2014 a la semana 35 de 2026, **incluyendo 2020** (la extensión más allá de 2023 es del ADR 0018). Rate-limit por minuto (`429`) con backoff en el loader.

## NOAA ONI

**Qué es.** Oceanic Niño Index del Climate Prediction Center de NOAA: `https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt`, texto plano público, serie mensual desde 1950 (ADR 0008).

**Qué se guarda.** Variable `oni_anom` (anomalía, no el valor absoluto), región nacional `SV`. El valor mensual se asigna a cada semana epidemiológica cuyo `fecha_inicio` cae en ese mes: es un índice de estado, no un conteo que se fraccione.

Se evaluó como predictor del clasificador retirado y **no se adoptó** en ese conjunto de features. El dato permanece cargado para usos descriptivos.

## Cómo se cita en el esquema

`fuentes_datos.codigo` usa exactamente estas cadenas: `opendengue_v1_3`, `minsal_pdf`, `minsal_tablero`, `open_meteo_era5_land`, `open_meteo_era5`, `noaa_oni`. `variables_ambientales.variable` es texto libre sin `CHECK`: un typo crea una segunda serie en silencio. Las cadenas vigentes son `temp_max`, `temp_min`, `temp_media`, `precipitation_sum`, `precipitation_hours`, `humedad_relativa_media`, `punto_rocio`, `oni_anom`.

Geometría del mapa: geoBoundaries gbOpen SLV ADM1 (OSM vía osm-boundaries.com). El `boundaryLicense` de esta boundary reporta CC BY-SA 2.0. La atribución está en los [términos de uso](/legal/terminos).
