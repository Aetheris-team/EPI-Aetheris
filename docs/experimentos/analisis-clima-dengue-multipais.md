# Análisis exploratorio: El Salvador frente a 18 países de las Américas (2026-10-03)

> Protocolo escrito el 2026-10-03, en la rama `feat/clima-dengue-por-anio`, antes de escribir o
> correr ningún script. Continúa `analisis-clima-dengue-por-anio.md` y el experimento multipaís del
> clasificador (`experimento-multipais.md`, hoy en el repo STC; última versión aquí en `ef698c8^`).
> No toca la prueba prospectiva congelada, las candidatas K1 a K4, el predictor, el backend ni los
> artefactos de `backend/api/datos/`. Ninguna decisión de modelado depende de este análisis.

## Pregunta

El experimento multipaís midió que la anomalía anual de casos de El Salvador correlaciona +0,280 con
la señal regional de 18 países, la más baja de todos. Esa cifra existe en un documento histórico y no
se ha reproducido ni ampliado. Este análisis la reproduce con los datos de entonces y la acompaña con
lo que permiten los mismos datos: el perfil de cada país, la incertidumbre de la medida, su
estabilidad, la asociación semanal entre el clima y el crecimiento de los casos medida igual que en
El Salvador, y el ciclo medio de casos y clima. El objetivo es dejar registradas las cifras con las
que cualquier lector pueda ubicar a El Salvador frente a los otros países. No se busca explicar por qué
difiere.

## Estado de la información

- Quien escribe este protocolo ya vio, de este conjunto de datos, las cifras reproducidas en un ensayo
  previo a este protocolo: con la definición de P2 salen 0,453 de correlación media entre países,
  51,8 % del primer componente, +0,280 para El Salvador (el menor de 18), 0,952 Colombia, 0,908
  Guatemala y 0,868 Honduras, iguales a las del documento histórico. Se probaron cuatro definiciones de
  anomalía (log1p del total anual estandarizado, total crudo, razón a la media y rangos); solo la
  primera reproduce las cifras y es la que se fija. La señal regional es la media de las anomalías de
  los 18 países, El Salvador incluido.
- No ha visto ninguna otra cifra de P1, P3, P4 ni de los intervalos y sensibilidades de P2.
- El análisis del clima de El Salvador por año (`analisis-clima-dengue-por-anio.md`) ya está hecho y es
  una entrada de este: sus valores para El Salvador son el contraste de P3.

## Datos

- Casos: `Temporal_extract_PAHO_V1_3.csv` del repositorio de OpenDengue
  (`https://github.com/OpenDengue/master-repo`, `assets/Temporal_extract_PAHO_V1_3.zip`), filas
  `S_res = Admin0` y `T_res = Week`, años 2014 a 2024, columna `dengue_total`. No se versiona. La
  salida guarda su SHA-256. Los 18 países son los que tienen al menos 45 semanas en cada uno de los 11
  años. Hay 16 con clima de superficie completo.
- Clima: Open-Meteo, un punto por país (`CENTROIDES` de `experimento_multipais.py`), diario de 2013 a
  2024, modelos `era5_land` (temperatura, humedad y punto de rocío) y `era5` (lluvia y horas de lluvia),
  del caché de ese experimento. No se versiona. La salida guarda su SHA-256. Bermuda e Islas Vírgenes
  (EE. UU.) devuelven nulo en las 5 variables de superficie y solo tienen las 2 de lluvia.
- ONI: `oni_anom` semanal de la base (la misma serie para todos los países).
- Años de análisis semanal: 2014 a 2019 y 2021 a 2023, los mismos 9 de El Salvador. Los totales anuales
  de P2 usan los 11 años (replicación) y los 9 (sensibilidad).

## Construcción semanal

Las funciones son las de `analisis_clima_por_anio.py` (importadas, no reescritas). Para cada país:

- Rejilla de semanas por fecha de inicio (`calendar_start_date`); las semanas ausentes quedan como
  faltantes. El año de una semana es el de su columna `Year`. La semana del año es
  `min((día del año − 1) // 7 + 1, 52)` a partir de la fecha de inicio, que difiere a lo sumo en una
  semana de la numeración epidemiológica de cada país.
- z: log1p del promedio de las 4 semanas que terminan en t, incluyendo las semanas con cero. A
  diferencia del análisis de El Salvador, los ceros no se tratan como faltantes porque en los países de
  baja incidencia son ceros reales. El Salvador se recalcula así para que la comparación sea de la
  misma construcción.
- Clima semanal: suma de 7 días para `precipitation_sum` y `precipitation_hours`, media para las demás,
  con al menos 5 días con dato; si no, faltante.
- Anomalías, climatología sin el año evaluado, g y pares: como en El Salvador (horizonte 4, ventana
  de 4 semanas, suavizado de 5 semanas, bloque de 8, 2000 remuestreos, semilla 20261003 más el índice
  del país y el año).
- ONI: el valor de la semana epidemiológica de El Salvador que contiene la fecha de inicio.

## Análisis (lista cerrada)

### P1. Perfil de cada país (descriptiva)

Por país: punto de clima, semanas por año, total anual 2014 a 2024, casos semanales medios y fracción
de semanas con cero (años de análisis), R² de 3 armónicos de z, semana del máximo del ciclo medio de
z, desviación estándar entre años del log1p del total anual, y cociente entre el total del año mayor
y la mediana de los totales.

### P2. Señal regional (replicación y ampliación)

- Anomalía anual: log1p del total anual, estandarizado dentro de cada país con los 11 años. Señal
  regional: media de las anomalías de los 18 países.
- Por país: correlación con la señal regional (incluye al propio país), con la señal de los otros 17
  países, y la matriz de correlaciones de a pares. Correlación media entre pares, parte de la varianza
  del primer componente y correlación de la señal con el ONI anual (media de las semanas de cada año).
- Intervalo del 95 % de la correlación de cada país con la señal: bootstrap sobre los años (2000
  remuestreos con reposición de los pares anomalía y señal de cada año).
- Estabilidad de El Salvador: su correlación al quitar cada año de los 11, y al quitar cada otro país de
  la señal; mínimo y máximo.
- Subconjunto centroamericano: Guatemala, Honduras, Nicaragua, Costa Rica, Panamá y El Salvador. Para
  cada uno, correlación con la media de los otros cinco.
- Sensibilidad: las mismas correlaciones con los 9 años de análisis.
- Verificación: el script se detiene si no reproduce, con diferencia menor que 0,0015, la correlación
  media entre pares (0,453), la parte del primer componente (0,518), y las correlaciones de El Salvador
  (0,280), Colombia (0,952), Guatemala (0,908) y Honduras (0,868); y si El Salvador no es el menor de
  los 18. La correlación con el ONI se verifica contra 0,517 con tolerancia de 0,015.

### P3. Asociación entre la anomalía climática y el crecimiento, por país

Cada país con las variables que tenga: las 7 climáticas (2 en las dos islas sin clima de superficie) y
el ONI. Misma estadística que A3: correlación de Pearson entre la anomalía climática en t y la
anomalía del crecimiento a 4 semanas, por año y agrupada, con intervalo del 95 % por bootstrap de
bloques. Un año de un país es evaluable si su total anual es al menos 100 casos y tiene al menos 30
pares completos. Un país tiene estimación agrupada si tiene al menos 5 años evaluables.

Etiqueta de consistencia: un país y una variable son consistentes si el signo de r es el mismo en
todos los años evaluables salvo a lo sumo uno y el intervalo agrupado excluye el cero; si no, variable
según el año. Sin estimación agrupada, no evaluable. Se reportan todos los países y todas las
variables, sin elegir.

### P4. Ciclo medio por país

Por país y variable climática: R² de 3 armónicos de la variable, y desfase de 0 a 16 semanas con la
mayor correlación entre la climatología de la variable y la de z desplazada hacia adelante, con esa
correlación y una marca si el máximo está en el borde (16). Se guardan las 52 semanas de la climatología
de z y de cada variable para dibujar.

### P5. Corridas anteriores del clasificador (lectura, sin recalcular)

De los resultados guardados de las corridas A (solo El Salvador, entrenando con los otros países), B
(regional) y C (regional con ONI): por corrida y año, soporte real de la clase alto, F1 y recall de alto
del modelo y de la climatología (medias sobre las semillas), semillas en que el modelo supera a la
climatología y semillas totales. Se citan con su procedencia (experimento del 2026-08-16, script
`experimento_multipais.py`).

### P6. Posición de El Salvador (derivada, sin cálculo nuevo)

Posición de El Salvador entre los países evaluables en: correlación con la señal regional, correlación
con los otros 17, desviación entre años, R² estacional, y correlación agrupada de la lluvia en mm y del
ONI con el crecimiento. Se reporta la posición y el número de países, de menor a mayor.

## Qué se puede decir con cada resultado

- El sitio puede afirmar que El Salvador tiene la menor correlación con la señal regional de los 18
  países solo si lo es en la medida principal y en la sensibilidad de 9 años. Si no, reporta la
  posición en cada una. En ambos casos muestra el intervalo.
- Las posiciones de P6 y las asociaciones de P3 se presentan como descripción de estos datos. Ninguna
  frase afirma una causa de las diferencias entre países. Las explicaciones posibles (serotipos,
  inmunidad, control vectorial, definición de caso, notificación, demografía) no se observan y se
  nombran, si se nombran, como no medidas.
- Los países de baja incidencia, o de gran extensión donde un punto no representa el clima (Brasil,
  México, Estados Unidos, Colombia, Bolivia), se marcan en la salida.

## Límites

- Un punto de clima por país. Para países grandes no representa el territorio.
- Las series de la OPS no tienen la misma definición de caso en todos los países; el campo
  `case_definition_standardised` de la fuente es `Total`, sin más detalle.
- Once años anuales: las correlaciones con la señal tienen intervalos amplios.
- Los años 2020 y 2024 se mantienen en los totales anuales de P2 (replicación) y quedan fuera del
  análisis semanal. La serie de El Salvador de 2024 es un promedio de varias semanas hecho en origen.
- La semana del año se calcula por fecha y puede diferir en una de la de cada país.
- P5 no se recalcula: las corridas anteriores no se vuelven a ejecutar.

## Reproducibilidad

- Script `backend/ingestion/analisis_clima_multipais.py`, con pruebas en
  `backend/ingestion/tests/test_clima_multipais.py`, que se escriben y se confirman en un commit
  anterior a la primera corrida. Lee Postgres (solo el ONI) y los dos archivos locales; no consulta ningún
  sitio externo.
- Salida: `docs/agentes/mejora-predictor/resultados-nuevos/clima_multipais.json`. Los resultados y
  su lectura se añaden a este documento en una sección posterior; un cambio al protocolo después de ver
  resultados se anota como enmienda con fecha y motivo.

## Enmiendas al protocolo

2026-10-03, después de la primera corrida y antes de escribir los resultados:

- La sección de sensibilidad de P2 decía "las mismas correlaciones con los 9 años" y el script omitía la versión del subconjunto centroamericano. Se añadió `centroamerica_9_anios`.
- Al ver los resultados de la primera corrida se añadió `sin_baja_incidencia`: las mismas medidas de P2 sin Bermudas e Islas Vírgenes (EE. UU.), con totales anuales de 0 a 3 casos en Bermudas y de 0 a 19 en Islas Vírgenes, salvo 185 en Islas Vírgenes en 2024. No estaba en el protocolo y se decidió después de conocer la posición de El Salvador.
- La segunda corrida se comparó con la primera: todas las demás secciones del JSON son idénticas, y solo cambian las dos claves nuevas de P2.

## Resultados (2026-10-03)

Entradas de la corrida: casos `Temporal_extract_PAHO_V1_3.csv` con SHA-256 `f8eaa7134dd7e4a718df16ec5e2bfdd60bf446732281a1bbf3a1463084af230f`; clima `clima_multipais.json` con SHA-256 `066f17474daa3fa7e020a8e83b83a54b3826c3a0fc81601eea325b4a49e55d48`. La salida completa está en `docs/agentes/mejora-predictor/resultados-nuevos/clima_multipais.json`, incluidas las 52 semanas de la climatología de casos y de cada variable de cada país (P4) y la matriz de correlaciones de a pares (P2).

### Verificación de la replicación

El script reprodujo, con diferencia menor que 0,0015, las cifras del documento histórico: correlación media entre pares 0,453, primer componente 0,518, El Salvador +0,280 (el menor de los 18), Colombia +0,952, Guatemala +0,908 y Honduras +0,868. La correlación de la señal con el ONI anual dio 0,527 frente a 0,517 del documento, dentro de la tolerancia fijada de 0,015.

### P2. Señal regional

| medida | 11 años (principal) | 9 años (sensibilidad) | sin las dos islas de baja incidencia (11 años) |
|---|---|---|---|
| correlación media entre pares | 0,453 | 0,387 | 0,448 |
| parte de la varianza del primer componente | 0,518 | 0,469 | 0,522 |
| correlación de la señal con el ONI anual | 0,527 |  |  |

Correlación de la anomalía anual de cada país con la señal regional, ordenada de menor a mayor. La columna de 16 países excluye a Bermudas e Islas Vírgenes (EE. UU.) y recalcula la señal sin ellas.

| país | r con la señal | intervalo 95 % | r con los otros 17 | pos. | r con la señal (9 años) | r con los otros 17 (9 años) | pos. (9 años) | r con la señal (16 países) |
|---|---|---|---|---|---|---|---|---|
| El Salvador | +0,280 | [−0,16; +0,80] | +0,204 | 1 | +0,465 | +0,394 | 5 | +0,283 |
| Barbados | +0,412 | [−0,14; +0,78] | +0,342 | 2 | +0,410 | +0,336 | 4 | +0,387 |
| Nicaragua | +0,512 | [+0,07; +0,84] | +0,449 | 3 | +0,560 | +0,497 | 8 | +0,541 |
| Jamaica | +0,544 | [+0,10; +0,86] | +0,484 | 4 | +0,557 | +0,494 | 7 | +0,532 |
| Estados Unidos | +0,586 | [−0,15; +0,94] | +0,530 | 5 | +0,365 | +0,287 | 2 | +0,551 |
| Panamá | +0,614 | [−0,20; +0,91] | +0,560 | 6 | +0,365 | +0,288 | 3 | +0,602 |
| Islas Vírgenes (EE. UU.) | +0,633 | [−0,02; +0,92] | +0,581 | 7 | +0,316 | +0,236 | 1 | sin dato |
| Ecuador | +0,651 | [−0,07; +0,91] | +0,601 | 8 | +0,490 | +0,421 | 6 | +0,664 |
| Puerto Rico | +0,657 | [+0,01; +0,90] | +0,607 | 9 | +0,624 | +0,567 | 9 | +0,671 |
| Bolivia | +0,682 | [+0,22; +0,98] | +0,635 | 10 | +0,866 | +0,842 | 15 | +0,722 |
| República Dominicana | +0,768 | [+0,47; +0,95] | +0,733 | 11 | +0,895 | +0,875 | 17 | +0,813 |
| Bermudas | +0,817 | [+0,56; +0,95] | +0,788 | 12 | +0,741 | +0,699 | 10 | sin dato |
| Brasil | +0,860 | [+0,46; +0,99] | +0,836 | 13 | +0,762 | +0,723 | 11 | +0,869 |
| Honduras | +0,868 | [+0,64; +0,97] | +0,846 | 14 | +0,794 | +0,759 | 12 | +0,867 |
| México | +0,872 | [+0,64; +0,97] | +0,851 | 15 | +0,801 | +0,766 | 13 | +0,867 |
| Costa Rica | +0,898 | [+0,74; +0,97] | +0,880 | 16 | +0,889 | +0,869 | 16 | +0,900 |
| Guatemala | +0,908 | [+0,73; +0,99] | +0,892 | 17 | +0,860 | +0,835 | 14 | +0,905 |
| Colombia | +0,952 | [+0,89; +0,99] | +0,944 | 18 | +0,922 | +0,907 | 18 | +0,944 |

Lectura de la tabla:

- En la medida principal (11 años) El Salvador es el de menor correlación con la señal, +0,280, y con la señal de los otros 17, +0,204. El intervalo del 95 % es de −0,16 a +0,80 y contiene el valor puntual de 10 de los otros 17 países. Seis de los 18 intervalos incluyen el cero (El Salvador, Barbados, Estados Unidos, Panamá, Ecuador e Islas Vírgenes).
- En la sensibilidad de 9 años (sin 2020 ni 2024) El Salvador sube a +0,465 y queda en la posición 5 de 18. Los cuatro países por debajo son Islas Vírgenes (+0,316), Estados Unidos (+0,365), Panamá (+0,365) y Barbados (+0,410). La regla fijada en el protocolo permite decir que El Salvador es el de menor correlación solo si ocurre en las dos medidas, y no ocurre. Se reportan las dos posiciones.
- Sin las dos islas de baja incidencia, El Salvador sigue en la posición 1 de 16 (+0,283).
- La correlación media entre pares baja de 0,453 a 0,387 y el primer componente de 0,518 a 0,469 al usar 9 años. Sin las dos islas no cambian de forma apreciable (0,448 y 0,522).

Anomalía anual de El Salvador y señal regional, año por año:

| año | casos de El Salvador | anomalía de El Salvador | señal regional |
|---|---|---|---|
| 2014 | 53.196 | +1,76 | +0,19 |
| 2015 | 50.169 | +1,69 | +0,17 |
| 2016 | 8.789 | −0,34 | +0,28 |
| 2017 | 4.402 | −1,15 | −0,88 |
| 2018 | 8.439 | −0,39 | −1,04 |
| 2019 | 27.490 | +0,99 | +0,44 |
| 2020 | 5.334 | −0,92 | −0,22 |
| 2021 | 5.752 | −0,83 | −0,85 |
| 2022 | 16.542 | +0,40 | −0,15 |
| 2023 | 5.863 | −0,81 | +0,69 |
| 2024 | 8.477 | −0,38 | +1,36 |

En 2014 y 2015 El Salvador tiene sus dos mayores anomalías (+1,76 y +1,69) mientras la señal regional está cerca de cero (+0,19 y +0,17). En 2023 y 2024 la señal regional es la más alta de la serie (+0,69 y +1,36) y El Salvador está por debajo de su media (−0,81 y −0,38).

Estabilidad de la correlación de El Salvador (+0,280) al quitar un año de los 11:

| año quitado | r de El Salvador |
|---|---|
| 2014 | +0,288 |
| 2015 | +0,291 |
| 2016 | +0,298 |
| 2017 | +0,165 |
| 2018 | +0,250 |
| 2019 | +0,231 |
| 2020 | +0,263 |
| 2021 | +0,196 |
| 2022 | +0,290 |
| 2023 | +0,390 |
| 2024 | +0,464 |

Al quitar un país de la señal:

| país quitado de la señal | r de El Salvador |
|---|---|
| Estados Unidos | +0,255 |
| República Dominicana | +0,259 |
| Honduras | +0,261 |
| Puerto Rico | +0,263 |
| Islas Vírgenes (EE. UU.) | +0,276 |
| Colombia | +0,278 |
| Guatemala | +0,279 |
| México | +0,282 |
| Bermudas | +0,287 |
| Barbados | +0,289 |
| Ecuador | +0,289 |
| Costa Rica | +0,291 |
| Jamaica | +0,301 |
| Nicaragua | +0,302 |
| Brasil | +0,303 |
| Bolivia | +0,305 |
| Panamá | +0,315 |

Al quitar un año la correlación va de +0,165 (sin 2017) a +0,464 (sin 2024). Al quitar un país va de +0,255 (sin Estados Unidos) a +0,315 (sin Panamá).

Subconjunto centroamericano, correlación de cada país con la media de los otros cinco:

| país | r con la media de los otros cinco (11 años) | 9 años |
|---|---|---|
| El Salvador | +0,118 | +0,191 |
| Nicaragua | +0,537 | +0,611 |
| Panamá | +0,554 | +0,338 |
| Costa Rica | +0,655 | +0,596 |
| Honduras | +0,760 | +0,674 |
| Guatemala | +0,923 | +0,905 |

El Salvador es el menor de los seis en las dos versiones: +0,118 con 11 años y +0,191 con 9, frente a +0,537 a +0,923 y +0,338 a +0,905 de los otros cinco. En la versión de 9 años Panamá (+0,338) es el más cercano.

### P1. Perfil de cada país

| país | casos semanales medios | semanas con cero | R² de 3 armónicos | semana del máximo | desv. del log1p del total anual | máximo / mediana anual | año del mayor total | marcas | punto de clima (lat.; long.) |
|---|---|---|---|---|---|---|---|---|---|
| Brasil | 30.169 | 0 % | 0,56 | 16 | 0,87 | 6,2 | 2024 | país extenso | −14,24; −51,93 |
| México | 2.744 | 1 % | 0,59 | 43 | 0,74 | 4,5 | 2024 | país extenso | 23,63; −102,55 |
| Nicaragua | 1.704 | 0 % | 0,23 | 35 | 0,54 | 2,9 | 2019 |  | 12,87; −85,21 |
| Colombia | 1.617 | 0 % | 0,02 | 49 | 0,62 | 3,3 | 2024 | país extenso | 4,57; −74,30 |
| Honduras | 716 | 0 % | 0,12 | 28 | 0,99 | 7,0 | 2024 |  | 14,75; −86,24 |
| Bolivia | 658 | 0 % | 0,38 | 14 | 0,93 | 7,1 | 2023 | país extenso | −16,29; −63,59 |
| Guatemala | 412 | 0 % | 0,26 | 35 | 1,24 | 21,1 | 2024 |  | 15,70; −90,36 |
| El Salvador | 384 | 2 % | 0,17 | 36 | 0,86 | 6,3 | 2014 |  | 13,79; −88,90 |
| Ecuador | 341 | 0 % | 0,32 | 22 | 0,76 | 3,8 | 2024 |  | −1,83; −78,18 |
| Costa Rica | 242 | 0 % | 0,35 | 34 | 0,74 | 3,2 | 2023 |  | 9,75; −83,75 |
| República Dominicana | 205 | 0 % | 0,13 | 43 | 0,94 | 4,3 | 2023 |  | 18,74; −70,16 |
| Panamá | 166 | 0 % | 0,33 | 50 | 0,75 | 4,7 | 2024 |  | 8,54; −80,78 |
| Jamaica | 43,5 | 35 % | 0,07 | 46 | 1,59 | 9,1 | 2023 |  | 18,11; −77,30 |
| Puerto Rico | 29,4 | 36 % | 0,02 | 48 | 2,98 | 9,7 | 2014 |  | 18,22; −66,59 |
| Barbados | 15,5 | 15 % | 0,07 | 41 | 1,04 | 4,5 | 2014 |  | 13,19; −59,54 |
| Estados Unidos | 12,7 | 22 % | 0,19 | 45 | 0,92 | 4,7 | 2024 | país extenso | 27,99; −81,76 |
| Islas Vírgenes (EE. UU.) | 0,072 | 96 % | 0,02 | 5 | 1,65 |  | 2024 | baja incidencia; solo lluvia | 18,34; −64,90 |
| Bermudas | 0,013 | 99 % | 0,06 | 33 | 0,53 |  | 2024 | baja incidencia; solo lluvia | 32,32; −64,76 |

Totales anuales de la fuente (suma de las semanas del año):

| país | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Barbados | 2.666 | 503 | 1.732 | 597 | 69 | 125 | 1.342 | 448 | 339 | 798 | 1.106 |
| Bermudas | 1 | 0 | 2 | 0 | 0 | 2 | 0 | 0 | 0 | 1 | 3 |
| Bolivia | 22.409 | 27.099 | 32.386 | 9.310 | 7.925 | 21.567 | 109.498 | 8.947 | 20.007 | 159.713 | 49.470 |
| Brasil | 586.510 | 1.649.008 | 2.220.482 | 512.827 | 470.269 | 2.253.883 | 1.446.298 | 975.474 | 2.363.490 | 3.147.717 | 10.184.099 |
| Colombia | 105.590 | 96.444 | 101.016 | 25.775 | 46.037 | 126.919 | 77.910 | 53.334 | 69.497 | 135.531 | 317.235 |
| Costa Rica | 10.901 | 17.394 | 23.319 | 5.607 | 2.718 | 9.472 | 9.955 | 5.174 | 7.485 | 31.565 | 30.343 |
| Ecuador | 15.460 | 42.473 | 14.159 | 11.429 | 3.140 | 8.480 | 19.803 | 20.829 | 16.017 | 28.313 | 60.854 |
| El Salvador | 53.196 | 50.169 | 8.789 | 4.402 | 8.439 | 27.490 | 5.334 | 5.752 | 16.542 | 5.863 | 8.477 |
| Estados Unidos | 659 | 945 | 990 | 453 | 331 | 1.158 | 307 | 114 | 1.156 | 156 | 3.071 |
| Guatemala | 19.764 | 18.058 | 8.844 | 4.308 | 6.850 | 50.540 | 5.761 | 2.861 | 8.553 | 73.975 | 186.968 |
| Honduras | 42.594 | 44.834 | 22.961 | 5.258 | 8.187 | 132.905 | 24.132 | 19.753 | 25.337 | 34.761 | 176.498 |
| Islas Vírgenes (EE. UU.) | 19 | 3 | 11 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 185 |
| Jamaica | 878 | 88 | 2.297 | 219 | 1.155 | 7.382 | 898 | 96 | 100 | 8.213 | 2.001 |
| México | 124.729 | 219.593 | 130.069 | 89.961 | 78.642 | 268.494 | 120.514 | 36.742 | 59.918 | 281.615 | 555.194 |
| Nicaragua | 34.998 | 49.326 | 88.463 | 65.400 | 59.315 | 186.405 | 52.464 | 36.741 | 97.541 | 182.642 | 90.476 |
| Panamá | 4.426 | 3.347 | 7.884 | 9.275 | 6.849 | 9.741 | 3.507 | 3.095 | 11.924 | 21.437 | 36.718 |
| Puerto Rico | 8.766 | 1.867 | 168 | 0 | 0 | 47 | 904 | 636 | 1.023 | 1.292 | 6.038 |
| República Dominicana | 6.068 | 17.048 | 6.645 | 1.367 | 1.602 | 20.323 | 3.776 | 3.746 | 10.784 | 28.737 | 9.486 |

Lectura de las dos tablas:

- El Salvador ocupa posiciones intermedias en los descriptores de amplitud y estacionalidad: octavo de 18 en casos semanales medios, octavo de menor a mayor en la desviación entre años del log1p del total anual (0,86) y noveno de menor a mayor en el R² de 3 armónicos de los casos (0,17). Diez de los 18 países tienen un R² estacional menor que 0,2.
- El año de mayor total anual es 2024 en 10 de los 18 países (Brasil, México, Colombia, Honduras, Guatemala, Ecuador, Panamá, Estados Unidos, Bermudas e Islas Vírgenes), 2023 en 4 (Bolivia, Costa Rica, República Dominicana, Jamaica), 2019 en Nicaragua y 2014 en tres (El Salvador, Puerto Rico, Barbados). El total de El Salvador en 2024 es 8.477 frente a 53.196 en 2014.
- Bermudas e Islas Vírgenes (EE. UU.) tienen una fracción de semanas con cero de 99 % y 96 %.

### P3. Clima y crecimiento de los casos, por país

Correlación agrupada entre la anomalía climática en t y la anomalía del crecimiento a 4 semanas, para los años evaluables de cada país. El asterisco marca un intervalo del 95 % que excluye el cero. La daga marca además la etiqueta consistente de la regla del protocolo. Bermudas e Islas Vírgenes (EE. UU.) no tienen años evaluables.

| país | temp. media | temp. máx. | temp. mín. | lluvia (mm) | lluvia (horas) | humedad | pto. de rocío | ONI |
|---|---|---|---|---|---|---|---|---|
| Barbados | +0,17 | +0,15 | +0,19 | −0,07 | +0,02 | −0,12 | +0,04 | +0,27† |
| Bolivia | −0,14* | −0,07 | −0,21* | +0,02 | −0,04 | −0,08 | −0,17 | −0,04 |
| Brasil | −0,07 | −0,05 | −0,09 | +0,03 | +0,04 | +0,06 | +0,03 | +0,02 |
| Colombia | −0,08 | −0,10 | −0,02 | +0,13* | +0,15* | +0,19* | +0,20* | +0,05 |
| Costa Rica | +0,12 | +0,20* | +0,04 | +0,10 | +0,01 | −0,19* | −0,10 | +0,19 |
| Ecuador | −0,03 | −0,01 | +0,06 | −0,01 | +0,10 | +0,08 | +0,05 | +0,09 |
| El Salvador | +0,13* | +0,16* | +0,05 | −0,16* | −0,21† | −0,16* | −0,06 | −0,09 |
| Estados Unidos | −0,06 | −0,07 | −0,02 | +0,04 | +0,04 | +0,07 | +0,01 | +0,07 |
| Guatemala | +0,01 | +0,04 | −0,07 | −0,05 | −0,05 | −0,10 | −0,11 | −0,05 |
| Honduras | +0,02 | −0,01 | +0,09 | −0,07 | +0,03 | +0,02 | +0,07 | +0,06 |
| Jamaica | +0,09 | +0,13* | +0,05 | +0,01 | +0,05 | −0,05 | +0,00 | +0,12 |
| México | +0,06 | +0,04 | +0,13 | −0,06 | +0,05 | +0,05 | +0,08 | +0,07 |
| Nicaragua | +0,00 | −0,08 | +0,10 | +0,02 | +0,14* | +0,07 | +0,10 | +0,08 |
| Panamá | −0,09 | −0,08 | −0,07 | +0,15† | +0,06 | +0,13* | +0,00 | −0,03 |
| Puerto Rico | +0,16* | +0,14 | +0,11† | +0,02 | +0,10 | −0,08 | +0,00 | −0,01 |
| República Dominicana | −0,03 | −0,08 | +0,06 | +0,11 | +0,14* | +0,12 | +0,09 | +0,09 |

Años evaluables (total anual de al menos 100 casos y al menos 30 pares):

| país | años evaluables | pares por año (mín.–máx.) |
|---|---|---|
| Barbados | 2014, 2015, 2016, 2017, 2019, 2021, 2022, 2023 | 48–49 |
| Bermudas | ninguno |  |
| Bolivia | 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023 | 48–49 |
| Brasil | 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023 | 48–49 |
| Colombia | 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023 | 48–49 |
| Costa Rica | 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023 | 48–49 |
| Ecuador | 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023 | 48–49 |
| El Salvador | 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023 | 48–49 |
| Estados Unidos | 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023 | 48–49 |
| Guatemala | 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023 | 48–49 |
| Honduras | 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023 | 48–49 |
| Islas Vírgenes (EE. UU.) | ninguno |  |
| Jamaica | 2014, 2016, 2017, 2018, 2019, 2022, 2023 | 48–49 |
| México | 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023 | 48–49 |
| Nicaragua | 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023 | 48–49 |
| Panamá | 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023 | 48–49 |
| Puerto Rico | 2014, 2015, 2016, 2021, 2022, 2023 | 48–49 |
| República Dominicana | 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023 | 48–49 |

De las 128 celdas país por variable, 21 tienen el intervalo agrupado fuera del cero y 4 cumplen la regla de consistencia: lluvia en horas en El Salvador (1 año positivo, 8 negativos), lluvia en mm en Panamá (8 positivos, 1 negativo), temperatura mínima en Puerto Rico (5 y 1) y ONI en Barbados (7 y 1). Diez de los 16 países tienen al menos una celda con intervalo fuera del cero. Con 128 celdas y un nivel del 95 % se esperarían unas 6 celdas con el intervalo fuera del cero si no hubiera asociación, aunque las celdas no son independientes entre sí porque las variables y los países están correlacionados.

Las 21 celdas con el intervalo fuera del cero:

| país | variable | r agrupado | intervalo 95 % | años r>0 / r<0 | etiqueta |
|---|---|---|---|---|---|
| Bolivia | temp. media | −0,142 | [−0,23; −0,05] | 4 / 5 | variable según el año |
| El Salvador | temp. media | +0,129 | [+0,02; +0,34] | 6 / 3 | variable según el año |
| Puerto Rico | temp. media | +0,161 | [+0,04; +0,36] | 4 / 2 | variable según el año |
| Costa Rica | temp. máx. | +0,195 | [+0,02; +0,41] | 6 / 3 | variable según el año |
| El Salvador | temp. máx. | +0,156 | [+0,04; +0,34] | 6 / 3 | variable según el año |
| Jamaica | temp. máx. | +0,130 | [+0,00; +0,22] | 4 / 3 | variable según el año |
| Bolivia | temp. mín. | −0,206 | [−0,30; −0,10] | 4 / 5 | variable según el año |
| Puerto Rico | temp. mín. | +0,108 | [+0,02; +0,27] | 5 / 1 | consistente |
| Colombia | lluvia (mm) | +0,131 | [+0,06; +0,32] | 6 / 3 | variable según el año |
| El Salvador | lluvia (mm) | −0,158 | [−0,30; −0,04] | 3 / 6 | variable según el año |
| Panamá | lluvia (mm) | +0,153 | [+0,02; +0,23] | 8 / 1 | consistente |
| Colombia | lluvia (horas) | +0,152 | [+0,08; +0,34] | 7 / 2 | variable según el año |
| El Salvador | lluvia (horas) | −0,213 | [−0,38; −0,11] | 1 / 8 | consistente |
| Nicaragua | lluvia (horas) | +0,140 | [+0,02; +0,30] | 6 / 3 | variable según el año |
| República Dominicana | lluvia (horas) | +0,136 | [+0,02; +0,29] | 7 / 2 | variable según el año |
| Colombia | humedad | +0,187 | [+0,06; +0,40] | 7 / 2 | variable según el año |
| Costa Rica | humedad | −0,189 | [−0,38; −0,04] | 4 / 5 | variable según el año |
| El Salvador | humedad | −0,163 | [−0,31; −0,02] | 2 / 7 | variable según el año |
| Panamá | humedad | +0,128 | [+0,00; +0,23] | 7 / 2 | variable según el año |
| Colombia | pto. de rocío | +0,198 | [+0,06; +0,39] | 7 / 2 | variable según el año |
| Barbados | ONI | +0,265 | [+0,04; +0,39] | 7 / 1 | consistente |

Lectura:

- Lluvia en mm: El Salvador (−0,158) es el único de los 16 países con el intervalo entero por debajo de cero. Colombia (+0,131) y Panamá (+0,153) lo tienen entero por encima. La mediana de los otros 15 países es +0,017, con 10 países positivos y 6 negativos en total.
- Lluvia en horas: El Salvador (−0,213) es el menor de los 16. Hay 13 países con valor positivo y la mediana de los otros 15 es +0,046.
- ONI: El Salvador (−0,086) es el menor de los 16, con el intervalo [−0,17; +0,20], que incluye el cero. La mediana de los otros 15 es +0,069.
- Humedad: El Salvador (−0,163) es el segundo menor, después de Costa Rica (−0,189). Colombia (+0,187) y Panamá (+0,128) tienen el intervalo fuera del cero con signo positivo.
- Temperatura: El Salvador tiene valores positivos en temperatura media (+0,129) y máxima (+0,156) con el intervalo fuera del cero. Bolivia tiene valores negativos en temperatura media y mínima.
- Colombia tiene el intervalo fuera del cero y signo positivo en 4 variables (lluvia, horas de lluvia, humedad y punto de rocío).

Esta construcción difiere de la del análisis de El Salvador por año en tres puntos: los ceros cuentan como casos y no como faltantes, la semana del año sale de la fecha de inicio y la serie es la de OpenDengue y no la de la base de datos. Resultado para El Salvador con las dos construcciones:

| variable | esta construcción (ceros incluidos, semanas por fecha) | análisis de El Salvador por año (ceros como faltantes) |
|---|---|---|
| temp. media | +0,13 [+0,02; +0,34] | +0,18 [+0,06; +0,36] |
| temp. máx. | +0,16 [+0,04; +0,34] | +0,19 [+0,07; +0,36] |
| temp. mín. | +0,05 [−0,03; +0,30] | +0,14 [+0,02; +0,35] |
| lluvia (mm) | −0,16 [−0,30; −0,04] | −0,17 [−0,34; −0,06] |
| lluvia (horas) | −0,21 [−0,38; −0,11] | −0,20 [−0,37; −0,09] |
| humedad | −0,16 [−0,31; −0,02] | −0,17 [−0,33; −0,04] |
| pto. de rocío | −0,06 [−0,15; +0,14] | −0,04 [−0,19; +0,15] |
| ONI | −0,09 [−0,17; +0,20] | −0,04 [−0,13; +0,22] |

Los valores agrupados difieren en 0,06 o menos, salvo la temperatura mínima (+0,05 frente a +0,14). La etiqueta de la lluvia en mm cambia: en el análisis por año había 1 año positivo y 8 negativos (consistente) y aquí hay 3 positivos y 6 negativos (variable según el año). Los años que cambian de signo son 2014 (de −0,29 a +0,06) y 2016 (de −0,18 a +0,00).

Correlaciones por año de El Salvador con esta construcción, lluvia en mm: 2014 +0,06; 2015 −0,28; 2016 +0,00; 2017 −0,31; 2018 −0,11; 2019 −0,22; 2021 −0,39; 2022 −0,21; 2023 +0,07. ONI: 2014 −0,49; 2015 −0,07; 2016 −0,40; 2017 −0,55; 2018 +0,01; 2019 +0,07; 2021 −0,71; 2022 +0,29; 2023 +0,14.

### P4. Ciclo medio

Para cada país, desfase en semanas (de 0 a 16) con la mayor correlación entre la climatología de la variable y la climatología de z de los casos desplazada hacia adelante, y esa correlación entre paréntesis. La daga marca un máximo en el borde (16 semanas), donde el verdadero máximo puede estar más allá del rango explorado.

| país | R² casos | temp. media | lluvia (mm) | lluvia (horas) | humedad | pto. de rocío |
|---|---|---|---|---|---|---|
| Barbados | 0,07 | 16† (+0,75) | 12 (+0,77) | 11 (+0,88) | 12 (+0,89) | 13 (+0,79) |
| Bermudas | 0,06 | sin dato | 12 (+0,54) | 10 (+0,02) | sin dato | sin dato |
| Bolivia | 0,38 | 15 (+0,83) | 10 (+0,99) | 8 (+0,99) | 4 (+0,91) | 8 (+0,95) |
| Brasil | 0,56 | 16† (−0,09) | 13 (+0,98) | 12 (+0,98) | 10 (+0,91) | 11 (+0,86) |
| Colombia | 0,02 | 14 (+0,84) | 5 (−0,13) | 3 (−0,15) | 3 (−0,01) | 3 (−0,02) |
| Costa Rica | 0,35 | 10 (+0,93) | 6 (+0,84) | 6 (+0,93) | 5 (+0,95) | 7 (+0,95) |
| Ecuador | 0,32 | 16† (+0,80) | 12 (+0,88) | 12 (+0,93) | 9 (+0,86) | 13 (+0,91) |
| El Salvador | 0,17 | 15 (+0,79) | 2 (+0,89) | 3 (+0,87) | 0 (+0,92) | 2 (+0,94) |
| Estados Unidos | 0,19 | 12 (+0,93) | 12 (+0,94) | 11 (+0,93) | 6 (+0,78) | 10 (+0,96) |
| Guatemala | 0,26 | 10 (+0,89) | 1 (+0,80) | 0 (+0,88) | 0 (+0,62) | 6 (+0,95) |
| Honduras | 0,12 | 11 (+0,95) | 4 (+0,81) | 3 (+0,91) | 0 (+0,75) | 3 (+0,96) |
| Islas Vírgenes (EE. UU.) | 0,02 | sin dato | 13 (+0,41) | 13 (+0,29) | sin dato | sin dato |
| Jamaica | 0,07 | 15 (+0,94) | 12 (+0,72) | 10 (+0,60) | 2 (+0,66) | 10 (+0,95) |
| México | 0,59 | 13 (+0,87) | 7 (+0,92) | 6 (+0,92) | 1 (+0,90) | 5 (+0,95) |
| Nicaragua | 0,23 | 14 (+0,80) | 6 (+0,92) | 6 (+0,91) | 2 (+0,92) | 6 (+0,97) |
| Panamá | 0,33 | 16† (+0,86) | 8 (+0,96) | 6 (+0,95) | 7 (+0,98) | 10 (+0,95) |
| Puerto Rico | 0,02 | 16† (+0,95) | 12 (+0,76) | 15 (+0,65) | 8 (+0,89) | 13 (+0,95) |
| República Dominicana | 0,13 | 9 (+0,94) | 10 (+0,62) | 15 (+0,74) | 0 (+0,84) | 7 (+0,94) |

R² de 3 armónicos de cada variable climática en cada país:

| país | temp. media | temp. máx. | temp. mín. | lluvia (mm) | lluvia (horas) | humedad | pto. de rocío |
|---|---|---|---|---|---|---|---|
| Barbados | 0,81 | 0,81 | 0,75 | 0,27 | 0,28 | 0,46 | 0,81 |
| Bermudas | sin dato | sin dato | sin dato | 0,03 | 0,09 | sin dato | sin dato |
| Bolivia | 0,50 | 0,43 | 0,57 | 0,36 | 0,52 | 0,53 | 0,56 |
| Brasil | 0,59 | 0,63 | 0,65 | 0,48 | 0,61 | 0,84 | 0,85 |
| Colombia | 0,36 | 0,38 | 0,25 | 0,40 | 0,44 | 0,59 | 0,61 |
| Costa Rica | 0,70 | 0,42 | 0,77 | 0,34 | 0,43 | 0,66 | 0,79 |
| Ecuador | 0,62 | 0,49 | 0,72 | 0,24 | 0,40 | 0,59 | 0,73 |
| El Salvador | 0,52 | 0,60 | 0,65 | 0,48 | 0,62 | 0,80 | 0,82 |
| Estados Unidos | 0,80 | 0,76 | 0,81 | 0,26 | 0,36 | 0,42 | 0,75 |
| Guatemala | 0,73 | 0,66 | 0,77 | 0,21 | 0,35 | 0,46 | 0,71 |
| Honduras | 0,63 | 0,56 | 0,68 | 0,26 | 0,34 | 0,51 | 0,71 |
| Islas Vírgenes (EE. UU.) | sin dato | sin dato | sin dato | 0,19 | 0,15 | sin dato | sin dato |
| Jamaica | 0,75 | 0,57 | 0,85 | 0,19 | 0,18 | 0,42 | 0,78 |
| México | 0,80 | 0,65 | 0,87 | 0,19 | 0,22 | 0,53 | 0,73 |
| Nicaragua | 0,67 | 0,66 | 0,64 | 0,31 | 0,29 | 0,66 | 0,74 |
| Panamá | 0,38 | 0,47 | 0,32 | 0,50 | 0,17 | 0,79 | 0,76 |
| Puerto Rico | 0,83 | 0,66 | 0,87 | 0,22 | 0,18 | 0,46 | 0,84 |
| República Dominicana | 0,82 | 0,70 | 0,81 | 0,10 | 0,03 | 0,21 | 0,81 |

Lectura:

- Para la lluvia en mm el desfase de mayor correlación es de 1 semana en Guatemala, 2 en El Salvador, 4 en Honduras, 5 en Colombia, 6 en Costa Rica y Nicaragua, 7 en México, 8 en Panamá, 10 en Bolivia y República Dominicana, 12 en Barbados, Bermudas, Ecuador, Jamaica, Puerto Rico y Estados Unidos, y 13 en Brasil e Islas Vírgenes. En Colombia la correlación en ese desfase es negativa (−0,13), por lo que no hay un máximo positivo.
- En lluvia en mm, El Salvador (2) y Guatemala (1) son los únicos países con un desfase de 2 semanas o menos.
- El R² estacional de los casos de El Salvador (0,17) es bajo, y el desfase se mide sobre un ciclo débil. Las correlaciones entre dos ciclos suaves de 52 puntos tienden a ser altas aunque la asociación sea débil (0,6 a 0,99 en la mayoría de las celdas) y no se acompañan de una prueba de significación.

### P5. Corridas anteriores del clasificador

Lectura de los resultados guardados del experimento del 2026-08-16 (`experimento_multipais.py`), sin recalcular. Las corridas B y C evalúan los 16 países con clima completo juntos, sin separar el resultado de El Salvador, por lo que los soportes de la clase alto son regionales. La corrida A entrena con los otros países y prueba solo en El Salvador. El archivo guardado de la corrida A contiene la semilla 42 por año; el documento histórico informa las 11 semillas, sin ninguna que supere a la climatología (0 de 55).

Corrida A (solo El Salvador, entrenando con los otros paises): años con mayoría de semillas que supera 0 de 5 

| año | casos altos | F1 modelo | recall alto modelo | F1 climatología | recall alto climatología | semillas que superan | semillas |
|---|---|---|---|---|---|---|---|
| 2014 | 38 | 0,027 | 0,00 | 0,027 | 0,00 | 0 | 1 |
| 2015 | 29 | 0,107 | 0,00 | 0,107 | 0,00 | 0 | 1 |
| 2016 | 5 | 0,294 | 0,00 | 0,294 | 0,00 | 0 | 1 |
| 2019 | 1 | 0,222 | 0,00 | 0,222 | 0,00 | 0 | 1 |
| 2022 | 11 | 0,268 | 0,00 | 0,268 | 0,00 | 0 | 1 |

Corrida B (regional): años con mayoría de semillas que supera 6 de 11 

| año | casos altos | F1 modelo | recall alto modelo | F1 climatología | recall alto climatología | semillas que superan | semillas |
|---|---|---|---|---|---|---|---|
| 2014 | 121 | 0,280 | 0,00 | 0,280 | 0,00 | 0 | 11 |
| 2015 | 104 | 0,278 | 0,00 | 0,276 | 0,00 | 0 | 11 |
| 2016 | 109 | 0,280 | 0,01 | 0,273 | 0,00 | 11 | 11 |
| 2017 | 4 | 0,386 | 0,25 | 0,326 | 0,00 | 11 | 11 |
| 2018 | 2 | 0,328 | 0,00 | 0,328 | 0,00 | 0 | 11 |
| 2019 | 140 | 0,247 | 0,01 | 0,246 | 0,00 | 9 | 11 |
| 2020 | 52 | 0,295 | 0,00 | 0,297 | 0,00 | 0 | 11 |
| 2021 | 2 | 0,324 | 0,00 | 0,325 | 0,00 | 0 | 11 |
| 2022 | 28 | 0,337 | 0,09 | 0,302 | 0,00 | 11 | 11 |
| 2023 | 240 | 0,273 | 0,06 | 0,227 | 0,00 | 11 | 11 |
| 2024 | 528 | 0,147 | 0,02 | 0,133 | 0,00 | 11 | 11 |

Corrida C (regional con ONI): años con mayoría de semillas que supera 8 de 11 

| año | casos altos | F1 modelo | recall alto modelo | F1 climatología | recall alto climatología | semillas que superan | semillas |
|---|---|---|---|---|---|---|---|
| 2014 | 121 | 0,283 | 0,00 | 0,280 | 0,00 | 0 | 11 |
| 2015 | 104 | 0,299 | 0,20 | 0,276 | 0,00 | 11 | 11 |
| 2016 | 109 | 0,320 | 0,11 | 0,273 | 0,00 | 11 | 11 |
| 2017 | 4 | 0,361 | 0,25 | 0,326 | 0,00 | 11 | 11 |
| 2018 | 2 | 0,366 | 0,91 | 0,328 | 0,00 | 11 | 11 |
| 2019 | 140 | 0,260 | 0,02 | 0,246 | 0,00 | 11 | 11 |
| 2020 | 52 | 0,339 | 0,04 | 0,297 | 0,00 | 11 | 11 |
| 2021 | 2 | 0,324 | 0,00 | 0,325 | 0,00 | 0 | 11 |
| 2022 | 28 | 0,302 | 0,00 | 0,302 | 0,00 | 0 | 11 |
| 2023 | 240 | 0,305 | 0,17 | 0,227 | 0,00 | 11 | 11 |
| 2024 | 528 | 0,201 | 0,09 | 0,133 | 0,00 | 11 | 11 |

Corrida A: ningún año supera a la climatología. Corrida B: 6 de 11 años con mayoría de semillas que supera. Corrida C (con ONI): 8 de 11. El recall de la clase alto del modelo es de 0,00 a 0,25 en casi todos los años con soporte real. La excepción es 2018 en la corrida C (0,91) con un soporte de 2 semanas.

### P6. Posición de El Salvador

| medida | valor de El Salvador | posición de menor a mayor | países |
|---|---|---|---|
| correlación con la señal regional | +0,280 | 1 | 18 |
| correlación con los otros 17 | +0,204 | 1 | 18 |
| desviación del log1p del total anual | 0,859 | 8 | 18 |
| R² estacional de los casos | 0,172 | 9 | 18 |
| r agrupado de la lluvia (mm) | −0,158 | 1 | 16 |
| r agrupado del ONI | −0,086 | 1 | 16 |

El Salvador está en la posición 1 en cuatro medidas (correlación con la señal regional, correlación con los otros 17, lluvia en mm y ONI) y en posiciones intermedias en la desviación entre años (8 de 18) y en el R² estacional de los casos (9 de 18).

## Qué se concluye

- La cifra histórica se reproduce con los datos y la definición de entonces. La definición de anomalía se fijó después de probar cuatro, y solo una reproduce las cifras, de modo que la replicación no es independiente de esa elección.
- La correlación de El Salvador con la señal regional es la menor de 18 con 11 años (+0,280, intervalo de −0,16 a +0,80) y la quinta menor con 9 años (+0,465). Con el criterio del protocolo, el sitio presenta las dos posiciones y el intervalo.
- En el subconjunto centroamericano El Salvador es el de menor correlación en las dos versiones (+0,118 y +0,191).
- La correlación de El Salvador cambia con los años incluidos: sin 2024 sube a +0,464, sin 2023 a +0,390 y sin 2017 baja a +0,165.
- En los datos de P3, El Salvador es el único de 16 países con asociación negativa entre la lluvia en mm y el crecimiento con el intervalo fuera del cero, y tiene el signo contrario a Colombia y Panamá. La etiqueta consistente de la lluvia en mm de El Salvador depende de la construcción de la serie.
- La amplitud entre años y la estacionalidad de los casos de El Salvador están en posiciones intermedias de los 18 países.
- Las diferencias entre países se describen y no se atribuyen a una causa. Serotipos circulantes, inmunidad poblacional, control vectorial, definición de caso y notificación no están medidos en estos datos.

## Qué habilita

- Las tablas P2, P3 y P4 se pueden mostrar en el sitio como descripción de estos datos, con los intervalos, las dos posiciones de P2 y la advertencia de que la correlación con la señal depende de los años que se incluyan.
- La salida guarda las series semanales de casos y clima de los 18 países y la climatología de 52 semanas, que sirven de entrada a cualquier análisis posterior sin repetir la descarga.
- Los datos que reducirían los límites de este análisis son clima con varios puntos por país (idealmente ponderado por población), series por fecha de inicio de síntomas con definiciones de caso comparables entre países, serotipos circulantes por país y año, y años anteriores a 2014.

## Límites añadidos tras ver los resultados

- Bermudas tiene de 0 a 3 casos por año e Islas Vírgenes (EE. UU.) de 0 a 19, salvo 185 en 2024, así que su correlación con la señal refleja muy pocos casos. Las medidas de P2 sin ellas están en la sensibilidad `sin_baja_incidencia`.
- Brasil, México, Estados Unidos, Colombia y Bolivia son países extensos y un punto de clima no representa su territorio. Los resultados de P3 y P4 de esos países pesan menos que los de países pequeños.
- En P3, 21 de 128 celdas tienen el intervalo fuera del cero y 4 cumplen la regla de consistencia. Con tantas celdas y 6 a 9 años por país, cada celda individual tiene poca evidencia.
- Jamaica y Puerto Rico tienen 7 y 6 años evaluables, y Barbados 8, por la regla de 100 casos anuales.
- Las correlaciones de P4 comparan dos ciclos medios de 52 puntos. No miden la asociación entre el clima y los casos de un año, y un máximo en el borde de 16 semanas no se debe leer como un desfase.
- En la corrida A de P5 el archivo guardado tiene una semilla por año.
- La serie de El Salvador de 2024 es un promedio de varias semanas hecho en origen, y el año 2024 es el de mayor influencia en la correlación de P2 (sin él sube a +0,464).
