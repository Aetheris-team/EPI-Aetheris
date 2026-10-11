// Envoltorios de WebAuthn para las llaves de acceso.
//
// El backend (py_webauthn) manda las opciones en JSON con camelCase y los
// binarios en base64url; el navegador exige ArrayBuffer. Estas funciones
// convierten en los dos sentidos y devuelven la credencial ya serializada
// como la espera el backend. Los errores del navegador se traducen a mensajes
// que la persona pueda actuar, sin el texto técnico de la API.

type Json = Record<string, unknown>;

/** Error de WebAuthn con un mensaje listo para mostrar. */
export class ErrorLlave extends Error {
  readonly cancelado: boolean;

  constructor(mensaje: string, cancelado = false) {
    super(mensaje);
    this.name = 'ErrorLlave';
    this.cancelado = cancelado;
  }
}

export function base64urlABuffer(texto: string): ArrayBuffer {
  const base64 = texto.replace(/-/g, '+').replace(/_/g, '/');
  const relleno = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
  const binario = atob(relleno);
  const bytes = new Uint8Array(binario.length);
  for (let i = 0; i < binario.length; i++) bytes[i] = binario.charCodeAt(i);
  return bytes.buffer;
}

export function bufferABase64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binario = '';
  for (const byte of bytes) binario += String.fromCharCode(byte);
  return btoa(binario)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

export function soportaLlaves(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.isSecureContext &&
    typeof window.PublicKeyCredential !== 'undefined' &&
    !!navigator.credentials
  );
}

export const MENSAJE_SIN_SOPORTE =
  'Este navegador o esta conexión no admite llaves de acceso. Usa una aplicación de autenticación o prueba con otro navegador.';

function esObjeto(valor: unknown): valor is Json {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor);
}

function descriptores(valor: unknown): PublicKeyCredentialDescriptor[] {
  if (!Array.isArray(valor)) return [];
  return valor.filter(esObjeto).map((d) => ({
    ...(d as unknown as PublicKeyCredentialDescriptor),
    id: base64urlABuffer(String(d.id)),
  }));
}

function traducirError(
  error: unknown,
  accion: 'registro' | 'ingreso',
): ErrorLlave {
  const nombre = error instanceof DOMException ? error.name : '';
  switch (nombre) {
    case 'NotAllowedError':
    case 'AbortError':
      return new ErrorLlave(
        accion === 'registro'
          ? 'Se canceló el registro o venció el tiempo. Inténtalo de nuevo.'
          : 'Se canceló la verificación o venció el tiempo. Inténtalo de nuevo.',
        true,
      );
    case 'InvalidStateError':
      return new ErrorLlave('Esta llave ya está registrada en tu cuenta.');
    case 'NotSupportedError':
      return new ErrorLlave(
        'Tu dispositivo no admite este tipo de llave. Prueba con otra o usa una aplicación de autenticación.',
      );
    case 'SecurityError':
      return new ErrorLlave(
        'El navegador rechazó la llave para este sitio. Abre el sitio desde su dirección habitual e inténtalo de nuevo.',
      );
    default:
      return new ErrorLlave(
        'No se pudo usar la llave de acceso. Inténtalo de nuevo o usa otro método.',
      );
  }
}

/** Crea una llave nueva a partir de las opciones del backend. */
export async function crearLlave(opciones: Json): Promise<Json> {
  if (!soportaLlaves()) throw new ErrorLlave(MENSAJE_SIN_SOPORTE);
  const usuario = opciones.user as Json | undefined;
  if (!esObjeto(usuario))
    throw new ErrorLlave('Las opciones de registro no son válidas.');
  const publica = {
    ...(opciones as unknown as PublicKeyCredentialCreationOptions),
    challenge: base64urlABuffer(String(opciones.challenge)),
    user: {
      ...(usuario as unknown as PublicKeyCredentialUserEntity),
      id: base64urlABuffer(String(usuario.id)),
    },
    excludeCredentials: descriptores(opciones.excludeCredentials),
  };
  let credencial: Credential | null;
  try {
    credencial = await navigator.credentials.create({ publicKey: publica });
  } catch (error) {
    throw traducirError(error, 'registro');
  }
  if (!(credencial instanceof PublicKeyCredential)) {
    throw new ErrorLlave('El dispositivo no devolvió una llave.');
  }
  const respuesta = credencial.response as AuthenticatorAttestationResponse;
  return {
    id: credencial.id,
    rawId: bufferABase64url(credencial.rawId),
    type: credencial.type,
    authenticatorAttachment: credencial.authenticatorAttachment ?? undefined,
    clientExtensionResults: credencial.getClientExtensionResults(),
    response: {
      clientDataJSON: bufferABase64url(respuesta.clientDataJSON),
      attestationObject: bufferABase64url(respuesta.attestationObject),
      transports:
        typeof respuesta.getTransports === 'function'
          ? respuesta.getTransports()
          : [],
    },
  };
}

/** Firma el desafío de ingreso con una llave ya registrada. */
export async function usarLlave(opciones: Json): Promise<Json> {
  if (!soportaLlaves()) throw new ErrorLlave(MENSAJE_SIN_SOPORTE);
  const publica = {
    ...(opciones as unknown as PublicKeyCredentialRequestOptions),
    challenge: base64urlABuffer(String(opciones.challenge)),
    allowCredentials: descriptores(opciones.allowCredentials),
  };
  let credencial: Credential | null;
  try {
    credencial = await navigator.credentials.get({ publicKey: publica });
  } catch (error) {
    throw traducirError(error, 'ingreso');
  }
  if (!(credencial instanceof PublicKeyCredential)) {
    throw new ErrorLlave('El dispositivo no devolvió una llave.');
  }
  const respuesta = credencial.response as AuthenticatorAssertionResponse;
  return {
    id: credencial.id,
    rawId: bufferABase64url(credencial.rawId),
    type: credencial.type,
    authenticatorAttachment: credencial.authenticatorAttachment ?? undefined,
    clientExtensionResults: credencial.getClientExtensionResults(),
    response: {
      clientDataJSON: bufferABase64url(respuesta.clientDataJSON),
      authenticatorData: bufferABase64url(respuesta.authenticatorData),
      signature: bufferABase64url(respuesta.signature),
      userHandle: respuesta.userHandle
        ? bufferABase64url(respuesta.userHandle)
        : undefined,
    },
  };
}
