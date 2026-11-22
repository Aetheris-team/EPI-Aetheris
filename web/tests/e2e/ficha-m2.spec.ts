import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const RUTA = '/biblioteca/fichas/m2-anomalia-climatica';

test.describe('ficha enriquecida de M2', () => {
  test('muestra cabecera, seis pasos y enlace a la documentación', async ({
    page,
  }) => {
    await page.goto(RUTA);
    await expect(
      page.getByRole('heading', { level: 1, name: /Anomalía climática/ }),
    ).toBeVisible();
    await expect(page.locator('.ficha-etiquetas li')).toHaveCount(4);
    await expect(page.locator('[data-paso]')).toHaveCount(6);
    await expect(
      page.getByRole('link', { name: 'Ver documentación de M2' }),
    ).toHaveAttribute('href', /03-funciones#m2-anomalía-climática-continua/);
    await expect(
      page.locator('#fuente').getByRole('link', { name: 'ficha de M1' }),
    ).toHaveAttribute('href', '/biblioteca/fichas/m1-idoneidad-biofisica');
  });

  test('no tiene violaciones de accesibilidad', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(RUTA);
    await page.locator('[data-lab-real]').waitFor();
    const resultado = await new AxeBuilder({ page }).analyze();
    expect(resultado.violations).toEqual([]);
  });

  test('no tiene violaciones de accesibilidad en tema oscuro', async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'dark' });
    await page.goto(RUTA);
    await page.locator('[data-lab-real]').waitFor();
    const resultado = await new AxeBuilder({ page }).analyze();
    expect(resultado.violations).toEqual([]);
  });

  test('el término mediana abre su nota con el teclado y Escape la cierra', async ({
    page,
  }) => {
    await page.goto(RUTA);
    const termino = page.locator('#habitual .termino-glosario-boton').first();
    // Primero se lleva a la vista: el scroll de focus() cerraría la nota.
    await termino.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await termino.focus();
    const nota = page.locator('.termino-glosario-nota:popover-open');
    await expect(nota).toBeVisible();
    await expect(nota).toContainText('Mediana');
    await page.keyboard.press('Escape');
    await expect(nota).toHaveCount(0);
  });

  test('cambiar los valores recalcula σ, la mediana y el mapa', async ({
    page,
  }) => {
    await page.goto(RUTA);
    const cifra = page.locator('[data-lab-cifra]');
    await expect(cifra).toHaveText('+0,08');
    await page.getByRole('button', { name: 'Semana inusual' }).click();
    await expect(cifra).not.toHaveText('+0,08');
    await page.locator('[data-lab-valor]').fill('0.2');
    await expect(cifra).toContainText('−');
    await page.getByRole('button', { name: 'Poca historia' }).click();
    await expect(cifra).toHaveText('sin dato');
    await expect(page.locator('[data-lab-frase]')).toContainText('al menos 3');
    await page.locator('[data-lab-depto]').selectOption('SV-SM');
    await expect(
      page.locator(
        '[data-laboratorio-anomalia] [data-codigo="SV-SM"].seleccionado',
      ),
    ).toHaveCount(1);
    await expect(page.locator('[data-lab-estado]')).toContainText('San Miguel');
  });

  test('«Calcular paso a paso» recorre el método y deja el resultado', async ({
    page,
  }) => {
    await page.goto(RUTA);
    await page.getByRole('button', { name: 'Semana inusual' }).click();
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
    await expect(page.locator('[data-lab-estado]')).toContainText('σ');
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
    await expect(page.locator('[data-lab-cifra]')).toHaveText('+0,08');
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
    await page.getByRole('button', { name: 'Semana inusual' }).click();
    await expect(page.locator('[data-lab-cifra]')).not.toHaveText('+0,08');
  });

  test('muestra la última anomalía que devuelve la API', async ({ page }) => {
    await page.route('**/datos/v1/temporal/**', (ruta) =>
      ruta.fulfill({
        json: {
          departamento_codigo: 'SV-SS',
          departamento_nombre: 'San Salvador',
          anio: 2026,
          aviso: '',
          semanas: [
            {
              semana_epi: 37,
              iv_real: 0.61,
              p25_baseline: 0.5,
              mediana_baseline: 0.55,
              p75_baseline: 0.6,
              anomaly_sigma: 1.25,
            },
            {
              semana_epi: 38,
              iv_real: null,
              p25_baseline: null,
              mediana_baseline: null,
              p75_baseline: null,
              anomaly_sigma: null,
            },
          ],
        },
      }),
    );
    await page.goto(RUTA);
    const real = page.locator('[data-lab-real]');
    await expect(real).toContainText('SE37');
    await expect(real).toContainText('+1,25 σ');
    await expect(real).toContainText('0,50 a 0,60');
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
