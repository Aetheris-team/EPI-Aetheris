import { textoAlcance } from './alcance-alertas';

export const AVISO_HONESTIDAD_ALERTAS_INTRO =
  'Alertas redactadas por el equipo de vigilancia del proyecto (INSAMT, Equipo 4) a partir de datos públicos históricos (MINSAL, OpenDengue, Open-Meteo).';

export const AVISO_HONESTIDAD_ALERTAS_CLINICO =
  'No reemplazan los lineamientos del MINSAL ni el criterio clínico.';

export const AVISO_HONESTIDAD_ALERTAS = `${AVISO_HONESTIDAD_ALERTAS_INTRO} ${AVISO_HONESTIDAD_ALERTAS_CLINICO}`;

export const TIPOS_ALERTA = ['dengue', 'respiratorio'] as const;
export type TipoAlerta = (typeof TIPOS_ALERTA)[number];

export const ETIQUETAS_TIPO: Record<TipoAlerta, string> = {
  dengue: 'Dengue',
  respiratorio: 'Respiratorio',
};

export const NIVELES_ALERTA = [
  'informativo',
  'atencion',
  'intensificacion',
] as const;
export type NivelAlerta = (typeof NIVELES_ALERTA)[number];

export const ETIQUETAS_NIVEL: Record<NivelAlerta, string> = {
  informativo: 'Informativo',
  atencion: 'Atención',
  intensificacion: 'Intensificación',
};

/** Significado operativo de cada nivel (INDICACIONES_ALERTAS.md §4). */
export const SIGNIFICADO_NIVEL: Record<NivelAlerta, string> = {
  informativo:
    'Sin señal relevante en los datos. Recordatorio de vigilancia rutinaria.',
  atencion:
    'Los datos históricos recientes están por encima de lo esperado para la época. Reforzar notificación y búsqueda de casos.',
  intensificacion:
    'Señal sostenida varias semanas y/o concentración territorial. Activar medidas locales y coordinar con SIBASI.',
};

export function esNivelAlerta(valor: string): valor is NivelAlerta {
  return (NIVELES_ALERTA as readonly string[]).includes(valor);
}

export function textoSignificadoNivel(nivel: string): string {
  return esNivelAlerta(nivel) ? SIGNIFICADO_NIVEL[nivel] : '';
}

export const ROTULO_ALERTA_PRUEBA =
  'ALERTA DE PRUEBA — NO ACTUAR SOBRE ESTA INFORMACIÓN';

export interface AlertaPublica {
  id: number;
  tipo: TipoAlerta;
  nivel: string;
  titulo: string;
  contexto: string;
  indicaciones: string;
  fuente: string;
  autor: string;
  vigente_desde: string;
  vigente_hasta: string | null;
  activa: boolean;
  etiqueta?: string | null;
  /** ADR 0022: null o ausente = nacional; lista de códigos ISO 3166-2 = regional. */
  departamentos?: string[] | null;
  // Campos clínicos opcionales (ADR 0014). El equipo los redacta a mano con
  // fuente MINSAL/OPS; null = el bloque no se muestra.
  signos_alarma?: string | null;
  criterios_referencia?: string | null;
  que_notificar?: string | null;
  definicion_caso?: string | null;
  contacto_vigilancia?: string | null;
}

// Campos clínicos opcionales, en el orden en que se muestran en la tarjeta.
export const CAMPOS_CLINICOS: ReadonlyArray<{
  clave: keyof AlertaPublica;
  etiqueta: string;
}> = [
  { clave: 'definicion_caso', etiqueta: 'Definición de caso' },
  { clave: 'signos_alarma', etiqueta: 'Signos de alarma' },
  { clave: 'criterios_referencia', etiqueta: 'Criterios de referencia' },
  { clave: 'que_notificar', etiqueta: 'Qué notificar' },
  { clave: 'contacto_vigilancia', etiqueta: 'A quién contactar (SIBASI)' },
];

export interface PayloadAlertas {
  aviso: string;
  ultima_revision: string | null;
  alertas: AlertaPublica[];
}

export type VistaAlertas =
  | { tipo: 'vacio'; texto: string }
  | { tipo: 'lista'; alertas: AlertaPublica[] };

export function textoEstadoVacio(fechaDdMmAaaa: string): string {
  return `No hay alertas activas. Última revisión del equipo: ${fechaDdMmAaaa}.`;
}

export function formatearFechaIso(iso: string | null | undefined): string {
  if (!iso) return '';
  const parte = iso.slice(0, 10);
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(parte);
  if (!match) return iso;
  return `${match[3]}/${match[2]}/${match[1]}`;
}

export function vistaDeAlertas(
  alertas: AlertaPublica[],
  ultimaRevisionIso: string | null,
  textoVacio?: string,
): VistaAlertas {
  if (alertas.length === 0) {
    if (textoVacio) return { tipo: 'vacio', texto: textoVacio };
    const fecha = formatearFechaIso(ultimaRevisionIso) || '—';
    return { tipo: 'vacio', texto: textoEstadoVacio(fecha) };
  }
  return { tipo: 'lista', alertas };
}

export function rutaModulo(tipo: TipoAlerta): string {
  return tipo === 'respiratorio' ? '/respiratorio' : '/dengue';
}

export function escapeHtml(texto: string): string {
  return texto
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function renderTextoAccionable(texto: string): string {
  const lineas = texto.replace(/\r\n/g, '\n').split('\n');
  const partes: string[] = [];
  let items: string[] = [];

  const vaciarLista = () => {
    if (items.length === 0) return;
    partes.push(
      `<ul class="list-disc space-y-1 pl-5">${items.map((item) => `<li>${item}</li>`).join('')}</ul>`,
    );
    items = [];
  };

  for (const cruda of lineas) {
    const item = /^\s*-\s+(.+)$/.exec(cruda);
    if (item) {
      items.push(escapeHtml(item[1]));
      continue;
    }
    vaciarLista();
    const recortada = cruda.trim();
    if (!recortada) continue;
    partes.push(`<p>${escapeHtml(recortada)}</p>`);
  }
  vaciarLista();
  return partes.join('');
}

export function textoVigencia(alerta: AlertaPublica): string {
  const desde = formatearFechaIso(alerta.vigente_desde);
  if (alerta.vigente_hasta) {
    return `Vigencia: ${desde} – ${formatearFechaIso(alerta.vigente_hasta)}`;
  }
  return `Vigencia: desde ${desde} (sin fecha de cierre)`;
}

export function alertaEstaVigente(
  alerta: AlertaPublica,
  hoyIso?: string,
): boolean {
  if (!alerta.activa) return false;
  if (!alerta.vigente_hasta) return true;
  const hoy = hoyIso ?? new Date().toISOString().slice(0, 10);
  return alerta.vigente_hasta.slice(0, 10) >= hoy;
}

export function textoNoVigente(
  alerta: AlertaPublica,
  hoyIso?: string,
): string | null {
  if (alertaEstaVigente(alerta, hoyIso)) return null;
  const fin = alerta.vigente_hasta || alerta.vigente_desde;
  return `NO VIGENTE — venció el ${formatearFechaIso(fin)}`;
}

export function esAlertaEtiquetada(alerta: AlertaPublica): boolean {
  return typeof alerta.etiqueta === 'string' && alerta.etiqueta.trim() !== '';
}

function svgIcono(nombre: string, clase = 'h-4 w-4'): string {
  switch (nombre) {
    case 'bug':
      return `<svg class="${clase}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 9v-1a3 3 0 0 1 6 0v1"></path><path d="M8 9h8a6 6 0 0 1 1 3v3a5 5 0 0 1 -10 0v-3a6 6 0 0 1 1 -3"></path><path d="M3 13l4 0"></path><path d="M17 13l4 0"></path><path d="M12 20l0 -6"></path><path d="M4 19l3.35 -2"></path><path d="M20 19l-3.35 -2"></path><path d="M4 7l3.75 1.5"></path><path d="M20 7l-3.75 1.5"></path></svg>`;
    case 'lungs':
      return `<svg class="${clase}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 12m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"></path><path d="M12 3v9"></path><path d="M7 11c-2.5 0 -4.5 2 -4.5 4.5c0 3.5 2.5 5.5 5.5 5.5c2 0 3 -1 3.5 -2.5"></path><path d="M17 11c2.5 0 4.5 2 4.5 4.5c0 3.5 -2.5 5.5 -5.5 5.5c-2 0 -3 -1 -3.5 -2.5"></path></svg>`;
    case 'calendar':
      return `<svg class="${clase}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2v-12z"></path><path d="M16 3v4"></path><path d="M8 3v4"></path><path d="M4 11h16"></path><path d="M11 15h1"></path><path d="M12 15v3"></path></svg>`;
    case 'clock':
      return `<svg class="${clase}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"></path><path d="M12 7v5l3 3"></path></svg>`;
    case 'map-pin':
      return `<svg class="${clase}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 11a3 3 0 1 0 6 0a3 3 0 0 0 -6 0"></path><path d="M17.657 16.657l-4.243 4.243a2 2 0 0 1 -2.827 0l-4.244 -4.243a8 8 0 1 1 11.314 0z"></path></svg>`;
    case 'shield-alert':
      return `<svg class="${clase}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3a12 12 0 0 0 8.5 3a12 12 0 0 1 -8.5 15a12 12 0 0 1 -8.5 -15a12 12 0 0 0 8.5 -3"></path><path d="M12 8v4"></path><path d="M12 16h.01"></path></svg>`;
    case 'alert-triangle':
      return `<svg class="${clase}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 9v4"></path><path d="M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636 -2.87l-8.106 -13.536a1.914 1.914 0 0 0 -3.274 0z"></path><path d="M12 16h.01"></path></svg>`;
    case 'info-circle':
      return `<svg class="${clase}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"></path><path d="M12 9h.01"></path><path d="M11 12h1v4h1"></path></svg>`;
    case 'share':
      return `<svg class="${clase}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0 -6 0"></path><path d="M18 6m-3 0a3 3 0 1 0 6 0a3 3 0 1 0 -6 0"></path><path d="M18 18m-3 0a3 3 0 1 0 6 0a3 3 0 1 0 -6 0"></path><path d="M8.7 10.7l6.6 -3.4"></path><path d="M8.7 13.3l6.6 3.4"></path></svg>`;
    case 'check':
      return `<svg class="${clase}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5l10 -10"></path></svg>`;
    case 'arrow-right':
      return `<svg class="${clase}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l14 0"></path><path d="M13 18l6 -6"></path><path d="M13 6l6 6"></path></svg>`;
    case 'stethoscope':
      return `<svg class="${clase}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 4h-1a2 2 0 0 0 -2 2v3.5h0a5.5 5.5 0 0 0 11 0v-3.5a2 2 0 0 0 -2 -2h-1"></path><path d="M8 15a6 6 0 0 0 12 0v-3"></path><path d="M11 3v2"></path><path d="M6 3v2"></path><circle cx="20" cy="10" r="2"></circle></svg>`;
    case 'clipboard-list':
      return `<svg class="${clase}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 5h-2a2 2 0 0 0 -2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-12a2 2 0 0 0 -2 -2h-2"></path><path d="M9 3m0 2a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2v0a2 2 0 0 1 -2 2h-2a2 2 0 0 1 -2 -2z"></path><path d="M9 12h6"></path><path d="M9 16h6"></path></svg>`;
    case 'chevron-down':
      return `<svg class="${clase}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6l6 -6"></path></svg>`;
    default:
      return '';
  }
}

function pintarTarjeta(
  alerta: AlertaPublica,
  esNueva = false,
  indice = 0,
  animar = true,
): HTMLElement {
  const articulo = document.createElement('article');

  // Borde y acento jerárquico según el nivel de alerta
  const estiloNivel =
    alerta.nivel === 'intensificacion'
      ? 'border-l-4 border-l-red-500 bg-surface'
      : alerta.nivel === 'atencion'
        ? 'border-l-4 border-l-amber-500 bg-surface'
        : 'border-l-4 border-l-accent bg-surface';

  articulo.className = `card-elevated rounded-2xl border border-border ${estiloNivel} p-5 sm:p-7 shadow-sm transition-all duration-300 hover:shadow-md hover:-translate-y-0.5 relative`;
  if (animar) {
    articulo.style.animation =
      'panel-entra 380ms cubic-bezier(0.16, 1, 0.3, 1) both';
    articulo.style.animationDelay = `${indice * 60}ms`;
  }

  articulo.setAttribute('data-alerta', '');
  articulo.setAttribute('data-tipo', alerta.tipo);
  articulo.setAttribute('data-nivel', alerta.nivel);
  articulo.id = `alerta-${alerta.id}`;
  if (esAlertaEtiquetada(alerta)) {
    articulo.setAttribute('data-alerta-etiqueta', String(alerta.etiqueta));
  }
  if (!alertaEstaVigente(alerta)) {
    articulo.setAttribute('data-alerta-no-vigente-tarjeta', '');
  }

  if (esAlertaEtiquetada(alerta)) {
    const avisoPrueba = document.createElement('p');
    avisoPrueba.setAttribute('data-alerta-prueba', '');
    avisoPrueba.className =
      'mb-4 rounded-xl border-2 border-secondary bg-secondary px-3.5 py-2 font-sans text-sm font-bold uppercase tracking-wide text-secondary-ink flex items-center gap-2 shadow-xs';
    avisoPrueba.innerHTML = `${svgIcono('alert-triangle', 'h-5 w-5 text-secondary-ink shrink-0')}<span>${ROTULO_ALERTA_PRUEBA}</span>`;
    articulo.appendChild(avisoPrueba);
  }

  const avisoNoVigente = textoNoVigente(alerta);
  if (avisoNoVigente) {
    const avisoVencida = document.createElement('p');
    avisoVencida.setAttribute('data-alerta-no-vigente', '');
    avisoVencida.className =
      'mb-4 rounded-xl border-2 border-ink bg-bg px-3.5 py-2 font-sans text-sm font-bold uppercase tracking-wide text-ink flex items-center gap-2';
    avisoVencida.innerHTML = `${svgIcono('clock', 'h-5 w-5 text-ink-muted shrink-0')}<span>${escapeHtml(avisoNoVigente)}</span>`;
    articulo.appendChild(avisoVencida);
  }

  const tipo = ETIQUETAS_TIPO[alerta.tipo] ?? alerta.tipo;
  const nivel = esNivelAlerta(alerta.nivel)
    ? ETIQUETAS_NIVEL[alerta.nivel]
    : alerta.nivel;
  const significadoNivel = textoSignificadoNivel(alerta.nivel);
  const modulo = rutaModulo(alerta.tipo);

  // Icono para tipo
  const iconoTipo =
    alerta.tipo === 'respiratorio'
      ? svgIcono('lungs', 'h-3.5 w-3.5 text-accent')
      : svgIcono('bug', 'h-3.5 w-3.5 text-accent');

  // Icono y color para nivel
  const iconoNivel =
    alerta.nivel === 'intensificacion'
      ? svgIcono('shield-alert', 'h-3.5 w-3.5 text-white')
      : alerta.nivel === 'atencion'
        ? svgIcono('alert-triangle', 'h-3.5 w-3.5 text-white')
        : svgIcono('info-circle', 'h-3.5 w-3.5 text-white');

  const clasePillNivel =
    alerta.nivel === 'intensificacion'
      ? 'bg-red-600 text-white border-red-600'
      : alerta.nivel === 'atencion'
        ? 'bg-amber-700 text-white border-amber-700'
        : 'bg-teal-700 text-white border-teal-700';

  const encabezado = document.createElement('header');
  encabezado.innerHTML = `
    <div class="flex flex-wrap items-center gap-2 text-xs">
      <span class="inline-flex items-center gap-1.5 rounded-full border border-border bg-bg px-2.5 py-1 font-sans font-semibold uppercase tracking-wider text-accent shadow-2xs">
        ${iconoTipo}
        <span data-alerta-tipo>${escapeHtml(tipo)}</span>
      </span>
      <span class="inline-flex items-center gap-1.5 rounded-full border ${clasePillNivel} px-2.5 py-1 font-sans font-semibold uppercase tracking-wider shadow-2xs">
        ${iconoNivel}
        <span data-alerta-nivel>${escapeHtml(nivel)}</span>
      </span>
      ${
        esNueva
          ? `<span data-alerta-nueva class="inline-flex items-center gap-1.5 rounded-full bg-accent px-2.5 py-1 font-sans text-[11px] font-semibold text-accent-ink shadow-2xs">
              <span class="relative flex h-2 w-2">
                <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
                <span class="relative inline-flex rounded-full h-2 w-2 bg-white"></span>
              </span>
              Nueva
            </span>`
          : ''
      }
    </div>
    ${
      significadoNivel
        ? `<p class="mt-2.5 font-sans text-sm text-ink-muted leading-relaxed" data-alerta-nivel-significado>${escapeHtml(significadoNivel)}</p>`
        : ''
    }
    <h2 class="mt-2.5 font-display text-xl sm:text-2xl font-semibold tracking-tight text-ink" data-alerta-titulo></h2>
    <div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 font-sans text-xs text-ink-muted">
      <span class="inline-flex items-center gap-1.5">
        ${svgIcono('calendar', 'h-3.5 w-3.5 text-accent/80')}
        <span>Emisión: <time data-alerta-emision datetime="${escapeHtml(alerta.vigente_desde)}">${escapeHtml(formatearFechaIso(alerta.vigente_desde))}</time></span>
      </span>
      <span class="text-border">·</span>
      <span class="inline-flex items-center gap-1.5">
        ${svgIcono('clock', 'h-3.5 w-3.5 text-accent/80')}
        <span data-alerta-vigencia>${escapeHtml(textoVigencia(alerta))}</span>
      </span>
      <span class="text-border">·</span>
      <span class="inline-flex items-center gap-1.5">
        ${svgIcono('map-pin', 'h-3.5 w-3.5 text-accent/80')}
        <span>Alcance: <span data-alerta-alcance>${escapeHtml(textoAlcance(alerta))}</span></span>
      </span>
    </div>
  `;
  const titulo = encabezado.querySelector('[data-alerta-titulo]');
  if (titulo) titulo.textContent = alerta.titulo;
  articulo.appendChild(encabezado);

  const contexto = document.createElement('section');
  contexto.className =
    'mt-4 rounded-xl border border-border/80 bg-bg/50 p-4 font-sans text-sm leading-relaxed text-ink';
  contexto.setAttribute('data-alerta-contexto', '');
  contexto.innerHTML = renderTextoAccionable(alerta.contexto);
  articulo.appendChild(contexto);

  const indicaciones = document.createElement('section');
  indicaciones.className =
    'mt-4 rounded-xl border border-accent/25 bg-accent/5 p-4 sm:p-5 font-sans text-sm leading-relaxed text-ink shadow-2xs';
  indicaciones.setAttribute('data-alerta-indicaciones', '');
  const hInd = document.createElement('h3');
  hInd.className =
    'font-sans text-sm font-semibold text-ink flex items-center gap-2';
  hInd.innerHTML = `${svgIcono('stethoscope', 'h-4 w-4 text-accent')}<span>Indicaciones para la unidad</span>`;
  indicaciones.appendChild(hInd);
  const cuerpoInd = document.createElement('div');
  cuerpoInd.className = 'mt-2.5 space-y-2';
  cuerpoInd.innerHTML = renderTextoAccionable(alerta.indicaciones);
  indicaciones.appendChild(cuerpoInd);
  articulo.appendChild(indicaciones);

  // Campos clínicos opcionales (ADR 0014): cada uno solo aparece si el equipo
  // ya lo llenó. Plegados por defecto para no alargar la tarjeta en consulta.
  for (const { clave, etiqueta } of CAMPOS_CLINICOS) {
    const valor = alerta[clave];
    if (typeof valor !== 'string' || valor.trim() === '') continue;
    const bloque = document.createElement('details');
    bloque.className =
      'group mt-3 rounded-xl border border-border bg-bg/75 px-4 py-2.5 font-sans text-sm text-ink transition-colors hover:border-accent/40';
    bloque.setAttribute('data-alerta-clinico', String(clave));
    const resumen = document.createElement('summary');
    resumen.className =
      'cursor-pointer py-1 font-semibold flex items-center justify-between gap-2 select-none';
    resumen.innerHTML = `
      <span class="inline-flex items-center gap-2">
        ${svgIcono('clipboard-list', 'h-4 w-4 text-accent/80')}
        <span>${escapeHtml(etiqueta)}</span>
      </span>
      <span class="text-ink-muted transition-transform duration-200 group-open:rotate-180">
        ${svgIcono('chevron-down', 'h-4 w-4')}
      </span>
    `;
    bloque.appendChild(resumen);
    const cuerpo = document.createElement('div');
    cuerpo.className =
      'mb-2 mt-2.5 space-y-2 leading-relaxed border-t border-border/70 pt-2.5';
    cuerpo.innerHTML = renderTextoAccionable(valor);
    bloque.appendChild(cuerpo);
    articulo.appendChild(bloque);
  }

  const meta = document.createElement('div');
  meta.className =
    'mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-border/60 bg-bg/40 px-3 py-2 font-sans text-xs leading-relaxed text-ink-muted';
  meta.innerHTML = `
    <span>Fuente: <strong data-alerta-fuente class="text-ink font-medium"></strong></span>
    <span class="text-border">·</span>
    <span>Autor: <strong data-alerta-autor class="text-ink font-medium"></strong></span>
  `;
  const fuenteNodo = meta.querySelector('[data-alerta-fuente]');
  const autorNodo = meta.querySelector('[data-alerta-autor]');
  if (fuenteNodo) fuenteNodo.textContent = alerta.fuente;
  if (autorNodo) autorNodo.textContent = alerta.autor;
  articulo.appendChild(meta);

  const acciones = document.createElement('div');
  acciones.className =
    'mt-5 flex flex-wrap items-center gap-3 border-t border-border/70 pt-4';
  acciones.setAttribute('data-alerta-acciones', '');

  const enlace = document.createElement('a');
  enlace.href = modulo;
  enlace.setAttribute('data-enlace-modulo', alerta.tipo);
  enlace.className =
    'inline-flex items-center gap-2 rounded-full border border-accent bg-accent px-4 py-2 font-sans text-xs sm:text-sm font-semibold text-accent-ink transition-all hover:opacity-90 hover:-translate-y-0.5 active:translate-y-0 shadow-xs';
  enlace.innerHTML = `
    <span>Ver datos que motivaron esta alerta (${escapeHtml(tipo.toLowerCase())})</span>
    ${svgIcono('arrow-right', 'h-4 w-4')}
  `;
  enlace.setAttribute(
    'aria-label',
    `Ver datos que motivaron la alerta: ${alerta.titulo}`,
  );
  acciones.appendChild(enlace);

  // Compartir: navigator.share donde exista (móvil), copiar enlace si no.
  // El enlace apunta al ancla de esta alerta dentro de /alertas.
  const compartir = document.createElement('button');
  compartir.type = 'button';
  compartir.setAttribute('data-alerta-compartir', String(alerta.id));
  compartir.setAttribute('aria-label', `Compartir alerta: ${alerta.titulo}`);
  compartir.className =
    'inline-flex items-center gap-2 rounded-full border border-border bg-surface px-4 py-2 font-sans text-xs sm:text-sm font-medium text-ink transition-all hover:border-accent/40 hover:bg-bg print:hidden shadow-2xs';
  compartir.innerHTML = `
    <span class="shrink-0 text-accent">${svgIcono('share', 'h-4 w-4')}</span>
    <span class="texto-compartir-btn">Compartir</span>
  `;
  const anuncioCompartir = document.createElement('p');
  anuncioCompartir.className = 'sr-only';
  anuncioCompartir.setAttribute('role', 'status');
  anuncioCompartir.setAttribute('aria-live', 'polite');
  compartir.addEventListener('click', () => {
    void compartirAlerta(alerta, compartir, anuncioCompartir);
  });
  acciones.appendChild(compartir);
  acciones.appendChild(anuncioCompartir);

  articulo.appendChild(acciones);

  return articulo;
}

export function enlaceDeAlerta(alerta: AlertaPublica): string {
  if (typeof window === 'undefined') return `/alertas#alerta-${alerta.id}`;
  return `${window.location.origin}/alertas?tipo=${encodeURIComponent(alerta.tipo)}#alerta-${alerta.id}`;
}

async function compartirAlerta(
  alerta: AlertaPublica,
  boton: HTMLButtonElement,
  anuncio: HTMLElement,
): Promise<void> {
  const url = enlaceDeAlerta(alerta);
  const nav = navigator as Navigator & {
    share?: (datos: {
      title: string;
      text: string;
      url: string;
    }) => Promise<void>;
  };
  if (typeof nav.share === 'function') {
    try {
      await nav.share({ title: alerta.titulo, text: alerta.titulo, url });
      return;
    } catch {
      // Cancelado por la persona o no permitido: se cae al copiado.
    }
  }
  const htmlOriginal = boton.innerHTML;
  try {
    await navigator.clipboard.writeText(url);
    boton.innerHTML = `
      <span class="shrink-0 text-emerald-600">${svgIcono('check', 'h-4 w-4')}</span>
      <span class="font-semibold text-emerald-700 dark:text-emerald-400">Enlace copiado</span>
    `;
    boton.classList.add('border-emerald-500/50', 'bg-emerald-500/10');
    anuncio.textContent = 'Enlace copiado al portapapeles.';
  } catch {
    boton.textContent = 'No se pudo copiar';
    anuncio.textContent = 'No se pudo copiar el enlace.';
  }
  window.setTimeout(() => {
    boton.innerHTML = htmlOriginal;
    boton.classList.remove('border-emerald-500/50', 'bg-emerald-500/10');
  }, 2500);
}

const CLAVE_VISTAS = 'epi-aetheris:alertas-vistas';

/** Ids de alertas que esta persona ya vio en este navegador. */
export function leerAlertasVistas(): Set<number> {
  try {
    const crudo = window.localStorage.getItem(CLAVE_VISTAS);
    if (!crudo) return new Set();
    const datos: unknown = JSON.parse(crudo);
    if (!Array.isArray(datos)) return new Set();
    return new Set(datos.filter((v): v is number => typeof v === 'number'));
  } catch {
    // Modo privado, almacenamiento bloqueado o JSON corrupto: sin historial,
    // todo se considera visto para no marcar todo como "Nueva" en falso.
    return new Set();
  }
}

export function guardarAlertasVistas(ids: Iterable<number>): void {
  try {
    window.localStorage.setItem(
      CLAVE_VISTAS,
      JSON.stringify([...new Set(ids)]),
    );
  } catch {
    // Sin almacenamiento la vista sigue funcionando; solo se pierde el "Nueva".
  }
}

/**
 * Marca como nuevas solo si ya había historial guardado. La primera visita
 * no marca nada: sin referencia previa, "nueva" no significa nada.
 */
export function calcularNuevas(
  alertas: AlertaPublica[],
  vistas: Set<number>,
): Set<number> {
  if (vistas.size === 0) return new Set();
  return new Set(alertas.filter((a) => !vistas.has(a.id)).map((a) => a.id));
}

export function despacharEventoAlertas(alertas: AlertaPublica[]): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent('alertas:actualizadas', {
      detail: {
        alertas,
        total: alertas.length,
        dengue: alertas.filter((a) => a.tipo === 'dengue').length,
        respiratorio: alertas.filter((a) => a.tipo === 'respiratorio').length,
        intensificacion: alertas.filter((a) => a.nivel === 'intensificacion')
          .length,
        atencion: alertas.filter((a) => a.nivel === 'atencion').length,
        informativo: alertas.filter((a) => a.nivel === 'informativo').length,
      },
    }),
  );
}

export function aplicarVistaAlertas(
  root: HTMLElement,
  payload: PayloadAlertas,
  nuevas: Set<number> = new Set(),
  textoVacio?: string,
  animar = true,
): void {
  const carga = root.querySelector<HTMLElement>('[data-alertas-carga]');
  const error = root.querySelector<HTMLElement>('[data-alertas-error]');
  const vacio = root.querySelector<HTMLElement>('[data-alertas-vacio]');
  const lista = root.querySelector<HTMLElement>('[data-alertas-lista]');
  if (carga) carga.hidden = true;
  if (error) error.hidden = true;

  const vista = vistaDeAlertas(
    payload.alertas,
    payload.ultima_revision,
    textoVacio,
  );
  if (vista.tipo === 'vacio') {
    if (vacio) {
      vacio.hidden = false;
      vacio.textContent = vista.texto;
    }
    if (lista) {
      lista.hidden = true;
      lista.replaceChildren();
    }
    root.setAttribute('data-cargado', '1');
    root.setAttribute('data-estado', 'vacio');
    despacharEventoAlertas(payload.alertas);
    return;
  }

  if (vacio) {
    vacio.hidden = true;
    vacio.textContent = '';
  }
  if (lista) {
    lista.hidden = false;
    lista.replaceChildren(
      ...vista.alertas.map((a, i) =>
        pintarTarjeta(a, nuevas.has(a.id), i, animar),
      ),
    );
  }
  root.setAttribute('data-cargado', '1');
  root.setAttribute('data-estado', 'lista');
  despacharEventoAlertas(payload.alertas);
}

export type PintarAlertas = (payload: PayloadAlertas) => void;
