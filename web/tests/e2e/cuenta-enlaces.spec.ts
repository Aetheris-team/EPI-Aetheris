import { expect, test } from '@playwright/test';

import {
  ANONIMA,
  CUENTAS_HABILITADAS,
  sesion,
  simularApi,
} from './cuenta-comun';

test.describe('cuentas: enlaces del pie', () => {
  test.skip(
    !CUENTAS_HABILITADAS,
    'Las cuentas están apagadas en este servidor.',
  );

  test('un lector sin pista de sesión ve "Ingresar" y no consulta al backend', async ({
    page,
  }) => {
    const llamadas = await simularApi(page, {
      'GET /api/cuenta/sesion': { json: ANONIMA },
    });
    await page.goto('/');
    const enlace = page
      .locator('footer')
      .getByRole('link', { name: 'Ingresar' });
    await expect(enlace).toHaveAttribute('href', '/cuenta/ingresar');
    // Espera a que el pie termine de cargar sus scripts.
    await page.waitForLoadState('networkidle');
    expect(llamadas).toHaveLength(0);
  });

  test('con sesión completa el pie ofrece "Mi cuenta"', async ({ page }) => {
    await simularApi(page, { 'GET /api/cuenta/sesion': { json: sesion() } });
    await page.addInitScript(() =>
      localStorage.setItem('epi:sesion-pista', '1'),
    );
    await page.goto('/');
    const enlace = page
      .locator('footer')
      .getByRole('link', { name: 'Mi cuenta' });
    await expect(enlace).toHaveAttribute('href', '/cuenta');
  });

  test('si la pista es vieja y no hay sesión, vuelve a "Ingresar" y borra la pista', async ({
    page,
  }) => {
    await simularApi(page, { 'GET /api/cuenta/sesion': { json: ANONIMA } });
    await page.addInitScript(() =>
      localStorage.setItem('epi:sesion-pista', '1'),
    );
    await page.goto('/');
    await expect(
      page.locator('footer').getByRole('link', { name: 'Ingresar' }),
    ).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem('epi:sesion-pista')))
      .toBeNull();
  });
});
