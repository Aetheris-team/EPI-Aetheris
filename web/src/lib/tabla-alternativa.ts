import { escapeHtml } from '../utils/security.ts';

// Todo lo que se interpola en innerHTML pasa por escapeHtml (regla de la casa,
// CLAUDE.md): los valores de las celdas vienen de la API -- el nombre del
// departamento, sin ir mas lejos -- y el encabezado y el caption los fija cada
// panel. escapeHtml devuelve la entrada intacta si no es string, asi que se
// convierte antes: una celda puede ser un numero o null.
function textoSeguro(valor: unknown): string {
  return escapeHtml(String(valor));
}

export interface ColumnaTabla {
  clave: string;
  encabezado: string;
  alineacion?: 'izquierda' | 'derecha';
  formato?: (valor: any, fila: any) => string;
}

export interface OpcionesTablaAlternativa<T> {
  details: HTMLDetailsElement;
  contenedorTabla: HTMLElement;
  caption: string;
  columnas: ColumnaTabla[];
  obtenerDatos: () => T[];
  limiteFilas?: number;
}

export class TablaAlternativa<T = any> {
  private caducada = true;
  private details: HTMLDetailsElement;
  private contenedor: HTMLElement;
  private caption: string;
  private columnas: ColumnaTabla[];
  private obtenerDatos: () => T[];
  private limiteFilas: number;

  constructor(opciones: OpcionesTablaAlternativa<T>) {
    this.details = opciones.details;
    this.contenedor = opciones.contenedorTabla;
    this.caption = opciones.caption;
    this.columnas = opciones.columnas;
    this.obtenerDatos = opciones.obtenerDatos;
    this.limiteFilas = opciones.limiteFilas ?? 500;

    this.details.addEventListener('toggle', () => {
      if (this.details.open && this.caducada) {
        this.construir();
      }
    });
  }

  public marcarCaducada(): void {
    this.caducada = true;
    if (this.details.open) {
      this.construir();
    }
  }

  public construir(): void {
    this.caducada = false;
    const datos = this.obtenerDatos();
    if (!datos || datos.length === 0) {
      this.contenedor.innerHTML =
        '<p class="p-3 text-xs text-ink-muted font-sans">No hay datos disponibles para la selección actual.</p>';
      return;
    }

    const totalFilas = datos.length;
    const filasVisibles = datos.slice(0, this.limiteFilas);
    const avisoLimite =
      totalFilas > this.limiteFilas
        ? `<p class="p-2 text-xs text-ink-muted font-sans">Mostrando las primeras ${this.limiteFilas} de ${totalFilas} filas para el rango seleccionado.</p>`
        : '';

    const encabezadosHtml = this.columnas
      .map(
        (col) =>
          `<th scope="col" class="px-3 py-2 text-left font-sans text-xs font-semibold text-ink ${
            col.alineacion === 'derecha' ? 'text-right' : ''
          }">${textoSeguro(col.encabezado)}</th>`,
      )
      .join('');

    const filasHtml = filasVisibles
      .map((fila) => {
        const celdas = this.columnas
          .map((col, i) => {
            const raw = (fila as any)[col.clave];
            const val = col.formato ? col.formato(raw, fila) : (raw ?? '—');
            const esDerecha = col.alineacion === 'derecha';
            const clase = `px-3 py-1.5 text-xs text-ink ${
              esDerecha ? 'text-right cifra' : 'font-sans'
            }`;
            // La primera columna identifica la fila (semana, año,
            // departamento): es su encabezado, y en el diseño apilado
            // encabeza cada tarjeta. El resto lleva su encabezado de columna
            // en data-etiqueta, que el CSS muestra cuando se ocultan los <th>.
            return i === 0
              ? `<th scope="row" class="${clase} font-semibold">${textoSeguro(val)}</th>`
              : `<td class="${clase}" data-etiqueta="${textoSeguro(col.encabezado)}">${textoSeguro(val)}</td>`;
          })
          .join('');
        return `<tr class="border-b border-border/50 hover:bg-secondary/20">${celdas}</tr>`;
      })
      .join('');

    // Con tres columnas o más, en un contenedor angosto la tabla se apila en
    // tarjetas (global.css, .tabla-alternativa). Con dos cabe tal cual.
    this.contenedor.classList.add('tabla-alternativa');
    this.contenedor.classList.toggle(
      'tabla-apilable',
      this.columnas.length >= 3,
    );
    this.contenedor.innerHTML = `
      <div tabindex="0" role="region" aria-label="${textoSeguro(this.caption)}" class="tabla-alternativa-region mt-2 max-h-64 overflow-y-auto overflow-x-auto rounded-lg border border-border">
        <table class="w-full border-collapse text-left font-sans">
          <caption class="sr-only">${textoSeguro(this.caption)}</caption>
          <thead class="sticky top-0 bg-surface border-b border-border">
            <tr>${encabezadosHtml}</tr>
          </thead>
          <tbody>
            ${filasHtml}
          </tbody>
        </table>
      </div>
      ${avisoLimite}
    `;
  }
}
