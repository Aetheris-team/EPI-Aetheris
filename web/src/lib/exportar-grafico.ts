// Exportar gráficos de ECharts (renderer SVG) como SVG o PNG (F6.3).
// Un SVG descargado pierde las variables CSS de la página (`var(--…)`), así
// que se resuelven con getComputedStyle sobre el original antes de guardar.
// Los mapas vectoriales SVG gestionan su propia exportación directa e independiente.

export interface OpcionesExportacion {
  titulo: string;
  fuente: string;
  /** Texto de los filtros activos, p. ej. «San Salvador · 2023 · probable». */
  filtros?: string;
  fecha?: Date;
  /** Nombre base del archivo, sin extensión. */
  nombreArchivo?: string;
}

const ESPACIO_LINEA = 16;
const MARGEN_PIE = 12;
const FUENTE_RESPALDO = "Inter, system-ui, 'Segoe UI', sans-serif";

/** Líneas de texto del pie que acompaña al gráfico exportado. */
export function lineasDelPie(opciones: OpcionesExportacion): string[] {
  const fecha = (opciones.fecha ?? new Date()).toISOString().slice(0, 10);
  const lineas = [opciones.titulo];
  if (opciones.filtros) lineas.push(`Filtros: ${opciones.filtros}`);
  lineas.push(`Fuente: ${opciones.fuente}`);
  lineas.push(`Generado el ${fecha} desde EPI-Aetheris`);
  return lineas;
}

/** Nombre de archivo sin tildes ni caracteres que un sistema de archivos rechace. */
export function nombreArchivoSeguro(texto: string): string {
  const base = texto
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return base || 'grafico';
}

const PROPIEDADES_RESUELTAS = [
  'fill',
  'stroke',
  'color',
  'font-family',
  'font-size',
  'stroke-width',
  'stroke-opacity',
  'fill-opacity',
] as const;

function usaVariable(el: Element): boolean {
  if (el.getAttribute('style')?.includes('var(')) return true;
  return Array.from(el.attributes).some(
    (a) => a.value.includes('var(') || a.value === 'currentColor',
  );
}

function resolverVariables(original: SVGSVGElement, copia: SVGSVGElement) {
  const origen = [original, ...Array.from(original.querySelectorAll('*'))];
  const destino = [copia, ...Array.from(copia.querySelectorAll('*'))];
  origen.forEach((nodo, i) => {
    const clon = destino[i] as SVGElement | undefined;
    if (!clon || !usaVariable(clon)) return;
    const calculado = getComputedStyle(nodo);
    for (const propiedad of PROPIEDADES_RESUELTAS) {
      const valor = calculado.getPropertyValue(propiedad);
      if (valor) clon.style.setProperty(propiedad, valor);
    }
    // Un atributo con var() no sirve fuera de la página: manda el estilo en línea.
    for (const atributo of ['fill', 'stroke']) {
      if (clon.getAttribute(atributo)?.includes('var(')) {
        clon.removeAttribute(atributo);
      }
    }
  });
  const raiz = copia.style;
  raiz.setProperty('font-family', FUENTE_RESPALDO);
}

function medidas(svg: SVGSVGElement): { ancho: number; alto: number } {
  const caja = svg.getBoundingClientRect();
  const vista = svg.viewBox.baseVal;
  const ancho =
    Number(svg.getAttribute('width')) || vista?.width || caja.width || 640;
  const alto =
    Number(svg.getAttribute('height')) || vista?.height || caja.height || 320;
  return { ancho, alto };
}

/** Copia autónoma del SVG con fondo, variables resueltas y el pie de fuente. */
export function prepararSvg(
  svg: SVGSVGElement,
  opciones: OpcionesExportacion,
): { nodo: SVGSVGElement; ancho: number; alto: number } {
  const copia = svg.cloneNode(true) as SVGSVGElement;
  resolverVariables(svg, copia);
  const { ancho, alto } = medidas(svg);
  const lineas = lineasDelPie(opciones);
  const altoPie = lineas.length * ESPACIO_LINEA + MARGEN_PIE * 2;
  const altoTotal = alto + altoPie;
  const NS = 'http://www.w3.org/2000/svg';

  // Los SVG con viewBox se ajustan a su contenedor con estilo en línea; fuera
  // de la página ese porcentaje no significa nada.
  copia.style.removeProperty('width');
  copia.style.removeProperty('height');
  copia.setAttribute('xmlns', NS);
  copia.setAttribute('width', String(ancho));
  copia.setAttribute('height', String(altoTotal));
  copia.setAttribute('viewBox', `0 0 ${ancho} ${altoTotal}`);

  const fondo = document.createElementNS(NS, 'rect');
  fondo.setAttribute('width', String(ancho));
  fondo.setAttribute('height', String(altoTotal));
  fondo.setAttribute('fill', '#ffffff');
  copia.insertBefore(fondo, copia.firstChild);

  const pie = document.createElementNS(NS, 'g');
  pie.setAttribute('font-family', FUENTE_RESPALDO);
  pie.setAttribute('font-size', '11');
  pie.setAttribute('fill', '#3f3f46');
  lineas.forEach((linea, i) => {
    const texto = document.createElementNS(NS, 'text');
    texto.setAttribute('x', '12');
    texto.setAttribute(
      'y',
      String(alto + MARGEN_PIE + (i + 1) * ESPACIO_LINEA),
    );
    if (i === 0) texto.setAttribute('font-weight', '600');
    texto.textContent = linea;
    pie.appendChild(texto);
  });
  copia.appendChild(pie);
  return { nodo: copia, ancho, alto: altoTotal };
}

function descargar(blob: Blob, nombre: string): void {
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement('a');
  enlace.href = url;
  enlace.download = nombre;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function nombreBase(opciones: OpcionesExportacion): string {
  return opciones.nombreArchivo ?? nombreArchivoSeguro(opciones.titulo);
}

export function exportarSvg(
  svg: SVGSVGElement,
  opciones: OpcionesExportacion,
): void {
  const { nodo } = prepararSvg(svg, opciones);
  const texto = new XMLSerializer().serializeToString(nodo);
  descargar(
    new Blob([texto], { type: 'image/svg+xml;charset=utf-8' }),
    `${nombreBase(opciones)}.svg`,
  );
}

export async function exportarPng(
  svg: SVGSVGElement,
  opciones: OpcionesExportacion,
  escala = 2,
): Promise<void> {
  const { nodo, ancho, alto } = prepararSvg(svg, opciones);
  const texto = new XMLSerializer().serializeToString(nodo);
  const url = URL.createObjectURL(
    new Blob([texto], { type: 'image/svg+xml;charset=utf-8' }),
  );
  try {
    const imagen = new Image();
    await new Promise<void>((resolver, rechazar) => {
      imagen.onload = () => resolver();
      imagen.onerror = () =>
        rechazar(new Error('No se pudo rasterizar el SVG'));
      imagen.src = url;
    });
    const lienzo = document.createElement('canvas');
    lienzo.width = Math.round(ancho * escala);
    lienzo.height = Math.round(alto * escala);
    const contexto = lienzo.getContext('2d');
    if (!contexto) throw new Error('El navegador no ofrece canvas 2D');
    contexto.scale(escala, escala);
    contexto.drawImage(imagen, 0, 0, ancho, alto);
    const blob = await new Promise<Blob | null>((r) =>
      lienzo.toBlob(r, 'image/png'),
    );
    if (!blob) throw new Error('No se pudo generar el PNG');
    descargar(blob, `${nombreBase(opciones)}.png`);
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Primer gráfico dentro de un contenedor: SVG de ECharts o SVG propio con role="img". */
export function encontrarGrafico(contenedor: ParentNode): SVGSVGElement | null {
  return contenedor.querySelector<SVGSVGElement>(
    'svg[role="img"]:not([aria-hidden="true"])',
  );
}
