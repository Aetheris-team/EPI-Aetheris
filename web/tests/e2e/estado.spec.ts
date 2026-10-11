import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('/estado lista la última semana con dato de cada serie', async ({
  page,
}) => {
  await page.route('**/health', (r) => r.fulfill({ json: { status: 'ok' } }));
  await page.route('**/api/v1/vigilancia/integridad', (r) =>
    r.fulfill({
      json: {
        aviso: 'x',
        resumen_anual: [],
        antiguedad: {
          dengue_tablero_nacional: {
            ultima_anio: 2026,
            ultima_semana_epi: 7,
            semanas: 2,
          },
          clima: { ultima_anio: 2026, ultima_semana_epi: 9, semanas: 0 },
          ira: { ultima_anio: null, ultima_semana_epi: null, semanas: null },
        },
      },
    }),
  );
  await page.goto('/estado');
  const seccion = page.locator('[data-frescura]');
  await expect(seccion.locator('tbody tr')).toHaveCount(3);
  await expect(seccion).toContainText('Dengue nacional (tablero de MINSAL)');
  await expect(seccion).toContainText('SE07 de 2026');
  await expect(seccion).toContainText('2 semanas de rezago');
  await expect(seccion).toContainText('al día');
  await expect(seccion).toContainText('sin datos');
  const resultados = await new AxeBuilder({ page })
    .include('[data-frescura]')
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  expect(resultados.violations).toEqual([]);
});

test('/estado explica el fallo de la consulta sin romper la página', async ({
  page,
}) => {
  await page.route('**/api/v1/vigilancia/integridad', (r) =>
    r.fulfill({ status: 500, body: 'error' }),
  );
  await page.goto('/estado');
  await expect(page.locator('[data-frescura-contenido]')).toContainText(
    'No se pudo consultar',
  );
});

test('/estado no enlaza a la documentación interactiva de la API', async ({
  page,
}) => {
  await page.route('**/health', (r) => r.fulfill({ json: { status: 'ok' } }));
  await page.goto('/estado');
  await expect(page.locator('main a[href$="/docs"]')).toHaveCount(0);
  await expect(page.locator('main a[href$="/redoc"]')).toHaveCount(0);
});
