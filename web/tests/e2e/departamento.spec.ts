import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

function alerta(id: number, titulo: string, departamentos: string[] | null) {
  return {
    id,
    tipo: 'dengue',
    nivel: 'informativo',
    titulo,
    contexto: 'Contexto de prueba.',
    indicaciones: '- Indicación de prueba.',
    fuente: 'Prueba automatizada',
    autor: 'suite de tests',
    vigente_desde: '2026-09-01',
    vigente_hasta: null,
    activa: true,
    etiqueta: null,
    departamentos,
  };
}

const ALERTAS = {
  aviso: 'Aviso de prueba.',
  ultima_revision: '2026-09-01',
  alertas: [
    alerta(1, 'Alerta nacional de prueba', null),
    alerta(2, 'Alerta de San Salvador', ['SV-SS']),
    alerta(3, 'Alerta de Santa Ana', ['SV-SA']),
  ],
};

const SEMANAS_PRESION = Array.from({ length: 52 }, (_, i) => ({
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

async function simularApi(page: Page) {
  await page.route('**/api/alertas?**', (r) => r.fulfill({ json: ALERTAS }));
  await page.route('**/api/alertas', (r) => r.fulfill({ json: ALERTAS }));
  await page.route('**/datos/v1/presion/temporal/**', (r) =>
    r.fulfill({
      json: {
        departamento_codigo: 'SV-SS',
        departamento_nombre: 'San Salvador',
        anio: 2023,
        semanas: SEMANAS_PRESION,
        aviso: 'x',
      },
    }),
  );
  await page.route('**/datos/v1/temporal/**', (r) =>
    r.fulfill({
      json: {
        departamento_codigo: 'SV-SS',
        departamento_nombre: 'San Salvador',
        anio: 2026,
        semanas: Array.from({ length: 30 }, (_, i) => ({
          semana_epi: i + 1,
          iv_real: 0.4 + (i % 5) / 20,
          p25_baseline: 0.35,
          mediana_baseline: 0.45,
          p75_baseline: 0.55,
          anomaly_sigma: 0.3,
        })),
        aviso: 'x',
      },
    }),
  );
  for (const evento of ['ira', 'neumonias']) {
    await page.route(`**/datos/${evento}/temporal/*`, (r) =>
      r.fulfill({
        json: {
          departamento_codigo: 'SV-SS',
          departamento_nombre: 'San Salvador',
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
      }),
    );
  }
}

test.describe('página por departamento', () => {
  test.beforeEach(async ({ page }) => {
    await simularApi(page);
  });

  test('reúne alertas que le aplican, canal, clima y respiratorio', async ({
    page,
  }) => {
    await page.goto('/departamento/SV-SS');
    await expect(page.locator('h1')).toHaveText('San Salvador');
    const alertas = page.locator('[data-alertas-lista] li');
    await expect(alertas).toHaveCount(2);
    await expect(alertas.first()).toContainText('Alerta de San Salvador');
    await expect(page.locator('[data-alertas-lista]')).not.toContainText(
      'Santa Ana',
    );
    await expect(
      page.locator('[data-canal-endemico] [data-canal-grafica] svg').first(),
    ).toBeVisible();
    await expect(page.locator('[data-clima-resumen]')).toContainText('Iv');
    await expect(
      page.locator('[data-curva-evento="ira"] svg').first(),
    ).toBeVisible();
    await expect(
      page.locator('[data-curva-evento="ira"] [data-curva-depto]'),
    ).toBeHidden();
    await expect(page.locator('[data-enlace-ficha]')).toHaveAttribute(
      'href',
      '/analisis/ficha/SV-SS',
    );
  });

  test('recordar el departamento cambia el filtro inicial de /alertas', async ({
    page,
  }) => {
    await page.goto('/departamento/SV-SS');
    await page.locator('[data-recordar-departamento]').click();
    await expect(page.locator('[data-recordar-departamento]')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await page.goto('/alertas');
    await expect(page.locator('[data-filtro-departamento]')).toHaveValue(
      'SV-SS',
    );
    await page.goto('/');
    await expect(page.locator('[data-tu-departamento-enlace]')).toHaveAttribute(
      'href',
      '/departamento/SV-SS',
    );
  });

  test('sin almacenamiento la página se ve igual', async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, 'localStorage', {
        get() {
          throw new Error('bloqueado');
        },
      });
    });
    await page.goto('/departamento/SV-SS');
    await page.locator('[data-recordar-departamento]').click();
    await expect(page.locator('[data-recordar-estado]')).toContainText(
      'no permite guardar',
    );
    await expect(page.locator('h1')).toHaveText('San Salvador');
  });

  test('no desborda horizontalmente a 375 px', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await page.goto('/departamento/SV-SS');
    await expect(page.locator('[data-alertas-lista] li').first()).toBeVisible();
    const desborde = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(desborde).toBeLessThanOrEqual(0);
  });

  test('no presenta violaciones automáticas WCAG A y AA', async ({ page }) => {
    await page.goto('/departamento/SV-SS');
    await expect(page.locator('[data-alertas-lista] li').first()).toBeVisible();
    await expect(
      page.locator('[data-canal-endemico] [data-canal-grafica] svg').first(),
    ).toBeVisible();
    const resultados = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    expect(resultados.violations).toEqual([]);
  });
});

test('el enlace del recordado sustituye al departamento vacío de /dengue', async ({
  page,
}) => {
  await page.addInitScript(() =>
    window.localStorage.setItem('epi:departamento', 'SV-SS'),
  );
  await page.goto('/dengue?year=2023');
  await expect(page).toHaveURL(/dept=SV-SS/);
});

test('un enlace con dept explícito no lo pisa el recordado', async ({
  page,
}) => {
  await page.addInitScript(() =>
    window.localStorage.setItem('epi:departamento', 'SV-SS'),
  );
  await page.goto('/dengue?year=2023&dept=SV-SA');
  await expect(page).toHaveURL(/dept=SV-SA/);
});
