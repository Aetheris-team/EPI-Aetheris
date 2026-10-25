# Experimento: brotes sin precedente en la historia y una familia que extrapola (2026-10-02)

> Protocolo fijado el 2026-10-02, antes de la primera corrida, en la rama
> `feat/mejora-predictor-agente`. Los años, los modelos, la métrica y los criterios quedan
> escritos aquí antes de ver un resultado. Cualquier cambio posterior va en una sección de
> enmiendas con fecha, antes de la corrida a la que afecta.

## Motivación

El sitio dice que la predicción puede quedarse corta ante un brote sin precedente en la serie,
y que su ventaja depende de que la historia de entrenamiento ya incluya un brote grande. El
soporte es un solo año: con la historia recortada a 2016 en adelante, el skill de 2019 fue
−0,32 contra la referencia publicada (`modelo-actual.md`, sección 5.2). Los árboles de M0 no
extrapolan por encima del rango de entrenamiento; una regresión cuantílica lineal sobre las
mismas variables sí puede hacerlo. Este experimento amplía la evidencia a más de un año y mide
esa alternativa.

## Preguntas

1. Cuando la historia de entrenamiento no contiene ningún año de magnitud igual o mayor que el
   año de prueba, ¿M0 conserva alguna ventaja sobre la persistencia?
2. ¿Una regresión cuantílica lineal con las mismas variables, calibrada igual, iguala a M0 en
   la validación normal y lo supera cuando falta el precedente?

## Diseño

**Años de prueba y recorte.** Para cada año de prueba Y se excluyen de los objetivos de
entrenamiento, además de 2020, todos los años cuyo total anual de OpenDengue es mayor o igual
que el de Y. Los años excluidos se conservan solo como insumo de rezagos, igual que 2020. Las
referencias se calculan con la misma historia recortada, para que modelo y referencia dispongan
de la misma información; la persistencia limpia con la historia completa se reporta al lado.

| Y | total de Y | años excluidos (total anual) | máximo anual que queda | razón Y / máximo |
|---|---|---|---|---|
| 2019 | 27.470 | 2014 (53.460), 2015 (50.169) | 8.789 (2016) | 3,1 |
| 2022 | 16.542 | 2014, 2015, 2019 (27.470) | 8.789 (2016) | 1,9 |
| 2024 | 8.552 | 2014, 2015, 2016 (8.789), 2019, 2022 | 8.448 (2018) | 1,0 |

Los totales salen de la base semilla (`modelo-actual.md`, sección 3.1). 2019 y 2022 son
pruebas de brote sin precedente; 2024 tiene un precedente de su misma magnitud y sirve de
control de que el recorte por sí solo no explica una caída. 2021 y 2023 no se pueden recortar
sin dejar la historia por debajo del mínimo de pares.

**Modelos.**

| Modelo | Definición |
|---|---|
| M0 | El publicado: HGBR por cuantil con los hiperparámetros del ADR 0020, calibración CQR-r con 52 pares, cadencia 2. |
| L0 | `sklearn.linear_model.QuantileRegressor` por cuantil sobre las mismas variables estandarizadas con la media y la desviación del entrenamiento propio, `alpha = 0,001` (penalización L1), `solver = "highs"`, mismo objetivo `log1p`, misma calibración CQR-r, misma cadencia, mismo mínimo de pares. |

Dos modelos, sin variantes adicionales.

**Corridas.**

- Validación normal (historia completa desde 2014): objetivos en 2019, 2021, 2022, 2023 y
  2024, h = 1 a 8, M0 y L0. M0 debe reproducir los cuantiles del experimento de mejora.
- Recorte: para cada Y de la tabla, objetivos en Y, h = 1 a 8, M0 y L0 con la historia
  recortada de Y.
- Serie del tablero (se mira una vez, solo si L0 pasa la validación normal): objetivos de
  2025-S1 a 2026-S37, L0 y la mezcla C construida con L0 en lugar de M0.

## Referencias

Persistencia limpia (criterio), climatología estacional y persistencia estacional del
experimento de mejora, con la historia recortada en las corridas de recorte. En el tablero, la
persistencia suavizada del experimento de tendencia.

## Métrica

WIS sobre 23 cuantiles, skill contra la referencia, cobertura del 50 % y del 95 %, fracción de
lo observado bajo la mediana, y el cociente entre la mediana predicha y lo observado en las
semanas del pico de cada año (las 8 semanas de mayor conteo), como medida de saturación.

## Criterios

**Pregunta 1.** La robustez ante brotes sin precedente se declara sostenida para un modelo si
su skill contra la persistencia limpia recortada es mayor que 0 en 2019 y en 2022, a h = 4 y
a h = 8. Si en alguno de los dos años es menor o igual que 0, la afirmación del sitio (la
predicción puede quedarse corta sin precedente) queda confirmada para ese modelo. 2024 no
entra al criterio.

**Pregunta 2, validación normal.** L0 pasa si, a h = 4 y a h = 8, contra la persistencia
limpia: skill medio por año mayor que 0, gana en al menos 4 de 5 años, cobertura del 95 % en
[0,85; 0,99] y del 50 % en [0,35; 0,65], y WIS agrupado no mayor que el de M0.

**Pregunta 2, recorte.** L0 supera a M0 sin precedente si su WIS es menor que el de M0 en
2019 y en 2022, a h = 4 y a h = 8.

**Tablero.** Si L0 pasó la validación normal: C con L0 cumple si a h = 4 y a h = 8 su WIS no
supera al de la C publicada y la cobertura del 95 % es de al menos 0,85, con skill mayor que 0
contra la persistencia suavizada.

## Qué habilita cada resultado

- Robustez sostenida para M0: el sitio puede suavizar la salvedad sobre brotes sin precedente,
  citando los dos años.
- Robustez no sostenida (lo esperado): la salvedad se mantiene con dos años de soporte en vez
  de uno, y la cifra pasa a la Biblioteca.
- L0 pasa la validación normal y supera a M0 sin precedente: queda descrita como candidata a
  reemplazo o a mezcla, con su propia firma y prueba prospectiva pendientes.
- L0 no pasa la validación normal: se archiva como familia descartada con las cifras, aunque
  extrapole mejor.

## Controles

- Aserción anti-fuga y control negativo a h = 4 en la validación normal y en cada recorte.
- La exclusión de años se verifica con una aserción sobre los índices reales de entrenamiento:
  ningún objetivo cae en un año excluido.
- M0 en la validación normal reproduce los cuantiles de `mejora_validacion.json`.
- Control de mutación para L0 a h = 4 en la validación normal: el WIS debe empeorar.

## Reproducibilidad

Script `backend/ingestion/experimento_nowcast_recorte.py`, solo lectura sobre Postgres, 4
procesos de un hilo y `nice`. Salida en `backend/ingestion/data/interim/nowcast/recorte_*.json`
y copia versionada en `docs/agentes/mejora-predictor/resultados-nuevos/`.

## Enmiendas

### 2026-10-02, antes de la primera corrida completa

1. **Orígenes sin predicción en el recorte de 2019.** Con 2014 y 2015 excluidos, la historia
   disponible al empezar 2019 tiene 156 pares (tres años menos los rezagos iniciales), por
   debajo del mínimo de 160 que exige el método publicado para ajustar y calibrar. Los primeros
   orígenes de 2019 no tienen predicción hasta que entran pares con objetivo en 2019; el número
   de orígenes sin predicción se reporta por horizonte y las cifras de 2019 recortado se
   comparan con la historia completa sobre los orígenes que sí tienen predicción. No se baja el
   mínimo para no cambiar el método.
2. **Referencias con la historia recortada.** Se implementan en
   `experimento_nowcast_comun.referencia`, que con solo 2020 excluido reproduce las del
   experimento de mejora (probado en `tests/test_experimento_nowcast_comun.py`).
3. **Saturación.** Las 8 semanas de mayor conteo se toman entre las que tienen predicción en
   cada corrida; el cociente es mediana predicha / observado promediado sobre ellas.

## Resultados (ejecución 2026-10-02)

Corrida única de `experimento_nowcast_recorte.py` sobre la base de esta rama. Salida completa
en `docs/agentes/mejora-predictor/resultados-nuevos/recorte.json` (flotantes redondeados a 3
decimales). Dos modelos, sin variantes añadidas.

### Controles

- Garantía anti-fuga y control negativo a h = 4 en la validación normal y en cada recorte.
- La exclusión de años coincide con la tabla del protocolo: 2019 excluye 2014 y 2015 (queda
  un máximo anual de 8.789); 2022 excluye 2014, 2015 y 2019 (8.789); 2024 excluye 2014, 2015,
  2016, 2019 y 2022 (8.448). La aserción sobre los índices reales de entrenamiento no encontró
  ningún objetivo en un año excluido.
- M0 reproduce las 2.044 predicciones de `mejora_validacion.json` con diferencia 0.
- Mutación de L0 a h = 4: el WIS pasa de 75,3 a 164,7.
- Orígenes sin predicción en el recorte de 2019 (enmienda 1): de 5 a h = 1 a 12 a h = 8, para
  los dos modelos; n = 44 a h = 4 y 40 a h = 8. Ninguno en 2022 ni en 2024.

### Validación normal (historia completa), contra la persistencia limpia

WIS; skill medio por año (años ganados); skill agrupado; cobertura 50 %; cobertura 95 %;
fracción bajo la mediana:

| h | M0 | L0 |
|---|---|---|
| 1 | 35,6; −0,04 (2/5); −0,01; 0,58; 0,92; 0,46 | 42,0; −0,44 (0/5); −0,19; 0,56; 0,89; 0,40 |
| 2 | 37,9; +0,06 (3/5); +0,06; 0,60; 0,91; 0,45 | 53,7; −0,35 (1/5); −0,33; 0,55; 0,90; 0,37 |
| 3 | 46,4; +0,05 (3/5); +0,05; 0,56; 0,90; 0,46 | 65,5; −0,41 (0/5); −0,35; 0,54; 0,86; 0,35 |
| 4 | 56,6; +0,05 (4/5); +0,04; 0,55; 0,88; 0,47 | 75,3; −0,37 (0/5); −0,28; 0,52; 0,84; 0,35 |
| 5 | 61,4; +0,12 (4/5); +0,09; 0,56; 0,90; 0,47 | 86,9; −0,39 (0/5); −0,28; 0,44; 0,84; 0,34 |
| 6 | 67,9; +0,13 (4/5); +0,11; 0,54; 0,90; 0,47 | 88,4; −0,26 (0/5); −0,16; 0,43; 0,83; 0,33 |
| 7 | 73,5; +0,16 (4/5); +0,14; 0,57; 0,89; 0,42 | 99,7; −0,30 (0/5); −0,17; 0,42; 0,79; 0,39 |
| 8 | 78,8; +0,18 (4/5); +0,17; 0,57; 0,88; 0,43 | 104,0; −0,28 (1/5); −0,09; 0,46; 0,81; 0,37 |

Skill por año de L0 contra la limpia: a h = 4, 2019 −0,20, 2021 −0,66, 2022 −0,40, 2023 −0,28,
2024 −0,29; a h = 8, +0,02, −0,42, −0,07, −0,89, −0,04. Contra la referencia publicada L0 queda
entre −0,06 y +0,10 agrupado, con 1 a 3 años ganados. L0 no pasa ninguna de las cuatro
condiciones en ninguno de los dos horizontes decisivos. Predice de menos de forma sistemática
(fracción bajo la mediana 0,33 a 0,40) y sus cuantiles altos se disparan en algunos orígenes:
el peor WIS individual en la validación es 1.583 (origen 2019-07-07, observado 2.178, mediana
436).

### Recorte: brotes sin precedente

Contra la persistencia limpia calculada con la misma historia recortada (n; WIS; WIS de la
referencia; skill; cobertura 50 %; cobertura 95 %; fracción bajo la mediana):

| año | h | M0 | L0 |
|---|---|---|---|
| 2019 | 1 | 47; 310,0; 108,1; −1,87; 0,49; 0,68; 0,23 | 47; 221,1; 108,1; −1,05; 0,60; 0,83; 0,13 |
| 2019 | 4 | 44; 343,8; 191,3; −0,80; 0,34; 0,66; 0,14 | 44; 285,4; 191,3; −0,49; 0,55; 0,73; 0,20 |
| 2019 | 8 | 40; 394,8; 309,0; −0,28; 0,30; 0,57; 0,03 | 40; 381,0; 309,0; −0,23; 0,42; 0,75; 0,17 |
| 2022 | 1 | 52; 87,6; 30,1; −1,91; 0,31; 0,69; 0,21 | 52; 102,3; 30,1; −2,40; 0,42; 0,77; 0,33 |
| 2022 | 4 | 52; 113,9; 56,3; −1,02; 0,44; 0,69; 0,21 | 52; 102,7; 56,3; −0,82; 0,42; 0,96; 0,40 |
| 2022 | 8 | 52; 134,2; 101,1; −0,33; 0,37; 0,58; 0,25 | 52; 526.058; 101,1; −5.203; 0,46; 0,92; 0,44 |
| 2024 | 1 | 52; 11,7; 9,8; −0,19; 0,69; 1,00; 0,58 | 52; 47,5; 9,8; −3,84; 0,44; 1,00; 0,71 |
| 2024 | 4 | 52; 20,9; 21,1; +0,01; 0,75; 0,98; 0,44 | 52; 233,7; 21,1; −10,07; 0,52; 0,98; 0,73 |
| 2024 | 8 | 52; 22,9; 31,7; +0,28; 0,52; 1,00; 0,31 | 52; 29,7; 31,7; +0,06; 0,69; 0,92; 0,58 |

Los ocho horizontes y la comparación contra la persistencia limpia con la historia completa
están en el JSON; con esa referencia los skill de 2019 y 2022 son entre 0,03 y 0,65 más
negativos aún, porque la historia completa da a la persistencia residuos de 2014-2015 que
ensanchan sus rangos. El WIS de L0 en 2022 a h = 6 (3.256) y h = 8 (526.058) y en 2024 a h = 3
(26.608) y h = 4 (234) viene de cuantiles altos que se disparan en pocos orígenes (en 2022-06-26
a h = 8 el WIS individual es 20 millones con una mediana de 241 y un observado de 353): la
calibración CQR-r topa el factor en 4 pero no acota los cuantiles de partida.

Saturación: cociente mediana predicha / observado en las 8 semanas de mayor conteo, con la
historia recortada y, entre paréntesis, con la historia completa (validación normal):

| año | h | M0 | L0 |
|---|---|---|---|
| 2019 | 4 | 0,12 (0,57) | 0,24 (0,41) |
| 2019 | 8 | 0,10 (0,31) | 0,10 (0,21) |
| 2022 | 4 | 0,41 (0,91) | 0,41 (0,81) |
| 2022 | 8 | 0,31 (0,88) | 0,63 (0,75) |
| 2024 | 4 | 0,83 (0,97) | 0,65 (0,95) |
| 2024 | 8 | 0,71 (0,84) | 0,69 (1,46) |

Lo que muestran las cifras:

- Sin un año de magnitud comparable en la historia, M0 queda muy por detrás de la persistencia
  en los dos años de brote: −0,80 y −0,28 en 2019, −1,02 y −0,33 en 2022 (h = 4 y 8). En el
  pico de 2019 su mediana vale el 12 % de lo observado; en el de 2022, el 41 %. Con la
  historia completa esas cifras son 57 % y 91 %. La cobertura del 95 % cae a 0,57 a 0,69 y la
  fracción de observados por debajo de la mediana a 0,03 a 0,25: el modelo predice de menos
  casi siempre.
- 2024 (control, con precedentes de su magnitud: 2018 con 8.448): el recorte no cambia el
  cuadro. M0 recortado da +0,01 y +0,28 contra la referencia recortada (con la historia
  completa, +0,03 y +0,47 contra la limpia). La caída de 2019 y 2022 viene de la falta de
  precedente, no de tener menos años.
- L0 extrapola más que M0 en 2019 (WIS 285 contra 344 a h = 4; 381 contra 395 a h = 8) y en
  2022 a h = 4 (103 contra 114), pero sigue muy por debajo de la persistencia y en 2022 a h = 8
  se dispara. La familia lineal no resuelve el problema; mueve la mediana del pico de 2019
  del 12 % al 24 % de lo observado.

### Veredicto

- Pregunta 1: la robustez ante brotes sin precedente no se sostiene, ni para M0 ni para L0.
  La salvedad del sitio ("ante un brote sin precedente en la serie, la predicción puede
  quedarse corta") queda confirmada con dos años en vez de uno, y con una cifra: en el pico
  la mediana queda en el 12 % (2019) y el 41 % (2022) de lo observado.
- Pregunta 2: L0 no pasa la validación normal (resultado negativo para la familia lineal con
  estas variables y esta regularización) y, aunque a h = 4 supera a M0 en los dos años sin
  precedente, no lo hace en 2022 a h = 8. La serie del tablero no se mira.

### Limitaciones

- Dos años sin precedente (2019 y 2022), que además comparten el mismo máximo anual previo
  (2016). No hay una tercera serie con que repetirlo.
- En 2019 recortado faltan los primeros 5 a 12 orígenes del año por el mínimo de pares; el
  pico de 2019 (junio a agosto) sí está cubierto.
- L0 se probó con una sola regularización (`alpha = 0,001`) y sin acotar los cuantiles; una
  variante con cuantiles acotados o con menos variables podría comportarse distinto, pero
  elegirla sobre estos años sería un barrido que el protocolo excluye.
- Las referencias recortadas usan la misma historia que el modelo; la persistencia depende
  poco del nivel absoluto y por eso resiste mejor el recorte, lo que es parte del hallazgo y
  no un sesgo de la comparación.
