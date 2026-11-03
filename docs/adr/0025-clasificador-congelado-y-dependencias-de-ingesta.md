# 0025 - Clasificador retirado congelado y dependencias de ingesta fuera de la imagen de la API

**Estado:** Aceptado (2026-10-14)

## Contexto

El clasificador de riesgo de brote interanual se retiró el 2026-08-18
(AGENTS.md §17): no detectó las semanas de riesgo alto en 2019 ni en 2022.
Su código se conserva como referencia histórica y la página `/prediccion`
(`MetricasModelo.astro`) muestra lo que predijo y por qué se retiró, a través
de `GET /api/riesgo-nacional`.

Ese endpoint cargaba en cada arranque el modelo (`joblib.load` de un
RandomForest) y el dataset de modelado, y corría `predict`/`predict_proba` en
cada request. Por eso la imagen de producción instalaba scikit-learn, scipy,
numpy y joblib. Además, `requirements.txt` era un único archivo para la API y
para la ingesta, de modo que pdfplumber, requests y sus dependencias también
entraban en la imagen de Render, aunque la API no los importa. Medido con el
lock vigente (Python 3.11, Linux x86_64): las librerías instaladas ocupaban
423 MB, de los que unos 270 MB eran scikit-learn, scipy y numpy.

El modelo no cambia: está retirado y su entrenamiento no se extiende. Servirlo
en vivo solo daba peso a la imagen y una deserialización con pickle en la API.

La auditoría de deuda técnica del 2026-10-14 planteó tres opciones: congelar
las salidas en un JSON, retirar el endpoint y la página, o dejarlo como
estaba. Se eligió congelar.

## Decisión

A. **Salidas congeladas.** `backend/ingestion/congelar_clasificador.py` corre
el modelo versionado una vez sobre las 250 semanas del dataset de modelado y
escribe `backend/api/datos/riesgo_nacional_congelado.json`. El archivo lleva
las métricas del modelo y la procedencia: script, rutas y SHA-256 del modelo y
del dataset. `GET /api/riesgo-nacional` sirve ese archivo con el mismo
contrato de antes: sin parámetros devuelve la última semana; con `anio` y
`semana`, esa semana o 404; sin el archivo, 200 con `disponible: false`. Se
comprobó que las 252 respuestas posibles (las 250 semanas, la llamada sin
parámetros y un 404) son idénticas a las del modelo en vivo.

B. **El modelo y el dataset siguen versionados** en
`backend/ingestion/data/interim/` (excepción del issue #72), porque son la
fuente del JSON. `ingestion/tests/test_congelar_clasificador.py` regenera el
artefacto y lo compara con el versionado: si alguien cambia el modelo o el
dataset sin volver a congelar, la suite falla.

C. **Tres archivos de dependencias.** `requirements.in` lleva solo lo que
importan la API y el runner de migraciones. `requirements-ingesta.in` lleva lo
de `backend/ingestion/` (pdfplumber, requests, scikit-learn, joblib, numpy), y
`requirements-dev.in`, lo de la suite (pytest, shapely, httpx2). Cada uno se
compila con restricción (`-c`) contra los anteriores, así que ninguno mueve
una versión de otro.

- `Dockerfile.render` (producción) instala solo `requirements.txt`.
- `Dockerfile` (compose) instala `requirements.txt` y
  `requirements-ingesta.txt`, porque es la imagen con la que se corre la
  ingesta de forma reproducible (`docker compose run backend python
  ingestion/...`).
- CI instala los tres y `pip-audit` audita los tres.

Los cargadores que se corren contra la base (`cargar_*.py`) solo usan psycopg2
y python-dotenv, que siguen en la imagen de la API.

D. **Sin herramientas de compilación en las imágenes.** Todas las
dependencias publican wheel para Python 3.11 en Linux x86_64, y psycopg2-binary
trae su libpq. Las dos imágenes dejan de instalar `build-essential` y
`libpq-dev` y pasan `--only-binary=:all:` a pip: si una versión futura deja de
publicar wheel, el build falla en vez de compilarla en silencio. No hace falta
un build en varias etapas, porque no queda ningún paso de compilación que
separar.

## Consecuencias

- Positivo: las librerías de la imagen de producción pasan de 423 MB a
  107 MB, y la API deja de deserializar un pickle en el arranque.
- Positivo: `/prediccion` no cambia para quien lee, y el contrato del endpoint
  es el mismo.
- Negativo: reentrenar el clasificador (que está fuera de alcance mientras
  siga retirado) exige volver a correr `congelar_clasificador.py`; el test de
  B lo recuerda.
- Negativo: quien prepare un entorno local para correr la ingesta o los tests
  tiene que instalar `requirements-ingesta.txt` además de `requirements.txt`.
- Neutral: no cambia el esquema ni otros contratos de la API.
- Pendiente de verificar con Docker: el build de las dos imágenes. Las tres
  combinaciones de archivos se instalaron con `--require-hashes
  --only-binary=:all:` en entornos limpios de Python 3.11, pero la sesión que
  hizo el cambio no tenía Docker.
