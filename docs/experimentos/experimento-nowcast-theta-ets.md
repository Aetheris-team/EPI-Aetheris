# Experimento: suavizado exponencial (ETS) y Theta como base de C (2026-10-03)

> Protocolo fijado el 2026-10-03, antes de escribir y de correr el script, en la rama
> `feat/mejora-tablero-theta-ets` (sale de `feat/mejora-tablero-firma-candidatas`). Es la parte B
> de la Fase 2 del plan de mejora del predictor para la serie del tablero. No toca la prueba
> prospectiva congelada (`experimento-nowcast-tendencia.md`, script
> `40b6ebb78fe670222966a225438155b83ada876d`) ni la firma de K1, K2 y K3
> (`firma-candidatas-ventana-prospectiva.md`). Ninguna decisión de este documento usa una semana
> objetivo posterior a 2026-S37 y no se carga ninguna captura nueva.

## Enmienda del mismo día, antes del script y del barrido

Al escribir las pruebas se vio que el par cuyo origen es la primera semana de la serie no es un
pronóstico de ETS: la pendiente inicial es 0 por construcción. Ese par no entra en los errores de
ETS, que es lo que deja los mismos pares que T con pendiente de una semana y hace alcanzable el
control de abajo. Es un detalle de implementación; no se había calculado ninguna métrica.

## Pregunta

C promedia M0 con T, la tendencia amortiguada que mide su pendiente con las últimas 3 semanas de
la historia promediada. T es una regla de dos números. Dos familias clásicas de pronóstico
estiman la misma idea con otra forma:

- ETS con tendencia aditiva amortiguada: el nivel y la pendiente son medias móviles exponenciales,
  de modo que la pendiente usa todas las semanas anteriores con peso decreciente y no solo tres.
- Theta: nivel por suavizado exponencial simple más una deriva igual a la mitad de la pendiente
  de una recta ajustada a las últimas L semanas.

¿Alguna de las dos, puesta en lugar de T dentro de C, mejora la predicción? ¿Y un promedio de las
tres bases (T, ETS y Theta) dentro de C?

## Exploración previa, declarada

- Antes de este protocolo se leyó la estructura de los scripts de T y de su selección
  (`experimento_nowcast_tendencia.py`, `experimento_nowcast_tendencia_seleccion.py`) y se consultó
  la forma de la serie (664 semanas, de 2013-12-29 a 2026-09-13, un hueco en 2025-S53). No se
  calculó ninguna métrica de ETS ni de Theta.
- T se fijó en la exploración del 2026-09-27 mirando 2024 a 2026-S37. Por eso 2025 a 2026-S37 no es
  una ventana limpia para C, y todo lo que se mida ahí se rotula dentro de muestra, como en las
  fases anteriores. Los parámetros de ETS y de Theta se eligen con la historia hasta 2023, no con
  esas semanas.
- No se añaden pruebas después de ver los resultados. Lo que se mire después se rotula
  exploratorio.

## Datos y reglas comunes

- Serie mixta nacional (`cargar_serie_mixta`), historia promediada a 7 semanas hasta 2023 y escala
  `log1p`, igual que T. Semana sin dato (2025-S53): queda como NaN.
- Los modelos se comparan en los mismos pares origen-horizonte que T. Un origen es admisible si
  tiene dato en las 6 semanas anteriores y en el objetivo (la misma regla de la selección de T).
- Cada base da una mediana para cada origen y horizonte. Los cuantiles son los de T: la mediana
  más los 23 cuantiles de los errores de los pares (t, t + h) cuyo objetivo cae antes del origen,
  de 2014 en adelante y sin 2020, con al menos 30 errores. Así cada modelo se diferencia de T solo
  en la mediana.
- Las bases usan únicamente datos hasta el origen. Los parámetros se fijan una vez, con la
  validación de la parte A, y no se reajustan por origen.
- C' es el promedio por cuantil, en `log1p`, de M0 y de la base con peso 0,5 de M0, como C. M0 sale
  de `rangos.json` (bloques `B_h1` a `B_h8`, `q_R0`).
- Referencia: la persistencia suavizada (v = 3, sin pendiente), como en todas las fases.

## Los dos modelos

ETS (tendencia aditiva amortiguada, sin estacionalidad). Estado de nivel l y pendiente b:

- l(t) = α · z(t) + (1 − α) · (l(t−1) + φ · b(t−1))
- b(t) = β · (l(t) − l(t−1)) + (1 − β) · φ · b(t−1)
- mediana a h semanas: l(t) + b(t) · (φ + φ² + … + φ^h)
- inicio: l(0) = z(0), b(0) = 0. En una semana sin dato el estado avanza sin actualizarse:
  l(t) = l(t−1) + φ · b(t−1) y b(t) = φ · b(t−1).
- rejilla: α en {0,4; 0,6; 0,8; 1,0}, β en {0,2; 0,4; 0,6; 0,8; 1,0}, φ en {0,8; 0,9; 0,95}. Son 60
  configuraciones. Con α = 1 y β = 1 es T con pendiente de una semana.

Theta (forma de Hyndman y Billah del método de Assimakopoulos y Nikolopoulos):

- ℓ(t): suavizado exponencial simple de z con α, ℓ(0) = z(0); en una semana sin dato ℓ no cambia.
- b(t): pendiente de la recta de mínimos cuadrados de z sobre las últimas L semanas, con las
  semanas que tienen dato y exigiendo al menos max(3, L/2) de ellas.
- mediana a h semanas: ℓ(t) + (b(t) / 2) · (h − 1 + 1/α).
- rejilla: α en {0,3; 0,5; 0,7; 0,9; 1,0} y L en {6, 8, 12, 16, 26}. Son 25 configuraciones.
- Sobre la serie completa la pendiente de una recta es casi cero (doce años de ondas epidémicas),
  por eso la recta es local. La deriva no se amortigua; es la diferencia de diseño con ETS.

Ninguna de las dos lleva estacionalidad: de eso se ocupa M0, y T tampoco la lleva.

## Controles antes de cualquier barrido

- Las pruebas del script comparan ETS y Theta con implementaciones independientes escritas con
  bucles explícitos, con series lineales y constantes, y comprueban que cortar la serie en un
  origen no cambia su mediana (sin fuga del futuro).
- ETS con α = 1, β = 1 y φ = 0,8 debe reproducir T con φ = 0,8 y pendiente de una semana
  (`Reglas.cuantiles(o, h, 0.8, 1)` de la selección), con diferencia máxima menor o igual que
  1e-9, en la validación, en H1 y en los orígenes de H2 anteriores al hueco de 2025-S53 (después
  del hueco los conjuntos de errores difieren por una semana).
- T vigente reproduce `q_T` y `q_C_R0` de `rangos.json` con las tolerancias de la selección (T
  0,0005; C 0,003; WIS de la referencia 0,0005): se llama al control de la selección.

Si un control falla no se barre nada.

## A. Elegir con la historia hasta 2023

Validación: objetivos de 2018, 2019, 2021, 2022 y 2023, con la historia promediada a 7 semanas y
como objetivo la propia historia, igual que la selección de T. Puntaje de una configuración en un
horizonte: 1 − WIS(configuración) / WIS(referencia), con el WIS promediado dentro de cada año.
Puntaje de la configuración: promedio sobre los cinco años y los ocho horizontes. Una sola
configuración por familia para los ocho horizontes; no se eligen tramos.

Regla de cambio, fijada ahora. La mejor configuración de una familia pasa solo si supera a T
vigente (φ = 0,8, pendiente de 3 semanas) en al menos 0,005 de puntaje promedio y la supera en al
menos 3 de los 5 años. Es la misma regla con que se examinó T. Si una familia no la pasa, el
resultado de esa familia es que no supera a T en la historia y no se confirma nada.

## Extensión E1, añadida después de correr A y antes de B

La parte A ya se corrió con la rejilla de arriba. Solo se miró la validación (historia hasta 2023),
no H1 ni H2. El mejor ETS, (α, β, φ) = (0,8; 1,0; 0,8), tiene la amortiguación mínima de la rejilla
y la β máxima posible; el mejor Theta, (α, L) = (1,0; 6), tiene la ventana mínima. Un óptimo en el
borde pide extender la rejilla hacia ese lado, como se hizo con la ventana de T en la Fase 1. Se
fija ahora, antes de calcular nada de la extensión y antes de mirar H1 y H2:

- ETS: φ en {0,5; 0,6; 0,7}, con las mismas α y β. Son 60 configuraciones más.
- Theta: L en {3, 4, 5}, con las mismas α. Son 15 configuraciones más.
- Se puntúan en la validación igual que las anteriores. La mejor de la extensión, de cada familia,
  sustituye a la mejor original solo si cumple las dos: supera a la mejor original en al menos
  0,005 de puntaje promedio y en al menos 3 de los 5 años, y cumple por sí sola la regla de cambio
  frente a T vigente. Si no, B y C usan la configuración original.
- B y C no se corren hasta tener la elección final de las dos familias. La extensión se rotula
  como añadida después de ver A.

## B. Confirmación fuera de la selección

Solo para las familias que pasen A. Dos conjuntos que no sirvieron para elegir la configuración:

- H1: objetivos de 2024 (OpenDengue ya promediado por MINSAL).
- H2: objetivos de 2025 a 2026-S37 (tablero). Rotulada dentro de muestra: T y C se fijaron mirándola.

Una familia (con su configuración elegida en A) queda elegible para firmarse como candidata
paralela a C si cumple todo:

- (a) la regla de cambio de A;
- (b) en H1 y en H2, el promedio sobre los ocho horizontes de WIS(C') / WIS(C) es menor que 1;
- (c) la cobertura al 95 % de C' en H2, agrupando horizontes, no baja más de 0,03 respecto a la de C.

Se reportan, sin criterio: el WIS de la base contra T, el skill contra la persistencia suavizada,
las coberturas del 50 % y del 95 %, la razón por horizonte y por grupo (h1-2, h3-4, h5-8), y la
prueba de Diebold-Mariano contra C por horizonte (Newey-West con h − 1 rezagos y corrección de
Harvey-Leybourne-Newbold, con Holm entre todas las comparaciones). La prueba no decide nada:
con unas 80 semanas autocorrelacionadas solo sirve para ver cuánta incertidumbre hay.

También se reporta, como descripción y aunque la familia no pase A, el mejor de cada familia
contra C en H1 y en H2. Esa fila no habilita nada.

## C. Promedio de bases (rotulado exploratorio)

Base ensamblada: promedio por cuantil, en `log1p`, de T vigente, del mejor ETS y del mejor Theta de
A (los mejores de cada familia por puntaje de validación, pasen o no la regla de cambio), con peso
1/3 cada uno. C'' es su mezcla al 50 % con M0. Se corre siempre. No tiene regla de selección
propia, así que se rotula exploratorio. Queda elegible para firmarse si cumple (b) y (c) con C''
en lugar de C'.

## Qué habilita cada resultado

- Una candidata elegible (ETS, Theta o el promedio) se propone a Eduardo para firmarse como
  predicción paralela a C en la ventana de la prueba congelada, en un documento aparte, con el
  criterio de K1 a K3: razón media de WIS contra C menor o igual que 0,99, razón menor que 1 en
  al menos 5 de 8 horizontes y cobertura del 95 % no más de 0,03 bajo C. Esto solo es posible
  antes de cargar una captura con 2026-S38 o posterior.
- Si ninguna es elegible, es un resultado negativo con sus cifras: la tendencia de 3 semanas está
  en la meseta de estas familias y no se firma nada nuevo.
- Estar elegible no confirma nada. La confirmación solo la da la ventana prospectiva.

## Probabilidad previa y comparaciones múltiples

T ya es una regla de tendencia amortiguada, y ETS la contiene como caso límite (α = β = 1, pendiente
de una semana). La ganancia esperable es pequeña. Con tres candidatas posibles y dos conjuntos
de confirmación que se ven a la vez, la regla puede dejar pasar por azar una variante sin ventaja.
Por eso la elegibilidad solo habilita a firmar una predicción paralela, cuyo costo es bajo, y no
cambia el sitio. En el peor caso la ventana prospectiva tendría seis candidatas contra C y la
corrección de Holm se hace sobre todas las comparaciones.

## Reproducibilidad

- Script `backend/ingestion/experimento_nowcast_theta_ets.py`, con pruebas en
  `backend/ingestion/tests/test_theta_ets.py`. Reutiliza `historia`, `Reglas`, `cargar_b` y las
  funciones de métrica de `experimento_nowcast_tendencia_seleccion.py`.
- Modos `--control`, `--parte-a`, `--extension-e1`, `--parte-b` y `--parte-c`. Salida en
  `docs/agentes/mejora-predictor/resultados-nuevos/theta_ets.json`.
- El script se escribe y se commitea, con sus pruebas, antes de correr cualquier parte.

## Resultados (2026-10-03)

Orden de los commits: protocolo 2dfb040, enmienda a29654b, script y pruebas d3a8afe, extensión E1
ecf1355 (protocolo) y 9c9681e (código); cada paso se commiteó antes de correrlo. Las 52 pruebas
unitarias pasan.

### Controles

T vigente reproduce `q_T` y `q_C_R0` guardados (diferencia máxima 0,0005 en T y 0,0026 en C, dentro
de las tolerancias de la Fase 1) y el WIS de la referencia (0,0005). ETS con α = 1, β = 1 y
φ = 0,8 reproduce T con pendiente de una semana con diferencia máxima 0 en 2940 pares origen-horizonte,
y el puntaje de validación de T calculado con este script coincide con el de la selección de
T con diferencia 0.

### A. Elegir con la historia hasta 2023

Validación de 2080 pares origen-horizonte. Puntaje de T vigente: +0,2258.

| familia | configuraciones | superan a T | mejor | puntaje | ganancia sobre T | años en que supera | regla de cambio |
|---|---|---|---|---|---|---|---|
| ETS | 60 | 13 | α 0,8; β 1,0; φ 0,8 | +0,2568 | +0,0309 | 4 de 5 | sí |
| Theta | 25 | 0 | α 1,0; L 6 | +0,1398 | −0,0860 | 0 de 5 | no |

Puntaje por año del mejor ETS contra T: 2018 0,295 contra 0,244; 2019 0,353 contra 0,305; 2021
0,221 contra 0,152; 2022 0,394 contra 0,366; 2023 0,022 contra 0,063 (el único año en que pierde).
Las cinco mejores ETS tienen β de 0,8 o 1,0 y φ de 0,8 o 0,9. El mejor Theta es el de menor
ventana y α = 1.

### Extensión E1 (añadida después de A)

ETS con φ de 0,5 a 0,7: la mejor, (0,8; 1,0; 0,7), puntúa +0,2267, 0,030 menos que la original y
gana en 1 de 5 años; no sustituye. El óptimo de φ queda interior, en 0,8. Theta con L de 3 a 5: la
mejor, (1,0; 3), puntúa +0,2275 y gana a la original de Theta en los 5 años, pero frente a T suma
+0,0017 en 3 años y no cumple la regla de cambio; no sustituye. Con L = 3 y α = 1 Theta usa una
pendiente de dos semanas con deriva de h/2 sin amortiguar, que se parece a T con pendiente de dos
semanas y suma amortiguada (0,5 a 4 contra 0,8 a 3,3 para h de 1 a 8), así que iguala a T y no la supera.

Configuraciones finales: ETS (0,8; 1,0; 0,8), de la rejilla original, y Theta (1,0; 6), que no pasa
la regla y se evalúa solo como descripción.

### B. Confirmación fuera de la selección

Razón de WIS de C' (M0 con la base) contra C, promedio de los 8 horizontes; entre paréntesis, por
grupo h1-2, h3-4 y h5-8. H1 son 52 pares por horizonte (2024); H2, 80 o 81 (2025 a 2026-S37, dentro
de muestra).

| base | H1 | H2 | base contra T, H1 y H2 | cobertura del 95 % en H2, C' contra C | elegible |
|---|---|---|---|---|---|
| ETS (0,8; 1,0; 0,8) | 0,973 (0,975; 0,976; 0,969) | 0,998 (0,996; 1,000; 0,997) | 0,966 y 1,003 | 0,907 contra 0,907 | sí |
| Theta (1,0; 6) | 1,041 (1,048; 1,041; 1,038) | 1,033 (1,070; 1,034; 1,014) | 1,054 y 1,023 | 0,912 contra 0,907 | no (no pasa A y la razón supera 1) |

ETS por horizonte, razón contra C. H1: 0,977; 0,974; 0,974; 0,978; 0,964; 0,964; 0,971; 0,978. H2:
1,000; 0,991; 0,998; 1,002; 1,002; 0,992; 0,998; 0,997. En H1 la cobertura del 95 % es 1,000 para
las dos, de modo que no distingue. En H2 la cobertura del 50 % de C' queda entre 0,37 y 0,53 por
horizonte, como la de C.

Diebold-Mariano de C' contra C, con Holm entre 48 comparaciones (ETS, Theta y el promedio de bases,
en H1 y H2, por horizonte):

- ETS: p crudo entre 0,014 y 0,18 en H1 (menores en h1, h5 y h6) y entre 0,61 y 0,98 en H2; con
  Holm ninguna baja de 0,57.
- Theta: es peor que C. En h = 1 el p crudo es 0,0003 en H1 y 0,00007 en H2 (Holm 0,015 y 0,003);
  en h = 2 de H2 el p crudo es 0,002 (Holm 0,095).

### C. Promedio de T, ETS y Theta (exploratorio)

Razón contra C: 0,999 en H1 y 1,005 en H2 (por horizonte entre 0,996 y 1,023); base contra T 0,982 y
0,990; cobertura del 95 % en H2 0,913 contra 0,907. No es elegible. El promedio con Theta pierde la
ganancia que traía ETS.

## Conclusiones

- Theta no sirve para esta serie. Ninguna de sus 25 configuraciones supera a T en la validación, la
  extensión a ventanas más cortas solo la acerca a T, y puesta dentro de C es peor que C en H1 y en
  H2, de forma apreciable en h = 1 y 2 (hasta 8 % de WIS).
- ETS (0,8; 1,0; 0,8) cumple la regla firmada, es decir, es elegible: gana a T en la validación
  (+0,031 de skill, 4 de 5 años) y la razón contra C es menor que 1 en los 8 horizontes de 2024
  (0,973). En el tablero esa ganancia desaparece: 0,998 en 2025 a 2026-S37, indistinguible de C. En
  2024 la ventaja es consistente entre horizontes pero ninguna prueba de Diebold-Mariano resiste
  Holm.
- Una explicación posible, no probada, es que ETS gana suavizando el ruido de series que aún lo
  tienen (la historia hasta 2023 promediada a 7 semanas y OpenDengue 2024) y que el tablero ya
  viene suavizado por MINSAL, de modo que el filtro de ETS aporta poco. La ventana prospectiva es
  del tablero, por lo que se parece a H2 y no a H1.
- La elegibilidad solo habilita a firmar una predicción paralela; no cambia el sitio. El criterio de
  confirmación de la firma (razón media menor o igual que 0,99) no se cumpliría con una razón como
  la de H2, de modo que la probabilidad previa de que ETS se confirme es baja.
- Limitaciones: la rejilla es gruesa (60 y 25 configuraciones); la elección usa cinco años; H2 es
  dentro de muestra para T y para C; la historia se promedió a 7 semanas por una aproximación que
  MINSAL no ha confirmado.

## Qué se hace con esto

Se prepara, sin firmarla, la propuesta de una candidata paralela a C con ETS (0,8; 1,0; 0,8)
como base (`firma-candidata-ets-ventana-prospectiva.md`). Theta y el promedio de bases se descartan.
La decisión de firmar es de Eduardo.
