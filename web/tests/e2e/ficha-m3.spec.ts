import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const RUTA = '/biblioteca/fichas/m3-presion-epidemiologica';

const celda = (percentil: number | null) => ({
  casos_observados: percentil === null ? null : 40,
  percentil,
  categoria: percentil === null ? null : 'alta',
  p50_baseline: percentil === null ? null : 12,
  p75_baseline: percentil === null ? null : 30,
  n_obs_baseline: 12,
  anios_baseline: 4,
});

test.describe('ficha enriquecida de M3', () => {
  test('muestra cabecera, siete pasos y enlace a la documentación', async ({
    page,
  }) => {
    await page.goto(RUTA);
    await expect(
      page.getByRole('heading', { level: 1, name: /Presión epidemiológica/ }),
    ).toBeVisible();
    await expect(page.locator('.ficha-etiquetas li')).toHaveCount(4);
    await expect(page.locator('[data-paso]')).toHaveCount(7);
    await expect(
      page.getByRole('heading', { level: 2, name: 'El canal endémico' }),
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: 'Ver documentación de M3' }),
    ).toHaveAttribute(
      'href',
      /03-funciones#m3-presión-epidemiológica-relativa/,
    );
  });

  for (const esquema of ['light', 'dark'] as const) {
    test(`no tiene violaciones de accesibilidad (${esquema})`, async ({
      page,
    }) => {
      await page.emulateMedia({
        reducedMotion: 'reduce',
        colorScheme: esquema,
      });
      await page.goto(RUTA);
      await page.locator('[data-lab-real]').waitFor();
      const resultado = await new AxeBuilder({ page }).analyze();
      expect(resultado.violations).toEqual([]);
    });
  }

  test('el término probable abre su nota con el teclado y Escape la cierra', async ({
    page,
  }) => {
    await page.goto(RUTA);
    const termino = page.locator('#fuente .termino-glosario-boton').first();
    await termino.focus();
    const nota = page.locator('.termino-glosario-nota:popover-open');
    await expect(nota).toBeVisible();
    await expect(nota).toContainText('Probable');
    await page.keyboard.press('Escape');
    await expect(nota).toHaveCount(0);
  });

  test('mover los casos recalcula el percentil, la categoría y el mapa', async ({
    page,
  }) => {
    await page.goto(RUTA);
    const cifra = page.locator('[data-lab-cifra]');
    await expect(cifra).toHaveText('86,7');
    await page.getByRole('button', { name: 'Semana baja' }).click();
    await expect(page.locator('[data-lab-categoria]')).toHaveText('baja');
    await page.getByRole('button', { name: 'Semana alta' }).click();
    await expect(page.locator('[data-lab-categoria]')).toHaveText('alta');
    await page.getByRole('button', { name: 'Sin historia suficiente' }).click();
    await expect(cifra).toHaveText('sin dato');
    await expect(page.locator('[data-lab-frase]')).toContainText(
      'hacen falta 3',
    );
    await page.locator('[data-lab-depto]').selectOption('SV-SM');
    await expect(
      page.locator(
        '[data-laboratorio-presion] [data-codigo="SV-SM"].seleccionado',
      ),
    ).toHaveCount(1);
    await expect(page.locator('[data-lab-estado]')).toContainText('San Miguel');
  });

  test('«Calcular paso a paso» recorre el método y deja el resultado', async ({
    page,
  }) => {
    await page.goto(RUTA);
    await page.getByRole('button', { name: 'Semana alta' }).click();
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
    await expect(page.locator('[data-lab-estado]')).toContainText('percentil');
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
    await expect(page.locator('[data-lab-cifra]')).toHaveText('86,7');
  });

  test('si la API falla, la simulación sigue y se ofrece reintentar', async ({
    page,
  }) => {
    await page.route('**/datos/v1/presion/temporal/**', (ruta) => ruta.abort());
    await page.goto(RUTA);
    await expect(
      page.locator('[data-lab-real]').getByRole('button', {
        name: 'Reintentar',
      }),
    ).toBeVisible();
    await page.getByRole('button', { name: 'Semana baja' }).click();
    await expect(page.locator('[data-lab-cifra]')).not.toHaveText('86,7');
  });

  test('muestra la última presión que devuelve la API, por serie', async ({
    page,
  }) => {
    await page.route('**/datos/v1/presion/temporal/**', (ruta) =>
      ruta.fulfill({
        json: {
          departamento_codigo: 'SV-SS',
          departamento_nombre: 'San Salvador',
          anio: 2023,
          aviso: '',
          semanas: [
            { semana_epi: 40, probable: celda(91.5), confirmado: celda(null) },
            { semana_epi: 41, probable: celda(null), confirmado: celda(null) },
          ],
        },
      }),
    );
    await page.goto(RUTA);
    const real = page.locator('[data-lab-real]');
    await expect(real).toContainText('SE40 de 2023');
    await expect(real).toContainText('percentil 91,5');
    await page.locator('[data-lab-serie]').selectOption('confirmado');
    await expect(real).toContainText('no tiene presión confirmado');
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
