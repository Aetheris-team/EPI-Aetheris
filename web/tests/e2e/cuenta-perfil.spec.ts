import { expect, test } from '@playwright/test';

import {
  ANONIMA,
  CUENTAS_HABILITADAS,
  error,
  sesion,
  simularApi,
  sinViolacionesAxe,
} from './cuenta-comun';

const FACTORES = [
  { id: 'f-1', tipo: 'totp', etiqueta: 'Aplicación de autenticación' },
  { id: 'f-2', tipo: 'webauthn', etiqueta: 'Llave del portátil' },
];
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
    {
      id: 's-2',
      creada_en: '2026-10-01T10:00:00+00:00',
      ultima_actividad_en: '2026-10-02T11:00:00+00:00',
      agente: 'Chrome en Android',
      red: null,
      actual: false,
    },
  ],
};

test.describe('cuentas: perfil', () => {
  test.skip(
    !CUENTAS_HABILITADAS,
    'Las cuentas están apagadas en este servidor.',
  );

  test('sesión anónima: lleva a ingresar con el destino de vuelta', async ({
    page,
  }) => {
    await simularApi(page, { 'GET /api/cuenta/sesion': { json: ANONIMA } });
    await page.route('**/cuenta/ingresar**', (ruta) => ruta.abort());
    const navegacion = page.waitForRequest(
      /\/cuenta\/ingresar\?siguiente=\/cuenta$/,
    );
    await page.goto('/cuenta');
    await navegacion;
  });

  test('muestra datos, factores y sesiones sin violaciones de accesibilidad', async ({
    page,
  }) => {
    await simularApi(page, {
      'GET /api/cuenta/sesion': {
        json: sesion({ factores: FACTORES, roles: ['revisor'] }),
      },
      'GET /api/cuenta/sesiones': { json: SESIONES },
    });
    await page.goto('/cuenta');
    await expect(
      page.getByRole('heading', { level: 1, name: 'Mi cuenta' }),
    ).toBeVisible();
    await expect(page.getByText('Ana Pérez')).toBeVisible();
    await expect(page.getByText('ana@salud.gob.sv')).toBeVisible();
    await expect(page.getByText('Revisor')).toBeVisible();
    await expect(
      page.getByText('Llave de acceso: Llave del portátil'),
    ).toBeVisible();
    await expect(
      page.getByRole('table', { name: 'Sesiones abiertas en tu cuenta' }),
    ).toBeVisible();
    await expect(
      page.getByText('Firefox en Linux (esta sesión)'),
    ).toBeVisible();
    await expect(page.getByText('Chrome en Android')).toBeVisible();
    await expect(
      page.getByRole('link', { name: /Administrar personas/ }),
    ).toBeHidden();
    await sinViolacionesAxe(page);
  });

  test('quitar un factor: pide confirmar, reautentica y reintenta', async ({
    page,
  }) => {
    let reautenticada = false;
    let factores = FACTORES;
    const llamadas = await simularApi(page, {
      'GET /api/cuenta/sesion': () => ({ json: sesion({ factores }) }),
      'GET /api/cuenta/sesiones': { json: SESIONES },
      'POST /api/cuenta/factores/f-1/revocar': () => {
        if (!reautenticada) {
          return error(
            403,
            'requiere_reautenticacion',
            'Confirma tu contraseña para continuar.',
          );
        }
        factores = FACTORES.slice(1);
        return { json: { mensaje: 'Factor eliminado.' } };
      },
      'POST /api/cuenta/reautenticar': (peticion) => {
        const { contrasena } = peticion.postDataJSON();
        if (contrasena !== 'la contraseña buena') {
          return error(401, 'credenciales', 'Contraseña incorrecta.');
        }
        reautenticada = true;
        return { json: sesion({ factores, csrf_token: 'csrf-reauth' }) };
      },
    });
    await page.goto('/cuenta');
    await page
      .getByRole('button', {
        name: 'Quitar aplicación de autenticación Aplicación de autenticación',
      })
      .click();

    const confirmar = page.getByRole('dialog', { name: 'Quitar factor' });
    await expect(confirmar).toBeVisible();
    await confirmar.getByRole('button', { name: 'Quitar' }).click();

    const reauth = page.getByRole('dialog', { name: 'Confirma tu contraseña' });
    await expect(reauth).toBeVisible();
    await sinViolacionesAxe(page);

    await reauth.getByLabel('Contraseña').fill('equivocada');
    await reauth.getByRole('button', { name: 'Confirmar' }).click();
    await expect(reauth.getByRole('alert')).toHaveText(
      'Contraseña incorrecta.',
    );
    await expect(reauth).toBeVisible();

    await reauth.getByLabel('Contraseña').fill('la contraseña buena');
    await reauth.getByRole('button', { name: 'Confirmar' }).click();
    await expect(reauth).toBeHidden();
    await expect(page.getByText('Factor eliminado.')).toBeVisible();
    await expect(
      page.getByText(
        'Aplicación de autenticación: Aplicación de autenticación',
      ),
    ).toBeHidden();

    const revocaciones = llamadas.filter(
      (l) => l.clave === 'POST /api/cuenta/factores/f-1/revocar',
    );
    expect(revocaciones).toHaveLength(2);
    // El reintento ya lleva el token CSRF que devolvió la reautenticación.
    expect(revocaciones[1].cabeceras['x-csrf-token']).toBe('csrf-reauth');
  });

  test('cancelar la reautenticación deja el error original', async ({
    page,
  }) => {
    await simularApi(page, {
      'GET /api/cuenta/sesion': { json: sesion({ factores: FACTORES }) },
      'GET /api/cuenta/sesiones': { json: SESIONES },
      'POST /api/cuenta/factores/f-2/revocar': error(
        403,
        'requiere_reautenticacion',
        'Confirma tu contraseña para continuar.',
      ),
    });
    await page.goto('/cuenta');
    await page.getByRole('button', { name: /Quitar llave de acceso/ }).click();
    await page
      .getByRole('dialog', { name: 'Quitar factor' })
      .getByRole('button', { name: 'Quitar' })
      .click();
    await page
      .getByRole('dialog', { name: 'Confirma tu contraseña' })
      .getByRole('button', { name: 'Cancelar' })
      .click();
    await expect(page.getByRole('alert')).toHaveText(
      'Confirma tu contraseña para continuar.',
    );
  });

  test('cambiar contraseña valida requisitos y llama con la contraseña actual', async ({
    page,
  }) => {
    const llamadas = await simularApi(page, {
      'GET /api/cuenta/sesion': { json: sesion() },
      'GET /api/cuenta/sesiones': { json: SESIONES },
      'POST /api/cuenta/clave/cambiar': {
        json: sesion({ csrf_token: 'csrf-nueva' }),
      },
    });
    await page.goto('/cuenta');
    await page.getByLabel('Contraseña actual').fill('la contraseña vieja');
    await page.getByLabel('Contraseña nueva', { exact: true }).fill('corta');
    await page.getByLabel('Repite la contraseña nueva').fill('corta');
    await page.getByRole('button', { name: 'Cambiar contraseña' }).click();
    await expect(page.getByRole('alert')).toHaveText(
      'La contraseña nueva no cumple los requisitos.',
    );

    await page
      .getByLabel('Contraseña nueva', { exact: true })
      .fill('un cuaderno rojo sobre la mesa');
    await page
      .getByLabel('Repite la contraseña nueva')
      .fill('un cuaderno rojo sobre la mesa');
    await page.getByRole('button', { name: 'Cambiar contraseña' }).click();
    await expect(
      page.getByText('Contraseña actualizada. Se cerraron tus otras sesiones.'),
    ).toBeVisible();
    expect(
      llamadas.find((l) => l.clave === 'POST /api/cuenta/clave/cambiar')
        ?.cuerpo,
    ).toEqual({
      actual: 'la contraseña vieja',
      nueva: 'un cuaderno rojo sobre la mesa',
    });
  });

  test('cerrar las otras sesiones y salir', async ({ page }) => {
    const llamadas = await simularApi(page, {
      'GET /api/cuenta/sesion': { json: sesion() },
      'GET /api/cuenta/sesiones': { json: SESIONES },
      'POST /api/cuenta/sesiones/cerrar-otras': { json: { cerradas: 1 } },
      'POST /api/cuenta/salir': { json: { mensaje: 'Sesión cerrada.' } },
    });
    await page.goto('/cuenta');
    await page
      .getByRole('button', { name: 'Cerrar las otras sesiones' })
      .click();
    await expect(page.getByText('Se cerró 1 sesión.')).toBeVisible();

    await page.route('**/cuenta/ingresar', (ruta) => ruta.abort());
    const navegacion = page.waitForRequest(/\/cuenta\/ingresar$/);
    await page.getByRole('button', { name: 'Salir de esta sesión' }).click();
    await navegacion;
    expect(llamadas.some((l) => l.clave === 'POST /api/cuenta/salir')).toBe(
      true,
    );
  });

  test('si la sesión caduca durante una acción, vuelve a ingresar', async ({
    page,
  }) => {
    await simularApi(page, {
      'GET /api/cuenta/sesion': { json: sesion() },
      'GET /api/cuenta/sesiones': { json: SESIONES },
      'POST /api/cuenta/sesiones/cerrar-otras': error(
        401,
        'sin_sesion',
        'Inicia sesión para continuar.',
      ),
    });
    await page.goto('/cuenta');
    await page.route('**/cuenta/ingresar**', (ruta) => ruta.abort());
    const navegacion = page.waitForRequest(
      /\/cuenta\/ingresar\?siguiente=\/cuenta$/,
    );
    await page
      .getByRole('button', { name: 'Cerrar las otras sesiones' })
      .click();
    await navegacion;
  });

  test('error de red al cargar: ofrece reintentar', async ({ page }) => {
    let fallar = true;
    await simularApi(page, {
      'GET /api/cuenta/sesion': () =>
        fallar ? { abortar: true } : { json: sesion() },
      'GET /api/cuenta/sesiones': { json: SESIONES },
    });
    await page.goto('/cuenta');
    await expect(
      page.getByRole('button', { name: 'Reintentar' }),
    ).toBeVisible();
    fallar = false;
    await page.getByRole('button', { name: 'Reintentar' }).click();
    await expect(page.getByText('Ana Pérez')).toBeVisible();
  });
});
