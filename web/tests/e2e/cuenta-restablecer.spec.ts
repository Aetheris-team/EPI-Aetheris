import { expect, test } from '@playwright/test';

import {
  CUENTAS_HABILITADAS,
  error,
  simularApi,
  sinViolacionesAxe,
} from './cuenta-comun';

const MENSAJE_OLVIDE =
  'Si el correo tiene una cuenta, enviamos un enlace para restablecer la contraseña.';

test.describe('cuentas: restablecer contraseña', () => {
  test.skip(
    !CUENTAS_HABILITADAS,
    'Las cuentas están apagadas en este servidor.',
  );

  test('olvidé mi contraseña: la respuesta es la misma exista o no la cuenta', async ({
    page,
  }) => {
    const llamadas = await simularApi(page, {
      'POST /api/cuenta/clave/olvide': {
        status: 202,
        json: { mensaje: MENSAJE_OLVIDE },
      },
    });
    await page.goto('/cuenta/olvide');
    await sinViolacionesAxe(page);

    const textos: string[] = [];
    for (const correo of ['existe@salud.gob.sv', 'no-existe@example.org']) {
      await page.getByLabel('Correo', { exact: true }).fill(correo);
      await page.getByRole('button', { name: 'Enviar enlace' }).click();
      const aviso = page
        .getByRole('status')
        .filter({ hasText: 'Si el correo tiene una cuenta' });
      await expect(aviso).toBeVisible();
      textos.push((await aviso.textContent()) ?? '');
    }
    expect(textos[0]).toBe(textos[1]);
    expect(textos[0]).toBe(MENSAJE_OLVIDE);
    expect(llamadas.map((l) => l.cuerpo)).toEqual([
      { correo: 'existe@salud.gob.sv' },
      { correo: 'no-existe@example.org' },
    ]);
  });

  test('olvidé mi contraseña: límite de intentos', async ({ page }) => {
    await simularApi(page, {
      'POST /api/cuenta/clave/olvide': error(
        429,
        'demasiados_intentos',
        'Demasiados intentos.',
        30,
      ),
    });
    await page.goto('/cuenta/olvide');
    await page.getByLabel('Correo', { exact: true }).fill('ana@salud.gob.sv');
    await page.getByRole('button', { name: 'Enviar enlace' }).click();
    await expect(page.getByRole('alert')).toContainText('Espera 30 segundos');
  });

  test('restablecer: token del fragmento fuera de la dirección y contraseña nueva', async ({
    page,
  }) => {
    const llamadas = await simularApi(page, {
      'POST /api/cuenta/clave/restablecer': {
        json: { mensaje: 'Contraseña actualizada. Ya puedes ingresar.' },
      },
    });
    await page.goto('/cuenta/restablecer#t=token-de-correo');
    expect(page.url()).not.toContain('token-de-correo');
    await expect(page.getByLabel('Contraseña nueva')).toBeVisible();
    await sinViolacionesAxe(page);

    await page.getByLabel('Contraseña nueva').fill('corta');
    await page.getByLabel('Repite la contraseña').fill('corta');
    await page.getByRole('button', { name: 'Guardar contraseña' }).click();
    await expect(page.getByRole('alert')).toHaveText(
      'La contraseña no cumple los requisitos.',
    );

    await page
      .getByLabel('Contraseña nueva')
      .fill('un cuaderno rojo sobre la mesa');
    await page
      .getByLabel('Repite la contraseña')
      .fill('un cuaderno rojo sobre la mesa');
    await page.getByRole('button', { name: 'Guardar contraseña' }).click();
    await expect(
      page.getByText('Contraseña actualizada. Ya puedes ingresar.'),
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: 'Ir a ingresar' }),
    ).toBeVisible();
    expect(llamadas[0].cuerpo).toEqual({
      token: 'token-de-correo',
      contrasena: 'un cuaderno rojo sobre la mesa',
    });
  });

  test('restablecer: enlace caducado muestra el error del servidor y deja reintentar', async ({
    page,
  }) => {
    await simularApi(page, {
      'POST /api/cuenta/clave/restablecer': error(
        410,
        'token_invalido',
        'El enlace no es válido o ya caducó.',
      ),
    });
    await page.goto('/cuenta/restablecer#t=viejo');
    await page
      .getByLabel('Contraseña nueva')
      .fill('un cuaderno rojo sobre la mesa');
    await page
      .getByLabel('Repite la contraseña')
      .fill('un cuaderno rojo sobre la mesa');
    await page.getByRole('button', { name: 'Guardar contraseña' }).click();
    await expect(page.getByRole('alert')).toHaveText(
      'El enlace no es válido o ya caducó.',
    );
    await expect(
      page.getByRole('button', { name: 'Guardar contraseña' }),
    ).toBeEnabled();
  });

  test('restablecer sin token ofrece pedir un enlace nuevo', async ({
    page,
  }) => {
    await simularApi(page, {});
    await page.goto('/cuenta/restablecer');
    await expect(page.getByText('El enlace está incompleto')).toBeVisible();
    await expect(
      page.getByRole('link', { name: 'pide uno nuevo' }),
    ).toHaveAttribute('href', '/cuenta/olvide');
    await sinViolacionesAxe(page);
  });
});
