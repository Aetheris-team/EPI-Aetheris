# Procedencia de los datos crudos

`data/raw/` no se trackea en git (ver `.gitignore`); este archivo sí, para dejar
constancia de dónde salió cada dato reunido en la Fase 0 de ingesta.

## OpenDengue (`data/raw/opendengue/`)

- **Archivo:** `opendengue_el_salvador_v1_3.csv`
- **Fuente:** OpenDengue Project, extracto de máxima resolución espacial
  `Spatial_extract_V1_3.zip`, distribuido en Figshare.
- **DOI:** `10.6084/m9.figshare.24259573` (v1.3)
- **URL de descarga directa:** `https://ndownloader.figshare.com/files/54854153`
- **Obtenido:** 2026-08-04
- **Transformación aplicada:** el CSV original (~2.8M filas, todos los países)
  se filtró a `ISO_A0 == "SLV"` (2208 filas) para mantener el repo liviano.
  Sin otra limpieza — es el dato crudo tal como lo entrega Figshare.
- **Cobertura confirmada en la muestra filtrada:** Admin0 (nacional)
  1978–2024, resolución semanal desde 2014 (574 filas semanales 2014–2024,
  las que carga `cargar_opendengue.py`); Admin1 (departamental) solo
  2000–2009, resolución mensual. Ver `docs/biblioteca/04-fuentes-de-datos.md`.

## Boletines MINSAL (`data/raw/minsal/`)

- **Fuente:** boletines epidemiológicos en PDF de `salud.gob.sv`
  (`www.salud.gob.sv/boletines-epidemiologicos-{año}/`), fuente interna
  citada "VIGEPES".
- **Obtenidos con:** `minsal/descargar_{año}.py` / `minsal/common.py` (ver
  esos scripts para el mecanismo de descarga: ruta directa vs. ruta de
  respaldo, validación por firma de bytes `%PDF`).
- **Años reunidos:** 2018, 2019, 2021, 2022, 2023 (2020 queda fuera de la
  ventana departamental por subregistro durante la covid; ver AGENTS.md,
  sección 17).
- **Dos esquemas de tabla:** Familia A (columnas Probable/Confirmado/Tasa)
  y Familia B (Probable/Confirmado sin tasa). El detector decide por
  documento, por la presencia de la columna de tasa, nunca por rango de año.

## Tablero de vigilancia MINSAL (`data/raw/minsal_tablero/`)

- **Fuente:** tablero Superset público `https://boletin.salud.gob.sv/superset/dashboard/{id}/?standalone=1`.
  Desde 2024 MINSAL publica aquí en lugar de en PDF.
- **Obtenido:** capturas HAR guardadas por una persona desde las
  herramientas de desarrollo del navegador al abrir el tablero. Ningún
  script hace peticiones al sitio (ADR 0021).
- **Carga:** `cargar_minsal_tablero.py` (fuente `minsal_tablero`, nivel
  nacional).
- **Capturas** (nombre = tablero y hora UTC de la captura; sha256):

  | Archivo | Datos | sha256 |
  |---|---|---|
  | `tablero-10_20260927T0542Z.har` | 2025, S1–S52 | `4d1c4add575cd82647c46c885cbe152b00f4e1e8d7a136f41774e1d4320eff7f` |
  | `tablero-06_20260927T0654Z.har` | 2026, S1–S37 | `79e677e2c59751e732ba85635efcc37bc16d2d883400acd1348d9b1d504926b4` |
  | `tablero-05_20260927T0655Z.har` | 2026, S1–S37 | `b696593a157b225063e11548b653cd6b94b7d3bab6b9c01aa8fa77b08f4d06e3` |
  | `tablero-04_20260927T0656Z.har` | 2026, S1–S37 | `5cabe8dbfd6a7012f0241d021951dce46600dc5f03cf0b525e9849e9c932e3db` |
  | `tablero-02_20261013T0723Z.har` | 2026, S1–S39 | `bef1e8427b4df9f6886e676c280a66e6169db81ee9871ca41071161bb5607298` |

- **Notas:** los tableros 04, 05 y 06 leen los mismos datos de 2026 aunque
  su rótulo diga otra fecha. Cada captura es una foto del día y MINSAL
  puede revisar semanas ya publicadas; guardar las capturas nuevas sin
  borrar las anteriores.
