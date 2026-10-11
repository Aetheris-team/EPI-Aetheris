import { readFile } from 'node:fs/promises';

import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test.describe('observatorio respiratorio', () => {
  test('carga IRA, Neumonías, virus y cobertura sin lenguaje de riesgo/causalidad', async ({
    page,
  }) => {
    await page.goto('/respiratorio');
    await expect(
      page.getByRole('heading', { name: /Observatorio respiratorio/i }),
    ).toBeVisible();
    await expect(page.locator('body')).not.toContainText('La Influenza causó');
    await expect(page.locator('main')).toContainText(
      'Observatorio respiratorio · MINSAL',
    );
    await expect(page.locator('main')).not.toContainText('sin predicción');

    const cobertura = page.locator('[data-cobertura]');
    await expect(cobertura).toContainText('MINSAL', { timeout: 15_000 });
    await expect(cobertura).toContainText('Neumonías');
    await expect(cobertura).not.toContainText('score de riesgo');

    await expect(page.locator('#ira [data-mapa-evento="ira"]')).toBeVisible();
    await expect(
      page.locator('#neumonias [data-mapa-evento="neumonias"]'),
    ).toBeVisible();
    await expect(
      page.locator('#ira [data-mapa-evento="ira"] .leaflet-container'),
    ).toBeVisible({ timeout: 20_000 });
    await expect(
      page.locator(
        '#neumonias [data-mapa-evento="neumonias"] .leaflet-container',
      ),
    ).toBeVisible({ timeout: 20_000 });
    await expect(
      page
        .locator('#ira [data-mapa-evento="ira"] path.leaflet-interactive')
        .first(),
    ).toBeVisible();
    await expect(
      page
        .locator(
          '#neumonias [data-mapa-evento="neumonias"] path.leaflet-interactive',
        )
        .first(),
    ).toBeVisible();

    const heatmap = page.locator('[data-heatmap-neu]');
    await expect(heatmap.locator('table')).toBeVisible({ timeout: 20_000 });
    await expect(heatmap).toContainText('San Salvador');
    await expect(heatmap).toContainText(/conteo notificado/i);

    await heatmap.locator('[data-hm-anio]').selectOption('2019');
    await expect(heatmap.locator('table')).toBeVisible();

    const virus = page.locator('[data-panel-virus]');
    await expect(virus).toContainText('nacional');
    await expect(virus.locator('table')).toBeVisible({ timeout: 20_000 });
    const toggles = virus.locator('[data-virus-toggles]');
    await expect(toggles).toContainText('influenza');
    await expect(toggles).not.toContainText('influenza_a_h1n1');
    await expect(toggles).not.toContainText('influenza_a_h3n2');
    await expect(toggles).not.toContainText('influenza_a_no_subtipificado');
    await expect(toggles).not.toContainText('influenza_b');
  });

  test('la curva de neumonías admite año y rango SE', async ({ page }) => {
    await page.goto('/respiratorio#neumonias');
    const curva = page.locator('#neumonias [data-curva-evento="neumonias"]');
    // Neumonías sí está cargada en esta base; IRA puede estar vacía.
    const grafico = curva.locator('svg[role="img"]');
    await expect(grafico).toBeVisible({ timeout: 20_000 });
    await curva.locator('[data-curva-anio]').selectOption('2023');
    await expect(grafico).toBeVisible();
    await curva.locator('[data-curva-desde]').fill('10');
    await curva.locator('[data-curva-hasta]').fill('20');
    await expect(curva.locator('[data-curva-rango]')).toHaveText(/SE10–SE20/);
  });

  test('el CSV del heatmap respeta el rango SE seleccionado', async ({
    page,
  }) => {
    await page.goto('/respiratorio');
    const heatmap = page.locator('[data-heatmap-neu]');
    await expect(heatmap.locator('table')).toBeVisible({ timeout: 20_000 });
    await heatmap.locator('[data-hm-desde]').fill('10');
    await heatmap.locator('[data-hm-hasta]').fill('20');
    await expect(heatmap.locator('[data-hm-rango]')).toHaveText(/SE10–SE20/);

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      heatmap.getByRole('button', { name: /Exportar.*CSV/i }).click(),
    ]);
    const tmp = test.info().outputPath('neumonias-heatmap.csv');
    await download.saveAs(tmp);
    const contenido = await readFile(tmp, 'utf8');
    const semanas = contenido
      .trim()
      .split('\n')
      .slice(1)
      .map((linea) => Number(linea.split(',')[3]));
    expect(semanas.length).toBeGreaterThan(0);
    expect(Math.min(...semanas)).toBe(10);
    expect(Math.max(...semanas)).toBe(20);
    expect(semanas.every((s) => s >= 10 && s <= 20)).toBe(true);
    expect(contenido).not.toMatch(/,9,/);
    expect(contenido).not.toMatch(/,21,/);
  });

  test('muestras analizadas usa vigilancia total y no muestra toggles de virus', async ({
    page,
  }) => {
    await page.goto('/respiratorio');
    const virus = page.locator('[data-panel-virus]');
    await expect(virus.locator('table')).toBeVisible({ timeout: 20_000 });
    await virus
      .locator('[data-virus-metrica]')
      .selectOption('muestras_analizadas');
    await expect(virus.locator('[data-virus-global]')).toBeVisible();
    await expect(virus.locator('[data-virus-global]')).toContainText(
      'Todos los virus / vigilancia total',
    );
    await expect(virus.locator('[data-virus-toggles]')).toBeHidden();
    await expect(virus.locator('table')).toBeVisible();
    await expect(virus.locator('table')).toContainText(
      'Todos los virus / vigilancia total',
    );
  });

  test('si la API de cobertura falla, el panel no inventa cifras', async ({
    page,
  }) => {
    await page.route('**/api/respiratorios/cobertura', (route) =>
      route.fulfill({ status: 500, body: 'error' }),
    );
    await page.goto('/respiratorio');
    await expect(page.locator('[data-cob-error]')).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.locator('[data-cob-error]')).toContainText(
      'No se pudo cargar',
    );
  });

  test('si la API responde disponible:false, se muestra el motivo y no un error de red', async ({
    page,
  }) => {
    const motivo =
      'Los datos de vigilancia de virus respiratorios no están disponibles en este despliegue (tabla ausente o sin filas).';
    const cuerpo = JSON.stringify({
      disponible: false,
      motivo,
      aviso: 'aviso de honestidad',
    });
    await page.route('**/api/respiratorios/cobertura', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: cuerpo,
      }),
    );
    await page.route('**/api/respiratorios/virus', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: cuerpo,
      }),
    );
    await page.goto('/respiratorio');
    await expect(page.locator('[data-cob-cuerpo]')).toContainText(
      'tabla ausente o sin filas',
      { timeout: 15_000 },
    );
    await expect(page.locator('[data-cob-error]')).toBeHidden();
    await expect(page.locator('[data-panel-virus]')).toContainText(
      'tabla ausente o sin filas',
    );
    await expect(page.locator('[data-virus-error]')).toBeHidden();
  });

  test('la serie nacional del tablero marca la semana sin publicar', async ({
    page,
  }) => {
    // 2025 completo hasta la SE52 y la SE53 sin fila, como en el tablero.
    const inicio2025 = Date.UTC(2024, 11, 29);
    const semanas = [
      ...Array.from({ length: 52 }, (_, i) => ({
        semana_inicio: new Date(inicio2025 + i * 7 * 86_400_000)
          .toISOString()
          .slice(0, 10),
        anio: 2025,
        semana_epi: i + 1,
        conteo: 300 - i,
      })),
      { semana_inicio: '2026-01-04', anio: 2026, semana_epi: 1, conteo: 263 },
      { semana_inicio: '2026-01-11', anio: 2026, semana_epi: 2, conteo: 210 },
    ];
    await page.route('**/api/neumonias/nacional', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          disponible: true,
          evento: 'neumonias',
          fuente: 'minsal_tablero',
          unidad: 'conteo_notificado',
          semanas,
          aviso: 'aviso',
        }),
      }),
    );
    await page.goto('/respiratorio#neumonias');
    const panel = page.locator('[data-nac-evento="neumonias"]');
    await expect(panel.locator('[data-nac-canvas] svg')).toBeVisible({
      timeout: 15_000,
    });
    await expect(panel.locator('[data-nac-resumen]')).toContainText(
      'SE2 de 2026',
    );
    await expect(panel.locator('[data-nac-resumen]')).toContainText(
      '30 % menos que en la misma semana de 2025 (299)',
    );
    await expect(panel.locator('[data-nac-huecos]')).toHaveText(
      'Sin publicar en el tablero: SE53 de 2025.',
    );

    await panel.getByText('Ver los valores semanales en una tabla').click();
    const tabla = panel.locator('[data-nac-tabla]');
    await expect(tabla.locator('tbody tr')).toHaveCount(53);
    await expect(tabla.locator('tbody tr').last()).toContainText(
      'sin publicar',
    );
    // Las semanas que aún no llegan en 2026 quedan vacías, no «sin publicar».
    await expect(tabla.locator('tbody tr').nth(2)).not.toContainText(
      'sin publicar',
    );

    await panel.getByRole('button', { name: /Exportar/ }).click();
    const [descarga] = await Promise.all([
      page.waitForEvent('download'),
      panel.getByRole('menuitem', { name: 'Datos (CSV)' }).click(),
    ]);
    const tmp = test.info().outputPath('neumonias-nacional.csv');
    await descarga.saveAs(tmp);
    const lineas = (await readFile(tmp, 'utf8')).trim().split('\n');
    expect(lineas).toHaveLength(semanas.length + 1);
    expect(lineas[53]).toBe('2026-01-04,2026,1,263,minsal_tablero');

    const resultados = await new AxeBuilder({ page })
      .include('[data-nac-evento]')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(resultados.violations).toEqual([]);
  });

  test('sin capturas del tablero, la serie nacional muestra el motivo', async ({
    page,
  }) => {
    const motivo =
      'La serie nacional del tablero de MINSAL no está cargada en este despliegue.';
    await page.route('**/api/ira/nacional', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ disponible: false, motivo, aviso: 'aviso' }),
      }),
    );
    await page.goto('/respiratorio#ira');
    const panel = page.locator('[data-nac-evento="ira"]');
    await expect(panel.locator('[data-nac-canvas]')).toHaveText(motivo, {
      timeout: 15_000,
    });
    await expect(panel.getByRole('button', { name: 'Reintentar' })).toHaveCount(
      0,
    );
    await expect(panel.locator('[data-nac-detalle]')).toBeHidden();
    // Sin serie no hay datos que exportar: la opción de CSV queda inactiva.
    await panel.getByRole('button', { name: /Exportar/ }).click();
    await expect(
      panel.getByRole('menuitem', { name: 'Datos (CSV)' }),
    ).toBeDisabled();
  });
});
