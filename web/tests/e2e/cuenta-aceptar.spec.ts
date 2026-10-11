import { expect, test } from '@playwright/test';

import {
  CUENTAS_HABILITADAS,
  autenticadorVirtual,
  error,
  opcionesRegistro,
  sesion,
  simularApi,
  sinViolacionesAxe,
} from './cuenta-comun';

const QR_VALIDO =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 29 29" class="segno"><path stroke="#000" d="M0 0h7v1H0z"/></svg>';
const QR_HOSTIL =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 29 29"><script>window.__xss = 1</script><path d="M0 0h7v1H0z"/></svg>';
const CODIGOS = Array.from({ length: 10 }, (_, i) => `ABCD-EFGH-JK${i}M-NPQR`);
const INVITACION = {
  correo: 'nueva@salud.gob.sv',
  roles: ['publicador'],
  institucion: 'Hospital Rosales',
  terminos_version: '2026-10',
};

test.describe('cuentas: aceptar invitación y alta', () => {
  test.skip(
    !CUENTAS_HABILITADAS,
    'Las cuentas están apagadas en este servidor.',
  );

  test('el token del fragmento se lee, se borra de la dirección y se muestra la invitación', async ({
    page,
  }) => {
    const llamadas = await simularApi(page, {
      'POST /api/cuenta/invitacion/ver': { json: INVITACION },
    });
    await page.goto('/cuenta/aceptar#t=token-secreto-123');
    await expect(page.getByText('nueva@salud.gob.sv')).toBeVisible();
    await expect(page.getByText('Publicador')).toBeVisible();
    await expect(page.getByText('Hospital Rosales')).toBeVisible();
    await expect(page.getByText(/versión 2026-10/)).toBeVisible();

    expect(page.url()).not.toContain('#');
    expect(page.url()).not.toContain('token-secreto');
    expect(await page.evaluate(() => history.length)).toBeGreaterThan(0);
    const ver = llamadas.find(
      (l) => l.clave === 'POST /api/cuenta/invitacion/ver',
    );
    expect(ver?.cuerpo).toEqual({ token: 'token-secreto-123' });
    await sinViolacionesAxe(page);
  });

  test('invitación caducada: avisa y no muestra el formulario', async ({
    page,
  }) => {
    await simularApi(page, {
      'POST /api/cuenta/invitacion/ver': error(
        410,
        'invitacion_invalida',
        'La invitación no es válida o ya caducó.',
      ),
    });
    await page.goto('/cuenta/aceptar#t=vieja');
    await expect(
      page.getByRole('heading', { name: 'La invitación no es válida' }),
    ).toBeVisible();
    await expect(page.getByText('ya caducó')).toBeVisible();
    await expect(page.getByLabel('Nombre', { exact: true })).toBeHidden();
    await sinViolacionesAxe(page);
  });

  test('sin token en el enlace', async ({ page }) => {
    await simularApi(page, {});
    await page.goto('/cuenta/aceptar');
    await expect(page.getByText('El enlace está incompleto')).toBeVisible();
  });

  test('aceptar la invitación pide requisitos y términos, y envía la versión del backend', async ({
    page,
  }) => {
    const llamadas = await simularApi(page, {
      'POST /api/cuenta/invitacion/ver': { json: INVITACION },
      'POST /api/cuenta/invitacion/aceptar': {
        json: sesion({
          nivel: 'alta_pendiente',
          factores: [],
          metodos: ['clave'],
          csrf_token: 'csrf-alta',
        }),
      },
    });
    await page.route('**/cuenta/alta', (ruta) => ruta.abort());
    await page.goto('/cuenta/aceptar#t=tok');

    await page.getByLabel('Nombre', { exact: true }).fill('Nora Quintanilla');
    await page.getByLabel('Cargo (opcional)').fill('Epidemióloga');
    await page.getByLabel('Contraseña', { exact: true }).fill('corta');

    const requisitos = page.locator('[data-requisitos] li');
    await expect(requisitos.first()).toContainText('Entre 12 y 128 caracteres');
    await expect(requisitos.first()).toContainText('(pendiente)');

    await page
      .getByRole('button', { name: 'Crear cuenta y continuar' })
      .click();
    await expect(page.getByRole('alert')).toHaveText(
      'La contraseña no cumple los requisitos.',
    );

    await page
      .getByLabel('Contraseña', { exact: true })
      .fill('nora quintanilla 2026');
    await expect(
      page.locator('[data-requisitos] li[data-cumple="false"]'),
    ).toHaveCount(1);
    await expect(page.locator('[data-requisitos] li').nth(2)).toContainText(
      'Sin tu nombre ni tu correo',
    );

    await page
      .getByLabel('Contraseña', { exact: true })
      .fill('un cuaderno rojo sobre la mesa');
    await expect(requisitos.first()).toContainText('(cumple)');
    await page
      .getByLabel('Repite la contraseña')
      .fill('un cuaderno rojo sobre la mesa distinto');
    await page
      .getByRole('button', { name: 'Crear cuenta y continuar' })
      .click();
    await expect(page.getByRole('alert')).toHaveText(
      'Las contraseñas no coinciden.',
    );

    await page
      .getByLabel('Repite la contraseña')
      .fill('un cuaderno rojo sobre la mesa');
    await page
      .getByRole('button', { name: 'Crear cuenta y continuar' })
      .click();
    await expect(page.getByRole('alert')).toHaveText(
      'Para continuar hay que aceptar los términos de uso y la política de privacidad.',
    );

    await page.getByLabel(/Acepto los términos de uso/).check();
    await page
      .getByRole('button', { name: 'Crear cuenta y continuar' })
      .click();
    await expect(page.getByRole('alert')).toHaveText(
      'Para continuar hay que aceptar la firma pública de lo que publiques.',
    );
    await page.getByLabel(/Acepto que lo que publique lleve mi nombre/).check();
    await page
      .getByRole('button', { name: 'Crear cuenta y continuar' })
      .click();
    await expect(page.getByRole('alert')).toHaveText(
      'Para continuar hay que aceptar el tratamiento de tus datos en Estados Unidos.',
    );
    await page.getByLabel(/Acepto que mis datos de cuenta se traten/).check();
    const navegacion = page.waitForRequest(/\/cuenta\/alta$/);
    await page
      .getByRole('button', { name: 'Crear cuenta y continuar' })
      .click();
    await navegacion;

    const aceptar = llamadas.find(
      (l) => l.clave === 'POST /api/cuenta/invitacion/aceptar',
    );
    expect(aceptar?.cuerpo).toEqual({
      token: 'tok',
      nombre_visible: 'Nora Quintanilla',
      cargo: 'Epidemióloga',
      contrasena: 'un cuaderno rojo sobre la mesa',
      terminos_version: '2026-10',
    });
  });

  test('mostrar contraseña cambia el tipo de los dos campos', async ({
    page,
  }) => {
    await simularApi(page, {
      'POST /api/cuenta/invitacion/ver': { json: INVITACION },
    });
    await page.goto('/cuenta/aceptar#t=tok');
    const campo = page.getByLabel('Contraseña', { exact: true });
    await expect(campo).toHaveAttribute('type', 'password');
    await page.getByLabel('Mostrar contraseña').check();
    await expect(campo).toHaveAttribute('type', 'text');
    await expect(page.getByLabel('Repite la contraseña')).toHaveAttribute(
      'type',
      'text',
    );
  });

  test('alta con aplicación: QR, clave en texto, códigos de recuperación y cierre', async ({
    page,
  }) => {
    let nivel = 'alta_pendiente';
    let factores: unknown[] = [];
    const llamadas = await simularApi(page, {
      'GET /api/cuenta/sesion': () => ({
        json: sesion({
          nivel,
          factores,
          csrf_token: 'csrf-alta',
          metodos: ['clave'],
        }),
      }),
      'POST /api/cuenta/factores/totp/iniciar': {
        json: {
          factor_id: 'f-nuevo',
          secreto: 'JBSWY3DPEHPK3PXP',
          uri: 'otpauth://totp/EPI:nueva@salud.gob.sv?secret=JBSWY3DPEHPK3PXP',
          qr_svg: QR_VALIDO,
        },
      },
      'POST /api/cuenta/factores/totp/confirmar': () => {
        factores = [
          {
            id: 'f-nuevo',
            tipo: 'totp',
            etiqueta: 'Aplicación de autenticación',
          },
        ];
        return { json: { activada: true, codigos_recuperacion: CODIGOS } };
      },
      'POST /api/cuenta/alta/completar': () => {
        nivel = 'completo';
        return { json: sesion({ factores, csrf_token: 'csrf-completo' }) };
      },
      'GET /api/cuenta/sesiones': { json: { sesiones: [] } },
    });
    await page.goto('/cuenta/alta');

    await expect(
      page.getByRole('heading', { name: 'Protege tu cuenta' }),
    ).toBeVisible();
    await expect(
      page.getByText('Todavía no has registrado ninguno'),
    ).toBeVisible();
    await page.getByRole('button', { name: 'Configurar aplicación' }).click();

    const qr = page.locator('[data-qr] img');
    await expect(qr).toBeVisible();
    await expect(qr).toHaveAttribute('alt', /Código QR/);
    await expect(page.locator('[data-secreto]')).toHaveText('JBSWY3DPEHPK3PXP');
    await sinViolacionesAxe(page);

    await page.getByLabel('Código de seis dígitos').fill('654321');
    await page.getByRole('button', { name: 'Confirmar aplicación' }).click();

    await expect(
      page.getByRole('heading', { name: 'Códigos de recuperación' }),
    ).toBeFocused();
    await expect(page.locator('[data-codigos] li')).toHaveCount(10);
    await expect(page.locator('[data-codigos] li').first()).toHaveText(
      CODIGOS[0],
    );
    const terminar = page.getByRole('button', {
      name: 'Terminar y entrar a mi cuenta',
    });
    await expect(terminar).toBeDisabled();

    const descarga = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Descargar como texto' }).click();
    expect((await descarga).suggestedFilename()).toBe(
      'codigos-recuperacion-epi-aetheris.txt',
    );

    await page.getByLabel('Guardé los códigos').check();
    await expect(terminar).toBeEnabled();
    await sinViolacionesAxe(page);
    await terminar.click();
    await expect(page).toHaveURL(/\/cuenta$/);

    const confirmar = llamadas.find(
      (l) => l.clave === 'POST /api/cuenta/factores/totp/confirmar',
    );
    expect(confirmar?.cuerpo).toEqual({
      factor_id: 'f-nuevo',
      codigo: '654321',
    });
    expect(confirmar?.cabeceras['x-csrf-token']).toBe('csrf-alta');

    // Los códigos no se guardan en el navegador.
    const guardado = await page.evaluate(
      () =>
        JSON.stringify({ ...localStorage }) +
        JSON.stringify({ ...sessionStorage }),
    );
    expect(guardado).not.toContain('ABCD-');
  });

  test('un QR con script se rechaza y se deja la clave en texto', async ({
    page,
  }) => {
    await simularApi(page, {
      'GET /api/cuenta/sesion': {
        json: sesion({ nivel: 'alta_pendiente', factores: [] }),
      },
      'POST /api/cuenta/factores/totp/iniciar': {
        json: {
          factor_id: 'f-1',
          secreto: 'ABCDEFGH',
          uri: 'otpauth://totp/x',
          qr_svg: QR_HOSTIL,
        },
      },
    });
    await page.goto('/cuenta/alta');
    await page.getByRole('button', { name: 'Configurar aplicación' }).click();
    await expect(page.locator('[data-qr]')).toHaveText(
      'No se pudo mostrar el código QR.',
    );
    await expect(page.locator('[data-qr] img')).toHaveCount(0);
    await expect(page.locator('[data-secreto]')).toHaveText('ABCDEFGH');
    expect(
      await page.evaluate(
        () => (window as unknown as { __xss?: number }).__xss,
      ),
    ).toBeUndefined();
  });

  test('código de la aplicación incorrecto: error con foco y sin avanzar', async ({
    page,
  }) => {
    await simularApi(page, {
      'GET /api/cuenta/sesion': {
        json: sesion({ nivel: 'alta_pendiente', factores: [] }),
      },
      'POST /api/cuenta/factores/totp/iniciar': {
        json: {
          factor_id: 'f-1',
          secreto: 'ABCDEFGH',
          uri: 'otpauth://totp/x',
          qr_svg: QR_VALIDO,
        },
      },
      'POST /api/cuenta/factores/totp/confirmar': error(
        401,
        'codigo_incorrecto',
        'Código incorrecto.',
      ),
    });
    await page.goto('/cuenta/alta');
    await page.getByRole('button', { name: 'Configurar aplicación' }).click();
    await page.getByLabel('Código de seis dígitos').fill('000000');
    await page.getByRole('button', { name: 'Confirmar aplicación' }).click();
    const alerta = page.getByRole('alert');
    await expect(alerta).toHaveText('Código incorrecto.');
    await expect(alerta).toBeFocused();
    await expect(page.locator('[data-bloque-codigos]')).toBeHidden();
  });

  test('administrador: exige llave de acceso y la registra con un autenticador virtual', async ({
    page,
  }) => {
    let factores: unknown[] = [];
    const llamadas = await simularApi(page, {
      'GET /api/cuenta/sesion': () => ({
        json: sesion({
          nivel: 'alta_pendiente',
          roles: ['administrador'],
          factores,
          csrf_token: 'csrf-alta',
        }),
      }),
      'POST /api/cuenta/factores/totp/iniciar': {
        json: {
          factor_id: 'f-t',
          secreto: 'ABCDEFGH',
          uri: 'otpauth://totp/x',
          qr_svg: QR_VALIDO,
        },
      },
      'POST /api/cuenta/factores/totp/confirmar': () => {
        factores = [
          { id: 'f-t', tipo: 'totp', etiqueta: 'Aplicación de autenticación' },
        ];
        return { json: { activada: false, codigos_recuperacion: null } };
      },
      'POST /api/cuenta/factores/llave/opciones': { json: opcionesRegistro() },
      'POST /api/cuenta/factores/llave': () => {
        factores = [
          ...factores,
          { id: 'f-w', tipo: 'webauthn', etiqueta: 'Llave del portátil' },
        ];
        return { json: { activada: true, codigos_recuperacion: CODIGOS } };
      },
    });
    await page.goto('/cuenta/alta');
    await autenticadorVirtual(page);
    await expect(
      page.getByText('Tu rol de administrador exige una llave de acceso'),
    ).toBeVisible();

    // La aplicación sola no activa la cuenta de un administrador.
    await page.getByRole('button', { name: 'Configurar aplicación' }).click();
    await page.getByLabel('Código de seis dígitos').fill('123456');
    await page.getByRole('button', { name: 'Confirmar aplicación' }).click();
    await expect(
      page.getByRole('status').filter({ hasText: 'Falta registrar una llave' }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Terminar y entrar a mi cuenta' }),
    ).toBeHidden();

    await page
      .getByLabel('Nombre de la llave (opcional)')
      .fill('Llave del portátil');
    await page
      .getByRole('button', { name: 'Registrar llave de acceso' })
      .click();
    await expect(page.locator('[data-codigos] li')).toHaveCount(10);

    const registro = llamadas.find(
      (l) => l.clave === 'POST /api/cuenta/factores/llave',
    );
    const cuerpo = registro?.cuerpo as {
      credencial: Record<string, any>;
      etiqueta: string;
    };
    expect(cuerpo.etiqueta).toBe('Llave del portátil');
    expect(cuerpo.credencial.type).toBe('public-key');
    expect(cuerpo.credencial.rawId).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(cuerpo.credencial.response.attestationObject).toMatch(
      /^[A-Za-z0-9_-]+$/,
    );
    expect(cuerpo.credencial.response.clientDataJSON).toMatch(
      /^[A-Za-z0-9_-]+$/,
    );
    await sinViolacionesAxe(page);
  });

  test('sin sesión de alta, /cuenta/alta lleva a ingresar', async ({
    page,
  }) => {
    await simularApi(page, {
      'GET /api/cuenta/sesion': { json: { autenticada: false } },
    });
    await page.route('**/cuenta/ingresar', (ruta) => ruta.abort());
    const navegacion = page.waitForRequest(/\/cuenta\/ingresar$/);
    await page.goto('/cuenta/alta');
    await navegacion;
  });
});
