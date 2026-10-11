import { expect, test } from '@playwright/test';

import {
  ANONIMA,
  CUENTAS_HABILITADAS,
  error,
  sesion,
  simularApi,
  sinViolacionesAxe,
} from './cuenta-comun';

const ADMIN = sesion({
  roles: ['administrador'],
  metodos: ['clave', 'webauthn'],
  usuario: {
    id: 'u-admin',
    correo: 'admin@salud.gob.sv',
    nombre: 'Rosa Admin',
  },
});

const USUARIOS = [
  {
    id: 'u-admin',
    correo: 'admin@salud.gob.sv',
    nombre: 'Rosa Admin',
    estado: 'activo',
    institucion: 'MINSAL',
    ultimo_ingreso_en: '2026-10-04T09:00:00+00:00',
    roles: ['administrador'],
  },
  {
    id: 'u-2',
    correo: 'luis@hospital.org.sv',
    nombre: '<img src=x onerror="window.__xss=1">',
    estado: 'activo',
    institucion: 'Hospital Rosales',
    ultimo_ingreso_en: null,
    roles: ['publicador'],
  },
];

const INSTITUCIONES = [
  {
    id: 1,
    nombre: 'MINSAL',
    tipo: 'minsal',
    dominios_correo: ['salud.gob.sv'],
    verificada: true,
    activa: true,
  },
  {
    id: 2,
    nombre: 'Hospital Rosales',
    tipo: 'hospital',
    dominios_correo: ['rosales.gob.sv'],
    verificada: false,
    activa: true,
  },
];

function rutasBase() {
  return {
    'GET /api/cuenta/sesion': { json: ADMIN },
    'GET /api/admin/usuarios': { json: { usuarios: USUARIOS } },
    'GET /api/admin/instituciones': { json: { instituciones: INSTITUCIONES } },
  };
}

test.describe('cuentas: administración', () => {
  test.skip(
    !CUENTAS_HABILITADAS,
    'Las cuentas están apagadas en este servidor.',
  );

  test('lista personas e instituciones, sin ejecutar HTML de la API ni violaciones axe', async ({
    page,
  }) => {
    await simularApi(page, rutasBase());
    await page.goto('/admin/usuarios');
    await expect(
      page.getByRole('heading', { level: 1, name: 'Personas e instituciones' }),
    ).toBeVisible();
    await expect(
      page.getByRole('table', { name: 'Personas con cuenta' }),
    ).toBeVisible();
    await expect(
      page.getByText('luis@hospital.org.sv · Hospital Rosales'),
    ).toBeVisible();
    // El nombre hostil se muestra como texto.
    await expect(page.getByText('<img src=x onerror=')).toBeVisible();
    expect(
      await page.evaluate(
        () => (window as unknown as { __xss?: number }).__xss,
      ),
    ).toBeUndefined();
    // Sobre la propia cuenta no hay acciones.
    await expect(page.getByText('Tu cuenta')).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Suspender a Rosa Admin' }),
    ).toHaveCount(0);
    await expect(
      page.getByRole('table', { name: 'Instituciones registradas' }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Verificar Hospital Rosales' }),
    ).toBeVisible();
    await sinViolacionesAxe(page);
  });

  test('quien no es administrador ve un aviso de falta de permiso', async ({
    page,
  }) => {
    await simularApi(page, { 'GET /api/cuenta/sesion': { json: sesion() } });
    await page.goto('/admin/usuarios');
    await expect(
      page.getByRole('heading', { name: 'Sin permiso' }),
    ).toBeVisible();
    await expect(page.getByRole('table')).toHaveCount(0);
  });

  test('sesión anónima: lleva a ingresar con el destino de vuelta', async ({
    page,
  }) => {
    await simularApi(page, { 'GET /api/cuenta/sesion': { json: ANONIMA } });
    await page.route('**/cuenta/ingresar**', (ruta) => ruta.abort());
    const navegacion = page.waitForRequest(
      /\/cuenta\/ingresar\?siguiente=\/admin\/usuarios$/,
    );
    await page.goto('/admin/usuarios');
    await navegacion;
  });

  test('invitar: la justificación de dominio aparece cuando el correo no es de la institución', async ({
    page,
  }) => {
    const llamadas = await simularApi(page, {
      ...rutasBase(),
      'POST /api/admin/invitaciones': { status: 201, json: { id: 'inv-1' } },
    });
    await page.goto('/admin/usuarios');
    const form = page.locator('[data-form-invitar]');
    await form.getByLabel('Correo', { exact: true }).fill('mario@gmail.com');
    await form.getByLabel('Revisor').check();
    await form
      .locator('select[name="institucion"]')
      .selectOption({ label: 'MINSAL' });
    await expect(
      form.getByLabel('Justificación del dominio de correo'),
    ).toBeVisible();

    await form
      .getByLabel('Cómo verificaste a la persona')
      .fill('Llamada al jefe de unidad.');
    await form.getByRole('button', { name: 'Enviar invitación' }).click();
    await expect(page.getByRole('alert')).toHaveText(
      'Escribe la justificación del dominio de correo.',
    );

    await form
      .getByLabel('Justificación del dominio de correo')
      .fill('Es consultor externo del programa.');
    await form.getByRole('button', { name: 'Enviar invitación' }).click();
    await expect(form.getByRole('status')).toHaveText('Invitación enviada.');

    expect(
      llamadas.find((l) => l.clave === 'POST /api/admin/invitaciones')?.cuerpo,
    ).toEqual({
      correo: 'mario@gmail.com',
      roles: ['revisor'],
      institucion_id: 1,
      nota_verificacion: 'Llamada al jefe de unidad.',
      justificacion_dominio: 'Es consultor externo del programa.',
    });
  });

  test('invitar: si el servidor pide la justificación, el campo se muestra', async ({
    page,
  }) => {
    await simularApi(page, {
      ...rutasBase(),
      'POST /api/admin/invitaciones': error(
        400,
        'dominio_fuera_de_institucion',
        'El correo no pertenece a los dominios de la institución. Escribe una justificación.',
      ),
    });
    await page.goto('/admin/usuarios');
    const form = page.locator('[data-form-invitar]');
    // Sin institución elegida el cliente no puede saberlo; el servidor sí.
    await form.getByLabel('Correo', { exact: true }).fill('mario@gmail.com');
    await form.getByLabel('Publicador').check();
    await form
      .getByLabel('Cómo verificaste a la persona')
      .fill('Llamada al jefe de unidad.');
    await form.getByRole('button', { name: 'Enviar invitación' }).click();
    await expect(form.getByRole('alert')).toContainText(
      'Escribe una justificación',
    );
    await expect(
      form.getByLabel('Justificación del dominio de correo'),
    ).toBeVisible();
  });

  test('suspender con motivo: reautentica y reintenta', async ({ page }) => {
    let reautenticada = false;
    const llamadas = await simularApi(page, {
      ...rutasBase(),
      'POST /api/admin/usuarios/u-2/estado': () =>
        reautenticada
          ? { json: { mensaje: 'Estado actualizado.' } }
          : error(
              403,
              'requiere_reautenticacion',
              'Confirma tu contraseña para continuar.',
            ),
      'POST /api/cuenta/reautenticar': () => {
        reautenticada = true;
        return { json: ADMIN };
      },
    });
    await page.goto('/admin/usuarios');
    await page.getByRole('button', { name: /^Suspender a / }).click();

    const confirmar = page.getByRole('dialog', { name: 'Suspender cuenta' });
    await confirmar.getByRole('button', { name: 'Suspender' }).click();
    await expect(confirmar.getByRole('alert')).toContainText('Motivo');
    await confirmar.getByLabel('Motivo').fill('Cambió de institución.');
    await confirmar.getByRole('button', { name: 'Suspender' }).click();

    const reauth = page.getByRole('dialog', { name: 'Confirma tu contraseña' });
    await reauth.getByLabel('Contraseña').fill('la contraseña buena');
    await reauth.getByRole('button', { name: 'Confirmar' }).click();
    await expect(page.getByText('Cuenta suspendida.')).toBeVisible();

    const envios = llamadas.filter(
      (l) => l.clave === 'POST /api/admin/usuarios/u-2/estado',
    );
    expect(envios).toHaveLength(2);
    expect(envios[1].cuerpo).toEqual({
      estado: 'suspendido',
      motivo: 'Cambió de institución.',
    });
  });

  test('cambiar roles sin llave de acceso explica qué hacer', async ({
    page,
  }) => {
    const llamadas = await simularApi(page, {
      ...rutasBase(),
      'PATCH /api/admin/usuarios/u-2/roles': error(
        403,
        'requiere_llave',
        'Esta acción exige haber ingresado con una llave de acceso.',
      ),
    });
    await page.goto('/admin/usuarios');
    await page.getByRole('button', { name: /^Cambiar roles de / }).click();
    const dialogo = page.getByRole('dialog', { name: 'Cambiar roles' });
    await expect(dialogo.getByLabel('Publicador')).toBeChecked();
    await dialogo.getByLabel('Revisor').check();
    await sinViolacionesAxe(page);
    await dialogo.getByRole('button', { name: 'Guardar roles' }).click();
    await expect(page.getByRole('alert')).toContainText('ingresa con tu llave');
    expect(
      llamadas.find((l) => l.clave === 'PATCH /api/admin/usuarios/u-2/roles')
        ?.cuerpo,
    ).toEqual({
      roles: ['publicador', 'revisor'],
    });
  });

  test('restablecer factores exige motivo y lo envía', async ({ page }) => {
    const llamadas = await simularApi(page, {
      ...rutasBase(),
      'POST /api/admin/usuarios/u-2/restablecer-factores': {
        json: { mensaje: 'Factores restablecidos.' },
      },
    });
    await page.goto('/admin/usuarios');
    await page
      .getByRole('button', { name: /^Restablecer los factores de / })
      .click();
    const dialogo = page.getByRole('dialog', { name: 'Restablecer factores' });
    await dialogo.getByLabel('Motivo').fill('Perdió el teléfono y las llaves.');
    await dialogo.getByRole('button', { name: 'Restablecer' }).click();
    await expect(page.getByText('Factores restablecidos.')).toBeVisible();
    expect(
      llamadas.find(
        (l) => l.clave === 'POST /api/admin/usuarios/u-2/restablecer-factores',
      )?.cuerpo,
    ).toEqual({ motivo: 'Perdió el teléfono y las llaves.' });
  });

  test('instituciones: agregar y verificar', async ({ page }) => {
    const llamadas = await simularApi(page, {
      ...rutasBase(),
      'POST /api/admin/instituciones': { status: 201, json: { id: 3 } },
      'POST /api/admin/instituciones/2/verificar': {
        json: { mensaje: 'Institución verificada.' },
      },
    });
    await page.goto('/admin/usuarios');

    const form = page.locator('[data-form-institucion]');
    await form
      .getByLabel('Nombre', { exact: true })
      .fill('Universidad Nacional');
    await form.getByLabel('Tipo').selectOption('universidad');
    await form
      .getByLabel('Dominios de correo (opcional)')
      .fill('UES.edu.sv, ues.edu.sv ,');
    await form.getByRole('button', { name: 'Agregar institución' }).click();
    await expect(form.getByRole('status')).toHaveText('Institución agregada.');
    expect(
      llamadas.find((l) => l.clave === 'POST /api/admin/instituciones')?.cuerpo,
    ).toEqual({
      nombre: 'Universidad Nacional',
      tipo: 'universidad',
      dominios_correo: ['ues.edu.sv', 'ues.edu.sv'],
      sitio_web: null,
    });

    await page
      .getByRole('button', { name: 'Verificar Hospital Rosales' })
      .click();
    const dialogo = page.getByRole('dialog', { name: 'Verificar institución' });
    await dialogo
      .getByLabel('Método de verificación')
      .fill('Llamada a la dirección del hospital.');
    await dialogo
      .getByRole('button', { name: 'Marcar como verificada' })
      .click();
    await expect(page.getByText('Institución verificada.')).toBeVisible();
  });
});
