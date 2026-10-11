import { expect, test } from '@playwright/test';

import {
  ANONIMA,
  CUENTAS_HABILITADAS,
  autenticadorVirtual,
  base64url,
  error,
  sesion,
  simularApi,
  sinViolacionesAxe,
} from './cuenta-comun';

test.describe('cuentas: ingreso', () => {
  test.skip(
    !CUENTAS_HABILITADAS,
    'Las cuentas están apagadas en este servidor.',
  );

  test('sesión anónima: muestra el formulario, sin violaciones de accesibilidad', async ({
    page,
  }) => {
    await simularApi(page, { 'GET /api/cuenta/sesion': { json: ANONIMA } });
    await page.goto('/cuenta/ingresar');
    await expect(
      page.getByRole('heading', { level: 1, name: 'Ingresar' }),
    ).toBeVisible();
    await expect(page.getByLabel('Correo', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Contraseña', { exact: true })).toBeVisible();
    await expect(
      page.getByRole('link', { name: '¿Olvidaste tu contraseña?' }),
    ).toBeVisible();
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute(
      'content',
      /noindex/,
    );
    await sinViolacionesAxe(page);
  });

  test('dos pasos con la aplicación: contraseña, código y entrada a la cuenta', async ({
    page,
  }) => {
    let actual: unknown = ANONIMA;
    const llamadas = await simularApi(page, {
      'GET /api/cuenta/sesion': () => ({ json: actual }),
      'POST /api/cuenta/ingresar': () => {
        actual = sesion({
          nivel: 'segundo_factor',
          csrf_token: 'csrf-paso-2',
          metodos: ['clave'],
        });
        return { json: actual };
      },
      'POST /api/cuenta/ingresar/totp': () => {
        actual = sesion();
        return { json: actual };
      },
      'GET /api/cuenta/sesiones': { json: { sesiones: [] } },
    });

    await page.goto('/cuenta/ingresar');
    await page.getByLabel('Correo', { exact: true }).fill('ana@salud.gob.sv');
    await page
      .getByLabel('Contraseña', { exact: true })
      .fill('una contraseña larga y buena');
    await page.getByRole('button', { name: 'Continuar' }).click();

    await expect(
      page.getByRole('heading', { name: 'Verificación en dos pasos' }),
    ).toBeVisible();
    await expect(page.getByLabel('Código de tu aplicación')).toBeVisible();
    await sinViolacionesAxe(page);

    await page.getByLabel('Código de tu aplicación').fill('123456');
    await page.getByRole('button', { name: 'Verificar', exact: true }).click();
    await expect(page).toHaveURL(/\/cuenta$/);
    await expect(
      page.getByRole('heading', { level: 1, name: 'Mi cuenta' }),
    ).toBeVisible();

    const ingreso = llamadas.find(
      (l) => l.clave === 'POST /api/cuenta/ingresar',
    );
    expect(ingreso?.cuerpo).toEqual({
      correo: 'ana@salud.gob.sv',
      contrasena: 'una contraseña larga y buena',
    });
    // El token CSRF de la sesión intermedia viaja en el segundo paso.
    const totp = llamadas.find(
      (l) => l.clave === 'POST /api/cuenta/ingresar/totp',
    );
    expect(totp?.cabeceras['x-csrf-token']).toBe('csrf-paso-2');
    expect(totp?.cuerpo).toEqual({ codigo: '123456' });

    // El token CSRF no se guarda en el navegador.
    const guardado = await page.evaluate(
      () =>
        JSON.stringify({ ...localStorage }) +
        JSON.stringify({ ...sessionStorage }) +
        document.cookie,
    );
    expect(guardado).not.toContain('csrf-');
  });

  test('segundo paso con código de recuperación', async ({ page }) => {
    let actual: unknown = ANONIMA;
    const llamadas = await simularApi(page, {
      'GET /api/cuenta/sesion': () => ({ json: actual }),
      'POST /api/cuenta/ingresar': () => {
        actual = sesion({ nivel: 'segundo_factor' });
        return { json: actual };
      },
      'POST /api/cuenta/ingresar/recuperacion': () => {
        actual = sesion();
        return { json: actual };
      },
      'GET /api/cuenta/sesiones': { json: { sesiones: [] } },
    });
    await page.goto('/cuenta/ingresar');
    await page.getByLabel('Correo', { exact: true }).fill('ana@salud.gob.sv');
    await page
      .getByLabel('Contraseña', { exact: true })
      .fill('una contraseña larga y buena');
    await page.getByRole('button', { name: 'Continuar' }).click();
    await page.getByText('Usar un código de recuperación').click();
    await page.getByLabel('Código de recuperación').fill('ABCD-EFGH-JKLM-NPQR');
    await page.getByRole('button', { name: 'Verificar código' }).click();
    await expect(page).toHaveURL(/\/cuenta$/);
    expect(
      llamadas.some(
        (l) => l.clave === 'POST /api/cuenta/ingresar/recuperacion',
      ),
    ).toBe(true);
  });

  test('credenciales incorrectas: el error recibe el foco', async ({
    page,
  }) => {
    await simularApi(page, {
      'GET /api/cuenta/sesion': { json: ANONIMA },
      'POST /api/cuenta/ingresar': error(
        401,
        'credenciales',
        'Correo o contraseña incorrectos.',
      ),
    });
    await page.goto('/cuenta/ingresar');
    await page.getByLabel('Correo', { exact: true }).fill('ana@salud.gob.sv');
    await page.getByLabel('Contraseña', { exact: true }).fill('mala');
    await page.getByRole('button', { name: 'Continuar' }).click();
    const alerta = page.getByRole('alert');
    await expect(alerta).toHaveText('Correo o contraseña incorrectos.');
    await expect(alerta).toBeFocused();
    await sinViolacionesAxe(page);
  });

  test('límite de intentos (429): indica cuánto esperar', async ({ page }) => {
    await simularApi(page, {
      'GET /api/cuenta/sesion': { json: ANONIMA },
      'POST /api/cuenta/ingresar': error(
        429,
        'demasiados_intentos',
        'Demasiados intentos. Espera antes de volver a probar.',
        42,
        { 'Retry-After': '42' },
      ),
    });
    await page.goto('/cuenta/ingresar');
    await page.getByLabel('Correo', { exact: true }).fill('ana@salud.gob.sv');
    await page.getByLabel('Contraseña', { exact: true }).fill('cualquiera');
    await page.getByRole('button', { name: 'Continuar' }).click();
    await expect(page.getByRole('alert')).toContainText('Espera 42 segundos');
  });

  test('429 del limitador sin cuerpo de la aplicación usa Retry-After', async ({
    page,
  }) => {
    await simularApi(page, {
      'GET /api/cuenta/sesion': { json: ANONIMA },
      'POST /api/cuenta/ingresar': {
        status: 429,
        headers: { 'Retry-After': '120' },
        json: { error: 'Rate limit exceeded: 10 per 1 minute' },
      },
    });
    await page.goto('/cuenta/ingresar');
    await page.getByLabel('Correo', { exact: true }).fill('ana@salud.gob.sv');
    await page.getByLabel('Contraseña', { exact: true }).fill('cualquiera');
    await page.getByRole('button', { name: 'Continuar' }).click();
    await expect(page.getByRole('alert')).toContainText('Espera 2 minutos');
  });

  test('cuenta sin alta terminada va a /cuenta/alta', async ({ page }) => {
    await simularApi(page, {
      'GET /api/cuenta/sesion': { json: ANONIMA },
      'POST /api/cuenta/ingresar': {
        json: sesion({ nivel: 'alta_pendiente', factores: [] }),
      },
    });
    await page.route('**/cuenta/alta', (ruta) => ruta.abort());
    await page.goto('/cuenta/ingresar');
    await page.getByLabel('Correo', { exact: true }).fill('nueva@salud.gob.sv');
    await page
      .getByLabel('Contraseña', { exact: true })
      .fill('una contraseña larga y buena');
    const navegacion = page.waitForRequest(/\/cuenta\/alta$/);
    await page.getByRole('button', { name: 'Continuar' }).click();
    await navegacion;
  });

  test('segundo paso con llave de acceso (autenticador virtual)', async ({
    page,
  }) => {
    await simularApi(page, { 'GET /api/cuenta/sesion': { json: ANONIMA } });
    await page.goto('/cuenta/ingresar');
    await autenticadorVirtual(page);
    // Se crea una credencial real en el autenticador virtual para poder firmar.
    const idCredencial = await page.evaluate(async () => {
      const c = (await navigator.credentials.create({
        publicKey: {
          rp: { name: 'prueba', id: 'localhost' },
          user: { id: new Uint8Array([1]), name: 'a', displayName: 'a' },
          challenge: new Uint8Array([1, 2, 3]),
          pubKeyCredParams: [{ type: 'public-key', alg: -7 }],
          authenticatorSelection: {
            userVerification: 'required',
            residentKey: 'preferred',
          },
        },
      })) as PublicKeyCredential;
      return btoa(String.fromCharCode(...new Uint8Array(c.rawId)))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=+$/, '');
    });

    let actual: unknown = ANONIMA;
    const llamadas = await simularApi(page, {
      'GET /api/cuenta/sesion': () => ({ json: actual }),
      'POST /api/cuenta/ingresar': () => {
        actual = sesion({
          nivel: 'segundo_factor',
          factores: [
            { id: 'f-2', tipo: 'webauthn', etiqueta: 'Llave del portátil' },
          ],
        });
        return { json: actual };
      },
      'POST /api/cuenta/ingresar/llave/opciones': {
        json: {
          challenge: base64url('desafio-de-ingreso-0123456789'),
          timeout: 60000,
          rpId: 'localhost',
          allowCredentials: [{ id: idCredencial, type: 'public-key' }],
          userVerification: 'required',
        },
      },
      'POST /api/cuenta/ingresar/llave': () => {
        actual = sesion({ metodos: ['clave', 'webauthn'] });
        return { json: actual };
      },
      'GET /api/cuenta/sesiones': { json: { sesiones: [] } },
    });

    await page.getByLabel('Correo', { exact: true }).fill('ana@salud.gob.sv');
    await page
      .getByLabel('Contraseña', { exact: true })
      .fill('una contraseña larga y buena');
    await page.getByRole('button', { name: 'Continuar' }).click();
    await expect(page.getByLabel('Código de tu aplicación')).toBeHidden();
    await page.getByRole('button', { name: 'Usar mi llave de acceso' }).click();
    await expect(page).toHaveURL(/\/cuenta$/);

    const envio = llamadas.find(
      (l) => l.clave === 'POST /api/cuenta/ingresar/llave',
    );
    const credencial = (envio?.cuerpo as { credencial: Record<string, any> })
      .credencial;
    expect(credencial.id).toBe(idCredencial);
    expect(credencial.rawId).toBe(idCredencial);
    expect(credencial.type).toBe('public-key');
    for (const campo of ['clientDataJSON', 'authenticatorData', 'signature']) {
      expect(credencial.response[campo]).toMatch(/^[A-Za-z0-9_-]+$/);
    }
  });
});
