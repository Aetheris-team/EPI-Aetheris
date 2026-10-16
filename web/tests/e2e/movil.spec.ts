import { expect, test } from '@playwright/test';
import { simularClimaDengue } from './clima-dengue-mock';

const RUTAS = ['/dengue', '/respiratorio', '/departamento/SV-SS', '/alertas'];

for (const ancho of [375, 768]) {
  for (const ruta of RUTAS) {
    test(`${ruta} no desborda horizontalmente a ${ancho} px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: ancho, height: 800 });
      await page.goto(ruta);
      await page.waitForLoadState('networkidle');
      const desborde = await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      );
      expect(desborde).toBeLessThanOrEqual(0);
    });
  }
}

test('en teléfono el workspace muestra un panel a la vez', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto('/dengue');
  const selector = page.locator('[data-selector-movil]');
  await expect(selector).toBeVisible();
  const botones = selector.locator('button');
  await expect(botones).toHaveCount(4);
  await expect(botones.first()).toHaveAttribute('aria-pressed', 'true');
  await expect(
    page.locator('[data-panel-workspace]:not([hidden])'),
  ).toHaveCount(1);
  await expect(page.locator('[data-panel-workspace="mapa"]')).toBeVisible();

  await selector.locator('[data-panel-movil="temporadas"]').click();
  await expect(
    page.locator('[data-panel-workspace]:not([hidden])'),
  ).toHaveCount(1);
  await expect(
    page.locator('[data-panel-workspace="temporadas"]'),
  ).toBeVisible();
  await expect(page.locator('[data-panel-workspace="mapa"]')).toBeHidden();
  await expect(page.locator('#analisis-zoom-mas')).toBeHidden();
});

test('en escritorio el selector móvil no aparece y los paneles conviven', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/dengue');
  await expect(page.locator('[data-selector-movil]')).toBeHidden();
  expect(
    await page.locator('[data-panel-workspace]:not([hidden])').count(),
  ).toBeGreaterThan(1);
  await expect(page.locator('#analisis-zoom-mas')).toBeVisible();
});

test('/dengue enlaza a la predicción y no la repite', async ({ page }) => {
  await page.goto('/dengue');
  await expect(page.locator('[data-enlace-prediccion]')).toHaveAttribute(
    'href',
    '/prediccion',
  );
  await expect(page.locator('[data-nowcast]')).toHaveCount(0);
  await expect(page.locator('[data-contraste-nowcast]')).toHaveCount(0);
  await expect(page.locator('[data-tabs]')).toHaveCount(0);
  await expect(page.locator('#curva')).toHaveCount(1);
});

test('/dengue muestra la última semana publicada sin la semana siguiente', async ({
  page,
}) => {
  await page.goto('/dengue');
  const franja = page.locator('[data-franja-ultima-semana] #ultima-semana');
  await expect(franja).toHaveCount(1);
  await expect(franja).not.toContainText('Semana siguiente');
});

test.describe('pantalla táctil', () => {
  test.use({
    hasTouch: true,
    isMobile: true,
    viewport: { width: 375, height: 740 },
  });

  test('los campos de formulario no bajan de 16 px (evita el zoom de iOS)', async ({
    page,
  }) => {
    for (const ruta of ['/alertas/nueva', '/respiratorio', '/acerca-de']) {
      await page.goto(ruta);
      const menores = await page.evaluate(() =>
        [
          ...document.querySelectorAll<HTMLElement>(
            'input:not([type=hidden],[type=checkbox],[type=radio],[type=range]),select,textarea',
          ),
        ]
          .filter((el) => el.getClientRects().length > 0)
          .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
          .map((el) => el.outerHTML.slice(0, 80)),
      );
      expect(menores, ruta).toEqual([]);
    }
  });

  test('los deslizadores y los resúmenes plegables tienen área táctil de 44 px', async ({
    page,
  }) => {
    await page.goto('/respiratorio');
    const rango = page.locator('input[type=range]:visible').first();
    expect((await rango.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    const resumen = page.locator('summary:visible').first();
    expect((await resumen.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  });
});

test('la ayuda del mapa no aplasta su texto en teléfono', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.goto('/dengue');
  const texto = page
    .locator('[data-ayudas-mapa]')
    .locator('xpath=preceding-sibling::p[1]');
  expect((await texto.boundingBox())?.width).toBeGreaterThan(180);
});

test('la descripción de una tarjeta no queda en una columna estrecha junto a Exportar', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.goto('/respiratorio');
  const descripcion = page
    .locator('.panel-cabecera .panel-descripcion')
    .first();
  expect((await descripcion.boundingBox())?.width).toBeGreaterThan(180);
});

test('en horizontal la cabecera deja de ser pegajosa', async ({ page }) => {
  await page.setViewportSize({ width: 740, height: 360 });
  await page.goto('/dengue');
  await expect(page.locator('header.cabecera-sitio')).toHaveCSS(
    'position',
    'static',
  );
  await page.setViewportSize({ width: 375, height: 740 });
  await expect(page.locator('header.cabecera-sitio')).toHaveCSS(
    'position',
    'sticky',
  );
});

for (const [ancho, apilada] of [
  [375, true],
  [1280, false],
] as const) {
  test(`la tabla alternativa ${apilada ? 'se apila en tarjetas' : 'conserva columnas'} a ${ancho} px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: ancho, height: 800 });
    await simularClimaDengue(page);
    await page.goto('/analisis/clima');
    const panel = page.locator('[data-panel-clima="asociacion"]');
    await panel.scrollIntoViewIfNeeded();
    await expect(panel.locator('[data-contenido]')).toBeVisible();
    await panel
      .getByText('Ver las correlaciones con sus intervalos en tabla')
      .click();
    const tabla = panel.getByRole('table', {
      name: /Correlación entre la anomalía climática/,
    });
    await expect(tabla.locator('tbody tr')).toHaveCount(10);
    await expect(tabla.locator('tbody th[scope=row]').first()).toBeVisible();
    if (apilada) {
      await expect(tabla.locator('thead')).toBeHidden();
      const celda = tabla.locator('tbody td').first();
      const etiqueta = await celda.getAttribute('data-etiqueta');
      expect(etiqueta).toBeTruthy();
      expect(
        await celda.evaluate((td) => getComputedStyle(td, '::before').content),
      ).toBe(`"${etiqueta}"`);
      // Una fila completa se lee sin desplazar en horizontal.
      const region = tabla.locator('xpath=..');
      expect(
        await region.evaluate((el) => el.scrollWidth - el.clientWidth),
      ).toBeLessThanOrEqual(0);
    } else {
      await expect(tabla.locator('thead')).toBeVisible();
      expect(
        await tabla
          .locator('tbody td')
          .first()
          .evaluate((td) => getComputedStyle(td).display),
      ).toBe('table-cell');
    }
  });
}

for (const ancho of [1024, 1280, 1600]) {
  test(`el mapa no queda aplastado junto a su barra lateral a ${ancho} px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: ancho, height: 900 });
    await page.goto('/dengue');
    const panel = await page
      .locator('[data-panel-workspace="mapa"]')
      .boundingBox();
    const mapa = await page.locator('#mapa-departamentos').boundingBox();
    // El mapa ocupa al menos la mitad del panel: la barra de controles solo
    // se pone al lado cuando el panel tiene sitio para los dos.
    expect(mapa!.width).toBeGreaterThan(panel!.width / 2);
  });
}
