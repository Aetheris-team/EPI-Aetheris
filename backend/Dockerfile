FROM python:3.14-slim

WORKDIR /app

# Dependencias de Python. Todas se instalan desde wheels (--only-binary): no
# hace falta compilador ni libpq-dev, psycopg2-binary trae su libpq. Esta
# imagen es la de desarrollo y la que corre la ingesta de forma reproducible
# (docker compose run backend python ingestion/...), así que lleva también
# requirements-ingesta.txt; la de Render (Dockerfile.render) no (ADR 0025).
COPY requirements.txt requirements-ingesta.txt ./
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: \
    -r requirements.txt -r requirements-ingesta.txt

# Copiar el código del backend
COPY . .

# Correr como usuario sin privilegios, no como root
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Iniciar servidor con recarga automática en desarrollo
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]