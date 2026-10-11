// Formas de las respuestas de /api/cuenta y /api/admin. Los validadores de
// cuenta-api.ts comprueban la forma antes de devolver estos tipos.

export const ROLES_CUENTA = ['publicador', 'revisor', 'administrador'] as const;
export type RolCuenta = (typeof ROLES_CUENTA)[number];

export type NivelSesion = 'alta_pendiente' | 'segundo_factor' | 'completo';

export type TipoFactor = 'totp' | 'webauthn';

export interface FactorCuenta {
  id: string;
  tipo: TipoFactor;
  etiqueta: string;
}

export interface SesionAnonima {
  autenticada: false;
}

export interface SesionActiva {
  autenticada: true;
  nivel: NivelSesion;
  usuario: { id: string; correo: string; nombre: string };
  roles: RolCuenta[];
  metodos: string[];
  csrf_token: string;
  reautenticacion_vigente: boolean;
  factores: FactorCuenta[];
}

export type EstadoSesion = SesionAnonima | SesionActiva;

export interface InvitacionVista {
  correo: string;
  roles: RolCuenta[];
  institucion: string | null;
  terminos_version: string;
}

export interface TotpIniciado {
  factor_id: string;
  secreto: string;
  uri: string;
  qr_svg: string;
}

export interface ResultadoFactor {
  activada: boolean;
  /** Solo llega una vez, al activarse la cuenta. */
  codigos_recuperacion: string[] | null;
}

export interface SesionAbierta {
  id: string;
  creada_en: string;
  ultima_actividad_en: string;
  agente: string | null;
  red: string | null;
  actual: boolean;
}

export type EstadoUsuario = 'invitado' | 'activo' | 'suspendido' | 'baja';

export interface UsuarioAdmin {
  id: string;
  correo: string;
  nombre: string | null;
  estado: EstadoUsuario;
  institucion: string | null;
  ultimo_ingreso_en: string | null;
  roles: RolCuenta[];
}

export const TIPOS_INSTITUCION = [
  'minsal',
  'sibasi',
  'hospital',
  'universidad',
  'organismo',
  'otro',
] as const;
export type TipoInstitucion = (typeof TIPOS_INSTITUCION)[number];

export interface InstitucionAdmin {
  id: number;
  nombre: string;
  tipo: TipoInstitucion;
  dominios_correo: string[];
  verificada: boolean;
  activa: boolean;
}

export interface DatosInvitacion {
  correo: string;
  roles: RolCuenta[];
  institucion_id: number | null;
  nota_verificacion: string;
  justificacion_dominio: string | null;
}

export interface DatosInstitucion {
  nombre: string;
  tipo: TipoInstitucion;
  dominios_correo: string[];
  sitio_web: string | null;
}
