import { expect, test } from '@playwright/test';

// El mapa no debe capturar el scroll de la página ni secuestrar la rueda del ratón
// (sustitución de Leaflet por SVG vectorial nativo).
test.describe('mapa: scroll y comportamiento natural', () => {
  test('la rueda sobre el mapa desplaza la página de forma natural sin secuestro ni avisos', async ({
    page,
  }) => {
    await page.goto('/respiratorio');
    const mapa = page.locator(
      '#ira [data-mapa-evento="ira"] [data-mapa-canvas] svg',
    );
    await expect(mapa).toBeVisible({ timeout: 15_000 });
    await mapa.scrollIntoViewIfNeeded();
    const caja = (await mapa.boundingBox())!;
    await page.mouse.move(caja.x + caja.width / 2, caja.y + caja.height / 2);

    const antes = await page.evaluate(() => window.scrollY);
    await page.mouse.wheel(0, 200);
    await expect
      .poll(() => page.evaluate(() => window.scrollY))
      .toBeGreaterThan(antes);

    // Sin secuestro: no hay pistas molestas ni overlays que capturen el scroll
    await expect(page.locator('.mapa-pista-scroll')).toHaveCount(0);
  });
});
