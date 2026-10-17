# Comparación externa del predictor de dengue (Fase 5, 2026-10-03)

> Búsqueda en la web abierta del 2026-10-03, para responder las preguntas de la sección 9 del
> documento del modelo. Cada página se leyó con una herramienta de extracción de texto, no con el
> PDF completo; las cifras se citan tal como esas lecturas las devolvieron y no se contrastaron con
> los artículos, salvo donde se indica. Lo que solo se vio en el resumen de un resultado de búsqueda
> se rotula así. No se consultó el sitio de MINSAL ni sus documentos.

## Resumen

1. No se encontró ningún modelo de pronóstico publicado para El Salvador ni una evaluación pública
   con sus series. La ausencia en una búsqueda no prueba que no exista. Por eso no hay contra qué
   comparar el modelo con la misma serie, el mismo horizonte y la misma métrica.
2. Los trabajos comparables (otros países, otras escalas) coinciden con tres cosas que el
   repositorio ya midió: los baselines estadísticos simples son difíciles de superar, el clima no
   mejora el pronóstico de forma consistente y los ensambles o mezclas son más robustos que un
   modelo solo.
3. La métrica del repositorio (WIS con 23 cuantiles) es la de los hubs de pronóstico de CDC y OPS,
   pero los trabajos de dengue leídos puntúan con log score, CRPS o error absoluto. Las cifras no
   se pueden poner en la misma tabla. La única comparación válida sería reevaluar un método
   publicado sobre la serie de El Salvador con el protocolo del repositorio.
4. Casi todas las evaluaciones publicadas usan datos finales, sin retrasos de notificación; la del
   repositorio también. Pocas incluyen una ventana prospectiva; la del repositorio la tiene
   registrada y sin ejecutar.

## Pregunta 1: modelos publicados para El Salvador y la región

- El Salvador. Un estudio ecológico de 262 municipios, 2011 a 2013, con casos del Ministerio de
  Salud, relaciona el dengue con temperatura, precipitación y variables socioeconómicas (Joyce et
  al., Vector-Borne and Zoonotic Diseases; texto en
  https://sites.ucmerced.edu/files/ajoyce2/files/2021_joyce_dengue_el_salvador_final.pdf). La lectura
  de la página no mostró ninguna evaluación fuera de muestra ni pronóstico. El resumen del resultado
  de búsqueda dice que las variables significativas fueron temperatura, precipitación y área sin
  bosque, con 29.764 casos confirmados.
- Un resultado de búsqueda apunta a un boletín epidemiológico de MINSAL de 2019 que incluiría
  «modelos matemáticos predictivos» con análisis de frecuencias y series de Fourier. No se abrió.
  Queda como pista para quien tenga acceso a ese documento.
- Costa Rica. Modelos clima-dengue con modelos aditivos generalizados, bosques aleatorios e INLA,
  a escala de cantón o distrito, con riesgo relativo y no conteos semanales nacionales
  (https://arxiv.org/pdf/2204.01483 y https://arxiv.org/pdf/2302.06747). Distinto objetivo y escala.
- Colombia. Bosques aleatorios y redes neuronales a escala departamental, semanal, de 1 a 12
  semanas (PLoS NTD 2020, https://pmc.ncbi.nlm.nih.gov/articles/PMC7537891/). Datos de 30
  departamentos, 2014 a 2018, entrenamiento 2014 a 2017 y validación 2018. El bosque aleatorio
  nacional (un modelo para todos los departamentos) tuvo un MAE de 9,32 a una semana y 24,56 a doce,
  y un error absoluto relativo contra ARIMA de 0,93 y 0,86. En ese trabajo las variables
  ambientales y meteorológicas pesaron más en horizontes cortos y las socioeconómicas en los largos,
  según la importancia de variables, que no es una ablación.

## Pregunta 2: evaluación pública con series de El Salvador

No se encontró.

## Pregunta 3: nowcasting con retraso de notificación

- Puerto Rico 2024: nowcasting bayesiano con suavizado (NobBS), contra un modelo base. El resumen
  dice que superó al base de forma consistente, que los años con retrasos más variables dieron más
  incertidumbre y que las anomalías de reporte a veces bajaron el desempeño
  (https://www.networkscienceinstitute.org/publications/lessons-learned-from-real-time-nowcasting-the-2024-dengue-outbreak-in-puerto-rico).
  Solo se leyó el resumen.
- Un método con redes neuronales probabilísticas (NowcastPNN) sobre São Paulo apareció en una
  búsqueda y no se abrió.
- Estos métodos estiman casos ocurridos y aún no notificados, y necesitan la fecha de notificación
  o de inicio de síntomas de cada caso para armar el triángulo de retrasos. El tablero publica una
  serie semanal ya agregada, sin esas fechas. Lo que hace el repositorio es pronosticar esa serie
  publicada; no corrige retrasos. No se encontró información sobre si MINSAL publica fechas que
  permitan reconstruir el triángulo.
- Lo que sí transfiere: las anomalías de reporte degradan los pronósticos, y los saltos de fin de
  año del tablero son de esa clase.

## Pregunta 4: métricas

El WIS sobre 23 cuantiles es el formato de los hubs de CDC y OPS (Bracher et al. 2021 define el
WIS). Los trabajos de dengue leídos usan otras: log score de distribuciones por intervalos para
objetivos de temporada (Johansson et al.), CRPS, log score y interval score (Sprint de Brasil), error
absoluto y error absoluto relativo contra ARIMA (Colombia, Iquitos, San Juan, Singapur). Una
cifra de skill de un trabajo no es comparable con la del repositorio.

El COVID-19 Forecast Hub usa como referencia un modelo cuya mediana es el último valor observado
(resultados de búsqueda sobre covid19forecasthub.org). La persistencia del repositorio tiene la
misma mediana y agrega cuantiles empíricos de los cambios a h pasos. Hay un preprint de 2025 sobre
cómo la elección del modelo de referencia cambia la evaluación («Mind the Baseline»,
https://www.medrxiv.org/content/10.1101/2025.08.01.25332807.full.pdf); no se pudo leer (error 403) y
queda pendiente, porque toca la elección entre la persistencia limpia y la suavizada.

## Pregunta 5: competencias y su desempeño

| Trabajo | Qué evaluó | Referencia | Lo que reporta |
|---|---|---|---|
| Desafío abierto de Johansson et al., PNAS 2019 (https://pmc.ncbi.nlm.nih.gov/articles/PMC6883829) | Iquitos (13 temporadas) y San Juan (23); objetivos de temporada (semana del pico, incidencia del pico y total); 4 temporadas de prueba | SARIMA | Los ensambles tuvieron mejor log score (diferencia media 1,02; IC 95 % 0,91 a 1,13); los mecanísticos peor (−0,65); los modelos con clima tuvieron menos habilidad (−0,14; IC 95 % −0,19 a −0,09). El SARIMA «generalmente se desempeñó bien» frente a modelos complejos. Los datos eran finales, sin retrasos de reporte, y el artículo lo declara como limitación |
| Sprint de Brasil 2024, PNAS (https://pmc.ncbi.nlm.nih.gov/articles/PMC12912988/) | Seis equipos, cinco estados, casos probables semanales de temporadas completas (2024 y 2025); CRPS, log score e interval score | Sin modelo de referencia declarado en la lectura | «Ningún modelo fue consistentemente el mejor», sobre todo en la temporada atípica de 2024; los ensambles reducen la incertidumbre; los modelos con clima o ENSO no mejoraron de forma consistente sus posiciones |
| Pronósticos semanales en Iquitos, San Juan y Singapur, PLoS NTD 2020 (https://pmc.ncbi.nlm.nih.gov/articles/PMC7567393/) | 4 y 12 semanas, validación hacia adelante con reajuste anual | Poisson y ARIMA | Con vigilancia, el bosque aleatorio tuvo 21 % y 33 % menos error que Poisson y ARIMA a 4 semanas; a 12 semanas ARIMA ganó en dos de los tres sitios. Sin datos de vigilancia (solo clima y calendario) el error normalizado del bosque fue de 0,96, 0,59 y 0,61 contra 0,88, 0,50 y 0,58 de Poisson |
| Colombia, PLoS NTD 2020 | Ver pregunta 1 | ARIMA local | Error relativo 0,93 a una semana y 0,86 a doce |
| Ensambles en más de 180 lugares (medRxiv 2024, https://www.medrxiv.org/content/10.1101/2024.10.22.24315925) | Pronósticos mensuales en Brasil, Colombia, Malasia, México, Tailandia, Iquitos y San Juan | Un modelo base con la información disponible | Resultado de búsqueda: los ensambles de varios modelos y de varios equipos superan de forma consistente a los modelos individuales. No se pudo abrir (error 403) |
| Segundo Sprint de Brasil, 2025 | 15 equipos, 19 modelos, todos los estados | | Resultados en https://github.com/Mosqlimate-project/2nd_IMDC_sprint_results; no se leyeron |

El único trabajo con ventana prospectiva leído es el Sprint de Brasil (pronósticos de 2025 hechos
con datos hasta 2024). El resto evalúa temporadas retenidas.

## Pregunta 6: clima y ENSO

- Estudios de Costa Rica y resúmenes regionales dicen que temperaturas mínimas y medias altas antes
  y al inicio de la temporada de lluvias se asocian con más dengue hasta con dos meses de rezago, y
  que El Niño se asocia con más incidencia (resúmenes de búsqueda, que citan estudios de Costa Rica
  y un informe de síntesis de MSF; no se verificaron en las fuentes primarias).
- En los trabajos de pronóstico leídos, la ganancia de agregar clima no se sostiene: menor habilidad
  con clima en Johansson et al., sin mejora consistente en el Sprint de Brasil, y sin ventaja del
  aprendizaje automático cuando solo hay clima y calendario en Iquitos, San Juan y Singapur. Un
  estudio de Río de Janeiro compara modelos estadísticos y de aprendizaje automático con y sin
  clima (https://tropmedhealth.biomedcentral.com/articles/10.1186/s41182-025-00723-7); solo se vio el
  título y el resumen del resultado de búsqueda.
- El experimento de insumos del repositorio (`docs/experimentos/experimento-nowcast-insumos.md`)
  dio un resultado de la misma dirección: quitar el clima cuesta entre 0,02 y 0,04 de WIS agrupado a
  2 a 8 semanas, concentrado en 2022, y no alcanza el umbral fijado; quitar el ONI no empeora nada
  medible.

## Pregunta 7: disponibilidad de datos

- OpenDengue (Clarke et al., Scientific Data 2024,
  https://pmc.ncbi.nlm.nih.gov/articles/PMC10940302/): 843 fuentes, 102 países, 56 millones de
  casos en la versión 1.2, con resolución semanal o mensual y datos subnacionales para 40 países. Es
  la fuente de la serie nacional del repositorio hasta 2024.
- PLISA de OPS: la búsqueda no devolvió una página de descarga para El Salvador. No se intentó
  ninguna otra vía.
- Los boletines epidemiológicos semanales de MINSAL están en el portal de transparencia del
  gobierno, según los resultados de búsqueda. No se abrieron.

## Pregunta 8: series suavizadas en la fuente

No se encontró literatura sobre vigilancia de dengue cuya serie publicada venga promediada en el
origen ni sobre su efecto en el pronóstico. En general, un resultado de búsqueda sobre mpox dice
que el error de pronóstico baja al pasar de datos crudos a una media móvil de 4 semanas y sube con
5 (https://arxiv.org/pdf/2602.06135), y otro menciona que cuatro técnicas de suavizado
influyeron en la precisión de distintos modelos, aunque el método de suavizado por sí solo no tuvo
un efecto significativo frente a la elección del modelo (https://www.mdpi.com/2079-3197/13/6/136). En ambos
el suavizado lo aplica quien pronostica sobre la entrada, no la fuente sobre lo que publica. Es
indicio de que el suavizado de la entrada importa, consistente con el hallazgo del repositorio de
que una tendencia amortiguada sobre la historia promediada gana a la persistencia en la serie del
tablero.

## Qué dice esto del modelo

Lo que la literatura leída respalda:

- La cautela del sitio sobre el clima. Ningún trabajo leído muestra que el clima mejore el
  pronóstico de forma consistente.
- La mezcla de modelos (C es una mezcla de M0 y T). Los trabajos coinciden en que los ensambles son
  más robustos que un modelo individual.
- La comparación con referencias simples. El SARIMA del desafío de Johansson et al. y el ARIMA de
  Colombia y de Iquitos se comportaron como referencias fuertes.
- El orden de magnitud de las ganancias. Las reducciones de error contra ARIMA o Poisson van de 7 a
  33 % según el caso. Las ganancias de M0 contra la persistencia limpia son de +0,05 a h = 4 y +0,18
  a h = 8 en la validación, y las de C contra la persistencia suavizada de +0,15 y +0,16 en
  2025-2026, dentro de muestra. Son magnitudes del mismo orden, con métricas distintas, y no
  permiten decir que el modelo rinde igual que los publicados.

Lo que no respalda:

- Ninguna afirmación de que el modelo sea mejor o peor que modelos publicados. No hay un modelo
  publicado para El Salvador con el que compararlo, y las métricas de los demás difieren.

## Comparación que sí se puede hacer

Reevaluar métodos publicados sobre la serie de El Salvador con el protocolo del repositorio. Los
candidatos con descripción suficiente son el SARIMA del desafío de Johansson et al. y el ARIMA
automático de los trabajos de Colombia, Iquitos y San Juan. ETS y Theta ya se midieron en el
experimento correspondiente y, como las variantes de tendencia, no superaron a T en el tablero.
Un ARIMA o SARIMA entraría como referencia externa y no como candidato, con los mismos pares
origen-horizonte y las mismas métricas. Es un experimento nuevo y necesita su protocolo.

## Pistas pendientes

- Abrir el boletín epidemiológico de MINSAL de 2019 con los «modelos matemáticos predictivos».
- Leer «Mind the Baseline» y el estudio de Río de Janeiro (clima con y sin).
- Revisar los resultados del segundo Sprint de Brasil, que cubre todos los estados.
- Preguntar a MINSAL si publica fechas de notificación o de inicio de síntomas por caso.
