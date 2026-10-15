import {
  esNoDisponible,
  type RespuestaNoDisponible,
} from '../components/estado-async';
import type { AlertaPublica } from './vista-alertas';
import type {
  AnioAnalisisDengue,
  CasoNacionalSemanal,
  ClimaDengueAnio,
  ClimaDengueMultipais,
  DatasetAnaliticoDengue,
  EventoRespiratorio,
  FiltrosAnalisis,
  IntegridadVigilancia,
  NowcastDengue,
  NowcastDengueRetrospectivo,
  ProcedenciaAnalitica,
  RespuestaIraDepartamental,
  SerieRespiratoriaNacional,
  SerieTemporalIdoneidad,
  SerieTemporalPresion,
} from './tipos-analisis';

const API_BASE = import.meta.env.PUBLIC_API_URL ?? 'http://localhost:8000';
/** Archivos completos de clima y dengue, enlazados desde el menú «Exportar». */
export const URL_CLIMA_POR_ANIO = `${API_BASE}/api/clima-dengue/por-anio`;
export const URL_CLIMA_MULTIPAIS = `${API_BASE}/api/clima-dengue/multipais`;
const cachePorAnio = new Map<
  AnioAnalisisDengue,
  Promise<DatasetAnaliticoDengue>
>();
let cacheCasosNacionales: Promise<CasoNacionalSemanal[]> | null = null;
let cacheIraDepartamental: Promise<RespuestaIraDepartamental> | null = null;
let cacheIntegridad: Promise<IntegridadVigilancia> | null = null;
let cacheNowcastDengue: Promise<NowcastDengue> | null = null;
let cacheAlertasDengue: Promise<AlertaPublica[]> | null = null;
let cacheNowcastRetro: Promise<NowcastDengueRetrospectivo> | null = null;
let cacheClimaDengueAnio: Promise<
  ClimaDengueAnio | RespuestaNoDisponible
> | null = null;
let cacheClimaDengueMultipais: Promise<
  ClimaDengueMultipais | RespuestaNoDisponible
> | null = null;
const cacheProcedencia = new Map<string, Promise<ProcedenciaAnalitica>>();
const cacheSerieIdoneidad = new Map<string, Promise<SerieTemporalIdoneidad>>();
const cacheSeriePresion = new Map<string, Promise<SerieTemporalPresion>>();
const cacheRespiratorioNacional = new Map<
  EventoRespiratorio,
  Promise<SerieRespiratoriaNacional | RespuestaNoDisponible>
>();

let peticionesEnVuelo = 0;

function notificarActividad() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent('epi:actividad-red', {
        detail: {
          enVuelo: peticionesEnVuelo > 0,
          conteo: peticionesEnVuelo,
        },
      }),
    );
  }
}

function registrarPeticion<T>(promesa: Promise<T>): Promise<T> {
  peticionesEnVuelo++;
  notificarActividad();
  return promesa.finally(() => {
    peticionesEnVuelo = Math.max(0, peticionesEnVuelo - 1);
    notificarActividad();
  });
}

export function hayPeticionesEnVuelo(): boolean {
  return peticionesEnVuelo > 0;
}

function cargarDataset(
  anio: AnioAnalisisDengue,
): Promise<DatasetAnaliticoDengue> {
  return registrarPeticion(
    fetch(`${API_BASE}/api/v1/analisis/dengue?year=${anio}`).then(
      async (respuesta) => {
        if (!respuesta.ok) {
          throw new Error(
            `No se pudo cargar el dataset analítico (${respuesta.status}).`,
          );
        }
        const datos: unknown = await respuesta.json();
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('epi:datos-cargados'));
        }
        if (esNoDisponible(datos)) {
          return datos as any;
        }
        if (
          !datos ||
          typeof datos !== 'object' ||
          !Array.isArray((datos as { departamentos?: unknown }).departamentos)
        ) {
          throw new Error(
            'El dataset analítico no tiene el contrato esperado.',
          );
        }
        return datos as DatasetAnaliticoDengue;
      },
    ),
  );
}

export function obtenerDatasetAnalitico(
  anio: AnioAnalisisDengue,
): Promise<DatasetAnaliticoDengue> {
  let solicitud = cachePorAnio.get(anio);
  if (!solicitud) {
    solicitud = cargarDataset(anio).catch((error) => {
      cachePorAnio.delete(anio);
      throw error;
    });
    cachePorAnio.set(anio, solicitud);
  }
  return solicitud;
}

export function obtenerCasosNacionales(): Promise<CasoNacionalSemanal[]> {
  if (!cacheCasosNacionales) {
    cacheCasosNacionales = registrarPeticion(
      fetch(`${API_BASE}/api/casos-nacional`)
        .then(async (respuesta) => {
          if (!respuesta.ok) {
            throw new Error(
              `No se pudo cargar la serie nacional (${respuesta.status}).`,
            );
          }
          const datos: unknown = await respuesta.json();
          if (esNoDisponible(datos)) {
            return datos as any;
          }
          if (!Array.isArray(datos)) {
            throw new Error('La serie nacional no tiene el contrato esperado.');
          }
          return datos as CasoNacionalSemanal[];
        })
        .catch((error) => {
          cacheCasosNacionales = null;
          throw error;
        }),
    );
  }
  return cacheCasosNacionales;
}

export function obtenerIntegridadVigilancia(): Promise<IntegridadVigilancia> {
  if (!cacheIntegridad) {
    cacheIntegridad = registrarPeticion(
      fetch(`${API_BASE}/api/v1/vigilancia/integridad`)
        .then(async (respuesta) => {
          if (!respuesta.ok) {
            throw new Error(
              `No se pudo cargar la integridad de vigilancia (${respuesta.status}).`,
            );
          }
          const datos: unknown = await respuesta.json();
          if (esNoDisponible(datos)) {
            return datos as any;
          }
          if (
            !datos ||
            typeof datos !== 'object' ||
            !('antiguedad' in datos) ||
            !Array.isArray((datos as { resumen_anual?: unknown }).resumen_anual)
          ) {
            throw new Error(
              'La integridad de vigilancia no tiene el contrato esperado.',
            );
          }
          return datos as IntegridadVigilancia;
        })
        .catch((error) => {
          cacheIntegridad = null;
          throw error;
        }),
    );
  }
  return cacheIntegridad;
}

// Mismo patrón que obtenerCasosNacionales: MapaIRA y CurvaIRADepartamental
// piden ambos /api/ira/departamental por su cuenta al montarse -- este
// helper deduplica esa petición (es uno de los endpoints más lentos del
// backend, ver informe de rendimiento) en una sola promesa compartida.
export function obtenerIraDepartamental(): Promise<RespuestaIraDepartamental> {
  if (!cacheIraDepartamental) {
    cacheIraDepartamental = registrarPeticion(
      fetch(`${API_BASE}/api/ira/departamental`)
        .then(async (respuesta) => {
          if (!respuesta.ok) {
            throw new Error(
              `No se pudo cargar la serie de IRA (${respuesta.status}).`,
            );
          }
          const datos: unknown = await respuesta.json();
          if (
            !datos ||
            typeof datos !== 'object' ||
            !Array.isArray((datos as { departamentos?: unknown }).departamentos)
          ) {
            throw new Error('La serie de IRA no tiene el contrato esperado.');
          }
          return datos as RespuestaIraDepartamental;
        })
        .catch((error) => {
          cacheIraDepartamental = null;
          throw error;
        }),
    );
  }
  return cacheIraDepartamental;
}

function tieneSemanas(datos: unknown): boolean {
  return (
    !!datos &&
    typeof datos === 'object' &&
    Array.isArray((datos as { semanas?: unknown }).semanas)
  );
}

/** Serie nacional de IRA o neumonías del tablero de MINSAL, desde 2025.
 *  Sin capturas cargadas la API responde disponible:false. */
export function obtenerSerieRespiratoriaNacional(
  evento: EventoRespiratorio,
): Promise<SerieRespiratoriaNacional | RespuestaNoDisponible> {
  let solicitud = cacheRespiratorioNacional.get(evento);
  if (!solicitud) {
    solicitud = registrarPeticion(
      fetch(`${API_BASE}/api/${evento}/nacional`)
        .then(async (respuesta) => {
          if (!respuesta.ok) {
            throw new Error(
              `No se pudo cargar la serie nacional (${respuesta.status}).`,
            );
          }
          const datos: unknown = await respuesta.json();
          if (esNoDisponible(datos)) {
            return datos;
          }
          if (!tieneSemanas(datos)) {
            throw new Error('La serie nacional no tiene el contrato esperado.');
          }
          return datos as SerieRespiratoriaNacional;
        })
        .catch((error) => {
          cacheRespiratorioNacional.delete(evento);
          throw error;
        }),
    );
    cacheRespiratorioNacional.set(evento, solicitud);
  }
  return solicitud;
}

/** Serie del año contra la banda histórica de Iv (M1) y la anomalía (M2)
 *  de un departamento. `codigo` es ISO 3166-2:SV (ej. 'SV-SS'). */
export function obtenerSerieIdoneidad(
  codigo: string,
  anio: number,
): Promise<SerieTemporalIdoneidad> {
  const clave = `${codigo}:${anio}`;
  let solicitud = cacheSerieIdoneidad.get(clave);
  if (!solicitud) {
    solicitud = registrarPeticion(
      fetch(
        `${API_BASE}/api/v1/temporal/${encodeURIComponent(codigo)}?anio=${anio}`,
      )
        .then(async (respuesta) => {
          if (!respuesta.ok) {
            throw new Error(
              `No se pudo cargar la serie de idoneidad (${respuesta.status}).`,
            );
          }
          const datos: unknown = await respuesta.json();
          if (esNoDisponible(datos)) {
            return datos as any;
          }
          if (!tieneSemanas(datos)) {
            throw new Error(
              'La serie de idoneidad no tiene el contrato esperado.',
            );
          }
          return datos as SerieTemporalIdoneidad;
        })
        .catch((error) => {
          cacheSerieIdoneidad.delete(clave);
          throw error;
        }),
    );
    cacheSerieIdoneidad.set(clave, solicitud);
  }
  return solicitud;
}

/** Serie del percentil de presión epidemiológica relativa (M3), probable y
 *  confirmado, de un departamento para `anio`. */
export function obtenerSeriePresion(
  codigo: string,
  anio: number,
): Promise<SerieTemporalPresion> {
  const clave = `${codigo}:${anio}`;
  let solicitud = cacheSeriePresion.get(clave);
  if (!solicitud) {
    solicitud = registrarPeticion(
      fetch(
        `${API_BASE}/api/v1/presion/temporal/${encodeURIComponent(codigo)}?anio=${anio}`,
      )
        .then(async (respuesta) => {
          if (!respuesta.ok) {
            throw new Error(
              `No se pudo cargar la serie de presión (${respuesta.status}).`,
            );
          }
          const datos: unknown = await respuesta.json();
          if (esNoDisponible(datos)) {
            return datos as any;
          }
          if (!tieneSemanas(datos)) {
            throw new Error(
              'La serie de presión no tiene el contrato esperado.',
            );
          }
          return datos as SerieTemporalPresion;
        })
        .catch((error) => {
          cacheSeriePresion.delete(clave);
          throw error;
        }),
    );
    cacheSeriePresion.set(clave, solicitud);
  }
  return solicitud;
}

export function obtenerProcedenciaAnalitica(
  filtros: Pick<FiltrosAnalisis, 'anio' | 'semana' | 'serie' | 'departamento'>,
): Promise<ProcedenciaAnalitica> {
  if (!filtros.departamento) {
    return Promise.reject(
      new Error('Se requiere un departamento para consultar procedencia.'),
    );
  }
  const clave = [
    filtros.anio,
    filtros.semana,
    filtros.serie,
    filtros.departamento,
  ].join(':');
  let solicitud = cacheProcedencia.get(clave);
  if (!solicitud) {
    const parametros = new URLSearchParams({
      year: String(filtros.anio),
      week: String(filtros.semana),
      serie: filtros.serie,
      dept: filtros.departamento,
    });
    solicitud = registrarPeticion(
      fetch(`${API_BASE}/api/v1/analisis/dengue/procedencia?${parametros}`)
        .then(async (respuesta) => {
          if (!respuesta.ok) {
            throw new Error(
              `No se pudo cargar la procedencia (${respuesta.status}).`,
            );
          }
          const datos: unknown = await respuesta.json();
          if (esNoDisponible(datos)) {
            return datos as any;
          }
          return datos as ProcedenciaAnalitica;
        })
        .catch((error) => {
          cacheProcedencia.delete(clave);
          throw error;
        }),
    );
    cacheProcedencia.set(clave, solicitud);
  }
  return solicitud;
}

export function obtenerNowcastDengue(): Promise<NowcastDengue> {
  if (!cacheNowcastDengue) {
    cacheNowcastDengue = registrarPeticion(
      fetch(`${API_BASE}/api/nowcast-dengue`)
        .then(async (respuesta) => {
          if (!respuesta.ok) {
            throw new Error(
              `No se pudo cargar la estimación de horizonte corto (${respuesta.status}).`,
            );
          }
          return (await respuesta.json()) as NowcastDengue;
        })
        .catch((error) => {
          cacheNowcastDengue = null;
          throw error;
        }),
    );
  }
  return cacheNowcastDengue;
}

export function obtenerNowcastRetrospectivo(): Promise<NowcastDengueRetrospectivo> {
  if (!cacheNowcastRetro) {
    cacheNowcastRetro = registrarPeticion(
      fetch(`${API_BASE}/api/nowcast-dengue/retrospectivo`)
        .then(async (respuesta) => {
          if (!respuesta.ok) {
            throw new Error(
              `No se pudo cargar la predicción retrospectiva (${respuesta.status}).`,
            );
          }
          const datos: unknown = await respuesta.json();
          if (esNoDisponible(datos)) {
            return datos as any;
          }
          const d = datos as Partial<NowcastDengueRetrospectivo> | null;
          if (
            !d ||
            !Array.isArray(d.observado) ||
            !Array.isArray(d.origenes) ||
            !Array.isArray(d.horizontes)
          ) {
            throw new Error(
              'La predicción retrospectiva no tiene el contrato esperado.',
            );
          }
          return d as NowcastDengueRetrospectivo;
        })
        .catch((error) => {
          cacheNowcastRetro = null;
          throw error;
        }),
    );
  }
  return cacheNowcastRetro;
}

function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor);
}

/**
 * Clima y dengue de El Salvador año por año (ADR 0023 del monorepo). Un 200
 * con `disponible: false` pasa tal cual: es una brecha de cobertura esperada,
 * no un error de red.
 */
export function obtenerClimaDengueAnio(): Promise<
  ClimaDengueAnio | RespuestaNoDisponible
> {
  if (!cacheClimaDengueAnio) {
    cacheClimaDengueAnio = registrarPeticion(
      fetch(URL_CLIMA_POR_ANIO)
        .then(async (respuesta) => {
          if (!respuesta.ok) {
            throw new Error(
              `No se pudo cargar el análisis de clima y dengue por año (${respuesta.status}).`,
            );
          }
          const datos: unknown = await respuesta.json();
          if (esNoDisponible(datos)) return datos;
          if (
            !esObjeto(datos) ||
            !esObjeto(datos.A1) ||
            !esObjeto(datos.A2) ||
            !esObjeto(datos.A3) ||
            !esObjeto(datos.A3.por_anio) ||
            !esObjeto(datos.A3.agrupado) ||
            !esObjeto(datos.A5)
          ) {
            throw new Error(
              'El análisis de clima y dengue por año no tiene el contrato esperado.',
            );
          }
          return datos as unknown as ClimaDengueAnio;
        })
        .catch((error) => {
          cacheClimaDengueAnio = null;
          throw error;
        }),
    );
  }
  return cacheClimaDengueAnio;
}

/** El Salvador frente a 18 países de las Américas (ADR 0023 del monorepo). */
export function obtenerClimaDengueMultipais(): Promise<
  ClimaDengueMultipais | RespuestaNoDisponible
> {
  if (!cacheClimaDengueMultipais) {
    cacheClimaDengueMultipais = registrarPeticion(
      fetch(URL_CLIMA_MULTIPAIS)
        .then(async (respuesta) => {
          if (!respuesta.ok) {
            throw new Error(
              `No se pudo cargar la comparación entre países (${respuesta.status}).`,
            );
          }
          const datos: unknown = await respuesta.json();
          if (esNoDisponible(datos)) return datos;
          if (
            !esObjeto(datos) ||
            !esObjeto(datos.P1) ||
            !esObjeto(datos.P2) ||
            !esObjeto(datos.P2.por_pais) ||
            !esObjeto(datos.P3) ||
            !esObjeto(datos.P4) ||
            !esObjeto(datos.P5) ||
            !esObjeto(datos.P6)
          ) {
            throw new Error(
              'La comparación entre países no tiene el contrato esperado.',
            );
          }
          return datos as unknown as ClimaDengueMultipais;
        })
        .catch((error) => {
          cacheClimaDengueMultipais = null;
          throw error;
        }),
    );
  }
  return cacheClimaDengueMultipais;
}

/**
 * Alertas de dengue activas (sin etiquetadas), nacionales y regionales. El
 * mapa las usa para marcar los departamentos con alerta vigente (ADR 0022).
 */
export function obtenerAlertasDengue(): Promise<AlertaPublica[]> {
  if (!cacheAlertasDengue) {
    cacheAlertasDengue = registrarPeticion(
      fetch(`${API_BASE}/api/alertas?tipo=dengue`)
        .then(async (respuesta) => {
          if (!respuesta.ok) {
            throw new Error(
              `No se pudieron cargar las alertas de dengue (${respuesta.status}).`,
            );
          }
          const datos: unknown = await respuesta.json();
          const alertas = (datos as { alertas?: unknown }).alertas;
          if (!Array.isArray(alertas)) {
            throw new Error('Las alertas de dengue llegaron con otro formato.');
          }
          return alertas as AlertaPublica[];
        })
        .catch((error) => {
          cacheAlertasDengue = null;
          throw error;
        }),
    );
  }
  return cacheAlertasDengue;
}
