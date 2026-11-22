import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('/estado publica el corte y la cobertura de sus archivos', async ({
  page,
  request,
}) => {
  const respuesta = await request.get('/datos/corte.json');
  expect(respuesta.ok()).toBe(true);
  const corte = await respuesta.json();

  const peticionesLegadas: string[] = [];
  page.on('request', (peticion) => {
    if (/^\/(api\/|health$)/.test(new URL(peticion.url()).pathname)) {
      peticionesLegadas.push(peticion.url());
    }
  });

  await page.goto('/estado');
  await expect(page.locator('[data-fecha-corte] time')).toHaveAttribute(
    'datetime',
    corte.fecha,
  );
  await expect(page.locator('main')).toContainText(corte.version);
  const seccion = page.locator('[data-frescura]');
  await expect(seccion.locator('tbody tr')).toHaveCount(
    Object.keys(corte.series).length,
  );
  await expect(seccion).toContainText('Dengue nacional (tablero de MINSAL)');
  await expect(seccion).toContainText('Clima (Open-Meteo)');
  expect(peticionesLegadas).toEqual([]);

  const resultados = await new AxeBuilder({ page })
    .include('[data-frescura]')
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  expect(resultados.violations).toEqual([]);
});
