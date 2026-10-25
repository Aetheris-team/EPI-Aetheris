# Análisis: qué filtro produce la forma de la serie del tablero (2026-10-03)

> Plan fijado el 2026-10-03, antes de correr el script, en la rama `feat/mejora-tablero-fase0`
> (sale de `feat/mejora-predictor-agente`). Es la Fase 0 del plan de mejora del predictor para
> la serie del tablero. Es un análisis descriptivo: no elige ni compara modelos, no cambia el
> predictor y no usa semanas objetivo desde 2026-S38.

## Pregunta

La serie semanal de casos sospechosos del tablero de MINSAL es mucho más lisa que un conteo
crudo (ADR 0021). El ADR 0021 la describe como un promedio hacia atrás de 6 o 7 semanas, y
dice que el núcleo exacto no se puede recuperar. Antes de suavizar la historia anterior a 2025
"como lo hace MINSAL", ¿se puede decir algo más preciso sobre ese filtro con lo que ya está
capturado?

## Exploración previa, declarada

Antes de fijar este plan se miró lo siguiente, y por eso el plan no es ciego:

- La serie de sospechosos de 2025 y 2026, que ya estaba a la vista en el ADR 0021.
- Una recursión sencilla que reconstruye los conteos crudos bajo un promedio móvil con
  ventana expansiva al inicio del año (x_t = x_(t-k) + k·(y_t − y_(t−1))). Con k de 3 a 10 dio
  conteos negativos en 2026 (entre 3 y 5 semanas con valor negativo, hasta −345) y entre 1 y 7
  en 2025. Era una exploración sin tolerancia de redondeo; este análisis la repite bien hecha.
- Un ajuste de los umbrales del corredor endémico del tablero (seguridad, alerta, epidemia) a
  cuartiles de OpenDengue crudo y suavizado: no reprodujo los umbrales (error logarítmico medio
  mínimo de 0,155 en 2025). Se repite con el espacio de búsqueda fijado abajo.

Los criterios de abajo se fijaron después de esa mirada pero antes de calcular nada con el
script. No se añaden pruebas después de ver los resultados.

## Datos

- Serie de sospechosos del tablero: `casos_epidemiologicos` con la fuente `minsal_tablero`,
  `clasificacion = 'sospechoso'`, 2025-S1 a 2026-S37 (89 semanas; 2025-S53 no está publicada).
  El script la lee de Postgres, cargado con `db/seed/seed_tablero_minsal.sql`.
- OpenDengue nacional, 2014 a 2024, `casos_epidemiologicos` con la fuente `opendengue_v1_3`.
- Umbrales del corredor endémico de 2025 y 2026, extraídos de las capturas HAR del tablero
  (`tablero-10` y `tablero-04`), guardados en el JSON de resultados para que el análisis se
  pueda repetir sin las capturas.

No se consulta el sitio de MINSAL. Las capturas son las que ya cargó una persona
(ADR 0021).

## A. ¿Puede ser un promedio móvil causal de k semanas?

Para k de 2 a 12 y para tres variantes del inicio de la serie:

- W1: ventana expansiva al comienzo de cada año (el promedio usa solo las semanas disponibles
  del propio año).
- W2: ventana completa con semanas previas desconocidas, libres y no negativas (cada año por
  separado).
- W3: la serie 2025-S1 a 2026-S37 como una sola, con 2025-S53 como semana desconocida y sin
  valor publicado.

Se plantea como factibilidad: ¿existen conteos crudos x ≥ 0 tales que el promedio de cada
ventana difiere de lo publicado en a lo sumo 0,5 (el redondeo a entero)? Entre las soluciones
factibles se minimiza el máximo semanal.

- Rechazado para ese k y esa variante si no hay solución factible.
- Plausible solo si el máximo semanal de la solución no supera R_k veces el máximo de la serie
  publicada, donde R_k es el mayor cociente entre el máximo semanal crudo y el máximo del
  promedio móvil causal de k semanas que se ve en un año de OpenDengue crudo de 2014 a 2023. Es
  decir, una solución que exige una semana más extrema que cualquier año real no cuenta como
  plausible.

## B. ¿Puede ser un promedio exponencial?

y_t = α·x_t + (1 − α)·y_(t−1), con α de 0,05 a 0,95 en pasos de 0,05 y la misma tolerancia de
0,5. Factible si todos los x_t despejados pueden ser no negativos dentro de la tolerancia.
Plausible con el mismo criterio de R_α, calculado con OpenDengue crudo.

## C. Perfil de saltos

Para cada serie, el valor absoluto del cambio semanal en escala logarítmica,
|log(y_t / y_(t−1))|, con la proporción de semanas por encima de 0,15 y de 0,30, y el máximo:

- tablero 2025, tablero 2026, y 2026 sin S1 a S4;
- OpenDengue 2024;
- OpenDengue crudo de 2014 a 2023, y filtrado con el promedio móvil causal de k de 3 a 8.

La pregunta es si saltos como los de 2026 (S1 a S3, S13, S19, S26) aparecen alguna vez en
OpenDengue filtrado. Si el tablero tiene más semanas con cambio mayor que 0,30 que cualquier
año filtrado de OpenDengue (por cada 36 semanas), se concluye que esos saltos no vienen del
suavizado de conteos crudos.

## D. Umbrales del corredor

Para los umbrales de 2025 y 2026 (seguridad, alerta, epidemia) se buscan, sobre OpenDengue,
los cuartiles semanales que mejor los reproducen, variando:

- la transformación: crudo, o promedio móvil causal o centrado de k de 2 a 10;
- los años: inicio entre 2014 y 2022, fin entre 2022 y 2024 (2023 y 2024 para los umbrales
  de 2026), con y sin 2020;
- el estadístico: cuartiles 25, 50 y 75.

Métrica: error logarítmico absoluto medio entre el umbral y el cuartil, sobre las 52 semanas.
Se considera una reproducción solo si el error es menor que 0,03. Si ninguna combinación llega
ahí, el resultado es inconcluso, no una refutación, porque el método de MINSAL puede ser otro.

## Qué habilita cada resultado

- Si hay un filtro (A o B) plausible para algún k o α, se reporta cuál y se usa para suavizar
  la historia en la Fase 1, junto con la sensibilidad a sus vecinos.
- Si ningún promedio móvil ni exponencial es plausible, el filtro exacto no es identificable
  con lo publicado. El suavizado de la historia pasa a ser una aproximación declarada como
  tal, con k = 6 y k = 7 como en el ADR 0021 y su sensibilidad, y la pregunta a MINSAL sobre
  cómo se calcula la serie queda como la vía segura.
- Si C muestra que los saltos de 2026 no aparecen en OpenDengue filtrado, la predicción debe
  tratarlos como un componente aparte (por ejemplo, riesgo de salto en el cambio de año), no
  como ruido que el suavizado explica.

## Reproducibilidad

```
cd backend/ingestion
python analisis_nowcast_forma_serie.py
```

Escribe `docs/agentes/mejora-predictor/resultados-nuevos/forma_serie_tablero.json`. Usa solo
datos hasta 2026-S37. No toca el script congelado de la prueba prospectiva, la API, el
frontend ni los artefactos de `backend/api/datos/`.

## Enmiendas

1. 2026-10-03, antes de la primera corrida: el script exige Postgres para la serie del tablero y para OpenDengue; no hay lectura alternativa desde la semilla (se simplificó la sección Datos).

## Resultados (2026-10-03)

Script `backend/ingestion/analisis_nowcast_forma_serie.py`, resultados en
`docs/agentes/mejora-predictor/resultados-nuevos/forma_serie_tablero.json`. Corrió una vez, con
los criterios de arriba, sin cambios entre el plan y la corrida.

### A. Promedio móvil causal de k semanas

Cada celda dice si existen conteos crudos no negativos que reproduzcan la serie dentro del
redondeo (F), y si además la semana más extrema de la solución cabe en lo visto en OpenDengue
crudo (P). La referencia R_k va de 1,3 (k = 2) a 1,9 (k = 12).

| Variante | Resultado |
|---|---|
| W1, ventana expansiva al inicio del año | 2026: infeasible para todo k de 2 a 12. 2025: plausible solo para k = 2, 3, 4 y 6; infeasible para k = 5 y para k de 7 a 12 |
| W2, ventana completa con semanas previas libres, cada año por separado | Plausible para k de 2 a 7 en 2025 y en 2026, con la solución a menos de 1,3 veces el máximo publicado. Para k de 8 a 12 solo cumple 2025 con k = 12 y 2026 con k = 11, nunca las dos a la vez |
| W3, serie continua 2025-S1 a 2026-S37 (2025-S53 desconocida) | Factible y plausible solo para k = 2 y 3. Infeasible para todo k de 4 a 12, que incluye el 6 y el 7 del ADR 0021 |

Lectura: cada año por separado es compatible con un promedio de 2 a 7 semanas si se le permite
un pasado libre, pero la serie continua no lo es para k de 4 en adelante. Lo que no cuadra es el
cambio de año: de 39 en 2025-S52 a 214 en 2026-S1, un salto que una ventana de 4 o más semanas
sobre conteos no negativos no puede producir. Con k = 2 o 3 sí cabe, porque la semana 53 de
2025, que el tablero no publica, absorbe el atraso. Por tanto el tablero no es un único promedio
móvil de 6 o 7 semanas aplicado de forma continua. Esto no dice qué es. W1 y W2 son solo
algunas de las formas posibles de empezar un año.

### B. Promedio exponencial

En 2025 es plausible para α de 0,20 en adelante; en 2026 es infeasible para α menor que 0,45.
Una caída semanal del 43 % (98 a 56 en 2026-S19) exige α de al menos 0,43, es decir, un filtro
que reacciona casi en una semana y no uno que promedie 6 o 7. Un promedio exponencial tampoco
describe la serie.

### C. Perfil de saltos

Cambios semanales mayores que 0,30 en escala logarítmica:

| Serie | Semanas con cambio > 0,30 | Máximo |
|---|---|---|
| Tablero 2025 (51 cambios) | 0 | 0,23 |
| Tablero 2026 (36 cambios) | 3: S2 a S3 (0,32), S18 a S19 (0,56), S25 a S26 (0,34) | 0,56 |
| OpenDengue 2024 | 0 | 0,17 |
| OpenDengue 2014-2023 crudo (37 semanas por año) | mediana 8, máximo 13 | |
| ... con promedio causal de k = 3 / 5 / 6 / 7 | máximo 6 / 2 / 2 / 1 | |

Con k de 6 o 7, que son los valores del ADR 0021, ningún año de OpenDengue filtrado de 2014 a
2023 llega a 3 cambios mayores que 0,30 en 37 semanas, y el tablero de 2026 tiene 3. Con k = 3 o
4 sí aparecen hasta 6 y 4. Se cumple el criterio fijado para concluir que esos saltos no los
explica un promedio de 6 o 7 semanas sobre conteos crudos, con la salvedad de que la evidencia es
mínima (3 contra un máximo de 2 en diez años). 2025 no tiene ningún cambio mayor que 0,30,
igual que OpenDengue 2024, y 2026 tiene 3: las dos series se comportan distinto.

### D. Umbrales del corredor

Ninguna combinación reproduce los umbrales: el mejor error logarítmico medio es 0,139 en 2025
(OpenDengue 2014-2022 sin 2020, con promedio de 2 o 3 semanas) y 0,568 en 2026, contra el 0,03
exigido. Es inconcluso, como dice el plan: el corredor de MINSAL usa otros años u otro método, y
con los de 2026 la distancia es grande.

### Qué se concluye

1. El filtro exacto no es identificable con lo capturado. Descartados como descripción continua
   y completa: el promedio móvil causal de 4 o más semanas y el promedio exponencial con α menor
   que 0,45.
2. El cambio de año y algunos saltos de 2026 no vienen de un promedio de 6 o 7 semanas sobre
   conteos crudos. Las hipótesis que quedan, sin probar: reprocesos o revisiones de semanas ya
   publicadas, empalmes entre cortes del año, o un cálculo que se reinicia al cambiar de año.
3. Para la Fase 1 rige el segundo caso de "Qué habilita cada resultado": suavizar la historia
   con promedio causal de k = 6 y k = 7 y su sensibilidad es una aproximación al aspecto liso de
   2025, no una réplica del proceso. Los saltos de 2026 deben tratarse aparte.
4. 2025 y 2026 se comportan distinto. Elegir y evaluar modelos con 2025 favorece a los que
   asumen una serie lisa.
5. La forma de resolverlo es empírica. Capturar el tablero cada semana y conservar todas las
   capturas permite ver si las semanas ya publicadas cambian, que es la prueba directa de la
   hipótesis de revisiones. La otra vía es preguntar a MINSAL cómo se calcula la serie.

### Límites

- A y B usan un solo criterio de plausibilidad, tomado de OpenDengue crudo. Es amplio: W2 deja
  libres las semanas previas y por eso admite casi cualquier k pequeño.
- Se probaron promedios móviles causales y exponenciales. No se probaron filtros con pesos no
  uniformes, medianas móviles ni procesos que combinen reportes de fechas distintas.
- La mirada previa del plan ya mostraba parte de estos resultados (la recursión sin tolerancia).
