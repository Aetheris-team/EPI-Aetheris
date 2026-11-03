# Postgres con el esquema y los datos dentro de la imagen: no depende de bind
# mounts del anfitrión. En el primer arranque, con el volumen vacío, Postgres
# ejecuta /docker-entrypoint-initdb.d en orden alfabético: las migraciones
# (0001...0018) y después el volcado de datos reales (ADR 0010), que se copia
# con prefijo 9999_ para que corra al final. Con el volumen ya creado no se
# vuelven a ejecutar.
FROM postgres:15-alpine

COPY migrations/*.sql /docker-entrypoint-initdb.d/
COPY seed/seed_datos_reales.sql /docker-entrypoint-initdb.d/9999_seed_datos_reales.sql
