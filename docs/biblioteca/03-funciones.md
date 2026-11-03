---
titulo: "Qué hace hoy"
descripcion: "Catálogo de módulos descriptivos (M1–M4), mapa, observatorio respiratorio, alertas de campo, PWA y pipeline de datos."
orden: 3
categoria: "Cómo funciona"
---

Cada función del sistema tiene un contrato visible: qué mide, qué la alimenta y qué deja fuera. Los módulos M1–M4 se calculan al consultar la API, sin tabla propia y sin cambio de esquema.

## M1 — Idoneidad biofísica (`Iv`)

Responde qué tan favorable es el clima de un departamento-semana para *Aedes aegypti*, en una escala continua 0–1.

Para seguir el cálculo con ejemplos y un laboratorio, ver la [ficha enriquecida de M1](/biblioteca/fichas/m1-idoneidad-biofisica).

**Datos.** Open-Meteo: `temp_media` y `humedad_relativa_media` de ERA5-Land; `precipitation_sum` de ERA5. Semanas con alguna de las tres variables ausente se omiten; no se imputa.

**Fórmulas** (mismas constantes que el experimento de lead time del 18 de agosto de 2026):

- **`f_T`** — forma **Brière**: `f_T(T) = c · T · (T − Tmin) · √(Tmax − T)` dentro de [16 °C, 38 °C], y 0 fuera. La constante de normalización `c` no viene publicada: se resuelve numéricamente (grid fino) para que el máximo de `f_T` en ese intervalo sea 1 (`c ≈ 0,000795`).
- **`f_R`** — **logística** sobre precipitación acumulada a dos semanas (semana actual + anterior, sin envolver entre años): `f_R(R) = 1 / (1 + e^(−k·(R−R0)))`, con R0 = 30 mm y k = 0,1.
- **`f_H`** — **rampa lineal**, estimación propia del equipo: `f_H(HR) = min(1, max(0, HR/50))`. El documento fuente pedía "penaliza humedad relativa bajo 50 %" sin fórmula; ni Mordecai et al. ni la tesis UES especifican una. Se eligió la forma más simple que cumple ese requisito cualitativo.
- **`Iv`** = `f_T × (0,3 + 0,7·f_R) × f_H`.

**Endpoints.** `GET /api/v1/spatial/current` y `GET /api/v1/temporal/{codigo}`.

**Qué no hace.** No clasifica riesgo de brote ni adelanta una temporada.

## M2 — Anomalía climática continua

Responde qué tan inusual es el `Iv` de un departamento-semana respecto de su propia historia climática.

**Método.** Z-score leave-one-out de `Iv` por (departamento, semana del año). Línea base: corpus desde 2014 hasta el año en curso (ADR 0018; los años nuevos entran al pool y mueven los σ históricos), excluyendo el año descrito (anti-fuga). Misma semana exacta, **sin** ventana de semanas vecinas. El reanálisis ERA5 tiene un rezago de unos 5 días.

**Presentación.** Serie continua (`anomaly_sigma`). El umbral Z ≥ 1,5 durante dos semanas consecutivas se usó en el experimento de lead time y se retiró: ese umbral se cruza en el 100 % de los años evaluados y no discrimina.

**Qué no hace.** No emite alerta binaria, no habla de "temporada adelantada" y no expone `lead_time_weeks`.

## M3 — Presión epidemiológica relativa

Responde qué tan alta es la presión de casos **ya observados** en un departamento-semana comparado con su propia historia. Fórmula cerrada por la coordinación el 21 de agosto de 2026.

| Elemento | Valor |
|---|---|
| Variable | `casos_epidemiologicos.conteo`, series **`probable` y `confirmado` por separado** (nunca `total`, nunca fusionadas) |
| Método | Percentil histórico leave-one-out |
| Años base | 2018, 2019, 2021, 2022, 2023 (2020 fuera del baseline) |
| Ventana | ±1 semana, sin envolver entre años |
| Piso | ≥ 3 de los 4 años leave-one-out con alguna observación en la ventana |
| Cortes | P50 y P75 |
| Lectura | ≤ P50 `baja`; P50 < x ≤ P75 `media`; > P75 `alta`, más el percentil crudo 0–100 |
| Insuficiencia | `percentil = null` y una nota; no se interpola |

**Endpoints.** `GET /api/v1/presion/current` y `GET /api/v1/presion/temporal/{codigo}`.

**Qué no hace.** No predice, no usa clima y no produce alerta binaria. Un percentil alto describe lo ya ocurrido frente a la historia observada del departamento.

### Canal endémico

El panel «Canal endémico» dibuja los mismos cortes de M3 como tres bandas: casos hasta el P50 (`baja`), entre el P50 y el P75 (`media`) y por encima del P75 (`alta`), con los casos observados encima. Usa la línea base de M3, que deja fuera el año descrito, así que la banda cambia de un año a otro. Las semanas sin línea base suficiente quedan en blanco.

## M4 — Integridad de la vigilancia

Tres hechos verificables sobre la calidad del dato, **sin combinarlos en un índice**:

- **Completitud geográfica:** cuántos de los 14 departamentos tienen fila esa semana (y cuántas semanas de cada año están completas).
- **Cuadre del boletín:** si la suma departamental coincide con el total nacional publicado en el mismo PDF, y por cuánto difiere cuando no.
- **Antigüedad:** semanas desde la última observación de cada serie (dengue MINSAL, OpenDengue, tablero de MINSAL, clima, IRA y neumonías de los boletines y del tablero, virus). Explica el corte de 2023 sin esconderlo. No es el retraso entre el caso y la publicación del boletín: esa fecha no está en la base.

**Endpoint.** `GET /api/v1/vigilancia/integridad`. Capa del mapa "Integridad de la vigilancia".

**Qué no hace.** No afirma transmisión ni riesgo. Un departamento sin color no es un departamento seguro: es un departamento sin fila esa semana.

## Mapa departamental descriptivo (dengue)

Catorce departamentos, unión por nombre normalizado contra el GeoJSON (el ISO 3166-2 viene vacío en la fuente de límites; ADR 0002). Capa por defecto: casos MINSAL **desacumulados** (probable o confirmado, a elección). Selector de capas para M1, M2 y las dos series de M3.

**Qué no hace.** No pinta un nivel de riesgo departamental. No hay clasificador en producción, nacional ni departamental.

## Observatorio respiratorio

Misma familia de boletines MINSAL, otras tablas, otra semántica. Vive en `/respiratorio` (IRA y neumonías son secciones de esa página; no hay ruta `/ira`).

- **Serie nacional de IRA y de neumonías:** casos notificados por semana según el tablero de MINSAL, desde 2025, con una línea por año, la última semana comparada con la misma de un año antes, las semanas sin publicar y una tabla con los valores. `GET /api/ira/nacional` y `GET /api/neumonias/nacional`.
- **Neumonías:** conteo clínico departamental único, acumulado desde SE1, `clasificacion = 'notificado'`, `tipos_evento = 'neumonia'`. No se mezcla con IRA ni hereda M1–M4.
- **IRA:** el mismo contrato de conteo notificado (ADR 0011), serie acumulada y desacumulada, 2.742 filas en el volcado vigente.
- **Vigilancia laboratorial nacional** (ADR 0012): influenza, VSR y SARS-CoV-2 — muestras, detecciones, positividad. Tabla `vigilancia_virus_respiratorios`. COVID-19 como fila aparece en 2023. No hay mapa departamental de virus.
- Panel de cobertura: qué semanas y qué tablas están presentes.

**Qué no hace.** No computa idoneidad, anomalía ni presión; esas fórmulas están cerradas solo para dengue.

## Alertas de campo

Decisiones **humanas** persistidas (ADR 0013, operable en ADR 0015): tipo (`dengue` | `respiratorio`), nivel (`informativo` | `atencion` | `intensificacion`), título, contexto, indicaciones, fuente, autor, vigencia, `activa`, y etiqueta opcional (`test` | `simulacro` | `historica`). La vista pública `/alertas` lista solo `activa = true` sin etiqueta. `GET /api/alertas` conserva ese contrato por defecto.

La escritura va por `POST /api/alertas` y `PATCH /api/alertas/{id}` con un secreto de entorno (`ALERTAS_TOKEN`, Bearer). No hay tabla de usuarios ni `DELETE`: una alerta emitida se desactiva, no se borra. El archivo vive en `/alertas/archivo`; el formulario mínimo en `/alertas/nueva` no está en la navegación.

Los cinco campos clínicos (ADR 0014) se llenaron por tipo con transcripción citada de VIGEPES/OPS (migración `0011`). Lo que no tiene fuente queda `null` — por ejemplo signos de alarma y criterios de referencia en respiratorio. El sistema no inventa teléfono ni correo.

**Qué no hace.** No se genera desde M1–M4 ni desde el clasificador retirado.

## PWA / offline

Service worker escrito a mano (`web/public/sw.js`), sin dependencias. El shell usa stale-while-revalidate. **`GET /api/alertas` es network-first**: una alerta ya apagada tiene consecuencia clínica, así que la red gana y el cache es último recurso. Lo servido desde cache lleva `_desde_cache: true` en el cuerpo JSON (no en una cabecera: la API es de otro origen y CORS filtra cabeceras propias) y la vista muestra el sello de frescura.

**Qué no hace.** No sirve una alerta apagada como si siguiera vigente cuando hay red.

## Pipeline de datos

- Descarga de **264 PDF** de boletines MINSAL (2018–2023, 2020 no descargado), validados por firma de bytes `%PDF`.
- Parser de tablas departamentales: dos familias de esquema, detectadas **por documento** (presencia de la columna de tasa), nunca por rango de año. Probable/confirmado son acumulados desde SE1; se desacumulan por diferencias. Huecos y correcciones retroactivas no se reparten ni se fabrican.
- Bitácora `boletines_procesados` (ADR 0004, 0007): `ok`, `ausencia_esperada`, `sin_texto_extraible`, `revision_manual`, `error`, `pendiente`.
- Carga de OpenDengue nacional (`clasificacion = 'total'`, ADR 0005) y de Open-Meteo (ERA5-Land + ERA5, ADR 0006).
- Carga de las series nacionales del tablero de MINSAL desde capturas HAR guardadas a mano desde el navegador (`clasificacion = 'sospechoso'` para dengue, ADR 0021). Ningún script hace peticiones al tablero.
- Semanas epidemiológicas PAHO/CDC (MMWR) vía la librería `epiweeks`.

**Qué no hace.** No rellena una celda vacía de MINSAL como dato ausente (en esa fuente, vacío = 0) ni convierte un hueco real de vacaciones en un conteo interpolado.
