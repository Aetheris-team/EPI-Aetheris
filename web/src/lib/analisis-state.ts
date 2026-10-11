import { DEPARTAMENTOS_POR_CODIGO } from './departamentos.ts';
import {
  aniosClimaPresentacion,
  type CapaAnalitica,
  type FiltrosAnalisis,
} from './tipos-analisis.ts';

export const EVENTO_FILTROS_ANALISIS = 'epi:filters-changed';

export const CAPAS_VALIDAS: readonly CapaAnalitica[] = [
  'minsal_volumen',
  'iv',
  'anomalia',
  'presion',
  'confianza',
] as const;

export const FILTROS_ANALISIS_PREDETERMINADOS: FiltrosAnalisis = {
  anio: 2023,
  semana: 1,
  semanaDesde: 1,
  semanaHasta: 53,
  serie: 'probable',
  departamento: null,
  comparar: [],
  modoMinsal: 'semana',
  capa: 'minsal_volumen',
};

function limitarSemana(valor: number): number {
  if (!Number.isFinite(valor)) return 1;
  return Math.min(53, Math.max(1, Math.trunc(valor)));
}

function esAnioDisponible(valor: number): boolean {
  return aniosClimaPresentacion().includes(valor);
}

function clonarEstado(valor: FiltrosAnalisis): FiltrosAnalisis {
  return { ...valor, comparar: [...valor.comparar] };
}

export function normalizarEstado(
  base: FiltrosAnalisis,
  cambios: Partial<FiltrosAnalisis>,
): FiltrosAnalisis {
  const candidato = { ...base, ...cambios };
  const semanaDesde = limitarSemana(candidato.semanaDesde);
  const semanaHasta = limitarSemana(candidato.semanaHasta);

  if (!esAnioDisponible(candidato.anio))
    candidato.anio = FILTROS_ANALISIS_PREDETERMINADOS.anio;
  candidato.semana = limitarSemana(candidato.semana);
  candidato.semanaDesde = Math.min(semanaDesde, semanaHasta);
  candidato.semanaHasta = Math.max(semanaDesde, semanaHasta);
  candidato.serie =
    candidato.serie === 'confirmado' ? 'confirmado' : 'probable';
  // La URL es entrada del visitante y estos valores terminan en rótulos y en
  // llamadas a la API: solo pasan los códigos de los 14 departamentos.
  const departamento = candidato.departamento?.trim() ?? '';
  candidato.departamento = DEPARTAMENTOS_POR_CODIGO[departamento]
    ? departamento
    : null;
  candidato.comparar = [
    ...new Set(candidato.comparar.filter((c) => DEPARTAMENTOS_POR_CODIGO[c])),
  ].slice(0, 4);
  candidato.modoMinsal = ['semana', 'ytd', 'historico'].includes(
    candidato.modoMinsal,
  )
    ? candidato.modoMinsal
    : 'semana';
  candidato.capa = CAPAS_VALIDAS.includes(candidato.capa)
    ? candidato.capa
    : 'minsal_volumen';
  return candidato;
}

function leerEstadoDesdeUrl(): Partial<FiltrosAnalisis> {
  if (typeof window === 'undefined') return {};
  const parametros = new URLSearchParams(window.location.search);
  const cambios: Partial<FiltrosAnalisis> = {};
  const anio = parametros.get('year');
  const semana = parametros.get('week');
  const semanaDesde = parametros.get('fromWeek');
  const semanaHasta = parametros.get('toWeek');
  const serie = parametros.get('serie');
  const departamento = parametros.get('dept');
  const comparar = parametros.get('compare');
  const modoMinsal = parametros.get('minsal');
  const capa = parametros.get('capa');
  if (anio !== null) cambios.anio = Number(anio);
  if (semana !== null) cambios.semana = Number(semana);
  if (semanaDesde !== null) cambios.semanaDesde = Number(semanaDesde);
  if (semanaHasta !== null) cambios.semanaHasta = Number(semanaHasta);
  if (serie === 'probable' || serie === 'confirmado') cambios.serie = serie;
  if (departamento !== null) cambios.departamento = departamento;
  if (comparar !== null) cambios.comparar = comparar.split(',');
  if (
    modoMinsal === 'semana' ||
    modoMinsal === 'ytd' ||
    modoMinsal === 'historico'
  ) {
    cambios.modoMinsal = modoMinsal;
  }
  if (capa && CAPAS_VALIDAS.includes(capa as CapaAnalitica)) {
    cambios.capa = capa as CapaAnalitica;
  }
  return cambios;
}

let timerSincronizarUrl: ReturnType<typeof setTimeout> | null = null;

function sincronizarUrl(filtros: FiltrosAnalisis, diferir = false): void {
  if (typeof window === 'undefined') return;
  const ruta = window.location.pathname;
  if (!ruta.startsWith('/dengue') && !ruta.startsWith('/analisis')) return;
  const ejecutar = () => {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('year', String(filtros.anio));
      url.searchParams.set('week', String(filtros.semana));
      url.searchParams.set('fromWeek', String(filtros.semanaDesde));
      url.searchParams.set('toWeek', String(filtros.semanaHasta));
      url.searchParams.set('serie', filtros.serie);
      url.searchParams.set('minsal', filtros.modoMinsal);
      if (filtros.capa && filtros.capa !== 'minsal_volumen') {
        url.searchParams.set('capa', filtros.capa);
      } else {
        url.searchParams.delete('capa');
      }
      if (filtros.departamento) {
        url.searchParams.set('dept', filtros.departamento);
      } else {
        url.searchParams.delete('dept');
      }
      if (filtros.comparar.length > 0) {
        url.searchParams.set('compare', filtros.comparar.join(','));
      } else {
        url.searchParams.delete('compare');
      }
      window.history.replaceState(null, '', url);
    } catch {
      // Ignorar SecurityError en navegadores con cuotas estrictas de replaceState (ej. Safari)
    }
  };

  if (diferir) {
    if (timerSincronizarUrl) clearTimeout(timerSincronizarUrl);
    timerSincronizarUrl = setTimeout(ejecutar, 200);
  } else {
    if (timerSincronizarUrl) {
      clearTimeout(timerSincronizarUrl);
      timerSincronizarUrl = null;
    }
    ejecutar();
  }
}

let estado = normalizarEstado(
  FILTROS_ANALISIS_PREDETERMINADOS,
  leerEstadoDesdeUrl(),
);
sincronizarUrl(estado);

function estadosIguales(a: FiltrosAnalisis, b: FiltrosAnalisis): boolean {
  return (
    a.anio === b.anio &&
    a.semana === b.semana &&
    a.semanaDesde === b.semanaDesde &&
    a.semanaHasta === b.semanaHasta &&
    a.serie === b.serie &&
    a.departamento === b.departamento &&
    a.modoMinsal === b.modoMinsal &&
    a.capa === b.capa &&
    a.comparar.length === b.comparar.length &&
    a.comparar.every((codigo, indice) => codigo === b.comparar[indice])
  );
}

export function obtenerFiltrosAnalisis(): FiltrosAnalisis {
  return clonarEstado(estado);
}

export function actualizarFiltrosAnalisis(
  cambios: Partial<FiltrosAnalisis>,
  opciones?: { diferirUrl?: boolean },
): FiltrosAnalisis {
  const siguiente = normalizarEstado(estado, cambios);
  if (estadosIguales(estado, siguiente)) return obtenerFiltrosAnalisis();

  estado = siguiente;
  const detalle = obtenerFiltrosAnalisis();
  if (typeof window !== 'undefined') {
    sincronizarUrl(detalle, opciones?.diferirUrl ?? false);
    window.dispatchEvent(
      new CustomEvent<FiltrosAnalisis>(EVENTO_FILTROS_ANALISIS, {
        detail: detalle,
      }),
    );
  }
  return detalle;
}

/**
 * Verdadero si `anterior` y `actual` difieren solo en la semana seleccionada.
 * Los componentes lo usan para actualizar la marca de semana con transición
 * en lugar de recrear la gráfica.
 */
export function soloCambiaSemana(
  anterior: FiltrosAnalisis | null,
  actual: FiltrosAnalisis,
): boolean {
  if (!anterior || anterior.semana === actual.semana) return false;
  return (
    JSON.stringify({ ...anterior, semana: 0 }) ===
    JSON.stringify({ ...actual, semana: 0 })
  );
}

export function restablecerFiltrosAnalisis(): FiltrosAnalisis {
  return actualizarFiltrosAnalisis(
    clonarEstado(FILTROS_ANALISIS_PREDETERMINADOS),
  );
}

export function suscribirFiltrosAnalisis(
  listener: (filtros: FiltrosAnalisis) => void,
  emitirInicial = true,
): () => void {
  if (emitirInicial) listener(obtenerFiltrosAnalisis());
  if (typeof window === 'undefined') return () => undefined;

  const manejarEvento = (evento: Event) => {
    listener(clonarEstado((evento as CustomEvent<FiltrosAnalisis>).detail));
  };
  window.addEventListener(EVENTO_FILTROS_ANALISIS, manejarEvento);
  return () =>
    window.removeEventListener(EVENTO_FILTROS_ANALISIS, manejarEvento);
}
