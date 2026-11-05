# Experimento: elegir la tendencia con la historia suavizada y recortar el entrenamiento de M0 (2026-10-03)

> Protocolo fijado el 2026-10-03, antes de escribir y de correr el script, en la rama
> `feat/mejora-tablero-fase0`. Es la Fase 1 del plan de mejora del predictor para la serie del
> tablero. No toca la prueba prospectiva firmada en `experimento-nowcast-tendencia.md` (script
> congelado en 40b6ebb, semanas objetivo desde 2026-S38). Ninguna decisión de este documento usa
> una semana objetivo posterior a 2026-S37.

## Enmienda del mismo día, antes del barrido

Al correr solo los controles (no el barrido) se vio que `rangos.json` guarda los cuantiles y
los WIS redondeados a 3 decimales, de modo que "diferencia máxima de cero" no es alcanzable
con ese archivo. La diferencia máxima observada en T fue 0,0004999, la mitad del paso de
redondeo, y la historia de k = 7 coincide bit a bit con la del experimento firmado. El control
pasa a ser:

- T: diferencia máxima menor o igual a 0,0005 (la mitad del paso de redondeo).
- C: diferencia máxima menor o igual a 0,003. C mezcla el M0 guardado, ya redondeado, con T, y
  el redondeo del primero se amplifica hasta 5 veces en la mezcla de logaritmos.
- WIS de la referencia (persistencia suavizada) contra `wis_suavizada` guardado: diferencia
  menor o igual a 0,0005, un control más de que la referencia es la misma.

Es un cambio del criterio de un control, no del análisis; no se había calculado ninguna métrica
de selección. La parte C usa como control sin recorte la misma tolerancia de redondeo.

## Pregunta

La Fase 0 no pudo identificar el filtro con que MINSAL construye la serie del tablero
(`analisis-forma-serie-tablero.md`). Queda lo que sí se puede hacer sin conocerlo: tratar la
historia de OpenDengue anterior a 2024 con un promedio causal de k semanas, como ya hace la
tendencia amortiguada T para aprender sus errores. Tres preguntas:

1. Suavizar la historia, ¿ayuda de verdad a T? Se compara contra no suavizar y contra otros k.
2. Los parámetros de T (amortiguación y ventana de la pendiente) se fijaron en la exploración
   del 2026-09-27 mirando 2024 a 2026. Elegidos solo con la historia suavizada hasta 2023,
   ¿salen los mismos? ¿Rinden igual o mejor fuera de esa historia?
3. M0 se entrena con OpenDengue crudo hasta 2023 y con 2024, que ya viene suavizado. ¿Mejora
   al predecir 2025 y 2026 si el entrenamiento se corta en 2023?

## Exploración previa, declarada

- T usa K = 7, φ = 0,8 y pendiente de 3 semanas desde el experimento firmado el 2026-09-27, que
  se fijó después de mirar 2024 a 2026-S37 (la constante `EXPLORACION` del script). Por eso
  2024 a 2026-S37 no es una ventana limpia para T vigente.
- Antes de este protocolo se leyó la estructura de `rangos.json` (guarda, por origen y horizonte,
  los cuantiles de M0 y de C de 2024 a 2026-S37) pero no se calculó ninguna métrica de esta
  fase. Los criterios de abajo se fijan antes de calcular nada.
- No se añaden pruebas después de ver los resultados. Lo que se mire después se rotula
  exploratorio.

## Datos

- Serie mixta nacional: OpenDengue total hasta 2024 y tablero sospechoso desde 2025
  (`cargar_serie_mixta`). Semanas sin dato, como 2025-S53, quedan como NaN y los orígenes que
  las necesitan se descartan.
- Historia suavizada con k: desde el inicio de la serie hasta 2023, cada semana pasa a ser el
  promedio de las k semanas que terminan en ella, contando los 0 como dato. De 2024 en adelante
  no se toca. Con k = 1 es la serie cruda.
- Cuantiles de M0, T y C de 2024 a 2026-S37: `docs/agentes/mejora-predictor/resultados-nuevos/rangos.json`,
  bloques `B_h1` a `B_h8` (`q_R0` es M0 publicado, `q_T`, `q_C_R0`). M0 no se reentrena salvo
  en la parte C.

## Regla T parametrizada

Mediana: z(o) + (z(o) − z(o − v)) / v · (φ + φ² + … + φ^h), con z = log1p(casos). Cuantiles:
mediana más los 23 cuantiles de los errores de los pares (t, t + h) cuyo objetivo cae antes del
origen, de 2014 en adelante y sin 2020. Vigente: φ = 0,8, v = 3, k = 7. La referencia es la
persistencia suavizada con v = 3 y el mismo k, igual que en el experimento firmado.

Controles antes de cualquier barrido: con (0,8; 3; 7) el código nuevo debe reproducir `q_T` de
`rangos.json` y, mezclado al 50 % con `q_R0`, `q_C_R0`, con diferencia máxima de cero en las
filas que existan en ambos.

## A. Elegir la tendencia con la historia hasta 2023

Validación: objetivos de 2018, 2019, 2021, 2022 y 2023 (2020 se excluye como en todo el
proyecto), con la historia suavizada con k = 7. Los errores para los cuantiles salen de 2014 en
adelante y de antes del origen, así que 2018 ya tiene cuatro años de errores.

Rejilla: φ en {0,5; 0,6; 0,7; 0,8; 0,9; 1,0} y v en {2, 3, 4, 5, 6}. Son 30 configuraciones.

Puntaje de una configuración en un horizonte h: promedio sobre los cinco años de
1 − WIS(T) / WIS(referencia), con el WIS promediado dentro de cada año. Se promedia por año y
no sobre todas las semanas para que los años de brote grande no manden.

Tres tipos de elección, todas con la validación y con las mismas semanas para todas las
configuraciones:

- Común: una sola (φ, v) para los ocho horizontes, la de mayor puntaje promedio sobre h = 1 a 8.
- Por tramo: una (φ, v) para h = 1 a 2, otra para 3 a 4 y otra para 5 a 8. Es exploratoria:
  triplica los grados de libertad con unas 90 semanas de tablero para confirmar.
- Vigente: (0,8; 3), el punto de comparación.

Regla de cambio, fijada ahora. La carga de la prueba está en el cambio: la mejor configuración
sustituye a la vigente solo si, en la validación, supera a la vigente en al menos 0,005 de
puntaje promedio y la supera en al menos 3 de los 5 años. Si no, T vigente se queda y el
resultado es que está en la meseta. Para un tramo, lo mismo con el puntaje promedio de sus
horizontes.

Confirmación fuera de la selección, solo para lo que pase la regla de cambio:

- H1: objetivos de 2024 (OpenDengue ya suavizado por MINSAL).
- H2: objetivos de 2025 a 2026-S37 (tablero). Rotulada dentro de muestra, porque T vigente se
  fijó mirándola.

La configuración nueva T' queda como candidata para la siguiente fase solo si se cumple todo:

- (a) la regla de cambio en la validación;
- (b) en H1 y en H2, el promedio sobre los horizontes de WIS(T') / WIS(T vigente) es menor que 1;
- (c) la cobertura al 95 % de T' en H2, agrupando horizontes, no baja más de 0,03 respecto a T
  vigente.

Se reporta además, como descripción, el WIS de C' (50 % M0 y 50 % T') contra C, y una prueba de
Diebold-Mariano por horizonte con varianza de largo plazo de Newey-West (rezagos h − 1) y
corrección de Harvey-Leybourne-Newbold. La prueba no decide nada: con unas 80 semanas
autocorrelacionadas solo sirve para saber qué tan grande es la incertidumbre.

## B. Sensibilidad al k del suavizado

k en {1, 3, 5, 6, 7, 8, 9, 12} con T vigente (y con T' si existe). k = 1 es no suavizar la
historia, la respuesta directa a la pregunta de la parte 1.

- En H1 y en H2 el objetivo no depende de k (solo cambian los errores que aprende T y, en 2024,
  algunos rezagos), así que el WIS es comparable entre k. Se reporta WIS, cobertura al 50 % y al
  95 % y skill contra la referencia oficial (persistencia suavizada con k = 7).
- En la validación el objetivo sí cambia con k, de modo que solo se reporta el skill contra la
  referencia del mismo k, y no se compara el WIS entre k.

No se elige k en esta fase. Regla de lectura fijada ahora: si el WIS agrupado en H2 de k = 6, 7 y
8 difiere menos de 3 %, la ambigüedad sobre el filtro no importa para T y K = 7 se queda. Si
k = 1 queda a menos de 3 % de k = 7 en H1 y en H2, suavizar la historia no aporta a T y se dice
así.

## C. M0 entrenado solo hasta 2023

M0 se reajusta cada dos semanas con ventana expansiva, de modo que al predecir 2025 y 2026 ya
entrena con 2024 (suavizado por MINSAL) y con el tablero. Variante M0_corte: los pares de
entrenamiento y de calibración quedan limitados a objetivos de 2023 o antes. Como ya no entra
ningún par nuevo, basta un ajuste por horizonte, hecho en el primer origen de H2. Recorta dos
cosas a la vez, el ajuste y la calibración CQR-r (los 104 pares más recientes), y no se pueden
separar.

- Solo H2, rotulada dentro de muestra.
- Controles: con corte en un año posterior al final de la serie y cadencia estándar, M0 debe
  reproducir `q_R0` guardado en 3 orígenes por horizonte con diferencia máxima de cero; la
  comprobación de ausencia de fuga del proyecto se corre sobre la serie y los orígenes usados.
- Lectura fijada ahora: el corte es ventaja solo si el WIS de M0_corte es menor que el de M0 en
  al menos 6 de los 8 horizontes y el promedio de WIS(M0_corte) / WIS(M0) es menor que 0,98. Si
  no, M0 se queda como está. Se reporta también C con M0_corte.

## Grados de libertad del analista

- Rejilla de 30 configuraciones para la elección común y para cada tramo (hasta 4 elecciones).
- 8 valores de k, descriptivos.
- 1 variante de M0.
- Cuatro conjuntos de semanas (validación, H1, H2, y la mezcla con C) y 8 horizontes. Con tan
  pocas semanas de tablero una diferencia pequeña no es evidencia. La estructura de elegir con
  la validación y confirmar fuera acota el exceso de optimismo de la rejilla, pero no lo
  elimina.

## Extensión E1, firmada después de ver la validación y la confirmación de (0,8; 2)

Las partes A y B ya se corrieron. La validación eligió (0,8; 2) para la elección común y para
los tres tramos, y esa elección está en el borde de la rejilla en v: v = 2 es el valor más
chico probado, y a φ fijo el puntaje sube al achicar v. Con el óptimo en el borde no se puede
decir que la rejilla lo contenga. Se añade una sola columna, v = 1 (la pendiente es el último
cambio semanal), con los mismos seis valores de φ. No se añade nada más a la rejilla.

Esto se fija después de haber visto la validación completa y la confirmación de (0,8; 2) en H1
y en H2, de modo que la regla es más estricta y H1 y H2 dejan de ser un conjunto virgen para
cualquier candidata de esta extensión:

- La mejor de las seis nuevas sustituye a (0,8; 2) solo si la supera en al menos 0,005 de
  puntaje promedio de validación (los ocho horizontes) y en al menos 3 de los 5 años. Si no, E1
  termina y (0,8; 2) queda como la mejor de la rejilla ampliada.
- Si la sustituye, se confirma con los criterios (b) y (c) de arriba, y además con la razón de
  WIS frente a (0,8; 2) menor que 1 en H1 y en H2.
- Cualquiera que sea el resultado, la adopción de una configuración nueva en el predictor
  exige la ventana prospectiva nueva de la Fase 4: elegir y confirmar con 2018 a 2026-S37 no
  alcanza, porque (0,8; 3) se eligió mirando 2024 a 2026-S37 y la rejilla ya se amplió una vez
  tras ver resultados.

## Lo que sigue a este experimento

- Si T' pasa la regla, se firma como candidata para una ventana prospectiva nueva (Fase 4), con
  semanas objetivo posteriores a la firma. No sustituye a C en la prueba prospectiva ya
  congelada, que se evalúa una sola vez con el script de 40b6ebb.
- Si no pasa, T vigente queda como línea de base de las fases siguientes (modelos nuevos para la
  serie suavizada).

## Resultados

Script: `backend/ingestion/experimento_nowcast_tendencia_seleccion.py`, modos `--tendencia`,
`--m0-corte` y `--extension-v1`. Salidas en `docs/agentes/mejora-predictor/resultados-nuevos/`:
`seleccion_tendencia.json`, `m0_corte_2023.json` y `seleccion_tendencia_v1.json`. Todo con
semanas objetivo hasta 2026-S37.

### Controles

Pasan los de la enmienda: la historia de k = 7 es idéntica a la del experimento firmado, la
diferencia máxima de T contra `rangos.json` es 0,0004999 y la de C 0,0026 en 1.063 filas, y el
WIS de la referencia difiere en menos de 0,0005 del guardado. Sin recorte y con la cadencia
estándar, M0 reproduce `q_R0` en un origen de cada uno de los 16 pares probados (el ajuste
coincide con la fase de reajuste en uno de los dos). La comprobación de ausencia de fuga del
proyecto pasa, con su control negativo.

### A. Elegir la tendencia con la historia hasta 2023

Puntaje de validación (skill medio contra la persistencia suavizada, 2018 a 2023 sin 2020, ocho
horizontes). Vigente (0,8; 3): +0,2258.

| φ \ v | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|
| 0,5 | +0,152 | +0,141 | +0,124 | +0,109 | +0,093 |
| 0,6 | +0,189 | +0,175 | +0,153 | +0,132 | +0,112 |
| 0,7 | +0,225 | +0,207 | +0,178 | +0,151 | +0,124 |
| 0,8 | +0,248 | +0,226 | +0,188 | +0,153 | +0,119 |
| 0,9 | +0,232 | +0,208 | +0,161 | +0,118 | +0,076 |
| 1,0 | +0,108 | +0,091 | +0,038 | −0,011 | −0,059 |

La elección común y las de los tres tramos (h 1 a 2, 3 a 4 y 5 a 8) dan la misma configuración,
(0,8; 2): ganancia de +0,022 sobre la vigente y mejor en 4 de los 5 años (2018: 0,282 contra
0,244; 2019: 0,340 contra 0,305; 2021: 0,193 contra 0,152; 2022: 0,386 contra 0,366; en 2023
pierde, 0,039 contra 0,063). La amortiguación φ = 0,8 es la mejor de su columna para v de 2 a 5; con v = 6 gana φ = 0,7.
No hay ganancia por horizonte: elegir por tramo no cambia nada.

La extensión E1 probó v = 1: el mejor es (0,8; 1) con +0,215, por debajo de (0,8; 2) con
+0,248 (ganancia −0,033, supera en 2 de 5 años). No sustituye. El óptimo de v es interior, en 2,
y el de φ también.

Confirmación de (0,8; 2) contra la vigente fuera de la selección, razón de WIS por horizonte:

| h | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | media |
|---|---|---|---|---|---|---|---|---|---|
| H1 (2024) | 0,913 | 0,963 | 0,984 | 0,990 | 0,970 | 0,976 | 0,976 | 0,981 | 0,969 |
| H2 (2025 a 2026-S37) | 0,984 | 1,001 | 1,005 | 1,010 | 1,005 | 0,991 | 0,998 | 0,992 | 0,998 |

- H1: mejor en los ocho horizontes. Solo h = 1 tiene Diebold-Mariano con p = 0,01; son 16
  pruebas por candidata, y con corrección por comparaciones múltiples ese p no se sostiene.
- H2: mejor en 4 horizontes de 8 y peor en los otros 4, con diferencias de 1 % o menos,
  salvo h = 1 (−1,6 %). Ningún p de Diebold-Mariano baja de 0,6. El skill agrupado es
  prácticamente igual (+0,183 contra +0,169 a 1 semana, +0,063 contra +0,056 a 8).
- Cobertura al 95 % agrupada: H1 0,959 contra 0,962; H2 0,867 contra 0,869.
- C con T' en lugar de T: razón media de WIS 0,979 en H1 y 0,995 en H2.

Por la regla firmada, (0,8; 2) es candidata (cumple a, b y c) en la elección común y en los
tramos h 1 a 2 y h 5 a 8; el tramo h 3 a 4 no lo es, porque en H2 su razón de WIS es 1,007. Las
tres coinciden en la misma configuración, así que en la práctica hay una sola candidata. Lectura
honesta: la regla se cumple por H1, donde la ganancia es de 3 %, y en la serie del tablero (H2)
T' y T vigente son indistinguibles. La mejora de la validación (+0,022 de skill) no se
trasladó al tablero.

### B. Sensibilidad al k del suavizado

T vigente con la historia suavizada con distintos k. La razón de WIS es el promedio sobre los
horizontes del WIS con ese k dividido por el de k = 7; skill y cobertura promedian los ocho
horizontes. El skill de H1 y H2 es contra la referencia oficial (k = 7).

| k | H1 razón | H1 cob. 95 | H2 razón | H2 cob. 50 | H2 cob. 95 | H2 skill |
|---|---|---|---|---|---|---|
| 1 | 71,3 | 0,94 | 15,8 | 0,70 | 0,995 | −13,3 |
| 3 | 1,295 | 0,98 | 1,023 | 0,60 | 0,946 | +0,097 |
| 5 | 1,074 | 0,96 | 0,999 | 0,52 | 0,915 | +0,118 |
| 6 | 1,026 | 0,97 | 0,999 | 0,48 | 0,896 | +0,118 |
| 7 | 1,000 | 0,96 | 1,000 | 0,46 | 0,869 | +0,117 |
| 8 | 0,993 | 0,95 | 1,002 | 0,45 | 0,847 | +0,115 |
| 9 | 0,992 | 0,95 | 1,006 | 0,43 | 0,835 | +0,113 |
| 12 | 0,991 | 0,93 | 1,020 | 0,38 | 0,799 | +0,100 |

- Suavizar la historia no es opcional para T. Con k = 1 (historia cruda) la mediana de 2025 y
  2026 es la misma, porque sus rezagos ya vienen del tablero, pero los errores que aprende T con
  la historia cruda son enormes y el WIS se multiplica por 16 (cobertura 0,995 por intervalos
  desmesurados). Con k = 3 ya es 2 % peor en H2 y 30 % peor en H1.
- Entre k = 5 y 9 el WIS en H2 se mueve menos de 1 %. Lectura firmada: k = 6, 7 y 8 difieren
  menos de 3 % en H2 (cumple), de modo que no conocer el k exacto no importa para el WIS de T.
  K = 7 se queda.
- Lo que sí cambia con k es el ancho: la cobertura al 95 % en H2 va de 0,915 (k = 5) a 0,835
  (k = 9), y la del 50 % de 0,52 a 0,43. Con K = 7 el 50 % queda en 0,46, bajo lo nominal. Es
  una observación dentro de muestra sobre el ancho, no una razón para cambiar K: en H1 los k
  chicos empeoran el WIS (k = 5: +7 %), y el ancho se trata en la Fase 3.
- En la validación el skill sube con k (0,14 con k = 5, 0,34 con k = 12) porque una serie más
  lisa es más fácil de extrapolar y el objetivo cambia con k; no es comparable entre filas.

### C. M0 entrenado solo hasta 2023 (H2, dentro de muestra)

| h | WIS de M0 | WIS con corte | razón | cob. 95 de M0 | cob. 95 con corte | razón de C |
|---|---|---|---|---|---|---|
| 1 | 10,12 | 10,27 | 1,014 | 0,81 | 0,99 | 1,070 |
| 2 | 16,37 | 16,36 | 1,000 | 0,75 | 0,96 | 1,021 |
| 3 | 22,14 | 21,14 | 0,955 | 0,72 | 0,95 | 0,990 |
| 4 | 25,60 | 25,52 | 0,997 | 0,73 | 0,93 | 1,020 |
| 5 | 28,13 | 29,77 | 1,058 | 0,69 | 0,91 | 1,039 |
| 6 | 29,00 | 30,09 | 1,038 | 0,69 | 0,89 | 1,022 |
| 7 | 30,61 | 34,08 | 1,113 | 0,73 | 0,86 | 1,063 |
| 8 | 31,46 | 35,28 | 1,121 | 0,69 | 0,86 | 1,057 |

El corte gana en 3 de 8 horizontes y la razón media de WIS es 1,037 (C: 1,035): no es ventaja,
y empeora justo a 5 a 8 semanas, que es donde M0 aporta. M0 se queda como está. El corte sí
ensancha los intervalos (cobertura al 95 % de 0,69 a 0,81 a 0,86 a 0,99), y la
calibración pasa a los 104 pares más recientes de 2022 y 2023, que son conteos crudos. Una
explicación posible es que esos datos tienen más dispersión relativa que los suavizados y la
calibración lo traslada al ancho; no se midió. De confirmarse, el ancho depende de la forma de
los datos con que se calibra, otra pista para la Fase 3. Como el corte cambia el ajuste y la calibración a la
vez, este resultado no separa cuál de las dos pierde el punto central.

### Qué se decide

- T vigente (0,8; 3; K = 7), C y M0 no cambian en el sitio ni en la prueba prospectiva
  congelada.
- (0,8; 2) queda como variante registrada para la ventana prospectiva de la Fase 4. Cumple la
  regla firmada, pero la evidencia en el tablero es nula; si hay que limitar candidatas por
  comparaciones múltiples, es la primera en salir.
- K = 7 se mantiene. La incertidumbre sobre el filtro de MINSAL no afecta el WIS de T en el
  rango de 5 a 9.
- El entrenamiento de M0 no se recorta.
- Lo que sale de la Fase 1 es que T y M0 están en una meseta: afinar sus parámetros, el k del
  suavizado o la ventana de entrenamiento no da ganancia comprobable en el tablero. Si hay mejora
  posible, estará en la estructura (Fase 2), en los saltos de fin de año (Fase 3) y en el ancho
  de los intervalos, que depende del k y de la ventana de calibración.

### Grados de libertad usados

30 configuraciones y 6 más de la extensión en la selección; 8 valores de k; una variante de
M0; 16 pruebas de Diebold-Mariano por candidata. La selección no usó H1 ni H2. Se miraron para
(0,8; 2), para el barrido de k con T vigente y para M0 con corte, y cada comparación se hizo una
vez.
