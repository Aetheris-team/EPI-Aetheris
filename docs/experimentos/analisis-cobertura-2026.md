# Análisis: dónde fallan los rangos de la predicción en 2026 (2026-10-03)

> Plan fijado el 2026-10-03, antes de calcular nada, en la rama `feat/mejora-predictor-agente`.
> Es un análisis descriptivo: no elige ni compara candidatos, no tiene criterio de éxito y no
> cambia el modelo. Responde a la revisión del PR the-monolith-project/EPI-Aetheris#167.

## Pregunta

En 2026, con la serie del tablero, la cobertura del 95 % de la predicción publicada (C) queda
en 0,79 a 4 y a 8 semanas, por debajo del 0,85 que exige la prueba prospectiva. ¿En qué semanas
objetivo cae fuera lo observado, por qué lado, y cuál de los dos componentes de C (M0 o la
tendencia amortiguada T) explica el desvío?

## Datos

Solo las predicciones ya guardadas en
`docs/agentes/mejora-predictor/resultados-nuevos/rangos.json` (fase B, capa R0, que es el
método publicado: C = mezcla 0,5 en log de M0 calibrado con CQR-r y T). No se corre ningún
modelo ni se consulta Postgres. Semanas objetivo de 2026-S1 a 2026-S37; las semanas 4 a 11 no
tienen predicción porque sus rezagos tocan el hueco de 2025-S53. Ninguna semana desde
2026-S38. 2025 se reporta al lado como comparación.

Esas predicciones se hicieron sin ONI de 2025-2026 en la base (enmienda 6 del experimento de
rangos) y difieren levemente del artefacto servido; el análisis describe esta corrida.

## Qué se calcula

Para cada horizonte h = 1 a 8 y cada semana objetivo de 2025 y 2026:

- si lo observado cae dentro del rango del 95 % y del 50 % de C, y por qué lado sale;
- el nivel del cuantil de C en que cae lo observado (interpolado entre los 23 cuantiles;
  0 o 1 si queda fuera de los extremos);
- el error de la mediana en escala `log1p` (mediana menos observado; positivo = predijo de más)
  para C, M0 y T.

Agrupado por tramo de semanas objetivo: S1 a S3 (cambio de año), S19 a S22, y el resto. Por
tramo se reporta n, cobertura del 95 % y del 50 %, fallos por arriba y por abajo, y el error
medio de la mediana de C, M0 y T. Además, la cobertura del 95 % de 2026 sin los dos tramos, como
medida de cuánto pesan.

Los tramos S1-S3 y S19-S22 los señaló el ADR 0020 al documentar la cobertura de 2026; no se
eligen mirando estos datos. No se añaden tramos después de ver los resultados.

## Reproducibilidad

Script `backend/ingestion/analisis_nowcast_cobertura_2026.py`, sin base de datos. Salida en
`docs/agentes/mejora-predictor/resultados-nuevos/cobertura_2026.json`.

## Enmienda (2026-10-03, antes de repetir)

Con el ONI de 2025-2026 cargado (`db/seed/seed_oni_2025_2026.sql`), el análisis se repite sobre
la nueva salida de `experimento_nowcast_rangos.py`, que reproduce exactamente las predicciones
publicadas. La primera versión de los resultados queda en el historial de git; la sección de
resultados se reemplaza.

## Resultados (2026-10-03, con el ONI de 2025-2026 cargado)

Salida de `analisis_nowcast_cobertura_2026.py` en
`docs/agentes/mejora-predictor/resultados-nuevos/cobertura_2026.json`. En 2026 hay 231
predicciones (28 o 29 por horizonte) y 40 quedan fuera del rango del 95 %.

### Cobertura del 95 % por tramo

Cobertura (n) y fallos por arriba / por abajo. "Arriba" significa que lo observado superó el
rango: la predicción quedó corta.

| h | 2026, todas | S1-S3 | S19-S22 | resto de 2026 | 2025, todas |
|---|---|---|---|---|---|
| 1 | 0,96 (28) 0/1 | sin predicción | 0,75 (4) 0/1 | 1,00 (24) | 0,92 (52) 1/3 |
| 2 | 0,86 (29) 1/3 | 0,00 (1) 1/0 | 0,25 (4) 0/3 | 1,00 (24) | 0,90 (52) 1/4 |
| 3 | 0,83 (29) 2/3 | 0,00 (2) 2/0 | 0,25 (4) 0/3 | 1,00 (23) | 0,92 (52) 2/2 |
| 4 | 0,79 (29) 3/3 | 0,00 (3) 3/0 | 0,25 (4) 0/3 | 1,00 (22) | 0,98 (52) 0/1 |
| 5 | 0,76 (29) 4/3 | 0,00 (3) 3/0 | 0,50 (4) 0/2 | 0,91 (22) 1/1 | 0,98 (52) 0/1 |
| 6 | 0,79 (29) 4/2 | 0,00 (3) 3/0 | 0,75 (4) 0/1 | 0,91 (22) 1/1 | 0,98 (52) 0/1 |
| 7 | 0,83 (29) 4/1 | 0,00 (3) 3/0 | 0,75 (4) 0/1 | 0,95 (22) 1/0 | 0,96 (52) 0/2 |
| 8 | 0,79 (29) 4/2 | 0,00 (3) 3/0 | 0,50 (4) 0/2 | 0,95 (22) 1/0 | 0,96 (52) 0/2 |

Los 40 fallos por semana objetivo (horizonte y lado):

| semana | fallos |
|---|---|
| S1 | h2 a h8, todos arriba |
| S2 | h3 a h8, arriba |
| S3 | h4 a h8, arriba |
| S4 | h5, arriba |
| S19 | h1, h2, h3, h7, h8, abajo |
| S20 | h2, h3, h4, h8, abajo |
| S21 | h2, h3, h4, h5, abajo |
| S22 | h4, h5, h6, abajo |
| S23 | h5, h6, abajo |
| S27, S28, S29 | h6, h7 y h8 respectivamente, arriba |

S1 a S4 y S19 a S23 suman 37 de los 40 fallos. Fuera de esos dos tramos la cobertura del 95 %
de 2026 es 1,00 a 1 a 4 semanas y entre 0,91 y 0,95 a 5 a 8.

### Qué pasa en esos tramos

Serie observada del tablero (sospechosos de dengue, `db/seed/seed_tablero_minsal.sql`):

| semana | 2025-S49 | S50 | S51 | S52 | 2026-S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|---|---|---|
| casos | 57 | 53 | 48 | 39 | 214 | 183 | 133 | 105 |

| semana | 2026-S16 | S17 | S18 | S19 | S20 | S21 | S22 | S23 |
|---|---|---|---|---|---|---|---|---|
| casos | 86 | 93 | 98 | 56 | 55 | 53 | 55 | 66 |

Son dos escalones de una semana a la otra: ×5,5 al cambiar de año y −43 % entre S18 y S19. En el
resto del año la serie cambia pocas unidades por semana. A 4 semanas, para 2026-S1 la predicción
fue una mediana de 55 con rango del 95 % de 5 a 110, y lo observado fue 214; para S20 a S22 la
mediana fue de 108 a 131, con el rango empezando en 72 a 79, y lo observado fue 53 a 55.

Error medio de la mediana en `log1p` (positivo = predijo de más), a h = 4 y h = 8:

| tramo | C | M0 | T |
|---|---|---|---|
| S1-S3, h = 4 | −1,22 | −0,93 | −1,52 |
| S1-S3, h = 8 | −1,04 | −0,71 | −1,37 |
| S19-S22, h = 4 | +0,69 | +0,89 | +0,50 |
| S19-S22, h = 8 | +0,70 | +0,90 | +0,51 |
| resto de 2026, h = 4 | −0,13 | −0,04 | −0,22 |
| resto de 2026, h = 8 | −0,31 | −0,10 | −0,53 |
| 2025, h = 4 | +0,10 | +0,17 | +0,03 |
| 2025, h = 8 | +0,16 | +0,22 | +0,10 |

Lectura:

- Los fallos de 2026 son de posición, no de ancho: en cada tramo todos los fallos salen por el
  mismo lado, y fuera de los tramos el rango cubre. Por eso ninguna capa de ancho del
  experimento de rangos los corrige.
- Ninguno de los dos componentes anticipa los escalones. En el cambio de año T falla más que M0
  (sigue la bajada de diciembre); en S19-S22 M0 falla más que T (esperaba la subida de mayo de
  años anteriores).
- Fuera de los tramos, T predice de menos en 2026 a horizontes largos (−0,53 a 8 semanas) y M0
  casi no tiene sesgo (−0,10). En 2025 los dos predijeron de más. El sesgo cambia de signo de un
  año al otro.
- Que los escalones vengan de cómo se construye la serie del tablero y no de la transmisión es
  una hipótesis: un promedio hacia atrás de 6 o 7 semanas (ADR 0021) no puede multiplicar por
  5,5 de una semana a la siguiente salvo que su ventana se reinicie al cambiar de año o que la
  tabla de origen se reescriba. Con una sola tanda de capturas no se puede comprobar. 2025-S1
  (75 casos tras 92 en OpenDengue 2024-S52) no muestra el escalón, pero allí se empalman dos
  fuentes distintas.

### Qué implica para la prueba prospectiva

El conjunto de prueba (objetivos desde 2026-S38, corte en 2027-S05) incluye el cambio de año.
Si el escalón de 2026-S1 se repite en 2027-S1, las semanas 2027-S1 a S3 pueden quedar fuera del
rango a 2 a 8 semanas, como en 2026. Con 20 semanas, el criterio admite 3 fuera; esas tres solas
lo agotarían. Esto describe un riesgo, no cambia la prueba: el criterio y el script congelado no
se tocan, y el protocolo ya reporta como sensibilidad las cifras sin las semanas 50 a 3.

### Limitaciones

- Las predicciones son las de la repetición con el ONI de 2025-2026 cargado, idénticas a las
  publicadas. La primera versión de este análisis (sin ese ONI) queda en el historial de git;
  sus conclusiones no cambian.
- En 2026 hay 4 semanas en S19-S22 y 1 a 3 en S1-S3 por horizonte: las cifras por tramo son
  descriptivas, no estimaciones con precisión.
- Las semanas 2026-S4 a S11 no tienen predicción a 4 semanas por el hueco de 2025-S53.
