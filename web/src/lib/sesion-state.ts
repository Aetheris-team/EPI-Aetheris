// Estado de la sesión de cuenta compartido entre componentes, con el mismo
// patrón que analisis-state.ts: nadie importa a nadie, todos escuchan
// `epi:session-changed` en window.
//
// La fuente de verdad es el backend (GET /api/cuenta/sesion). Aquí solo hay
// una copia en memoria. Lo único que se guarda en el navegador es una pista
// (`epi:sesion-pista`) de que esta persona abrió una sesión alguna vez: sirve
// para que el pie y las páginas públicas no consulten /api/cuenta/sesion a
// quien nunca ha ingresado, que es casi todo el público lector. La pista no
// autentica nada.

import { EVENTO_SESION_EXPIRADA, obtenerSesion } from './cuenta-api';
import type { EstadoSesion, SesionActiva } from './tipos-cuenta';

export const EVENTO_SESION = 'epi:session-changed';
const CLAVE_PISTA = 'epi:sesion-pista';

let actual: EstadoSesion | null = null;
let enCurso: Promise<EstadoSesion> | null = null;

function emitir(): void {
  window.dispatchEvent(new CustomEvent(EVENTO_SESION, { detail: actual }));
}

function guardarPista(hay: boolean): void {
  try {
    if (hay) localStorage.setItem(CLAVE_PISTA, '1');
    else localStorage.removeItem(CLAVE_PISTA);
  } catch {
    // Sin almacenamiento (ventana privada, bloqueado): el pie no ofrece
    // "Mi cuenta" hasta que la página de cuenta consulte la sesión.
  }
}

export function hayPistaDeSesion(): boolean {
  try {
    return localStorage.getItem(CLAVE_PISTA) === '1';
  } catch {
    return false;
  }
}

export function sesionActual(): EstadoSesion | null {
  return actual;
}

/** Registra una sesión devuelta por una acción (ingreso, alta, reautenticación). */
export function fijarSesion(sesion: EstadoSesion): void {
  actual = sesion;
  guardarPista(sesion.autenticada);
  emitir();
}

/** La sesión terminó (salir, o el backend la declaró inválida). */
export function olvidarSesion(): void {
  fijarSesion({ autenticada: false });
}

/**
 * Consulta la sesión al backend. Varias llamadas simultáneas comparten una
 * petición; `forzar` descarta la copia en memoria.
 */
export async function cargarSesion(forzar = false): Promise<EstadoSesion> {
  if (!forzar && actual) return actual;
  if (!enCurso) {
    enCurso = obtenerSesion()
      .then((sesion) => {
        fijarSesion(sesion);
        return sesion;
      })
      .finally(() => {
        enCurso = null;
      });
  }
  return enCurso;
}

/** Para páginas públicas: consulta solo si hay pista de una sesión previa. */
export async function cargarSesionSiHayPista(): Promise<EstadoSesion | null> {
  if (!hayPistaDeSesion()) return null;
  try {
    return await cargarSesion();
  } catch {
    return null;
  }
}

export function suscribirSesion(
  alCambiar: (sesion: EstadoSesion | null) => void,
): () => void {
  const escucha = (): void => alCambiar(actual);
  window.addEventListener(EVENTO_SESION, escucha);
  return () => window.removeEventListener(EVENTO_SESION, escucha);
}

export function esSesionCompleta(
  sesion: EstadoSesion | null,
): sesion is SesionActiva {
  return !!sesion && sesion.autenticada && sesion.nivel === 'completo';
}

// Una petición que el backend rechaza por falta de sesión deja a todos los
// suscriptores con la sesión anónima, para que cada pantalla decida a dónde ir.
if (typeof window !== 'undefined') {
  window.addEventListener(EVENTO_SESION_EXPIRADA, olvidarSesion);
}
