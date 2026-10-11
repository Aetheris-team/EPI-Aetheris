// Interruptor de las cuentas. Con el backend de cuentas apagado
// (CUENTAS_HABILITADAS=false) las rutas /api/cuenta no existen, así que el
// sitio no debe ofrecer ningún enlace hacia ellas. Se resuelve al construir
// y vale para todo el sitio estático.
export const CUENTAS_HABILITADAS =
  import.meta.env.PUBLIC_CUENTAS_HABILITADAS === 'true';
