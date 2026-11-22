import { expect, test } from '@playwright/test';

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

const PAYLOAD = {
  aviso: 'Aviso de prueba.',
  ultima_revision: '2026-09-01',
  alertas: [
    alerta(1, 'Alerta nacional de prueba', null),
    alerta(2, 'Alerta de San Salvador', ['SV-SS']),
    alerta(3, 'Alerta de Santa Ana', ['SV-SA']),
  ],
};

test.describe('alertas con alcance territorial', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/datos/alertas/registradas-activas.json', (r) =>
      r.fulfill({ json: PAYLOAD }),
    );
  });

  test('cada tarjeta muestra su alcance y sin filtro aparecen todas', async ({
    page,
  }) => {
    await page.goto('/alertas');
    const tarjetas = page.locator('[data-alerta]');
    await expect(tarjetas).toHaveCount(3);
    await expect(page.locator('#alerta-1 [data-alerta-alcance]')).toHaveText(
      'Nacional',
    );
    await expect(page.locator('#alerta-2 [data-alerta-alcance]')).toHaveText(
      'San Salvador',
    );
  });

  test('filtra por departamento y conserva el estado en la URL', async ({
    page,
  }) => {
    await page.goto('/alertas');
    await expect(page.locator('[data-alerta]')).toHaveCount(3);
    await page.locator('[data-filtro-departamento]').selectOption('SV-SS');
    await expect(page.locator('[data-alerta]')).toHaveCount(2);
    await expect(page.locator('#alerta-3')).toHaveCount(0);
    expect(page.url()).toContain('dept=SV-SS');

    await page.reload();
    await expect(page.locator('[data-alerta]')).toHaveCount(2);
    await expect(page.locator('[data-filtro-departamento]')).toHaveValue(
      'SV-SS',
    );
  });

  test('sin alertas para el departamento lo dice en lugar de mostrar otras', async ({
    page,
  }) => {
    await page.goto('/alertas?dept=SV-US');
    await expect(page.locator('[data-alerta]')).toHaveCount(1);
    await page.route('**/datos/alertas/registradas-activas.json', (r) =>
      r.fulfill({
        json: { ...PAYLOAD, alertas: [PAYLOAD.alertas[2]] },
      }),
    );
    await page.reload();
    await expect(page.locator('[data-alertas-vacio]')).toContainText(
      'No hay alertas registradas para Usulután',
    );
  });

  test('usa el departamento recordado cuando la URL no trae dept', async ({
    page,
  }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('epi:departamento', 'SV-SA');
    });
    await page.goto('/alertas');
    await expect(page.locator('[data-filtro-departamento]')).toHaveValue(
      'SV-SA',
    );
    await expect(page.locator('[data-alerta]')).toHaveCount(2);
    await expect(page.locator('#alerta-2')).toHaveCount(0);
  });
});
