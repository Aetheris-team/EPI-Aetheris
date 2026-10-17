# Experimento: modelo estructural del tablero (2026-10-03)

> Protocolo escrito el 2026-10-03, en la rama `feat/mejora-tablero-estructural`, antes de escribir
> o correr ningún script. Continúa `analisis-forma-serie-tablero.md` y `experimento-nowcast-theta-ets.md`.
> No toca la prueba prospectiva congelada (`experimento-nowcast-tendencia.md`, script
> `40b6ebb78fe670222966a225438155b83ada876d`), las candidatas K1 a K4, la web, el backend ni los
> artefactos de `backend/api/datos/`.

## Pregunta

El plan de mejora tenía un punto 2C: si la serie del tablero es el promedio de k semanas de
conteos crudos, el cambio de una semana a la siguiente es

y(t+1) = y(t) + (x(t+1) − x(t+1−k)) / k,

donde x son los conteos crudos. El término x(t+1−k) es la semana que sale de la ventana y ya
ocurrió. Un modelo que lo conociera sabría, antes de que pase, cuánto va a bajar o subir la serie
por lo que sale. Ni T ni C usan esa información. ¿Se puede aplicar ese modelo con los datos que hay, y
qué parte de la ganancia posible está al alcance?

## Por qué no se puede probar tal cual

Tres requisitos, que el modelo estructural necesita y los datos no cumplen:

1. La forma del filtro conocida y continua. El análisis de forma de la serie (Fase 0) descartó el
   promedio móvil causal de 4 o más semanas como descripción de la serie continua 2025-S1 a
   2026-S37, y atribuyó el salto del cambio de año y tres saltos de 2026 a algo distinto de un
   promedio de 6 o 7 semanas. El filtro no es identificable con lo capturado.
2. Los conteos crudos x. Un promedio móvil de k semanas deja sin determinar cualquier secuencia de
   período k y suma cero: sumada a x, da la misma y. Los conteos que salen de la ventana solo se
   recuperan hasta esa ambigüedad, salvo que se conozcan k semanas crudas contiguas como ancla, y
   cada redondeo de y a entero arrastra error a la ancla.
3. Validación fuera del sesgo. La historia hasta 2023 que usa el predictor es el promedio exacto de
   7 semanas de OpenDengue crudo. Cualquier modelo estructural validado en esos años acierta por
   construcción, igual que ocurrió con la ganancia de ETS, que desapareció en el tablero.

La comprobación de enteros (si k · y es entero) tampoco identifica k: todos los valores de
2022 a 2026 de la base son enteros y la fracción es 1,0 para todo k de 2 a 12.

## Estado de la información

- Los datos son los de la base: OpenDengue hasta 2024-S52 y el tablero de 2025-S1 a 2026-S37, de
  las capturas del 2026-09-27. Quien escribe este protocolo ya vio las series de 2023, 2024, 2025 y
  2026 (valores y gráficos de la Fase 0). Las pruebas de abajo son por eso descriptivas y de
  compuerta, no confirmatorias.
- Ninguna semana objetivo de 2026-S38 en adelante está en la base ni se mira. No se carga ninguna
  captura. No se calcula ningún pronóstico en este documento.

## Etapas

Cada etapa tiene una regla de parada escrita antes de verla. Las etapas posteriores a una parada no
se corren.

### E0a. ¿OpenDengue 2024 continúa el crudo de 2023? (descriptiva, sin decisión)

Es la única ocasión en que hay un ancla real: los conteos crudos de OpenDengue 2023 junto a una serie
ya promediada, la de 2024. Para cada k de 2 a 12 se plantea el programa lineal de la Fase 0: existen
conteos x(s) no negativos para las k − 1 semanas previas a 2024-S1 y las 52 de 2024, tales que el
promedio causal de k semanas queda a no más de 0,5 de cada valor publicado de 2024.

Tres variantes del pasado (las k − 1 semanas de 2023 anteriores a 2024-S1):

- P: fijo a los valores crudos de OpenDengue 2023.
- P': fijo, salvo las semanas con valor 0, que quedan libres y no negativas. Los ceros del cierre de
  año son casos que las vacaciones dejaron sin notificar y que pasan a la semana siguiente.
- L: todo libre y no negativo.

Se reporta, por k y variante, si es factible y, si lo es, el error de identificación e_id de E0b
(definido abajo) con origen en 2024-S52, para los k desde 4. Si L es factible y P' no, el crudo de 2023 no es el insumo de la serie de 2024
(otra fuente o otro corte). No hay regla de parada: describe el insumo y no decide nada.

### E0b. Ancho de identificación en el régimen que importa (compuerta)

Se calcula, para el tablero, cuánta de la información de la semana que sale de la ventana queda
determinada por los datos, aun si el filtro fuese exactamente un promedio causal de k semanas.

Para cada año del tablero por separado (el pasado de k − 1 semanas libre y no negativo), cada k de 2
a 12 y cada origen t de la lista de abajo, con los datos del año hasta t:

- Factibilidad del programa lineal con tolerancia 0,5 (la de la Fase 0).
- Para h = 4, la suma S de los conteos crudos de las h semanas más antiguas de la ventana, es decir
  x(t−k+1) + … + x(t−k+h). Es la cantidad que el modelo estructural necesita saber. Su mínimo y
  su máximo se obtienen por programa lineal. El error de identificación del pronóstico a h = 4 es

  e_id = (máximo de S − mínimo de S) / (2 · k · y(t)).

- Orígenes: 2026-S20 a 2026-S37, para la compuerta. Los de 2025-S20 a 2025-S51, como contraste.

Magnitud contra la que se compara: m4, la mediana de |y(t+4) − y(t)| / y(t) sobre los pares dentro
del mismo año con dato en los dos extremos, en 2025 y 2026 (semanas ya vistas). Es cuánto se mueve la
serie en 4 semanas, que es lo que un pronosticador tiene que explicar.

Compuerta. Sea G el conjunto de k de 4 a 9 que son factibles con el año completo en 2025 y en 2026
(se mira solo la factibilidad; el criterio de plausibilidad de la Fase 0 no se repite). La
compuerta se supera si algún k de G cumple que la mediana de e_id sobre los orígenes 2026-S20 a
2026-S37 es menor o igual que 0,25 · m4.

Por qué esa regla: es una condición necesaria. Si ni la cota optimista de identificación (el
programa lineal da el rango máximo posible, sin ninguna otra suposición) cabe en una cuarta parte
del movimiento de la serie, el término que sale de la ventana no se puede usar. Superarla deja
abierta una prueba de pronóstico y no anticipa su resultado.

La probabilidad previa de superarla es baja, por la ambigüedad de período k de arriba. La
restricción de no negatividad puede apretar el rango cuando los conteos son pequeños, y por eso se
mide en vez de suponerse.

### E1. Prueba de pronóstico (condicional)

Solo si se supera la compuerta de E0b. Se escribe entonces un protocolo propio, firmado antes de
cualquier script, con una versión del modelo estructural que reconstruya los conteos de la ventana
con una regularización fija, la compare contra T y C con la regla de cambio del experimento de
tendencia (ganancia media de skill mayor o igual que 0,005 y al menos 3 de 5 años) y la confirme en
2024 y en 2025 a 2026-S37. Nada de eso se define ni se corre aquí.

## Qué habilita cada resultado

- Si E0b no supera la compuerta, el modelo estructural se descarta con los datos disponibles. Se
  reabre solo si llega información que identifique el filtro: capturas semanales que conserven todas
  las versiones del tablero, o la respuesta de MINSAL sobre cómo calcula la serie. Se cierra el
  punto 2C del plan con esa conclusión.
- Si la supera, se redacta el protocolo de E1. El sitio no cambia por este experimento en ningún caso.
- E0a no habilita nada por sí sola.

## Reproducibilidad

- Script `backend/ingestion/analisis_nowcast_estructural.py`, con pruebas en
  `backend/ingestion/tests/test_estructural.py`. Se escriben y se commitean antes de correr.
- Reutiliza `cargar` y la tolerancia de `analisis_nowcast_forma_serie.py`. Lee Postgres, solo hasta
  2026-S37; no consulta el sitio de MINSAL.
- Salida: `docs/agentes/mejora-predictor/resultados-nuevos/estructural_identificacion.json`.
- Se corre una sola vez con estos criterios. Los resultados y las conclusiones se agregan al final de
  este documento.

## Enmiendas

1. 2026-10-03, antes de escribir el script: en E0a la cantidad reportada era la suma de los
   conteos crudos de las k últimas semanas, que queda fijada por el promedio publicado (k veces el
   valor, con la tolerancia) y no informa nada. Se reemplaza por e_id de E0b, que mide la suma de
   las semanas más antiguas de la ventana. E0b no cambia. En E0b, e_id se calcula solo para los k
   desde 4, porque con h = 4 y ventana menor que 4 las semanas que salen incluyen semanas futuras.
2. 2026-10-03, después de la corrida (ver Resultados): la compuerta, tal como estaba escrita, admite
   k = 4 con h = 4. En ese caso las semanas que salen son toda la ventana, su suma queda fijada por
   el valor publicado y el término que sale no aporta nada al pronóstico, porque y(t+4) es entonces
   el promedio de cuatro semanas futuras. Se agrega la condición k mayor que h (k de 5 a 9). La
   corrección se hace con los resultados a la vista; el motivo es aritmético y no depende de los
   datos, y endurece la compuerta. Se reportan las dos lecturas.

## Resultados (2026-10-03)

Script `backend/ingestion/analisis_nowcast_estructural.py` (commit `3dfa79e`), pruebas
`tests/test_estructural.py`, salida en
`docs/agentes/mejora-predictor/resultados-nuevos/estructural_identificacion.json`. Corrió una vez,
con los criterios del protocolo y sus dos enmiendas. Solo datos hasta 2026-S37.

### E0b. Ancho de identificación en el tablero

La magnitud de comparación es m4 = 0,179 (mediana del movimiento relativo a 4 semanas en 2025 y
2026), y el umbral 0,25 · m4 = 0,0446. Los k de 4 a 9 son factibles en 2025 y en 2026, así que G
contiene los seis. e_id es la mitad del ancho del rango de la suma de las 4 semanas más antiguas
de la ventana, relativa al nivel, con las cotas del programa lineal:

| k | e_id mediana 2026 (mínimo a máximo, 18 orígenes) | e_id mediana 2025 (contraste, 32 orígenes) |
|---|---|---|
| 4 | 0,0035 (0,0015 a 0,0094) | 0,0040 |
| 5 | 0,118 (0,062 a 0,314) | 0,323 |
| 6 | 0,099 (0,048 a 0,241) | 0,312 |
| 7 | 0,116 (0,056 a 0,305) | 0,252 |
| 8 | 0,106 (0,049 a 0,278) | 0,216 |
| 9 | 0,106 (0,048 a 0,278) | 0,207 |

Fuera de G, solo informativo: en 2026, k = 10, 11 y 12 dan 0,092, 0,092 y 0,082. En 2025, k = 10 y 11
son infactibles.

Lectura literal de la regla: la compuerta se supera, con k = 4 solamente.

Lectura con la enmienda 2: k = 4 no cuenta, porque con h = 4 la suma de las semanas que salen es
4 · y(t) por construcción. Para k de 5 a 9 las medianas de 2026 van de 0,099 a 0,118, entre 2,2 y
2,7 veces el umbral, y la compuerta no se supera. Sensibilidad: el umbral tendría que subir a 0,55
veces m4 para que k = 6 pasara. Lo que el modelo estructural necesita saber cuando la ventana tiene 5
a 9 semanas queda sin determinar en un 10 a 12 % del nivel, frente a un movimiento
típico de 18 % en 4 semanas. En 2025 es peor, de 21 a 32 %.

### E0a. OpenDengue 2024 con el crudo de 2023 como ancla (descriptiva)

| k | Factible con P, P' y L | e_id en 2024-S52 |
|---|---|---|
| 2, 3 | las tres | no se define (k menor que 4) |
| 4 | las tres | 0,0054 (caso k = h) |
| 5 | las tres | 0,108 con P y con P'; 0,356 con L |
| 6 | solo L | 0,323 con L |
| 7 | P' y L | 0,105 con P'; 0,323 con L |
| 8 a 12 | solo L | de 0,101 a 0,383 con L |

El ancla de 2023 admite para 2024 un promedio causal de 2 a 5 semanas con el crudo tal cual, o de
7 semanas si se liberan los dos ceros del cierre de 2023; no admite 6 ni 8 a 12. No identifica k. Aun
con el ancla fija, el error de identificación al final de 2024 es de 0,105 a 0,108, más del doble del
umbral. Por la forma de la recursión, el margen del redondeo de cada valor publicado se suma semana
a semana desde el ancla.

### Qué se concluye

1. Con los datos del tablero, el término de la semana que sale de la ventana no se puede usar:
   incluso en la cota optimista (el filtro exacto, la tolerancia de redondeo y nada más), el rango
   para k de 5 a 9 abarca el 10 a 12 % del nivel a h = 4. La compuerta de E0b no se supera con la
   lectura que corrige el caso k = h.
2. El mejor caso que existe, un ancla de conteos crudos reales de 2023 y un año de 2024 compatible
   con k = 7, tampoco baja de 0,105 al cierre del año.
3. No se escribe el protocolo de E1. El modelo estructural se descarta con los datos disponibles y se
   cierra el punto 2C del plan. Se reabre si llega información que identifique el filtro: capturas
   semanales que conserven todas las versiones del tablero, o la respuesta de MINSAL sobre cómo
   calcula la serie. La lectura literal (k = 4) dejaría abierto E1; no se sigue por esa vía por lo
   que dice la enmienda 2. Si Eduardo quiere E1 de todos modos, necesita su propio protocolo.

### Límites

- El rango del programa lineal es una cota sobre toda secuencia no negativa, sin ninguna suposición
  sobre cómo se comportan los conteos crudos. Con un supuesto de suavidad el rango bajaría, pero
  entonces la reconstrucción de la ventana coincide con la extrapolación suave que T ya hace, y
  la parte que escapa a T está en la componente que el supuesto descarta.
- Supone que el filtro es exactamente un promedio causal uniforme de k semanas, que la Fase 0 no
  confirmó para la serie continua. Si el filtro es otro, el término que sale de la ventana no
  tiene la forma del protocolo.
- El umbral de 0,25 · m4 es una elección propia, sin calibrar contra el error de T. La sensibilidad
  de arriba muestra que la conclusión se mantiene hasta un umbral más del doble de grande.
- La serie es una sola captura del tablero, del 2026-09-27.
