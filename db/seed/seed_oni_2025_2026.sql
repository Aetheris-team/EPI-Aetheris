-- Anomalía mensual del ONI de NOAA CPC (variable oni_anom, región SV, fuente noaa_oni)
-- para 2025 y 2026 (con diciembre de 2024, que cubre la semana 1 de 2025). El volcado principal (seed_datos_reales.sql) llega hasta 2024.
-- Fuente: https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt, descargado el 2026-10-03.
-- Misma regla que backend/ingestion/cargar_oni.py: cada semana epidemiológica toma el valor del
-- mes calendario de su fecha_inicio; las semanas cuyo mes no está publicado quedan sin valor.
-- Cárgalo DESPUÉS de db/seed/seed_datos_reales.sql. Es idempotente.
BEGIN;
INSERT INTO variables_ambientales (region_id, anio, semana_epi, variable, valor, fuente_id)
SELECT r.id, s.anio, s.semana_epi, 'oni_anom', m.anom, f.id
FROM semanas_epidemiologicas s
JOIN (VALUES
  (2024, 12, -0.43),
  (2025, 1, -0.46),
  (2025, 2, -0.22),
  (2025, 3, -0.08),
  (2025, 4, 0.02),
  (2025, 5, -0.04),
  (2025, 6, -0.02),
  (2025, 7, -0.11),
  (2025, 8, -0.26),
  (2025, 9, -0.43),
  (2025, 10, -0.57),
  (2025, 11, -0.61),
  (2025, 12, -0.60),
  (2026, 1, -0.39),
  (2026, 2, -0.21),
  (2026, 3, 0.11),
  (2026, 4, 0.46),
  (2026, 5, 0.95),
  (2026, 6, 1.39),
  (2026, 7, 1.80)
) AS m(anio_mes, mes, anom)
  ON m.anio_mes = EXTRACT(YEAR FROM s.fecha_inicio) AND m.mes = EXTRACT(MONTH FROM s.fecha_inicio)
CROSS JOIN (SELECT id FROM regiones WHERE codigo = 'SV') r
CROSS JOIN (SELECT id FROM fuentes_datos WHERE codigo = 'noaa_oni') f
WHERE s.anio BETWEEN 2025 AND 2026
ON CONFLICT (region_id, anio, semana_epi, variable, fuente_id)
DO UPDATE SET valor = EXCLUDED.valor, fecha_ingesta = now();
COMMIT;
