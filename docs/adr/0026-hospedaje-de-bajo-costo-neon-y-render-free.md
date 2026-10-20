# 0026 - Hospedaje de bajo costo: base en Neon Free y backend en Render Free

**Estado:** Propuesto (2026-10-20)

## Contexto

Desde el 2026-08-22 el sitio corre en Render (`docs/despliegue-render.md`):
backend en plan Starter ($7 al mes) y base `basic-256mb` (unos $6–7 al mes más
$0.30 por GB de almacenamiento). La cuenta ronda los $17 al mes y el equipo no
puede sostenerla. El sitio estático (`aetheris-nitor`) ya es gratuito.

Ese plan se eligió para el video demo y la Expo Técnica, cuando el backend no
podía tardar en despertar. Esas fechas ya pasaron. La carga es pequeña: el
volcado de datos reales (`db/seed/seed_datos_reales.sql`) pesa 5.7 MB y los
artefactos precalculados de `backend/api/datos/`, cerca de 1 MB. El tráfico es
esporádico.

Condiciones de los planes gratuitos consultadas el 2026-10-19:

- **Render Free (web service):** se duerme tras 15 minutos sin tráfico y tarda
  cerca de un minuto en despertar. Da 750 horas de instancia al mes por
  workspace y admite dominio propio. No tiene Shell, disco persistente ni red
  privada entrante.
- **Render Free (Postgres):** caduca a los 30 días y se borra 14 días después.
  No sirve.
- **Neon Free:** 100 horas de cómputo (CU-hours) al mes por proyecto, 0.5–1 GB
  de almacenamiento, 5 GB de transferencia. Se duerme tras 5 minutos sin
  consultas y despierta sola en menos de un segundo. Si se agota la cuota, el
  cómputo queda suspendido hasta el mes siguiente, sin borrar datos. Recuperación
  a un instante de las últimas 6 horas y una instantánea manual. No admite lista
  de IP permitidas.
- **Supabase Free:** se pausa tras una semana sin actividad y alguien tiene que
  reactivarla a mano.
- **Aiven Free:** se apaga tras un periodo sin actividad que no se publica;
  máximo 20 conexiones.

Dos rasgos del código pesan en la elección:

- `GET /health` ejecuta `SELECT 1` contra la base. Lo que sondee `/health`
  mantiene despierta a la base.
- El pool de `backend/api/main.py` (`ThreadedConnectionPool`) guarda abiertas
  hasta `POSTGRES_POOL_MIN` conexiones (1 por defecto) y no descarta las que
  llegan cerradas al devolverlas. Neon cierra las conexiones al dormirse, así
  que la primera petición tras ese momento fallaría con 503.

## Decisión

A. **La base pasa a Neon Free**, en la región AWS `us-west-2` (Oregón, la misma
del backend) y con Postgres 15, la versión de `docker-compose.yml` y del CI. Si
Neon ya no ofrece la 15 para proyectos nuevos, se usa la menor disponible y se
anota aquí. El cómputo se fija en 0.25 CU: la carga no necesita más y cada CU
adicional gasta la cuota más rápido. La API se conecta por el endpoint directo,
no por el `-pooler`.

B. **El backend pasa a Render Free** con la misma imagen
(`backend/Dockerfile.render`). El sitio estático, el dominio y el correo
transaccional no cambian.

C. **Dos roles, obligatorios.** El rol propietario de Neon queda solo en
`DATABASE_URL_MIGRACIONES`. La API usa `epi_app` en `DATABASE_URL`, creado con
`db/crear_rol_aplicacion.py` (ADR 0024, enmienda del 2026-10-11). En Render la
separación era opcional mientras la base vivía en red privada. Aquí es requisito,
porque la base queda accesible desde internet (punto F).

D. **`POSTGRES_POOL_MIN=0`** en el entorno del backend. Con mínimo cero, el pool
cierra cada conexión al devolverla y abre una nueva en la siguiente petición, de
modo que nunca reutiliza una conexión que Neon cortó. Es configuración, no código.
Cuesta unos milisegundos por petición, y el cache en memoria de las respuestas
evita la mayoría de los viajes a la base.

E. **Sin sondeos que mantengan despierta la base.** No se instala ningún ping
externo para evitar que Render duerma el backend. Además, `healthCheckPath` se
deja vacío, y Render comprueba solo que el puerto responda: si cada sondeo a
`/health` llega a Neon, la base no se duerme mientras el backend esté
despierto, aunque nadie visite el sitio. Con 0.25 CU, la cuota alcanza
para 400 horas despierta al mes, poco más de la mitad del mes. Una base siempre
despierta la agotaría hacia el día 16.

F. **La base acepta conexiones desde internet**, protegidas por TLS (Neon lo
exige), por la contraseña de cada rol y por los privilegios mínimos de
`epi_app`. Es una excepción a la red privada que declaraba `render.yaml`
(`ipAllowList: []`), que existía porque la base guarda las cuentas del ADR 0024.
La coordinación la acepta de forma explícita al aceptar este ADR. La contraseña
del propietario vive solo en el panel de Render y en el gestor de contraseñas.

G. **Migraciones desde el host si hace falta.** Si el `preDeployCommand` no está
disponible en el plan Free (hay que comprobarlo en el panel), las migraciones
nuevas se aplican con `python db/aplicar_migraciones.py` desde una máquina del
equipo, con `DATABASE_URL_MIGRACIONES` apuntando a Neon, antes de mergear a
`main`. El runner vuelve a aplicar los privilegios de `epi_app` en cada corrida,
como hasta ahora.

H. **Respaldos propios.** Neon Free solo guarda 6 horas de historial. El equipo
hace una copia lógica (`pg_dump`) cada semana y antes de cada migración. La
guarda cifrada y fuera del repositorio, porque contiene datos de cuentas. De
esa copia depende "restaurar la última copia verificada" en
`docs/seguridad/respuesta-a-incidentes.md`.

I. **El traslado sigue el procedimiento** de "Mover la base a Neon" en
`docs/despliegue-render.md`: volcado completo (esquema y datos) en una ventana
de mantenimiento, restauración en una base vacía, comprobación de filas y de la
cadena de auditoría, y después cambio de variables en Render. La base de Render
se conserva unos días como respaldo antes de borrarla.

Al aceptarse este ADR, `render.yaml` cambia en el mismo cambio que el
procedimiento ya ejecutado. El bloque `databases` y las variables `fromDatabase`
salen, `plan` pasa a `free`, `healthCheckPath` se quita, se agrega
`POSTGRES_POOL_MIN` y `DATABASE_URL`/`DATABASE_URL_MIGRACIONES` quedan como
`sync: false`. `docs/despliegue-render.md` actualiza su encabezado de costos.

### Alternativas descartadas

- **Supabase Free o Aiven Free para la base:** se pausan o se apagan y alguien
  tiene que reactivarlas. El sitio quedaría sin datos hasta entonces.
- **Render Free para la base:** caduca a los 30 días.
- **Una máquina en Oracle Cloud Always Free con `docker compose`:** en junio de
  2026 recortó la capacidad sin aviso, apaga las máquinas que considera ociosas y
  deja al equipo la operación y los respaldos de Postgres.
- **Backend en Google Cloud Run, Koyeb o Fly.io:** despiertan en segundos en vez
  de un minuto. Exigen tarjeta o una configuración nueva fuera de Render. Quedan
  como siguiente paso si el arranque lento aleja a quienes visitan el sitio.
- **Render Starter con la base en Neon ($7 al mes):** evita la espera del
  backend a mitad de costo. Es la vuelta atrás natural si el presupuesto lo
  permite. Solo cambia el plan del backend; la base no se mueve.

## Consecuencias

- Positivo: el costo de hospedaje baja de unos $17 a $0 al mes. El costo de
  replicación tiende a cero, como pide AGENTS.md §5.
- Positivo: el repositorio, la imagen y el flujo de ramas no cambian. Volver a
  un plan de pago es cambiar el plan del backend en Render, o restaurar una copia
  en una base de pago.
- Negativo: la primera visita tras 15 minutos sin tráfico espera cerca de un
  minuto a que despierte el backend. Las páginas estáticas cargan al instante;
  los paneles con datos esperan.
- Negativo: con tráfico continuo, la cuota de Neon se agota y la base queda
  suspendida hasta el mes siguiente. Hay que revisar el consumo en el panel de
  Neon, sobre todo la primera semana.
- Negativo: la base es alcanzable desde internet. Una contraseña filtrada da
  acceso directo, sin pasar por la API.
- Negativo: los respaldos y, quizá, las migraciones pasan a ser tareas manuales
  del equipo.
- Neutral: el cache en memoria y el límite de peticiones se reinician cada vez
  que el backend se duerme. Ya ocurría en cada despliegue.
