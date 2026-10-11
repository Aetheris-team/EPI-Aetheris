// Requisitos de contraseña que el backend aplica (api/cuentas/contrasenas.py).
// Se repiten aquí solo para mostrarlos mientras la persona escribe; quien
// decide es el servidor, que además consulta filtraciones conocidas.

export const LARGO_MIN_CONTRASENA = 12;
export const LARGO_MAX_CONTRASENA = 128;

export interface RequisitoContrasena {
  id: string;
  texto: string;
  cumple: boolean;
}

export interface DatosPersonales {
  nombre?: string;
  correo?: string;
}

function contieneDato(contrasena: string, dato: string | undefined): boolean {
  const limpio = (dato ?? '').trim().toLowerCase();
  return limpio.length >= 4 && contrasena.toLowerCase().includes(limpio);
}

export function evaluarContrasena(
  contrasena: string,
  datos: DatosPersonales = {},
): RequisitoContrasena[] {
  const normal = contrasena.normalize('NFKC');
  const parteLocal = (datos.correo ?? '').split('@')[0];
  return [
    {
      id: 'largo',
      texto: `Entre ${LARGO_MIN_CONTRASENA} y ${LARGO_MAX_CONTRASENA} caracteres`,
      cumple:
        normal.length >= LARGO_MIN_CONTRASENA &&
        normal.length <= LARGO_MAX_CONTRASENA,
    },
    {
      id: 'variedad',
      texto: 'Con al menos 5 caracteres distintos',
      cumple: new Set(normal).size >= 5,
    },
    {
      id: 'personal',
      texto: 'Sin tu nombre ni tu correo',
      cumple:
        !contieneDato(normal, datos.nombre) &&
        !contieneDato(normal, datos.correo) &&
        !contieneDato(normal, parteLocal),
    },
  ];
}

export function contrasenaCumple(
  contrasena: string,
  datos: DatosPersonales = {},
): boolean {
  return evaluarContrasena(contrasena, datos).every((r) => r.cumple);
}
