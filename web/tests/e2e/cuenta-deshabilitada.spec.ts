import { expect, test } from '@playwright/test';

test('la edición estática carece de rutas y enlaces de escritura', async ({
  page,
}) => {
  for (const ruta of [
    '/cuenta',
    '/cuenta/ingresar',
    '/cuenta/aceptar',
    '/cuenta/alta',
    '/cuenta/olvide',
    '/cuenta/restablecer',
    '/admin/usuarios',
    '/alertas/nueva',
  ]) {
    const respuesta = await page.goto(ruta);
    expect(respuesta?.status(), ruta).toBe(404);
  }

  await page.goto('/alertas');
  await expect(
    page.locator(
      'a[href^="/cuenta"], a[href^="/admin"], a[href="/alertas/nueva"]',
    ),
  ).toHaveCount(0);
});
