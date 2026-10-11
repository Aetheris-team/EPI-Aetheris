import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { simularClimaDengue } from './clima-dengue-mock';

const casos = Array.from({ length: 30 }, (_, i) => ({
  anio: 2025,
  semana_epi: i + 1,
  semana_inicio: '2025-01-05',
  conteo: 100 + i,
  fuente: 'minsal_tablero',
}));

async function abrirCurva(page: import('@playwright/test').Page) {
  await page.route('**/api/casos-nacional*', (r) => r.fulfill({ json: casos }));
  await page.goto('/dengue');
  const curva = page.locator('section:has(#curva-epidemica)');
  await expect(curva.locator('#curva-epidemica svg').first()).toBeVisible();
  return curva;
}

test('la curva nacional reúne CSV, SVG, PNG e incrustar bajo «Exportar»', async ({
  page,
}) => {
  const curva = await abrirCurva(page);
  const boton = curva.getByRole('button', { name: 'Exportar' });
  await expect(boton).toHaveAttribute('aria-expanded', 'false');
  // Ya no quedan botones de descarga sueltos en la sección.
  await expect(curva.getByRole('button', { name: /^Descargar/ })).toHaveCount(
    0,
  );

  await boton.click();
  await expect(boton).toHaveAttribute('aria-expanded', 'true');
  const opciones = curva.getByRole('menuitem');
  await expect(opciones).toHaveText([
    'Datos (CSV)',
    'Imagen vectorial (SVG)',
    'Imagen (PNG)',
    'Copiar código para incrustar',
  ]);
  // Cada opción lleva su icono.
  await expect(curva.locator('[role="menuitem"] svg')).toHaveCount(4);
});

test('las opciones del menú descargan los archivos y copian el código', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  const curva = await abrirCurva(page);
  const boton = curva.getByRole('button', { name: 'Exportar' });

  await boton.click();
  const [csv] = await Promise.all([
    page.waitForEvent('download'),
    curva.getByRole('menuitem', { name: 'Datos (CSV)' }).click(),
  ]);
  expect(csv.suggestedFilename()).toMatch(
    /^epi-aetheris-dengue-nacional-.*\.csv$/,
  );

  await boton.click();
  const [svg] = await Promise.all([
    page.waitForEvent('download'),
    curva.getByRole('menuitem', { name: /SVG/ }).click(),
  ]);
  expect(svg.suggestedFilename()).toMatch(/\.svg$/);

  await boton.click();
  await curva.getByRole('menuitem', { name: /incrustar/ }).click();
  const texto = await page.evaluate(() => navigator.clipboard.readText());
  expect(texto).toMatch(
    /^<iframe src="https:\/\/epi-aetheris\.dev\/incrustar\/curva-nacional"/,
  );
  await expect(curva.locator('[data-menu-exportar-estado]')).toContainText(
    'copiado',
  );
});

test('el menú se maneja con el teclado y se cierra con Escape', async ({
  page,
}) => {
  const curva = await abrirCurva(page);
  const boton = curva.getByRole('button', { name: 'Exportar' });
  await boton.focus();
  await page.keyboard.press('ArrowDown');
  await expect(
    curva.getByRole('menuitem', { name: 'Datos (CSV)' }),
  ).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(curva.getByRole('menuitem', { name: /SVG/ })).toBeFocused();
  await page.keyboard.press('End');
  await expect(
    curva.getByRole('menuitem', { name: /incrustar/ }),
  ).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(boton).toHaveAttribute('aria-expanded', 'false');
  await expect(boton).toBeFocused();
});

test('el menú abierto no presenta violaciones WCAG A y AA', async ({
  page,
}) => {
  const curva = await abrirCurva(page);
  await curva.getByRole('button', { name: 'Exportar' }).click();
  const resultados = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    .include('section:has(#curva-epidemica)')
    .analyze();
  expect(resultados.violations).toEqual([]);
});

const PANELES_CLIMA = [
  'aporte',
  'asociacion',
  'ciclo',
  'paises',
  'pais-variable',
] as const;

test('cada panel de clima tiene un solo botón «Exportar» con la imagen y los datos completos', async ({
  page,
}) => {
  await simularClimaDengue(page);
  await page.goto('/analisis/clima');
  for (const id of PANELES_CLIMA) {
    const panel = page.locator(`[data-panel-clima="${id}"]`);
    await panel.scrollIntoViewIfNeeded();
    await expect(panel.locator('svg[role="img"]').first()).toBeVisible();
    await expect(panel.getByRole('button', { name: /Descargar/ })).toHaveCount(
      0,
    );
    const boton = panel.getByRole('button', { name: /Exportar/ });
    await expect(boton).toHaveCount(1);
    await boton.click();
    const opciones = panel.getByRole('menuitem');
    await expect(opciones).toHaveCount(3);
    await expect(opciones.nth(0)).toHaveText('Imagen vectorial (SVG)');
    await expect(opciones.nth(1)).toHaveText('Imagen (PNG)');
    await expect(opciones.nth(2)).toHaveAttribute(
      'href',
      /\/api\/clima-dengue\/(por-anio|multipais)$/,
    );
    await page.keyboard.press('Escape');
    await expect(boton).toHaveAttribute('aria-expanded', 'false');
  }
});

test('la descarga de los dos archivos de clima va en un solo menú sin opciones de imagen', async ({
  page,
}) => {
  await simularClimaDengue(page);
  await page.goto('/analisis/clima');
  const seccion = page.locator(
    'section[aria-labelledby="clima-descargas-titulo"]',
  );
  await seccion.scrollIntoViewIfNeeded();
  await expect(seccion.getByRole('link')).toHaveCount(0);
  await seccion.getByRole('button', { name: /Exportar/ }).click();
  await expect(seccion.getByRole('menuitem')).toHaveText([
    'El Salvador por año (JSON)',
    '18 países (JSON)',
  ]);
  // Las opciones de enlace también se recorren con el teclado.
  await page.keyboard.press('ArrowDown');
  await expect(
    seccion.getByRole('menuitem', { name: '18 países (JSON)' }),
  ).toBeFocused();
});
