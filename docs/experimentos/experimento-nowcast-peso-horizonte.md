# Experimento: peso de M0 por horizonte en la mezcla C (2026-10-03)

> Protocolo fijado el 2026-10-03, antes de escribir y de correr el script, en la rama
> `feat/mejora-tablero-ch`, que sale de `feat/mejora-tablero-banda-alta`. Es la Fase 2 (línea D, C_h)
> del plan de mejora del predictor para la serie del tablero. No toca la prueba prospectiva firmada
> en `experimento-nowcast-tendencia.md` (script congelado en 40b6ebb, semanas objetivo desde
> 2026-S38). Ninguna decisión de este documento usa una semana objetivo posterior a 2026-S37. No
> modifica `nowcast_estimacion_dengue.py` ni los artefactos publicados.

## Pregunta

C mezcla M0 y T cuantil a cuantil en escala log1p con el mismo peso, 0,5, en los ocho horizontes.
Hay indicios de que el peso conviene distinto según el horizonte: a 1 y 2 semanas T sola rinde
mejor que C. Tres preguntas:

1. Elegido con la historia y no con 2025 a 2026, ¿cambia el peso de M0 por tramo de horizonte?
2. ¿Ese peso se confirma en 2024 y en el tablero?
3. Si el peso baja y los intervalos pierden cobertura, ¿se puede separar el centro del ancho?

## Exploración previa, declarada

- En `experimento-nowcast-rangos.md` (parte B) se publicó, para 2025 a 2026-S37, el WIS por horizonte
  de C, de T sola y de M0 sola. T sola: 4,7; 10,4; 15,5; 19,5; 22,8; 26,0; 29,3; 32,1 (h = 1 a 8). C:
  5,9; 11,2; 15,9; 19,1; 21,7; 23,9; 26,4; 28,6. M0 sola: 10,1; 16,4; 22,1; 25,6; 28,1; 29,0; 30,6; 31,5.
  La cobertura al 95 % de T sola va de 0,84 a 0,90 y la de C de 0,89 a 0,94. Esa es la pista que motiva
  este experimento, y la razón de que 2025 a 2026-S37 ya no sea una ventana limpia para C_h.
- Se probó antes un peso por desempeño reciente (C1, `experimento-nowcast-rangos.md`), que se
  descartó. C_h es otra cosa: pesos fijos por tramo, elegidos con la historia.
- Antes de este protocolo se leyó el código de la Fase 1 y la estructura de `rangos.json`, y no se
  calculó ninguna métrica de esta fase.
- No se añaden pruebas después de ver los resultados. Lo que se mire después se rotula
  exploratorio.

## Datos

- Serie mixta nacional (`cargar_serie_mixta`) con la historia suavizada de k = 7 hasta 2023
  (`historia`). T es la vigente, φ = 0,8, v = 3, k = 7, con los errores de la propia historia
  (`Reglas`). La referencia es la persistencia suavizada con v = 3.
- Cuantiles de M0 (`q_R0`, ya calibrado con CQR-r) guardados en `rangos.json`: bloques `A_h1` a
  `A_h8` para los objetivos de 2019, 2021, 2022 y 2023, y `B_h1` a `B_h8` para 2024 y para 2025 a
  2026-S37. M0 no se reentrena. C_w es la mezcla `_mezcla(q_M0, q_T, w)` con w el peso de M0; w = 1
  deja M0 sola y w = 0 deja T sola.
- Validación: objetivos de 2019, 2021, 2022 y 2023 (2018 no tiene M0 y 2020 se excluye, como en todo
  el proyecto), con el objetivo en la historia suavizada, igual que la validación de T en la Fase 1.
  Sesgo conocido: M0 se entrenó y se calibró contra objetivos crudos y con rezagos crudos, de modo que
  frente a un objetivo suavizado sus intervalos resultan anchos, y ese ancho se hereda en C. Eso sesga
  la validación hacia pesos menores de M0. Por eso un cambio exige que también lo respalden 2024 y
  2025 a 2026-S37, donde la serie ya viene suavizada.
- H1: objetivos de 2024 (OpenDengue ya suavizado por MINSAL). H2: objetivos de 2025 a 2026-S37
  (tablero), rotulada dentro de muestra.

Controles antes de cualquier barrido: con w = 0,5, el código nuevo debe reproducir `q_T` y `q_C_R0` de
`rangos.json` en H1 y H2 con las tolerancias de la Fase 1 (T: 0,0005; C: 0,003; WIS de la referencia:
0,0005). Además, w = 1 devuelve M0 y w = 0 devuelve T.

## Candidatos

Rejilla de pesos: w en {0; 0,25; 0,5; 0,75; 1}. Tramos de horizonte, los de la Fase 1: h = 1 a 2,
3 a 4 y 5 a 8. Cada tramo elige su peso por separado, sin restricción de monotonía. El punto de
comparación es la vigente, w = 0,5.

Puntaje de un peso en un tramo: promedio sobre los horizontes del tramo y sobre los cuatro años de
validación de 1 − WIS(C_w) / WIS(referencia), con el WIS promediado dentro de cada año para que los
años de brote grande no manden.

Admisible: el peso cuya cobertura al 95 % en la validación (agrupando los horizontes del tramo y los
cuatro años) no queda más de 0,03 por debajo de la de w = 0,5. De los admisibles gana el de mayor
puntaje.

## Regla de cambio

La carga de la prueba está en el cambio. Para un tramo, el mejor peso admisible sustituye a 0,5 solo
si, en la validación, supera a 0,5 en al menos 0,005 de puntaje promedio y lo supera en al menos 3 de
los 4 años. Si no, el tramo se queda en 0,5 y el resultado es que el peso está en la meseta.

Confirmación, solo para los tramos que pasen la regla de cambio. El peso nuevo queda como candidato
para la siguiente fase solo si se cumple todo:

- (a) la regla de cambio en la validación;
- (b) en H1 y en H2, el promedio sobre los horizontes del tramo de WIS(C_w') / WIS(C_0,5) es menor que
  1, y en H2 es menor o igual a 0,99;
- (c) la cobertura al 95 % de C_w' en H2, agrupando los horizontes del tramo, no baja más de 0,03
  respecto a C_0,5.

Se reporta además, como descripción, el WIS por horizonte de C_w', de C_0,5, de T sola y de M0 sola, el
skill contra la referencia, la cobertura al 50 % y al 95 %, el resultado de aplicar los tres pesos
elegidos a la vez (C_h completo) y una prueba de Diebold-Mariano por horizonte con varianza de largo
plazo de Newey-West (rezagos h − 1) y corrección de Harvey-Leybourne-Newbold. La prueba no decide
nada: con unas 80 semanas autocorrelacionadas solo mide la incertidumbre.

## Extensión E1, condicionada

La cobertura puede ser la razón por la que un peso bajo no pase. Si en un tramo el mejor peso sin la
restricción de admisibilidad supera la regla de cambio en puntaje y años pero es inadmisible por
cobertura, se corre esta extensión solo para ese tramo: el centro (la mediana de la mezcla) usa ese
peso y el ancho (las desviaciones de cada cuantil respecto a la mediana, en log1p) usa w = 0,5. Con
el mismo peso en las dos partes se recupera la mezcla simple. La extensión se evalúa con la misma regla
de cambio y la misma confirmación. Si ningún tramo cumple la condición, no se corre.

## Qué se decide y qué no

Se decide si hay un C_h candidato para la Fase 4, que lo registraría como predicción paralela firmada
antes de la ventana prospectiva, y con qué pesos. No se cambia la web, el backend ni C. Un resultado
dentro de muestra no demuestra mejora; solo la ventana prospectiva puede hacerlo.

## Salidas

- Script `backend/ingestion/experimento_nowcast_peso_horizonte.py` con `--control`, `--validacion`,
  `--confirmacion` y `--extension-e1`.
- `docs/agentes/mejora-predictor/resultados-nuevos/peso_m0_por_horizonte.json`.
- Sección de resultados en este documento.

## Resultados (2026-10-03)

Script commiteado antes de correr (c7bd85e). Controles: `q_T` y `q_C_R0` guardados se reproducen en H1
y H2 (diferencias máximas 0,0005 en T y 0,0026 en C, dentro de las tolerancias de la Fase 1); w = 1
devuelve M0 y w = 0 devuelve T con diferencia menor que 1e-11; la variante de centro y ancho con
pesos iguales reproduce la mezcla simple. Las 9 pruebas unitarias pasan. Pares origen-horizonte de
la validación: 416 (2019), 380 (2021), 416 (2022) y 416 (2023).

### Validación: 2019, 2021, 2022 y 2023, objetivo en la historia suavizada

Puntaje (skill medio contra la persistencia suavizada) y, entre paréntesis, cobertura al 95 %:

| peso de M0 | h = 1 a 2 | h = 3 a 4 | h = 5 a 8 |
|---|---|---|---|
| 0 (T sola) | +0,297 (0,969) | +0,267 (0,971) | +0,149 (0,953) |
| 0,25 | +0,160 (0,998) | +0,299 (0,990) | +0,226 (0,973) |
| 0,5 (vigente) | −0,237 (0,993) | +0,209 (0,983) | +0,235 (0,981) |
| 0,75 | −0,727 (0,983) | +0,020 (0,978) | +0,186 (0,975) |
| 1 (M0 sola) | −1,266 (0,978) | −0,238 (0,958) | +0,075 (0,953) |

Regla de cambio: en h = 1 a 2 gana w = 0 (ganancia de +0,534 sobre 0,5, en los 4 años); en h = 3 a 4
gana w = 0,25 (+0,090, en los 4 años); en h = 5 a 8 el mejor es 0,5 y el tramo se queda. Los tres
pesos mejores eran admisibles por cobertura, de modo que la extensión E1 firmada no se corre. La
magnitud de las ganancias en h = 1 a 2 refleja el sesgo declarado (M0 crudo frente a un objetivo
suavizado): con 0,5 el skill es negativo, lo que no ocurre en el tablero. Por eso decide lo que sigue.

### Confirmación en 2024 (H1) y en 2025 a 2026-S37 (H2, dentro de muestra)

Razón de WIS del candidato contra C con peso 0,5 (promedio de los horizontes del tramo, por
horizonte entre paréntesis) y cobertura al 95 % agrupada:

| tramo | H1 razón | H2 razón | cobertura H1 | cobertura H2 | (b) | (c) | candidata |
|---|---|---|---|---|---|---|---|
| h = 1 a 2, w = 0 | 0,749 (0,664; 0,834) | 0,862 (0,800; 0,925) | 0,942 contra 1,000 | 0,857 contra 0,913 | sí | no (baja 0,056) | no |
| h = 3 a 4, w = 0,25 | 0,904 (0,913; 0,894) | 0,959 (0,943; 0,975) | 0,981 contra 1,000 | 0,907 contra 0,901 | sí | sí | sí |

Diebold-Mariano (candidato menos vigente, solo informativo): en h = 1 a 2 con w = 0, p de 0,00 y 0,07
en H1 y de 0,00 y 0,23 en H2; en h = 3 a 4 con w = 0,25, p de 0,05 y 0,07 en H1 y de 0,11 y 0,57 en H2.

### Decisión por la regla firmada

Hay un tramo candidato para la Fase 4: h = 3 a 4 con peso 0,25 de M0 en lugar de 0,5. La mejora en
H2, dentro de muestra, es de 2,5 % a 5,7 % de WIS. Los demás tramos quedan como están. El tramo
h = 1 a 2 con T sola gana mucho en WIS y en las dos ventanas, pero pierde cobertura en H2 (T sola
produce intervalos angostos), y la regla firmada exige no bajar más de 0,03.

### Exploratorio (después de ver la confirmación; no es la extensión firmada)

La condición firmada de la extensión E1 se miraba en la validación, y allí w = 0 era admisible, así que
no se corrió. La falla apareció en H2. Con la misma variante (centro de T, ancho de la mezcla simple)
aplicada igualmente a h = 1 a 2, rotulada como posterior:

- Validación: puntaje +0,016 contra −0,237 de C, cobertura 1,000.
- H1: razón 0,981 (h = 1: 0,930; h = 2: 1,031), cobertura 1,000 contra 1,000.
- H2: razón 0,884 (h = 1: 0,833; h = 2: 0,936), cobertura 0,932 contra 0,913. Cumple (b) y (c).
- C_h completo con esa variante en h = 1 a 2, w = 0,25 en h = 3 a 4 y 0,5 en h = 5 a 8: razón media
  de WIS de 0,971 en H1 y de 0,961 en H2, con cobertura 0,995 y 0,913 (C vigente 1,000 y 0,907). En H2
  el WIS pasa de 5,91 a 4,92 en h = 1, de 11,21 a 10,49 en h = 2, de 15,92 a 15,02 en h = 3 y de 19,09
  a 18,62 en h = 4; de h = 5 a 8 no cambia.

La ganancia con evidencia más sólida está en h = 1 (p menor que 0,01 en las dos ventanas); en h = 2 a 4
las diferencias son pequeñas y su incertidumbre grande.

### Qué sigue

C_h queda como candidato para la Fase 4: h = 3 a 4 con 0,25 (cumple la regla firmada) y h = 1 a 2 con
centro de T y ancho de la mezcla (variante exploratoria, elegida después de ver H2 y por eso más
débil). Ninguna de las dos demuestra mejora: H2 es dentro de muestra y fue la pista que originó el
experimento. Se firmarían como predicción paralela, con objetivos posteriores a la firma, para
compararlas con C en la ventana nueva. No se cambia la web ni el backend.
