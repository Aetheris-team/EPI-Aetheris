# 0025 - Claves de API con límites de peticiones más altos

**Estado:** Propuesto (2026-10-14)

> Amplía ADR 0017 (rate limiting). No cambia el esquema: las claves viven en
> una variable de entorno. La API sigue abierta sin clave.

## Contexto

La API limita por IP con slowapi en memoria: `RATE_LIMIT_DEFAULT`
(`120/minute`) para todo y `RATE_LIMIT_HEAVY` (`30/minute`) para los
endpoints de cálculo on-demand. Esos umbrales protegen un único proceso
Uvicorn en un plan chico de Render y son adecuados para el sitio.

Los scripts y notebooks del equipo que recorren la API (por ejemplo, una
consulta por semana y departamento) superan `30/minute` en segundos y
reciben 429. Subir los umbrales globales abriría el mismo margen a
cualquiera; apagar el límite por IP para el equipo exigiría una lista de
IPs, que cambian.

## Decisión

* Cabecera `X-API-Key`. Con una clave válida, el request usa
  `RATE_LIMIT_CLAVE_DEFAULT` (default `1200/minute`) en vez de
  `RATE_LIMIT_DEFAULT` y `RATE_LIMIT_CLAVE_HEAVY` (default `300/minute`) en
  vez de `RATE_LIMIT_HEAVY`. Sin cabecera, todo sigue igual.
* `RATE_LIMIT_WRITE` (alertas) y `RATE_LIMIT_AUTH` (cuentas) no cambian con
  clave: una clave de lectura no relaja la superficie de escritura ni de
  ingreso.
* El contador sigue siendo por IP (misma `key_func`, ADR 0017 / issue #67).
  `limits` incluye el umbral en la llave del contador, así que las
  peticiones con clave cuentan aparte de las anónimas de la misma IP.
* `API_CLAVES` guarda `nombre:sha256hex` separados por comas, nunca la clave
  en claro. La comparación usa `secrets.compare_digest` sobre todas las
  huellas. Una entrada mal formada detiene el arranque.
* Una cabecera con clave desconocida responde 401 en vez de tratarse como
  anónima: un error de copia no se confunde con otro 429.
* `X-API-Key` **no** se añade a `allow_headers` de CORS: las claves son para
  clientes fuera del navegador. El frontend no las usa ni las embebe.
* Implementación: slowapi solo resuelve límites dependientes de la clave en
  rutas decoradas, no en `default_limits`. Un middleware ASGI
  (`backend/api/claves_api.py`) valida la clave por fuera de
  `SlowAPIMiddleware` y por dentro de CORS, y deja el nombre en un
  `ContextVar` que leen los proveedores de límite. No se reordena ningún
  middleware existente.
* Ninguna dependencia nueva.

Generar una clave y su huella:

```bash
python -c "import secrets,hashlib;k=secrets.token_urlsafe(32);print('clave:',k);print('huella:',hashlib.sha256(k.encode()).hexdigest())"
```

La clave se guarda fuera del repositorio (gestor de contraseñas); en Render se
pone `API_CLAVES=<nombre>:<huella>` en el panel (`sync: false`).

## Consecuencias

* Positivo: el equipo corre scripts contra producción sin 429 y sin abrir
  más margen al tráfico anónimo. Revocar una clave es quitar su entrada y
  reiniciar el servicio.
* Negativo: con varias claves activas a la vez la carga máxima sobre el
  único proceso crece; los defaults son 10 veces los anónimos y se ajustan
  por entorno. Una clave filtrada da ese margen a quien la tenga hasta que se
  revoque.
* Neutral: los términos de uso públicos (`/legal/terminos`) siguen
  describiendo los límites anónimos, que no cambian. Quién recibe una clave
  lo decide el equipo; este ADR no define un proceso de solicitud público.
