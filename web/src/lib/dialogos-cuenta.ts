// Diálogos de /cuenta y /admin: confirmar la contraseña (reautenticación) y
// confirmar una acción con motivo. Usan <dialog> modal nativo, que atrapa el
// foco y se cierra con Escape; el marcado vive en DialogosCuenta.astro.

import { ErrorCuenta, reautenticar } from './cuenta-api';
import {
  limpiarAviso,
  mensajeDeError,
  mostrarAviso,
  pedirElemento,
} from './cuenta-ui';
import { fijarSesion } from './sesion-state';

function dialogo(selector: string): HTMLDialogElement {
  return pedirElemento<HTMLDialogElement>(document, selector);
}

/** Conecta "Cancelar" y devuelve la función que lo desconecta. */
function vincularCancelar(el: HTMLDialogElement): () => void {
  const boton = pedirElemento<HTMLButtonElement>(el, '[data-cancelar]');
  const cancelar = (): void => el.close('cancelar');
  boton.addEventListener('click', cancelar);
  return () => boton.removeEventListener('click', cancelar);
}

function esperarCierre(el: HTMLDialogElement): Promise<string> {
  return new Promise((resolver) => {
    el.addEventListener('close', () => resolver(el.returnValue), {
      once: true,
    });
  });
}

/**
 * Pide la contraseña y la valida con /api/cuenta/reautenticar. Un error
 * (contraseña equivocada, demasiados intentos) se muestra dentro del diálogo,
 * que sigue abierto. Devuelve true si la reautenticación quedó vigente.
 */
export async function pedirReautenticacion(): Promise<boolean> {
  const el = dialogo('[data-dialogo-reauth]');
  const form = pedirElemento<HTMLFormElement>(el, 'form');
  const campo = pedirElemento<HTMLInputElement>(el, '[name="contrasena"]');
  const aviso = pedirElemento<HTMLElement>(el, '[data-aviso]');
  const enviar = pedirElemento<HTMLButtonElement>(el, '[data-confirmar]');

  campo.value = '';
  limpiarAviso(aviso);
  el.returnValue = '';

  const alEnviar = async (evento: SubmitEvent): Promise<void> => {
    evento.preventDefault();
    if (enviar.disabled) return;
    if (!campo.value) {
      mostrarAviso(aviso, 'error', 'Escribe tu contraseña.');
      return;
    }
    enviar.disabled = true;
    limpiarAviso(aviso);
    try {
      fijarSesion(await reautenticar(campo.value));
      el.close('ok');
    } catch (error) {
      mostrarAviso(aviso, 'error', mensajeDeError(error));
    } finally {
      enviar.disabled = false;
    }
  };
  form.addEventListener('submit', alEnviar);
  const desvincular = vincularCancelar(el);
  el.showModal();
  campo.focus();
  const resultado = await esperarCierre(el);
  form.removeEventListener('submit', alEnviar);
  desvincular();
  campo.value = '';
  return resultado === 'ok';
}

/**
 * Ejecuta una acción y, si el backend pide confirmar la contraseña
 * (`requiere_reautenticacion`), la pide y reintenta una vez. Si la persona
 * cancela, se propaga el error original.
 */
export async function conReautenticacion<T>(
  tarea: () => Promise<T>,
): Promise<T> {
  try {
    return await tarea();
  } catch (error) {
    if (
      error instanceof ErrorCuenta &&
      error.codigo === 'requiere_reautenticacion' &&
      (await pedirReautenticacion())
    ) {
      return tarea();
    }
    throw error;
  }
}

export interface OpcionesConfirmacion {
  titulo: string;
  texto: string;
  etiquetaConfirmar: string;
  /** Pide un motivo de al menos 5 caracteres, que queda en la auditoría. */
  pedirMotivo?: boolean;
  /** Nombre del campo cuando no es "Motivo" (por ejemplo, el método de verificación). */
  etiquetaMotivo?: string;
}

/** Devuelve el motivo escrito (vacío si no se pidió) o null si se cancela. */
export async function confirmarAccion(
  opciones: OpcionesConfirmacion,
): Promise<{ motivo: string } | null> {
  const el = dialogo('[data-dialogo-confirmar]');
  const form = pedirElemento<HTMLFormElement>(el, 'form');
  const titulo = pedirElemento<HTMLElement>(el, '[data-titulo]');
  const texto = pedirElemento<HTMLElement>(el, '[data-texto]');
  const grupoMotivo = pedirElemento<HTMLElement>(el, '[data-grupo-motivo]');
  const motivo = pedirElemento<HTMLTextAreaElement>(el, '[name="motivo"]');
  const aviso = pedirElemento<HTMLElement>(el, '[data-aviso]');
  const confirmar = pedirElemento<HTMLButtonElement>(el, '[data-confirmar]');

  titulo.textContent = opciones.titulo;
  texto.textContent = opciones.texto;
  confirmar.textContent = opciones.etiquetaConfirmar;
  pedirElemento<HTMLElement>(
    grupoMotivo,
    '[data-etiqueta-motivo]',
  ).textContent = opciones.etiquetaMotivo ?? 'Motivo';
  grupoMotivo.hidden = !opciones.pedirMotivo;
  motivo.required = !!opciones.pedirMotivo;
  motivo.value = '';
  limpiarAviso(aviso);
  el.returnValue = '';

  const alEnviar = (evento: SubmitEvent): void => {
    evento.preventDefault();
    if (opciones.pedirMotivo && motivo.value.trim().length < 5) {
      mostrarAviso(
        aviso,
        'error',
        `Completa el campo «${opciones.etiquetaMotivo ?? 'Motivo'}» (al menos 5 caracteres).`,
      );
      return;
    }
    el.close('ok');
  };
  form.addEventListener('submit', alEnviar);
  const desvincular = vincularCancelar(el);
  el.showModal();
  (opciones.pedirMotivo ? motivo : confirmar).focus();
  const resultado = await esperarCierre(el);
  form.removeEventListener('submit', alEnviar);
  desvincular();
  return resultado === 'ok' ? { motivo: motivo.value.trim() } : null;
}
