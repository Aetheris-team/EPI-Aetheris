import { expect, test } from '@playwright/test';

const semanas = Array.from({ length: 52 }, (_, i) => ({
  semana_epi: i + 1,
  probable: {
    casos_observados: 10 + i,
    percentil: 50,
    categoria: 'media',
    p50_baseline: 20,
    p75_baseline: 40,
    n_obs_baseline: 4,
    anios_baseline: 4,
  },
  confirmado: {
    casos_observados: 1,
    percentil: 10,
    categoria: 'baja',
    p50_baseline: 2,
    p75_baseline: 4,
    n_obs_baseline: 4,
    anios_baseline: 4,
  },
}));

test('el canal endémico se descarga como SVG con el pie de fuente y sin variables CSS', async ({
  page,
}) => {
  await page.route('**/api/v1/presion/temporal/**', (ruta) =>
    ruta.fulfill({
      json: {
        departamento_codigo: 'SV-SS',
        departamento_nombre: 'San Salvador',
        anio: 2023,
        semanas,
        aviso: 'x',
      },
    }),
  );
  await page.goto('/departamento/SV-SS');
  const canal = page.locator('[data-canal-endemico]');
  await expect(canal.locator('[data-canal-grafica] svg').first()).toBeVisible();

  // Un solo botón «Exportar» con las opciones de imagen en su menú.
  await expect(canal.getByRole('button', { name: /^Descargar/ })).toHaveCount(
    0,
  );
  await canal.getByRole('button', { name: /Exportar/ }).click();
  await expect(canal.getByRole('menuitem')).toHaveText([
    'Imagen vectorial (SVG)',
    'Imagen (PNG)',
  ]);
  const [descarga] = await Promise.all([
    page.waitForEvent('download'),
    canal.getByRole('menuitem', { name: /SVG/ }).click(),
  ]);
  expect(descarga.suggestedFilename()).toBe('canal-endemico.svg');
  const ruta = await descarga.path();
  const { readFile } = await import('node:fs/promises');
  const texto = await readFile(ruta, 'utf8');
  expect(texto).toContain('Fuente: Boletines epidemiológicos de MINSAL');
  expect(texto).toContain('Filtros: SV-SS · 2023');
  expect(texto).not.toContain('var(--');
});

test('el canal endémico se descarga como PNG', async ({ page }) => {
  await page.route('**/api/v1/presion/temporal/**', (ruta) =>
    ruta.fulfill({
      json: {
        departamento_codigo: 'SV-SS',
        departamento_nombre: 'San Salvador',
        anio: 2023,
        semanas,
        aviso: 'x',
      },
    }),
  );
  await page.goto('/departamento/SV-SS');
  const canal = page.locator('[data-canal-endemico]');
  await expect(canal.locator('[data-canal-grafica] svg').first()).toBeVisible();
  await canal.getByRole('button', { name: /Exportar/ }).click();
  const [descarga] = await Promise.all([
    page.waitForEvent('download'),
    canal.getByRole('menuitem', { name: /PNG/ }).click(),
  ]);
  expect(descarga.suggestedFilename()).toBe('canal-endemico.png');
});

test('el menú de un panel ofrece la descarga solo si hay gráfico', async ({
  page,
}) => {
  await page.goto('/dengue');
  await expect(page.locator('#heatmap-resumen')).not.toContainText('Cargando');
  const menuMapa = page.locator('[data-boton-menu-panel="mapa"]');
  await menuMapa.click();
  await expect(
    page.locator('[data-menu-panel="mapa"] [data-accion-panel="exportar-svg"]'),
  ).toBeHidden();
  await page.keyboard.press('Escape');
  await page.locator('[data-boton-menu-panel="presion"]').click();
  await expect(
    page.locator(
      '[data-menu-panel="presion"] [data-accion-panel="exportar-svg"]',
    ),
  ).toBeVisible();
});
