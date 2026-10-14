# 0025 - Refresco recurrente de la capa climática (A2 del ADR 0018)

**Estado:** Propuesto (2026-10-14)

## Contexto

El [ADR 0018](0018-extension-capa-climatica-presente.md) extendió
`ANIOS_CLIMA` hasta el año en curso pero dejó explícitamente fuera de
alcance la decisión A2: "la forma de ese job (GitHub Actions contra
host externo vs `type: cron` en Render) sigue abierta". Desde entonces
nadie volvió a correr `cargar_clima.py` a mano: el seed committeado y
la base quedaron congelados en la corrida del 2026-09-13, dejando
idoneidad biofísica (Iv) y anomalía climática sin datos de ~un mes
(semana epi ~35 en adelante) hasta el backfill manual de hoy
2026-10-14.

El reanálisis ERA5/ERA5-Land vía Open-Meteo no es la causa: tiene solo
~5 días de rezago. El problema es puramente operativo: no existe nada
que vuelva a ejecutar el loader sin intervención humana.

**Restricción que no estaba resuelta en el ADR 0018:** el Postgres
gestionado de Render (`epi-aetheris-db` en `render.yaml`) declara
`ipAllowList: []` — solo acepta conexiones desde la red privada de
Render, nunca desde internet. Esto descarta de entrada un workflow de
GitHub Actions que se conecte directo a la base de producción: abrir
el `ipAllowList` para permitirlo contradice la postura de seguridad ya
tomada (ADR 0024, roles de base de datos con privilegios mínimos).

También existe ya un precedente de autenticación para escritura desde
fuera del propio backend: `backend/api/alertas.py` protege sus
endpoints de escritura con un Bearer token comparado con
`secrets.compare_digest` contra una variable de entorno
(`ALERTAS_TOKEN`), sin sesión ni usuario.

## Decisión

**Opción B: endpoint interno en el backend, disparado por un workflow
de GitHub Actions con `schedule` (cron) vía HTTPS.**

- Nuevo endpoint `POST /internal/clima/refrescar` en el backend,
  protegido con el mismo patrón Bearer + `secrets.compare_digest` que
  `alertas.py`, usando una variable de entorno nueva
  (`CLIMA_REFRESCO_TOKEN`) en vez de reusar `ALERTAS_TOKEN` — son
  superficies distintas y un token comprometido de una no debe dar
  acceso a la otra.
- El endpoint encola la ejecución de `cargar_clima.py` en segundo plano
  (`BackgroundTasks` de FastAPI o un proceso separado lanzado con
  `subprocess`) y responde de inmediato con 202; no bloquea el worker
  de la API mientras dura el rate-limit backoff de Open-Meteo (puede
  tardar varios minutos, ver guarda de reintentos en
  `cargar_clima.py`).
- El workflow de GitHub Actions corre con `schedule: cron: '0 12 * * 1'`
  (semanal, lunes) y hace un solo `curl` autenticado al endpoint. No
  necesita red privada de Render ni credenciales de base de datos: el
  backend ya tiene su propia conexión a Postgres.
- Si el endpoint no puede completar la carga (p.ej. Open-Meteo caído),
  devuelve el error en la respuesta del propio request síncrono previo
  al encolado (validaciones de entrada) o lo deja en el log del
  backend; el workflow falla visiblemente en GitHub Actions si el
  `curl` no devuelve 2xx, lo cual ya manda una notificación por default
  a quien lo mergeó o al dueño del repo.

### Alternativas descartadas

* **Render Cron Job** (`type: cron` en `render.yaml`, misma red
  privada que el backend) — técnicamente más directo: correría
  `cargar_clima.py` contra la base sin pasar por la API. Descartado
  por costo: es un servicio de pago adicional en un proyecto que ya
  eligió planes "starter"/"basic-256mb" por costo-beneficio (comentario
  en `render.yaml`), para un job que corre una vez por semana y tarda
  minutos. Se revisita si el proyecto deja de ser sensible al costo o
  si aparecen más jobs recurrentes que justifiquen el servicio.
* **GitHub Actions con `ipAllowList` abierto** — conectaría directo a
  Postgres sin backend de por medio, pero expone la base gestionada a
  internet (aunque sea detrás de usuario/contraseña) y contradice ADR
  0024. Descartado.
* **Self-hosted runner de GitHub Actions dentro de la red de Render**
  — resolvería el acceso privado sin pagar un cron de Render, pero es
  sobre-ingeniería para un job semanal de minutos: añade un proceso
  persistente que mantener, parchear y monitorear por su cuenta.
  Descartado.

## Consecuencias

* Positivo: sin servicio nuevo en Render ni cambios al
  `ipAllowList`; el refresco corre con la infraestructura que ya
  existe.
* Positivo: mismo patrón de autenticación que `alertas.py`, sin
  introducir un mecanismo nuevo de credenciales.
* Positivo: la falla del job es visible por defecto (GitHub Actions
  marca el workflow en rojo) sin montar alertas propias.
* Negativo: agrega una ruta de escritura más a la superficie pública
  del backend (`/internal/clima/refrescar`), aunque protegida por
  token; si `CLIMA_REFRESCO_TOKEN` no está seteado el endpoint debe
  responder 503 igual que `alertas.py` lo hace con `ALERTAS_TOKEN`
  ausente, nunca ejecutar sin token configurado.
* Negativo: un fallo de GitHub Actions no manda una alerta activa a
  nadie en particular — depende de que alguien revise el estado del
  workflow o reciba el correo default de Actions. Si esto resulta
  insuficiente en la práctica, revisar un job siguiente de
  notificación explícita (p.ej. a un canal), no cubierto por este ADR.
* Neutral: `cargar_clima.py` sigue siendo invocable a mano igual que
  hoy; el endpoint es un disparador adicional, no un reemplazo del uso
  manual para backfills grandes o fuera de rango.

## Acciones pendientes

1. [ ] Implementar `POST /internal/clima/refrescar` en el backend
   (Bearer + `CLIMA_REFRESCO_TOKEN`, ejecución en segundo plano).
2. [ ] Agregar `CLIMA_REFRESCO_TOKEN` a las variables de entorno del
   servicio en Render (panel, no versionado — mismo tratamiento que
   `ALERTAS_TOKEN`).
3. [ ] Crear el workflow de GitHub Actions con `schedule` semanal que
   llame al endpoint.
4. [ ] Documentar el procedimiento y el token en
   `docs/despliegue-render.md`.
