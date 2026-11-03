import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test.describe('pie de página', () => {
  test('muestra cuatro columnas con título y enlaces', async ({ page }) => {
    await page.goto('/');
    const columnas = page.locator('footer nav');
    await expect(columnas).toHaveCount(4);
    await expect(
      page.locator('footer').getByRole('heading', { level: 2 }),
    ).toHaveText(['EPI-Aetheris', 'Herramientas', 'Datos y método', 'Externo']);
  });

  test('los enlaces internos apuntan a rutas que responden', async ({
    page,
    request,
  }) => {
    await page.goto('/');
    const hrefs = await page
      .locator('footer nav a[href^="/"]')
      .evaluateAll((as) => [
        ...new Set(as.map((a) => (a as HTMLAnchorElement).pathname)),
      ]);
    expect(hrefs.length).toBeGreaterThan(10);
    for (const ruta of hrefs) {
      const respuesta = await request.get(ruta);
      expect(respuesta.status(), ruta).toBe(200);
    }
  });

  test('los enlaces externos llevan rel noopener noreferrer', async ({
    page,
  }) => {
    await page.goto('/');
    const rels = await page
      .locator('footer nav a[href^="http"]')
      .evaluateAll((as) => as.map((a) => a.getAttribute('rel')));
    expect(rels.length).toBeGreaterThan(3);
    for (const rel of rels) expect(rel).toBe('noopener noreferrer');
  });

  test('ningún enlace del pie lleva a /docs ni /redoc de la API', async ({
    page,
  }) => {
    await page.goto('/');
    const hrefs = await page
      .locator('footer a')
      .evaluateAll((as) => as.map((a) => (a as HTMLAnchorElement).pathname));
    expect(hrefs.length).toBeGreaterThan(10);
    for (const ruta of hrefs) expect(ruta).not.toMatch(/^\/(docs|redoc)\/?$/);
    await expect(
      page.locator('footer').getByText('API pública (Swagger)'),
    ).toHaveCount(0);
  });

  test('el interruptor de animaciones persiste y cambia aria-checked', async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.goto('/');
    const interruptor = page.getByRole('switch', { name: 'Animaciones' });
    await expect(interruptor).toHaveAttribute('aria-checked', 'true');
    await expect(page.locator('html')).toHaveAttribute(
      'data-animaciones',
      'on',
    );

    await interruptor.click();
    await expect(interruptor).toHaveAttribute('aria-checked', 'false');
    await expect(page.locator('html')).toHaveAttribute(
      'data-animaciones',
      'off',
    );

    await page.reload();
    await expect(
      page.getByRole('switch', { name: 'Animaciones' }),
    ).toHaveAttribute('aria-checked', 'false');
  });

  test('con reduced-motion del sistema arranca apagado', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/');
    await expect(
      page.getByRole('switch', { name: 'Animaciones' }),
    ).toHaveAttribute('aria-checked', 'false');
  });

  for (const esquema of ['light', 'dark'] as const) {
    test(`sin violaciones de axe en tema ${esquema}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: esquema });
      await page.addInitScript(
        (tema) => window.localStorage.setItem('epi:tema', tema),
        esquema,
      );
      await page.goto('/legal');
      const resultado = await new AxeBuilder({ page })
        .include('footer')
        .analyze();
      expect(resultado.violations).toEqual([]);
    });
  }
});
