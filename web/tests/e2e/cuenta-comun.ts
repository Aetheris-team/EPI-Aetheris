import AxeBuilder from '@axe-core/playwright';
import {
  expect,
  type CDPSession,
  type Page,
  type Request,
} from '@playwright/test';

/**
 * Las pantallas de cuenta solo existen si el sitio se construyó con
 * PUBLIC_CUENTAS_HABILITADAS=true. El servidor de desarrollo y la prueba
 * deben arrancarse con el mismo valor.
 */
export const CUENTAS_HABILITADAS =
  process.env.PUBLIC_CUENTAS_HABILITADAS === 'true';

export interface RespuestaSimulada {
  status?: number;
  json?: unknown;
  headers?: Record<string, string>;
  /** Corta la conexión, como una red caída. */
  abortar?: boolean;
}

export type Simulacion =
  | RespuestaSimulada
  | ((peticion: Request) => RespuestaSimulada | Promise<RespuestaSimulada>);

export interface Llamada {
  clave: string;
  cuerpo: unknown;
  cabeceras: Record<string, string>;
}

/**
 * Simula /api/cuenta y /api/admin. Cada clave es "MÉTODO /ruta". Responde
 * también las comprobaciones previas de CORS, porque el sitio y la API están
 * en orígenes distintos y el cliente manda cookies y X-CSRF-Token.
 */
export async function simularApi(
  page: Page,
  rutas: Record<string, Simulacion>,
): Promise<Llamada[]> {
  const llamadas: Llamada[] = [];
  await page.route(/\/api\/(cuenta|admin)\//, async (route) => {
    const peticion = route.request();
    const cors = {
      'access-control-allow-origin': peticion.headers()['origin'] ?? '*',
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': 'content-type, x-csrf-token',
      'access-control-allow-methods': 'GET, POST, PATCH, OPTIONS',
      'access-control-expose-headers': 'retry-after',
    };
    if (peticion.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: cors });
      return;
    }
    const clave = `${peticion.method()} ${new URL(peticion.url()).pathname}`;
    llamadas.push({
      clave,
      cuerpo: peticion.postDataJSON() ?? null,
      cabeceras: peticion.headers(),
    });
    const simulacion = rutas[clave];
    if (!simulacion) {
      await route.fulfill({
        status: 500,
        headers: cors,
        json: {
          detail: {
            codigo: 'sin_simulacion',
            mensaje: `Sin simulación para ${clave}`,
          },
        },
      });
      return;
    }
    const respuesta =
      typeof simulacion === 'function'
        ? await simulacion(peticion)
        : simulacion;
    if (respuesta.abortar) {
      await route.abort('failed');
      return;
    }
    await route.fulfill({
      status: respuesta.status ?? 200,
      headers: { ...cors, ...respuesta.headers },
      json: respuesta.json,
    });
  });
  return llamadas;
}

export function error(
  status: number,
  codigo: string,
  mensaje: string,
  espera_s: number | null = null,
  headers: Record<string, string> = {},
): RespuestaSimulada {
  return { status, headers, json: { detail: { codigo, mensaje, espera_s } } };
}

export const ANONIMA = { autenticada: false };

export function sesion(cambios: Record<string, unknown> = {}) {
  return {
    autenticada: true,
    nivel: 'completo',
    usuario: { id: 'u-1', correo: 'ana@salud.gob.sv', nombre: 'Ana Pérez' },
    roles: ['publicador'],
    metodos: ['clave', 'totp'],
    csrf_token: 'csrf-completo',
    reautenticacion_vigente: true,
    factores: [
      { id: 'f-1', tipo: 'totp', etiqueta: 'Aplicación de autenticación' },
    ],
    ...cambios,
  };
}

export async function sinViolacionesAxe(page: Page): Promise<void> {
  const resultado = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  expect(
    resultado.violations.map((v) => ({
      id: v.id,
      nodos: v.nodes.slice(0, 3).map((n) => n.target.join(' ')),
    })),
  ).toEqual([]);
}

/** Autenticador virtual de Chromium para probar llaves de acceso sin hardware. */
export async function autenticadorVirtual(page: Page): Promise<CDPSession> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('WebAuthn.enable');
  await cdp.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2',
      transport: 'internal',
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
  return cdp;
}

export function base64url(texto: string): string {
  return Buffer.from(texto).toString('base64url');
}

/** Opciones de registro con la forma que entrega py_webauthn. */
export function opcionesRegistro() {
  return {
    rp: { name: 'EPI-Aetheris', id: 'localhost' },
    user: {
      id: base64url('u-1'),
      name: 'ana@salud.gob.sv',
      displayName: 'Ana Pérez',
    },
    challenge: base64url('desafio-de-registro-0123456789'),
    pubKeyCredParams: [{ type: 'public-key', alg: -7 }],
    timeout: 60000,
    excludeCredentials: [],
    authenticatorSelection: {
      residentKey: 'preferred',
      requireResidentKey: false,
      userVerification: 'required',
    },
    attestation: 'none',
  };
}
