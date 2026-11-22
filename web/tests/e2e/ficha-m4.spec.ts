import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const RUTA = '/biblioteca/fichas/m4-integridad-vigilancia';

test.describe('ficha enriquecida de M4', () => {
  test('muestra cabecera, seis pasos y enlace a la documentación', async ({
    page,
  }) => {
    await page.goto(RUTA);
    await expect(
      page.getByRole('heading', {
        level: 1,
        name: /Integridad de la vigilancia/,
      }),
    ).toBeVisible();
    await expect(page.locator('.ficha-etiquetas li')).toHaveCount(4);
    await expect(page.locator('[data-paso]')).toHaveCount(6);
    await expect(
      page.getByRole('link', { name: 'Ver documentación de M4' }),
    ).toHaveAttribute('href', /03-funciones#m4-integridad-de-la-vigilancia/);
    // Los ejemplos calculados con la biblioteca.
    await expect(page.locator('#completitud')).toContainText('11 de 14');
    await expect(page.locator('#cuadre')).toContainText('−5');
    await expect(page.locator('#antiguedad')).toContainText('144 semanas');
    await expect(page.locator('#antiguedad')).toContainText('SE53 de 2025');
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

  test('el término hueco abre su nota con el teclado y Escape la cierra', async ({
    page,
  }) => {
    await page.goto(RUTA);
    const termino = page
      .locator('#para-que .termino-glosario-boton')
      .filter({ hasText: 'hueco' });
    await termino.focus();
    const nota = page.locator('.termino-glosario-nota:popover-open');
    await expect(nota).toBeVisible();
    await expect(nota).toContainText('Hueco de la fuente');
    await page.keyboard.press('Escape');
    await expect(nota).toHaveCount(0);
  });

  test('marcar departamentos y cambiar el boletín recalcula el estado', async ({
    page,
  }) => {
    await page.goto(RUTA);
    const lab = page.locator('[data-laboratorio-integridad]');
    await expect(lab.locator('[data-lab-n]')).toHaveText('14 de 14');
    await page.getByRole('button', { name: 'Faltan departamentos' }).click();
    await expect(lab.locator('[data-lab-n]')).toHaveText('11 de 14');
    await page.locator('[data-lab-depto]').selectOption('SV-MO');
    await expect(lab.locator('[data-lab-estado-depto]')).toHaveText(
      'sin dato esta semana',
    );
    await lab.getByRole('checkbox', { name: 'Morazán' }).check();
    await expect(lab.locator('[data-lab-n]')).toHaveText('12 de 14');
    await expect(lab.locator('[data-lab-estado-depto]')).toHaveText(
      'dato presente',
    );
    await page.getByRole('button', { name: 'Boletín que no cuadra' }).click();
    await expect(lab.locator('[data-lab-diferencia]')).toHaveText('−5');
    await expect(lab.locator('[data-lab-estado-depto]')).toHaveText(
      'dato presente, el boletín no cuadra',
    );
    await page.getByRole('button', { name: 'Sin boletín' }).click();
    await expect(lab.locator('[data-lab-diferencia]')).toHaveText('vacía');
    await expect(lab.locator('[data-lab-estado-depto]')).toHaveText(
      'dato presente',
    );
    await expect(lab.locator('[data-codigo="SV-MO"].seleccionado')).toHaveCount(
      1,
    );
    await expect(page.locator('[data-lab-estado]')).toContainText('Morazán');
  });

  test('«Calcular paso a paso» recorre el método y deja el resultado', async ({
    page,
  }) => {
    await page.goto(RUTA);
    await page.getByRole('button', { name: 'Boletín que no cuadra' }).click();
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
    await expect(page.locator('[data-lab-diferencia]')).toHaveText('−5');
    await expect(page.locator('[data-lab-estado]')).toContainText('no cuadra');
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
    await expect(page.locator('[data-lab-n]')).toHaveText('14 de 14');
  });

  test('si la API falla, la simulación sigue y se ofrece reintentar', async ({
    page,
  }) => {
    await page.route('**/datos/v1/vigilancia/integridad**', (ruta) =>
      ruta.abort(),
    );
    await page.goto(RUTA);
    await expect(
      page.locator('[data-lab-real]').getByRole('button', {
        name: 'Reintentar',
      }),
    ).toBeVisible();
    await page.getByRole('button', { name: 'Faltan departamentos' }).click();
    await expect(page.locator('[data-lab-n]')).toHaveText('11 de 14');
  });

  test('muestra la antigüedad y el resumen anual que devuelve la API', async ({
    page,
  }) => {
    await page.route('**/datos/v1/vigilancia/integridad**', (ruta) =>
      ruta.fulfill({
        json: {
          aviso: '',
          antiguedad: {
            dengue_minsal_departamental: {
              ultima_anio: 2023,
              ultima_semana_epi: 52,
              semanas: 144,
            },
            clima: { ultima_anio: 2026, ultima_semana_epi: 38, semanas: 1 },
          },
          resumen_anual: [
            {
              anio: 2023,
              probable: {
                semanas_completas: 40,
                semanas_con_dato: 48,
                semanas_nominales: 52,
              },
              confirmado: {
                semanas_completas: 38,
                semanas_con_dato: 48,
                semanas_nominales: 52,
              },
            },
          ],
        },
      }),
    );
    await page.goto(RUTA);
    const real = page.locator('[data-lab-real]');
    await expect(real).toContainText('Dengue por departamento');
    await expect(real).toContainText('SE52 de 2023');
    await expect(real).toContainText('144 semanas de rezago');
    await expect(real).toContainText('Resumen de 2023');
  });

  test('las fichas se enlazan en orden y /estado lleva a la de M4', async ({
    page,
  }) => {
    await page.goto(RUTA);
    const vecinas = page.getByRole('navigation', { name: 'Otras fichas' });
    await expect(
      vecinas.getByRole('link', { name: /Presión epidemiológica relativa/ }),
    ).toHaveAttribute('href', '/biblioteca/fichas/m3-presion-epidemiologica');
    await expect(vecinas.getByRole('link')).toHaveCount(1);
    await page.goto('/biblioteca/fichas/m2-anomalia-climatica');
    await expect(
      page.getByRole('navigation', { name: 'Otras fichas' }).getByRole('link'),
    ).toHaveCount(2);
    await page.goto('/estado');
    await page
      .locator('[data-frescura]')
      .getByRole('link', { name: 'integridad de la vigilancia' })
      .click();
    await expect(page).toHaveURL(new RegExp(RUTA));
  });

  test('la Biblioteca lista las cuatro fichas', async ({ page }) => {
    await page.goto('/biblioteca');
    for (const nombre of [
      'Idoneidad biofísica (M1)',
      'Anomalía climática (M2)',
      'Presión epidemiológica relativa (M3)',
      'Integridad de la vigilancia (M4)',
    ]) {
      await expect(
        page.getByRole('link', {
          name: new RegExp(nombre.replace(/[\\()]/g, '\\$&')),
        }),
      ).toBeVisible();
    }
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
