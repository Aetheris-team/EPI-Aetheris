import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { climaPorAnio, simularClimaDengue } from './clima-dengue-mock';

const PANELES = [
  'aporte',
  'asociacion',
  'ciclo',
  'paises',
  'pais-variable',
] as const;

/** Los paneles cargan al acercarse a la pantalla: se recorren todos. */
async function cargarTodos(page: Page): Promise<void> {
  for (const id of PANELES) {
    const panel = page.locator(`[data-panel-clima="${id}"]`);
    await panel.scrollIntoViewIfNeeded();
    await expect(panel.locator('[data-contenido]')).toBeVisible();
    await expect(panel.locator('svg[role="img"]').first()).toBeVisible();
  }
}

test('/analisis ofrece la tarjeta de clima y dengue', async ({ page }) => {
  await page.goto('/analisis');
  await expect(
    page.locator('[data-herramienta="/analisis/clima"]'),
  ).toBeVisible();
});

test('/analisis/clima carga los cinco paneles con su gráfica y sus tablas', async ({
  page,
}) => {
  await simularClimaDengue(page);
  await page.goto('/analisis/clima');
  await expect(
    page.getByRole('heading', { level: 1, name: 'Clima y dengue' }),
  ).toBeVisible();
  await cargarTodos(page);
  for (const id of PANELES) {
    const panel = page.locator(`[data-panel-clima="${id}"]`);
    expect(await panel.locator('details').count()).toBeGreaterThan(0);
  }
  await expect(
    page.locator(
      'nav[aria-label="Navegación principal"] a[aria-current="page"]',
    ),
  ).toHaveText('Análisis');
});

test('el horizonte cambia el resumen del aporte del clima', async ({
  page,
}) => {
  await simularClimaDengue(page);
  await page.goto('/analisis/clima');
  const panel = page.locator('[data-panel-clima="aporte"]');
  await panel.scrollIntoViewIfNeeded();
  await expect(panel.locator('[data-resumen]')).toContainText(
    'A 4 semanas, el clima ayudó al pronóstico en 2 de 5 años (2021 y 2022)',
  );
  await panel.locator('[data-horizonte]').selectOption('8');
  await expect(panel.locator('[data-resumen]')).toContainText('A 8 semanas');
});

test('la tabla de la matriz por año trae una fila por año y la de todos', async ({
  page,
}) => {
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
  await expect(tabla.locator('tbody tr').last()).toContainText(
    'Todos los años',
  );
});

test('el ciclo cambia con el país y ofrece solo las variables que tiene', async ({
  page,
}) => {
  await simularClimaDengue(page);
  await page.goto('/analisis/clima');
  const panel = page.locator('[data-panel-clima="ciclo"]');
  await panel.scrollIntoViewIfNeeded();
  await expect(panel.locator('[data-resumen]')).toContainText('El Salvador:');
  await expect(panel.locator('[data-variable] option')).toHaveCount(7);
  await panel.locator('[data-pais]').selectOption('BERMUDA');
  await expect(panel.locator('[data-resumen]')).toContainText('Bermudas:');
  await expect(panel.locator('[data-variable] option')).toHaveCount(2);
});

test('la comparación de países cambia de 11 a 9 años', async ({ page }) => {
  await simularClimaDengue(page);
  await page.goto('/analisis/clima');
  const panel = page.locator('[data-panel-clima="paises"]');
  await panel.scrollIntoViewIfNeeded();
  await expect(panel.locator('[data-resumen]')).toContainText(
    'la menor de los 4 países',
  );
  await expect(
    panel.locator('svg text', { hasText: 'Correlación (11 años)' }),
  ).toHaveCount(1);
  await panel.getByLabel('9 años (sin 2020 y 2024)').check();
  await expect(
    panel.locator('svg text', { hasText: 'Correlación (9 años)' }),
  ).toHaveCount(1);
});

test('un país sin años evaluables aparece sin dato en la matriz por país', async ({
  page,
}) => {
  await simularClimaDengue(page);
  await page.goto('/analisis/clima');
  const panel = page.locator('[data-panel-clima="pais-variable"]');
  await panel.scrollIntoViewIfNeeded();
  await expect(panel.locator('[data-contenido]')).toBeVisible();
  await panel.getByText('Ver las correlaciones de los países en tabla').click();
  const fila = panel.getByRole('row', { name: /Bermudas/ });
  await expect(fila).toContainText('sin estimación');
});

test('sin artefacto los paneles lo dicen sin ofrecer reintentar', async ({
  page,
}) => {
  await simularClimaDengue(page, {
    porAnio: 'no-disponible',
    multipais: 'no-disponible',
  });
  await page.goto('/analisis/clima');
  for (const id of PANELES) {
    const panel = page.locator(`[data-panel-clima="${id}"]`);
    await panel.scrollIntoViewIfNeeded();
    await expect(panel.locator('[data-estado]')).toContainText(
      'El análisis aún no está generado en este despliegue.',
    );
    await expect(panel.getByRole('button', { name: 'Reintentar' })).toHaveCount(
      0,
    );
    await expect(panel.locator('[data-contenido]')).toBeHidden();
  }
});

test('un error de red permite reintentar y el panel se carga', async ({
  page,
}) => {
  let fallar = true;
  await page.route('**/datos/clima-dengue/por-anio.json', async (ruta) => {
    if (fallar) {
      await ruta.fulfill({ status: 500, body: 'error' });
      return;
    }
    await ruta.fulfill({ json: climaPorAnio() });
  });
  await page.goto('/analisis/clima');
  const panel = page.locator('[data-panel-clima="aporte"]');
  await panel.scrollIntoViewIfNeeded();
  const reintentar = panel.getByRole('button', { name: 'Reintentar' });
  await expect(reintentar).toBeVisible();
  fallar = false;
  await reintentar.click();
  await expect(panel.locator('[data-contenido]')).toBeVisible();
  await expect(panel.locator('svg[role="img"]').first()).toBeVisible();
});

test('/analisis/clima no tiene violaciones de accesibilidad', async ({
  page,
}) => {
  await simularClimaDengue(page);
  await page.goto('/analisis/clima');
  await cargarTodos(page);
  for (const resumen of await page
    .locator('[data-panel-clima] summary')
    .all()) {
    await resumen.click();
  }
  const resultados = await new AxeBuilder({ page })
    .include('main')
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  expect(resultados.violations).toEqual([]);
});
