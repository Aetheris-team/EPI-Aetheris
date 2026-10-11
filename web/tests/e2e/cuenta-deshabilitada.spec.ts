import { expect, test } from '@playwright/test';

import { CUENTAS_HABILITADAS, sinViolacionesAxe } from './cuenta-comun';

// Estas pruebas valen para un sitio construido sin PUBLIC_CUENTAS_HABILITADAS
// (el valor por defecto). Arrancar `pnpm dev` sin la variable y correrlas
// contra ese servidor.
test.describe('cuentas apagadas', () => {
  test.skip(
    CUENTAS_HABILITADAS,
    'Las cuentas están encendidas en este servidor.',
  );

  for (const ruta of [
    '/cuenta',
    '/cuenta/ingresar',
    '/cuenta/aceptar',
    '/cuenta/alta',
    '/cuenta/olvide',
    '/cuenta/restablecer',
    '/admin/usuarios',
  ]) {
    test(`${ruta} muestra un aviso neutro y no se indexa`, async ({ page }) => {
      const peticionesDeCuenta: string[] = [];
      page.on('request', (peticion) => {
        if (/\/api\/(cuenta|admin)\//.test(peticion.url())) {
          peticionesDeCuenta.push(peticion.url());
        }
      });
      await page.goto(ruta);
      await expect(
        page.getByRole('heading', {
          level: 1,
          name: 'Las cuentas no están disponibles',
        }),
      ).toBeVisible();
      await expect(page.locator('meta[name="robots"]')).toHaveAttribute(
        'content',
        /noindex/,
      );
      await expect(page.getByLabel('Contraseña')).toHaveCount(0);
      expect(peticionesDeCuenta).toEqual([]);
      await sinViolacionesAxe(page);
    });
  }

  test('ni la navegación ni el pie enlazan hacia ingresar', async ({
    page,
  }) => {
    await page.goto('/');
    await expect(page.locator('footer')).toBeVisible();
    await expect(
      page.locator('a[href^="/cuenta"], a[href^="/admin"]'),
    ).toHaveCount(0);
  });
});
