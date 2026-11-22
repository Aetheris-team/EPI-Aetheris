import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const casos = Array.from({ length: 30 }, (_, i) => ({
  anio: 2025,
  semana_epi: i + 1,
  semana_inicio: '2025-01-05',
  conteo: 100 + i,
  fuente: 'minsal_tablero',
}));

test('las vistas incrustables salen del índice y llevan atribución', async ({
  page,
}) => {
  await page.route('**/datos/casos-nacional*', (r) => r.fulfill({ json: casos }));
  for (const ruta of [
    '/incrustar/curva-nacional',
    '/incrustar/ultima-semana',
  ]) {
    await page.goto(ruta);
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute(
      'content',
      /noindex/,
    );
    await expect(page.locator('body > header')).toHaveCount(0);
    await expect(page.locator('[data-atribucion]')).toHaveAttribute(
      'href',
      /^https:\/\/epi-aetheris\.dev\//,
    );
    await expect(page.locator('[data-incrustar]').first()).toBeHidden();
  }
});

test('los enlaces internos de una vista incrustada abren el sitio completo', async ({
  page,
}) => {
  await page.route('**/datos/casos-nacional*', (r) => r.fulfill({ json: casos }));
  await page.goto('/incrustar/ultima-semana');
  await page.waitForFunction(
    () => document.querySelectorAll('main a[href]').length > 0,
  );
  const enlaces = await page.locator('main a[href]').evaluateAll((els) =>
    els.map((e) => ({
      href: e.getAttribute('href'),
      target: e.getAttribute('target'),
    })),
  );
  for (const enlace of enlaces) {
    expect(enlace.href).toMatch(/^https?:\/\//);
    expect(enlace.target).toBe('_blank');
  }
});

test('el botón Incrustar copia un iframe con la ruta de la vista', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto('/dengue');
  const boton = page.locator('[data-incrustar-copiar]').first();
  await boton.scrollIntoViewIfNeeded();
  await boton.click();
  const texto = await page.evaluate(() => navigator.clipboard.readText());
  expect(texto).toMatch(
    /^<iframe src="https:\/\/epi-aetheris\.dev\/incrustar\//,
  );
  expect(texto).toContain('loading="lazy"');
  await expect(page.locator('[data-incrustar-estado]').first()).toContainText(
    'copiado',
  );
});

test('la vista incrustada no presenta violaciones WCAG A y AA', async ({
  page,
}) => {
  await page.route('**/datos/casos-nacional*', (r) => r.fulfill({ json: casos }));
  await page.goto('/incrustar/curva-nacional');
  await expect(page.locator('main svg[role="img"]').first()).toBeVisible();
  const resultados = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  expect(resultados.violations).toEqual([]);
});
