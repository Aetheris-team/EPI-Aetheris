import { expect, test } from '@playwright/test';

import {
  ANONIMA,
  CUENTAS_HABILITADAS,
  sesion,
  simularApi,
} from './cuenta-comun';

const SESIONES = {
  sesiones: [
    {
      id: 's-1',
      creada_en: '2026-10-03T14:00:00+00:00',
      ultima_actividad_en: '2026-10-04T09:30:00+00:00',
      agente: 'Firefox en Linux',
      red: '190.5.0.0/24',
      actual: true,
    },
  ],
};

// Playwright desactiva por defecto la caché de páginas del historial
// (bfcache) y su Chromium sin interfaz no la implementa. Aquí hace falta
// activa para reproducir lo que ve un navegador real al pulsar "Atrás".
test.use({
  channel: 'chromium',
  launchOptions: { ignoreDefaultArgs: ['--disable-back-forward-cache'] },
});

test.describe('cuentas: historial del navegador tras salir', () => {
  test.skip(
    !CUENTAS_HABILITADAS,
    'Las cuentas están apagadas en este servidor.',
  );

  test('"Atrás" después de salir no vuelve a mostrar los datos de la cuenta', async ({
    page,
  }) => {
    let actual: unknown = sesion();
    await simularApi(page, {
      'GET /api/cuenta/sesion': () => ({ json: actual }),
      'GET /api/cuenta/sesiones': { json: SESIONES },
      'POST /api/cuenta/salir': () => {
        actual = ANONIMA;
        return { json: { mensaje: 'Sesión cerrada.' } };
      },
    });

    await page.goto('/cuenta');
    await expect(page.locator('[data-dato="correo"]')).toHaveText(
      'ana@salud.gob.sv',
    );

    await page.getByRole('button', { name: 'Salir de esta sesión' }).click();
    await expect(page).toHaveURL(/\/cuenta\/ingresar$/);
    await expect(page.getByLabel('Correo', { exact: true })).toBeVisible();

    await page.goBack({ waitUntil: 'commit' });

    // Con la página restaurada del historial, el correo seguiría a la vista
    // aunque la sesión ya no exista. Debe volver a consultarse y mandar a
    // ingresar.
    await expect(page).toHaveURL(/\/cuenta\/ingresar(\?.*)?$/);
    await expect(page.locator('[data-dato="correo"]')).toHaveCount(0);
  });
});
