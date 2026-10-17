# Experimento: qué aportan a M0 el clima, el ONI y el tratamiento de los ceros (2026-10-02)

> Protocolo fijado el 2026-10-02, antes de la primera corrida, en la rama
> `feat/mejora-predictor-agente`. Las variantes, los años, la métrica y el criterio quedan
> escritos aquí antes de ver un resultado. Cualquier cambio posterior va en una sección de
> enmiendas con fecha, antes de la corrida a la que afecta.

## Motivación

M0 (ADR 0020) usa como variables ocho rezagos del conteo en `log1p`, tres resúmenes,
seis armónicos estacionales, siete medias de clima nacional, la anomalía ONI y el año de la
semana objetivo. Nunca se midió cuánto aporta cada grupo: no hay ablación en el repositorio
(`docs/agentes/mejora-predictor/modelo-actual.md`, sección 5.7). El sitio describe el clima
como insumo, y la Biblioteca no afirma que mejore la predicción; este experimento mide si esa
cautela es necesaria o si el clima se puede retirar sin pérdida.

La misma máquina sirve para medir un tratamiento de las semanas con cero casos de OpenDengue.
Hay nueve (2016-S15, S30, S51; 2018-S2; 2020-S53; 2022-S51; 2023-S30, S51, S52), seguidas de
una semana con aproximadamente el doble de lo habitual. La referencia limpia del experimento de
mejora deja de aprender de ellas; M0 las usa como dato tanto en los rezagos como en los
objetivos de entrenamiento. Aquí se mide si repartirlas entre las dos semanas, solo como insumo
del modelo, mejora los rangos sin cambiar la puntuación.

## Pregunta

Para cada grupo de insumo (clima, ONI, año, tratamiento de los ceros): ¿quitarlo o cambiarlo
mueve el WIS de M0 de forma sostenida en los años de validación, y en qué sentido?

## Variantes

Todas comparten lo demás con M0: `HistGradientBoostingRegressor` por cuantil con los
hiperparámetros publicados, 23 cuantiles, historia desde 2014, 2020 excluido como objetivo,
reajuste cada 2 semanas, calibración CQR-r con los 52 pares más recientes (winsorización al p90,
factor topado en 4,0), serie mixta con el hueco de 2025-S53 como ausencia.

| Variante | Qué cambia respecto a M0 |
|---|---|
| I0 | M0 sin cambios. Control: debe reproducir los cuantiles del experimento de mejora. |
| I1 | Sin la variable ONI. |
| I2 | Sin las siete medias de clima. Conserva el ONI. |
| I3 | Sin clima ni ONI. Quedan rezagos, resúmenes, estacionalidad y año. |
| I4 | Sin la variable año de la semana objetivo. |
| I5 | Ceros repartidos: en la serie de insumo (rezagos, resúmenes y objetivos de entrenamiento), cada semana de OpenDengue con 0 casos y la siguiente se reemplazan por su promedio. En el origen que es la propia semana con 0 (la siguiente no se conoce), el rezago `z[t]` toma el valor de la semana anterior. La puntuación usa siempre el conteo publicado. |

Son cinco variantes además del control. No se añaden otras después de ver un resultado.

## Datos y protocolo

Los del experimento de mejora: serie mixta (OpenDengue `total` hasta 2024, sospechosos del
tablero desde 2025), clima y ONI como en el modelo publicado, forward-chaining con ventana
expansiva y la aserción anti-fuga de `experimento_nowcast_corto_plazo.py` con su control
negativo.

- Validación (criterio): objetivos en 2019, 2021, 2022, 2023 y 2024, h = 1 a 8.
- Serie del tablero (se reporta, no decide): objetivos de 2025-S1 a 2026-S37, h = 1 a 8. Para
  cada variante se reporta también la mezcla C construida con ella (peso 0,5 con la tendencia
  amortiguada, sin cambios), porque eso es lo que se publica en ese tramo. Esos años sirvieron
  para elegir C y no son dato no visto. Ninguna semana objetivo desde 2026-S38 entra.

## Referencias

Las del experimento de mejora, calculadas sobre los mismos orígenes: persistencia limpia
(criterio en la validación), persistencia publicada y, en el tablero, la persistencia
suavizada del experimento de tendencia.

## Métrica

WIS sobre los 23 cuantiles, agrupado y por año. Skill `1 − WIS_modelo / WIS_referencia`.
Skill de cada variante contra I0, agrupado: `s = 1 − WIS_variante / WIS_I0`. Cobertura
empírica del 50 % y del 95 %. Sesgo: fracción de lo observado por debajo de la mediana.

## Criterio

Para I1 a I4, en la validación, a h = 4 y a h = 8, con `s` el skill de la variante contra I0:

- el insumo aporta si `s ≤ −0,03` en los dos horizontes y la variante pierde contra I0 en al
  menos 4 de los 5 años en los dos;
- el insumo estorba si `s ≥ +0,03` en los dos horizontes y la variante gana a I0 en al menos 4
  de los 5 años en los dos;
- en cualquier otro caso el efecto no es medible con estos datos.

Para I5, que es un candidato y no una ablación, el criterio del experimento de mejora: pasa la
validación si, a h = 4 y a h = 8, contra la persistencia limpia, el skill medio por año es
mayor que 0, gana en al menos 4 de 5 años, la cobertura del 95 % está en [0,85; 0,99] y la del
50 % en [0,35; 0,65], y su WIS agrupado no supera al de I0. Si pasa, se mira la serie del
tablero: C construida con I5 debe tener, a h = 4 y a h = 8, WIS no mayor que la C publicada y
cobertura del 95 % de al menos 0,85, con skill mayor que 0 contra la persistencia suavizada.

## Qué habilita cada resultado

- Un insumo que aporta: el sitio puede decir que el modelo usa ese insumo y que su retiro
  empeora la predicción en la validación, con la cifra.
- Un insumo que estorba: se deja descrita la variante sin ese insumo como candidata; cambiar el
  modelo publicado requiere su propia firma y una prueba con semanas posteriores.
- Un insumo sin efecto medible: el sitio sigue sin afirmar que mejora la predicción. Si el
  clima no tiene efecto medible, queda la decisión de conservarlo como insumo descriptivo o
  retirarlo del modelo para simplificar la carga de datos.
- I5 que pasa validación y tablero: queda descrito como candidato a prueba prospectiva. Si no,
  resultado negativo con las cifras.

## Controles

- Aserción anti-fuga y control negativo a h = 4 sobre los orígenes de la validación.
- I0 reproduce los cuantiles de M0 de `mejora_validacion.json` y `mejora_confirmacion.json`
  (diferencia 0 en todas las predicciones comparables); si no, el experimento se detiene.
- Control de mutación para I3 a h = 4 (etiquetas permutadas con semilla 12345): el WIS debe
  empeorar. I3 es la variante con menos información y la que más podría parecerse a una regla
  trivial.

## Reproducibilidad

Script `backend/ingestion/experimento_nowcast_insumos.py`, solo lectura sobre Postgres, con
semillas fijas, 4 procesos de un hilo cada uno y `nice`. Salida en
`backend/ingestion/data/interim/nowcast/insumos_*.json` y copia versionada en
`docs/agentes/mejora-predictor/resultados-nuevos/`.

## Enmiendas

### 2026-10-02, antes de la primera corrida: control de reproducción en el tramo del tablero

La base semilla de esta rama no contiene valores de ONI para 2025 ni 2026 (`modelo-actual.md`,
sección 3.5), y el entorno de esta rama no alcanza al servidor de NOAA para cargarlos. El
código arrastra el último valor de 2024. En una prueba del script con 12 orígenes, I0
reproduce con diferencia 0 los cuantiles de la validación (objetivos hasta 2024) y difiere en
hasta 1,8 casos por cuantil (sobre medianas de unos 100 casos) en los orígenes desde 2025-02,
donde entran pares con objetivo en 2025. La diferencia es compatible con un ONI distinto en
2025 y no se puede cerrar desde aquí.

El control queda así: en la validación la diferencia debe ser 0 (sin cambio); en el tramo del
tablero el script reporta el número de predicciones comparadas, la diferencia máxima por
cuantil y la diferencia máxima relativa de la mediana, sin detenerse. Las comparaciones entre
variantes dentro del tablero no se ven afectadas, porque todas usan los mismos datos.

### 2026-10-03, antes de repetir el tramo del tablero: ONI de 2025-2026 cargado

La rama incorpora `db/seed/seed_oni_2025_2026.sql` (commit `564590f`): el ONI mensual de NOAA de
diciembre de 2024 a julio de 2026, con la regla de `cargar_oni.py` (83 semanas; desde 2026-S31
el código arrastra el valor de julio). Con esa semilla cargada, M0 reproduce con diferencia 0
las predicciones de `mejora_confirmacion.json` a h = 1, 4 y 8 (242 predicciones comparadas).
La diferencia anterior venía solo del ONI faltante.

Se repite el tramo del tablero (2025-S1 a 2026-S37) con el mismo script y los mismos
candidatos, umbrales y criterios. La validación (objetivos hasta 2024) no cambia, porque no usa
ONI posterior a 2024, y se reutiliza de la caché por tarea. El control de reproducción del
tablero vuelve a ser exacto: se espera diferencia 0. Las cifras del tramo del tablero de la
ejecución del 2026-10-02 quedan en el historial de git; los resultados de esta sección las
reemplazan.

## Resultados (ejecución 2026-10-02; tramo del tablero repetido el 2026-10-03)

Corrida única de `experimento_nowcast_insumos.py` sobre la base de esta rama (Postgres 16
local, semillas `seed_datos_reales.sql` y `seed_tablero_minsal.sql`). Salida completa en
`docs/agentes/mejora-predictor/resultados-nuevos/insumos.json` (flotantes redondeados a 3
decimales; la copia local en `backend/ingestion/data/interim/nowcast/insumos.json` conserva la
precisión). Seis variantes, ninguna añadida después de ver resultados.

### Controles

- Garantía anti-fuga verificada en 13 orígenes a h = 4, con el control negativo rompiendo como
  se espera.
- I0 reproduce las 2.044 predicciones de M0 de `mejora_validacion.json` (2019, 2021-2024,
  h = 1 a 8) con diferencia máxima 0,000.
- En el tramo del tablero, la primera ejecución (2026-10-02, sin ONI de 2025-2026) difería de
  `mejora_confirmacion.json` desde el origen 2025-01-05. En la repetición con el ONI cargado
  (2026-10-03) I0 reproduce las 647 predicciones con diferencia 0.
- Mutación de I3 a h = 4 (etiquetas permutadas): el WIS pasa de 57,4 a 144,6.

### Validación (2019, 2021-2024): efecto de cada insumo

Skill agrupado de cada variante contra I0 (`1 − WIS_variante / WIS_I0`; positivo = la variante
es mejor que M0) y, entre paréntesis, años en que la variante mejora / empeora a I0:

| h | I1 sin ONI | I2 sin clima | I3 sin clima ni ONI | I4 sin año | I5 ceros repartidos |
|---|---|---|---|---|---|
| 1 | +0,02 (5/0) | −0,01 (2/3) | −0,01 (3/2) | +0,01 (4/1) | +0,02 (1/4) |
| 2 | −0,00 (3/2) | −0,03 (3/2) | −0,07 (4/1) | −0,03 (2/3) | −0,01 (1/4) |
| 3 | +0,01 (3/2) | −0,04 (3/2) | −0,05 (3/2) | +0,01 (2/3) | −0,03 (1/4) |
| 4 | +0,02 (3/2) | −0,02 (3/2) | −0,01 (3/2) | −0,02 (1/4) | −0,01 (1/4) |
| 5 | +0,03 (3/2) | −0,03 (3/2) | −0,03 (3/2) | −0,04 (2/3) | −0,03 (1/4) |
| 6 | +0,05 (5/0) | +0,00 (3/2) | +0,03 (3/2) | −0,08 (2/3) | −0,05 (0/5) |
| 7 | +0,03 (5/0) | −0,02 (2/3) | −0,03 (3/2) | −0,05 (1/4) | −0,04 (2/3) |
| 8 | +0,03 (5/0) | −0,04 (3/2) | −0,05 (3/2) | −0,04 (1/4) | −0,03 (1/4) |

Veredicto con el criterio fijado (|s| ≥ 0,03 a h = 4 y a h = 8 con 4 de 5 años en el mismo
sentido): ningún insumo alcanza el umbral. Los cuatro quedan como sin efecto medible.

Lo que las cifras muestran por debajo del umbral:

- Quitar el ONI (I1) nunca empeora de forma agrupada y mejora en 5 de 5 años a h = 1, 6, 7 y
  8; a h = 4 la mejora es de 0,017, por debajo del umbral. El ONI, con el arrastre mensual
  que usa M0, no aporta en esta serie.
- Quitar el clima (I2) empeora entre 0,02 y 0,04 en seis de los ocho horizontes, pero el
  efecto no es uniforme por año: a h = 4, sin clima el skill de 2022 pasa de −0,15 a −0,47 y
  el de 2024 de +0,03 a +0,26. El clima ayuda en el año de brote medio (2022) y estorba en el
  año de serie suavizada (2024). Con 3 años mejor y 2 peor, no es un aporte sostenido.
- Quitar el año (I4) empeora a 5 a 8 semanas (−0,04 a −0,08) y no cambia a 1 a 4. El año de
  la semana objetivo actúa como marca de régimen para los horizontes largos.

Métricas completas contra la persistencia limpia (WIS; skill medio por año con años ganados;
cobertura 50 %; cobertura 95 %; fracción bajo la mediana):

| h | I0 | I1 | I2 | I3 | I4 | I5 |
|---|---|---|---|---|---|---|
| 1 | 35,6; −0,04 (2/5); 0,58; 0,92; 0,46 | 34,9; −0,02 (3/5); 0,54; 0,93; 0,47 | 36,1; −0,05 (3/5); 0,58; 0,93; 0,44 | 35,9; −0,05 (3/5); 0,56; 0,92; 0,47 | 35,3; −0,02 (3/5); 0,58; 0,92; 0,48 | 35,1; −0,05 (2/5); 0,56; 0,92; 0,49 |
| 2 | 37,9; +0,06 (3/5); 0,60; 0,91; 0,45 | 38,1; +0,05 (3/5); 0,55; 0,92; 0,49 | 39,2; +0,04 (3/5); 0,58; 0,91; 0,43 | 40,7; +0,00 (3/5); 0,56; 0,92; 0,48 | 39,1; +0,04 (2/5); 0,59; 0,90; 0,48 | 38,3; +0,04 (3/5); 0,57; 0,93; 0,47 |
| 3 | 46,4; +0,05 (3/5); 0,56; 0,90; 0,46 | 45,8; +0,06 (3/5); 0,53; 0,93; 0,47 | 48,3; +0,02 (3/5); 0,53; 0,91; 0,49 | 48,5; +0,03 (3/5); 0,53; 0,91; 0,50 | 46,1; +0,05 (3/5); 0,58; 0,91; 0,48 | 47,9; −0,00 (3/5); 0,58; 0,92; 0,46 |
| 4 | 56,6; +0,05 (4/5); 0,55; 0,88; 0,47 | 55,7; +0,06 (4/5); 0,55; 0,90; 0,49 | 58,0; +0,03 (3/5); 0,55; 0,89; 0,48 | 57,4; +0,03 (3/5); 0,51; 0,89; 0,50 | 57,5; +0,03 (3/5); 0,55; 0,89; 0,53 | 57,3; +0,00 (3/5); 0,55; 0,90; 0,45 |
| 5 | 61,4; +0,12 (4/5); 0,56; 0,90; 0,47 | 59,8; +0,13 (4/5); 0,56; 0,92; 0,49 | 63,0; +0,08 (3/5); 0,57; 0,89; 0,49 | 63,5; +0,07 (3/5); 0,52; 0,93; 0,51 | 63,9; +0,09 (3/5); 0,57; 0,91; 0,53 | 63,6; +0,06 (4/5); 0,59; 0,91; 0,42 |
| 6 | 67,9; +0,13 (4/5); 0,54; 0,90; 0,47 | 64,4; +0,17 (4/5); 0,54; 0,92; 0,51 | 67,8; +0,10 (4/5); 0,55; 0,87; 0,48 | 66,1; +0,12 (4/5); 0,53; 0,94; 0,50 | 73,3; +0,08 (3/5); 0,56; 0,88; 0,51 | 71,3; +0,07 (4/5); 0,58; 0,92; 0,43 |
| 7 | 73,5; +0,16 (4/5); 0,57; 0,89; 0,42 | 71,2; +0,19 (5/5); 0,56; 0,91; 0,47 | 75,0; +0,12 (4/5); 0,56; 0,87; 0,49 | 75,8; +0,10 (3/5); 0,51; 0,91; 0,49 | 77,2; +0,13 (3/5); 0,57; 0,89; 0,49 | 76,6; +0,07 (3/5); 0,55; 0,91; 0,42 |
| 8 | 78,8; +0,18 (4/5); 0,57; 0,88; 0,43 | 76,3; +0,21 (5/5); 0,53; 0,90; 0,48 | 82,2; +0,14 (4/5); 0,61; 0,88; 0,46 | 82,4; +0,13 (3/5); 0,52; 0,89; 0,49 | 82,0; +0,16 (4/5); 0,62; 0,89; 0,47 | 81,5; +0,12 (3/5); 0,58; 0,90; 0,43 |

WIS de la persistencia limpia por horizonte: 35,2; 40,3; 48,7; 58,8; 67,7; 76,4; 85,5; 95,3
(n = 259 a 252 orígenes). Contra la referencia publicada todas las variantes ganan en 4 o 5 de
5 años en todos los horizontes (skill medio entre +0,23 y +0,39); esas tablas están en el JSON.

Skill por año contra la limpia en los horizontes decisivos:

| h = 4 | 2019 | 2021 | 2022 | 2023 | 2024 | medio |
|---|---|---|---|---|---|---|
| I0 | +0,06 | +0,04 | −0,15 | +0,26 | +0,03 | +0,05 |
| I1 | +0,09 | +0,02 | −0,16 | +0,28 | +0,04 | +0,06 |
| I2 | +0,10 | −0,03 | −0,47 | +0,29 | +0,26 | +0,03 |
| I3 | +0,13 | −0,05 | −0,49 | +0,31 | +0,25 | +0,03 |
| I4 | +0,05 | −0,03 | −0,18 | +0,25 | +0,06 | +0,03 |
| I5 | +0,10 | −0,01 | −0,23 | +0,14 | +0,01 | +0,00 |

| h = 8 | 2019 | 2021 | 2022 | 2023 | 2024 | medio |
|---|---|---|---|---|---|---|
| I0 | +0,22 | +0,09 | −0,02 | +0,15 | +0,47 | +0,18 |
| I1 | +0,23 | +0,13 | +0,04 | +0,16 | +0,50 | +0,21 |
| I2 | +0,24 | +0,01 | −0,25 | +0,15 | +0,54 | +0,14 |
| I3 | +0,27 | −0,04 | −0,34 | +0,20 | +0,55 | +0,13 |
| I4 | +0,20 | +0,12 | −0,11 | +0,11 | +0,46 | +0,16 |
| I5 | +0,22 | +0,14 | −0,04 | −0,02 | +0,30 | +0,12 |

### Validación: I5 (ceros repartidos) como candidato

I5 no pasa. A h = 4 y a h = 8 su WIS agrupado supera al de I0 (57,3 contra 56,6 y 81,5 contra
78,8), gana en 3 de 5 años contra la limpia y su skill medio es +0,00 y +0,12. La cobertura
queda en banda (0,90 al 95 % en los dos horizontes). Repartir los ceros entre las dos semanas
como insumo no acerca la predicción al dato publicado, que sigue teniendo el cero y el doble.

### Serie del tablero (2025-S1 a 2026-S37; se reporta, no decide)

Cifras de la repetición del 2026-10-03, con el ONI de 2025-2026 cargado (ver enmienda). I0
reproduce con diferencia 0 las 647 predicciones de `mejora_confirmacion.json`.

M0 con cada insumo contra la persistencia suavizada (WIS; skill agrupado con 2025 y 2026
entre paréntesis; cobertura 50 %; cobertura 95 %; fracción bajo la mediana; n = 80 u 81):

| h | I0 | I1 | I2 | I3 | I4 | I5 |
|---|---|---|---|---|---|---|
| 1 | 10,1; −0,78 (−0,88, −0,68); 0,40; 0,81; 0,71 | 10,1; −0,77 (−0,87, −0,66); 0,34; 0,80; 0,70 | 10,2; −0,79 (−0,92, −0,67); 0,38; 0,84; 0,69 | 10,1; −0,77 (−0,91, −0,63); 0,45; 0,85; 0,66 | 10,0; −0,76 (−0,85, −0,68); 0,40; 0,85; 0,69 | 9,2; −0,62 (−0,81, −0,44); 0,41; 0,81; 0,64 |
| 4 | 25,6; −0,14 (−0,33, −0,01); 0,32; 0,73; 0,73 | 25,4; −0,14 (−0,33, −0,00); 0,28; 0,75; 0,73 | 25,3; −0,13 (−0,27, −0,03); 0,27; 0,80; 0,68 | 25,4; −0,14 (−0,30, −0,02); 0,28; 0,78; 0,65 | 25,2; −0,13 (−0,32, +0,01); 0,35; 0,74; 0,72 | 24,0; −0,07 (−0,17, +0,00); 0,32; 0,67; 0,72 |
| 8 | 31,5; +0,07 (+0,11, +0,04); 0,22; 0,69; 0,67 | 31,4; +0,08 (+0,12, +0,03); 0,25; 0,75; 0,68 | 32,2; +0,05 (+0,10, +0,01); 0,20; 0,73; 0,69 | 32,6; +0,04 (+0,08, +0,00); 0,17; 0,77; 0,68 | 31,9; +0,06 (+0,10, +0,02); 0,25; 0,68; 0,67 | 29,6; +0,13 (+0,20, +0,06); 0,25; 0,77; 0,67 |

Con la serie del tablero M0 pierde contra la persistencia a 1 a 5 semanas con cualquier
insumo; ninguna ablación cambia ese cuadro. Mezcla C (peso 0,5 con la tendencia amortiguada)
construida con cada variante, misma referencia:

| h | I0 | I1 | I2 | I3 | I4 | I5 |
|---|---|---|---|---|---|---|
| 1 | 5,9; −0,04 (−0,07, −0,01); 0,55; 0,94; 0,62 | 5,9; −0,04 (−0,07, −0,00); 0,54; 0,95; 0,65 | 6,0; −0,05 (−0,07, −0,02); 0,54; 0,94; 0,59 | 5,9; −0,04 (−0,08, −0,01); 0,55; 0,94; 0,60 | 5,9; −0,04 (−0,06, −0,01); 0,59; 0,95; 0,62 | 5,6; +0,01 (−0,07, +0,08); 0,59; 0,95; 0,65 |
| 2 | 11,2; +0,09 (+0,03, +0,13); 0,53; 0,89; 0,63 | 11,3; +0,08 (+0,01, +0,13); 0,47; 0,90; 0,62 | 11,3; +0,08 (+0,04, +0,11); 0,56; 0,91; 0,60 | 11,2; +0,09 (+0,05, +0,12); 0,53; 0,90; 0,58 | 11,2; +0,09 (+0,03, +0,14); 0,52; 0,89; 0,63 | 10,7; +0,13 (+0,11, +0,14); 0,51; 0,90; 0,60 |
| 3 | 15,9; +0,11 (+0,08, +0,14); 0,46; 0,89; 0,59 | 15,9; +0,12 (+0,09, +0,13); 0,49; 0,89; 0,59 | 15,8; +0,12 (+0,12, +0,12); 0,47; 0,89; 0,57 | 15,9; +0,11 (+0,11, +0,11); 0,49; 0,89; 0,57 | 15,8; +0,12 (+0,08, +0,14); 0,51; 0,89; 0,60 | 15,3; +0,15 (+0,14, +0,15); 0,48; 0,86; 0,56 |
| 4 | 19,1; +0,15 (+0,13, +0,16); 0,41; 0,91; 0,60 | 19,3; +0,14 (+0,13, +0,15); 0,43; 0,91; 0,58 | 19,2; +0,14 (+0,17, +0,12); 0,40; 0,90; 0,57 | 19,4; +0,13 (+0,15, +0,12); 0,44; 0,90; 0,57 | 18,9; +0,15 (+0,14, +0,17); 0,42; 0,89; 0,59 | 18,5; +0,17 (+0,19, +0,16); 0,42; 0,90; 0,57 |
| 5 | 21,7; +0,16 (+0,15, +0,17); 0,42; 0,90; 0,59 | 22,1; +0,15 (+0,15, +0,15); 0,41; 0,90; 0,60 | 21,9; +0,15 (+0,17, +0,14); 0,46; 0,86; 0,58 | 22,4; +0,13 (+0,17, +0,11); 0,46; 0,86; 0,58 | 21,9; +0,15 (+0,15, +0,16); 0,41; 0,91; 0,59 | 20,9; +0,19 (+0,22, +0,17); 0,43; 0,86; 0,56 |
| 6 | 23,9; +0,17 (+0,20, +0,14); 0,40; 0,91; 0,60 | 24,3; +0,16 (+0,20, +0,12); 0,40; 0,91; 0,60 | 24,5; +0,15 (+0,19, +0,11); 0,42; 0,90; 0,60 | 24,9; +0,14 (+0,19, +0,09); 0,43; 0,90; 0,60 | 24,0; +0,17 (+0,20, +0,14); 0,41; 0,89; 0,60 | 23,4; +0,19 (+0,25, +0,14); 0,43; 0,94; 0,57 |
| 7 | 26,4; +0,17 (+0,22, +0,11); 0,40; 0,91; 0,57 | 26,6; +0,16 (+0,23, +0,10); 0,40; 0,91; 0,57 | 27,0; +0,15 (+0,23, +0,08); 0,40; 0,91; 0,58 | 27,5; +0,13 (+0,22, +0,05); 0,43; 0,91; 0,59 | 25,9; +0,18 (+0,24, +0,13); 0,40; 0,91; 0,56 | 25,7; +0,19 (+0,26, +0,13); 0,40; 0,91; 0,56 |
| 8 | 28,6; +0,16 (+0,23, +0,09); 0,35; 0,90; 0,56 | 28,8; +0,15 (+0,23, +0,08); 0,37; 0,89; 0,56 | 28,5; +0,16 (+0,24, +0,08); 0,41; 0,94; 0,62 | 29,0; +0,15 (+0,23, +0,06); 0,40; 0,93; 0,62 | 28,2; +0,17 (+0,23, +0,11); 0,33; 0,91; 0,57 | 27,6; +0,19 (+0,27, +0,11); 0,40; 0,94; 0,57 |

WIS de la persistencia suavizada por horizonte: 5,7; 12,3; 17,9; 22,4; 25,9; 28,8; 31,7; 34,0.
Skill de C con cada variante contra C con I0: entre −0,04 y +0,02 para I1 a I4 en
todos los horizontes; I5 entre +0,02 y +0,05 en los ocho. En este tramo C con I5
cumpliría las tres condiciones del tablero a h = 4 y h = 8, pero no decide porque I5 no pasó la
validación, y 2025-2026 sirvieron para elegir C.

C con I0 a h = 4 da WIS 19,1 contra 22,4 (skill agrupado 0,15, cobertura 0,41 al
50 % y 0,91 al 95 %). El bloque `desempeno` de `nowcast_dengue.json` (19,6 contra 22,8; 0,39 y
0,91) usa 77 semanas objetivo desde 2025-01-26; aquí son 81 desde 2025-S1. Las predicciones
son las mismas.

### Veredicto

- Clima, ONI, año y tratamiento de los ceros: sin efecto medible con el umbral fijado. El sitio
  puede seguir diciendo que el modelo usa clima y ONI como insumo; no puede decir que mejoran
  la predicción. Retirar el ONI no empeoraría nada medible (es la variante con mejor cifra en
  todos los horizontes salvo h = 2) y simplificaría la carga de datos; retirar el clima costaría
  entre 0,02 y 0,04 de WIS agrupado a 2 a 8 semanas, concentrado en 2022. Ninguna de las dos
  cosas se decide aquí.
- I5 (ceros repartidos): resultado negativo en la validación.

### Limitaciones

- Una sola serie y cinco temporadas de validación: diferencias de 0,02 a 0,03 en skill
  agrupado quedan dentro de lo que un año mueve (2022 solo decide el signo de I2).
- La ablación quita variables sin reajustar hiperparámetros; un modelo sin clima podría
  beneficiarse de otra configuración, pero eso sería un barrido sobre los años de validación
  que el protocolo excluye.
- El ONI entra con arrastre mensual (desde 2026-S31, con el valor de julio de 2026, el último
  publicado); la ablación mide ese insumo tal como M0 lo usa, no el valor del ENSO en general.
