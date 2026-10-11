# 0024 - Cuentas de usuario y publicación con identidad

**Estado:** Aceptado (2026-10-04)

> Reemplaza a ADR 0015 en dos puntos: el secreto compartido como autorización de escritura y el descarte de una tabla de usuarios. Aceptado antes de la primera migración de cuentas (ADR 0009). Aceptarlo no activa las cuentas: el código sigue apagado con `CUENTAS_HABILITADAS=false` hasta cumplir lo de la sección Cumplimiento. Relacionados: ADR 0013, ADR 0017, ADR 0022.

## Contexto

La escritura de alertas se autoriza con un secreto compartido (ADR 0015). No hay autor verificable, ni historial de cambios, ni retirada con motivo, y una alerta emitida llega a personal de salud. Las tres alertas que hay en producción están firmadas con texto libre.

ADR 0015 descartó una tabla de usuarios para no guardar datos personales. El proyecto necesita ahora atribuir lo publicado a personas concretas, publicar noticias y reportes, y poder demostrar quién dijo qué y cuándo.

Se evaluaron tres caminos: un proveedor gestionado, un proveedor autoalojado (Keycloak o Zitadel) y cuentas propias en el backend. El proveedor gestionado pone a un tercero a custodiar datos de las cuentas y exige adaptar sus pantallas a WCAG AA. Los autoalojados son un servicio más que operar, con una memoria que no cabe en el servicio actual de Render. No existe un marco de cuentas para FastAPI que cubra llaves de acceso y segundo factor y siga en desarrollo activo.

## Decisión

**A. Cuentas propias en el backend.** Alta solo por invitación de un administrador, sin registro público. Tres roles: publicador, revisor y administrador. Los permisos viven en código, en una única tabla de política, y una prueba recorre todas las rutas y comprueba la matriz rol por acción.

**B. Dominio.** La API se sirve en `api.epi-aetheris.dev` y el sitio canónico es `epi-aetheris.dev`. Los sitios estáticos de Render no admiten un 301 por dominio, así que las direcciones `onrender.com` del sitio redirigen desde el navegador al dominio canónico, conservando ruta, consulta y ancla, y cada página declara su `canonical`. Los orígenes `onrender.com` salen de la lista de CORS cuando se activen las cuentas. Un dominio hermano permite cookies de sesión `__Host-` con `HttpOnly` y `SameSite=Strict`. La protección contra CSRF comprueba `Origin` y una cabecera derivada de la sesión.

**C. Credenciales.** Contraseña con Argon2id y una pimienta versionada. Segundo factor obligatorio, con TOTP o llave de acceso, y llaves de acceso obligatorias para administradores. Sesiones opacas en el servidor, revocables.

**D. Publicación con confianza.** Alertas, noticias y reportes llevan firma de la persona y de su institución, versiones inmutables con diferencias públicas y aprobación de una segunda persona según el nivel: atención e intensificación en alertas, y siempre en reportes. Retirar es inmediato, lo hace una sola persona y exige un motivo público.

**E. Auditoría.** Tabla de auditoría encadenada por hash, escrita por disparadores, y roles de base separados para que la aplicación no pueda alterar lo ya registrado.

**F. Correo.** Servicio transaccional con un subdominio de envío propio y SPF, DKIM y DMARC. Se usa para invitaciones, recuperación y avisos de seguridad.

**G. Contenido editorial.** Noticias y reportes se publican desde cuentas propias, no desde un gestor de contenido externo. El servidor convierte un markdown limitado en un árbol validado y el navegador lo pinta con nodos del DOM, sin `innerHTML`. Las imágenes se recodifican a WebP sin metadatos.

**H. Requisitos operativos.** Al menos dos administradores activos y dos personas con permiso de aprobar, distintas del autor de cada pieza. Pueden ser las mismas dos personas con varios roles. Sin eso la regla de segunda persona bloquea las alertas y no se abre la entrega de alertas con identidad.

**I. Retiro del secreto compartido.** Por etapas aditivas: las alertas existentes se atribuyen a un usuario técnico sin credenciales, el secreto queda unos 14 días solo para retirar alertas, y después se elimina del código y de Render. Hay una orden de consola para retirar una alerta en una emergencia. Volver al secreto compartido no se considera una vía.

**J. Dependencias nuevas.** `argon2-cffi`, `pyotp`, `webauthn`, `cryptography`, `segno`, `markdown-it-py` y `Pillow`, más `python-multipart`, `email-validator` y `Jinja2` cuando haya formularios, validación de correo y plantillas. Cada una se fija por versión y se audita en CI. Todas tienen lanzamientos en 2026 salvo `argon2-cffi` y `segno`, con último lanzamiento en 2025.

## Excepciones a AGENTS.md

Esta decisión contradice cuatro reglas y se registran como excepciones acotadas. AGENTS.md las recoge en las secciones 5, 12 y 16.

1. **Privacidad (sección 5).** Se guardan datos personales mínimos: nombre, correo, institución y, si la persona lo elige, cargo. Los lectores no tienen cuenta ni se registra nada de ellos.
2. **Costos y dependencias (sección 5).** El correo transaccional es un servicio externo. Se elige uno con plan gratuito suficiente para el volumen esperado, y el funcionamiento central del sitio no depende de él: leer alertas, noticias y reportes no requiere correo.
3. **Seguridad (sección 12).** CORS pasa a admitir credenciales para el origen canónico, `SecurityHeadersMiddleware` suma una CSP propia para las rutas privadas y aparece el orden de middleware de sesión y CSRF.
4. **Documentación (sección 16).** Se crea `docs/seguridad/` con el procedimiento de respuesta a incidentes. Es un procedimiento operativo que no encaja en un ADR ni en la Biblioteca, y debe estar versionado y revisado como el código. La excepción cubre solo esa carpeta.

## Consecuencias

- Autoría verificable, historial público de lo corregido, retirada controlada y una base para el contenido editorial.
- El proyecto asume operar un sistema de autenticación: mantenimiento, rotación de secretos y revisión externa antes de abrir cuentas reales.
- Se guardan datos personales, hace falta un dominio propio para la API y un servicio de correo, y el backend crece de unos 28 a unos 70 endpoints.
- Las cuentas se pueden desactivar sin perder lo publicado.
- La API pública de lectura no cambia de forma incompatible: `GET /api/alertas` solo suma campos.

## Alternativas consideradas

- **Credencial por persona, sin cuentas ni correo.** Descartada por la persona dueña: no ofrece recuperación, ni segundo factor, ni experiencia de cuenta.
- **Proveedor gestionado.** Descartado por el tercero con datos y por el costo de adaptar sus pantallas a WCAG AA.
- **Proveedor autoalojado (Keycloak o Zitadel).** Alternativa si no hay capacidad de mantener el código propio. Se decide al cerrar la preparación.
- **Gestor de contenido sobre Git para noticias y reportes.** Descartado: no da retirada inmediata, insignia de institución verificada ni auditoría encadenada.

## Cumplimiento

- Pruebas de la matriz de permisos, de contraseñas, segundo factor y sesiones, y de entradas hostiles en markdown e imágenes.
- Revisión externa antes de abrir cuentas reales.
- Política de privacidad y términos publicados antes de la primera invitación.
- Entregas en orden: preparación, identidad, administración, revisión externa, alertas con identidad, noticias, reportes e imágenes. Cada una cierra antes de que abra la siguiente.

## Enmienda 2026-10-11: roles de base de datos (punto E)

Se concreta el punto E con dos roles. El propietario del esquema (el usuario primario de Render) queda reservado a las migraciones, que lee de `DATABASE_URL_MIGRACIONES`. La API usa el rol `epi_app`, que llega en `DATABASE_URL`, con SELECT sobre los datos epidemiológicos, SELECT, INSERT y UPDATE sobre las tablas de cuentas y alertas, DELETE solo en `factores_autenticacion` e `intentos_ingreso` (las únicas donde el código borra filas), SELECT e INSERT en `auditoria`, y sin CREATE sobre el esquema. Si una de las variables falta, se usa la otra y, en último lugar, las `POSTGRES_*` actuales, de modo que nada cambia hasta que se configure. La migración `0018` define `aplicar_privilegios_roles()`, que el runner vuelve a llamar en cada despliegue, porque la creación del rol con su clave no puede vivir en una migración y se hace una vez a mano (`db/crear_rol_aplicacion.py`). No se crea un tercer rol de solo lectura por ahora: exigiría un segundo grupo de conexiones y la elección del grupo en cada ruta. Los límites y el procedimiento están en `docs/seguridad/roles-de-base-de-datos.md`.
