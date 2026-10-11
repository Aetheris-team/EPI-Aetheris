// Cliente de /api/cuenta y /api/admin (ADR 0024).
//
// El backend identifica a la persona por una cookie de sesión HttpOnly que el
// navegador manda solo (credentials: 'include'); este código nunca la ve. Toda
// petición que cambia estado la acepta si el Origin es el canónico y trae
// X-CSRF-Token, un valor derivado de la sesión que llega en las respuestas de
// sesión. Ese token vive solo en memoria: tras recargar la página se recupera
// con obtenerSesion(), y no se escribe en localStorage.
//
// A diferencia de analisis-api.ts, aquí no hay caché de promesas: son
// acciones de una persona sobre su cuenta, no lecturas compartidas.

import {
  ROLES_CUENTA,
  TIPOS_INSTITUCION,
  type DatosInstitucion,
  type DatosInvitacion,
  type EstadoSesion,
  type EstadoUsuario,
  type FactorCuenta,
  type InstitucionAdmin,
  type InvitacionVista,
  type NivelSesion,
  type ResultadoFactor,
  type RolCuenta,
  type SesionAbierta,
  type SesionActiva,
  type TipoInstitucion,
  type TotpIniciado,
  type UsuarioAdmin,
} from './tipos-cuenta';

const API_BASE = import.meta.env.PUBLIC_API_URL ?? 'http://localhost:8000';

/** Se emite cuando el backend dice que ya no hay sesión (caducó o la cerraron). */
export const EVENTO_SESION_EXPIRADA = 'epi:sesion-expirada';

let tokenCsrf: string | null = null;

/** Error del backend (`{detail:{codigo,mensaje,espera_s}}`) o de red. */
export class ErrorCuenta extends Error {
  readonly status: number;
  readonly codigo: string;
  /** Segundos que hay que esperar antes de reintentar (429). */
  readonly esperaS: number | null;

  constructor(
    status: number,
    codigo: string,
    mensaje: string,
    esperaS: number | null = null,
  ) {
    super(mensaje);
    this.name = 'ErrorCuenta';
    this.status = status;
    this.codigo = codigo;
    this.esperaS = esperaS;
  }
}

type Json = Record<string, unknown>;

function esObjeto(valor: unknown): valor is Json {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor);
}

function formaInvalida(ruta: string): ErrorCuenta {
  return new ErrorCuenta(
    502,
    'respuesta_invalida',
    `La respuesta de ${ruta} no tiene la forma esperada.`,
  );
}

function segundos(valor: unknown): number | null {
  const n = typeof valor === 'string' ? Number(valor) : valor;
  return typeof n === 'number' && Number.isFinite(n) && n > 0
    ? Math.ceil(n)
    : null;
}

async function errorDeRespuesta(res: Response): Promise<ErrorCuenta> {
  let cuerpo: unknown;
  try {
    cuerpo = await res.json();
  } catch {
    cuerpo = null;
  }
  const detalle = esObjeto(cuerpo) ? cuerpo.detail : null;
  const espera =
    (esObjeto(detalle) ? segundos(detalle.espera_s) : null) ??
    segundos(res.headers.get('Retry-After'));

  if (esObjeto(detalle) && typeof detalle.mensaje === 'string') {
    const codigo =
      typeof detalle.codigo === 'string' ? detalle.codigo : 'error';
    return new ErrorCuenta(res.status, codigo, detalle.mensaje, espera);
  }
  // El limitador de peticiones responde 429 sin el formato anterior.
  if (res.status === 429) {
    return new ErrorCuenta(
      429,
      'demasiados_intentos',
      'Demasiados intentos.',
      espera,
    );
  }
  if (res.status === 422) {
    return new ErrorCuenta(
      422,
      'validacion',
      'Revisa los datos: alguno no tiene el formato esperado.',
    );
  }
  if (res.status === 503) {
    return new ErrorCuenta(
      503,
      'cuentas_no_configuradas',
      'Las cuentas no están disponibles.',
    );
  }
  return new ErrorCuenta(
    res.status,
    'error',
    'El servicio respondió con un error inesperado.',
  );
}

async function pedir(
  metodo: 'GET' | 'POST' | 'PATCH',
  ruta: string,
  cuerpo?: unknown,
): Promise<unknown> {
  const cabeceras: Record<string, string> = { Accept: 'application/json' };
  if (cuerpo !== undefined) cabeceras['Content-Type'] = 'application/json';
  if (metodo !== 'GET' && tokenCsrf) cabeceras['X-CSRF-Token'] = tokenCsrf;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${ruta}`, {
      method: metodo,
      credentials: 'include',
      headers: cabeceras,
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
    });
  } catch {
    throw new ErrorCuenta(
      0,
      'red',
      'No se pudo contactar el servicio. Revisa tu conexión e inténtalo de nuevo.',
    );
  }
  if (!res.ok) {
    const error = await errorDeRespuesta(res);
    if (error.status === 401 && error.codigo === 'sin_sesion') {
      tokenCsrf = null;
      window.dispatchEvent(new CustomEvent(EVENTO_SESION_EXPIRADA));
    }
    throw error;
  }
  try {
    return await res.json();
  } catch {
    throw formaInvalida(ruta);
  }
}

// --- Validadores de forma ---------------------------------------------------

function esRol(valor: unknown): valor is RolCuenta {
  return ROLES_CUENTA.includes(valor as RolCuenta);
}

function listaTextos(valor: unknown): valor is string[] {
  return Array.isArray(valor) && valor.every((v) => typeof v === 'string');
}

function textoONulo(valor: unknown): valor is string | null {
  return valor === null || typeof valor === 'string';
}

function listaRoles(valor: unknown): valor is RolCuenta[] {
  return Array.isArray(valor) && valor.every(esRol);
}

function esFactor(valor: unknown): valor is FactorCuenta {
  return (
    esObjeto(valor) &&
    typeof valor.id === 'string' &&
    (valor.tipo === 'totp' || valor.tipo === 'webauthn') &&
    typeof valor.etiqueta === 'string'
  );
}

const NIVELES: NivelSesion[] = ['alta_pendiente', 'segundo_factor', 'completo'];

function validarSesion(dato: unknown, ruta: string): EstadoSesion {
  if (!esObjeto(dato)) throw formaInvalida(ruta);
  if (dato.autenticada === false) return { autenticada: false };
  const usuario = dato.usuario;
  if (
    dato.autenticada !== true ||
    !NIVELES.includes(dato.nivel as NivelSesion) ||
    !esObjeto(usuario) ||
    typeof usuario.id !== 'string' ||
    typeof usuario.correo !== 'string' ||
    !listaRoles(dato.roles) ||
    !listaTextos(dato.metodos) ||
    typeof dato.csrf_token !== 'string' ||
    typeof dato.reautenticacion_vigente !== 'boolean' ||
    !Array.isArray(dato.factores) ||
    !dato.factores.every(esFactor)
  ) {
    throw formaInvalida(ruta);
  }
  tokenCsrf = dato.csrf_token;
  return {
    autenticada: true,
    nivel: dato.nivel as NivelSesion,
    usuario: {
      id: usuario.id,
      correo: usuario.correo,
      nombre: typeof usuario.nombre === 'string' ? usuario.nombre : '',
    },
    roles: dato.roles,
    metodos: dato.metodos,
    csrf_token: dato.csrf_token,
    reautenticacion_vigente: dato.reautenticacion_vigente,
    factores: dato.factores,
  };
}

function validarSesionActiva(dato: unknown, ruta: string): SesionActiva {
  const sesion = validarSesion(dato, ruta);
  if (!sesion.autenticada) throw formaInvalida(ruta);
  return sesion;
}

function validarResultadoFactor(dato: unknown, ruta: string): ResultadoFactor {
  if (
    !esObjeto(dato) ||
    typeof dato.activada !== 'boolean' ||
    !(
      dato.codigos_recuperacion === null ||
      listaTextos(dato.codigos_recuperacion)
    )
  ) {
    throw formaInvalida(ruta);
  }
  return {
    activada: dato.activada,
    codigos_recuperacion: dato.codigos_recuperacion as string[] | null,
  };
}

function mensajeDe(dato: unknown, ruta: string): string {
  if (!esObjeto(dato) || typeof dato.mensaje !== 'string') {
    throw formaInvalida(ruta);
  }
  return dato.mensaje;
}

// --- Sesión e ingreso -------------------------------------------------------

export async function obtenerSesion(): Promise<EstadoSesion> {
  const ruta = '/api/cuenta/sesion';
  return validarSesion(await pedir('GET', ruta), ruta);
}

export async function ingresar(
  correo: string,
  contrasena: string,
): Promise<SesionActiva> {
  const ruta = '/api/cuenta/ingresar';
  return validarSesionActiva(
    await pedir('POST', ruta, { correo, contrasena }),
    ruta,
  );
}

export async function ingresarConTotp(codigo: string): Promise<SesionActiva> {
  const ruta = '/api/cuenta/ingresar/totp';
  return validarSesionActiva(await pedir('POST', ruta, { codigo }), ruta);
}

export async function ingresarConRecuperacion(
  codigo: string,
): Promise<SesionActiva> {
  const ruta = '/api/cuenta/ingresar/recuperacion';
  return validarSesionActiva(await pedir('POST', ruta, { codigo }), ruta);
}

/** Opciones de py_webauthn (camelCase) para navigator.credentials.get. */
export async function opcionesLlaveIngreso(): Promise<Json> {
  const ruta = '/api/cuenta/ingresar/llave/opciones';
  const dato = await pedir('POST', ruta);
  if (!esObjeto(dato) || typeof dato.challenge !== 'string') {
    throw formaInvalida(ruta);
  }
  return dato;
}

export async function ingresarConLlave(
  credencial: Json,
): Promise<SesionActiva> {
  const ruta = '/api/cuenta/ingresar/llave';
  return validarSesionActiva(await pedir('POST', ruta, { credencial }), ruta);
}

export async function salir(): Promise<void> {
  await pedir('POST', '/api/cuenta/salir');
  tokenCsrf = null;
}

export async function reautenticar(contrasena: string): Promise<SesionActiva> {
  const ruta = '/api/cuenta/reautenticar';
  return validarSesionActiva(await pedir('POST', ruta, { contrasena }), ruta);
}

// --- Recuperación de contraseña --------------------------------------------

export async function solicitarRestablecimiento(
  correo: string,
): Promise<string> {
  const ruta = '/api/cuenta/clave/olvide';
  return mensajeDe(await pedir('POST', ruta, { correo }), ruta);
}

export async function restablecerClave(
  token: string,
  contrasena: string,
): Promise<string> {
  const ruta = '/api/cuenta/clave/restablecer';
  return mensajeDe(await pedir('POST', ruta, { token, contrasena }), ruta);
}

export async function cambiarClave(
  actual: string,
  nueva: string,
): Promise<SesionActiva> {
  const ruta = '/api/cuenta/clave/cambiar';
  return validarSesionActiva(
    await pedir('POST', ruta, { actual, nueva }),
    ruta,
  );
}

// --- Invitación y alta ------------------------------------------------------

export async function verInvitacion(token: string): Promise<InvitacionVista> {
  const ruta = '/api/cuenta/invitacion/ver';
  const dato = await pedir('POST', ruta, { token });
  if (
    !esObjeto(dato) ||
    typeof dato.correo !== 'string' ||
    !listaRoles(dato.roles) ||
    !textoONulo(dato.institucion) ||
    typeof dato.terminos_version !== 'string'
  ) {
    throw formaInvalida(ruta);
  }
  return {
    correo: dato.correo,
    roles: dato.roles,
    institucion: dato.institucion,
    terminos_version: dato.terminos_version,
  };
}

export interface DatosAceptacion {
  token: string;
  nombre_visible: string;
  cargo: string | null;
  contrasena: string;
  terminos_version: string;
}

export async function aceptarInvitacion(
  datos: DatosAceptacion,
): Promise<SesionActiva> {
  const ruta = '/api/cuenta/invitacion/aceptar';
  return validarSesionActiva(await pedir('POST', ruta, datos), ruta);
}

export async function iniciarTotp(etiqueta = ''): Promise<TotpIniciado> {
  const ruta = '/api/cuenta/factores/totp/iniciar';
  const dato = await pedir('POST', ruta, { etiqueta });
  if (
    !esObjeto(dato) ||
    typeof dato.factor_id !== 'string' ||
    typeof dato.secreto !== 'string' ||
    typeof dato.uri !== 'string' ||
    typeof dato.qr_svg !== 'string'
  ) {
    throw formaInvalida(ruta);
  }
  return {
    factor_id: dato.factor_id,
    secreto: dato.secreto,
    uri: dato.uri,
    qr_svg: dato.qr_svg,
  };
}

export async function confirmarTotp(
  factorId: string,
  codigo: string,
): Promise<ResultadoFactor> {
  const ruta = '/api/cuenta/factores/totp/confirmar';
  return validarResultadoFactor(
    await pedir('POST', ruta, { factor_id: factorId, codigo }),
    ruta,
  );
}

/** Opciones de py_webauthn (camelCase) para navigator.credentials.create. */
export async function opcionesLlaveRegistro(): Promise<Json> {
  const ruta = '/api/cuenta/factores/llave/opciones';
  const dato = await pedir('POST', ruta);
  if (!esObjeto(dato) || typeof dato.challenge !== 'string') {
    throw formaInvalida(ruta);
  }
  return dato;
}

export async function registrarLlave(
  credencial: Json,
  etiqueta = '',
): Promise<ResultadoFactor> {
  const ruta = '/api/cuenta/factores/llave';
  return validarResultadoFactor(
    await pedir('POST', ruta, { credencial, etiqueta }),
    ruta,
  );
}

export async function completarAlta(): Promise<SesionActiva> {
  const ruta = '/api/cuenta/alta/completar';
  return validarSesionActiva(await pedir('POST', ruta), ruta);
}

// --- Perfil -----------------------------------------------------------------

export async function revocarFactor(factorId: string): Promise<void> {
  const ruta = `/api/cuenta/factores/${encodeURIComponent(factorId)}/revocar`;
  mensajeDe(await pedir('POST', ruta), ruta);
}

function validarSesionAbierta(valor: unknown): valor is SesionAbierta {
  return (
    esObjeto(valor) &&
    typeof valor.id === 'string' &&
    typeof valor.creada_en === 'string' &&
    typeof valor.ultima_actividad_en === 'string' &&
    (valor.agente === null || typeof valor.agente === 'string') &&
    (valor.red === null || typeof valor.red === 'string') &&
    typeof valor.actual === 'boolean'
  );
}

export async function listarSesiones(): Promise<SesionAbierta[]> {
  const ruta = '/api/cuenta/sesiones';
  const dato = await pedir('GET', ruta);
  if (
    !esObjeto(dato) ||
    !Array.isArray(dato.sesiones) ||
    !dato.sesiones.every(validarSesionAbierta)
  ) {
    throw formaInvalida(ruta);
  }
  return dato.sesiones;
}

export async function cerrarOtrasSesiones(): Promise<number> {
  const ruta = '/api/cuenta/sesiones/cerrar-otras';
  const dato = await pedir('POST', ruta);
  if (!esObjeto(dato) || typeof dato.cerradas !== 'number') {
    throw formaInvalida(ruta);
  }
  return dato.cerradas;
}

// --- Administración ---------------------------------------------------------

const ESTADOS: EstadoUsuario[] = ['invitado', 'activo', 'suspendido', 'baja'];

function esUsuarioAdmin(valor: unknown): valor is UsuarioAdmin {
  return (
    esObjeto(valor) &&
    typeof valor.id === 'string' &&
    typeof valor.correo === 'string' &&
    (valor.nombre === null || typeof valor.nombre === 'string') &&
    ESTADOS.includes(valor.estado as EstadoUsuario) &&
    (valor.institucion === null || typeof valor.institucion === 'string') &&
    (valor.ultimo_ingreso_en === null ||
      typeof valor.ultimo_ingreso_en === 'string') &&
    listaRoles(valor.roles)
  );
}

export async function listarUsuarios(): Promise<UsuarioAdmin[]> {
  const ruta = '/api/admin/usuarios';
  const dato = await pedir('GET', ruta);
  if (
    !esObjeto(dato) ||
    !Array.isArray(dato.usuarios) ||
    !dato.usuarios.every(esUsuarioAdmin)
  ) {
    throw formaInvalida(ruta);
  }
  return dato.usuarios;
}

export async function invitar(datos: DatosInvitacion): Promise<void> {
  const ruta = '/api/admin/invitaciones';
  const dato = await pedir('POST', ruta, datos);
  if (!esObjeto(dato)) throw formaInvalida(ruta);
}

export async function cambiarRoles(
  usuarioId: string,
  roles: RolCuenta[],
): Promise<void> {
  const ruta = `/api/admin/usuarios/${encodeURIComponent(usuarioId)}/roles`;
  mensajeDe(await pedir('PATCH', ruta, { roles }), ruta);
}

export async function cambiarEstado(
  usuarioId: string,
  estado: 'activo' | 'suspendido' | 'baja',
  motivo: string,
): Promise<void> {
  const ruta = `/api/admin/usuarios/${encodeURIComponent(usuarioId)}/estado`;
  mensajeDe(await pedir('POST', ruta, { estado, motivo }), ruta);
}

export async function restablecerFactores(
  usuarioId: string,
  motivo: string,
): Promise<void> {
  const ruta = `/api/admin/usuarios/${encodeURIComponent(usuarioId)}/restablecer-factores`;
  mensajeDe(await pedir('POST', ruta, { motivo }), ruta);
}

function esInstitucion(valor: unknown): valor is InstitucionAdmin {
  return (
    esObjeto(valor) &&
    typeof valor.id === 'number' &&
    typeof valor.nombre === 'string' &&
    TIPOS_INSTITUCION.includes(valor.tipo as TipoInstitucion) &&
    listaTextos(valor.dominios_correo ?? []) &&
    typeof valor.verificada === 'boolean' &&
    typeof valor.activa === 'boolean'
  );
}

export async function listarInstituciones(): Promise<InstitucionAdmin[]> {
  const ruta = '/api/admin/instituciones';
  const dato = await pedir('GET', ruta);
  if (
    !esObjeto(dato) ||
    !Array.isArray(dato.instituciones) ||
    !dato.instituciones.every(esInstitucion)
  ) {
    throw formaInvalida(ruta);
  }
  return dato.instituciones.map((i) => ({
    ...i,
    dominios_correo: i.dominios_correo ?? [],
  }));
}

export async function crearInstitucion(
  datos: DatosInstitucion,
): Promise<number> {
  const ruta = '/api/admin/instituciones';
  const dato = await pedir('POST', ruta, datos);
  if (!esObjeto(dato) || typeof dato.id !== 'number') throw formaInvalida(ruta);
  return dato.id;
}

export async function verificarInstitucion(
  id: number,
  metodo: string,
): Promise<void> {
  const ruta = `/api/admin/instituciones/${id}/verificar`;
  mensajeDe(await pedir('POST', ruta, { metodo }), ruta);
}
