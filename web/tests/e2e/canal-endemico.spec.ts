import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const semanas = Array.from({ length: 52 }, (_, i) => ({
  semana_epi: i + 1,
  probable: {
    casos_observados: i % 7 === 0 ? null : 10 + i,
    percentil: 50,
    categoria: 'media',
    p50_baseline: i < 3 ? null : 20,
    p75_baseline: i < 3 ? null : 40,
    n_obs_baseline: 4,
    anios_baseline: 4,
  },
  confirmado: {
    casos_observados: 1,
    percentil: 10,
    categoria: 'baja',
    p50_baseline: 2,
    p75_baseline: 4,
    n_obs_baseline: 4,
    anios_baseline: 4,
  },
}));

test('el canal endémico dibuja las bandas y su tabla', async ({ page }) => {
  await page.route('**/datos/v1/presion/temporal/**', (ruta) =>
    ruta.fulfill({
      json: {
        departamento_codigo: 'SV-SS',
        departamento_nombre: 'San Salvador',
        anio: 2023,
        semanas,
        aviso: 'Aviso de prueba',
      },
    }),
  );
  await page.goto(
    '/dengue?year=2023&week=1&fromWeek=1&toWeek=53&serie=probable&dept=SV-SS&view=temporal',
  );
  await page.locator('#analisis-abrir-filtros').click();
  await page.locator('#analisis-vista').selectOption('temporal');
  // En escritorio los filtros no son un cajón y el botón no se muestra.
  const cerrar = page.locator('#analisis-cerrar-filtros');
  if (await cerrar.isVisible()) await cerrar.click();
  const panel = page.locator('[data-panel-workspace="canal"]');
  await expect(panel).toBeVisible();
  await expect(panel.locator('[data-canal-grafica] svg').first()).toBeVisible();
  await expect(panel.locator('[data-canal-resumen]')).toContainText(
    'San Salvador',
  );
  await panel.locator('summary').click();
  await expect(panel.locator('table')).toContainText('SE05');
  const resultados = await new AxeBuilder({ page })
    .include('[data-panel-workspace="canal"]')
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  expect(resultados.violations).toEqual([]);
});

test('sin datos en la fuente muestra el estado sin dato', async ({ page }) => {
  await page.route('**/datos/v1/presion/temporal/**', (ruta) =>
    ruta.fulfill({
      json: {
        disponible: false,
        motivo: 'Serie no generada en este despliegue.',
      },
    }),
  );
  await page.goto('/dengue?year=2022&dept=SV-SS&serie=probable');
  await page.locator('#analisis-abrir-filtros').click();
  await page.locator('#analisis-vista').selectOption('temporal');
  // En escritorio los filtros no son un cajón y el botón no se muestra.
  const cerrar = page.locator('#analisis-cerrar-filtros');
  if (await cerrar.isVisible()) await cerrar.click();
  const panel = page.locator('[data-panel-workspace="canal"]');
  await expect(panel.locator('[data-canal-grafica]')).toContainText(
    'no generada',
  );
  await expect(panel.locator('[data-canal-grafica] svg')).toHaveCount(0);
});
