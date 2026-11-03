FROM python:3.14-slim

WORKDIR /app

# Instalar dependencias mínimas del sistema operativo
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# Copiar el código del backend
COPY . .

# Correr como usuario sin privilegios, no como root
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Iniciar servidor con recarga automática en desarrollo
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]