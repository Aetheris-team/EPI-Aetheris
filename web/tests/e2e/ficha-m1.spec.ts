import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const RUTA = '/biblioteca/fichas/m1-idoneidad-biofisica';

test.describe('ficha enriquecida de M1', () => {
  test('muestra cabecera, seis pasos y enlace a la documentación', async ({
    page,
  }) => {
    await page.goto(RUTA);
    await expect(
      page.getByRole('heading', { level: 1, name: /Idoneidad biofísica/ }),
    ).toBeVisible();
    await expect(page.locator('.ficha-etiquetas li')).toHaveCount(4);
    await expect(page.locator('[data-paso]')).toHaveCount(6);
    await expect(
      page.getByRole('link', { name: 'Ver documentación de M1' }),
    ).toHaveAttribute('href', /03-funciones#m1-idoneidad-biofísica-iv/);
  });

  test('/biblioteca/fichas redirige al índice de la Biblioteca', async ({
    page,
  }) => {
    await page.goto('/biblioteca/fichas');
    await expect(page).toHaveURL(/\/biblioteca\/?$/);
    await expect(
      page.getByRole('heading', { level: 2, name: 'Fichas enriquecidas' }),
    ).toBeVisible();
  });

  test('no tiene violaciones de accesibilidad', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(RUTA);
    await page.locator('[data-lab-real]').waitFor();
    const resultado = await new AxeBuilder({ page }).analyze();
    expect(resultado.violations).toEqual([]);
  });

  test('el término Iv abre su nota con el teclado y Escape la cierra', async ({
    page,
  }) => {
    await page.goto(RUTA);
    const termino = page.locator('#fuente .termino-glosario-boton').first();
    await termino.focus();
    const nota = page.locator('.termino-glosario-nota:popover-open');
    await expect(nota).toBeVisible();
    await expect(nota.getByRole('link')).toHaveAttribute(
      'href',
      /03-funciones/,
    );
    await page.keyboard.press('Escape');
    await expect(nota).toHaveCount(0);
  });

  test('mover un control recalcula el Iv y el mapa', async ({ page }) => {
    await page.goto(RUTA);
    const cifra = page.locator('[data-lab-cifra]');
    await expect(cifra).toHaveText('0,64');
    await page.getByRole('button', { name: 'Seco' }).click();
    await expect(cifra).not.toHaveText('0,64');
    await page.getByRole('button', { name: 'Calor extremo' }).click();
    // 37 °C está cerca del límite de 38 °C: la curva de temperatura cae.
    await expect(page.locator('[data-lab-entrada="ft"]')).toHaveValue('37');
    const ruta = page.locator(
      '[data-laboratorio] [data-mapa-iv-svg] .seleccionado',
    );
    await expect(ruta).toHaveCount(1);
    await page.locator('[data-lab-depto]').selectOption('SV-SM');
    await expect(
      page.locator(
        '[data-laboratorio] [data-mapa-iv-svg] [data-codigo="SV-SM"].seleccionado',
      ),
    ).toHaveCount(1);
    await expect(page.locator('[data-lab-estado]')).toContainText('San Miguel');
  });

  test('«Calcular paso a paso» recorre el método y deja el resultado', async ({
    page,
  }) => {
    await page.goto(RUTA);
    await page.getByRole('button', { name: 'Cálido y lluvioso' }).click();
    const final = await page.locator('[data-lab-cifra]').textContent();
    await page.getByRole('button', { name: /Calcular paso a paso/ }).click();
    await expect(page.locator('[data-lab-controles]')).toHaveAttribute(
      'disabled',
      '',
    );
    await expect(page.locator('.lab-activo').first()).toBeVisible();
    await expect(page.locator('[data-lab-controles]')).not.toHaveAttribute(
      'disabled',
      '',
      { timeout: 10_000 },
    );
    await expect(page.locator('[data-lab-cifra]')).toHaveText(final ?? '');
    await expect(page.locator('[data-lab-estado]')).toContainText('Iv de la');
  });

  test('con animaciones apagadas el cálculo salta al resultado', async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(RUTA);
    await page.getByRole('button', { name: /Calcular paso a paso/ }).click();
    await expect(page.locator('[data-lab-controles]')).not.toHaveAttribute(
      'disabled',
      '',
    );
    await expect(page.locator('.lab-activo')).toHaveCount(0);
    await expect(page.locator('[data-lab-cifra]')).toHaveText('0,64');
  });

  test('si la API falla, la simulación sigue y se ofrece reintentar', async ({
    page,
  }) => {
    await page.route('**/datos/v1/temporal/**', (ruta) => ruta.abort());
    await page.goto(RUTA);
    await expect(
      page.locator('[data-lab-real]').getByRole('button', {
        name: 'Reintentar',
      }),
    ).toBeVisible();
    await page.getByRole('button', { name: 'Fresco' }).click();
    await expect(page.locator('[data-lab-cifra]')).not.toHaveText('');
  });

  test('en móvil no hay desplazamiento horizontal', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await page.goto(RUTA);
    await page.locator('[data-lab-real]').waitFor();
    const desborde = await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    );
    expect(desborde).toBe(false);
  });
});
