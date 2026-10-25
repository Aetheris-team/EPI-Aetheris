# Experimento: calibración de los rangos y ajustes de corto plazo (2026-10-02)

> Protocolo fijado el 2026-10-02, antes de la primera corrida, en la rama
> `feat/mejora-predictor-agente`. Las variantes, las fases, la métrica y los criterios quedan
> escritos aquí antes de ver un resultado. Cualquier cambio posterior va en una sección de
> enmiendas con fecha, antes de la corrida a la que afecta.

## Motivación

1. **Los rangos quedan por debajo del nominal.** En la validación de OpenDengue (2019 y
   2021-2024) M0 calibrado cubre 0,55 al 50 % y 0,88 al 95 % a 4 semanas. Con la serie del
   tablero (2025-2026) la mezcla C cubre 0,39 y 0,91; en 2026 solo, 0,79 al 95 %, por debajo
   del 0,85 que exige la prueba prospectiva. La calibración CQR-r actual estira cada semiancho
   con un factor simétrico calculado sobre 52 pares, winsorizado y topado, y los tres
   intervalos externos colapsan al mismo factor (`modelo-actual.md`, sección 2.3).
2. **A 1 a 3 semanas la ventaja es casi nula.** Contra la persistencia limpia, M0 vale entre
   −0,04 y 0,05 a 1 a 3 semanas en la validación, y C vale −0,08 a 1 semana en 2024-2026.
   En 2025 el modelo predijo de más casi todo el año: el problema estaba en la posición de la
   mediana, no en el ancho (experimento de mejora, lectura).

Las dos cosas se pueden tratar sin reentrenar nada: son capas que actúan sobre los cuantiles
que el modelo ya produce, con información anterior al origen. Por eso van en un solo
experimento con dos preguntas.

## Preguntas

A. ¿Alguna calibración alternativa acerca la cobertura al nominal con un costo en WIS de a lo
sumo 5 %?

B. ¿Una corrección del sesgo reciente o un peso de mezcla elegido por desempeño reciente
mejora la predicción a 1 a 3 semanas sin empeorarla a 4 y a 8?

## Qué no se hace

- No se reentrena M0 ni se cambian sus hiperparámetros, sus variables ni su cadencia.
- No se tocan la base de datos, la API, el frontend ni los artefactos publicados.
- No se usan semanas objetivo desde 2026-S38.
- No se añaden variantes después de ver un resultado.

## Capas

Todas actúan sobre los cuantiles en escala `log1p`, se reordenan y vuelven a escala natural
con piso 0. Todas usan solo pares con fecha objetivo anterior a la del origen.

Calibración (pregunta A):

| Capa | Definición |
|---|---|
| R0 | CQR-r publicada: factor simétrico por intervalo sobre los 52 pares más recientes, score winsorizado al p90, factor en [0; 4]. Control. |
| R1 | CQR-r asimétrica: un factor para el semiancho inferior y otro para el superior, cada uno al nivel conformal `1 − α/2` de su propio score (`(m − y)/semi_inf` y `(y − m)/semi_sup`), con la misma winsorización y el mismo tope. |
| R2 | CQR-r con 104 pares de calibración en lugar de 52 (mínimo de entrenamiento propio 120, como ahora; los orígenes con menos de 224 pares no tienen predicción con esta capa). |
| R3 | Conformal adaptativo (Gibbs y Candès, 2021) sobre R0: por intervalo, el nivel nominal `1 − α` se reemplaza por `1 − α_t`, con `α_{t+1} = α_t + γ (α − err_t)`, `err_t = 1` si el valor observado del par más reciente ya conocido quedó fuera del intervalo R0 y 0 si no, `α_0 = α`, `γ = 0,03`, `α_t` acotado en [0,001; 0,5]. El factor se lee de los mismos scores de R0 al nivel `1 − α_t`. |

Capas de corto plazo (pregunta B):

| Capa | Definición |
|---|---|
| S1 | Sesgo reciente: todos los cuantiles se desplazan en `log1p` por `−β · ē`, con `ē` el promedio de `log1p(mediana) − log1p(y)` en los últimos `K = 8` pares conocidos del mismo horizonte (objetivo anterior al origen), `β = 1`. Si hay menos de 4 pares conocidos no se corrige. |
| C1 | Peso por desempeño reciente, solo para la mezcla C: `w ∈ {0; 0,25; 0,5; 0,75; 1}` es el peso de M0 que minimiza el WIS medio de la mezcla con T sobre los últimos `K = 26` pares conocidos del mismo horizonte. Con menos de 8 pares conocidos, `w = 0,5`. |

Sensibilidades, que se reportan y no deciden: R3 con `γ` en {0,01; 0,10}; S1 con `K` en
{4; 13} y con `β = 0,5`; C1 con `K` en {13; 52}.

## Fases

**Fase A, validación (decide):** M0 sobre la serie mixta con objetivos en 2019, 2021, 2022,
2023 y 2024, h = 1 a 8. Capas R1, R2, R3 y S1 sobre M0. La cadena de M0 es la del experimento
de mejora y debe reproducir sus cuantiles.

**Fase B, serie del tablero (se mira una vez):** objetivos de 2025-S1 a 2026-S37, h = 1 a 8.
La predicción publicada ahí es C, mezcla de M0 calibrado y T. Se evalúan:

- C con R0 (control, debe reproducir `tendencia_verificacion.json`);
- C con la capa de calibración elegida en la fase A aplicada a M0 antes de mezclar;
- R4: CQR-r simétrica de 52 pares aplicada a la mezcla C misma, con los errores de C en los
  pares de calibración (T se evalúa en esos pares con la historia promediada). Solo existe en
  esta fase porque C solo existe aquí;
- S1 y C1 sobre C, si pasaron la fase A (S1) o directamente (C1, que no tiene equivalente en
  la fase A; el experimento de mejora ya midió la mezcla con la persistencia por desempeño
  reciente y no se confirmó).

Las demás capas se calculan y se reportan en la fase B, pero su cifra no decide nada. Los
orígenes de la fase B que necesitan historia de 2024 para las ventanas de S1 y C1 la toman de
la cadena de validación, como hace `experimento_nowcast_tendencia.py --verificar`.

2025 y 2026 sirvieron para elegir C. Un resultado positivo en la fase B es candidato a una
prueba prospectiva futura, no una confirmación.

## Referencias

Persistencia limpia (validación) y persistencia suavizada (tablero), como en los experimentos
de mejora y de tendencia. Se reportan también la publicada y, en el tablero, la limpia.

## Métrica

WIS sobre 23 cuantiles, agrupado y por año; skill contra la referencia y contra la capa de
control; cobertura del 50 % y del 95 %; fracción de lo observado bajo la mediana. Horizontes
decisivos: h = 4 y h = 8 para la pregunta A; h = 1, 2 y 3 (ganancia) más h = 4 y h = 8 (no
empeorar) para la pregunta B.

## Criterios

**Pregunta A, fase A.** Una capa de calibración pasa si, agrupado sobre la validación, a
h = 4 y a h = 8: cobertura del 95 % en [0,90; 0,99], cobertura del 50 % en [0,40; 0,60] y
WIS ≤ 1,05 × WIS de R0. Si pasa más de una, se elige la de menor WIS medio entre h = 4 y
h = 8. Si no pasa ninguna, resultado negativo.

**Pregunta A, fase B.** La capa elegida (y R4) cumple si, sobre 2025-2026 agrupados, a h = 4 y
a h = 8: cobertura del 95 % de al menos 0,85 en 2025 y en 2026 por separado, cobertura del
50 % en [0,35; 0,65], WIS ≤ 1,05 × WIS de C con R0 y skill mayor que 0 contra la persistencia
suavizada.

**Pregunta B, fase A (S1).** Pasa si, agrupado sobre la validación, el WIS de M0 con S1 es
menor que el de M0 en h = 1, 2 y 3, con skill mayor que 0 contra la persistencia limpia en
los tres, y a h = 4 y h = 8 su WIS no supera 1,02 × WIS de M0.

**Pregunta B, fase B (S1 y C1).** Cumple si, sobre 2025-2026 agrupados, el WIS de la capa
sobre C es menor que el de C en h = 1, 2 y 3, con skill mayor que 0 contra la persistencia
suavizada en los tres, a h = 4 y h = 8 su WIS no supera 1,02 × WIS de C, y la cobertura del
95 % a h = 4 y h = 8 es de al menos 0,85.

## Qué habilita cada resultado

- Una capa que pasa la fase A y cumple en la fase B queda descrita como candidata a prueba
  prospectiva, con el procedimiento para aplicarla al artefacto. No reemplaza nada.
- Una capa que pasa la fase A y no cumple en la fase B se archiva con las cifras; el sitio no
  cambia.
- Ninguna capa pasa: resultado negativo; la cobertura por debajo del nominal queda como
  limitación medida y no corregible con estas capas.

## Controles

- Aserción anti-fuga y control negativo a h = 4 en las dos fases.
- M0 con R0 reproduce los cuantiles de `mejora_validacion.json` y `mejora_confirmacion.json`
  (diferencia 0); C con R0 reproduce `tendencia_verificacion.json` en 2025-2026.
- Las capas R3, S1 y C1 solo pueden usar pares cuyo objetivo es anterior a la fecha del
  origen; el script lo comprueba con una aserción sobre los índices reales.
- Número de variantes: 4 capas de calibración (una de control), 2 capas de corto plazo y 6
  sensibilidades. Se reportan todas.

## Reproducibilidad

Script `backend/ingestion/experimento_nowcast_rangos.py`, solo lectura sobre Postgres, 4
procesos de un hilo y `nice`. La cadena de M0 guarda, por origen, los cuantiles sin calibrar
y las predicciones del conjunto de calibración, de modo que todas las capas se calculan sobre
la misma corrida. Salida en `backend/ingestion/data/interim/nowcast/rangos_*.json` y copia
versionada en `docs/agentes/mejora-predictor/resultados-nuevos/`.

## Enmiendas

### 2026-10-02, antes de la primera corrida

Decisiones de implementación que el protocolo no fijaba. Ninguna cambia las capas elegibles,
las fases ni los criterios.

1. **Ventana de recencia de S1 y C1.** Las cadenas de validación solo contienen pares con
   objetivo en los años de validación, de modo que para los primeros orígenes de 2021 los
   "últimos pares conocidos" serían de 2019. Para que la corrección sea reciente de verdad, S1
   y C1 solo consideran pares cuyo objetivo cae dentro de las 52 semanas anteriores a la fecha
   del origen, y dentro de ellos toman los últimos `K`. Con menos de 4 pares (S1) u 8 pares (C1)
   no se corrige y el peso queda en 0,5.
2. **Empates en C1.** Si varios pesos dan el mismo WIS medio, se elige el más cercano a 0,5.
3. **Mediana en S1.** El sesgo se mide con la mediana calibrada por R0, que coincide con la del
   modelo sin calibrar porque CQR-r no mueve la mediana.
4. **R3 durante 2020.** No hay pares con objetivo en 2020 en la cadena; el nivel adaptado se
   conserva sin actualizar entre el último par de 2019 y el primero de 2021.
5. **Orígenes sin predicción.** Los orígenes que R2 deja sin predicción por el mínimo de 224
   pares se excluyen de la comparación de todas las capas en ese horizonte, para que todas se
   midan sobre los mismos orígenes; el número excluido se reporta.
6. **Control de reproducción en la fase B.** Por la misma razón que en la enmienda del
   experimento de insumos (sin ONI de 2025-2026 en la semilla de esta rama), M0 con R0 y C con
   R0 reproducen con diferencia 0 la validación, y en 2025-2026 el script reporta la diferencia
   máxima frente a `mejora_confirmacion.json` y `tendencia_verificacion.json` sin detenerse.
   Todas las capas de la fase B se comparan sobre la misma corrida.

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

## Resultados (ejecución 2026-10-02; fase B repetida el 2026-10-03)

Corrida única de `experimento_nowcast_rangos.py` sobre la base de esta rama. Salida completa en
`docs/agentes/mejora-predictor/resultados-nuevos/rangos.json` (flotantes redondeados a 3
decimales). Capas elegibles: R1, R2, R3 (calibración), S1 y C1 (corto plazo); sensibilidades:
R3 con γ 0,01 y 0,10, S1 con (K, β) = (4; 1), (13; 1) y (8; 0,5), C1 con K = 13 y 52. Se
reportan todas; solo las elegibles deciden.

### Controles

- Garantía anti-fuga verificada a h = 4 en la validación (13 orígenes) y en el tablero (14),
  con control negativo.
- M0 con R0 reproduce las 2.044 predicciones de `mejora_validacion.json` con diferencia 0; C
  con R0 reproduce las 416 predicciones de 2024 de `tendencia_verificacion.json` con
  diferencia 0. En 2025-2026, la primera ejecución (sin ONI de 2025-2026) difería desde
  2025-01-05; en la repetición con el ONI cargado M0 y C reproducen las 647 predicciones con
  diferencia 0.
- R2 no dejó ningún origen sin predicción (el mínimo de 224 pares se cumple en todos).

### Fase A, validación 2019 y 2021-2024, contra la persistencia limpia

Capas elegibles (WIS; skill contra R0; skill contra la referencia; cobertura 50 %; cobertura
95 %; fracción bajo la mediana; n = 259 a 252):

| h | R0 (publicada) | R1 asimétrica | R2 104 pares | R3 adaptativa | S1 sesgo reciente |
|---|---|---|---|---|---|
| 1 | 35,6; 0,00; −0,01; 0,57; 0,92; 0,46 | 35,7; −0,00; −0,01; 0,55; 0,86; 0,46 | 36,3; −0,02; −0,03; 0,51; 0,92; 0,51 | 37,5; −0,05; −0,07; 0,71; 0,92; 0,46 | 40,6; −0,14; −0,15; 0,49; 0,90; 0,45 |
| 2 | 37,9; 0,00; +0,06; 0,60; 0,92; 0,45 | 38,7; −0,02; +0,04; 0,55; 0,82; 0,45 | 38,2; −0,01; +0,05; 0,56; 0,90; 0,48 | 39,4; −0,04; +0,02; 0,67; 0,90; 0,45 | 43,9; −0,16; −0,09; 0,50; 0,92; 0,45 |
| 3 | 46,4; 0,00; +0,05; 0,56; 0,90; 0,46 | 49,6; −0,07; −0,02; 0,53; 0,81; 0,46 | 47,9; −0,03; +0,02; 0,54; 0,89; 0,49 | 52,3; −0,13; −0,07; 0,68; 0,91; 0,46 | 60,4; −0,30; −0,24; 0,48; 0,91; 0,47 |
| 4 | 56,6; 0,00; +0,04; 0,55; 0,88; 0,47 | 58,3; −0,03; +0,01; 0,54; 0,77; 0,47 | 54,9; +0,03; +0,07; 0,54; 0,91; 0,48 | 63,7; −0,13; −0,09; 0,64; 0,89; 0,47 | 81,4; −0,44; −0,39; 0,48; 0,90; 0,46 |
| 5 | 61,4; 0,00; +0,09; 0,56; 0,90; 0,47 | 61,3; +0,00; +0,09; 0,56; 0,78; 0,47 | 60,0; +0,02; +0,11; 0,56; 0,93; 0,47 | 66,4; −0,08; +0,02; 0,64; 0,90; 0,47 | 100,4; −0,64; −0,48; 0,45; 0,91; 0,48 |
| 6 | 67,9; 0,00; +0,11; 0,54; 0,90; 0,47 | 69,5; −0,02; +0,09; 0,49; 0,78; 0,47 | 68,3; −0,01; +0,11; 0,56; 0,91; 0,47 | 74,5; −0,10; +0,03; 0,67; 0,92; 0,47 | 122,3; −0,80; −0,60; 0,47; 0,92; 0,48 |
| 7 | 73,5; 0,00; +0,14; 0,56; 0,89; 0,42 | 75,6; −0,03; +0,12; 0,51; 0,80; 0,42 | 75,7; −0,03; +0,12; 0,56; 0,91; 0,41 | 82,8; −0,13; +0,03; 0,66; 0,90; 0,42 | 131,4; −0,79; −0,54; 0,49; 0,91; 0,47 |
| 8 | 78,8; 0,00; +0,17; 0,57; 0,88; 0,43 | 79,0; −0,00; +0,17; 0,50; 0,79; 0,43 | 80,9; −0,03; +0,15; 0,56; 0,91; 0,43 | 86,6; −0,10; +0,09; 0,65; 0,89; 0,43 | 130,2; −0,65; −0,37; 0,48; 0,89; 0,46 |

Cobertura del 95 % por año en los horizontes decisivos:

| capa | 2019 h4 | 2021 h4 | 2022 h4 | 2023 h4 | 2024 h4 | 2019 h8 | 2021 h8 | 2022 h8 | 2023 h8 | 2024 h8 |
|---|---|---|---|---|---|---|---|---|---|---|
| R0 | 0,85 | 0,94 | 0,71 | 0,90 | 1,00 | 0,88 | 0,98 | 0,73 | 0,83 | 1,00 |
| R1 | 0,83 | 0,75 | 0,52 | 0,85 | 0,88 | 0,87 | 0,77 | 0,56 | 0,87 | 0,88 |
| R2 | 0,85 | 0,98 | 0,83 | 0,90 | 1,00 | 0,85 | 1,00 | 0,83 | 0,87 | 1,00 |
| R3 | 0,85 | 0,94 | 0,75 | 0,90 | 1,00 | 0,87 | 0,98 | 0,77 | 0,83 | 1,00 |

Sensibilidades (WIS; skill contra R0; cobertura 50 %; cobertura 95 %) a h = 4 y h = 8:

| capa | h = 4 | h = 8 |
|---|---|---|
| R3 γ = 0,01 | 61,8; −0,09; 0,62; 0,89 | 83,1; −0,06; 0,63; 0,88 |
| R3 γ = 0,10 | 63,7; −0,13; 0,63; 0,88 | 85,6; −0,09; 0,63; 0,86 |
| S1 K = 4, β = 1 | 79,5; −0,40; 0,47; 0,88 | 134,9; −0,71; 0,52; 0,91 |
| S1 K = 13, β = 1 | 79,7; −0,41; 0,48; 0,89 | 121,3; −0,54; 0,44; 0,91 |
| S1 K = 8, β = 0,5 | 60,3; −0,07; 0,54; 0,90 | 87,1; −0,10; 0,54; 0,91 |

Veredicto de la pregunta A en la fase A:

- R1 no pasa: la cobertura del 95 % cae a 0,77 y 0,79. Con 52 pares, el nivel `1 − α/2` por
  lado winsorizado al p90 produce factores menores que el simétrico; los intervalos se
  estrechan en vez de ensancharse.
- R2 pasa las tres condiciones a h = 4 y a h = 8: cobertura del 95 % 0,91 y 0,91, del 50 %
  0,54 y 0,56, WIS 54,9 (3 % menor que R0) y 80,9 (3 % mayor, dentro del 5 %). Es la capa
  elegida. Su efecto se concentra en 2022, el año que R0 cubre peor (0,71 y 0,73 pasan a 0,83).
- R3 no pasa: cuesta entre 8 % y 13 % de WIS en los horizontes decisivos y no lleva la
  cobertura del 95 % a la banda; sube la del 50 % a 0,64 y 0,65, por encima del nominal. Con
  γ = 0,01 y 0,10 pasa lo mismo.

Veredicto de la pregunta B en la fase A: S1 no pasa. Corregir la mediana con el sesgo de los
últimos 8 pares conocidos empeora el WIS en todos los horizontes (−0,14 a h = 1, −0,44 a
h = 4, −0,65 a h = 8). Los residuos de M0 a un horizonte dado en pares consecutivos están
correlacionados por la superposición de ventanas, pero el sesgo reciente no se mantiene las
h semanas siguientes; β = 0,5 reduce el daño sin convertirlo en ganancia.

### Fase B, tablero 2025-S1 a 2026-S37, contra la persistencia suavizada

Cifras de la repetición del 2026-10-03, con el ONI de 2025-2026 cargado (enmienda del
2026-10-03). M0 con R0 reproduce las 647 predicciones de `mejora_confirmacion.json` y C con R0
las 647 de 2025-2026 de `tendencia_verificacion.json`, las dos con diferencia 0.

Capas sobre C (WIS; skill contra C con R0; skill contra la referencia con 2025 y 2026 entre
paréntesis; cobertura 50 %; cobertura 95 % con 2025 y 2026 entre paréntesis; fracción bajo la
mediana; n = 80 u 81). Se añaden M0 solo (R0) y T solo como contexto.

| h | C con R0 | C con R2 (elegida) | C con R3 | R4: C calibrada | C con S1 | C con C1 | M0 solo | T solo |
|---|---|---|---|---|---|---|---|---|
| 1 | 5,9; 0,00; −0,04 (−0,07, −0,01); 0,55; 0,94 (0,92, 0,96); 0,62 | 6,0; −0,02; −0,06 (−0,03, −0,10); 0,59; 0,95 (0,96, 0,93); 0,60 | 6,2; −0,05; −0,09 (−0,12, −0,07); 0,64; 0,95 (0,94, 0,96); 0,62 | 6,0; −0,02; −0,06 (−0,08, −0,03); 0,41; 0,82 (0,81, 0,86); 0,62 | 6,1; −0,04; −0,08 (−0,07, −0,08); 0,64; 0,91 (0,94, 0,86); 0,50 | 4,7; +0,20; +0,17 (+0,13, +0,21); 0,55; 0,91 (0,90, 0,93); 0,36 | 10,1; −0,71; −0,78 (−0,88, −0,68); 0,40; 0,81 (0,79, 0,86); 0,71 | 4,7; +0,20; +0,17 (+0,17, +0,17); 0,44; 0,86 (0,89, 0,82); 0,36 |
| 2 | 11,2; 0,00; +0,09 (+0,03, +0,13); 0,53; 0,89 (0,90, 0,86); 0,63 | 11,4; −0,02; +0,07 (+0,04, +0,09); 0,52; 0,91 (0,96, 0,83); 0,63 | 11,8; −0,05; +0,04 (−0,00, +0,07); 0,64; 0,91 (0,94, 0,86); 0,63 | 11,5; −0,03; +0,06 (−0,03, +0,13); 0,40; 0,79 (0,77, 0,83); 0,63 | 12,1; −0,08; +0,02 (−0,02, +0,04); 0,54; 0,93 (0,94, 0,90); 0,51 | 10,3; +0,08; +0,17 (+0,18, +0,15); 0,53; 0,90 (0,92, 0,86); 0,43 | 16,4; −0,46; −0,33 (−0,59, −0,15); 0,36; 0,75 (0,73, 0,79); 0,73 | 10,4; +0,07; +0,16 (+0,21, +0,12); 0,49; 0,85 (0,92, 0,72); 0,37 |
| 3 | 15,9; 0,00; +0,11 (+0,08, +0,14); 0,46; 0,89 (0,92, 0,83); 0,59 | 16,0; −0,00; +0,11 (+0,09, +0,12); 0,49; 0,91 (0,96, 0,83); 0,59 | 16,1; −0,01; +0,10 (+0,08, +0,12); 0,57; 0,90 (0,94, 0,83); 0,59 | 16,6; −0,04; +0,07 (+0,00, +0,12); 0,36; 0,77 (0,75, 0,79); 0,59 | 18,8; −0,18; −0,05 (+0,00, −0,08); 0,41; 0,86 (0,92, 0,76); 0,53 | 16,1; −0,01; +0,10 (+0,19, +0,05); 0,47; 0,88 (0,94, 0,76); 0,42 | 22,1; −0,39; −0,23 (−0,45, −0,09); 0,26; 0,72 (0,73, 0,69); 0,75 | 15,5; +0,03; +0,14 (+0,20, +0,09); 0,44; 0,84 (0,94, 0,66); 0,37 |
| 4 | 19,1; 0,00; +0,15 (+0,13, +0,16); 0,41; 0,91 (0,98, 0,79); 0,60 | 19,7; −0,03; +0,12 (+0,12, +0,12); 0,38; 0,91 (1,00, 0,76); 0,60 | 19,5; −0,02; +0,13 (+0,08, +0,16); 0,53; 0,91 (0,98, 0,79); 0,60 | 19,8; −0,04; +0,11 (+0,07, +0,15); 0,33; 0,69 (0,65, 0,76); 0,60 | 25,7; −0,34; −0,15 (−0,00, −0,26); 0,32; 0,83 (0,96, 0,59); 0,53 | 20,2; −0,06; +0,10 (+0,19, +0,03); 0,47; 0,86 (0,98, 0,66); 0,47 | 25,6; −0,34; −0,14 (−0,33, −0,01); 0,32; 0,73 (0,73, 0,72); 0,73 | 19,5; −0,02; +0,13 (+0,19, +0,08); 0,46; 0,85 (0,98, 0,62); 0,44 |
| 5 | 21,7; 0,00; +0,16 (+0,15, +0,17); 0,42; 0,90 (0,98, 0,76); 0,59 | 22,9; −0,05; +0,12 (+0,13, +0,11); 0,37; 0,90 (1,00, 0,72); 0,62 | 21,3; +0,02; +0,18 (+0,17, +0,18); 0,48; 0,91 (1,00, 0,76); 0,59 | 23,1; −0,07; +0,11 (+0,05, +0,15); 0,35; 0,67 (0,65, 0,69); 0,59 | 30,8; −0,42; −0,19 (−0,00, −0,34); 0,28; 0,80 (0,98, 0,48); 0,58 | 23,7; −0,09; +0,09 (+0,18, +0,01); 0,41; 0,88 (1,00, 0,66); 0,54 | 28,1; −0,29; −0,09 (−0,21, +0,01); 0,30; 0,69 (0,69, 0,69); 0,69 | 22,8; −0,05; +0,12 (+0,17, +0,08); 0,47; 0,90 (1,00, 0,72); 0,46 |
| 6 | 23,9; 0,00; +0,17 (+0,20, +0,14); 0,40; 0,91 (0,98, 0,79); 0,60 | 25,2; −0,05; +0,13 (+0,17, +0,09); 0,36; 0,88 (0,98, 0,69); 0,62 | 23,3; +0,03; +0,19 (+0,22, +0,17); 0,44; 0,94 (0,98, 0,86); 0,60 | 25,4; −0,06; +0,12 (+0,11, +0,12); 0,37; 0,67 (0,65, 0,69); 0,60 | 36,3; −0,52; −0,26 (+0,01, −0,50); 0,28; 0,77 (0,94, 0,45); 0,51 | 27,8; −0,16; +0,03 (+0,15, −0,07); 0,31; 0,83 (0,98, 0,55); 0,59 | 29,0; −0,21; −0,01 (−0,06, +0,04); 0,28; 0,69 (0,71, 0,66); 0,65 | 26,0; −0,09; +0,10 (+0,14, +0,06); 0,44; 0,90 (1,00, 0,72); 0,49 |
| 7 | 26,4; 0,00; +0,17 (+0,22, +0,11); 0,40; 0,91 (0,96, 0,83); 0,57 | 28,4; −0,07; +0,11 (+0,15, +0,06); 0,36; 0,90 (0,96, 0,79); 0,62 | 26,0; +0,02; +0,18 (+0,22, +0,14); 0,43; 0,94 (1,00, 0,83); 0,57 | 27,5; −0,04; +0,13 (+0,17, +0,10); 0,32; 0,69 (0,69, 0,69); 0,57 | 42,1; −0,59; −0,33 (−0,01, −0,63); 0,22; 0,72 (0,90, 0,38); 0,48 | 29,3; −0,11; +0,08 (+0,15, +0,00); 0,31; 0,79 (0,85, 0,69); 0,63 | 30,6; −0,16; +0,04 (+0,05, +0,02); 0,33; 0,73 (0,73, 0,72); 0,67 | 29,3; −0,11; +0,08 (+0,13, +0,03); 0,46; 0,86 (0,98, 0,66); 0,49 |
| 8 | 28,6; 0,00; +0,16 (+0,23, +0,09); 0,35; 0,90 (0,96, 0,79); 0,56 | 30,5; −0,07; +0,10 (+0,17, +0,04); 0,37; 0,85 (0,92, 0,72); 0,62 | 28,0; +0,02; +0,18 (+0,22, +0,13); 0,47; 0,96 (1,00, 0,90); 0,56 | 30,2; −0,06; +0,11 (+0,16, +0,06); 0,31; 0,65 (0,64, 0,69); 0,56 | 47,1; −0,65; −0,39 (−0,00, −0,78); 0,25; 0,75 (0,94, 0,41); 0,47 | 31,4; −0,10; +0,08 (+0,15, +0,00); 0,15; 0,78 (0,79, 0,76); 0,68 | 31,5; −0,10; +0,07 (+0,11, +0,04); 0,22; 0,69 (0,65, 0,76); 0,67 | 32,1; −0,12; +0,06 (+0,10, +0,01); 0,51; 0,88 (1,00, 0,66); 0,47 |

WIS de la persistencia suavizada por horizonte: 5,7; 12,3; 17,9; 22,4; 25,9; 28,8; 31,7; 34,0.
C con R1 y las sensibilidades están en el JSON; lo relevante de ellas: C con C1 y K = 52 da
+0,20, +0,09, +0,03, −0,02, −0,01 contra C con R0 a h = 1, 2, 3, 4 y 8 (cobertura del 95 %
0,91, 0,89, 0,91, 0,90, 0,84), y C con S1 y β = 0,5 queda entre −0,28 y +0,03.

Peso de M0 que elige C1 (fracción de orígenes de 2025-2026): a h = 1, 0 en el 46 %, 0,25 en el 54 %; a h = 4,
0 en el 28 %, 0,25 en el 59 %, 0,50 en el 11 %, 0,75 en el 1 %; a h = 8, 0,50 en el 22 %, 0,75 en el 33 %, 1 en el 44 %. El desempeño reciente pide menos M0 a corto plazo
y más a largo, en línea con lo que M0 y T hacen por separado.

Veredictos de la fase B:

- C con R2 (la capa elegida en la fase A) no cumple: la cobertura del 95 % en 2026 queda en
  0,76 a h = 4 y 0,72 a h = 8 (R0: 0,79 y 0,79), y a h = 8 el WIS sube
  7 %. Más pares de calibración no corrigen 2026, porque los fallos de 2026 no
  son de ancho sino de posición (ver `analisis-cobertura-2026.md`).
- R4 (calibrar la mezcla C) no cumple: la cobertura del 95 % baja a 0,69 y 0,65. Los errores
  de C en los 52 pares de calibración de 2025 son pequeños (serie suavizada, año tranquilo) y
  el factor conformal estrecha los intervalos justo antes de 2026.
- C con C1 no cumple: gana a 1 y 2 semanas (WIS 4,7 contra 5,9 y 10,3 contra 11,2), empata a
  3 y empeora a 4 (−0,06) y a 8 (−0,10, con cobertura 0,78). Con K = 52 el peso cambia más
  despacio y cumpliría todas las condiciones salvo la cobertura del 95 % a h = 8 (0,84), pero
  es una sensibilidad y no un candidato.
- C con S1 (informativo, no pasó la fase A): empeora en todos los horizontes salvo h = 2.

### Veredicto

- Pregunta A: en la validación de OpenDengue, calibrar con 104 pares en vez de 52 (R2) lleva
  la cobertura del 95 % de 0,88 a 0,91 en los dos horizontes decisivos, con la del 50 % en
  0,54 a 0,56, y no cuesta WIS a h = 4 (lo baja 3 %) ni más del 3 % a h = 8. En la serie del
  tablero no corrige la cobertura de 2026, que es el caso que motivó la pregunta. Resultado:
  positivo para el tramo de OpenDengue (candidato a reemplazar N_CAL = 52 por 104 en la base
  de M0, con su propia firma), negativo para C en 2025-2026. Las capas asimétrica, adaptativa
  y sobre la mezcla no pasan.
- Pregunta B: negativa. La corrección del sesgo reciente empeora en las dos series. El peso
  por desempeño reciente mejora a 1 y 2 semanas y empeora a 4 y 8 en el tablero; con una
  ventana larga (52) gana a 1, 2 y 3 semanas (+0,20, +0,09 y +0,03 contra C), queda a menos de
  2 % de C a 4 y 8, y solo incumple la cobertura del 95 % a 8 semanas (0,84 contra 0,85). Es una
  sensibilidad sobre años que sirvieron para elegir C, no un candidato. A 1 semana, T sola
  (WIS 4,7) y C con C1 (4,7) son mejores que C (5,9) y que la persistencia suavizada (5,7),
  lo que indica que el peso 0,5 de M0 es alto para h = 1 y 2 en esta serie; decidir un peso
  por horizonte requiere otra firma y semanas posteriores a ella.

### Limitaciones

- 2025 y 2026 sirvieron para elegir C; cualquier capa sobre C evaluada ahí es, como mínimo,
  parcialmente dentro de muestra. La cobertura de 2026 se mide sobre 29 semanas objetivo.
- Las capas R3, S1 y C1 dependen de pares recientes; en la validación de OpenDengue las
  cadenas solo contienen pares con objetivo en los años de validación, de modo que al inicio
  de 2021 esas capas parten sin historia reciente (enmienda 1).
- La fase B se repitió con el ONI de 2025-2026 (enmienda del 2026-10-03); sus predicciones
  coinciden con las publicadas. El bloque `desempeno` del artefacto servido usa 77 semanas
  objetivo desde 2025-01-26 y aquí son 81 desde 2025-S1, por eso sus cifras agregadas difieren.
- 4 capas de calibración, 2 de corto plazo y 7 sensibilidades sobre los mismos años: el
  resultado positivo de R2 en la validación se obtuvo con 3 candidatos; su confirmación
  requiere semanas no vistas.
