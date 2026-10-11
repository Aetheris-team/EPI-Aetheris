import { DEPARTAMENTOS_POR_CODIGO } from './departamentos.ts';

export const EVENTO_FILTROS_RESPIRATORIO = 'epi:respiratorio-changed';

/** Años con datos departamentales de IRA y neumonías (boletines, sin 2020). */
export const ANIOS_RESPIRATORIO = [2023, 2022, 2021, 2019, 2018] as const;
export const SEMANA_MAXIMA_RESPIRATORIO = 52;

export interface FiltrosRespiratorio {
  departamento: string;
  anio: number | 'todos';
  /** Departamento contra el que se compara la curva; null = ninguno. */
  comparar: string | null;
  semanaDesde: number;
  semanaHasta: number;
}

export const FILTROS_RESPIRATORIO_PREDETERMINADOS: FiltrosRespiratorio = {
  departamento: 'SV-SS',
  anio: 'todos',
  comparar: null,
  semanaDesde: 1,
  semanaHasta: SEMANA_MAXIMA_RESPIRATORIO,
};

function limitarSemana(valor: number): number {
  if (!Number.isFinite(valor)) return 1;
  return Math.min(SEMANA_MAXIMA_RESPIRATORIO, Math.max(1, Math.trunc(valor)));
}

/** Aplica cambios sobre una base y deja el resultado siempre válido. */
export function normalizarFiltrosRespiratorio(
  base: FiltrosRespiratorio,
  cambios: Partial<FiltrosRespiratorio>,
): FiltrosRespiratorio {
  const candidato = { ...base, ...cambios };
  const desde = limitarSemana(candidato.semanaDesde);
  const hasta = limitarSemana(candidato.semanaHasta);
  const departamento = DEPARTAMENTOS_POR_CODIGO[candidato.departamento]
    ? candidato.departamento
    : FILTROS_RESPIRATORIO_PREDETERMINADOS.departamento;
  const anioValido =
    candidato.anio === 'todos' ||
    (ANIOS_RESPIRATORIO as readonly number[]).includes(candidato.anio);
  const comparar =
    candidato.comparar &&
    DEPARTAMENTOS_POR_CODIGO[candidato.comparar] &&
    candidato.comparar !== departamento
      ? candidato.comparar
      : null;
  return {
    departamento,
    anio: anioValido ? candidato.anio : 'todos',
    comparar,
    semanaDesde: Math.min(desde, hasta),
    semanaHasta: Math.max(desde, hasta),
  };
}

/** Lee los parámetros de la URL con los mismos nombres que dengue. */
export function cambiosDesdeParametros(
  parametros: URLSearchParams,
): Partial<FiltrosRespiratorio> {
  const cambios: Partial<FiltrosRespiratorio> = {};
  const dept = parametros.get('dept');
  const anio = parametros.get('year');
  const compare = parametros.get('compare');
  const desde = parametros.get('fromWeek');
  const hasta = parametros.get('toWeek');
  if (dept !== null) cambios.departamento = dept;
  if (anio !== null) cambios.anio = anio === 'todos' ? 'todos' : Number(anio);
  if (compare !== null) cambios.comparar = compare || null;
  if (desde !== null) cambios.semanaDesde = Number(desde);
  if (hasta !== null) cambios.semanaHasta = Number(hasta);
  return cambios;
}

/** Escribe en la URL solo lo que difiere del valor predeterminado. */
export function aplicarFiltrosAParametros(
  filtros: FiltrosRespiratorio,
  parametros: URLSearchParams,
): void {
  const pred = FILTROS_RESPIRATORIO_PREDETERMINADOS;
  const poner = (
    clave: string,
    valor: string | null,
    defecto: string | null,
  ) => {
    if (valor === null || valor === defecto) parametros.delete(clave);
    else parametros.set(clave, valor);
  };
  poner('dept', filtros.departamento, pred.departamento);
  poner('year', String(filtros.anio), String(pred.anio));
  poner('compare', filtros.comparar, null);
  poner('fromWeek', String(filtros.semanaDesde), String(pred.semanaDesde));
  poner('toWeek', String(filtros.semanaHasta), String(pred.semanaHasta));
}

/** True si entre dos estados cambió solo el departamento seleccionado. */
export function soloCambiaDepartamento(
  anterior: FiltrosRespiratorio | null,
  actual: FiltrosRespiratorio,
): boolean {
  if (!anterior || anterior.departamento === actual.departamento) {
    return false;
  }
  return (
    JSON.stringify({ ...anterior, departamento: '' }) ===
    JSON.stringify({ ...actual, departamento: '' })
  );
}

export function filtrosRespiratorioIguales(
  a: FiltrosRespiratorio,
  b: FiltrosRespiratorio,
): boolean {
  return (
    a.departamento === b.departamento &&
    a.anio === b.anio &&
    a.comparar === b.comparar &&
    a.semanaDesde === b.semanaDesde &&
    a.semanaHasta === b.semanaHasta
  );
}

// --- Estado en el navegador -------------------------------------------------

let estado = normalizarFiltrosRespiratorio(
  FILTROS_RESPIRATORIO_PREDETERMINADOS,
  typeof window === 'undefined'
    ? {}
    : cambiosDesdeParametros(new URLSearchParams(window.location.search)),
);

function sincronizarUrl(filtros: FiltrosRespiratorio): void {
  if (typeof window === 'undefined') return;
  const url = new URL(window.location.href);
  aplicarFiltrosAParametros(filtros, url.searchParams);
  window.history.replaceState(null, '', url);
}

export function obtenerFiltrosRespiratorio(): FiltrosRespiratorio {
  return { ...estado };
}

export function actualizarFiltrosRespiratorio(
  cambios: Partial<FiltrosRespiratorio>,
): FiltrosRespiratorio {
  const siguiente = normalizarFiltrosRespiratorio(estado, cambios);
  if (filtrosRespiratorioIguales(estado, siguiente)) {
    return obtenerFiltrosRespiratorio();
  }
  estado = siguiente;
  const detalle = obtenerFiltrosRespiratorio();
  if (typeof window !== 'undefined') {
    sincronizarUrl(detalle);
    window.dispatchEvent(
      new CustomEvent<FiltrosRespiratorio>(EVENTO_FILTROS_RESPIRATORIO, {
        detail: detalle,
      }),
    );
  }
  return detalle;
}

export function suscribirFiltrosRespiratorio(
  listener: (filtros: FiltrosRespiratorio) => void,
  emitirInicial = true,
): () => void {
  if (emitirInicial) listener(obtenerFiltrosRespiratorio());
  if (typeof window === 'undefined') return () => undefined;
  const manejar = (evento: Event) => {
    listener({ ...(evento as CustomEvent<FiltrosRespiratorio>).detail });
  };
  window.addEventListener(EVENTO_FILTROS_RESPIRATORIO, manejar);
  return () => window.removeEventListener(EVENTO_FILTROS_RESPIRATORIO, manejar);
}
