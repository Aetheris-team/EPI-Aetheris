# Análisis exploratorio: clima y dengue año por año (2026-10-03)

> Protocolo escrito el 2026-10-03, en la rama `feat/clima-dengue-por-anio`, antes de escribir o
> correr ningún script. Continúa `experimento-nowcast-insumos.md` (ablación del clima). No toca la
> prueba prospectiva congelada (`experimento-nowcast-tendencia.md`, script
> `40b6ebb78fe670222966a225438155b83ada876d`), las candidatas K1 a K4, el predictor, el backend ni los
> artefactos de `backend/api/datos/`. Ninguna decisión de modelado depende de este análisis.

## Pregunta

La ablación del clima encontró que quitar el clima de M0 ayuda en unos años y perjudica en otros, sin
un efecto sostenido. Eduardo pidió convertir eso en algo que se pueda ver en el sitio: cómo se
relaciona el clima con el dengue en esta serie, año por año, y qué parte de esa relación es solo el
ciclo estacional compartido. Este análisis produce los números de ese material. La base solo tiene
El Salvador, de modo que el análisis describe esa serie y no puede dar causas ni comparar con otros
países.

## Estado de la información

- Quien escribe este protocolo ya vio, del experimento de insumos, el skill por año de las variantes
  I0 a I5 (cifras del `insumos.json`). Por eso A1 es una lectura de resultados ya conocidos, no una
  prueba.
- No ha visto ninguna correlación entre clima y casos, por año ni agrupada, ni el perfil anual de A4.
  A2 a A5 son cálculos nuevos.
- No se mira ninguna semana objetivo de 2026-S38 en adelante. No se carga ninguna captura.

## Datos

- Casos: OpenDengue nacional, clasificación `total` (sospechosos), semanal. Años de análisis: 2014 a
  2019 y 2021 a 2023 (9 años). 2020 se excluye por la pandemia, como en el resto de los experimentos.
  2024 se excluye de A2 a A5: su serie es ya un promedio de varias semanas hecho en origen (ver
  `analisis-forma-serie-tablero.md`) y desplaza el momento de los máximos, lo que contamina cualquier
  correlación con rezagos. Lo mismo vale para el tablero de 2025 y 2026.
- Las semanas con valor 0 en las vacaciones son casos no notificados que pasan a la semana siguiente.
  Se tratan como faltantes. El promedio de 4 semanas de abajo se calcula con las semanas con dato.
- Clima: las siete variables de `variables_ambientales` (`temp_media`, `temp_max`, `temp_min`,
  `precipitation_sum`, `precipitation_hours`, `humedad_relativa_media`, `punto_rocio`) como media simple
  de los 14 departamentos, y `oni_anom`, igual que `cargar_serie` del experimento de insumos. Es un
  reanálisis (Open-Meteo), no estaciones.

## Definiciones

- z(t): log1p del promedio de las 4 semanas que terminan en t (las que tienen dato). NaN si no hay
  ninguna.
- g(t) = z(t + 4) − z(t): crecimiento a 4 semanas. Se usa el origen t y el horizonte 4 porque son los de
  los rasgos de M0 (medias de 4 semanas) y los de la ablación.
- Semana del año: 1 a 52; la 53 se pliega a la 52.
- Climatología de una serie en un año Y: media de la misma semana del año en los otros 8 años de
  análisis, suavizada con una media móvil circular centrada de 5 semanas. No usa el año Y.
- Anomalía: valor menos la climatología del mismo año. Para el clima, la media de las 4 semanas que
  terminan en t (t − 3 a t, pudiendo caer en el año anterior) menos su climatología. Para g, g(t) menos
  la climatología de g. El ONI ya es una anomalía: se usa su valor en t, sin climatología.
- Un par (t, g) entra si t y t + 4 están en el año Y y ambos extremos tienen dato.

## Análisis (lista cerrada)

### A1. Aporte del clima al pronóstico por año (lectura, sin recalcular)

Del `insumos.json`, fase de validación, referencia persistencia limpia: el aporte del clima es
skill(I0) − skill(I2) y el del ONI es skill(I0) − skill(I1), por año de 2019, 2021, 2022, 2023 y 2024,
en h = 4 y h = 8. Positivo significa que el rasgo ayuda. Se reportan también los otros horizontes, y
las variantes I3 e I4 como contexto.

### A2. Cuánto del ciclo es estacional (descriptiva)

Para cada variable climática y para z: fracción de la varianza semanal explicada por 3 armónicos
anuales (R² de una regresión con intercepto, sen y cos de 1, 2 y 3 ciclos por año), sobre los 9 años.
Para cada variable, correlación entre su climatología (52 valores, sobre los 9 años) y la climatología
de z desplazada 0 a 16 semanas hacia adelante; se reporta el desplazamiento con la mayor correlación y
su valor.

### A3. Asociación entre la anomalía climática y el crecimiento, por año

Para cada año Y, cada una de las 8 variables (7 climáticas y ONI): correlación de Pearson entre la
anomalía climática en t y la anomalía de g(t). Intervalo del 95 % por bootstrap de bloques móviles
(longitud 8 semanas, 2000 remuestreos, semilla 20261003) sobre los pares del año. Son 72 estimaciones
y se reportan todas. No se usa ningún valor p ni se elige una variable por su resultado.

Agrupado: la misma correlación sobre los pares de los 9 años juntos, con el bootstrap de bloques hecho
dentro de cada año (cada año conserva su número de pares). Es un resumen, no un contraste.

### A4. Perfil de cada año (descriptiva)

Por año: casos totales, semana y valor del máximo de z, media anual de cada variable climática y su
anomalía respecto de la climatología de los otros 8 años, ONI medio. Además, correlación de rangos de
Spearman entre los casos totales del año y cada anomalía media anual, con n = 9. Con n = 9 la
correlación es un dato descriptivo; no se reporta su significación y el texto no la usa como prueba.

### A5. Consistencia entre años

Derivada de A3, sin cálculo nuevo. Para cada variable: años con r > 0, años con r < 0, años cuyo
intervalo excluye 0 y el rango de r. Una variable se llama consistente si tiene el mismo signo en al
menos 8 de los 9 años y el intervalo agrupado excluye 0. Cualquier otra se llama variable según el año.
La regla queda fijada aquí para que la etiqueta no dependa de lo que se vea.

## Qué se puede decir con cada resultado

- Si ninguna variable es consistente, el material dice que en esta serie la asociación del clima con
  el crecimiento a 4 semanas cambia de signo o de tamaño entre años, y muestra los 9 años. No da una
  causa.
- Si alguna variable es consistente, el material la nombra, con su tamaño y su intervalo, y dice que es
  una asociación lineal de esta serie que el modelo no convirtió en una ganancia sostenida (A1).
- A2 se presenta como contexto: qué parte del clima y de los casos es estación. Una variable casi toda
  estacional repite lo que ya aportan los armónicos del modelo.
- Ninguna frase del material afirma por qué El Salvador difiere de otros lugares, ni que difiera. Las
  explicaciones posibles (serotipos, inmunidad poblacional, control vectorial, notificación) no se
  observan en la base y se nombran, si se nombran, como no medidas.
- Cada panel del material usa solo cifras del archivo de salida de este análisis y de `insumos.json`.

## Límites

- Nueve años y un solo país. Los intervalos de A3 suponen que los bloques de 8 semanas capturan la
  dependencia temporal; con 45 pares por año es una aproximación.
- La correlación es lineal y mide una variable a la vez. No detecta interacciones, umbrales ni rezagos
  distintos de la ventana de 4 semanas.
- El clima es la media de 14 departamentos de un reanálisis; los casos son el total nacional de
  sospechosos con demoras de notificación y artefactos de vacaciones.
- El resultado depende de que se haya excluido 2020 y 2024 en adelante; no se prueba otra exclusión.

## Reproducibilidad

- Script `backend/ingestion/analisis_clima_por_anio.py`, con pruebas en
  `backend/ingestion/tests/test_clima_por_anio.py`, que se escriben y se confirman en un commit
  anterior a la primera corrida. Lee Postgres; no consulta ningún sitio externo.
- Salida: `docs/agentes/mejora-predictor/resultados-nuevos/clima_por_anio.json`. Los resultados y su
  lectura se añaden a este documento en una sección posterior, sin modificar lo de arriba; un cambio
  al protocolo después de ver resultados se anota como enmienda con fecha y motivo.

## Resultados (2026-10-03)

Una sola corrida del script del commit `e3410f3`, sin cambios posteriores al protocolo. Salida en
`docs/agentes/mejora-predictor/resultados-nuevos/clima_por_anio.json`. Cada año tiene 48 o 49 pares
(433 en total). El asterisco marca un intervalo del 95 % que no contiene el cero. El archivo incluye
además las series semanales de cada año (casos de 4 semanas, clima y anomalías), como entrada para
dibujar; no es un análisis.

### A3. Correlación entre la anomalía climática y la anomalía del crecimiento a 4 semanas

| año | pares | temp. media | temp. máx. | temp. mín. | lluvia (mm) | lluvia (horas) | humedad | pto. de rocío | ONI |
|---|---|---|---|---|---|---|---|---|---|
| 2014 | 49 | +0,61 | +0,53 | +0,67* | −0,29 | −0,37 | −0,34 | +0,08 | −0,54 |
| 2015 | 48 | +0,10 | +0,18 | −0,17 | −0,26 | −0,30 | −0,22 | −0,22 | −0,10 |
| 2016 | 48 | +0,10 | +0,25 | +0,00 | −0,18 | −0,27 | −0,12 | −0,04 | −0,34 |
| 2017 | 48 | +0,07 | +0,06 | +0,03 | −0,17 | −0,05 | +0,04 | +0,14 | −0,45* |
| 2018 | 48 | −0,09 | −0,04 | −0,06 | −0,02 | −0,11 | −0,05 | −0,06 | +0,28 |
| 2019 | 48 | −0,07 | −0,09 | −0,00 | −0,12 | −0,11 | +0,12 | +0,16 | +0,09 |
| 2021 | 48 | +0,24 | +0,29 | +0,08 | −0,41 | −0,37 | −0,27 | −0,16 | −0,66* |
| 2022 | 48 | +0,64* | +0,59* | +0,69* | −0,34 | −0,57* | −0,75* | −0,04 | +0,26 |
| 2023 | 48 | −0,03 | −0,12 | +0,14 | +0,14 | +0,37 | +0,22 | +0,26 | +0,29 |
| agrupado | 433 | +0,18* | +0,19* | +0,14* | −0,17* | −0,20* | −0,17* | −0,04 | −0,04 |

### A5. Consistencia entre años

| variable | años con r > 0 | años con r < 0 | años con intervalo sin el cero | rango de r | r agrupado [intervalo 95 %] | etiqueta |
|---|---|---|---|---|---|---|
| temp. media | 6 | 3 | 1 | −0,09 a +0,64 | +0,18 [+0,06; +0,36] | variable según el año |
| temp. máx. | 6 | 3 | 1 | −0,12 a +0,59 | +0,19 [+0,07; +0,36] | variable según el año |
| temp. mín. | 6 | 3 | 2 | −0,17 a +0,69 | +0,14 [+0,02; +0,35] | variable según el año |
| lluvia (mm) | 1 | 8 | 0 | −0,41 a +0,14 | −0,17 [−0,34; −0,06] | consistente |
| lluvia (horas) | 1 | 8 | 1 | −0,57 a +0,37 | −0,20 [−0,37; −0,09] | consistente |
| humedad | 3 | 6 | 1 | −0,75 a +0,22 | −0,17 [−0,33; −0,04] | variable según el año |
| pto. de rocío | 4 | 5 | 0 | −0,22 a +0,26 | −0,04 [−0,19; +0,15] | variable según el año |
| ONI | 4 | 5 | 2 | −0,66 a +0,29 | −0,04 [−0,13; +0,22] | variable según el año |

Con la regla fijada de antemano, dos variables son consistentes: la lluvia semanal y las horas de
lluvia, ambas con signo negativo en 8 de 9 años y con intervalo agrupado que excluye el cero. Las demás
variables se etiquetan variable según el año.

### A2. Parte estacional y desfase entre ciclos

| serie | R² de 3 armónicos | desfase con mayor correlación (semanas) | correlación en ese desfase |
|---|---|---|---|
| casos (z) | 0,16 | | |
| temp. media | 0,53 | 15 | 0,81 |
| temp. máx. | 0,59 | 16 | 0,65 |
| temp. mín. | 0,67 | 8 | 0,88 |
| lluvia (mm) | 0,53 | 2 | 0,89 |
| lluvia (horas) | 0,64 | 2 | 0,87 |
| humedad | 0,79 | 0 | 0,92 |
| pto. de rocío | 0,82 | 2 | 0,94 |

El desfase compara la climatología de cada variable con la de z desplazada hacia adelante entre 0 y 16
semanas. Para la temperatura máxima el máximo está en el borde del rango (16). z es un promedio de 4
semanas y arrastra por construcción un rezago de unas 1,5 semanas respecto de los casos semanales.

### A4. Perfil de cada año

| año | casos | semana del pico | valor del pico (promedio de 4 semanas) | ONI medio | anomalía de lluvia (mm por semana) | anomalía de temp. media (°C) |
|---|---|---|---|---|---|---|
| 2014 | 53.460 | 36 | 2827 | +0,22 | −2,7 | −0,16 |
| 2015 | 50.169 | 36 | 2204 | +1,48 | −3,9 | +0,56 |
| 2016 | 8.789 | 1 | 418 | +0,50 | −5,1 | +0,17 |
| 2017 | 4.297 | 25 | 138 | −0,06 | +3,6 | −0,37 |
| 2018 | 8.448 | 39 | 343 | +0,12 | −0,7 | −0,10 |
| 2019 | 27.470 | 35 | 1443 | +0,65 | −0,9 | +0,32 |
| 2021 | 5.752 | 26 | 157 | −0,65 | +0,2 | −0,22 |
| 2022 | 16.542 | 24 | 606 | −0,78 | +11,8 | −0,69 |
| 2023 | 5.788 | 31 | 204 | +0,80 | −2,3 | +0,50 |

Correlación de rangos de Spearman entre los casos totales y la anomalía media anual, con n = 9:
temp. media +0,33; temp. máx. +0,33; temp. mín. +0,15; lluvia (mm) −0,50; lluvia (horas) −0,67; humedad −0,52; pto. de rocío −0,02; ONI +0,40. Es un dato descriptivo con nueve puntos. La semana del pico de 2016 (la 1) es
probablemente la cola de la epidemia de 2015 y no un máximo del propio año.

### A1. Aporte al pronóstico por año (lectura de `insumos.json`)

Positivo significa que quitar el rasgo empeora el skill del predictor, es decir que el rasgo ayuda.

| horizonte | rasgo | 2019 | 2021 | 2022 | 2023 | 2024 | años a favor |
|---|---|---|---|---|---|---|---|
| h = 4 | clima | −0,040 | +0,075 | +0,314 | −0,029 | −0,227 | 2 de 5 |
| h = 4 | ONI | −0,027 | +0,021 | +0,004 | −0,018 | −0,012 | 2 de 5 |
| h = 4 | año del objetivo | +0,013 | +0,071 | +0,032 | +0,007 | −0,034 | 4 de 5 |
| h = 8 | clima | −0,022 | +0,085 | +0,229 | −0,002 | −0,074 | 2 de 5 |
| h = 8 | ONI | −0,010 | −0,040 | −0,061 | −0,012 | −0,033 | 0 de 5 |
| h = 8 | año del objetivo | +0,020 | −0,033 | +0,092 | +0,039 | +0,005 | 4 de 5 |

## Qué se concluye

- La asociación lineal más estable de la serie es negativa con la lluvia: una lluvia mayor que la
  normal en las 4 semanas previas acompaña un crecimiento menor en las 4 siguientes. El tamaño es
  pequeño: la correlación agrupada es de −0,17 (lluvia en mm) y −0,20 (horas de lluvia), alrededor
  del 3 al 4 % de la varianza de la anomalía del crecimiento. Ningún año por separado tiene el
  intervalo de la lluvia en mm fuera del cero, y solo 2022 lo tiene en las horas de lluvia, en el
  límite del cero. Las dos
  variables miden lo mismo con dos unidades y cuentan como un solo hallazgo.
- El signo es el contrario al que suele esperarse de la lluvia. La base no mide almacenamiento de
  agua, control vectorial, serotipos ni inmunidad, y este análisis no distingue entre explicaciones.
- La temperatura tiene una correlación agrupada positiva de 0,14 a 0,19 que viene de dos años: 2014
  (0,5 a 0,7) y 2022 (0,6 a 0,7). En los otros siete años la correlación está entre −0,17 y +0,29. La
  regla la etiqueta variable según el año.
- 2022 es el único año en que varias variables climáticas tienen el intervalo fuera del cero a la vez
  (temperatura media, máxima y mínima, humedad y horas de lluvia). Es también el año con la mayor
  anomalía de lluvia de la serie (+11,8 mm por semana, ONI de −0,78) y aquel en que el clima más ayudó al
  predictor (A1: +0,31 a h = 4).
- El ONI cambia de signo según el año (4 positivos y 5 negativos) y su aporte al pronóstico es de
  0,03 o menos en valor absoluto en todos los años a h = 4.
- A2: entre el 53 y el 82 % de la varianza de cada variable climática es ciclo anual; en los casos
  (z) es el 16 %. La mayor parte de la variación de los casos queda entre años y dentro del año fuera
  del ciclo medio. El ciclo medio de los casos
  coincide con el de la lluvia, la humedad y el punto de rocío (correlación de 0,87 a 0,94 con un
  desfase de 0 a 2 semanas); el de la temperatura lo precede de 8 a 16 semanas.
- En A1 el clima ayudó al predictor en 2021 y 2022 y no en 2019, 2023 ni 2024. No hay una ganancia
  sostenida, igual que en el veredicto del experimento de insumos.

## Observación posterior, no prevista en el protocolo

Para los cuatro años que están en A1 y en A3 (2019, 2021, 2022 y 2023), el promedio del valor
absoluto de la correlación de las 7 variables climáticas (0,09; 0,26; 0,52; 0,18) ordena los años
igual que el aporte del clima a h = 4 (−0,040; +0,075; +0,314; −0,029). Con cuatro años, una
coincidencia exacta del orden ocurre una vez de cada 24 por azar. Se registra como descripción de la
serie. No se usa como prueba ni se pone en el sitio como resultado.

Sensibilidad posterior de la correlación agrupada al quitar años, calculada después de ver A3:

| variable | todos los años | sin 2022 | sin 2014 | sin 2014 ni 2022 |
|---|---|---|---|---|
| temp. media | +0,18 | +0,11 | +0,14 | +0,05 |
| temp. máx. | +0,19 | +0,13 | +0,16 | +0,08 |
| temp. mín. | +0,14 | +0,06 | +0,08 | −0,02 |
| lluvia (mm) | −0,17 | −0,13 | −0,17 | −0,12 |
| lluvia (horas) | −0,20 | −0,13 | −0,20 | −0,11 |
| humedad | −0,17 | −0,11 | −0,16 | −0,09 |

La correlación positiva de la temperatura desaparece sin 2014 y 2022. La de la lluvia baja a −0,12 y
−0,11 sin ellos y conserva el signo.

## Qué habilita

- Material para el sitio, con cifras solo de este archivo y de `insumos.json`: el aporte del clima al
  pronóstico por año (A1), la matriz año por variable de A3 con los intervalos, el ciclo medio de los
  casos junto al de la lluvia (A2) y el perfil de los años (A4). El texto dice qué asociación es
  consistente y cuáles varían según el año, con los tamaños de arriba, y nombra como no medidos los
  mecanismos posibles.
- Una variante de M0 con el clima expresado como anomalía respecto de la estación necesitaría su
  propio protocolo. Quien lo escriba ya vio A3, de modo que A3 no cuenta como evidencia independiente
  a su favor, y la ventana prospectiva firmada para K1 a K4 no se modifica.
- Este análisis usa solo El Salvador y no permite decir si difiere de otros países. Esa comparación
  existe en el experimento multipaís (`experimento-multipais.md`, hoy en el repo STC; última versión en
  este repo en el commit `ef698c8^`). Con 18 países de las Américas (OpenDengue PAHO, 2014 a 2024),
  la correlación entre la anomalía anual de casos de El Salvador y la señal regional compartida es de
  +0,280, la más baja de los 18 (Colombia +0,952, Guatemala +0,908, Honduras +0,868). Un clasificador
  regional con clima superó a la climatología en 6 de 11 años (8 de 11 con ONI), y el entrenado con
  los otros países no transfirió a El Salvador. Esa medida es sobre casos, usa un solo punto de clima
  por país y es de otra tarea (clasificación del canal endémico). No se reprodujo aquí. Mostrarla en el
  sitio exige recalcularla con un protocolo propio.

## Límites añadidos tras ver los resultados

- El intervalo agrupado remuestrea bloques dentro de cada uno de los 9 años observados. Describe la
  incertidumbre de esos años y no la de un año nuevo. Que 8 de 9 años compartan el signo es la
  evidencia de que otros años lo comparten, y con 9 años es limitada.
- Son 8 variables y 2 salieron consistentes, sin ajuste por comparaciones múltiples. La regla se fijó
  antes de ver los datos; la lluvia en mm y en horas no son independientes entre sí.
- Las primeras semanas de 2014 usan ventanas parciales porque la serie empieza en 2014-S1.
- Para evaluar un año, la climatología excluye ese año. Al evaluar los demás años entra 2022, que
  tiene una anomalía de lluvia muy alta, y eso sube algo la referencia y baja sus anomalías.
