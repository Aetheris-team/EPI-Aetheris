import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { simularApi } from './nowcast-mock';

// Gráficas de la predicción (ECharts, renderizador SVG). La API se simula:
// aquí se prueba lo visible y accesible, no los trazos del SVG.

test('el abanico es una imagen con etiqueta en español y alternativa en tabla', async ({
  page,
}) => {
  await simularApi(page);
  await page.goto('/prediccion');
  const panel = page.locator('[data-nowcast]');

  const grafico = panel.locator('svg[role="img"]').first();
  await expect(grafico).toBeVisible({ timeout: 15_000 });
  await expect(grafico).toHaveAttribute('aria-label', /predicción/i);

  // resumen en texto sobre la gráfica
  await expect(panel.locator('[data-nowcast-resumen]')).toContainText(
    'la mediana de la predicción es',
  );

  // alternativa en tabla
  const detalle = panel.locator('details').first();
  await detalle.locator('summary').click();
  await expect(detalle.locator('tbody tr')).not.toHaveCount(0);
});

test('la leyenda enciende y apaga series, y el periodo se anuncia', async ({
  page,
}) => {
  await simularApi(page);
  await page.goto('/prediccion');
  const panel = page.locator('[data-nowcast]');
  await expect(panel.locator('svg[role="img"]').first()).toBeVisible({
    timeout: 15_000,
  });

  const rango95 = panel.getByRole('button', { name: 'Rango 95 %' }).first();
  await expect(rango95).toHaveAttribute('aria-pressed', 'true');
  await rango95.click();
  await expect(rango95).toHaveAttribute('aria-pressed', 'false');
  await rango95.click();
  await expect(rango95).toHaveAttribute('aria-pressed', 'true');

  const tresMeses = panel.getByRole('button', { name: '3 meses' });
  await tresMeses.click();
  await expect(tresMeses).toHaveAttribute('aria-pressed', 'true');
  await expect(panel.getByRole('button', { name: '1 año' })).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  // el cambio de periodo lo oye quien usa lector de pantalla
  await expect(panel.locator('.sr-only[role="status"]')).not.toBeEmpty();
});

test('el panel pasa axe en claro y en oscuro', async ({ page }) => {
  await simularApi(page);
  for (const tema of ['light', 'dark'] as const) {
    await page.addInitScript((t) => {
      try {
        localStorage.setItem('epi:tema', t);
      } catch {
        /* sin almacenamiento */
      }
    }, tema);
    await page.goto('/prediccion');
    await expect(
      page.locator('[data-nowcast] svg[role="img"]').first(),
    ).toBeVisible({ timeout: 15_000 });
    const resultados = await new AxeBuilder({ page })
      .include('[data-nowcast]')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(resultados.violations).toEqual([]);
  }
});

test('sin predicción generada se muestra un mensaje neutro, sin reintento', async ({
  page,
}) => {
  await page.route('**/datos/nowcast-dengue**', (ruta) =>
    ruta.fulfill({
      json: { disponible: false, motivo: 'Aún no se generó la predicción.' },
    }),
  );
  await page.goto('/prediccion');
  const panel = page.locator('[data-nowcast]');
  await expect(panel).toContainText('Aún no se generó la predicción.');
  await expect(panel.getByRole('button', { name: 'Reintentar' })).toHaveCount(
    0,
  );
  await expect(panel.locator('svg[role="img"]')).toHaveCount(0);
});

test('si la fuente falla se ofrece reintentar y al reintentar se dibuja', async ({
  page,
}) => {
  let fallar = true;
  const { principal, retro } = (await import('./nowcast-mock')).respuestas();
  await page.route('**/datos/nowcast-dengue/retrospectivo.json', (ruta) =>
    ruta.fulfill({ json: retro }),
  );
  await page.route('**/datos/nowcast-dengue.json', (ruta) =>
    fallar
      ? ruta.fulfill({ status: 503, body: 'caído' })
      : ruta.fulfill({ json: principal }),
  );
  await page.goto('/prediccion');
  const panel = page.locator('[data-nowcast]');
  const reintentar = panel.getByRole('button', { name: 'Reintentar' });
  await expect(reintentar).toBeVisible({ timeout: 15_000 });
  fallar = false;
  await reintentar.click();
  await expect(panel.locator('svg[role="img"]').first()).toBeVisible({
    timeout: 15_000,
  });
});

test.describe('móvil de 375 px', () => {
  test.use({ viewport: { width: 375, height: 800 } });

  test('las gráficas caben sin desplazamiento horizontal de la página', async ({
    page,
  }) => {
    await simularApi(page);
    await page.goto('/prediccion');
    await expect(
      page.locator('[data-nowcast] svg[role="img"]').first(),
    ).toBeVisible({ timeout: 15_000 });
    // en pantalla estrecha el abanico arranca en el encuadre cercano
    await expect(
      page.locator('[data-nowcast]').getByRole('button', { name: '3 meses' }),
    ).toHaveAttribute('aria-pressed', 'true');
    const desborda = await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    );
    expect(desborda).toBe(false);
  });
});
