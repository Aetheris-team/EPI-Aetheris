import { expect, test, type Page } from '@playwright/test';

const DEPARTAMENTOS = [
  ['SV-AH', 'Ahuachapán'],
  ['SV-CA', 'Cabañas'],
  ['SV-CH', 'Chalatenango'],
  ['SV-CU', 'Cuscatlán'],
  ['SV-LI', 'La Libertad'],
  ['SV-MO', 'Morazán'],
  ['SV-PA', 'La Paz'],
  ['SV-SA', 'Santa Ana'],
  ['SV-SM', 'San Miguel'],
  ['SV-SO', 'Sonsonate'],
  ['SV-SS', 'San Salvador'],
  ['SV-SV', 'San Vicente'],
  ['SV-UN', 'La Unión'],
  ['SV-US', 'Usulután'],
];

async function simularApi(page: Page) {
  for (const evento of ['ira', 'neumonias']) {
    await page.route(`**/datos/${evento}/departamental.json`, (r) =>
      r.fulfill({
        json: {
          aviso: 'x',
          departamentos: DEPARTAMENTOS.map(([codigo, nombre], i) => ({
            codigo,
            nombre,
            notificado_total: 100 + i,
            semanas_con_dato: 100,
            primer_anio: 2018,
            ultimo_anio: 2023,
          })),
        },
      }),
    );
    await page.route(`**/datos/${evento}/temporal/*`, (r) => {
      const codigo = r.request().url().split('/').pop()?.split('?')[0] ?? '';
      const nombre = DEPARTAMENTOS.find(([c]) => c === codigo)?.[1] ?? codigo;
      return r.fulfill({
        json: {
          departamento_codigo: codigo,
          departamento_nombre: nombre,
          anios: [2022, 2023],
          series: {
            '2022': [
              [1, 5],
              [2, 8],
            ],
            '2023': [
              [1, 10],
              [2, 20],
            ],
          },
          aviso: 'x',
        },
      });
    });
  }
  await page.route('**/datos/neumonias/heatmap/*', (r) =>
    r.fulfill({
      json: {
        departamentos: DEPARTAMENTOS.map(([codigo, nombre]) => ({
          codigo,
          nombre,
          semanas: { '1': 5, '2': 7 },
        })),
      },
    }),
  );
}

test.describe('respiratorio con estado compartido', () => {
  test('elegir un departamento en el mapa mueve las curvas y el mapa de calor', async ({
    page,
  }) => {
    await simularApi(page);
    await page.goto('/respiratorio');
    const solicitudIra = page.waitForRequest('**/datos/ira/temporal/SV-SA*');
    const solicitudNeu = page.waitForRequest(
      '**/datos/neumonias/temporal/SV-SA*',
    );

    const rutaSantaAna = page.locator(
      '#ira path[aria-label="Seleccionar Santa Ana"]',
    );
    await expect(rutaSantaAna).toBeAttached({ timeout: 20_000 });
    await rutaSantaAna.dispatchEvent('click');
    await solicitudIra;
    await solicitudNeu;

    await expect(page.locator('#ira [data-curva-depto]')).toHaveValue('SV-SA');
    await expect(page.locator('#neumonias [data-curva-depto]')).toHaveValue(
      'SV-SA',
    );
    await expect(page.locator('#ira [data-mapa-seleccion]')).toContainText(
      'Santa Ana',
    );
    await expect(
      page.locator('[data-heatmap-neu] [data-fila-seleccionada] th'),
    ).toContainText('Santa Ana');
    expect(page.url()).toContain('dept=SV-SA');
  });

  test('una recarga conserva departamento, año y rango', async ({ page }) => {
    await simularApi(page);
    await page.goto('/respiratorio?dept=SV-LI&year=2022&fromWeek=3&toWeek=20');
    await expect(page.locator('#ira [data-curva-depto]')).toHaveValue('SV-LI', {
      timeout: 20_000,
    });
    await expect(page.locator('#ira [data-curva-anio]')).toHaveValue('2022');
    await expect(page.locator('#ira [data-curva-rango]')).toHaveText(
      'SE3–SE20',
    );
    await expect(page.locator('[data-heatmap-neu] [data-hm-anio]')).toHaveValue(
      '2022',
    );
    await expect(
      page.locator('[data-heatmap-neu] [data-fila-seleccionada] th'),
    ).toContainText('La Libertad');
  });

  test('cambiar el año en una curva cambia el del mapa de calor y la URL', async ({
    page,
  }) => {
    await simularApi(page);
    await page.goto('/respiratorio');
    await expect(page.locator('#ira [data-curva-depto] option')).toHaveCount(
      14,
      { timeout: 20_000 },
    );
    await page.locator('#ira [data-curva-anio]').selectOption('2021');
    await expect(page.locator('[data-heatmap-neu] [data-hm-anio]')).toHaveValue(
      '2021',
    );
    await expect(page.locator('#neumonias [data-curva-anio]')).toHaveValue(
      '2021',
    );
    expect(page.url()).toContain('year=2021');
  });
});
