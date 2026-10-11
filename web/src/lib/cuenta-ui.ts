// Utilidades de DOM compartidas por las pantallas de cuenta. Las pantallas
// son Astro estático con TypeScript en el navegador (sin framework), así que
// aquí viven las piezas que se repetían: avisos accesibles, carga de botones,
// lectura del token del fragmento y el QR del alta.

import { ErrorCuenta } from './cuenta-api';
import { ErrorLlave } from './webauthn-cliente';
import {
  evaluarContrasena,
  type DatosPersonales,
} from './contrasena-requisitos';
import type { EstadoUsuario, RolCuenta } from './tipos-cuenta';

export function pedirElemento<T extends HTMLElement>(
  raiz: ParentNode,
  selector: string,
): T {
  const el = raiz.querySelector<T>(selector);
  if (!el) throw new Error(`Falta el elemento ${selector} en la página.`);
  return el;
}

// --- Avisos -----------------------------------------------------------------

export type TipoAviso = 'error' | 'ok' | 'info';

const CLASES_AVISO: Record<TipoAviso, string> = {
  error: 'border-red-500/40 bg-red-500/10 text-red-800 dark:text-red-200',
  ok: 'border-accent/40 bg-accent/10 text-ink',
  info: 'border-border bg-surface text-ink',
};

const BASE_AVISO =
  'rounded-xl border p-3 font-sans text-sm leading-relaxed focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent';

/**
 * Pinta un mensaje en una región `tabindex="-1"`. Los errores usan
 * role="alert" y reciben el foco para que quien navega con teclado o lector
 * de pantalla llegue a ellos; el resto es role="status" y no mueve el foco.
 */
export function mostrarAviso(
  region: HTMLElement,
  tipo: TipoAviso,
  texto: string,
): void {
  region.hidden = false;
  region.setAttribute('role', tipo === 'error' ? 'alert' : 'status');
  region.className = `${BASE_AVISO} ${CLASES_AVISO[tipo]}`;
  region.textContent = texto;
  if (tipo === 'error') region.focus();
}

export function limpiarAviso(region: HTMLElement): void {
  region.hidden = true;
  region.textContent = '';
}

export function mensajeDeError(error: unknown): string {
  if (error instanceof ErrorCuenta) {
    if (error.status === 429 || error.codigo === 'demasiados_intentos') {
      return error.esperaS
        ? `Demasiados intentos. Espera ${textoEspera(error.esperaS)} antes de volver a probar.`
        : 'Demasiados intentos. Espera un momento antes de volver a probar.';
    }
    return error.message;
  }
  if (error instanceof ErrorLlave) return error.message;
  return 'Ocurrió un error inesperado. Inténtalo de nuevo.';
}

function textoEspera(segundos: number): string {
  if (segundos < 90) return `${segundos} segundos`;
  return `${Math.ceil(segundos / 60)} minutos`;
}

/** Deshabilita el botón y marca aria-busy mientras corre la tarea. */
export async function conCarga(
  boton: HTMLButtonElement,
  tarea: () => Promise<void>,
): Promise<void> {
  if (boton.disabled) return;
  boton.disabled = true;
  boton.setAttribute('aria-busy', 'true');
  try {
    await tarea();
  } finally {
    boton.disabled = false;
    boton.removeAttribute('aria-busy');
  }
}

// --- Token en el fragmento --------------------------------------------------

/**
 * Los enlaces de invitación y restablecimiento llevan el token en el
 * fragmento (`#t=...`): el navegador no lo envía al servidor, así que no queda
 * en registros de acceso ni en el Referer. Se lee una vez y se borra de la
 * barra de direcciones y del historial.
 */
export function leerTokenDelFragmento(): string | null {
  const parametros = new URLSearchParams(location.hash.replace(/^#/, ''));
  const token = parametros.get('t');
  if (location.hash) {
    history.replaceState(null, '', location.pathname + location.search);
  }
  return token && token.length <= 200 ? token : null;
}

/** Destino tras ingresar: solo rutas internas de cuenta o administración. */
export function rutaSiguiente(porDefecto = '/cuenta'): string {
  const siguiente = new URLSearchParams(location.search).get('siguiente');
  if (
    siguiente &&
    /^\/(cuenta|admin)(\/[A-Za-z0-9\-_/]*)?$/.test(siguiente) &&
    !siguiente.startsWith('//')
  ) {
    return siguiente;
  }
  return porDefecto;
}

// --- QR del alta -------------------------------------------------------------

/**
 * Muestra el QR que genera el backend (SVG con xmlns, fondo transparente).
 * Se valida con DOMParser (raíz svg, sin scripts, foreignObject, atributos
 * on* ni enlaces) y se pinta como <img> con data URL: dentro de <img> un SVG
 * no ejecuta nada aunque la validación fallara. Va sobre fondo blanco porque
 * los lectores de QR necesitan contraste oscuro sobre claro, también en tema
 * oscuro. Devuelve false si el SVG no es de fiar.
 */
export function pintarQr(
  contenedor: HTMLElement,
  svg: string,
  alternativa: string,
): boolean {
  const documento = new DOMParser().parseFromString(svg, 'image/svg+xml');
  const raiz = documento.documentElement;
  if (
    raiz.localName !== 'svg' ||
    documento.querySelector('parsererror') ||
    documento.querySelector('script, foreignObject, image, use, a, style')
  ) {
    return false;
  }
  for (const nodo of [raiz, ...Array.from(raiz.querySelectorAll('*'))]) {
    for (const atributo of Array.from(nodo.attributes)) {
      if (/^on/i.test(atributo.name) || /href/i.test(atributo.name)) {
        return false;
      }
    }
  }
  const img = document.createElement('img');
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  img.alt = alternativa;
  img.className = 'h-44 w-44 [image-rendering:pixelated]';
  contenedor.replaceChildren(img);
  return true;
}

// --- Contraseñas ---------------------------------------------------------------

/**
 * Pinta la lista de requisitos de una contraseña. El estado va en texto
 * (no solo en color) para que no dependa de verlo.
 */
export function vincularRequisitos(
  campo: HTMLInputElement,
  lista: HTMLElement,
  datos: () => DatosPersonales = () => ({}),
): void {
  const pintar = (): void => {
    const requisitos = evaluarContrasena(campo.value, datos());
    lista.replaceChildren(
      ...requisitos.map((r) => {
        const li = document.createElement('li');
        li.className = r.cumple ? 'text-ink' : 'text-ink-muted';
        li.dataset.cumple = String(r.cumple);
        const marca = document.createElement('span');
        marca.setAttribute('aria-hidden', 'true');
        marca.textContent = r.cumple ? '✓ ' : '• ';
        const texto = document.createElement('span');
        texto.textContent = r.texto;
        const estado = document.createElement('span');
        estado.className = 'sr-only';
        estado.textContent = r.cumple ? ' (cumple)' : ' (pendiente)';
        li.append(marca, texto, estado);
        return li;
      }),
    );
  };
  campo.addEventListener('input', pintar);
  pintar();
}

/** Casilla "Mostrar contraseña" para uno o más campos. */
export function vincularMostrarContrasena(
  casilla: HTMLInputElement,
  campos: HTMLInputElement[],
): void {
  casilla.addEventListener('change', () => {
    for (const campo of campos)
      campo.type = casilla.checked ? 'text' : 'password';
  });
}

// --- Presentación ---------------------------------------------------------------

const ETIQUETAS_ROL: Record<RolCuenta, string> = {
  publicador: 'Publicador',
  revisor: 'Revisor',
  administrador: 'Administrador',
};

const ETIQUETAS_ESTADO: Record<EstadoUsuario, string> = {
  invitado: 'Invitado',
  activo: 'Activo',
  suspendido: 'Suspendido',
  baja: 'De baja',
};

export function etiquetaRol(rol: RolCuenta): string {
  return ETIQUETAS_ROL[rol];
}

export function etiquetaEstado(estado: EstadoUsuario): string {
  return ETIQUETAS_ESTADO[estado];
}

export function formatearFecha(iso: string | null): string {
  if (!iso) return 'Nunca';
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return iso;
  return new Intl.DateTimeFormat('es-SV', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'America/El_Salvador',
  }).format(fecha);
}

/** Texto de un agente de usuario reducido a algo legible. */
export function resumirAgente(agente: string | null): string {
  return agente?.trim() || 'Dispositivo desconocido';
}
