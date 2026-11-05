# Instrucciones: búsqueda de mejoras al predictor de dengue

Este documento es para un agente de Claude Code que trabaja en la nube sobre la rama `feat/mejora-predictor-agente`. Léelo completo antes de empezar y lee también `AGENTS.md` en la raíz del repo, que fija las convenciones del proyecto. La rama no se mergea: es un espacio de trabajo con los datos que el agente necesita y que no están en `main`.

## Objetivo

Encontrar, con experimentos rigurosos, cambios que mejoren el predictor de casos de dengue a corto plazo de EPI-Aetheris para El Salvador, o concluir con evidencia que no hay mejora alcanzable con los datos disponibles. Un resultado negativo bien medido vale tanto como uno positivo.

El predictor es un pronóstico probabilístico del conteo semanal nacional de dengue, de 1 a 8 semanas desde la última semana publicada, con 23 cuantiles. Tiene dos tramos: M0 (gradient boosting cuantílico con calibración CQR-r, para la serie de OpenDengue hasta 2024) y C (mezcla 50/50 de M0 con una tendencia amortiguada, para la serie del tablero de MINSAL desde 2025). Su descripción completa, con archivo y línea, está en `docs/agentes/mejora-predictor/modelo-actual.md`. Léelo antes de proponer nada: ahí están los hiperparámetros, las variables, los resultados medidos y las limitaciones ya conocidas.

## Qué hay en esta rama que no está en `main`

| Ruta | Qué es |
|---|---|
| `db/seed/seed_tablero_minsal.sql` | Serie del tablero de MINSAL de 2025-S1 a 2026-S37 (356 filas: dengue sospechoso y confirmado, IRA, neumonías). El volcado principal no la incluye. Se carga después de `seed_datos_reales.sql`, es idempotente y fue probada. |
| `docs/agentes/mejora-predictor/modelo-actual.md` | Descripción exacta del modelo vigente, con afirmaciones etiquetadas como hecho, documentado o inferencia, y la lista de lo que no se puede afirmar. |
| `docs/agentes/mejora-predictor/modelos-predictivos-dengue.md` | Revisión bibliográfica de modelos de dengue (global, Américas y El Salvador). Es una fuente de ideas, no de hechos: ver la sección sobre cómo usarla. Las fórmulas, que eran imágenes, quedaron como `[fórmula]`. |
| `docs/agentes/mejora-predictor/resultados-previos/` | Salidas JSON de los experimentos ya corridos (`nowcast/` y `nowcast_calibracion/`), que en el repo original están ignoradas por git. Sirven para comparar sin repetir corridas largas. No incluyen los `.pkl` crudos. |

## Preparar el entorno

1. Python con `backend/requirements.txt` y `backend/requirements-dev.txt`. Los scripts de experimentos también usan `numpy` y `threadpoolctl` (vienen con scikit-learn).
2. Postgres 15. La forma más simple es `docker compose up -d db` con un `.env` copiado de `.env.example` (valores locales de prueba; no pongas credenciales reales). Si no hay Docker, instala Postgres y crea la base con las mismas variables `POSTGRES_*`.
3. Cargar datos, en este orden: las migraciones de `db/migrations/` (en `docker compose` se aplican solas al crear el volumen), luego `db/seed/seed_datos_reales.sql`, luego `db/seed/seed_tablero_minsal.sql`. Comprueba que existen 356 filas con la fuente del tablero:

   ```sql
   SELECT count(*) FROM casos_epidemiologicos ce
   JOIN fuentes_datos f ON f.id = ce.fuente_id
   WHERE f.nombre LIKE 'Tablero%';
   ```

4. Los scripts se ejecutan desde `backend/ingestion/` con `POSTGRES_HOST=localhost` (los comandos exactos están en el encabezado de cada `experimento_nowcast_*.py`). Los experimentos largos usan `nice` y `threadpool_limits`; respeta eso para no saturar la máquina.
5. Las pruebas: `python -m pytest ingestion/tests/ api/tests/` desde `backend/`. Los tests con base se saltan si no hay Postgres.

Si algo del entorno no se puede reproducir (por ejemplo, el volcado no carga), detente y documenta el problema; no inventes datos.

## Reglas del método

El proyecto tiene un protocolo de experimentos que debes seguir. Mira `docs/experimentos/experimento-nowcast-mejora.md` y `experimento-nowcast-tendencia.md` como ejemplos de formato.

1. **Protocolo antes de correr.** Escribe, antes de ejecutar nada, un documento en `docs/experimentos/` con: pregunta, candidatos, parámetros fijados, años y horizontes de evaluación, métrica primaria, criterio de éxito y qué se hará con cada resultado posible. Hazle un commit propio antes de la primera corrida. Cualquier cambio posterior va en una sección de enmiendas con fecha, antes de la corrida a la que afecta.
2. **Forward-chaining sin fuga.** Cada predicción usa solo información anterior a su semana de partida. Reutiliza la aserción anti-fuga y el control negativo de `experimento_nowcast_corto_plazo.py` en cualquier código nuevo. Una fuga invalida el experimento entero.
3. **Métrica.** La métrica primaria es el WIS sobre los 23 cuantiles, y el skill es `1 - WIS_modelo / WIS_referencia`. Reporta también la cobertura empírica de los rangos del 50 % y 95 % y el sesgo. Usa `wis` y `cobertura` de `experimento_nowcast_corto_plazo.py`.
4. **Referencias.** Compara siempre contra la persistencia limpia (la que no aprende de las nueve semanas con cero casos, ver el experimento de mejora) y contra la referencia publicada, y contra el modelo vigente (M0 para OpenDengue, C para el tablero). Una mejora frente a una referencia débil no cuenta.
5. **Sin ajustar sobre los años de prueba.** Elige hiperparámetros con años de validación distintos de los de confirmación, como hizo el experimento de mejora (fase de validación y fase de confirmación). Documenta cuántas variantes probaste; muchas variantes sobre los mismos años inflan el resultado.
6. **Años y series.** OpenDengue: 2014-2024, sin 2020 como objetivo. Años de evaluación del modelo vigente: 2019 y 2021-2024. Tablero: 2025-S1 a 2026-S37. La serie del tablero es un promedio de unas 6 o 7 semanas hecho por MINSAL; lo que se predice allí es una serie suavizada. No mezcles las dos series sin tratar esa diferencia.
7. **La prueba prospectiva está reservada.** La evaluación prospectiva del modelo vigente cubre 20 semanas desde 2026-S38 con el script congelado en el commit `40b6ebb78fe670222966a225438155b83ada876d` (ver `docs/experimentos/experimento-nowcast-tendencia.md`). No uses datos de 2026-S38 en adelante para elegir nada, aunque llegues a tenerlos, y no modifiques ese script. Tu trabajo es candidato a una prueba prospectiva futura, no sustituye la actual.
8. **Un resultado se declara solo si cumple su criterio** fijado de antemano. Si no lo cumple, se reporta como no concluyente o negativo, con los números.
9. **Reproducibilidad.** Cada experimento nuevo es un script `backend/ingestion/experimento_*.py` que se corre de punta a punta, con semillas fijas, y escribe sus resultados en JSON. Guarda los JSON relevantes en `docs/agentes/mejora-predictor/resultados-nuevos/` (esta rama, versionados) además de la salida por defecto.

## Qué explorar

El orden es una sugerencia; justifica el tuyo en el protocolo.

1. **Leer y descartar con criterio.** Del documento de revisión bibliográfica, extrae las ideas aplicables a este problema: serie nacional semanal, 1 a 8 semanas, predicción probabilística, datos disponibles (conteos nacionales, clima de 14 departamentos, ONI). Descarta lo que exige datos que no existen aquí (serotipos, movilidad, datos entomológicos, series departamentales largas) y dilo explícitamente. Verifica en las fuentes originales las afirmaciones de rendimiento que quieras usar; la revisión puede contener errores o cifras de otros contextos.
2. **Cobertura de los rangos.** Es el punto más débil medido: 0,39 al 50 % y 0,91 al 95 % en 2025-2026, y 0,79 al 95 % solo en 2026 (el criterio exige 0,85). Prueba otras calibraciones (conformal adaptativo, por horizonte, con ventana móvil), con sus costos en WIS.
3. **Horizontes cortos.** A 1 a 3 semanas el skill contra la persistencia limpia es casi nulo. Evalúa si alguna estructura (modelos de dinámica local, errores autorregresivos, mezcla ponderada por desempeño reciente) lo mejora de forma sostenida.
4. **Peso de la mezcla y otras familias.** El peso 0,5 de C es fijo. Evalúa pesos dependientes del horizonte o del régimen, y familias de la literatura que se puedan implementar con las dependencias existentes o con otras que justifiques: SARIMAX/ETS con exógenas, modelos bayesianos estructurales, quantile regression forests, redes pequeñas, ensambles de cuantiles. Mide cada una contra las referencias de la regla 4.
5. **Aporte del clima.** Nunca se midió con ablación. Haz la ablación (con y sin clima, con y sin ONI) en M0. Es un resultado útil sea cual sea el signo: respalda o retira una afirmación del sitio.
6. **Robustez ante brotes.** El soporte de la robustez ante brotes sin precedente es un solo año (2019). Propón una evaluación que lo ponga a prueba con la historia recortada y reporta honestamente lo que se puede y no se puede concluir.
7. **Semanas problemáticas.** Las semanas con cero casos por vacaciones y la semana 53 distorsionan referencias y modelos. Evalúa si un tratamiento explícito mejora la calidad de los rangos sin trampa en la puntuación.

No es necesario cubrir todo. Prefiere pocas líneas bien medidas a muchas superficiales.

## Qué no hacer

- No cambies el modelo publicado, los artefactos `backend/api/datos/*.json`, la API ni el frontend. Esta tarea produce evidencia y propuestas, no despliegues. Si una mejora resulta clara, déjala descrita y reproducible; la integración se decide aparte.
- No modifiques el script de la prueba prospectiva congelada ni su criterio.
- No añadas datos externos que no tengan licencia clara ni los mezcles con las series sin documentar fuente, definición de caso y tratamiento. Si usas datos públicos nuevos, descarga solo lo necesario y documenta cómo reproducir la descarga.
- No incluyas credenciales, tokens ni el contenido de ningún `.env`.
- No afirmes que el modelo supera a modelos de terceros salvo con una comparación hecha aquí, sobre la misma variable objetivo, horizonte, periodo y datos disponibles en tiempo real.
- No inventes cifras. Toda cifra en un documento sale de una corrida reproducible, con su archivo de resultados.

## Cómo usar la revisión bibliográfica

`modelos-predictivos-dengue.md` es una síntesis hecha por otra herramienta. Úsala para generar hipótesis. Antes de apoyarte en una cifra o una conclusión de ahí:

- Búscala en la fuente original si tienes acceso a la web; si no, márcala como no verificada.
- Comprueba que el contexto (país, variable objetivo, horizonte, métrica) sea comparable con el nuestro. Los rendimientos de modelos evaluados con otras métricas, otras resoluciones o datos más ricos no son comparables sin una corrida propia.

## Redacción de los documentos

Todo en español. Reglas de estilo del proyecto: sin historia interna ni relato de cómo se llegó a algo, sin tono defensivo ni autoelogio, sin eslóganes, sin metacomentarios, sin rayas largas como recurso, sin abuso de negritas, sin mayúsculas enfáticas y sin la frase "no es X, es Y". Las tablas y las cifras con su fuente valen más que los adjetivos. Los avisos de honestidad del sitio mandan: descriptivo, no alarmista, sin lenguaje de riesgo ni causalidad.

## Qué entregar

1. El protocolo (o los protocolos) en `docs/experimentos/`, con commit anterior a la primera corrida.
2. Los scripts nuevos en `backend/ingestion/` con pruebas en `backend/ingestion/tests/` cuando haya lógica reutilizable.
3. Los resultados en `docs/agentes/mejora-predictor/resultados-nuevos/` y, por cada experimento, un documento de resultados en `docs/experimentos/` con: qué se hizo, tablas por año y horizonte (WIS, skill contra cada referencia, cobertura al 50 % y 95 %, sesgo), cuántas variantes se probaron, el veredicto frente al criterio fijado de antemano y las limitaciones.
4. Un resumen final en `docs/agentes/mejora-predictor/INFORME.md`, de una a dos páginas: qué mejora hay (si la hay) y con qué evidencia, qué se descartó y por qué, qué afirmaciones del sitio se confirman o se contradicen con lo medido, y qué decisiones quedan para la persona dueña del proyecto.
5. Commits en Conventional Commits en español (`feat(nowcast): ...`, `docs(experimentos): ...`). No añadas `Co-Authored-By`, "Generated with Claude Code" ni ninguna línea de atribución de agente en commits, PRs ni descripciones.
6. Un PR en borrador contra `main` desde esta rama, sin mergear. En la descripción: resumen, enlace al informe, lista de experimentos con su veredicto. Como esta rama contiene datos de trabajo (volcado del tablero, resultados previos, revisión bibliográfica), la integración a `main` de lo que corresponda se hará aparte, archivo por archivo.

## Criterio de cierre

La tarea termina cuando: (a) cada línea explorada tiene protocolo, corrida y veredicto documentados, (b) `INFORME.md` existe y sus cifras coinciden con los JSON de resultados, (c) las pruebas del repositorio siguen pasando, y (d) el PR en borrador está abierto. Si te quedas sin presupuesto antes de cubrir todo, deja el informe con lo hecho y una lista de lo pendiente en el orden en que lo harías.
