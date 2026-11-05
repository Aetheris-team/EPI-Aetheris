# Búsqueda de mejoras al predictor de dengue: informe (2026-10-02, actualizado el 2026-10-03)

Rama `feat/mejora-predictor-agente`. Tres experimentos con protocolo escrito y commiteado antes
de correr, scripts reproducibles y resultados versionados. Cada cifra de este informe sale de
uno de estos archivos, todos en `docs/agentes/mejora-predictor/resultados-nuevos/`:

| Experimento | Protocolo y resultados | Script | Resultados |
|---|---|---|---|
| Insumos de M0 (clima, ONI, año, ceros) | `docs/experimentos/experimento-nowcast-insumos.md` | `backend/ingestion/experimento_nowcast_insumos.py` | `insumos.json` |
| Calibración de rangos y ajustes de corto plazo | `docs/experimentos/experimento-nowcast-rangos.md` | `backend/ingestion/experimento_nowcast_rangos.py` | `rangos.json` |
| Brotes sin precedente y una familia lineal | `docs/experimentos/experimento-nowcast-recorte.md` | `backend/ingestion/experimento_nowcast_recorte.py` | `recorte.json` |
| Dónde fallan los rangos en 2026 (descriptivo, a pedido de la revisión del PR) | `docs/experimentos/analisis-cobertura-2026.md` | `backend/ingestion/analisis_nowcast_cobertura_2026.py` | `cobertura_2026.json` |

Piezas compartidas en `backend/ingestion/experimento_nowcast_comun.py`, con 20 pruebas sin base
de datos en `backend/ingestion/tests/test_experimento_nowcast_comun.py`.

## Qué mejora hay

No hay una mejora lista para reemplazar el modelo publicado. Hay un candidato débil y un
indicio que merece su propia firma:

1. **Calibrar M0 con 104 pares en vez de 52 (capa R2).** En la validación de OpenDengue (2019 y
   2021-2024) es la única capa de calibración que pasa el criterio fijado. Su efecto se
   concentra en 2022, el año que la calibración actual cubre peor.

   | h | cobertura 95 % (52 → 104 pares) | cobertura 50 % | WIS |
   |---|---|---|---|
   | 4 | 0,88 → 0,91 | 0,55 → 0,54 | 56,6 → 54,9 |
   | 8 | 0,88 → 0,91 | 0,57 → 0,56 | 78,8 → 80,9 |

   Es un candidato débil. La cobertura del 95 % pasa la banda fijada (0,90 a 0,99) pero sigue
   por debajo del nominal, el WIS a 8 semanas empeora, y el resultado sale de una sola pasada
   sobre los mismos cinco años con tres capas candidatas. En la serie del tablero, que es lo que
   se sirve desde 2025, no corrige el problema que motivó la pregunta: la cobertura del 95 % de
   C en 2026 pasa de 0,79 a 0,76 a 4 semanas y de 0,79 a 0,72 a 8. No se recomienda para C.
2. **El peso 0,5 de M0 en C es alto a 1 y 2 semanas.** En 2025-2026 la tendencia amortiguada
   sola tiene WIS 4,7 a 1 semana, contra 5,9 de C y 5,7 de la persistencia suavizada. El peso
   elegido por desempeño reciente (C1) mejora C a 1 y 2 semanas y la empeora a 4 y 8; no pasa
   su criterio. Con una ventana de 52 semanas en vez de 26 (una sensibilidad), mejora C a 1, 2 y
   3 semanas, queda a menos de 2 % de C a 4 y 8, y solo incumple la cobertura del 95 % a 8
   semanas (0,84 contra 0,85). Un peso fijo por horizonte es una hipótesis contaminada: 2025-2026 ya sirvieron
   para elegir C. Solo vale con un protocolo firmado antes y semanas objetivo posteriores que no
   se crucen con la prueba prospectiva en curso (desde 2026-S38 hasta 2027-S05).

Aparte, quitar el ONI de M0 sería una simplificación sin costo medible, no una mejora: en la
validación la variante sin ONI no empeora en ningún horizonte decisivo, pero con cinco
temporadas y un umbral de ±0,03 la prueba tiene poca potencia para detectar efectos pequeños.

## Qué se descartó y por qué

| Línea | Resultado | Cifra decisiva |
|---|---|---|
| Ablación de clima (I2), ONI (I1), clima y ONI (I3), año (I4) | Sin efecto medible con el umbral fijado, lo que no equivale a sin efecto: con cinco temporadas la prueba solo detecta efectos grandes (±0,03 de skill contra M0 a 4 y 8 semanas, en 4 de 5 años) | Skill contra M0 a h = 4 y h = 8: I1 +0,02 y +0,03; I2 −0,02 y −0,04; I3 −0,01 y −0,05; I4 −0,02 y −0,04. Ninguno con 4 de 5 años en el mismo sentido en los dos horizontes |
| Ceros de vacaciones repartidos como insumo (I5) | No pasa la validación | WIS 57,3 contra 56,6 de M0 a h = 4; 3 de 5 años ganados |
| CQR-r asimétrica (R1) | No pasa: estrecha los rangos | Cobertura del 95 %: 0,77 a h = 4 |
| Conformal adaptativo (R3) | No pasa: cuesta 8 % a 13 % de WIS | WIS 63,7 contra 56,6 a h = 4 |
| Calibrar la mezcla C (R4) | No cumple en el tablero | Cobertura del 95 %: 0,69 a h = 4 |
| Corrección del sesgo reciente (S1) | Empeora en las dos series | Skill contra M0: −0,14 a h = 1, −0,44 a h = 4 |
| Peso de la mezcla por desempeño reciente (C1) | No cumple: gana a 1-2 semanas, pierde a 4-8 | WIS 4,7 contra 5,9 a h = 1; 31,4 contra 28,6 a h = 8 |
| Regresión cuantílica lineal (L0) como familia que extrapola | No pasa la validación normal; 0 de 5 años ganados a h = 4 | Skill medio por año contra la persistencia limpia −0,37 a h = 4 |

Ideas de la revisión bibliográfica descartadas sin correr, por falta de datos o de condiciones:
modelos de retraso de notificación (MINSAL no publica fechas de notificación ni versiones
sucesivas), serotipos, entomología, movilidad y búsquedas web (no existen series públicas con
licencia clara en el proyecto), modelos espacio-temporales (la serie departamental termina en
2023), y redes neuronales (574 semanas de OpenDengue y 89 del tablero, y exigirían una
dependencia nueva). Esto último es una línea no abierta, no un resultado negativo.

Ninguna cifra de la revisión se verificó: el proxy de red de este entorno bloquea pnas.org,
pmc.ncbi.nlm.nih.gov, medrxiv.org y plos.org. Ninguna se usa como dato. La revisión mezcla
métricas no comparables (SUCRA, R², sensibilidad y valor predictivo de alertas municipales,
CRPS de un ejercicio estatal) y contextos distintos del de este proyecto.

## Afirmaciones del sitio frente a lo medido

| Afirmación o pregunta | Lo medido | Estado |
|---|---|---|
| "Ante un brote sin precedente en la serie, la predicción puede quedarse corta" | Sin un año de magnitud comparable en la historia, M0 queda detrás de la persistencia en 2019 (skill −0,80 a h = 4 y −0,28 a h = 8) y en 2022 (−1,02 y −0,33). En el pico, su mediana vale el 12 % (2019) y el 41 % (2022) de lo observado. Con la historia completa, 57 % y 91 %. En 2024, que sí tiene precedente, el recorte no cambia el resultado (+0,01 y +0,28) | Confirmada, con dos años de soporte en vez de uno |
| El modelo usa clima y ONI | Cierto; su aporte no es medible con el umbral fijado. El clima ayuda en 2022 (sin clima, skill −0,47 contra −0,15 a h = 4) y estorba en 2024 (+0,26 contra +0,03) | Se puede decir que se usan; no que mejoran la predicción |
| La ventaja a 5-8 semanas se midió en 2019-2024 | Reproducida sin diferencia: skill medio contra la persistencia limpia +0,12 a +0,18, 4 de 5 años | Confirmada |
| Los rangos tienen la probabilidad nominal (glosario) | Validación: 0,55 al 50 % y 0,88 al 95 % a 4 semanas. Tablero 2026: 0,79 al 95 %. Ninguna de las cinco capas probadas lleva 2026 a 0,85. 37 de los 40 fallos de 2026 caen en dos escalones de la serie (2026-S1 a S4 y S19 a S23); fuera de ellos la cobertura del 95 % es 1,00 a 1 a 4 semanas | Sigue por debajo del nominal; los fallos de 2026 son de posición ante saltos bruscos, no de ancho |
| A 1-3 semanas M0 rinde como la persistencia limpia | Reproducido: skill agrupado −0,01, +0,06 y +0,05 | Confirmada |

## Reproducción y límites del entorno

- Postgres 16 local (sin Docker en el entorno), migraciones `0001` a `0013`,
  `seed_datos_reales.sql` y `seed_tablero_minsal.sql` (356 filas del tablero, verificadas con
  la consulta del paquete de instrucciones). Los scripts se corren desde `backend/ingestion/`
  con `POSTGRES_HOST=localhost`; tardaron 2 h 08 min, 46 min y 24 min con 4 procesos de un
  hilo. Cada uno tiene un modo `--humo` (pocos orígenes, sin escribir resultados versionados)
  que se usó para probar el código antes de las corridas completas; ningún parámetro, umbral
  ni candidato se cambió después de esas pruebas, y las enmiendas de implementación están
  fechadas en cada protocolo.
- Los tres scripts reproducen con diferencia 0 las 2.044 predicciones de M0 de
  `mejora_validacion.json`, y C reproduce las 416 de 2024 de `tendencia_verificacion.json`.
- La primera ejecución (2026-10-02) se hizo sin ONI de 2025-2026 y sus predicciones de ese
  tramo diferían de las publicadas. El 2026-10-03 se añadió `db/seed/seed_oni_2025_2026.sql`
  (ONI mensual de NOAA de diciembre de 2024 a julio de 2026) y se repitió el tramo del tablero
  de los experimentos de insumos y de rangos y el análisis de cobertura, con enmiendas
  fechadas antes de la repetición. Con ese ONI, M0 y C reproducen con diferencia 0 las 647
  predicciones publicadas de 2025-2026. Ningún veredicto cambió; las cifras de este informe son
  las de la repetición. El experimento de recorte no usa datos posteriores a 2024 y no se
  repitió.
- Los valores del ONI de la semilla no se pudieron contrastar desde este entorno con el archivo
  de NOAA (el proxy bloquea el servidor). Que las predicciones publicadas se reproduzcan sin
  diferencia indica que son los mismos valores con que se generaron los artefactos.
- El bloque `desempeno` de `nowcast_dengue.json` usa 77 semanas objetivo desde 2025-01-26 a 4
  semanas; los experimentos usan 81 desde 2025-S1. Las predicciones coinciden; las cifras
  agregadas difieren por la muestra.
- No se usó ninguna semana objetivo desde 2026-S38. El script de la prueba prospectiva
  congelada (`experimento_nowcast_tendencia.py`) no se modificó. No se tocaron la API, el
  frontend, los artefactos de `backend/api/datos/` ni el esquema.
- Las pruebas del repositorio pasan: 382 aprobadas y 18 saltadas.

## Dónde fallan los rangos en 2026

En 2026 hay 231 predicciones de C con objetivo hasta S37 y 40 caen fuera del rango del 95 %. 37
de ellas están en dos tramos de semanas objetivo, y todas las de cada tramo salen por el mismo
lado:

| tramo | lo observado | lo que pasó | lado de los fallos |
|---|---|---|---|
| 2026-S1 a S4 | 39 casos en 2025-S52 y 214 en 2026-S1 (×5,5 en una semana) | La predicción seguía la bajada de diciembre: a 4 semanas, mediana 55 y rango del 95 % de 5 a 110 para S1 | Por arriba: la predicción quedó corta |
| 2026-S19 a S23 | 98 casos en S18 y 56 en S19 (−43 % en una semana) | La predicción esperaba la subida de mayo: a 4 semanas, medianas de 108 a 131 para S20 a S22, observados 53 a 55 | Por abajo: la predicción quedó larga |

Fuera de esos tramos la cobertura del 95 % de 2026 es 1,00 a 1 a 4 semanas y entre 0,91 y 0,95 a
5 a 8. Los fallos son de posición ante saltos bruscos, no de ancho, y por eso ninguna capa de
calibración los corrige. En el cambio de año falla más la tendencia amortiguada; en S19-S22
falla más M0.

Que los dos escalones vengan de cómo se construye la serie del tablero, y no de la transmisión,
es una hipótesis que no se puede comprobar con una sola tanda de capturas. Un promedio de 6 o 7
semanas hacia atrás no multiplica por 5,5 de una semana a la siguiente salvo que su ventana se
reinicie al cambiar de año o que la tabla de origen se reescriba.

Riesgo para la prueba prospectiva en curso: su conjunto incluye el cambio de año. Si el escalón
se repite en 2027-S1, las semanas 2027-S1 a S3 pueden quedar fuera del rango, y el criterio
admite 3 de 20 semanas fuera. No se cambia nada: el criterio y el script congelado quedan como
están, y el protocolo ya reporta como sensibilidad las cifras sin las semanas 50 a 3.

## Decisiones para la persona dueña del proyecto

1. Si se retira el ONI de M0 como simplificación. No empeora nada medible en la validación,
   pero cambiar el modelo publicado requiere su propia firma.
2. Si se firma un experimento de peso por horizonte en C (por ejemplo, menos peso de M0 a 1 y
   2 semanas), con semanas objetivo posteriores a la firma que no se crucen con la prueba
   prospectiva en curso.
3. Si se intenta comprobar el origen de los escalones del tablero, por ejemplo con capturas
   sucesivas de las primeras semanas de 2027 o consultando a MINSAL cómo calcula la serie.
4. Si la Biblioteca incorpora la cifra de saturación ante brotes sin precedente (12 % y 41 %
   de lo observado en el pico) junto a la salvedad que ya tiene.

N_CAL = 104 queda descartado para C: no mejora la cobertura del tablero.

## Pendiente, en el orden en que lo haría

1. Si se firma el peso por horizonte, escribir su protocolo y esperar semanas objetivo
   posteriores al corte de la prueba prospectiva.
2. Incorporar `db/seed/seed_oni_2025_2026.sql` a la carga documentada (después de
   `seed_datos_reales.sql`), para que el tramo del tablero se reproduzca desde un clon limpio.
   Los scripts guardan caché por tarea en `backend/ingestion/data/interim/nowcast/cache/`, sin
   control de cambios en los datos: si cambian los datos, hay que borrar ahí las tareas
   afectadas antes de repetir.
3. Una comparación con modelos externos, cuando haya predicciones públicas para El Salvador
   sobre el mismo objetivo, horizonte y periodo. No se hizo ninguna aquí.
