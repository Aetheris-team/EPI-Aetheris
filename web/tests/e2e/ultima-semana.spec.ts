import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const CASOS = [
  {
    semana_inicio: '2025-07-20',
    anio: 2025,
    semana_epi: 30,
    conteo: 100,
    fuente: 'minsal_tablero',
  },
  {
    semana_inicio: '2026-07-19',
    anio: 2026,
    semana_epi: 30,
    conteo: 150,
    fuente: 'minsal_tablero',
  },
];

const INTEGRIDAD = {
  aviso: 'x',
  antiguedad: {
    dengue_tablero_nacional: {
      ultima_anio: 2026,
      ultima_semana_epi: 30,
      semanas: 80,
    },
  },
};

test.describe('última semana de dengue', () => {
  test('muestra la última semana y la comparación con el año anterior', async ({
    page,
  }) => {
    await page.route('**/datos/casos-nacional.json', (r) =>
      r.fulfill({ json: CASOS }),
    );
    await page.route('**/datos/v1/vigilancia/integridad.json', (r) =>
      r.fulfill({ json: INTEGRIDAD }),
    );
    await page.goto('/incrustar/ultima-semana');
    const franja = page.locator('#ultima-semana');
    await expect(franja).toContainText('SE30/2026', { timeout: 15_000 });
    await expect(franja).toContainText('150');
    await expect(franja).toContainText('Misma semana de 2025');
    await expect(franja).toContainText('+50 %');
    await expect(
      franja.getByRole('link', { name: 'Ver predicción' }),
    ).toHaveAttribute('href', /\/prediccion$/);
    const resultados = await new AxeBuilder({ page })
      .include('[data-ultima-semana]')
      .analyze();
    expect(resultados.violations).toEqual([]);
  });

  test('avisa cuando el tablero no trae semanas', async ({ page }) => {
    await page.route('**/datos/casos-nacional.json', (r) => r.fulfill({ json: [] }));
    await page.goto('/incrustar/ultima-semana');
    await expect(page.locator('#ultima-semana')).toContainText(
      'todavía no tiene semanas',
      { timeout: 15_000 },
    );
  });

  test('ofrece reintentar si la fuente falla', async ({ page }) => {
    await page.route('**/datos/casos-nacional.json', (r) =>
      r.fulfill({ status: 500 }),
    );
    await page.goto('/incrustar/ultima-semana');
    // Con la copia del build (sitio compilado) el fallo conserva la copia y
    // muestra un aviso, sin botón: lo cubre la prueba de la copia del build.
    test.skip(
      (await page.locator('#ultima-semana-instantanea').count()) > 0,
      'el sitio compilado conserva la copia del build',
    );
    await expect(
      page
        .locator('#ultima-semana')
        .getByRole('button', { name: /reintentar/i }),
    ).toBeVisible({ timeout: 15_000 });
  });
});

const INSTANTANEA = {
  generado: '2026-07-20',
  casos: [
    {
      semana_inicio: '2025-07-13',
      anio: 2025,
      semana_epi: 29,
      conteo: 90,
      fuente: 'minsal_tablero',
    },
    {
      semana_inicio: '2026-07-12',
      anio: 2026,
      semana_epi: 29,
      conteo: 120,
      fuente: 'minsal_tablero',
    },
  ],
};

// El servidor de desarrollo no toma la copia del build (import.meta.env.DEV);
// aquí se inyecta en el HTML como lo haría un build de producción.
async function conInstantanea(page: import('@playwright/test').Page) {
  await page.route('**/incrustar/ultima-semana', async (ruta) => {
    const respuesta = await ruta.fetch();
    const html = (await respuesta.text()).replace(
      /(<script[^>]*id="ultima-semana-instantanea"[^>]*>)[^<]*(<\/script>)/,
      `$1${JSON.stringify(INSTANTANEA)}$2`,
    );
    await ruta.fulfill({ response: respuesta, body: html });
  });
}

test('la franja se pinta con la copia del build mientras llega la API', async ({
  page,
}) => {
  await conInstantanea(page);
  await page.route('**/datos/casos-nacional.json', async (ruta) => {
    await new Promise((r) => setTimeout(r, 1500));
    await ruta.fulfill({ json: CASOS });
  });
  await page.route('**/datos/v1/vigilancia/integridad.json', (r) =>
    r.fulfill({ json: INTEGRIDAD }),
  );
  await page.goto('/incrustar/ultima-semana');
  const franja = page.locator('#ultima-semana');
  await expect(franja).toContainText('SE29/2026');
  await expect(franja).toContainText('Cifras guardadas al publicar el sitio');
  // Cuando llega la API la copia se reemplaza por la serie vigente.
  await expect(franja).toContainText('SE30/2026');
  await expect(franja).not.toContainText('Cifras guardadas');
});

test('si la API falla se conserva la copia del build con su aviso', async ({
  page,
}) => {
  await conInstantanea(page);
  await page.route('**/datos/casos-nacional.json', (r) =>
    r.fulfill({ status: 500, body: 'error' }),
  );
  await page.route('**/datos/v1/vigilancia/integridad.json', (r) =>
    r.fulfill({ json: INTEGRIDAD }),
  );
  await page.goto('/incrustar/ultima-semana');
  const franja = page.locator('#ultima-semana');
  await expect(franja).toContainText('No se pudo actualizar');
  await expect(franja).toContainText('SE29/2026');
});
