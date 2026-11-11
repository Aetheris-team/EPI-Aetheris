FROM python:3.15-slim

WORKDIR /app

# Solo las dependencias de la API (ADR 0025). Todas se instalan desde wheels
# (--only-binary): no hace falta compilador ni libpq-dev, psycopg2-binary trae
# su libpq. La ingesta no corre en esta imagen: los datos llegan con el
# volcado de db/seed/.
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.txt

COPY . .

# Correr como usuario sin privilegios, no como root
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
