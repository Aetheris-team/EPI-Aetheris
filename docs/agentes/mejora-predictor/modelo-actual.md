# Modelo de predicción de EPI-Aetheris: qué es, con qué datos de El Salvador y qué se puede afirmar

Documento interno. Fecha de la revisión: 2026-10-02. Estado del código revisado: monorepo `EPI-Aetheris` en `main` (último commit 88a4ef5, 2026-10-01) y frontend `aetheris-nitor` en la rama `feat/toolbar-autocontraer` (914a682).

Rutas: `M:` = `/home/over/orca/EPI-Aetheris` (monorepo, backend, ADR, experimentos). `N:` = `/home/over/orca/aetheris-nitor` (frontend y Biblioteca pública vigente). Las referencias llevan la forma `archivo:línea`.

Etiquetas de cada afirmación:

- `[H]` hecho verificado leyendo el código, los artefactos JSON versionados o la base semilla.
- `[D]` documentado en ADR, experimento o Biblioteca, sin verificar en código (o con la salida local gitignored como único respaldo).
- `[I]` inferencia mía.

Comandos ejecutados en la revisión (todos de solo lectura): `grep`, `sed`, `git log/show` (incluido `git show ef698c8^:` para recuperar documentos podados), lectura de los JSON de `M:backend/api/datos/` y de `M:backend/ingestion/data/interim/nowcast/` con Python, y conteos con `awk` sobre `M:db/seed/seed_datos_reales.sql`. No se corrió ningún modelo, backtest ni script de ingestión; no se tocó base de datos ni servicio; no se consultó la red. No se leyó `/home/over/SisDocs/`.

## Índice

1. Resumen ejecutivo
2. Definición exacta del modelo
3. Datos
4. Qué es específico de El Salvador
5. Evaluación y validación
6. Comparación con alternativas
7. Limitaciones y cómo las comunica el sitio
8. Preguntas difíciles anticipadas
9. Qué debe buscar la investigación externa
10. Inventario de fuentes consultadas
11. Huecos y "No verificado"

---

## 1. Resumen ejecutivo

El modelo es un pronóstico probabilístico de horizonte corto del conteo semanal nacional de dengue de El Salvador. Parte de la última semana epidemiológica publicada y entrega, para cada una de las 8 semanas siguientes (h = 1 a 8), 23 cuantiles de la distribución predictiva (el conjunto de los hubs de CDC y OPS), de los que el sitio dibuja la mediana y los rangos del 50 % y del 95 %. No es un modelo departamental, no clasifica riesgo y no anticipa temporadas. `[H]` `M:backend/ingestion/nowcast_estimacion_dengue.py:67-72`, `M:docs/adr/0020-nowcast-corto-plazo.md:40-47`.

Hay dos métodos según el tramo de la serie. Hasta 2024-S52, con la serie de OpenDengue, el método es M0: gradient boosting con pérdida cuantílica (un `HistGradientBoostingRegressor` por cuantil y por horizonte), con ocho rezagos del propio conteo en `log1p`, estacionalidad anual, media nacional de siete variables de clima de los 14 departamentos, anomalía ONI y año, reajustado cada dos semanas con ventana expansiva desde 2014 y calibrado con un heurístico conformal (CQR-r). Desde 2025-S1, con la serie suavizada del tablero de MINSAL, la predicción que se publica es C: la mezcla 50/50, en `log1p` y por cuantil, de M0 y de una regla de tendencia amortiguada (φ = 0,8) que no entrena nada. `[H]` `M:backend/ingestion/experimento_nowcast_corto_plazo.py:94-103,246-287`, `M:backend/ingestion/experimento_nowcast_tendencia.py:55-113`, `M:backend/ingestion/nowcast_tablero_dengue.py:92-93`.

Los datos son de El Salvador de punta a punta: la serie nacional de dengue de OpenDengue V1.3 (2014-2024, 574 semanas, que coincide en definición y casi en cifra con los casos sospechosos de MINSAL), la serie de sospechosos del tablero de MINSAL (2025-S1 a 2026-S37, capturada a mano), el clima semanal de Open-Meteo para los 14 departamentos y el índice ONI de NOAA. `[H]` `M:backend/ingestion/experimento_nowcast_corto_plazo.py:132-208`.

La evaluación es forward-chaining con ventana expansiva, aserción anti-fuga con control negativo, control de mutación, repetibilidad y una segunda implementación independiente, con protocolo, métrica y criterio firmados antes de correr. La métrica primaria es el WIS y el skill es `1 - WIS_modelo / WIS_referencia`, con la referencia más fuerte entre persistencia, climatología estacional y persistencia estacional. En 2019 y 2021-2024, a h = 4, M0 calibrado tiene WIS 56,6 frente a 74,6 de la referencia publicada (skill medio por año 0,285; gana 5 de 5 años; cobertura 0,55 al 50 % y 0,88 al 95 %). Contra la referencia limpia, que no aprende de nueve semanas con cero casos, el mismo resultado es WIS 56,6 frente a 58,8 a h = 4 (skill medio por año 0,05, 4 de 5 años) y 78,8 frente a 95,3 a h = 8 (0,18, 4 de 5 años). En 2025-2026, con la serie del tablero, C tiene WIS 19,6 frente a 22,8 de la persistencia suavizada a h = 4 (skill 0,14), pero esos años sirvieron para elegir el método. La prueba prospectiva (20 semanas desde 2026-S38, una sola evaluación hacia febrero de 2027) está pendiente. `[H]` para los artefactos, `[D]` para las corridas (`M:docs/experimentos/experimento-nowcast-mejora.md:204-255`, `M:docs/adr/0020-nowcast-corto-plazo.md:200-204`).

Lo que hace específico al modelo para El Salvador, con respaldo en el repo: el objeto predicho es la serie nacional de El Salvador; el clima se agrega sobre los 14 departamentos con coordenadas propias; el calendario es el MMWR con el que MINSAL numera las semanas; el tratamiento de ceros y vacaciones, la exclusión de 2020 y la verificación de 2014-2015 contra el boletín SE52-2015 de MINSAL responden a rasgos de la vigilancia salvadoreña; y los experimentos multipaís mostraron que la señal regional de las Américas no transfiere a El Salvador (correlación +0,280 con la señal regional, la más baja de 18 países). Ver sección 4.

Límites principales: la validación de C está dentro de muestra y su prueba prospectiva está sin ejecutar; no existe comparación con ningún modelo externo ni publicado; la ventaja de M0 sobre la persistencia limpia es modesta (casi nula a 1 a 3 semanas); el soporte de la robustez ante brotes sin precedente es de un solo año (2019); el aporte del clima a la predicción nunca se midió con una ablación; la cobertura empírica queda por debajo de la nominal (0,39 al 50 % y 0,91 al 95 % en 2025-2026; 0,79 al 95 % solo en 2026); y la serie del tablero es un promedio de unas seis o siete semanas, de modo que lo que se predice es una serie suavizada y no el conteo semanal crudo.

Las cinco afirmaciones que se pueden sostener:

1. El modelo se construyó y se evalúa solo con datos de El Salvador: serie nacional de MINSAL/PAHO (OpenDengue) y del tablero de MINSAL, clima de los 14 departamentos y calendario epidemiológico MMWR (secciones 2 y 3). `[H]`
2. Todas las predicciones evaluadas usan solo información anterior a su semana de partida, con una aserción de código que lo comprueba y un control negativo que demuestra que la aserción detecta fugas, más un control de mutación y repetibilidad (sección 5). `[H]` para el código, `[D]` para el resultado de las corridas.
3. Entre 2019 y 2024, a 5 a 8 semanas, M0 reduce el WIS frente a la persistencia limpia entre 9 % y 17 % (skill medio por año entre 0,12 y 0,18, 4 de 5 años), y frente a la referencia publicada entre 24 % y 28 % (sección 5.3, reducción del WIS agrupado). `[D]` respaldado por `M:backend/ingestion/data/interim/nowcast/mejora_validacion.json` (gitignored).
4. El desempeño se mide con una regla de puntuación propia para predicciones probabilísticas (WIS sobre 23 cuantiles) y con cobertura empírica, y el sitio muestra la cobertura por año en la vista de contraste (`N:src/components/nowcast/ContrasteNowcastDengue.astro:626-638`). `[H]`
5. La prueba prospectiva está firmada, con el script congelado en el commit `40b6ebb78fe670222966a225438155b83ada876d`, un criterio de tres condiciones y un corte en 2027-S05 (`M:docs/experimentos/experimento-nowcast-tendencia.md:99-132,166-175`). `[H]` para el commit, `[D]` para el procedimiento.

Las cinco que no se deben hacer:

1. Decir que el modelo publicado desde 2025 es "un modelo entrenado": la mitad de C es una regla de tendencia sin parámetros ajustados, y M0 solo se entrena con la serie nacional de El Salvador (sección 2.4).
2. Decir que supera o iguala a otros modelos de dengue, publicados o de instituciones: no hay ninguna comparación (sección 6).
3. Decir que C está confirmado: 2025 y 2026 sirvieron para elegirlo, la cobertura del 95 % en 2026 (0,79) queda por debajo del 0,85 que exige el criterio, y la prueba prospectiva no se ha corrido.
4. Decir que el clima mejora la predicción, o que la predicción anticipa el inicio de una temporada o un brote: no hay ablación del clima en el nowcast, el clasificador climático se retiró por recall de "alto" igual a 0, y el lead time se retiró como cifra comunicable (secciones 5.7 y 6).
5. Decir que funciona ante un brote sin precedente en la serie: con la historia recortada a 2016+ el skill de 2019 fue -0,32, y el soporte de la conclusión contraria es un solo año.

---

## 2. Definición exacta del modelo

### 2.1 Qué se predice

- Objeto: conteo semanal de la serie nacional de dengue de El Salvador. En M0, `casos_epidemiologicos.conteo` con `clasificacion = 'total'`, región `SV`, fuente `opendengue_v1_3`. `[H]` `M:backend/ingestion/experimento_nowcast_corto_plazo.py:135-148`.
- Desde 2025-S1 la serie mixta añade `clasificacion = 'sospechoso'` de la fuente `minsal_tablero`, sin semanas compartidas con OpenDengue (OpenDengue hasta 2024-S52, tablero desde 2025-S1). `[H]` `M:backend/ingestion/experimento_nowcast_tablero.py:71`, `M:backend/ingestion/nowcast_tablero_dengue.py:88,112-126`; `[D]` `M:docs/adr/0021-fuente-tablero-minsal.md:59-61`.
- Horizonte: h = 1 a 8 semanas desde la última semana publicada (`HORIZONTES = list(range(1, 9))`). Horizontes decisivos de los experimentos: h = 4 (ADR 0020) y h = 4 y h = 8 (experimentos de mejora y de tendencia). `[H]` `M:backend/ingestion/nowcast_estimacion_dengue.py:67-68`.
- Resolución: nacional y semanal. No hay predicción departamental; las series departamentales de dengue terminan en 2023 y el tablero no las publica. `[H]` `M:backend/ingestion/experimento_nowcast_corto_plazo.py:135-148`; `[D]` `N:docs/biblioteca/04-fuentes-de-datos.md:12`.
- Salida: 23 cuantiles (0,01; 0,025; 0,05; 0,10 a 0,95 de cinco en cinco; 0,975; 0,99), la mediana (índice 11) y dos rangos derivados: banda del 50 % = cuantiles 0,25 y 0,75; banda del 95 % = cuantiles 0,025 y 0,975. `[H]` `M:backend/ingestion/experimento_nowcast_corto_plazo.py:79-83`, `M:backend/ingestion/nowcast_estimacion_dengue.py:71-72,119-126`.

### 2.2 Terminología: "nowcast" y "predicción"

El nombre interno (`nowcast`, `/api/nowcast-dengue`, ADR 0020 "Predicción de casos de dengue a corto plazo (nowcast)") designa un pronóstico a 1 a 8 semanas desde la última semana publicada. No corrige retrasos de notificación ni revisiones de la semana en curso: en el código no hay ningún modelo de retraso (sección 8, pregunta 17). El sitio usa la palabra "predicción" (`N:src/pages/prediccion.astro:33`). `[H]`.

### 2.3 M0: gradient boosting cuantílico con calibración CQR-r

Familia: `sklearn.ensemble.HistGradientBoostingRegressor(loss="quantile")`, un modelo por cuantil (23) y por horizonte (8). `[H]` `M:backend/ingestion/experimento_nowcast_calibracion.py:147-153`.

Hiperparámetros, fijados antes de correr y sin barrido contra los años de prueba `[H]` `M:backend/ingestion/experimento_nowcast_corto_plazo.py:93-103`:

| Parámetro | Valor |
|---|---|
| `loss` | `quantile` |
| `max_iter` | 150 |
| `max_leaf_nodes` | 7 |
| `min_samples_leaf` | 20 |
| `l2_regularization` | 1,0 |
| `learning_rate` | 0,05 |
| `early_stopping` | False |
| `random_state` | 0 |

Objetivo: `z = log1p(casos)`. La predicción se devuelve a escala natural con `expm1` y piso 0. `[H]` `M:backend/ingestion/experimento_nowcast_corto_plazo.py:205-208`.

Variables (todas conocidas en el origen t; ninguna contemporánea a t+h) `[H]` `M:backend/ingestion/experimento_nowcast_corto_plazo.py:246-287`:

| Grupo | Variables |
|---|---|
| Rezagos | `z[t]`, `z[t-1]`, ..., `z[t-7]` (8) |
| Resúmenes | media de 4 semanas, media de 8 semanas, momentum `z[t] - z[t-4]` |
| Estacionalidad | seno y coseno de `2π·k·doy/365,25` para k = 1, 2, 3, con `doy` = día del año de la semana objetivo t+h (6) |
| Clima | media de 4 semanas (t-3 a t) de 7 variables, cada una promediada sobre los 14 departamentos: `temp_media`, `temp_max`, `temp_min`, `precipitation_sum`, `precipitation_hours`, `humedad_relativa_media`, `punto_rocio` (7) |
| Contexto | ONI al origen (con arrastre del último valor; 0 si falta) y año de la semana objetivo (2) |

Si falta cualquier insumo climático del origen, el origen no tiene predicción. `[H]` `M:backend/ingestion/experimento_nowcast_corto_plazo.py:268-274`.

Entrenamiento (cómo se obtienen los parámetros del árbol): los pares (X, y) con objetivo de fecha estrictamente anterior a la del origen, objetivo desde 2014 y objetivo distinto de 2020. Ventana expansiva, reajuste cada 2 semanas (`CADENCIA_REAJUSTE = 2`). 2020 se conserva solo como insumo de rezagos. `[H]` `M:backend/ingestion/experimento_nowcast_corto_plazo.py:293-330,76`. La cadencia de 2 semanas es una decisión de costo de cómputo; la segunda implementación midió que 1, 2 o 4 semanas mueven el WIS agrupado menos de 3 % `[D]` (`ef698c8^:docs/experimentos/experimento-nowcast-corto-plazo.md`, sección "Segunda confirmación independiente").

Calibración CQR-r (`M:backend/ingestion/experimento_nowcast_calibracion.py:103-126`) `[H]`:

- Los 52 pares con objetivo más reciente forman el conjunto de calibración (`N_CAL = 52`); los modelos cuantílicos se ajustan con el resto ("proper train"). Mínimos: 120 pares de entrenamiento propio y 40 de calibración; por debajo, el origen no tiene predicción (`MIN_PROPER = 120`, `MIN_CAL = 40`, líneas 88-90).
- Para cada uno de los 11 intervalos centrales, el score de cada par de calibración es cuánto hay que estirar el semiancho (inferior o superior) para cubrir el valor observado, normalizado por el semiancho (conformidad multiplicativa).
- Los scores se winsorizan en el percentil 90 y el factor resultante se topa en 4,0. Con n = 52 el score crudo lo domina una sola semana de brote; sin esos topes el WIS explotaba.
- Consecuencia que el propio experimento declara: para los intervalos del 90, 95 y 98 % la corrección colapsa al mismo factor, de modo que CQR-r es un heurístico y no conformal estricto en los intervalos externos `[D]`.
- Adicionalmente, `_monotona_en_horizonte` impone que el semiancho de cada intervalo no decrezca con h, sin tocar las medianas (`M:backend/ingestion/nowcast_estimacion_dengue.py:129-150`). La evaluación puntúa las predicciones sin ese ajuste; el abanico mostrado lo incluye `[D]` (`M:docs/experimentos/experimento-nowcast-tendencia.md:187-192`).

### 2.4 T y C: la regla de tendencia amortiguada y la mezcla que se publica desde 2025

T (tendencia amortiguada) `[H]` `M:backend/ingestion/experimento_nowcast_tendencia.py:55-62,81-113`:

- Escala `log1p`. Mediana: `z[o] + b · (φ + φ² + ... + φ^h)`, con `b = (z[o] - z[o-3]) / 3` (pendiente medida en 3 semanas, `V_PENDIENTE = 3`) y `φ = 0,8` (`PHI`).
- Cuantiles: la mediana más los cuantiles empíricos de los errores de esa misma regla en todos los pares de la historia con objetivo anterior al origen, desde 2014 y sin 2020 como objetivo.
- Historia promediada: antes de calcular los errores, cada semana hasta 2023 se reemplaza por el promedio de las 7 semanas que terminan en ella (`K_HISTORIA = 7`), para que la historia tenga la forma de la serie del tablero. Desde 2024 la serie ya viene promediada y no se toca.
- No se entrena nada. Los tres números (7, 0,8, 3) se fijaron en una exploración sin firmar sobre 2024-2026 y luego se firmaron como fijos; la exploración reporta que el resultado no depende de ellos dentro de rangos de 5 a 9 semanas, φ de 0,6 a 0,9 y pendiente de 2 a 4 semanas (T a 4 semanas entre +0,19 y +0,24 contra la referencia limpia) `[D]` (`M:docs/experimentos/experimento-nowcast-tendencia.md:41-46`).

C (candidato publicado desde 2025-S1) `[H]` `M:backend/ingestion/experimento_nowcast_mejora.py:147-152`, `M:backend/ingestion/experimento_nowcast_tendencia.py:132-134`:

```
q_C = expm1( 0,5 · log1p(q_M0) + 0,5 · log1p(q_T) )     por cuantil, ordenado, piso 0
```

Peso fijo `PESO_M0 = 0,5`.

Racional de la tendencia amortiguada `[D]` (`M:docs/experimentos/experimento-nowcast-tendencia.md:11-25`): la serie del tablero es un promedio hacia atrás de unas 6 o 7 semanas, de modo que un movimiento tiende a continuar; M0 se entrenó con conteos crudos, donde un salto de una semana suele ser ruido que se deshace, y por eso pierde contra la persistencia a 1 a 5 semanas en 2025-2026. La tendencia amortiguada aprovecha la inercia de la serie suavizada. `[I]`: que ese promedio sea la causa del problema de M0 es la hipótesis del experimento, respaldada por la huella que deja un promedio de 6 o 7 semanas aplicado a OpenDengue crudo, pero el proceso exacto del tablero no se conoce ni se puede recuperar.

Precisión sobre "entrenado": M0 se ajusta con datos de El Salvador en cada reajuste. T no ajusta parámetros: sus cuatro constantes están fijas y sus cuantiles son errores empíricos de la propia regla. C hereda ambas propiedades. `[H]`.

Qué reproduce el artefacto servido: el abanico que se muestra es la predicción C que se va a puntuar, con los anchos hechos monótonos en h; el backtest y el bloque `desempeno` cubren 2025 y 2026 a h = 4 contra la persistencia suavizada, con `dentro_de_muestra: true`. `[H]` `M:backend/ingestion/nowcast_tablero_dengue.py:176-233`.

### 2.5 Qué hacen los orígenes sin historia o con huecos

- Sin historia suficiente (menos de 160 pares): el artefacto retrospectivo marca el origen con `motivo: "historia_insuficiente"` y no rellena con persistencia. La primera semana con predicción es 2017-S13. `[H]` `M:backend/ingestion/nowcast_retrospectivo_dengue.py:97`, `M:backend/api/datos/nowcast_dengue_retrospectivo_opendengue.json` (`primera_semana_con_prediccion`).
- 2025-S53 no está publicada por el tablero: los orígenes de 2025-S53 a 2026-S7 (cuya ventana de 8 semanas la incluye) quedan con `motivo: "hueco_en_serie"`. `[H]` `M:backend/ingestion/nowcast_tablero_dengue.py:90`, `M:docs/adr/0020-nowcast-corto-plazo.md:197-199`.

### 2.6 Relación con los módulos descriptivos

El pronóstico no usa M1, M2, M3 ni M4, ni sus cortes como objetivo o variable (`M:docs/adr/0020-nowcast-corto-plazo.md:44-47`; la lista de variables de `features_en` no contiene ninguna). `[H]`.

| Módulo | Qué es | Relación con la predicción |
|---|---|---|
| M1, Iv | `f_T × (0,3 + 0,7·f_R) × f_H`: curva de Brière de temperatura (16 a 38 °C, c ≈ 0,000795), logística de lluvia acumulada a 2 semanas (R0 = 30 mm, k = 0,1) y rampa lineal de humedad `min(1, max(0, HR/50))`, esta última propuesta por el equipo y no citada (`N:docs/biblioteca/03-funciones.md:18-25`) `[D]` | Ninguna. No clasifica riesgo ni anticipa temporadas. |
| M2, anomalía | Z-score de Iv por departamento y semana del año, leave-one-out, línea base 2014 al año en curso, misma semana exacta `[D]` | Ninguna. El umbral Z ≥ 1,5 durante dos semanas se retiró porque se cruzaba en todos los años evaluados. |
| M3, presión | Percentil histórico leave-one-out de `probable` y `confirmado` por separado; años base 2018, 2019, 2021-2023; ventana ±1 semana; mínimo 3 de 4 años; cortes P50 y P75 `[D]` | Ninguna. |
| Canal endémico | Los cortes de M3 dibujados como tres bandas `[D]` (`N:docs/biblioteca/03-funciones.md:58-60`) | Ninguna. |
| M4, integridad | Completitud geográfica, cuadre del boletín, antigüedad de cada serie `[D]` | Ninguna. |

Los módulos M1 a M3 solo están definidos para dengue y se calculan al consultar la API. El pronóstico, en cambio, se precomputa y se versiona como JSON.

### 2.7 Artefactos y endpoints

- `M:backend/api/datos/nowcast_dengue.json` (servido), `nowcast_dengue_retrospectivo.json` (servido), y las dos bases de M0 `nowcast_dengue_opendengue.json` y `nowcast_dengue_retrospectivo_opendengue.json`. Generación: `nowcast_estimacion_dengue.py` y `nowcast_retrospectivo_dengue.py` escriben la base de M0; `nowcast_tablero_dengue.py` la combina con la serie del tablero y escribe lo que sirve la API. `[H]` `M:backend/ingestion/nowcast_tablero_dengue.py:84-85`.
- `GET /api/nowcast-dengue` y `GET /api/nowcast-dengue/retrospectivo` sirven el JSON tal cual, con `RATE_LIMIT_HEAVY`; si el archivo falta responden 200 con `disponible: false` y `motivo`. Nada se recalcula por petición ni se escribe en Postgres. `[H]` `M:backend/api/main.py:564-620`.
- Aviso que viaja con la respuesta: "Prediccion estadistica de horizonte corto sobre la serie nacional de dengue: OpenDengue hasta 2024 y sospechosos del tablero de MINSAL desde 2025. Se extiende desde la ultima semana publicada. Desde 2025 combina el modelo validado con una tendencia amortiguada y esta en prueba con las semanas publicadas desde 2026-S38." `[H]` `M:backend/api/main.py:566-572`.
- Tests del endpoint: `M:backend/api/tests/test_endpoints_nowcast.py:33,44,56` comprueban el contrato `disponible: false`, el aviso y la coherencia del retrospectivo versionado. No hay pruebas unitarias del modelo (`wis`, `features_en`, CQR-r) en `backend/ingestion/tests/`. `[H]`.

### 2.8 Frontend

- Panel de la predicción: `N:src/components/nowcast/PanelNowcastDengue.astro` (1001 líneas). Descripción: "Predicción estadística del conteo nacional de dengue para las próximas 1 a 8 semanas, con intervalo de incertidumbre, a partir de la última semana observada." (líneas 46-50). Nota de ancla (líneas 746-752) y chips de desempeño (759-800).
- Vista de contraste desde cualquier semana: `N:src/components/nowcast/ContrasteNowcastDengue.astro` (801 líneas). Solo existe en el frontend `aetheris-nitor` `[D]` `M:docs/adr/0020-nowcast-corto-plazo.md:165-167`.
- Página: `N:src/pages/prediccion.astro`. Tipos: `N:src/lib/tipos-analisis.ts:296-350`. Acceso a la API: `N:src/lib/analisis-api.ts`.

---

## 3. Datos

### 3.1 OpenDengue V1.3 (serie nacional 2014-2024)

| Aspecto | Contenido |
|---|---|
| Qué es | Extracto `Spatial_extract_V1_3.csv`; se carga la serie nacional de El Salvador, 574 filas semanales, `clasificacion = 'total'`, fuente `opendengue_v1_3` `[D]` `N:docs/biblioteca/04-fuentes-de-datos.md:48-50` |
| Origen primario | PAHO PLISA; la serie 2014-2021 viene de `V1_0_paho_for_opendengue.csv` y la de 2022-2024 de la actualización V1.3 de PLISA, con `case_definition_standardised = "Total"` en todos los años `[D]` (`/home/over/D3v/proyecto26/añañin/experimentos/verificacion-dengue-2014-2015.local.md`, fuera del repo) |
| Cobertura temporal | 2014 a 2024. Departamental de OpenDengue: mensual y solo 2000-2009, no se usa `[D]` |
| Cobertura territorial | Nacional (Admin0) |
| Definición de caso | "Total" de PLISA, dominado por sospechosos. El total de 2019 (27.470) coincide con los sospechosos nacionales que publicó MINSAL ese año; 2018: 8.448 contra 8.443 del boletín de la semana 52; 2022: 16.542 contra 16.529 `[D]` `N:docs/biblioteca/04-fuentes-de-datos.md:56`, `M:docs/adr/0021-fuente-tablero-minsal.md:51-53` |
| Sumas anuales en la base semilla | 2014: 53.460; 2015: 50.169; 2016: 8.789; 2017: 4.297; 2018: 8.448; 2019: 27.470; 2020: 5.450; 2021: 5.752; 2022: 16.542; 2023: 5.788; 2024: 8.552 `[H]` (conteo `awk` sobre `M:db/seed/seed_datos_reales.sql`, sección `casos_epidemiologicos`) |
| Ceros | Hay 9 semanas con 0 casos (2016-S15, S30, S51; 2018-S2; 2020-S53; 2022-S51; 2023-S30, S51, S52), seguidas de una semana con aproximadamente el doble de lo habitual. Son casos no notificados en vacaciones que se desplazan a la semana siguiente, no huecos; se conservan como los publica la fuente `[D]` `M:docs/experimentos/experimento-nowcast-mejora.md:14-17`, memoria `opendengue-ceros-vacaciones.md` |
| Suavizado | OpenDengue 2024 tiene la misma forma lisa que el tablero (desviación respecto a vecinas, en unidades de ruido de Poisson, 0,26 en 2024 frente a 1,2 a 8,3 de 2014 a 2023) `[D]` `M:docs/adr/0021-fuente-tablero-minsal.md:17` |
| Calendario | Cada fila se asigna a su semana epidemiológica comparando `calendar_start_date` con `semanas_epidemiologicas.fecha_inicio` (domingo a sábado, criterio OPS/CDC); 2014 y 2020 tienen 53 semanas `[D]` + `[H]` (`53` semanas en el conteo semilla de 2014 y 2020) |
| Retrasos y revisiones | El extracto es una versión fija; la serie va unos 21 meses detrás del tiempo real. No hay versiones sucesivas de la serie ni semanas con "valor al momento de la publicación" `[H]` (no existe tabla de versiones) `[D]` (ADR 0020, consecuencias) |
| Versionado | Archivo `opendengue_el_salvador_v1_3.csv`, DOI `10.6084/m9.figshare.24259573` `[D]` `M:backend/ingestion/data/README.md:6-16` |
| Licencia | La Biblioteca dice "con DOI y licencia" sin nombrar la licencia; los términos del sitio dicen que los datos de OpenDengue "mantienen las condiciones de su fuente" `N:src/pages/legal/terminos.astro:208-212`. Nombre de la licencia: no verificado en el repo |
| Diferencia con MINSAL | Verificación 2014-2015: OpenDengue 53.196 y 50.169 contra sospechosos de MINSAL 53.290 y 50.144 (boletín SE52-2015) `[D]` (nota local fuera del repo). Las sumas de la base semilla (53.460 en 2014) difieren de esa nota en varios años, ver sección 11 |

### 3.2 Tablero de vigilancia de MINSAL (2025-2026)

| Aspecto | Contenido |
|---|---|
| Qué es | Tablero Superset público en `boletin.salud.gob.sv`; fuente `minsal_tablero`. Se carga con `cargar_minsal_tablero.py` desde archivos HAR guardados por una persona; nunca desde el sitio `[D]` `M:docs/adr/0021-fuente-tablero-minsal.md:7-9,21-31` |
| Capturas | 2025 completo (tablero 10, S1-S52) y 2026 hasta S37 (tableros 04, 05 y 06, que leen los mismos datos), hechas el 2026-09-27; sha256 en `M:backend/ingestion/data/README.md:48-55`. Los HAR no se versionan |
| Cobertura | Solo series nacionales. Sin 2024 en ningún tablero encontrado. Sin dengue por departamento |
| Clase | `sospechoso` (nombre de la fuente "Casos Sospechosos de Dengue"); los confirmados del tablero se cargan como `confirmado`; IRA y neumonías, como `notificado` |
| Escala | 5.833 sospechosos en 2025, al nivel de OpenDengue en 2021 y 2023; confirmados 203 (2025) y 48 (2026) `[D]` `M:docs/adr/0021-fuente-tablero-minsal.md:15-16` |
| Suavizado | Forma de promedio hacia atrás de 6 o 7 semanas. La consulta del tablero solo suma `total_casos` de la tabla `diagnosticos_acumulados`, así que el promedio viene de la tabla de MINSAL. Medido en unidades de Poisson: 0,28 en 2025 y 0,70 en 2026. Aplicar un promedio de 6 o 7 semanas a OpenDengue crudo deja la misma huella y la caída de Semana Santa de 2026 aparece en la semana 13 sin adelantarse. El núcleo exacto no se puede recuperar `[D]` `M:docs/adr/0021-fuente-tablero-minsal.md:46-58`, memoria `tablero-suavizado-7-semanas.md` |
| Saltos | Al cambiar de año: 39 sospechosos en 2025-S52 y 214 en 2026-S1 `[D]` |
| Hueco | 2025-S53 (28 de dic. al 3 de ene.) no se publica; queda sin fila (decisión E) |
| Revisiones | Una cifra por semana, la de la captura más reciente; si dos capturas difieren se informa como revisión de MINSAL y las capturas viejas se conservan (decisión D). Hasta la fecha hay una sola tanda de capturas |
| Acceso | El navegador del usuario es la única vía. `backend/ingestion/minsal/common.py` prohíbe que scripts y agentes hagan peticiones al sitio (Cloudflare bloquea las descargas automáticas desde 2024); no hay PDF desde 2024 `[D]`, memoria `minsal-dashboard-capturas.md` |
| Licencia | Publicación oficial de MINSAL, con las mismas condiciones que los boletines `[D]` `N:docs/biblioteca/04-fuentes-de-datos.md:44` |
| Reproducibilidad | El volcado `db/seed` no incluye el tablero: desde un clon limpio solo se puede regenerar la base de M0 `[D]` `M:docs/adr/0020-nowcast-corto-plazo.md:213-214` |

### 3.3 Boletines PDF de MINSAL (2018-2023, departamental)

| Aspecto | Contenido |
|---|---|
| Qué es | 264 PDF semanales (VIGEPES) de 2018 a 2023, sin 2020 `[D]` `N:docs/biblioteca/04-fuentes-de-datos.md:12` |
| Uso en la predicción | Ninguno directo. Alimenta M3 y el canal endémico (departamental, `probable` y `confirmado`) y sirvió para verificar que el total de OpenDengue coincide con los sospechosos de MINSAL |
| Cobertura | 14 departamentos, unas 49 semanas de 52 por año (48 en 2023); los boletines de Semana Santa, fiestas agostinas y fin de año no traen tabla departamental |
| Desacumulación | Las cifras vienen acumuladas desde la semana 1 y se pasan a semanales restando boletines consecutivos; los huecos no se reparten. Hay 19 diferencias negativas (-1 o -2 casos) que se excluyen como correcciones retroactivas |
| Definición | `probable` y `confirmado` por separado, nunca sumados `[D]` `N:docs/biblioteca/03-funciones.md:43` |
| 2020 | No se descargó: subregistro durante la covid y tablas difíciles de extraer |
| Límite | La serie departamental termina en 2023; el tablero no publica dengue por departamento |

### 3.4 Open-Meteo (clima)

| Aspecto | Contenido |
|---|---|
| Modelos | `era5_land` (0,1°, unos 11 km) para temperatura máxima, mínima y media, humedad relativa media y punto de rocío; `era5` (0,25°) para lluvia acumulada y horas de lluvia. 13 celdas de lluvia para 14 departamentos `[D]` `N:docs/biblioteca/04-fuentes-de-datos.md:62-67` |
| Agregación | Diaria a semanal (media en variables de estado, suma en lluvia) con zona horaria `America/El_Salvador`. Las coordenadas son un punto representativo de cada departamento (ADR 0003) |
| Cobertura en la base semilla | 14 departamentos × 7 variables desde 2014 hasta 2026 parcial. Semanas con clima por departamento: 52 por año (53 en 2014, 2020 y 2025) y 35 en 2026 (hasta la semana 35, mientras el ancla del artefacto servido es 2026-S37, por lo que ese tramo se recargó fuera de la semilla). Filas por año: 5.148 (52 semanas), 5.247 (53 semanas, 2014 y 2020), 5.194 (2025) y 3.430 (2026); en 2014 a 2024 cada semana incluye además una fila de `oni_anom`, y en 2025 y 2026 no hay filas de `oni_anom` en la semilla `[H]` (`awk` sobre la semilla). La Biblioteca 04 dice "35.868 filas, 2018 a 2024", ver sección 11 |
| Uso en el modelo | Media simple sobre los 14 departamentos, media móvil de 4 semanas al origen `[H]` `M:backend/ingestion/experimento_nowcast_corto_plazo.py:166-185` |
| Retraso y revisión | ERA5 llega con unos 5 días de retraso (ADR 0018). Para predecir desde una semana de partida hay que recargar el clima hasta esa semana; ERA5 puede revisar semanas recientes, de modo que el abanico puntuado puede diferir en poco del publicado `[D]` `M:docs/experimentos/experimento-nowcast-tendencia.md:193-194` |
| Licencia | CC BY 4.0; obliga a citar y a indicar que el dato se modificó `N:src/pages/legal/terminos.astro:216-221` |

### 3.5 NOAA ONI

Anomalía mensual del Índice Oceánico de El Niño (`oni_anom`, región `SV`), serie desde 1950 (ADR 0008). El valor del mes se asigna a las semanas que empiezan en ese mes y se arrastra hacia adelante cuando falta. Entra a M0 como una variable (`oni_t`). En la base semilla hay valores de `oni_anom` de 2014 a 2024 (574 semanas) y ninguno de 2025 ni 2026, así que para esas semanas el código arrastra el último valor disponible (`M:backend/ingestion/experimento_nowcast_corto_plazo.py:199-202`, y `oni[-1]` en `nowcast_estimacion_dengue.py:103`); si la base local usada para generar los artefactos tenía ONI de 2025-2026 no se pudo verificar. Se probó como predictor del clasificador retirado y no mejoró sus resultados `[D]` (`N:docs/biblioteca/04-fuentes-de-datos.md:77-83`). En el nowcast no se midió su aporte (sección 5.7).

### 3.6 Otras fuentes

| Fuente | Uso |
|---|---|
| geoBoundaries gbOpen SLV ADM1 (CC BY-SA 2.0) | Límites del mapa; sin relación con el pronóstico |
| `Temporal_extract_PAHO_V1_3.csv` (OpenDengue, 18 países de las Américas) | Solo en el experimento multipaís del clasificador; no entra al pronóstico `[D]` |

---

## 4. Qué es específico de El Salvador

Cada punto lleva su evidencia. La columna final indica si la propiedad es verificable en código, está documentada o es una inferencia.

| # | Rasgo | Evidencia | Etiqueta |
|---|---|---|---|
| 1 | El objeto predicho es la serie nacional de El Salvador: filtro `r.codigo = 'SV'` y fuente `opendengue_v1_3`, y desde 2025 `minsal_tablero` | `M:backend/ingestion/experimento_nowcast_corto_plazo.py:135-148`; `M:backend/ingestion/nowcast_tablero_dengue.py:88,112-126` | `[H]` |
| 2 | El clima se agrega sobre los 14 departamentos de El Salvador (`r.nivel_admin = 1 AND r.pais = 'SV'`), con una celda de `era5_land` por departamento y coordenadas representativas propias (ADR 0003) | `M:backend/ingestion/experimento_nowcast_corto_plazo.py:166-185`; `N:docs/biblioteca/04-fuentes-de-datos.md:62-71` | `[H]` + `[D]` |
| 3 | Semanas MMWR (domingo a sábado) con la librería `epiweeks`, la numeración con que MINSAL y OPS reportan; 2014 y 2020 con 53 semanas; zona horaria `America/El_Salvador` para la agregación semanal del clima | `N:docs/biblioteca/03-funciones.md:114`; `N:docs/biblioteca/04-fuentes-de-datos.md:71`; conteo de semanas en la semilla | `[D]` + `[H]` |
| 4 | Los ceros de vacaciones (Semana Santa, fiestas agostinas, fin de año) se tratan como no notificación y no como huecos: la referencia limpia no aprende de las 17 semanas afectadas, y la variante M1 del experimento de mejora añadió una marca de esos tres períodos | `M:docs/experimentos/experimento-nowcast-mejora.md:14-34,81-85,97-98`; `M:backend/ingestion/experimento_nowcast_mejora.py:97` | `[H]` + `[D]` |
| 5 | 2020 se excluye como objetivo, como origen de prueba y del conjunto de la climatología por subregistro durante la covid; se conserva solo como insumo de rezagos | `M:backend/ingestion/experimento_nowcast_corto_plazo.py:72-73,293-330`; el sitio muestra 2020 con el aviso "En 2020 la pandemia de COVID-19 redujo la consulta y la notificación. Este año no se usó para entrenar ni para validar el modelo." | `[H]` |
| 6 | Se verificó contra el boletín SE52-2015 de MINSAL que 2014-2015 son transmisión real y no reetiquetado ni contaminación por chikungunya (MINSAL contó 167.957 casos de chikungunya en 2014 en una línea aparte; los confirmados de dengue de 2014, unos 15.900, superan por sí solos el total de 2016, 2017 y 2018). Caveat declarado: la intensidad de vigilancia fue mayor en 2014-2015 (alerta nacional de arbovirosis, tamizaje masivo de síndrome febril) | `ef698c8^:docs/experimentos/experimento-nowcast-corto-plazo.md` (sección "2014–2015 verificado"); `N:docs/biblioteca/05-sensibilidad-y-honestidad.md:27`; nota local `verificacion-dengue-2014-2015.local.md` | `[D]` |
| 7 | La definición de caso es la de El Salvador: el total de OpenDengue es la misma definición que los sospechosos de MINSAL (27.470 en 2019 en ambos) | `M:docs/adr/0021-fuente-tablero-minsal.md:51-53`; memoria `opendengue-total-es-sospechosos.md` | `[D]` |
| 8 | La dinámica de El Salvador está desacoplada de la regional: la correlación entre la anomalía anual de El Salvador y la señal regional de 18 países de las Américas es +0,280, la más baja de los 18 (Colombia +0,952, Guatemala +0,908, Honduras +0,868). Un clasificador regional superó la climatología en 6 de 11 años (8 de 11 con ONI) pero la corrida solo con El Salvador falló en 55 de 55 combinaciones semilla-año | `ef698c8^:docs/experimentos/experimento-multipais.md`; `M:backend/ingestion/experimento_multipais.py` | `[D]` |
| 9 | La transferencia de otros países no sirvió: el modelo regional no transfiere a países no vistos (0 de 16 países con transferencia sostenida, Vía 0) | `ef698c8^:docs/rescate-prediccion/informe-cierre-rescate-prediccion.md` | `[D]` |
| 10 | El historial de entrenamiento contiene el brote 2014-2015 de El Salvador (53.460 y 50.169 casos), que es lo que le permite al árbol ver niveles altos; con la historia recortada a 2016+ el skill de 2019 cae a -0,32 | `M:db/seed/seed_datos_reales.sql` (sumas); `ef698c8^:docs/experimentos/experimento-nowcast-corto-plazo.md` (sección Lectura) | `[H]` + `[D]` |
| 11 | Todas las salidas del sitio son nacionales y están rotuladas como serie nacional de El Salvador; no hay predicción departamental y el sitio lo declara | `N:docs/biblioteca/05-sensibilidad-y-honestidad.md:12-14`; `N:src/pages/acerca-de.astro:22-25` | `[H]` |
| 12 | El calendario de feriados interno (Semana Santa, 1 a 6 de agosto, 20 de diciembre a 2 de enero) se definió para El Salvador en M1; el candidato M1 que lo usaba no pasó la validación y no está en el modelo publicado | `M:docs/experimentos/experimento-nowcast-mejora.md:81-85,229-231` | `[D]` |

Rasgos que a primera vista parecerían específicos y no lo están, para no afirmarlos:

- Las 7 variables de clima y su aporte: no hay ablación; no se sabe si la información climática de El Salvador mejora el pronóstico (sección 5.7).
- Estacionalidad de El Salvador: los armónicos usan el día del año de la semana objetivo, pero no hay parámetros calibrados a la época lluviosa; los aprende el árbol de la propia serie. `[I]`
- Departamentos: ninguno entra al modelo; solo su media climática.

---

## 5. Evaluación y validación

### 5.1 Protocolo

- Forward-chaining con ventana expansiva: para cada origen, entrenamiento, normalización y referencias usan solo datos con fecha de inicio anterior a la del origen. `[H]` `M:backend/ingestion/experimento_nowcast_corto_plazo.py:293-330`.
- Aserción anti-fuga independiente del filtro: toma los índices de objetivo que `pares_entrenamiento` devuelve y comprueba que todos son anteriores al corte; un control negativo desactiva el filtro y confirma que la aserción entonces falla. `[H]` `M:backend/ingestion/experimento_nowcast_corto_plazo.py:517-547`.
- Control de mutación: etiquetas de entrenamiento permutadas (semilla 12345); el WIS debe empeorar. Resultados: 53,1 a 128,8 en el experimento original (sin calibrar); en el experimento de mejora, 56,6 a 142,3 para M0. `[D]` `M:docs/experimentos/experimento-nowcast-mejora.md:198-201`, confirmado en `mejora_validacion.json` (`wis_mutado` 142,33).
- Repetibilidad: dos corridas independientes del mismo caso dan métricas idénticas (el JSON de métricas idéntico byte a byte en el experimento original; cuantiles idénticos en el de mejora). `[D]`. Al regenerar los artefactos, el script no exige igualdad punto a punto porque el ajuste no es reproducible bit a bit entre corridas. `[D]` `M:docs/adr/0020-nowcast-corto-plazo.md:152-156`.
- Segunda confirmación independiente: WIS, forward-chaining y baselines reimplementados desde cero en `M:backend/ingestion/nowcast_segunda_confirmacion.py`; paridad a la décima en las 8 filas de la tabla principal y mismo veredicto por fila. `[D]` (resultado), `[H]` (el script existe).
- Años de prueba: 2019, 2021, 2022, 2023, 2024 (`ANIOS_PRUEBA`, línea 72). Los años previos a 2019 forman el entrenamiento inicial; 2020 se excluye. `[H]`.
- Métrica: WIS sobre 23 cuantiles (Bracher et al. 2021; K = 11 intervalos más la mediana) `[H]` `M:backend/ingestion/experimento_nowcast_corto_plazo.py:211-231`. Skill = `1 - WIS_modelo / WIS_referencia`; skill medio por año con peso igual (para que no domine el año de mayor conteo); cobertura empírica al 50 % y al 95 %.
- Criterio de éxito, firmado antes de correr: skill medio por año > 0, WIS ≤ referencia en al menos 4 de 5 años, cobertura del 95 % en [0,85; 0,99] y del 50 % en [0,35; 0,65]. El ajuste de "3 de N años" a "4 de 5" se firmó el 2026-09-08 para no repetir una vara que una vía del rescate no alcanzó. `[D]`.
- Referencia decisiva: la más fuerte de tres por WIS medio, calculada como `persistencia_rw` a h ≤ 6 y `persistencia_estacional` a h = 7 y 8 (ver `referencia_por_horizonte` del artefacto retrospectivo). `[H]` `M:backend/api/datos/nowcast_dengue_retrospectivo_opendengue.json`.
  - persistencia RW en log: `ŷ(t+h) = y(t)`, cuantiles de los residuos de h pasos de toda la historia previa (líneas 336-356);
  - climatología estacional: cuantiles de la misma semana ±1 en años estrictamente anteriores, sin 2020 (357-386);
  - persistencia estacional: persistencia más la diferencia de medianas log entre la semana objetivo y la de origen (388-413).

### 5.2 Resultados originales (2026-09-09), sin calibrar, ventana 2014+

Fuente: `ef698c8^:docs/experimentos/experimento-nowcast-corto-plazo.md` (tabla de resultados), referenciada por `M:docs/adr/0020-nowcast-corto-plazo.md:16-22`. `[D]`.

| h | WIS referencia | WIS modelo | Skill medio por año | Años ganados |
|---|---|---|---|---|
| 1 | 46,7 | 33,7 | +0,31 | 5/5 |
| 2 | 50,8 | 38,3 | +0,31 | 5/5 |
| 4 | 74,6 | 53,1 | +0,33 | 5/5 |
| 8 | 105,9 | 75,1 | +0,37 | 5/5 |

Skill por año a h = 4 con historia 2014+: 2019 +0,28; 2021 +0,36; 2022 +0,15; 2023 +0,39; 2024 +0,47. Con historia 2016+: 2019 -0,32; 2021 +0,41; 2022 +0,14; 2023 +0,39; 2024 +0,55. Cobertura (nominal 0,50 y 0,95) a h = 4: 0,42 y 0,94 con 2014+; 0,38 y 0,88 con 2016+.

### 5.3 Modelo publicado (calibrado con CQR-r) y referencia limpia

El modelo publicado hasta 2024 es el calibrado. Calibrar con CQR-r en 2014+ llevó la cobertura al 50 % de 0,40-0,52 a 0,55-0,60, mantuvo la del 95 % entre 0,88 y 0,92 y costó entre 0,02 y 0,05 de skill. A h = 4: WIS 56,6, skill +0,29, cobertura 0,55 y 0,88. A h = 8: WIS 78,8, skill +0,35, cobertura 0,57 y 0,88. `[D]` (`ef698c8^:docs/experimentos/experimento-nowcast-corto-plazo.md`, sección Calibración) y `[H]` en el artefacto: `desempeno` de `M:backend/api/datos/nowcast_dengue_opendengue.json` da `wis_modelo` 56,6, `wis_baseline` 74,6, `reduccion_wis` 0,241, `skill_medio_por_anio` 0,285, `skill_por_anio` {2019: 0,227; 2021: 0,333; 2022: 0,124; 2023: 0,392; 2024: 0,349}, `cobertura_50` 0,551, `cobertura_95` 0,879.

El experimento de mejora (2026-09-27) recalculó la referencia sin aprender de las 17 semanas afectadas por los ceros de vacaciones. Resultados de M0 en 2019 y 2021-2024 (de `M:backend/ingestion/data/interim/nowcast/mejora_validacion.json`, WIS agrupados; skill agrupado calculado por mí como `1 - WIS_M0 / WIS_ref`) `[D]` + `[I]` para el cálculo:

| h | Skill medio por año contra la referencia limpia (años ganados) | Cobertura 95 % | WIS M0 / WIS ref. limpia | Skill agrupado `[I]` contra limpia | Skill agrupado `[I]` contra publicada |
|---|---|---|---|---|---|
| 1 | -0,04 (2/5) | 0,92 | 35,6 / 35,2 | -0,01 | 0,24 |
| 2 | 0,06 (3/5) | 0,91 | 37,9 / 40,3 | 0,06 | 0,25 |
| 3 | 0,05 (3/5) | 0,90 | 46,4 / 48,7 | 0,05 | 0,26 |
| 4 | 0,05 (4/5) | 0,88 | 56,6 / 58,8 | 0,04 | 0,24 |
| 5 | 0,12 (4/5) | 0,90 | 61,4 / 67,7 | 0,09 | 0,25 |
| 6 | 0,13 (4/5) | 0,90 | 67,9 / 76,4 | 0,11 | 0,24 |
| 7 | 0,16 (4/5) | 0,89 | 73,5 / 85,5 | 0,14 | 0,28 |
| 8 | 0,18 (4/5) | 0,88 | 78,8 / 95,3 | 0,17 | 0,26 |

Lectura: la ventaja contra la referencia que aprende de las semanas con ceros es de 24 % a 28 % de reducción del WIS en todos los horizontes; la ventaja contra la que no aprende de ellas es casi nula a 1 a 3 semanas y de 9 % a 17 % a 5 a 8 semanas. El propio experimento lo resume: "El modelo no gana por acertar en ellas, sino porque la referencia se ensancha por ellas" (a 1 a 3 semanas) y "hay una ventaja real y modesta a 5-8 semanas" `[D]` (`M:docs/experimentos/experimento-nowcast-mejora.md:28-29,259-260`). Quitar esas semanas solo de la puntuación cambia las cifras en menos de 0,05.

### 5.4 Resultados por año y horizonte (retrospectivo versionado)

Datos de `M:backend/api/datos/nowcast_dengue_retrospectivo.json` (`resumen_por_anio`), predicciones precomputadas con la misma cadena del experimento, referencia `persistencia_rw` (OpenDengue) y `persistencia_suavizada` (2025-2026). Skill a h = 1, 4 y 8, con cobertura 50 % y 95 % a h = 4. `[H]`.

| Año | n (h = 4) | Skill h = 1 | Skill h = 4 | Skill h = 8 | Cob. 50 % (h = 4) | Cob. 95 % (h = 4) | Nota |
|---|---|---|---|---|---|---|---|
| 2017 | 33 | -1,76 | -3,22 | -5,10 | 0,61 | 0,97 | No es año de prueba del experimento; 2017-S13 es la primera semana con predicción |
| 2018 | 52 | +0,14 | -0,01 | -0,57 | 0,33 | 0,87 | No es año de prueba |
| 2019 | 52 | +0,22 | +0,23 | +0,18 | 0,54 | 0,85 | Año de prueba; brote grande (27.470) |
| 2020 | 53 | -0,02 | +0,11 | +0,29 | 0,23 | 0,96 | Excluido; no entra a ningún agregado |
| 2021 | 52 | +0,23 | +0,32 | +0,52 | 0,52 | 0,94 | Año de prueba |
| 2022 | 52 | +0,07 | +0,12 | +0,20 | 0,58 | 0,71 | Año de prueba; 16.542 casos |
| 2023 | 52 | +0,34 | +0,39 | +0,25 | 0,46 | 0,90 | Año de prueba |
| 2024 | 52 | +0,53 | +0,35 | +0,56 | 0,64 | 1,00 | Año de prueba |
| 2025 | 48 | -0,09 | +0,11 | +0,17 | 0,40 | 0,98 | C sobre tablero; dentro de muestra; referencia suavizada |
| 2026 | 29 | -0,01 | +0,16 | +0,09 | 0,38 | 0,79 | C sobre tablero; dentro de muestra; hasta S37 |

Esta tabla está en el artefacto versionado y el sitio muestra la fila de cada año a h = 4 en la vista de contraste (`N:src/components/nowcast/ContrasteNowcastDengue.astro:626-638`, con frases como "A 4 semanas, en 2017 el modelo tuvo 322 % más error que repetir el último valor"). `[H]`.

Dos observaciones `[I]`: (a) 2017 y 2018 son los años con menor historia de entrenamiento (3 a 4 años) y el modelo pierde ahí contra la persistencia; que los años de prueba del experimento empiecen en 2019 se justifica por la regla de historia mínima y se firmó antes de correr, pero los años omitidos son los peores. (b) 2022 tiene cobertura del 95 % de 0,71 a h = 4 aunque su skill es positivo; los intervalos fallan sobre todo en los años de nivel medio-alto después de un valle.

### 5.5 Sobre 2025-2026 con la serie del tablero

Dentro de muestra (2025 y 2026 sirvieron para elegir C; `dentro_de_muestra: true`). Artefacto servido, `desempeno` de `M:backend/api/datos/nowcast_dengue.json` `[H]`: h = 4, referencia `persistencia_suavizada`, `wis_modelo` 19,6, `wis_baseline` 22,8, `reduccion_wis` 0,139, `skill_medio_por_anio` 0,134, `skill_por_anio` {2025: 0,108; 2026: 0,160}, `cobertura_50` 0,39, `cobertura_95` 0,909. En 2026 la cobertura del 95 % es 0,79 a h = 4 y a h = 8, por debajo del 0,85 del criterio; los fallos se concentran en 2026-S1 a S3 (salto del cambio de año) y S19 a S22 `[D]` `M:docs/adr/0020-nowcast-corto-plazo.md:200-204`.

Verificación de M0, T y C sobre 2024-2026 (`M:backend/ingestion/data/interim/nowcast/tendencia_verificacion.json`, 1.063 predicciones de M0 reproducidas sin diferencia; exploración reproducida con diferencia máxima de 0,005) `[D]`:

| h | Skill M0 (referencia suavizada) | Skill T | Skill C |
|---|---|---|---|
| 1 | -0,79 | 0,19 | -0,08 |
| 2 | -0,33 | 0,19 | 0,09 |
| 4 | -0,19 | 0,15 | 0,12 |
| 6 | 0,05 | 0,11 | 0,19 |
| 8 | 0,19 | 0,06 | 0,21 |

Contra la referencia limpia, a 4 semanas, M0 vale -0,07 y T 0,24 (mismo archivo). En el experimento de mejora, con la confirmación sobre 81 semanas de 2025-2026, M0 y el candidato M2 no superaron a la persistencia limpia a 1 a 5 semanas y predijeron de más (el rango del 50 % contenía entre el 20 % y el 33 % de lo observado; recalibrar los rangos no lo corrigió) `[D]` `M:docs/experimentos/experimento-nowcast-mejora.md:236-270`.

### 5.6 Prueba prospectiva

- Conjunto de prueba: todos los pares (origen, h) con h de 1 a 8 cuya semana objetivo sea 2026-S38 (20 al 26 de septiembre de 2026) o posterior; corte con 20 semanas objetivo publicadas, es decir, hasta 2027-S05, hacia mediados de febrero de 2027. El script se niega a puntuar antes, si su archivo tiene cambios sin commit, si faltan semanas o si la salida ya existe. Se evalúa una sola vez. `[D]` `M:docs/experimentos/experimento-nowcast-tendencia.md:99-131,173-175`; `[H]` las constantes `INICIO_PRUEBA` y `SEMANAS_PRUEBA` en `M:backend/ingestion/experimento_nowcast_tendencia.py:61-62`.
- Criterio, a h = 4 y a h = 8: skill agrupado > 0 contra la persistencia suavizada, WIS medio ≤ el de M0 y cobertura del 95 % ≥ 0,85 (a lo sumo 3 de 20 semanas fuera del rango). No se exige techo de cobertura.
- Si no se confirma, el sitio vuelve a M0 y dice que con la serie del tablero no supera a la persistencia.
- Estado a 2026-10-02: la última semana capturada es 2026-S37 (ancla 2026-09-13, 329 casos); ninguna semana de prueba está publicada. `[H]` `M:backend/api/datos/nowcast_dengue.json` (`ancla`). No hay validación prospectiva de M0 sobre OpenDengue (la serie termina en 2024).
- Sensibilidad prevista: repetir con los datos de la primera captura que incluye cada origen, para medir el efecto de revisiones de MINSAL.

### 5.7 Lo que no se ha medido

| Pregunta | Estado |
|---|---|
| Aporte del clima al pronóstico | No hay ablación (modelo sin clima contra modelo con clima). `grep` de "ablaci" en `backend/ingestion/*.py` solo devuelve código del experimento multipaís y del clasificador. Los clasificadores climáticos se retiraron (recall de "alto" = 0 en 2019 y 2022) y el ONI no mejoró al clasificador. `[H]` |
| Importancia de variables del pronóstico | No se calcula. |
| Métricas por departamento | No existen; el modelo es nacional. |
| Métricas en semanas epidémicas frente a no epidémicas | No existen como corte. Lo más cercano: skill por año, donde 2019 (brote) y 2022 (16.542 casos) son los años con más casos. |
| Datos al momento de la publicación (vintages) | No existen. La evaluación usa la serie final de OpenDengue o la última captura del tablero. |
| Comparación con modelos externos o publicados | Nunca se hizo. |
| Prueba prospectiva | Pendiente (sección 5.6). |
| Una segunda ventana o serie para la fragilidad ante brotes sin precedente | Pendiente; el soporte es 2019 (n = 1). |
| Sensibilidad al promedio de 6 o 7 semanas del tablero | Solo exploratoria sobre 2024-2026, no firmada. |

---

## 6. Comparación con alternativas

### 6.1 Baselines internos (los únicos contra los que se comparó)

| Baseline | Definición | Uso |
|---|---|---|
| Persistencia RW | Mediana `z[o]`; cuantiles de los residuos de h pasos | Referencia decisiva a h ≤ 6 (publicada) |
| Climatología estacional | Cuantiles de la misma semana ±1 de años anteriores, sin 2020; respaldo de persistencia si hay menos de 3 observaciones | Calculada, nunca la más fuerte |
| Persistencia estacional | Persistencia más la diferencia de medianas log entre semanas | Referencia decisiva a h = 7 y 8 (publicada) |
| Persistencia limpia | Como RW pero sin aprender de las 17 semanas afectadas por ceros | Referencia del criterio del experimento de mejora |
| Persistencia suavizada | Mediana `z[o]` y cuantiles de `z[t+h] - z[t]` en la historia promediada a 7 semanas | Referencia del criterio del experimento de tendencia; ver `N:src/components/nowcast/ContrasteNowcastDengue.astro:137-143` para el nombre que muestra el sitio ("repetir el último valor") |

### 6.2 Variantes internas consideradas, probadas y descartadas

| Alternativa | Resultado | Fuente |
|---|---|---|
| Recalcular por petición desde Postgres | Descartada: el ajuste es caro y el artefacto versionado hace el número auditable | ADR 0020 |
| Semáforo alto/medio/bajo sobre el conteo predicho | Descartada: reintroduce la salida que el pivote retiró | ADR 0020 |
| Historia desde 2016 como ventana principal | Descartada: el modelo falla en 2019 (skill -0,32); se conserva como chequeo de robustez | ADR 0020; experimento original |
| Calibración por inflado global | Descartada frente a CQR-r: cuesta 2 a 3 veces más en skill y es ciega al régimen | experimento original, sección Calibración |
| LightGBM | Descartado por no añadir dependencia (hardware modesto) | ADR 0020 |
| M1, predecir el cambio `z[t+h] - z[t]` con marca de vacaciones | No pasa la validación: skill medio negativo a h = 4, 2 de 5 años; -0,48 en 2021 | `M:docs/experimentos/experimento-nowcast-mejora.md:229-231` |
| M2, mezcla con la persistencia por cuantil con peso elegido en cada reajuste | Pasa la validación, no se confirma en 2025-2026 (skill -0,078 a h = 4 y cobertura 0,70 a h = 8) | mismo documento, líneas 232-255 |
| Reentrenar M0 con la historia promediada | Descartado: mejora a 1-2 semanas y en 2026 empeora a 5-8 (entre -0,38 y -0,71) | `M:docs/experimentos/experimento-nowcast-tendencia.md:44-46` |
| C, mezcla 50/50 de M0 y T | Publicada desde 2025, en prueba | ADR 0020 enmendada |

### 6.3 Línea previa: el clasificador de riesgo de brote y sus rescates

Un Random Forest sobre clima rezagado asignaba a cada semana nacional riesgo alto, medio o bajo (etiqueta: percentil P75 y P90 del canal endémico). Se retiró el 2026-08-18 por recall de "alto" igual a 0,000 en 2019 y 2022, los dos años de la ventana con semanas "alto" reales, y por no superar la línea base climatológica `[D]` (`N:docs/biblioteca/05-sensibilidad-y-honestidad.md:44-48`). Se cerraron además cinco vías de rescate, todas con evidencia reproducible en el código `[D]`:

| Intento | Resultado |
|---|---|
| Ajuste de umbral de decisión, cambio de algoritmo (RandomForest, GradientBoosting, ExtraTrees, regresión logística) | Sin mejora |
| Ventana climática ampliada | Sin mejora |
| ONI como predictor nacional | Sin mejora |
| Vía multipaís (18 países de las Américas, 16 con clima) | Regional supera la climatología en 6 de 11 años y 8 de 11 con ONI; la corrida de El Salvador solo, falla 0/55; el modelo regional no transfiere a países no vistos (0 de 16) |
| Vías 1 a 3 (casos previos, clima como posición dentro de la temporada, features con mecanismo biológico) | 0 de 10 semillas en el único fold evaluable (1 y 3); éxito estable en 3 de 5 folds (2) |
| Lead time del índice de idoneidad Iv | Alerta Z ≥ 1,5 por dos semanas disparó en pocos años; solo 2 pares alerta-inicio comparables, con signos opuestos (+29 y -30 semanas); la tesis de anticipación se retiró del producto |

El código del clasificador sigue en el repositorio (`entrenar_clasificador.py` y afines) como referencia; `AGENTS.md` pide no reactivarlo `[D]`.

### 6.4 Modelos externos, publicados o de otras instituciones

El repositorio no contiene ninguna comparación, prueba ni corrida contra modelos externos, ni lista de los que se consideraron. El único contacto con la literatura es: (a) el uso del conjunto de 23 cuantiles de los hubs de CDC y OPS y del WIS de Bracher et al. 2021 para que la métrica sea comparable en formato; (b) la frase de la Biblioteca "El aprendizaje automático aplicado al dengue y al clima ya tiene mucha literatura, con estudios en Bangladesh, Vietnam, India o Brasil. EPI-Aetheris no propone un modelo nuevo; su aporte es el software" (`N:docs/biblioteca/05-sensibilidad-y-honestidad.md:91`). Cualquier afirmación sobre cómo rinden esos modelos queda fuera de este documento.

---

## 7. Limitaciones y cómo las comunica el sitio

### 7.1 Lo que el modelo no hace

- No predice por departamento ni por municipio; no hay series departamentales de dengue después de 2023.
- No clasifica riesgo, no emite alertas y no anticipa inicio de temporada ni brotes `[D]`.
- No corrige retraso de notificación ni revisiones.
- No usa la información de M1 a M4.
- No usa datos de otros países, de búsquedas, de movilidad ni demográficos.
- No predice más allá de 8 semanas.

### 7.2 Supuestos

- Estacionariedad suficiente entre el historial de entrenamiento y el futuro, y presencia de un brote grande en el historial (supuesto de M0, declarado en `nota_alcance` y en la Biblioteca).
- Que la serie del tablero conserve la forma de promedio de 6 o 7 semanas (supuesto de T y C).
- Que 2020 sea un año anómalo que no debe enseñar nada al modelo.
- Que el total de OpenDengue y los sospechosos del tablero midan lo mismo; el empalme de 2024 a 2025 no corrige nivel ni forma.

### 7.3 Sensibilidades medidas

- Ventana de historia: con 2016+ el skill de 2019 es -0,32 (n = 1).
- Referencia: contra la persistencia limpia la ventaja baja de 24 % a 4 % a h = 4 (pooled).
- Datos suavizados: M0 pierde contra la persistencia a 1-5 semanas en 2025-2026 (skill -0,19 a h = 4 contra la suavizada).
- Calibración: sobre 2016+, cualquier calibración tira el skill a ≤ 0.
- Cadencia de reajuste: 1, 2 o 4 semanas, menos de 3 % de diferencia en WIS.
- Parámetros de T: robusto en los rangos explorados (5 a 9 semanas, φ de 0,6 a 0,9, pendiente de 2 a 4).

### 7.4 Situaciones de fallo documentadas

- Brote sin precedente en el historial: el modelo satura (la mediana y el grueso quedan cerca del máximo de entrenamiento; q0,99 llega a 7,68 en log pero la mediana no).
- Cambio de año en la serie del tablero (2026-S1 a S3) y mayo de 2026 (la predicción esperaba una subida mayor que la observada).
- Años con poca historia (2017-2018).
- Años de nivel medio-alto tras un valle (2022, cobertura del 95 % de 0,71).
- Semana 53 de 2025: sin predicción entre 2025-S53 y 2026-S7.

### 7.5 Calidad de los datos fuente

El conteo es sospechoso notificado, sensible a la intensidad de la vigilancia (2014-2015), a vacaciones, a revisiones de MINSAL, y la serie del tablero está suavizada y cambia de nivel al cambiar de año. Hay 19 correcciones retroactivas negativas en los boletines que se excluyen. La serie de OpenDengue 2024 tiene la misma forma lisa que el tablero, así que 2024 como año de prueba tiene una forma de dato distinta de 2019 a 2023 (`M:docs/adr/0021-fuente-tablero-minsal.md:39`).

### 7.6 Textos con que el sitio comunica el alcance

| Dónde | Texto o contenido |
|---|---|
| `M:backend/api/main.py:566-572` (aviso del endpoint) | "Prediccion estadistica de horizonte corto sobre la serie nacional de dengue: OpenDengue hasta 2024 y sospechosos del tablero de MINSAL desde 2025. Se extiende desde la ultima semana publicada. Desde 2025 combina el modelo validado con una tendencia amortiguada y esta en prueba con las semanas publicadas desde 2026-S38." |
| `N:src/components/nowcast/PanelNowcastDengue.astro:746-752` | "La predicción parte de la última semana publicada en el tablero de MINSAL (fecha, N casos). El tablero publica cada semana como un promedio de varias." (para OpenDengue: "...de la serie pública ..., que se actualiza con retraso.") |
| mismo, 759-800 | Chips: "−N % de error frente a la persistencia en 2025–2026", "en prueba con semanas nuevas desde la semana 38 de 2026", "horizonte de referencia: 4 semanas" (cuando `dentro_de_muestra`); para la serie OpenDengue: "−N % de error frente a la persistencia" y "mejor en N de 5 temporadas de prueba" |
| mismo, 970-975 (pie) | "Predicción estadística del conteo nacional de casos de dengue. Método y validación." (enlace a la Biblioteca 05) |
| `N:docs/biblioteca/05-sensibilidad-y-honestidad.md:16-36` | Sección completa: muestra el número y un rango; la fecha de partida siempre a la vista; 2020 con aviso; "Su ventaja depende de que los datos de entrenamiento, que empiezan en 2014, ya incluyan un brote grande... Ante un brote sin precedente en la serie, la predicción puede quedarse corta."; "Esos años sirvieron para elegir el método, así que la cifra mide cómo se ajusta a ellos."; "En 2026 el valor observado quedó fuera del rango del 95 % en una de cada cinco semanas"; condiciones de la prueba y cuándo se vuelve a M0 |
| `N:src/components/nowcast/ContrasteNowcastDengue.astro:612-639` | Por año: aviso de 2020; "Desde 2025 la serie es la del tablero de MINSAL y la predicción combina el modelo con una tendencia amortiguada. 2025 y 2026 sirvieron para elegir ese método; la prueba con semanas nuevas empieza en la semana 38 de 2026."; "A 4 semanas, en AAAA el modelo tuvo N % menos (o más) error que repetir el último valor; lo observado quedó dentro del rango del 50 % en el X % de las semanas y dentro del 95 % en el Y %." |
| `N:src/lib/glosario.ts:71-76` | Banda: "Rango en el que caería la cifra prevista con esa probabilidad. La banda del 95 % es más ancha que la del 50 %." |
| `N:src/pages/acerca-de.astro:22-25` | "No diagnostica ni asigna niveles de riesgo; la única predicción es la del número de casos de dengue a corto plazo, con sus métricas a la vista." |
| `N:src/pages/prediccion.astro:36-47` | "Conteo nacional de casos para las próximas 1 a 8 semanas." y enlace al método en la Biblioteca |

`[H]`: los textos citados. Nota `[I]`: el glosario describe los rangos con la probabilidad nominal; la cobertura medida es menor (0,39 y 0,91 en 2025-2026; 0,55 y 0,88 en la validación de OpenDengue). El panel principal no muestra la cobertura (no hay referencias a `cobertura` en `PanelNowcastDengue.astro`); la vista de contraste sí la muestra por año.

---

## 8. Preguntas difíciles anticipadas

Cada respuesta usa solo evidencia del repo. Donde algo no se midió se indica la prueba más simple. En ningún caso se afirma cómo rinden los modelos externos.

**1. ¿Es un modelo entrenado o una regla estadística?**
Respuesta: son dos cosas según el tramo. Hasta 2024 es M0, un gradient boosting cuantílico entrenado y reajustado cada dos semanas con datos de El Salvador. Desde 2025 es C, mitad M0 y mitad una regla de tendencia con cuatro constantes fijas y errores empíricos, sin parámetros entrenados. `[H]` Soporte: secciones 2.3 y 2.4. Investigar fuera: nada. Prueba mínima: ninguna.

**2. ¿Por qué no un modelo mecanístico o compartimental (SIR, SEIR con vector)?**
Respuesta: no se probó ni se descartó con evidencia. El proyecto eligió un modelo estadístico de conteo por su horizonte corto y el tamaño de la serie. `[H]` (ausencia en el repo). Investigar fuera: modelos compartimentales de dengue en Centroamérica y su exigencia de datos. Prueba mínima: implementar un modelo de crecimiento exponencial amortiguado de dos parámetros como baseline adicional y puntuarlo con el mismo WIS; es un cambio de horas porque el marco de evaluación ya existe.

**3. ¿Qué hace InfoDengue y cómo se compara?**
Respuesta: no se comparó con InfoDengue. El repo no contiene ni sus métodos ni sus predicciones. Investigar fuera: método, resolución, horizonte, datos de entrada y métricas publicadas. Prueba mínima: si existen predicciones públicas comparables, puntuarlas sobre las mismas semanas, el mismo objetivo y la misma métrica; primero hay que averiguar si hay alguna para El Salvador.

**4. ¿Y los modelos de los proyectos de pronóstico de dengue de OPS/OMS o CDC?**
Respuesta: la salida usa el mismo formato (23 cuantiles, WIS) para poder comparar, pero la comparación nunca se hizo. `[H]` Investigar fuera: resultados de esos esfuerzos con series de Centroamérica y El Caribe, y si El Salvador figura entre los sitios evaluados. Prueba mínima: si hay predicciones publicadas para El Salvador en un periodo cubierto, puntuarlas con el `wis()` del repo (`M:backend/ingestion/experimento_nowcast_corto_plazo.py:211`).

**5. ¿Por qué no deep learning (LSTM, transformers)?**
Respuesta: no se probó. La serie nacional tiene 574 semanas, de las cuales 2020 no se usa como objetivo, y la validación efectiva cubre cinco temporadas. Una red con muchos parámetros tendría ese tamaño de datos. `[I]`. Investigar fuera: resultados de modelos neuronales con series de dengue de esa longitud. Prueba mínima: ninguna proporcionada; el mismo marco de forward-chaining admite cualquier modelo que devuelva 23 cuantiles.

**6. ¿Usa el clima? ¿Por qué debería creerse que ayuda?**
Respuesta: el clima nacional (7 variables) y el ONI entran como variables de M0, pero nunca se midió su aporte. Los clasificadores climáticos fallaron. `[H]` Soporte: sección 5.7. Prueba mínima: correr `experimento_nowcast_corto_plazo.py` con `VARIABLES_CLIMA` vacío y sin ONI, mismos años y horizontes, y comparar el WIS. Si no cambia, el clima no aporta; si empeora, aporta. Es una modificación de una constante (`M:backend/ingestion/experimento_nowcast_corto_plazo.py:87-91`).

**7. ¿Se validó con datos futuros o en tiempo real?**
Respuesta: no todavía. La validación retrospectiva es forward-chaining con ventana expansiva, pero con series finales. La prueba prospectiva con semanas aún no publicadas al firmar (desde 2026-S38) está firmada y se evalúa una sola vez en 2027. `[H]`/`[D]`. Prueba mínima: esperar el corte; antes de eso, el sitio puede mostrar semana a semana cómo se comporta la predicción publicada contra lo que MINSAL publica, sin puntuar.

**8. ¿Qué pasa con que los datos del tablero estén suavizados?**
Respuesta: lo que se predice desde 2025 es una serie suavizada (promedio de unas 6 o 7 semanas), no el conteo semanal crudo. M0 pierde contra la persistencia con esa serie; C se diseñó para aprovechar la inercia. La causa exacta del suavizado no se puede recuperar. `[D]` Soporte: ADR 0021, experimento de tendencia. Investigar fuera: si MINSAL documenta cómo calcula las cifras semanales del tablero. Prueba mínima: pedir a MINSAL o contrastar capturas sucesivas de la misma semana para ver si se revisa.

**9. ¿Qué tan buenos son los intervalos?**
Respuesta: por debajo del nominal. Validación de OpenDengue: 0,55 al 50 % y 0,88 al 95 % a h = 4 (agrupado); por año el 95 % va de 0,71 (2022) a 1,00 (2024). 2025-2026: 0,39 y 0,91; 2026 solo: 0,79 al 95 %. CQR-r es un heurístico, no conformal estricto en los intervalos externos. `[H]` Soporte: sección 5.4. Prueba mínima: ya está planeada en la prueba prospectiva (cobertura 95 % ≥ 0,85 con 20 semanas).

**10. ¿Qué pasa en un brote atípico o sin precedente?**
Respuesta: el modelo de árboles no extrapola por encima del rango de entrenamiento. Con historia desde 2016 el skill de 2019 cae a -0,32; con historia desde 2014 la serie incluye un brote grande y gana. El soporte es un solo año. `[D]` Prueba mínima: repetir el recorte de historia en una segunda ventana o serie (pendiente declarado en `02-decisiones-abiertas.md`).

**11. ¿El brote de 2014-2015 no será un artefacto de la vigilancia?**
Respuesta: se verificó contra el boletín SE52-2015 de MINSAL que es transmisión real, con el caveat de mayor intensidad de vigilancia por la alerta de arbovirosis y el tamizaje de síndrome febril. El árbol depende de ese pico. `[D]` Prueba mínima: ya existe, es el recorte a 2016+.

**12. ¿Por qué se excluyó 2020? ¿No es elegir los datos?**
Respuesta: la exclusión se firmó antes de correr (2026-09-08), por subregistro durante la covid, y se aplica como objetivo, origen de prueba y conjunto de la climatología; se conserva como rezago. El sitio muestra 2020 con aviso y fuera de los agregados. `[H]`. Prueba mínima: puntuar 2020 aparte; el retrospectivo ya lo hace (skill h = 4: +0,11, cobertura del 50 %: 0,23).

**13. ¿Los años de prueba se eligieron para que saliera bien?**
Respuesta: se fijaron antes de correr (2019, 2021 a 2024). Los años anteriores forman el entrenamiento inicial. El artefacto retrospectivo contiene 2017 y 2018, donde el modelo pierde ante la persistencia (skill a h = 4: -3,22 y -0,01), y el sitio los muestra. `[H]` `[D]`. Prueba mínima: ninguna; documentar la regla de historia mínima en la Biblioteca.

**14. ¿Cuánto del skill se debe a una referencia débil?**
Respuesta: mucho a 1 a 3 semanas. Contra la referencia que aprende de las semanas con cero casos de vacaciones, el WIS baja entre 24 % y 28 % en todos los horizontes; contra la que no aprende de ellas, entre -1 % y 6 % a 1 a 4 semanas y entre 9 % y 17 % a 5 a 8 semanas. `[D]` Soporte: sección 5.3. El sitio sigue mostrando la cifra contra la referencia publicada en la vista por año de 2017-2024 y la Biblioteca dice que "en las cinco temporadas tuvo menos error que repetir el último valor observado" (ver sección 11).

**15. ¿Qué hace con los ceros de vacaciones?**
Respuesta: los conserva como los publica la fuente. Hay 9 semanas con 0 casos seguidas de una con el doble; la referencia publicada aprende saltos de hasta ±4 en log de ellas y abre sus cuantiles extremos. M0 no tiene tratamiento especial de esas semanas; el candidato M1 con marca de vacaciones no pasó. `[D]`.

**16. ¿Predice por departamento?**
Respuesta: no. Los datos departamentales de dengue terminan en 2023 y el tablero no los publica. `[H]`.

**17. ¿Es un nowcast en sentido estricto (corrige retrasos de notificación)?**
Respuesta: no. Es un pronóstico a 1-8 semanas desde la última semana publicada. No hay un modelo de retraso ni se usan datos con revisiones. La palabra "nowcast" es el nombre interno. `[H]`. Investigar fuera: métodos de nowcasting con retraso y si MINSAL publica el momento de cada notificación. Prueba mínima: comparar capturas sucesivas del tablero para cuantificar la revisión de las últimas semanas.

**18. ¿Por qué el código dice "nowcast" y el sitio "predicción"?**
Respuesta: al inicio del proyecto se vetó la palabra "predicción" por un clasificador que falló; al levantarse el veto se mantuvo el nombre interno. `[D]` `M:AGENTS.md:451`. Para lectores externos conviene decir "pronóstico a corto plazo" en los documentos técnicos. `[I]`.

**19. ¿Los parámetros se ajustaron sobre los datos de prueba?**
Respuesta: los hiperparámetros de M0 se fijaron antes de correr y no se barrieron. Los de T (7 semanas, φ = 0,8, pendiente de 3) se eligieron en una exploración sobre 2024-2026, que por eso se declara dentro de muestra, con sensibilidad en rangos. El peso 0,5 de la mezcla se fijó, no se optimizó. `[D]`.

**20. ¿Es reproducible?**
Respuesta: los artefactos están versionados, los scripts son de solo lectura sobre Postgres y el experimento de tendencia está congelado en un commit. El ajuste no es reproducible bit a bit entre corridas y el script lo tolera. Desde un clon limpio solo se puede regenerar la base de M0, porque el volcado `db/seed` no incluye el tablero y los HAR no se versionan. `[D]` + `[H]`.

**21. ¿Qué datos usa el modelo que no están disponibles en tiempo real?**
Respuesta: el clima de las últimas semanas (ERA5 con ~5 días de retraso) debe recargarse hasta la semana de anclaje; la serie del tablero se captura a mano. El ancla va unas dos semanas detrás del tiempo real con el tablero, y ~21 meses con OpenDengue. `[D]`.

**22. ¿A qué horizonte sirve?**
Respuesta: contra la persistencia limpia, la ventaja de M0 es nula a 1-3 semanas y de 9 % a 17 % del WIS a 5-8 semanas; con C sobre el tablero, el skill es -0,08 a h = 1 y 0,12 a 0,21 a h = 4 a 8 (2024-2026, dentro de muestra). `[D]`.

**23. ¿Se probó con otras enfermedades o países?**
Respuesta: el nowcast no; la nota técnica de `AGENTS.md` pide no reutilizarlo en otra serie sin verificar que el historial contenga un brote grande. El experimento multipaís (clasificador) usó 18 países. `[D]`.

**24. ¿Los intervalos tienen garantías conformal?**
Respuesta: no estrictas. Los scores se winsorizan en el percentil 90, el factor se topa en 4,0 y los tres intervalos externos colapsan al mismo factor; además los anchos se hacen monótonos en h. `[H]`.

**25. ¿Cómo maneja las semanas 53 y el calendario?**
Respuesta: calendario MMWR; 2014 y 2020 tienen 53 semanas; 2025-S53 no se publica y deja una ventana sin predicción. `[H]`. Hay una inconsistencia de etiquetas en el artefacto base de OpenDengue (sección 11).

**26. ¿Sirve para decidir?**
Respuesta: el proyecto lo presenta como herramienta descriptiva de vigilancia; no se evaluó utilidad para decisiones (camas, fumigación) ni el costo de errores. `[D]` `N:docs/biblioteca/05-sensibilidad-y-honestidad.md:10-14`.

**27. ¿Habría mejores datos que los usados?**
Respuesta: no se exploraron series de casos por departamento después de 2023, búsquedas, movilidad ni datos de laboratorio de dengue. Para IRA hay datos de virus respiratorios en el repo, sin relación con este modelo. `[H]`.

**28. ¿Qué licencia tienen los datos?**
Respuesta: MINSAL, NOAA y OpenDengue "mantienen las condiciones de su fuente"; Open-Meteo, CC BY 4.0 (con atribución). El nombre de la licencia de OpenDengue no está escrito en el repo. `[H]`.

---

## 9. Qué debe buscar la investigación externa

Preguntas delimitadas, cada una con lo que el repo permite comparar.

1. Modelos publicados de pronóstico de dengue para Centroamérica y el Caribe, y para El Salvador en particular: método, resolución (nacional o departamental), horizonte, ventana de evaluación, fuente de datos, métrica y si usan clima. Contraste inmediato con este modelo: nacional, semanal, h = 1 a 8, 2019 y 2021-2024, WIS sobre 23 cuantiles.
2. Si existe evaluación pública de pronósticos de dengue con series de El Salvador: periodo, objetivo, métricas (WIS, cobertura, error absoluto) y referencia.
3. Metodología de nowcasting con retraso de notificación aplicada a dengue o a vigilancia en la región, y si MINSAL publica fechas de notificación o de inicio de síntomas que permitan reconstruir un triángulo de retrasos.
4. Métricas probabilísticas usadas en competencias o hubs de pronóstico de dengue o de enfermedades infecciosas (WIS, CRPS, cobertura, log score) y su definición exacta para comparar. El repo implementa WIS con 11 intervalos y la mediana.
5. Resultados de competencias de pronóstico de dengue o de enfermedades transmitidas por vectores: qué baselines usaron (persistencia, climatología, estacional), qué skill alcanzaron sus mejores modelos respecto a esos baselines, y en qué horizontes. Solo para fijar qué skill sería comparable, sin trasladar cifras.
6. Modelos climáticos de dengue (temperatura, lluvia, ENSO) en Centroamérica: qué rezagos, qué resolución y qué ganancia reportan frente a un modelo autorregresivo.
7. Disponibilidad de datos comparables: series semanales de dengue de El Salvador de otras fuentes (por ejemplo PLISA directamente), departamentales o municipales posteriores a 2023, y publicaciones de MINSAL con revisión de cifras.
8. Estado de la literatura sobre series de vigilancia suavizadas o con promedio móvil en la fuente y su efecto sobre el pronóstico.

Criterios para una comparación justa:

| Criterio | Qué exigir |
|---|---|
| Mismo objetivo | Conteo semanal nacional de dengue de El Salvador, definición sospechosos (OpenDengue total) |
| Mismo horizonte | h = 1 a 8 semanas desde la última semana publicada |
| Misma resolución | Nacional; no comparar un modelo departamental agregado salvo declararlo |
| Mismo periodo | 2019, 2021, 2022, 2023, 2024 (excluye 2020); 2025-2026 solo como dato dentro de muestra |
| Disponibilidad en tiempo real | Que el modelo comparado solo use datos disponibles en la fecha de origen, sin vintages posteriores |
| Misma métrica | WIS sobre 23 cuantiles, skill contra la persistencia limpia y la suavizada, cobertura al 50 % y 95 % |
| Misma referencia | Persistencia (limpia y publicada), climatología estacional y persistencia estacional ya implementadas |

Baselines y herramientas que el repo ya soporta: tres baselines (`experimento_nowcast_corto_plazo.py:336-413`), referencia limpia (`experimento_nowcast_mejora.py:97,129`), referencia suavizada (`experimento_nowcast_tendencia.py:81-113`), WIS y cobertura (`:211-241`), y `nowcast_segunda_confirmacion.py` como implementación independiente del WIS para comprobar cualquier tabla ajena.

---

## 10. Inventario de fuentes consultadas

### 10.1 Monorepo `M:`

| Ruta | Uso |
|---|---|
| `docs/adr/0020-nowcast-corto-plazo.md` | Decisión, alternativas, ampliación retrospectiva y enmienda del tablero |
| `docs/adr/0021-fuente-tablero-minsal.md` | Tablero como fuente, forma suavizada, definición de caso |
| `docs/adr/0018-extension-capa-climatica-presente.md` | Clima desde 2014 hasta el presente, ERA5 con 5 días de retraso |
| `docs/experimentos/experimento-nowcast-mejora.md` | Referencia limpia, M1 y M2, confirmación 2025-2026 |
| `docs/experimentos/experimento-nowcast-tendencia.md` | T, C y prueba prospectiva |
| `backend/ingestion/experimento_nowcast_corto_plazo.py` | Modelo M0, variables, WIS, baselines, aserción anti-fuga |
| `backend/ingestion/experimento_nowcast_calibracion.py` | CQR-r e inflado global |
| `backend/ingestion/experimento_nowcast_mejora.py` | M1, M2, referencia limpia, mezcla |
| `backend/ingestion/experimento_nowcast_tablero.py` | Serie mixta y huecos |
| `backend/ingestion/experimento_nowcast_tendencia.py` | T, C, verificación y evaluación |
| `backend/ingestion/nowcast_estimacion_dengue.py` | Artefacto base de M0 |
| `backend/ingestion/nowcast_retrospectivo_dengue.py` | Retrospectivo de M0 |
| `backend/ingestion/nowcast_tablero_dengue.py` | Artefactos servidos |
| `backend/ingestion/nowcast_segunda_confirmacion.py` | Segunda implementación |
| `backend/ingestion/experimento_multipais.py` y `tests/test_experimento_multipais.py` | Experimento multipaís del clasificador |
| `backend/api/main.py:564-620` | Endpoints y aviso |
| `backend/api/tests/test_endpoints_nowcast.py` | Pruebas del contrato |
| `backend/api/datos/nowcast_dengue*.json` (4 archivos) | Artefactos |
| `backend/ingestion/data/interim/nowcast/*.json`, `nowcast_calibracion/resumen.json` | Salidas locales gitignored de los experimentos |
| `backend/ingestion/data/README.md` | Procedencia de OpenDengue y capturas HAR |
| `db/seed/seed_datos_reales.sql` | Conteos de verificación |
| `AGENTS.md:105,111,448-452,504` | Reglas de producto sobre la predicción |

### 10.2 Frontend `N:`

| Ruta | Uso |
|---|---|
| `docs/biblioteca/01-que-es.md`, `03-funciones.md`, `04-fuentes-de-datos.md`, `05-sensibilidad-y-honestidad.md` | Texto público vigente |
| `src/components/nowcast/PanelNowcastDengue.astro`, `ContrasteNowcastDengue.astro`, `svg-nowcast.ts` | Interfaz |
| `src/pages/prediccion.astro`, `acerca-de.astro`, `legal/terminos.astro` | Textos y licencias |
| `src/lib/glosario.ts`, `tipos-analisis.ts`, `enlaces.ts` | Glosario, tipos, rutas |
| `tests/e2e/prediccion.spec.ts`, `contraste-nowcast.spec.ts` | Pruebas de interfaz |
| `CLAUDE.md` | Convenciones del repo |

### 10.3 Documentos históricos recuperados con `git show ef698c8^:...` (podados del árbol de trabajo el 2026-09-25)

`docs/experimentos/experimento-nowcast-corto-plazo.md` (resultados originales, 2014-2015, segunda confirmación, calibración), `docs/contexto/01-decisiones-cerradas.md`, `docs/contexto/02-decisiones-abiertas.md`, `docs/contexto/03-fuentes-de-datos.md`, `docs/rescate-prediccion/informe-cierre-rescate-prediccion.md`, `experimento-oni-predictor.md`, `experimento-ventana-climatica-ampliada.md`, `experimento-multipais.md`, `experimento-validacion-leadtime-idoneidad.md`, `modulo-3-presion-epidemiologica.md`.

### 10.4 Notas locales fuera de los repos y memoria

`/home/over/D3v/proyecto26/añañin/experimentos/verificacion-dengue-2014-2015.local.md` y `nowcast-segunda-confirmacion.local.md`. Memoria del proyecto: `estilo-redaccion.md`, `opendengue-ceros-vacaciones.md`, `opendengue-total-es-sospechosos.md`, `tablero-suavizado-7-semanas.md`, `minsal-dashboard-capturas.md`, `no-camino-ancho.md`, `docs-sin-code-y-acordeones.md`.

### 10.5 Commits que fijan hitos

`bd042f0` (2026-09-10, predicción en la UI), `025b33e` (ADR 0020), `ef957cf` (retrospectivo desde cualquier semana), `561a854` y `c6be38e` y `623441d` (firma, script y resultados del experimento de mejora), `a98f3ef` (firma del experimento de tendencia), `40b6ebb` (script congelado, 2026-09-27), `06d9293` (2026-09-27, predicción sobre el tablero), `ef698c8` (2026-09-25, poda de documentación histórica), `88a4ef5` (2026-10-01, sincronización del frontend). En `N:`: `21952ae`, `a1a5ccd`, `957ea45`, `ea035ad`, `b2b6b6b`.

---

## 11. Huecos y "No verificado"

Contradicciones entre documentos, código y datos, con ambas citas:

1. Referencia publicada frente a limpia. `N:docs/biblioteca/05-sensibilidad-y-honestidad.md:25` dice "En las cinco temporadas tuvo menos error que repetir el último valor observado" y el chip del panel para la serie OpenDengue muestra "−24 % de error" y "mejor en 5 de 5 temporadas" (`PanelNowcastDengue.astro:790-798`, de `desempeno.baseline = persistencia_rw`). El experimento de mejora, firmado, resuelve que "las métricas del sitio se corrigen con la referencia limpia" (`M:docs/experimentos/experimento-nowcast-mejora.md:273-276`) y contra esa referencia la ventaja a h = 4 es 0,05 (4 de 5 años) y a h = 1 es -0,04 (2 de 5). La corrección no figura en la Biblioteca 05 ni en `nowcast_dengue_opendengue.json`. La vista de contraste por año sigue usando `persistencia_rw` y `persistencia_estacional` publicadas.
2. Cobertura nominal frente a medida. `N:src/lib/glosario.ts:73` define el rango "en el que caería la cifra prevista con esa probabilidad"; la cobertura medida es 0,39 al 50 % y 0,91 al 95 % en 2025-2026 (`nowcast_dengue.json`, `desempeno`) y 0,55 y 0,88 en la validación de OpenDengue. La Biblioteca declara la cobertura del 95 % en 2026 ("una de cada cinco semanas fuera"), pero el panel principal no muestra cobertura.
3. Cobertura en el criterio. ADR 0020 (líneas 18-19) cita "cobertura 0,42/0,94" (sin calibrar); el artefacto servido para la serie OpenDengue es calibrado (0,551/0,879). Ambas cifras son correctas para versiones distintas, pero la ADR no aclara que el modelo servido es el calibrado en la primera mención. Además, la calibración con CQR-r baja la cobertura del 95 % de 0,94 a 0,88 y la ADR la valora por subir la del 50 %.
4. Años de clima. `N:docs/biblioteca/04-fuentes-de-datos.md:75` dice "Filas cargadas: 35.868 (7 variables, 14 departamentos, de 2018 a 2024, con 2020)". La base semilla tiene filas de clima desde 2014 hasta 2026 parcial (5.148 por año y 3.430 en 2026) y el modelo usa clima desde 2014. `N:docs/biblioteca/03-funciones.md:33` sí dice 2014 hasta el año en curso para M2. El número de la Biblioteca 04 quedó anterior a ADR 0018.
5. Definición de caso OpenDengue frente a MINSAL. `N:docs/biblioteca/04-fuentes-de-datos.md:56` dice que las dos fuentes "no usan la misma definición de caso" para explicar las diferencias de 5 y 13 casos; el ADR 0021 (enmienda) y las memorias dicen que es la misma definición. Las diferencias de cifras no se explican con ninguna de las dos hipótesis.
6. Sumas de OpenDengue. La nota de verificación 2014-2015 dice que las sumas "coinciden con la BD del proyecto" y da 2014: 53.196, 2017: 4.402, 2020: 5.334, 2023: 5.863, 2024: 8.477; la base semilla da 53.460, 4.297, 5.450, 5.788 y 8.552. Puede ser una diferencia entre el `masterDB` y el `Spatial_extract`. No verificado.
7. Etiquetas de semana en el artefacto base de OpenDengue. `M:backend/ingestion/nowcast_estimacion_dengue.py:96` calcula la semana de las semanas futuras con `isocalendar()` (ISO), no MMWR. El h = 1 de `nowcast_dengue_opendengue.json` cae el 2024-12-29 y lleva `anio: 2024, semana: 52`, cuando en MMWR sería 2025-S1. `nowcast_tablero_dengue.py:112-126` corrige las etiquetas con `semanas_epidemiologicas` en el artefacto servido; el base de OpenDengue conserva la etiqueta ISO. Efecto: solo etiquetas, no cifras.
8. Documentos citados que no están en el árbol. ADR 0020 cita `02-decisiones-abiertas.md` y las Biblioteca/ADR citan `docs/experimentos/verificacion-dengue-2014-2015.local.md`, ausentes tras `ef698c8` (2026-09-25); los resultados originales, la calibración y la segunda confirmación solo están en el historial de git. `[H]`.
9. Duplicación de frontends. ADR 0020 (consecuencias) dice que el panel está duplicado en `web/` del monorepo y en `aetheris-nitor`; la vista de contraste solo está en `aetheris-nitor`. Los textos del monorepo pueden diferir de los de `N:`. La Biblioteca de `M:docs/biblioteca/04-fuentes-de-datos.md` es distinta de la de `N:`.

No verificado:

- Aporte del clima y del ONI al pronóstico (sin ablación).
- Que el soporte de M0 ante un brote nuevo se mantenga en una segunda serie (n = 1).
- Segunda confirmación: el resultado "paridad a la décima" está en la documentación; no volví a correrla.
- Que las cifras del experimento original (tabla 5.2) y de la calibración se reproduzcan hoy: las leí en el documento recuperado de git, y las de mejora coinciden con `mejora_validacion.json`.
- La licencia exacta de OpenDengue V1.3.
- Qué hace MINSAL para producir el promedio de 6 o 7 semanas del tablero.
- Si el tablero revisa semanas ya publicadas (solo hay una tanda de capturas).
- Utilidad para decisiones de salud pública.
- Cualquier comparación con modelos externos.
- Que InfoDengue u otros proyectos cubran El Salvador.
- Estado de la prueba prospectiva: ninguna semana de prueba publicada a 2026-10-02.

Preguntas abiertas del código que conviene resolver antes de la conversación externa:

- ¿Se corrige la Biblioteca 05 con la referencia limpia, como lo dice el experimento de mejora?
- ¿Se publica la cobertura en el panel principal junto a la cifra de skill?
- ¿Se corre la ablación del clima (cambio de una constante) para poder decir si el clima de El Salvador aporta?
