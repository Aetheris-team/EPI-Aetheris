---
titulo: "Clima y dengue"
descripcion: "Qué se midió entre el clima y los casos de dengue en El Salvador y en otros 17 países de las Américas, con sus intervalos, y qué datos harían falta para avanzar."
orden: 7
categoria: "Datos y método"
---

La relación entre el clima y los casos de dengue en El Salvador se midió con series públicas de 2014 a 2024: casos de OpenDengue y clima reanalizado de Open-Meteo. El aporte del clima al pronóstico cambia de un año a otro. La lluvia es la única variable con el mismo signo en 8 de 9 años, y su tamaño es pequeño. La evolución anual de los casos en El Salvador es de las que menos coinciden con la de la región. Las gráficas interactivas y las tablas de cada gráfica están en [Clima y dengue](/analisis/clima).

## Qué se midió

Casos. Para El Salvador por año, la serie nacional semanal de OpenDengue con la clasificación total, que corresponde a los casos sospechosos. Para la comparación entre países, la serie semanal de la OPS en OpenDengue, que incluye los 18 países, El Salvador entre ellos. Los totales anuales de las dos series de El Salvador difieren poco (en 2019, 27.470 y 27.490).

Clima. Siete variables diarias de Open-Meteo (temperatura media, máxima y mínima, lluvia en milímetros, horas de lluvia, humedad relativa y punto de rocío), agregadas por semana con la suma para las dos de lluvia y la media para las demás, y el índice ONI, que mide la anomalía de la temperatura del Pacífico ecuatorial ligada a El Niño y La Niña. Open-Meteo es un reanálisis, sin mediciones de estaciones locales. Para El Salvador por año, el clima es la media de los 14 departamentos. En la comparación entre países hay un punto de clima por país, el centroide.

Años. De 2014 a 2024. Las asociaciones semanales usan 9 años, de 2014 a 2019 y de 2021 a 2023. 2020 queda fuera por la pandemia y 2024 por la forma de su serie en El Salvador, que es un promedio de varias semanas hecho en origen. La comparación anual entre países usa los 11 años y se repite con 9. Por año, las semanas con valor 0 en las vacaciones se tratan como faltantes porque son casos no notificados que pasan a la semana siguiente. En la comparación entre países los ceros cuentan como ceros.

Medidas. El crecimiento a 4 semanas es la diferencia entre el logaritmo (log1p) del promedio de las 4 semanas que terminan 4 semanas después y el del promedio de las 4 semanas que terminan en la semana de origen. La anomalía de una serie es su valor menos el ciclo habitual de los demás años, suavizado con una media de 5 semanas, sin usar el año evaluado. La correlación es la de Pearson entre la anomalía climática de las 4 semanas previas y la anomalía del crecimiento. Los intervalos del 95 % salen de un bootstrap de bloques móviles de 8 semanas con 2.000 remuestreos (semilla 20261003).

Regla de consistencia, fijada antes de calcular. Por año, una variable se llama consistente si tiene el mismo signo en al menos 8 de los 9 años y el intervalo del conjunto excluye el cero. En la comparación entre países, si tiene el mismo signo en todos los años evaluables salvo a lo sumo uno y el intervalo del conjunto excluye el cero. Cualquier otra se llama variable según el año.

## Aporte del clima al pronóstico por año

La habilidad del predictor es la reducción relativa del error ponderado de intervalos (WIS) frente a la persistencia, que repite el último valor observado. El aporte de un grupo de variables es la habilidad del predictor completo menos la habilidad del mismo predictor sin ese grupo, año por año. Un valor positivo indica que el grupo mejoró el pronóstico ese año. El año del objetivo es el año calendario de la semana pronosticada. La tabla es una lectura de la ablación del predictor, hecha antes de calcular las correlaciones de las secciones siguientes.

| Horizonte | Grupo de variables | 2019 | 2021 | 2022 | 2023 | 2024 | Años a favor |
|---|---|---|---|---|---|---|---|
| 4 semanas | Predictor completo (habilidad) | +0,064 | +0,044 | −0,152 | +0,258 | +0,030 |  |
| 4 semanas | Clima de superficie | −0,040 | +0,075 | +0,314 | −0,029 | −0,227 | 2 de 5 |
| 4 semanas | ONI | −0,027 | +0,021 | +0,004 | −0,018 | −0,012 | 2 de 5 |
| 4 semanas | Clima y ONI | −0,062 | +0,098 | +0,334 | −0,053 | −0,221 | 2 de 5 |
| 4 semanas | Año del objetivo | +0,013 | +0,071 | +0,032 | +0,007 | −0,034 | 4 de 5 |
| 8 semanas | Predictor completo (habilidad) | +0,217 | +0,090 | −0,023 | +0,149 | +0,466 |  |
| 8 semanas | Clima de superficie | −0,022 | +0,085 | +0,229 | −0,002 | −0,074 | 2 de 5 |
| 8 semanas | ONI | −0,010 | −0,040 | −0,061 | −0,012 | −0,033 | 0 de 5 |
| 8 semanas | Clima y ONI | −0,052 | +0,129 | +0,320 | −0,046 | −0,084 | 2 de 5 |
| 8 semanas | Año del objetivo | +0,020 | −0,033 | +0,092 | +0,039 | +0,005 | 4 de 5 |

A 4 semanas, el clima de superficie mejoró el pronóstico en 2021 y 2022 y lo empeoró en 2019, 2023 y 2024. El ONI aportó entre −0,027 y +0,021. A 8 semanas el ONI no mejoró el pronóstico en ninguno de los cinco años. No hay una ganancia sostenida del clima en ninguno de los dos horizontes.

## Clima y crecimiento de los casos en El Salvador

Correlación entre la anomalía climática y la anomalía del crecimiento de los casos a 4 semanas, con 433 pares semanales en los 9 años.

| Variable | Correlación en el conjunto | Años positivos | Años negativos | Años con intervalo sin el cero | Rango por año | Etiqueta |
|---|---|---|---|---|---|---|
| Temp. media | +0,18 [+0,06; +0,36] | 6 | 3 | 1 | −0,09 a +0,64 | variable según el año |
| Temp. máxima | +0,19 [+0,07; +0,36] | 6 | 3 | 1 | −0,12 a +0,59 | variable según el año |
| Temp. mínima | +0,14 [+0,02; +0,35] | 6 | 3 | 2 | −0,17 a +0,69 | variable según el año |
| Lluvia (mm) | −0,17 [−0,34; −0,06] | 1 | 8 | 0 | −0,41 a +0,14 | consistente |
| Lluvia (horas) | −0,20 [−0,37; −0,09] | 1 | 8 | 1 | −0,57 a +0,37 | consistente |
| Humedad | −0,17 [−0,33; −0,04] | 3 | 6 | 1 | −0,75 a +0,22 | variable según el año |
| Punto de rocío | −0,04 [−0,19; +0,15] | 4 | 5 | 0 | −0,22 a +0,26 | variable según el año |
| ONI | −0,04 [−0,13; +0,22] | 4 | 5 | 2 | −0,66 a +0,29 | variable según el año |

Dos variables cumplen la regla de consistencia: la lluvia en milímetros y las horas de lluvia, ambas con signo negativo. Una lluvia mayor que la normal en las 4 semanas previas acompaña un crecimiento menor en las 4 siguientes. El tamaño es pequeño: −0,17 y −0,20 equivalen a entre el 3 % y el 4 % de la varianza de la anomalía del crecimiento. Las dos variables describen la lluvia de dos maneras y no son resultados independientes. De las 8 variables, 2 salieron consistentes, sin ajuste por comparaciones múltiples.

La correlación del conjunto de las tres temperaturas es positiva, entre +0,14 y +0,19, y viene de dos años: en 2014 y 2022 las tres temperaturas superan +0,5, y en los otros siete años la correlación está entre −0,17 y +0,29. 2022 es el único año en que varias variables tienen el intervalo fuera del cero a la vez (temperatura media, máxima y mínima, humedad y horas de lluvia). Es también el año con la mayor anomalía de lluvia de la serie (+11,8 mm por semana, con un ONI medio de −0,78) y aquel en que el clima más ayudó al predictor (+0,31 a 4 semanas).

Correlación por año. Un asterisco marca un intervalo del 95 % que excluye el cero.

| Año | Pares | Temp. media | Temp. máxima | Temp. mínima | Lluvia (mm) | Lluvia (horas) | Humedad | Punto de rocío | ONI |
|---|---|---|---|---|---|---|---|---|---|
| 2014 | 49 | +0,61 | +0,53 | +0,67* | −0,29 | −0,37 | −0,34 | +0,08 | −0,54 |
| 2015 | 48 | +0,10 | +0,18 | −0,17 | −0,26 | −0,30 | −0,22 | −0,22 | −0,10 |
| 2016 | 48 | +0,10 | +0,25 | +0,00 | −0,18 | −0,27 | −0,12 | −0,04 | −0,34 |
| 2017 | 48 | +0,07 | +0,06 | +0,03 | −0,17 | −0,05 | +0,04 | +0,14 | −0,45* |
| 2018 | 48 | −0,09 | −0,04 | −0,06 | −0,02 | −0,11 | −0,05 | −0,06 | +0,28 |
| 2019 | 48 | −0,07 | −0,09 | +0,00 | −0,12 | −0,11 | +0,12 | +0,16 | +0,09 |
| 2021 | 48 | +0,24 | +0,29 | +0,08 | −0,41 | −0,37 | −0,27 | −0,16 | −0,66* |
| 2022 | 48 | +0,64* | +0,59* | +0,69* | −0,34 | −0,57* | −0,75* | −0,04 | +0,26 |
| 2023 | 48 | −0,03 | −0,12 | +0,14 | +0,14 | +0,37 | +0,22 | +0,26 | +0,29 |
| Todos | 433 | +0,18* | +0,19* | +0,14* | −0,17* | −0,20* | −0,17* | −0,04 | −0,04 |

El ONI cambia de signo según el año (4 positivos y 5 negativos), y su aporte al pronóstico es de 0,03 o menos en valor absoluto en todos los años a 4 semanas.

Sensibilidad del conjunto al quitar años, calculada después de ver la matriz por año. La correlación positiva de la temperatura desaparece sin 2014 y 2022. La de la lluvia baja a −0,12 y −0,11 sin ellos y conserva el signo.

| Variable | Todos los años | Sin 2022 | Sin 2014 | Sin 2014 ni 2022 |
|---|---|---|---|---|
| Temp. media | +0,18 | +0,11 | +0,14 | +0,05 |
| Temp. máxima | +0,19 | +0,13 | +0,16 | +0,08 |
| Temp. mínima | +0,14 | +0,06 | +0,08 | −0,02 |
| Lluvia (mm) | −0,17 | −0,13 | −0,17 | −0,12 |
| Lluvia (horas) | −0,20 | −0,13 | −0,20 | −0,11 |
| Humedad | −0,17 | −0,11 | −0,16 | −0,09 |

Perfil de cada año. La semana del pico de 2016 (la 1) es probablemente la cola de la epidemia de 2015 y no un máximo del propio año.

| Año | Casos del año | Semana del pico | Casos por semana en el pico | ONI medio | Anomalía de lluvia (mm) | Anomalía de horas de lluvia | Anomalía de temp. media (°C) | Anomalía de humedad (%) |
|---|---|---|---|---|---|---|---|---|
| 2014 | 53.460 | 36 | 2.827 | +0,22 | −2,66 | −4,76 | −0,16 | −0,80 |
| 2015 | 50.169 | 36 | 2.204 | +1,48 | −3,87 | −5,63 | +0,56 | −2,03 |
| 2016 | 8.789 | 1 | 418 | +0,50 | −5,14 | −3,72 | +0,17 | +0,18 |
| 2017 | 4.297 | 25 | 138 | −0,06 | +3,64 | +0,76 | −0,37 | +1,25 |
| 2018 | 8.448 | 39 | 343 | +0,12 | −0,69 | −3,92 | −0,10 | −1,37 |
| 2019 | 27.470 | 35 | 1.443 | +0,65 | −0,90 | −3,92 | +0,32 | −0,83 |
| 2021 | 5.752 | 26 | 157 | −0,65 | +0,21 | −2,48 | −0,22 | +0,70 |
| 2022 | 16.542 | 24 | 606 | −0,78 | +11,80 | +17,61 | −0,69 | +3,27 |
| 2023 | 5.788 | 31 | 204 | +0,80 | −2,34 | +6,13 | +0,50 | −0,36 |

Con 9 puntos, la correlación de rangos entre los casos totales del año y la anomalía media anual de cada variable es:

| Medida | Temp. media | Temp. máxima | Temp. mínima | Lluvia (mm) | Lluvia (horas) | Humedad | Punto de rocío | ONI |
|---|---|---|---|---|---|---|---|---|
| Correlación de rangos de Spearman | +0,33 | +0,33 | +0,15 | −0,50 | −0,67 | −0,52 | −0,02 | +0,40 |

Los datos usados no incluyen almacenamiento de agua, control vectorial, serotipos ni inmunidad, y el análisis no distingue entre explicaciones.

## Ciclo anual de los casos y del clima

Entre el 53 % y el 82 % de la varianza de cada variable climática es ciclo anual (tres armónicos). En los casos de El Salvador es el 16 % de la variación semanal del logaritmo del promedio de 4 semanas. La tabla da, para cada variable, el desfase de 0 a 16 semanas con que su ciclo medio se parece más al de los casos. El ciclo medio de los casos coincide con el de la lluvia, la humedad y el punto de rocío con un desfase de 0 a 2 semanas, y el de la temperatura lo precede entre 8 y 16 semanas. El promedio de 4 semanas de los casos arrastra por construcción un rezago de unas 1,5 semanas respecto de los casos semanales.

| Variable | R² del ciclo anual | Desfase (semanas) | Correlación en ese desfase |
|---|---|---|---|
| Temperatura media | 0,53 | 15 | +0,81 |
| Temperatura máxima | 0,59 | 16* | +0,65 |
| Temperatura mínima | 0,67 | 8 | +0,88 |
| Lluvia (mm por semana) | 0,53 | 2 | +0,89 |
| Horas de lluvia por semana | 0,64 | 2 | +0,87 |
| Humedad relativa | 0,79 | 0 | +0,92 |
| Punto de rocío | 0,82 | 2 | +0,94 |

Un asterisco marca un máximo en el borde del rango explorado (16 semanas), que no debe leerse como un desfase. Las correlaciones comparan dos ciclos medios de 52 puntos y no miden la asociación entre el clima y los casos de un año.

El mismo cálculo en cada país, con la serie de la comparación entre países. Entre paréntesis, la correlación en el desfase de mayor correlación. El R² de los casos de El Salvador es 0,17 con esta serie y 0,16 con la del análisis por año.

| País | R² del ciclo de casos | Lluvia (mm) | Lluvia (horas) | Humedad | Temp. media | Punto de rocío |
|---|---|---|---|---|---|---|
| Barbados | 0,07 | 12 (+0,77) | 11 (+0,88) | 12 (+0,89) | 16* (+0,75) | 13 (+0,79) |
| Bermudas | 0,06 | 12 (+0,54) | 10 (+0,02) | sin dato | sin dato | sin dato |
| Bolivia | 0,38 | 10 (+0,99) | 8 (+0,99) | 4 (+0,91) | 15 (+0,83) | 8 (+0,95) |
| Brasil | 0,56 | 13 (+0,98) | 12 (+0,98) | 10 (+0,91) | 16* (−0,09) | 11 (+0,86) |
| Colombia | 0,02 | 5 (−0,13) | 3 (−0,15) | 3 (−0,01) | 14 (+0,84) | 3 (−0,02) |
| Costa Rica | 0,35 | 6 (+0,84) | 6 (+0,93) | 5 (+0,95) | 10 (+0,93) | 7 (+0,95) |
| Ecuador | 0,32 | 12 (+0,88) | 12 (+0,93) | 9 (+0,86) | 16* (+0,80) | 13 (+0,91) |
| El Salvador | 0,17 | 2 (+0,89) | 3 (+0,87) | 0 (+0,92) | 15 (+0,79) | 2 (+0,94) |
| Estados Unidos | 0,19 | 12 (+0,94) | 11 (+0,93) | 6 (+0,78) | 12 (+0,93) | 10 (+0,96) |
| Guatemala | 0,26 | 1 (+0,80) | 0 (+0,88) | 0 (+0,62) | 10 (+0,89) | 6 (+0,95) |
| Honduras | 0,12 | 4 (+0,81) | 3 (+0,91) | 0 (+0,75) | 11 (+0,95) | 3 (+0,96) |
| Islas Vírgenes (EE. UU.) | 0,02 | 13 (+0,41) | 13 (+0,29) | sin dato | sin dato | sin dato |
| Jamaica | 0,07 | 12 (+0,72) | 10 (+0,60) | 2 (+0,66) | 15 (+0,94) | 10 (+0,95) |
| México | 0,59 | 7 (+0,92) | 6 (+0,92) | 1 (+0,90) | 13 (+0,87) | 5 (+0,95) |
| Nicaragua | 0,23 | 6 (+0,92) | 6 (+0,91) | 2 (+0,92) | 14 (+0,80) | 6 (+0,97) |
| Panamá | 0,33 | 8 (+0,96) | 6 (+0,95) | 7 (+0,98) | 16* (+0,86) | 10 (+0,95) |
| Puerto Rico | 0,02 | 12 (+0,76) | 15 (+0,65) | 8 (+0,89) | 16* (+0,95) | 13 (+0,95) |
| República Dominicana | 0,13 | 10 (+0,62) | 15 (+0,74) | 0 (+0,84) | 9 (+0,94) | 7 (+0,94) |

## El Salvador entre 18 países

Cada país tiene una anomalía anual del total de casos (logaritmo de uno más el total, estandarizado dentro del país con los 11 años). La señal regional es la media de las anomalías de los 18 países. Se mide la correlación de cada país con esa señal.

Con los 11 años, El Salvador tiene la menor correlación de los 18: +0,280, con un intervalo del 95 % de −0,16 a +0,80. Con los 9 años de la sensibilidad (sin 2020 y 2024) queda en la posición 5 de 18, con +0,465. Quitar solo 2024 da +0,464, casi igual que la medida de 9 años, y quitar solo 2020 da +0,263. Sin Bermudas ni Islas Vírgenes (EE. UU.), que tienen muy pocos casos, la correlación es +0,283 y la posición 1 de 16. Entre los 6 países de Centroamérica, El Salvador tiene la menor correlación con la media de los otros cinco en las dos medidas.

| País | Con la señal regional (11 años) | Intervalo del 95 % | Posición | Con los otros 17 (11 años) | Con la señal regional (9 años) | Posición (9 años) | Con los otros 17 (9 años) |
|---|---|---|---|---|---|---|---|
| El Salvador | +0,280 | [−0,16; +0,80] | 1 | +0,204 | +0,465 | 5 | +0,394 |
| Barbados | +0,412 | [−0,14; +0,78] | 2 | +0,342 | +0,410 | 4 | +0,336 |
| Nicaragua | +0,512 | [+0,07; +0,84] | 3 | +0,449 | +0,560 | 8 | +0,497 |
| Jamaica | +0,544 | [+0,10; +0,86] | 4 | +0,484 | +0,557 | 7 | +0,494 |
| Estados Unidos | +0,586 | [−0,15; +0,94] | 5 | +0,530 | +0,365 | 2 | +0,287 |
| Panamá | +0,614 | [−0,20; +0,91] | 6 | +0,560 | +0,365 | 3 | +0,288 |
| Islas Vírgenes (EE. UU.) | +0,633 | [−0,02; +0,92] | 7 | +0,581 | +0,316 | 1 | +0,236 |
| Ecuador | +0,651 | [−0,07; +0,91] | 8 | +0,601 | +0,490 | 6 | +0,421 |
| Puerto Rico | +0,657 | [+0,01; +0,90] | 9 | +0,607 | +0,624 | 9 | +0,567 |
| Bolivia | +0,682 | [+0,22; +0,98] | 10 | +0,635 | +0,866 | 15 | +0,842 |
| República Dominicana | +0,768 | [+0,47; +0,95] | 11 | +0,733 | +0,895 | 17 | +0,875 |
| Bermudas | +0,817 | [+0,56; +0,95] | 12 | +0,788 | +0,741 | 10 | +0,699 |
| Brasil | +0,860 | [+0,46; +0,99] | 13 | +0,836 | +0,762 | 11 | +0,723 |
| Honduras | +0,868 | [+0,64; +0,97] | 14 | +0,846 | +0,794 | 12 | +0,759 |
| México | +0,872 | [+0,64; +0,97] | 15 | +0,851 | +0,801 | 13 | +0,766 |
| Costa Rica | +0,898 | [+0,74; +0,97] | 16 | +0,880 | +0,889 | 16 | +0,869 |
| Guatemala | +0,908 | [+0,73; +0,99] | 17 | +0,892 | +0,860 | 14 | +0,835 |
| Colombia | +0,952 | [+0,89; +0,99] | 18 | +0,944 | +0,922 | 18 | +0,907 |

La correlación media entre pares de países es 0,453 con los 11 años y 0,387 con 9. El primer componente explica el 51,8 % de la varianza con 11 años y el 46,9 % con 9. La señal regional tiene una correlación de +0,527 con el ONI anual.

Centroamérica:

| País | Con la media de los otros cinco (11 años) | Con la media de los otros cinco (9 años) |
|---|---|---|
| El Salvador | +0,118 | +0,191 |
| Nicaragua | +0,537 | +0,611 |
| Panamá | +0,554 | +0,338 |
| Costa Rica | +0,655 | +0,596 |
| Honduras | +0,760 | +0,674 |
| Guatemala | +0,923 | +0,905 |

Anomalía anual de El Salvador y señal regional:

| Año | Casos de El Salvador | Anomalía de El Salvador | Señal regional |
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

Correlación de El Salvador con la señal al quitar un año. 2024 es el año de mayor influencia:

| Año quitado | Correlación de El Salvador |
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

Al quitar un país de la señal, la correlación de El Salvador queda entre +0,255 y +0,315:

| País quitado de la señal | Correlación de El Salvador |
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

Posición de El Salvador en seis medidas, de menor a mayor. Está en la posición 1 en cuatro: correlación con la señal regional, correlación con la señal de los otros 17, correlación semanal con la lluvia (mm) y correlación semanal con el ONI. En las otras dos tiene posiciones intermedias: variación entre años del total anual (8 de 18) y parte de la variación semanal que explica el ciclo anual (9 de 18).

| Medida | Valor de El Salvador | Posición de menor a mayor | Países comparados |
|---|---|---|---|
| Correlación con la señal regional | +0,280 | 1 | 18 |
| Correlación con la señal de los otros 17 | +0,204 | 1 | 18 |
| Variación entre años del total anual | 0,859 | 8 | 18 |
| Parte de la variación semanal que explica el ciclo anual | 0,172 | 9 | 18 |
| Correlación semanal con la lluvia (mm) | −0,158 | 1 | 16 |
| Correlación semanal con el ONI | −0,086 | 1 | 16 |

Perfil de cada país:

| País | Casos por semana (media) | Semanas en cero | R² del ciclo anual | Semana del máximo | Variación entre años del total | Marcas | Punto de clima (lat.; long.) |
|---|---|---|---|---|---|---|---|
| Barbados | 15,5 | 15 % | 0,07 | 41 | 1,04 |  | 13,19; −59,54 |
| Bermudas | 0,013 | 99 % | 0,06 | 33 | 0,53 | baja incidencia; solo lluvia | 32,32; −64,76 |
| Bolivia | 658 | 0 % | 0,38 | 14 | 0,93 | país extenso | −16,29; −63,59 |
| Brasil | 30.169 | 0 % | 0,56 | 16 | 0,87 | país extenso | −14,24; −51,93 |
| Colombia | 1.617 | 0 % | 0,02 | 49 | 0,62 | país extenso | 4,57; −74,30 |
| Costa Rica | 242 | 0 % | 0,35 | 34 | 0,74 |  | 9,75; −83,75 |
| Ecuador | 341 | 0 % | 0,32 | 22 | 0,76 |  | −1,83; −78,18 |
| El Salvador | 384 | 2 % | 0,17 | 36 | 0,86 |  | 13,79; −88,90 |
| Estados Unidos | 12,7 | 22 % | 0,19 | 45 | 0,92 | país extenso | 27,99; −81,76 |
| Guatemala | 412 | 0 % | 0,26 | 35 | 1,24 |  | 15,70; −90,36 |
| Honduras | 716 | 0 % | 0,12 | 28 | 0,99 |  | 14,75; −86,24 |
| Islas Vírgenes (EE. UU.) | 0,072 | 96 % | 0,02 | 5 | 1,65 | baja incidencia; solo lluvia | 18,34; −64,90 |
| Jamaica | 43,5 | 35 % | 0,07 | 46 | 1,59 |  | 18,11; −77,30 |
| México | 2.744 | 1 % | 0,59 | 43 | 0,74 | país extenso | 23,63; −102,55 |
| Nicaragua | 1.704 | 0 % | 0,23 | 35 | 0,54 |  | 12,87; −85,21 |
| Panamá | 166 | 0 % | 0,33 | 50 | 0,75 |  | 8,54; −80,78 |
| Puerto Rico | 29,4 | 36 % | 0,02 | 48 | 2,98 |  | 18,22; −66,59 |
| República Dominicana | 205 | 0 % | 0,13 | 43 | 0,94 |  | 18,74; −70,16 |

Total anual de casos por país:

| País | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
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

Las diferencias entre países se describen sin atribuirlas a una causa. Serotipos circulantes, inmunidad de la población, control vectorial, definición de caso y notificación no están medidos en estos datos.

## La misma asociación en cada país

La misma correlación semanal entre la anomalía climática y el crecimiento a 4 semanas, con los años evaluables de cada país. Un año es evaluable con al menos 100 casos en el año y 30 pares completos, y un país necesita al menos 5 años evaluables para tener estimación. Bermudas e Islas Vírgenes (EE. UU.) no tienen años evaluables. Tienen menos de 9 años evaluables Barbados (8), Jamaica (7) y Puerto Rico (6). Cada año evaluable tiene entre 48 y 49 pares. Un asterisco marca un intervalo del 95 % que excluye el cero. Una daga marca, en su lugar, la etiqueta de consistencia.

| País | Años evaluables | Temp. media | Temp. máxima | Temp. mínima | Lluvia (mm) | Lluvia (horas) | Humedad | Punto de rocío | ONI |
|---|---|---|---|---|---|---|---|---|---|
| Barbados | 8 | +0,17 | +0,15 | +0,19 | −0,07 | +0,02 | −0,12 | +0,04 | +0,27† |
| Bolivia | 9 | −0,14* | −0,07 | −0,21* | +0,02 | −0,04 | −0,08 | −0,17 | −0,04 |
| Brasil | 9 | −0,07 | −0,05 | −0,09 | +0,03 | +0,04 | +0,06 | +0,03 | +0,02 |
| Colombia | 9 | −0,08 | −0,10 | −0,02 | +0,13* | +0,15* | +0,19* | +0,20* | +0,05 |
| Costa Rica | 9 | +0,12 | +0,20* | +0,04 | +0,10 | +0,01 | −0,19* | −0,10 | +0,19 |
| Ecuador | 9 | −0,03 | −0,01 | +0,06 | −0,01 | +0,10 | +0,08 | +0,05 | +0,09 |
| El Salvador | 9 | +0,13* | +0,16* | +0,05 | −0,16* | −0,21† | −0,16* | −0,06 | −0,09 |
| Estados Unidos | 9 | −0,06 | −0,07 | −0,02 | +0,04 | +0,04 | +0,07 | +0,01 | +0,07 |
| Guatemala | 9 | +0,01 | +0,04 | −0,07 | −0,05 | −0,05 | −0,10 | −0,11 | −0,05 |
| Honduras | 9 | +0,02 | −0,01 | +0,09 | −0,07 | +0,03 | +0,02 | +0,07 | +0,06 |
| Jamaica | 7 | +0,09 | +0,13* | +0,05 | +0,01 | +0,05 | −0,05 | +0,00 | +0,12 |
| México | 9 | +0,06 | +0,04 | +0,13 | −0,06 | +0,05 | +0,05 | +0,08 | +0,07 |
| Nicaragua | 9 | +0,00 | −0,08 | +0,10 | +0,02 | +0,14* | +0,07 | +0,10 | +0,08 |
| Panamá | 9 | −0,09 | −0,08 | −0,07 | +0,15† | +0,06 | +0,13* | +0,00 | −0,03 |
| Puerto Rico | 6 | +0,16* | +0,14 | +0,11† | +0,02 | +0,10 | −0,08 | +0,00 | −0,01 |
| República Dominicana | 9 | −0,03 | −0,08 | +0,06 | +0,11 | +0,14* | +0,12 | +0,09 | +0,09 |

De 128 celdas país por variable con estimación, 21 tienen el intervalo fuera del cero y 4 cumplen la regla de consistencia: ONI en Barbados (7 años positivos, 1 negativo); lluvia (horas) en El Salvador (1 año positivo, 8 negativos); lluvia (mm) en Panamá (8 años positivos, 1 negativo); temp. mínima en Puerto Rico (5 años positivos, 1 negativo). Con 128 celdas y un nivel del 95 % se esperarían unas 6 con el intervalo fuera del cero sin ninguna asociación, aunque las celdas no son independientes entre sí porque las variables y los países están correlacionados. Hay al menos una celda con el intervalo fuera del cero en 10 de los 16 países. Con entre 6 y 9 años por país, cada celda tiene poca evidencia por sí sola.

En la lluvia en milímetros, El Salvador es el único de 16 países con el intervalo fuera del cero y negativo (−0,16). Con el intervalo fuera del cero y positivo están Colombia y Panamá. En la lluvia en horas y en el ONI, El Salvador tiene el valor más bajo de los 16 países.

La serie de El Salvador se construyó de dos maneras. En la comparación entre países los ceros de las vacaciones cuentan como ceros y las semanas se asignan por fecha. En el análisis por año los ceros se tratan como faltantes. Con la segunda construcción, la lluvia en milímetros tiene 1 año positivo y 8 negativos (consistente), y con la primera 3 positivos y 6 negativos (variable según el año). Los valores del conjunto difieren en 0,06 o menos, salvo la temperatura mínima (0,08).

| Variable | Serie multipaís | Años positivos y negativos | Serie del análisis por año | Años positivos y negativos (análisis por año) |
|---|---|---|---|---|
| Temp. media | +0,13 [+0,02; +0,34] | 6 y 3; variable según el año | +0,18 [+0,06; +0,36] | 6 y 3; variable según el año |
| Temp. máxima | +0,16 [+0,04; +0,34] | 6 y 3; variable según el año | +0,19 [+0,07; +0,36] | 6 y 3; variable según el año |
| Temp. mínima | +0,05 [−0,03; +0,30] | 4 y 5; variable según el año | +0,14 [+0,02; +0,35] | 6 y 3; variable según el año |
| Lluvia (mm) | −0,16 [−0,30; −0,04] | 3 y 6; variable según el año | −0,17 [−0,34; −0,06] | 1 y 8; consistente |
| Lluvia (horas) | −0,21 [−0,38; −0,11] | 1 y 8; consistente | −0,20 [−0,37; −0,09] | 1 y 8; consistente |
| Humedad | −0,16 [−0,31; −0,02] | 2 y 7; variable según el año | −0,17 [−0,33; −0,04] | 3 y 6; variable según el año |
| Punto de rocío | −0,06 [−0,15; +0,14] | 4 y 5; variable según el año | −0,04 [−0,19; +0,15] | 4 y 5; variable según el año |
| ONI | −0,09 [−0,17; +0,20] | 4 y 5; variable según el año | −0,04 [−0,13; +0,22] | 4 y 5; variable según el año |

## Corridas multipaís del clasificador retirado

Resultados guardados de tres corridas del [clasificador retirado](/biblioteca/05-sensibilidad-y-honestidad#por-qué-se-retiró-el-clasificador), que asignaba a cada semana un nivel de riesgo alto, medio o bajo. Se citan sin recalcular. En la corrida A, 0 de 5 años tienen una mayoría de semillas por encima de la climatología. En la B, 6 de 11, y en la C, 8 de 11. Las corridas B y C evalúan los 16 países con clima completo juntos y no separan el resultado de El Salvador, de modo que las semanas de nivel alto de la tabla son regionales. La A entrena con los otros países y prueba solo en El Salvador. El archivo guardado de la A contiene la semilla 42 de cada año, y el informe de esa corrida registra 11 semillas sin ninguna por encima de la climatología (0 de 55 combinaciones de año y semilla).

| Corrida | Año | Semanas de nivel alto | F1 del modelo | Recall del modelo | F1 de la climatología | Recall de la climatología | Semillas que superan la climatología |
|---|---|---|---|---|---|---|---|
| A: solo El Salvador, entrenando con los otros países | 2014 | 38 | 0,03 | 0,00 | 0,03 | 0,00 | 0 de 1 |
| A: solo El Salvador, entrenando con los otros países | 2015 | 29 | 0,11 | 0,00 | 0,11 | 0,00 | 0 de 1 |
| A: solo El Salvador, entrenando con los otros países | 2016 | 5 | 0,29 | 0,00 | 0,29 | 0,00 | 0 de 1 |
| A: solo El Salvador, entrenando con los otros países | 2019 | 1 | 0,22 | 0,00 | 0,22 | 0,00 | 0 de 1 |
| A: solo El Salvador, entrenando con los otros países | 2022 | 11 | 0,27 | 0,00 | 0,27 | 0,00 | 0 de 1 |
| B: regional, 16 países con clima completo | 2014 | 121 | 0,28 | 0,00 | 0,28 | 0,00 | 0 de 11 |
| B: regional, 16 países con clima completo | 2015 | 104 | 0,28 | 0,00 | 0,28 | 0,00 | 0 de 11 |
| B: regional, 16 países con clima completo | 2016 | 109 | 0,28 | 0,01 | 0,27 | 0,00 | 11 de 11 |
| B: regional, 16 países con clima completo | 2017 | 4 | 0,39 | 0,25 | 0,33 | 0,00 | 11 de 11 |
| B: regional, 16 países con clima completo | 2018 | 2 | 0,33 | 0,00 | 0,33 | 0,00 | 0 de 11 |
| B: regional, 16 países con clima completo | 2019 | 140 | 0,25 | 0,01 | 0,25 | 0,00 | 9 de 11 |
| B: regional, 16 países con clima completo | 2020 | 52 | 0,30 | 0,00 | 0,30 | 0,00 | 0 de 11 |
| B: regional, 16 países con clima completo | 2021 | 2 | 0,32 | 0,00 | 0,32 | 0,00 | 0 de 11 |
| B: regional, 16 países con clima completo | 2022 | 28 | 0,34 | 0,09 | 0,30 | 0,00 | 11 de 11 |
| B: regional, 16 países con clima completo | 2023 | 240 | 0,27 | 0,06 | 0,23 | 0,00 | 11 de 11 |
| B: regional, 16 países con clima completo | 2024 | 528 | 0,15 | 0,02 | 0,13 | 0,00 | 11 de 11 |
| C: regional con ONI, 16 países con clima completo | 2014 | 121 | 0,28 | 0,00 | 0,28 | 0,00 | 0 de 11 |
| C: regional con ONI, 16 países con clima completo | 2015 | 104 | 0,30 | 0,20 | 0,28 | 0,00 | 11 de 11 |
| C: regional con ONI, 16 países con clima completo | 2016 | 109 | 0,32 | 0,11 | 0,27 | 0,00 | 11 de 11 |
| C: regional con ONI, 16 países con clima completo | 2017 | 4 | 0,36 | 0,25 | 0,33 | 0,00 | 11 de 11 |
| C: regional con ONI, 16 países con clima completo | 2018 | 2 | 0,37 | 0,91 | 0,33 | 0,00 | 11 de 11 |
| C: regional con ONI, 16 países con clima completo | 2019 | 140 | 0,26 | 0,02 | 0,25 | 0,00 | 11 de 11 |
| C: regional con ONI, 16 países con clima completo | 2020 | 52 | 0,34 | 0,04 | 0,30 | 0,00 | 11 de 11 |
| C: regional con ONI, 16 países con clima completo | 2021 | 2 | 0,32 | 0,00 | 0,32 | 0,00 | 0 de 11 |
| C: regional con ONI, 16 países con clima completo | 2022 | 28 | 0,30 | 0,00 | 0,30 | 0,00 | 0 de 11 |
| C: regional con ONI, 16 países con clima completo | 2023 | 240 | 0,30 | 0,17 | 0,23 | 0,00 | 11 de 11 |
| C: regional con ONI, 16 países con clima completo | 2024 | 528 | 0,20 | 0,09 | 0,13 | 0,00 | 11 de 11 |

## Límites de los datos

- Un punto de clima por país. En Brasil, México, Estados Unidos, Colombia y Bolivia, que son países extensos, un punto no representa el territorio, y sus resultados pesan menos que los de países pequeños.
- La definición de caso de las series de la OPS no es la misma en todos los países, y la fuente indica solo el total.
- Once puntos anuales para la correlación con la señal regional. Los intervalos son amplios: de −0,16 a +0,80 en El Salvador.
- La serie de El Salvador de 2024 es un promedio de varias semanas hecho en origen. 2020 y 2024 quedan fuera del análisis semanal.
- La semana del año se calcula por la fecha de inicio y puede diferir en una de la numeración epidemiológica de cada país.
- El clima diario se agrega con la zona horaria de El Salvador para todos los países.
- Bermudas tiene entre 0 y 3 casos al año e Islas Vírgenes (EE. UU.) entre 0 y 19, salvo 185 en 2024. Ninguna de las dos tiene años evaluables y su clima incluye solo las dos variables de lluvia.
- Nueve años por país o menos para las correlaciones semanales.
- El Salvador cambia de posición según los años que se incluyan en la señal regional, como muestran las dos medidas y la tabla de años quitados.
- Los desfases de la sección del ciclo anual se calculan entre ciclos medios y dependen del promedio de 4 semanas de los casos.

## Datos que harían falta

Lo que no se pudo medir con las series actuales, qué permitiría medir cada dato y quién podría tenerlo.

| Dato | Qué permitiría medir | Quién podría tenerlo |
|---|---|---|
| Capturas semanales del tablero de MINSAL con cada versión conservada | Las revisiones de la serie y una evaluación del pronóstico con los datos tal como estaban publicados cada semana | MINSAL |
| Casos por fecha de inicio de síntomas y por fecha de notificación, sin promedio de varias semanas | Los desfases reales entre el clima y los casos, hoy mezclados con el promedio que aplica la fuente | MINSAL |
| Series semanales por departamento con una definición de caso constante en más años que los cinco analizables hoy (2018, 2019, 2021, 2022 y 2023) | La comparación entre departamentos con más años y la prueba de las asociaciones por zona | MINSAL |
| Población por departamento y año | Incidencia en lugar de conteos, y su comparación entre departamentos y entre países | DIGESTYC y organismos de estadística de cada país |
| Clima con más resolución: estaciones meteorológicas con lluvia diaria, varios puntos por país o promedios ponderados por población | Una medida de la lluvia que represente el territorio en que ocurren los casos | MARN y servicios meteorológicos de cada país |
| Serotipos circulantes por semana | Si los años de mayor aumento de casos coinciden con un cambio de serotipo | MINSAL (vigilancia de laboratorio) |
| Índices entomológicos (viviendas con larvas, ovitrampas) | La relación entre el clima, la población de mosquitos y los casos | MINSAL |
| Acciones de control vectorial con fecha y lugar (fumigación, eliminación de criaderos) | Separar el efecto del clima del efecto de las campañas | MINSAL |
| Seroprevalencia por edad | La parte de la población con inmunidad previa en cada año | Estudios de campo |
| Almacenamiento de agua en viviendas y datos de abastecimiento | Si los años de lluvia baja tienen más recipientes con agua almacenada | Estudios de campo y operadores de agua |
| Definición de caso y cambios de notificación por país y año | Comparar los 18 países con la misma definición | Ministerios de salud y OPS |
| Años anteriores a 2014 | Más de un brote grande para evaluar la estabilidad de las asociaciones | MINSAL y OPS |

## Reproducir y descargar

Los dos archivos completos, con los parámetros de cada cálculo, las series semanales de casos y clima de los 18 países y la climatología de 52 semanas, se descargan desde la página [Clima y dengue](/analisis/clima). El archivo de los 18 países guarda el SHA-256 de las dos entradas que no se versionan:

| Entrada | SHA-256 |
|---|---|
| Temporal_extract_PAHO_V1_3.csv | f8eaa7134dd7e4a718df16ec5e2bfdd60bf446732281a1bbf3a1463084af230f |
| clima_multipais.json | 066f17474daa3fa7e020a8e83b83a54b3826c3a0fc81601eea325b4a49e55d48 |

Los protocolos de los dos análisis se escribieron antes de correr el código. La estructura de los archivos y la decisión de publicarlos están en la [decisión de arquitectura 0023](https://github.com/aetheris-team/EPI-Aetheris/blob/main/docs/adr/0023-clima-dengue-descriptivo.md).
