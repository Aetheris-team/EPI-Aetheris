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
    await page.route('**/api/alertas?**', (r) => r.fulfill({ json: PAYLOAD }));
    await page.route('**/api/alertas', (r) => r.fulfill({ json: PAYLOAD }));
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
    await page.route('**/api/alertas**', (r) =>
      r.fulfill({
        json: { ...PAYLOAD, alertas: [PAYLOAD.alertas[2]] },
      }),
    );
    await page.reload();
    await expect(page.locator('[data-alertas-vacio]')).toContainText(
      'No hay alertas vigentes para Usulután',
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

  test('el formulario de alta ofrece los 14 departamentos', async ({
    page,
  }) => {
    await page.goto('/alertas/nueva');
    await expect(page.locator('input[name="departamentos"]')).toHaveCount(14);
    await expect(page.getByRole('group', { name: /Alcance/ })).toContainText(
      'Sin marcar ninguno, la alerta es nacional',
    );
  });

  test('la vista previa de indicaciones muestra el HTML como texto', async ({
    page,
  }) => {
    await page.goto('/alertas/nueva');
    await page
      .locator('textarea[name="indicaciones"]')
      .fill(
        '- <img src=x onerror="window.__inyectado = true"> uno\n<b>dos</b>',
      );
    const vista = page.locator('#preview-indicaciones');
    await expect(vista).toContainText('<img src=x onerror=');
    await expect(vista.locator('img, b')).toHaveCount(0);
    expect(await page.evaluate(() => 'inyectado' in window)).toBe(false);
  });

  test('el token recordado vive en sessionStorage, no en localStorage', async ({
    page,
  }) => {
    await page.goto('/alertas/nueva');
    await page.evaluate(() =>
      window.localStorage.setItem('epi-aetheris:alertas-token', 'viejo'),
    );
    await page.reload();
    expect(
      await page.evaluate(() =>
        window.localStorage.getItem('epi-aetheris:alertas-token'),
      ),
    ).toBeNull();

    await page.locator('input[name="token"]').fill('secreto-de-prueba');
    await page.locator('[data-alerta-recordar-token]').check();
    // Un envío con el formulario incompleto no llega al servidor, pero el
    // navegador no dispara submit; se fuerza para ejercitar el guardado.
    await page.evaluate(() =>
      document
        .querySelector<HTMLFormElement>('[data-form-alerta]')
        ?.dispatchEvent(new Event('submit', { cancelable: true })),
    );
    expect(
      await page.evaluate(() =>
        window.sessionStorage.getItem('epi-aetheris:alertas-token'),
      ),
    ).toBe('secreto-de-prueba');
    expect(
      await page.evaluate(() =>
        window.localStorage.getItem('epi-aetheris:alertas-token'),
      ),
    ).toBeNull();
  });
});
