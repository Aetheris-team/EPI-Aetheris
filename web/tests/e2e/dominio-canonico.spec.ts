import { expect, test } from '@playwright/test';

// Render no permite un 301 por dominio en sitios estáticos, así que el
// Layout redirige desde el navegador (ADR 0024). Se simula el dominio de
// onrender.com sirviendo el HTML local bajo ese nombre.
test.describe('Dominio canónico', () => {
  test('la dirección de onrender.com lleva al dominio canónico con ruta, consulta y ancla', async ({
    page,
    request,
  }) => {
    const html = await (await request.get('/respiratorio')).text();
    await page.route('https://epi-aetheris-web.onrender.com/**', (ruta) =>
      ruta.fulfill({ contentType: 'text/html', body: html }),
    );
    await page.route('https://epi-aetheris.dev/**', (ruta) =>
      ruta.fulfill({
        contentType: 'text/html',
        body: '<!doctype html><title>canónico</title>',
      }),
    );

    await page.goto(
      'https://epi-aetheris-web.onrender.com/respiratorio?anio=2022#mapa',
    );
    await expect(page).toHaveURL(
      'https://epi-aetheris.dev/respiratorio?anio=2022#mapa',
    );
  });

  test('una preview de PR en onrender.com no se redirige', async ({
    page,
    request,
  }) => {
    const html = await (await request.get('/respiratorio')).text();
    await page.route('https://epi-aetheris-web-pr-1.onrender.com/**', (ruta) =>
      ruta.fulfill({ contentType: 'text/html', body: html }),
    );
    await page.goto('https://epi-aetheris-web-pr-1.onrender.com/respiratorio');
    await expect(page).toHaveURL(
      'https://epi-aetheris-web-pr-1.onrender.com/respiratorio',
    );
  });
});
