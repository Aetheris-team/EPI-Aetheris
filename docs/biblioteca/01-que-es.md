---
titulo: "Qué es EPI-Aetheris"
descripcion: "Sistema libre de vigilancia epidemiológica descriptiva, contenedorizado y reproducible, piloteado con dengue y eventos respiratorios en El Salvador."
orden: 1
categoria: "El proyecto"
---

EPI-Aetheris es un sistema **open-source, contenedorizado y desplegable con un comando** que alinea casos históricos de dengue y de eventos respiratorios con variables climáticas, por semana epidemiológica, y los expone en una API y un mapa.

El piloto cubre **El Salvador**: 14 departamentos, series de MINSAL 2018–2023 (sin 2020 en la ventana departamental) y la serie nacional de OpenDengue. El diseño del esquema es **agnóstico a enfermedad y a región**: `tipos_evento` y `regiones` son catálogos. Dengue e IRA en El Salvador son el caso que el sistema ya sirve; no son el techo de la arquitectura.

## Qué resuelve

El dengue es endémico en El Salvador. La respuesta institucional es mayoritariamente reactiva, aunque la literatura documenta correlación entre incidencia y clima (temperatura, lluvia, humedad) con rezago de semanas. Falta una herramienta **local, gratuita y reproducible** que cruce esos datos, conserve procedencia y deje inspeccionar la serie contra su propia historia.

Eso es lo que el sistema entrega:

- Ingesta de boletines MINSAL, OpenDengue, Open-Meteo y NOAA ONI, con bitácora de cada boletín.
- Un esquema de hechos que no mezcla definiciones de caso distintas (`probable`, `confirmado`, `total`, `notificado`).
- Módulos descriptivos (idoneidad biofísica, anomalía climática, presión epidemiológica relativa) calculados a pedido.
- Un mapa departamental, un observatorio respiratorio y un canal de alertas de campo redactadas por el equipo de vigilancia.
- Replicación a costo cercano a cero: `git clone` + `docker compose up` deja el sistema funcionando con datos reales versionados.

## Cómo está organizado el producto

El sitio tiene dos caras, que son **secciones**, no un modo que se conmuta:

- **Consulta** (`/alertas`): personal de salud ve las alertas vigentes y qué hacer en la unidad.
- **Análisis** (`/analisis`): dengue (mapa y módulos descriptivos M1–M3) y respiratorio (neumonías, IRA, vigilancia laboratorial de virus).

La **Biblioteca** es esta colección: el relato del proyecto, el catálogo de funciones, las fuentes y el método. El detalle de sensibilidad —límites, deslindes, qué no afirma el sistema— vive en [Sensibilidad y honestidad](/biblioteca/05-sensibilidad-y-honestidad).

## Quién lo construye

El proyecto lo desarrolla el Equipo 4 de 3.er año de Bachillerato Técnico Vocacional en Desarrollo de Software del **INSAMT** (Instituto Nacional de San Miguel Tepezontes, El Salvador), para Expotécnica. Cinco integrantes; tres dedicados de lleno a programación. El repositorio es público: `github.com/aetheris-team/EPI-Aetheris`.

El aporte que el equipo sostiene es de **ingeniería de software**: integración, trazabilidad, despliegue y acceso abierto. La literatura de dengue, clima y aprendizaje automático ya existe; lo que este repositorio publica es un sistema que se clona, se corre y se audita.
