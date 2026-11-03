# EPI-Aetheris — Agent Instructions

Este archivo define cómo deben trabajar los agentes de programación dentro de este repositorio.

Su propósito es indicar **qué fuentes consultar, qué reglas respetar y cómo proceder antes de modificar código**. No duplica los ADR de `docs/adr/`; el contexto técnico vigente está consolidado en la sección 17.

---

## 1. Punto de entrada obligatorio

Antes de realizar cambios relevantes, lee la **sección 17** de este archivo (contexto técnico vigente) y los ADR de `docs/adr/` que toquen el área de la tarea.

No cargues toda la documentación por defecto. Consulta archivos adicionales únicamente cuando sean relevantes para la tarea.

---

## 2. Fuentes de autoridad del proyecto

### Decisiones

Las decisiones vigentes están en los **ADR aceptados** (`docs/adr/`) y en el resumen de la sección 17. No reabras, contradigas o reemplaces una decisión sin una instrucción explícita del coordinador o del usuario.

### Decisiones abiertas

Las que siguen sin resolver se listan en la sección 17 ("Decisiones abiertas"). **No inventes una respuesta para cerrarlas.** Si una tarea depende de una:

1. identifica la dependencia;
2. explica qué información falta;
3. evita convertir una hipótesis en una decisión oficial.

---

## 3. Architecture Decision Records

Las decisiones arquitectónicas formales se registran en:

`docs/adr/`

Plantilla actual:

`docs/adr/0001-plantilla-base.md`

Un ADR puede tener los estados:

* Propuesto
* Aceptado
* Rechazado
* Obsoleto

Los ADR aceptados representan decisiones arquitectónicas vigentes.

### Cambios de esquema

**No modifiques el esquema de base de datos sin comprobar primero los ADR existentes.**

Cualquier cambio que implique, entre otros:

* nuevas tablas;
* nuevas columnas;
* eliminación de columnas;
* nuevas restricciones;
* modificación de `CHECK`;
* cambios estructurales en relaciones;
* cambios en valores controlados a nivel de esquema;

requiere un ADR aceptado antes de implementar la migración.

No escribas primero la migración para documentarla después.

---

## 4. Precedencia de información

Cuando varias fuentes parezcan entrar en conflicto, utiliza este orden como guía:

1. ADR aceptado aplicable.
2. Sección 17 de este archivo.
3. Código y configuración actualmente presentes en `main`.

Si el conflicto no puede resolverse con estas fuentes, **decláralo en lugar de asumir una respuesta**.

No cambies documentación silenciosamente para hacerla coincidir con una implementación contradictoria.

---

## 5. Principios no negociables

### Datos

* Utiliza únicamente datos reales, públicos y agregados.
* No fabriques datasets.
* No simules datos epidemiológicos para hacer que una demo funcione.
* No rellenes datos ausentes mediante supuestos no aprobados.
* No conviertas ausencia de datos en cero salvo que la documentación de la fuente lo establezca explícitamente.
* Conserva trazabilidad y procedencia de los datos.

### Interpretación epidemiológica

EPI-Aetheris es una herramienta de apoyo para estimar y comunicar riesgo.

No presentes su salida como:

* diagnóstico;
* certeza clínica;
* predicción infalible;
* recomendación médica;
* descubrimiento epidemiológico novedoso.

Eso aplica a la *salida de los módulos y del clasificador*. Es distinto —y sí está permitido— mostrar material informativo de prevención tomado literalmente de una fuente oficial publicada (OPS/OMS, MINSAL) con su cita: tarjetas tipo "elimine criaderos, revise depósitos de agua". No se redacta consejo clínico propio ni se generan recomendaciones automáticas por nivel de riesgo.

**Redacción de producto:** el copy de cara al usuario se escribe en voz afirmativa — primero qué es y qué aporta, después el límite. Cada salvedad ("no es diagnóstico", "no es clasificación de riesgo de brote", "la predicción a corto plazo parte de la última semana observada de la serie pública", "coexistencia ≠ causalidad") se declara una sola vez, en su hogar canónico (footer, panel de alertas, Biblioteca — `docs/biblioteca/05-sensibilidad-y-honestidad.md`), no en cada pantalla. El rigor se muestra con métricas y fuentes visibles, no repitiendo disclaimers.

El aporte principal del proyecto es de ingeniería de software: reproducibilidad, integración, despliegue y acceso abierto.

### Costos y dependencias

El sistema debe mantenerse reproducible y con costo de replicación tendiendo a cero.

Antes de introducir una dependencia:

1. determina si ya existe una herramienta equivalente en el proyecto;
2. comprueba decisiones cerradas relacionadas;
3. justifica la necesidad;
4. evalúa mantenimiento, licencia, tamaño y complejidad;
5. evita servicios pagos, freemium obligatorios o suscripciones necesarias para el funcionamiento central.

No instales una dependencia únicamente porque simplifica unas pocas líneas de código.

Excepción acotada (ADR 0024): el correo transaccional de las cuentas usa un servicio externo con subdominio de envío propio y plan gratuito. El funcionamiento central del sitio no depende de él: leer alertas, noticias y reportes no requiere correo.

### Privacidad

No introduzcas datos personales.

El sistema trabaja con información pública y agregada y debe conservar esa característica.

Excepción acotada (ADR 0024): las cuentas de quienes publican guardan nombre, correo, institución y, si la persona lo elige, cargo. Quienes leen el sitio no tienen cuenta ni se registra nada de ellos.

### Reproducibilidad

Docker forma parte del funcionamiento esperado del proyecto.

Un cambio que funcione únicamente en la máquina local del desarrollador no se considera una implementación completa.

---

## 6. Alcance epidemiológico actual

No asumas que todas las capas geográficas representan la misma cosa.

El clasificador de la primera fase opera a **nivel nacional**.

El mapa puede mostrar información departamental como capa descriptiva, pero eso no significa que exista una predicción departamental del modelo.

Nunca transformes una clasificación nacional en etiquetas departamentales salvo que exista una implementación y decisión explícita que lo respalde.

Consulta siempre la documentación vigente antes de modificar esta relación.

---

## 7. Arquitectura general

Antes de modificar una parte importante del sistema, inspecciona su implementación actual.

La arquitectura principal está compuesta por:

* PostgreSQL para persistencia;
* FastAPI/Python en `backend/`;
* Astro + TypeScript en `web/`;
* Docker Compose para orquestación.

No introduzcas otro framework, ORM, motor de base de datos, plataforma o arquitectura principal sin comprobar primero las decisiones existentes.

La presencia de una alternativa técnicamente válida no significa que deba introducirse.

---

## 8. Base de datos

Las migraciones están en:

`db/migrations/`

Antes de cambiar una migración o escribir una nueva:

1. revisa los ADR relacionados;
2. inspecciona el esquema vigente;
3. identifica qué código depende del esquema;
4. comprueba pipelines de ingestión;
5. comprueba consultas del backend;
6. determina compatibilidad con datos existentes.

No inventes valores controlados.

Cuando exista una lista documentada de valores válidos, utiliza exactamente esos valores.

---

## 9. Ingestión y datos

Los pipelines de ingestión contienen conocimiento de dominio que no siempre resulta evidente observando solamente el código.

Antes de corregir un comportamiento que parezca extraño, consulta las trampas resumidas en la sección 17 ("Fuentes de datos").

En particular, evita asumir comportamientos uniformes en:

* boletines MINSAL;
* semanas epidemiológicas;
* OpenDengue;
* Open-Meteo;
* datos acumulados;
* valores faltantes;
* revisiones de boletines;
* agregación temporal.

Una implementación más simple no es necesariamente una implementación correcta.

---

## 10. Frontend

El frontend se encuentra en:

`web/`

Tecnologías principales:

* Astro;
* TypeScript;
* Tailwind;
* Leaflet.

Antes de instalar una librería nueva, revisa si existe una decisión previa sobre el stack.

No introduzcas React, Vue u otro framework de componentes salvo decisión explícita del equipo.

**Arquitectura de información (ADR 0014).** El sitio tiene dos caras —consulta
(`/alertas`) y análisis (`/analisis`, que agrupa `/dengue` y `/respiratorio`;
IRA y neumonías son secciones de `/respiratorio`)— pero **no** un interruptor de
"modo": son secciones, sin estado
persistido, y ninguna esconde a la otra. No agregues un toggle de enfoque en la
barra. Ninguna vista se titula "hoy" ni "esta semana": la ventana cargada llega
hasta 2023 y `regiones.nivel_admin = 2` (municipio) sigue reservado sin filas.

**Service worker (`web/public/sw.js`).** Escrito a mano, sin dependencias.
`GET /api/alertas` va **network-first** —una alerta ya apagada tiene
consecuencia clínica— y lo servido desde cache se marca con `_desde_cache: true`
en el cuerpo JSON para que `/alertas` muestre el sello de frescura. La marca va
en el cuerpo y no en una cabecera porque la API es de otro origen y el navegador
filtra por CORS las cabeceras propias; el backend nunca emite ese campo. No
cambies la estrategia a cache-first ni quites el sello. Al desplegar, sube
`VERSION` en `sw.js`.

Al representar resultados epidemiológicos:

* diferencia claramente datos descriptivos y salidas del modelo;
* muestra incertidumbre cuando corresponda;
* evita lenguaje que sugiera certeza;
* no conviertas etiquetas nacionales en riesgo departamental;
* conserva accesibilidad y legibilidad.

---

## 11. Backend

El backend se encuentra en:

`backend/`

La API principal utiliza FastAPI.

Antes de modificar endpoints:

1. revisa consumidores actuales;
2. conserva contratos existentes salvo que el cambio sea intencional;
3. comprueba validación de entrada;
4. comprueba manejo de errores;
5. revisa implicaciones de seguridad;
6. revisa cambios de serialización;
7. ejecuta pruebas relevantes.

No confundas CORS con otras medidas de seguridad HTTP. Una capa no sustituye automáticamente a otra.

---

## 12. Seguridad

Cuando una tarea toque autenticación, middleware, CORS, cabeceras HTTP, secretos, configuración del servidor o exposición de endpoints:

* analiza explícitamente las consecuencias de seguridad;
* no elimines controles únicamente para resolver un error de desarrollo;
* no guardes secretos en el repositorio;
* utiliza `.env.example` únicamente como referencia de variables;
* nunca copies credenciales reales a código, documentación, tests o commits.
* `POST`/`PATCH /api/alertas` llevan umbral propio `RATE_LIMIT_WRITE` (default `10/minute`); `SecurityHeadersMiddleware` incluye `Referrer-Policy` y `Permissions-Policy`; CORS `allow_headers` es lista explícita (`Authorization`, `Content-Type`), no `*`. No reordenes los middleware.
* Excepción acotada (ADR 0024): con `CUENTAS_HABILITADAS=true`, CORS admite credenciales solo para el origen canónico y `allow_headers` suma `X-CSRF-Token`. La CSP propia para las rutas privadas y el orden de los middleware de sesión y CSRF se documentan al activar las cuentas.

---

## 13. Forma de trabajar

Para tareas de implementación utiliza, salvo instrucción distinta, este flujo:

**analizar → proponer → implementar → validar → revisar diff**

### Analizar

Antes de modificar:

* inspecciona archivos relevantes;
* identifica dependencias;
* consulta documentación aplicable;
* comprueba decisiones cerradas y abiertas.

### Proponer

Cuando la tarea implique una decisión técnica no trivial:

* explica brevemente el enfoque;
* identifica archivos afectados;
* señala riesgos o trade-offs.

No conviertas automáticamente una propuesta en una decisión arquitectónica.

### Implementar

Realiza el cambio mínimo necesario para cumplir la tarea.

Evita:

* refactors no solicitados;
* cambios cosméticos masivos;
* renombrados innecesarios;
* añadir dependencias sin necesidad;
* modificar componentes fuera del alcance sin justificación.

### Validar

Después de implementar:

* ejecuta tests relevantes;
* ejecuta linters/typecheck cuando existan;
* comprueba comportamiento directamente relacionado;
* revisa errores introducidos.

Si una validación no puede ejecutarse, indícalo explícitamente.

### Revisar diff

Antes de considerar finalizada una tarea:

* inspecciona el diff;
* comprueba que no haya archivos ajenos modificados;
* busca cambios accidentales;
* resume qué cambió y qué queda pendiente.

---

## 14. Tareas de análisis o revisión

Si el usuario solicita:

* revisar;
* analizar;
* investigar;
* comparar;
* auditar;
* explicar;
* evaluar un PR;
* buscar problemas;

no modifiques archivos automáticamente.

Primero entrega los hallazgos.

Solo implementa cambios cuando la solicitud incluya explícitamente corregir, modificar, implementar o equivalente.

---

## 15. Git

### Flujo de ramas

* `main` es la rama de **release**: es lo que Render despliega (ver `render.yaml`). Solo recibe PRs desde `dev`.
* `dev` es la rama de **integración** y la rama por defecto del repo. Todas las PRs de features y fixes van contra `dev`.
* Cuando `dev` está estable se abre una PR `dev → main`; ese merge dispara el despliegue.
* Ramas de trabajo: `feat/*`, `fix/*`, `chore/*`, `docs/*`, partiendo de `dev`.

Respeta el estado actual del repositorio.

Antes de modificar:

* revisa `git status`;
* no sobrescribas trabajo ajeno;
* no descartes cambios locales que no hayas creado;
* no uses comandos destructivos para limpiar el árbol sin autorización.

No hagas commit, push, merge, rebase o force push salvo que el usuario lo solicite.

### Atribución

Los mensajes de commit y las descripciones y comentarios de PR **no llevan líneas de atribución**: ni `Co-Authored-By`, ni `Claude-Session`, ni «Generated with Claude Code» ni enlaces a sesiones. Terminan en su última línea de contenido. Esta regla prevalece sobre la configuración por defecto de cualquier herramienta o agente.

### Archivos de tarea locales

Los `.md` que se te pasan para delegar o describir una tarea (planes, listas de
indicaciones, informes de auditoría intermedios) **no se versionan**: son
andamiaje, no entregable. Lo que queda en el repo al terminar es el código, el
ADR, la migración y las pruebas — nunca el `.md` de la tarea.

* Nombralos con sufijo **`.local.md`** (p. ej. `PLAN_ALERTAS_OPERABLES.local.md`,
  `AUDITORIA_TONO.local.md`). `.gitignore` ignora `*.local.md`.
* Viven en la raíz del repo (o del worktree) y aparecen ignorados, no como `??`.
* El hook `.githooks/pre-commit` aborta el commit si uno llega al stage con
  `git add -f`. Activalo una vez por clon: `git config core.hooksPath .githooks`.
* No los agregues a `.gitignore` uno por uno ni con `git add -A` los subas.

Al trabajar con un Pull Request, distingue siempre entre:

* estado de `main`;
* rama del PR;
* cambios del diff;
* cambios que surgirían después del merge.

---

## 16. Documentación

No crees un sistema paralelo de documentación sin necesidad.

En este repositorio `docs/` contiene sólo lo esencial:

```text
docs/
├── adr/                    # decisiones arquitectónicas formales
├── biblioteca/             # documentos públicos de /biblioteca (colección de Astro; no mover)
├── experimentos/           # experimentos firmados que respaldan un ADR aceptado (ver abajo)
├── seguridad/              # procedimiento de respuesta a incidentes (excepción del ADR 0024)
└── despliegue-render.md    # procedimiento de despliegue (referenciado por render.yaml)
```

Cuando surja conocimiento nuevo:

* decisión arquitectónica o de proyecto → ADR en `docs/adr/`;
* contexto técnico que un agente necesita antes de tocar código → sección 17 de este archivo, breve;
* historial de cambios → los mensajes de commit (no hay CHANGELOG);
* protocolos y resultados de experimentos, notas de sesión, planes → no se versionan.

Excepción acotada: `docs/experimentos/` guarda **solo** experimentos firmados (protocolo fechado y resultado) que respaldan un ADR aceptado y que ese ADR o el código citan, como la mezcla C del nowcast (ADR 0020, ADR 0021). Un experimento exploratorio, uno sin firmar o uno que ningún ADR usa sigue sin versionarse.

No crees carpetas de documentación nuevas fuera de `docs/adr/`, `docs/biblioteca/`, `docs/experimentos/` y `docs/seguridad/`. Esta última, por el ADR 0024, contiene solo el procedimiento de respuesta a incidentes.

---

## 17. Contexto técnico del proyecto

Referencia rápida de lo vigente. Ante una contradicción, aplica la precedencia de la sección 4.

### Qué es y qué no es

EPI-Aetheris es un sistema de vigilancia epidemiológica **descriptiva** (piloto: dengue e IRA en El Salvador). Ingesta casos históricos y predictores ambientales, los alinea por semana epidemiológica y los expone vía FastAPI + mapa Leaflet.

- **El clasificador de riesgo de brote interanual está retirado** (pivote a herramienta descriptiva, cerrado 2026-08-18). Clasificaba semanas en alto/medio/bajo y obtuvo recall de "alto" = 0 en 2019 y 2022. El código entrenado (`entrenar_clasificador.py` y afines) se conserva como referencia histórica: **no lo extiendas ni lo reactives.** Es un modelo distinto de la predicción de conteo de abajo. `/prediccion` lo sigue mostrando a partir de salidas **congeladas** (ADR 0025): `congelar_clasificador.py` escribe `backend/api/datos/riesgo_nacional_congelado.json` y `GET /api/riesgo-nacional` lo sirve tal cual; la API no carga el modelo ni importa scikit-learn/joblib.
- **Predicción de casos a corto plazo** (autorizada por Eduardo el 2026-09-09): la página de dengue predice el conteo nacional de casos a 1–8 semanas desde la última semana observada, con intervalo calibrado. Validada con WIS + segunda confirmación independiente (ADR 0020). Artefactos: `nowcast_estimacion_dengue.py` y `nowcast_retrospectivo_dengue.py` generan la base de OpenDengue (`backend/api/datos/*_opendengue.json`) y `nowcast_tablero_dengue.py` la combina con la serie del tablero de MINSAL en `nowcast_dengue.json` y `nowcast_dengue_retrospectivo.json`; endpoint `GET /api/nowcast-dengue`. Desde 2025 el método publicado es la mezcla C de `docs/experimentos/experimento-nowcast-tendencia.md`, en prueba hasta el corte de 2027-S05. Se llama **predicción**: al inicio del proyecto se creyó que ni un proto-predictor era viable y de ahí venía el veto a esa palabra; el experimento mostró lo contrario para la serie nacional agregada. Nota técnica para mantenimiento (no es copy de producto): el método sólo gana a la persistencia cuando el historial de entrenamiento ya contiene una temporada de brote grande — no reutilizarlo en otra serie sin verificar esa condición.
- **Clima y dengue, análisis descriptivo** (ADR 0023): dos artefactos precomputados, `backend/api/datos/clima_dengue_por_anio.json` (El Salvador, 9 años) y `clima_dengue_multipais.json` (18 países de OpenDengue/OPS), servidos por `GET /api/clima-dengue/por-anio` y `/multipais`. Describen asociaciones en datos pasados; no atribuyen causa y no alimentan el predictor ni las alertas. Antes de afirmar que El Salvador tiene la menor correlación con la señal regional, revisa la sensibilidad de 9 años (posición 5 de 18).
- El proyecto es descriptivo salvo esa capa: "qué está pasando y qué tan inusual es contra su propia historia", más una predicción del conteo nacional a pocas semanas con su incertidumbre.
- El aporte es de **ingeniería de software** (sistema libre, contenedorizado, reproducible), no de novedad epidemiológica ni un oráculo médico (esto no impide mostrar guías de prevención públicas citadas).
- Modelo de dominio **agnóstico a enfermedad y región**: `tipos_evento` y `regiones` son catálogos, no columnas fijas.

### Módulos descriptivos (M1–M4)

- **M1 — Idoneidad biofísica (`Iv`)** y **M2 — Anomalía climática continua (Z-score leave-one-out)** — implementados en `backend/api/idoneidad.py`, servidos vía `GET /api/v1/spatial/current` y `/api/v1/temporal/{codigo}`. M2 es serie continua: sin alerta binaria, sin lenguaje de lead-time.
- **M3 — Presión epidemiológica relativa** — implementado en `backend/api/presion.py` (fórmula **cerrada** por la coordinación 2026-08-21): percentil histórico leave-one-out por departamento, `probable` y `confirmado` como series **separadas** (nunca `total`), años base 2018/2019/2021/2022/2023, ventana ±1 semana, piso de ≥3 años, cortes P50/P75. Salida = percentil + lectura cualitativa (baja/media/alta), **nunca alerta binaria**; celdas insuficientes → `null` + nota. Vía `GET /api/v1/presion/current` y `/api/v1/presion/temporal/{codigo}`. No ajustes estos parámetros sin nueva decisión de la coordinación.
- **M4 — Integridad de vigilancia** — implementado en `backend/api/vigilancia.py` (fórmula **cerrada** 2026-09-08, ADR 0019): tres métricas separadas, sin número compuesto. `completitud` = n/14 departamentos con fila esa semana-serie (dengue MINSAL, `probable`/`confirmado`); `cuadre` = expone `validacion_cuadra` y la discrepancia ya almacenada en `boletines_procesados` (no recalcula la suma); `antiguedad` = semanas PAHO/CDC (`epiweeks`) desde la última SE con dato, por serie — **no** es latencia de reporte. Vía `GET /api/v1/vigilancia/integridad` (`week`+`year` = vista semanal; sin parámetros = resumen anual + antigüedad). Capa del mapa `'confianza'`. No combines las tres en un índice ni uses lenguaje de riesgo.
- **Alertas de campo** — tabla `alertas` (ADR 0013, migración `0009`; operable por ADR 0015, migración `0011`). Decisiones humanas persistidas; **no** se generan desde M1–M3 ni del clasificador. `GET /api/alertas` por defecto: `activa=true` y `etiqueta IS NULL`, filtro opcional `tipo`; parámetros opcionales `desde`/`hasta` (solapamiento de vigencia), `incluir_inactivas=true`, `incluir_etiquetadas=true` (AND). UI en `/alertas`; archivo en `/alertas/archivo`; formulario de alta (sin enlace en la nav) en `/alertas/nueva`. `POST /api/alertas` y `PATCH /api/alertas/{id}` exigen `Authorization: Bearer` contra `ALERTAS_TOKEN` (`secrets.compare_digest`); sin token en el entorno → 503; cabecera ausente o token incorrecto → 401; no hay `DELETE`. Esos dos endpoints llevan además `@limiter.limit(RATE_LIMIT_WRITE)` (default `10/minute`; ADR 0017); el GET público se queda con el límite global. `etiqueta`: `NULL` | `test` | `simulacro` | `historica`. Migración `0010` (ADR 0014) añadió cinco columnas `TEXT` nulas; `0011` las llena **por `tipo`** con transcripción citada (VIGEPES/OPS): dengue tiene los cuatro bloques clínicos; respiratorio deja `signos_alarma` y `criterios_referencia` en `NULL`; `contacto_vigilancia` es la ruta SIBASI/VIGEPES-01 **sin teléfono ni correo**. No inventes texto clínico ni datos de contacto. `AVISO_HONESTIDAD_ALERTAS` no se altera.

Nada de M1–M4 se persiste (se calcula on-request, sin cambios de esquema). El selector de capas del mapa (`web/src/components/MapaDepartamentos.astro`) tiene botones para M1/M2, las dos series de M3 y la integridad de vigilancia (M4). IRA se sirve aparte (`backend/api/ira.py`, UI en `/respiratorio`) y **no** computa los módulos M1–M4. Las alertas de campo sí se persisten: las redacta el equipo, no un módulo.

### Arquitectura

Tres servicios Docker (`docker-compose.yml`, red `aetheris_network`):

- **`db`** — PostgreSQL 15. El esquema se carga desde `db/migrations/*.sql` **solo una vez, sobre volumen vacío**. Para una base ya inicializada usa el runner de ADR 0009: `python db/aplicar_migraciones.py --bootstrap` una vez, luego `python db/aplicar_migraciones.py` tras añadir cada migración (corre desde el host contra `localhost:5432`, sin rollback — una migración mala se corrige con otra migración).
- **`backend`** (`./backend`) — FastAPI + `psycopg2` directo, sin ORM. Entrada: `backend/api/main.py` (app, middleware, pool, rate limiting, `/health`). Los endpoints viven en routers por dominio en `backend/api/rutas/` (`dengue`, `modulos`, `respiratorio`, `alertas`; las cuentas en `api/cuentas/rutas.py`): cada uno expone `crear_router(limiter=..., abrir_conexion=..., límite)` y `main.py` los crea al importarse, así que un `importlib.reload(api.main)` en los tests los rehace con la configuración nueva. Cache-Control, cache de respuestas y la traducción de fallos de Postgres a HTTP están en `backend/api/respuestas.py`. Los tests parchean `api.main._conexion` (llega a los routers vía `_abrir_conexion`) y las constantes de cada router en su módulo (p. ej. `api.rutas.dengue.NOWCAST_DENGUE_PATH`). Los GET públicos de solo lectura pasan por un cache en memoria (`backend/api/cache_respuestas.py`) con el mismo TTL de su `Cache-Control`: un dato recién ingerido tarda hasta ese TTL en verse (o reinicia el servicio). No lo uses para alertas, `/health` ni cuentas; los tests lo vacían en `api/tests/conftest.py`.
- **`web`** (`./web`) — Astro + TypeScript + Leaflet.

### Valores controlados del esquema — reutiliza verbatim, nunca inventes

`variables_ambientales.variable` es texto libre **sin `CHECK`**: un typo crea una segunda serie separada en silencio. Usa exactamente estas cadenas:

`temp_max`, `temp_min`, `temp_media`, `precipitation_sum`, `precipitation_hours`, `humedad_relativa_media`, `punto_rocio`, `oni_anom`

(`et0_fao` está deprecado, nunca se carga. `oni_anom` = anomalía ONI de NOAA, ADR 0008, bajo región `SV` nacional. Añadir un predictor = añadir su string a esta lista en la misma sesión, no en el call site.)

- `casos_epidemiologicos.clasificacion`: `probable`, `confirmado`, `total` (agregado de OpenDengue, solo `fuente_id=opendengue_v1_3` nacional — **NO** equivale a `confirmado`), `notificado` (departamental sin split probable/confirmado, p.ej. IRA — ADR 0011). Nunca sumes `conteo` entre valores de `clasificacion` sin filtrar primero.
- `boletines_procesados.estado`: `pendiente`, `ok`, `revision_manual`, `error`, `ausencia_esperada` (ADR 0004), `sin_texto_extraible` (ADR 0007).
- `boletines_procesados.familia_esquema`: `A` o `B`.
- `fuentes_datos.codigo`: `opendengue_v1_3`, `minsal_pdf`, `open_meteo_era5_land`, `open_meteo_era5` (ADR 0006 — `era5` es exclusivo para `precipitation_sum`/`precipitation_hours`), `noaa_oni`.
- `regiones.codigo`: ISO 3166-2:SV (**sin verificar aún** contra el GeoJSON de Leaflet — confírmalo antes de usarlo como clave de join).
- `alertas.tipo`: `dengue`, `respiratorio`. `alertas.nivel`: `informativo`, `atencion`, `intensificacion` (ADR 0013). `alertas.etiqueta`: `NULL` | `test` | `simulacro` | `historica` (ADR 0015; `NULL` = producción). `activa` es el filtro de la vista pública; no lo infieras de `vigente_hasta`.
- Semanas epidemiológicas: **PAHO/CDC (MMWR), no ISO 8601** — usa la librería `epiweeks`, no recalcules límites a mano.

### Fuentes de datos

Trampas empíricas de las fuentes: MINSAL (el año impreso en el PDF no es fiable; dos familias de tabla detectadas **por documento**, nunca por rango de año; celdas vacías = `0`; fila "Otros países"; Probable/Confirmado son **acumulados desde SE1** que hay que desacumular por diferencias; boletines de vacaciones sin tabla; ~49/52 semanas reales), OpenDengue (`case_definition_standardised` siempre `Total`; resolver la semana por coincidencia exacta de `calendar_start_date`), Open-Meteo (`era5_land` para temp/humedad/rocío + `era5` para precipitación, nunca `best_match`; ceros falsos de precipitación; rate-limit `429` por minuto). Tenlas presentes antes de tocar cualquier pipeline de ingesta. No reimplementes la desacumulación MINSAL desde cero: existe validada en `backend/ingestion/corrida_distribucion.py` y en producción en `backend/ingestion/minsal/parser.py`.

**2020 está deliberadamente ausente** de la ventana departamental (subregistro real por covid + riesgo de extracción) — no lo "arregles". Es una exclusión de ventana de entrenamiento: no filtres 2020 durante la ingesta. La serie nacional de OpenDengue sí muestra 2020 con nota explicativa.

### Convenciones del repo

- Contenido de dominio (tablas, columnas, comentarios, docstrings) en **español**.
- Extiende los catálogos (`tipos_evento` / `regiones` / `fuentes_datos`) en vez de añadir columnas por enfermedad o país.
- Datos crudos e intermedios **no se versionan** (`backend/ingestion/data/raw/` y `.../interim/` gitignoreados). Excepción: el modelo y el dataset del clasificador retirado en `.../interim/` (issue #72; fuente del artefacto congelado, ADR 0025). Excepción deliberada: `db/seed/seed_datos_reales.sql` (ADR 0010, volcado `pg_dump --data-only` de las tablas de hechos, montado en `/docker-entrypoint-initdb.d/` para que `git clone` + `docker compose up` dé un sistema con datos reales).
- Valida PDFs descargados por firma de bytes (`%PDF`), no por `Content-Type` (el servidor devuelve `application/octet-stream`).

### Decisiones abiertas

No resuelvas unilateralmente: las coordenadas departamentales para Open-Meteo, si la exclusión de 2020 gobierna la ingesta, y si el clasificador de riesgo de brote interanual se reactiva (esa línea está cerrada — no la resucites sin instrucción explícita; la predicción de conteo a corto plazo autorizada el 2026-09-09 es una línea separada, no esa reapertura). M4 (fórmula y dónde vive) quedó cerrado el 2026-09-08, ADR 0019.

### Comandos

```bash
docker-compose up --build          # todo: API :8000 (/health), web :4321, Postgres :5432
```

Variables de entorno desde `.env` (copiar de `.env.example`; nunca commitear `.env`).

- **Backend fuera de Docker:** `cd backend && pip install -r requirements.txt && uvicorn api.main:app --reload` (entorno Arch — prefiere virtualenv).
- **Web fuera de Docker:** `cd web && pnpm install && pnpm dev|build|preview` (pnpm vía Corepack, fijado a v9 — **no `npm`**).
- **Dependencias Python (ADR 0025):** `requirements.txt` = API (lo único que entra en la imagen de Render); `requirements-ingesta.txt` = `backend/ingestion/`; `requirements-dev.txt` = suite. Se compilan desde sus `.in` con `uv pip compile --generate-hashes` en ese orden (comando en `requirements.in`); no edites los `.txt` a mano.
- **Tests:** pytest **desde `backend/`** (`pip install --require-hashes -r requirements.txt -r requirements-ingesta.txt -r requirements-dev.txt`, luego `python -m pytest ingestion/tests/ api/tests/`). Los tests con BD se **saltan** (no fallan) si no hay Postgres en `localhost:5432`. CI (`.github/workflows/`): `backend-tests.yml` corre esa suite contra Postgres con migraciones + seed, y `seguridad.yml` audita dependencias y secretos. No hay linter de Python; `web/` trae ESLint/Prettier (`pnpm lint`, `pnpm format:check`), que ningún workflow de este repo corre.
- **Multi-worktree (Orca ADE):** `docker-compose.yml` usa `container_name` y puertos fijos compartidos a nivel del daemon Docker — **solo un worktree corre `docker-compose up` a la vez**. No lo "arregles" namespaceando puertos/nombres por worktree sin preguntar.

---

## 18. Manejo de contradicciones

Si encuentras que:

* código y documentación discrepan;
* dos documentos se contradicen;
* un ADR aceptado contradice comportamiento actual;
* una decisión cerrada parece haber sido implementada de otra manera;

no "corrijas" automáticamente una de las partes.

Haz lo siguiente:

1. identifica exactamente la contradicción;
2. determina cuál fuente debería tener precedencia;
3. comprueba el historial cuando sea necesario;
4. informa del conflicto;
5. modifica solo cuando exista una conclusión suficientemente respaldada.

---

## 19. No asumir

Cuando falte información:

* no inventes datos;
* no inventes requisitos;
* no inventes una decisión del equipo;
* no conviertas una aproximación en hecho;
* no escondas incertidumbre.

Distingue claramente entre:

* estado actual;
* evidencia;
* decisión aprobada;
* hipótesis;
* propuesta;
* pendiente.

---

## 20. Objetivo del agente

Tu función dentro de EPI-Aetheris es ayudar a producir cambios:

* técnicamente correctos;
* reproducibles;
* verificables;
* coherentes con las decisiones existentes;
* honestos respecto a limitaciones y datos;
* simples de mantener por el equipo.

La prioridad no es generar la mayor cantidad de código posible.

La prioridad es **mejorar el proyecto sin romper su coherencia técnica ni documental**.
