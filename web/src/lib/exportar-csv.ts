// Descarga de CSV compartida por los paneles que ofrecen «Datos (CSV)» en el
// menú «Exportar» (MenuExportar). Cada panel arma su contenido; aquí viven la
// escritura de celdas, la descarga y el enlace con la opción del menú.

export type CeldaCsv = string | number | boolean | null | undefined;

/** Una celda con comillas si lleva coma, comilla o salto de línea. */
export function celdaCsv(valor: CeldaCsv): string {
  if (valor === null || valor === undefined) return '';
  const texto = String(valor);
  return /[",\n]/.test(texto) ? `"${texto.replaceAll('"', '""')}"` : texto;
}

export function lineaCsv(celdas: CeldaCsv[]): string {
  return celdas.map(celdaCsv).join(',');
}

export function descargarCsv(nombre: string, contenido: string): void {
  const enlace = document.createElement('a');
  enlace.href = URL.createObjectURL(
    new Blob([contenido], { type: 'text/csv;charset=utf-8' }),
  );
  enlace.download = nombre;
  // El clic del enlace no debe llegar al documento: los paneles que se cierran
  // al pulsar fuera de ellos (los filtros de /dengue) lo tomarían por un clic
  // del usuario en otra parte.
  enlace.addEventListener('click', (evento) => evento.stopPropagation());
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(enlace.href);
}

export interface ArchivoCsv {
  nombre: string;
  contenido: string;
}

/**
 * Habilita la opción «Datos (CSV)» de un menú «Exportar» y le asigna la
 * descarga. Se puede llamar de nuevo cuando cambian los datos: reemplaza la
 * anterior en lugar de acumular escuchas. Si `generar` devuelve null no
 * descarga nada.
 */
export function habilitarCsv(
  opcion: HTMLElement | null,
  generar: () => ArchivoCsv | null,
): void {
  if (!(opcion instanceof HTMLButtonElement)) return;
  opcion.disabled = false;
  opcion.removeAttribute('title');
  opcion.onclick = () => {
    const archivo = generar();
    if (archivo) descargarCsv(archivo.nombre, archivo.contenido);
  };
}

/** Vuelve a dejar la opción sin efecto, por ejemplo tras un error de carga. */
export function inhabilitarCsv(opcion: HTMLElement | null): void {
  if (!(opcion instanceof HTMLButtonElement)) return;
  opcion.disabled = true;
  opcion.onclick = null;
}
