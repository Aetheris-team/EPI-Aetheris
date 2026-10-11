import { expect, test } from '@playwright/test';

const RUTA = '/biblioteca/fichas/modelo-predictivo';

test.describe('ficha enriquecida del modelo predictivo (disposición dividida)', () => {
  test('muestra cabecera, formalidades, seis etapas y layout dividido', async ({
    page,
  }) => {
    await page.goto(RUTA);
    await expect(
      page.getByRole('heading', {
        level: 1,
        name: /Modelo predictivo de dengue/,
      }),
    ).toBeVisible();

    // Comprobar presencia del contenedor dividido
    await expect(page.locator('[data-ficha-predictiva]')).toBeVisible();

    // Comprobar las 6 etapas técnicas en la columna izquierda
    await expect(page.locator('[data-paso-card]')).toHaveCount(6);

    // Comprobar el enlace a la documentación formal
    const enlaceDoc = page.getByRole('link', {
      name: /Ver documento formal: Sensibilidad y honestidad/,
    });
    await expect(enlaceDoc).toHaveAttribute(
      'href',
      /05-sensibilidad-y-honestidad#predicción-de-casos-a-corto-plazo/,
    );
  });

  test('el stepper de la columna derecha conmuta las etapas y actualiza el escenario', async ({
    page,
  }) => {
    await page.goto(RUTA);

    // Inicialmente estamos en la etapa 1
    const indicador = page.locator('[data-indicador-contador]');
    await expect(indicador).toHaveText('Etapa 1 de 6');

    // Click en la etapa 3 (Cuantiles)
    const btnEtapa3 = page.locator('[data-boton-etapa="2"]');
    await btnEtapa3.click();

    await expect(indicador).toHaveText('Etapa 3 de 6');
    await expect(page.locator('[data-titulo-etapa-activa]')).toContainText(
      'Gradient Boosting y 23 cuantiles',
    );
    await expect(page.locator('[data-escenario-panel="2"]')).toBeVisible();

    // Click en botón siguiente (debe pasar a etapa 4)
    await page.locator('[data-btn-siguiente]').click();
    await expect(indicador).toHaveText('Etapa 4 de 6');
    await expect(page.locator('[data-escenario-panel="3"]')).toBeVisible();
  });

  test('el simulador interactivo de la etapa 6 reacciona a los sliders', async ({
    page,
  }) => {
    await page.goto(RUTA);

    // Ir a la etapa 6 (Simulador)
    await page.locator('[data-boton-etapa="5"]').click();
    await expect(page.locator('[data-escenario-panel="5"]')).toBeVisible();

    // Verificar valores iniciales
    const txtCasos = page.locator('[data-sim-val-casos]');
    await expect(txtCasos).toHaveText('85 casos');

    // Cambiar el slider de casos a 200
    const sliderCasos = page.locator('#sim-casos');
    await sliderCasos.fill('200');

    // Comprobar que el texto y los resultados se actualizaron
    await expect(txtCasos).toHaveText('200 casos');
    const resS1 = page.locator('#sim-res-s1');
    await expect(resS1).not.toHaveText('88 [60-120]');
  });

  test('aparece catalogada y destacada en el índice de la biblioteca', async ({
    page,
  }) => {
    await page.goto('/biblioteca');
    const tarjeta = page.locator(
      'a[href="/biblioteca/fichas/modelo-predictivo"]',
    );
    await expect(tarjeta).toBeVisible();
    await expect(tarjeta).toContainText('Modelo predictivo de dengue');
    await expect(tarjeta).toContainText('Simulador Nowcast CQR-r');
  });
});
