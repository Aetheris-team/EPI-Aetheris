// Calendario epidemiológico para selección interactiva de semanas (MINSAL / OPS).
// Semanas de domingo a sábado, donde SE01 es la primera semana con al menos cuatro días
// del año (contiene el 4 de enero). El cálculo se apoya en src/lib/integridad.ts.
// Todas las operaciones con fechas emplean UTC para evitar desviaciones por huso horario.

import {
  inicioSemanaEpi,
  semanasDelAnio,
  semanaEpidemiologica,
  type SemanaEpi,
} from './integridad.ts';

const MS_DIA = 86_400_000;

export const NOMBRES_MESES = [
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
] as const;

export const NOMBRES_MESES_CORTOS = [
  'ene',
  'feb',
  'mar',
  'abr',
  'may',
  'jun',
  'jul',
  'ago',
  'sep',
  'oct',
  'nov',
  'dic',
] as const;

export const DIAS_SEMANA_CORTOS = [
  'Dom',
  'Lun',
  'Mar',
  'Mié',
  'Jue',
  'Vie',
  'Sáb',
] as const;

export const DIAS_SEMANA_COMPLETOS = [
  'Domingo',
  'Lunes',
  'Martes',
  'Miércoles',
  'Jueves',
  'Viernes',
  'Sábado',
] as const;

export interface InfoSemanaEpi {
  anio: number;
  semana: number;
  codigo: string;
  fechaInicioIso: string;
  fechaFinIso: string;
  diaInicio: number;
  mesInicio: number;
  anioInicio: number;
  diaFin: number;
  mesFin: number;
  anioFin: number;
  etiquetaRango: string;
  etiquetaCorta: string;
  etiquetaCompleta: string;
}

export interface DiaCalendarioEpi {
  fechaIso: string;
  numeroDia: number;
  mes: number;
  anio: number;
  diaSemana: number;
  esMesActual: boolean;
  semanaEpi: number;
  anioEpi: number;
}

export interface FilaSemanaEpi {
  semana: number;
  anio: number;
  codigo: string;
  etiquetaRango: string;
  etiquetaCorta: string;
  dias: DiaCalendarioEpi[];
  esActiva: boolean;
}

export interface MesCalendarioEpi {
  anio: number;
  mes: number;
  nombreMes: string;
  nombreMesCorto: string;
  filas: FilaSemanaEpi[];
}

export interface TrimestreCuadriculaEpi {
  indice: number;
  nombre: string;
  semanas: (InfoSemanaEpi & { esActiva: boolean })[];
}

export interface CuadriculaAnualEpi {
  anio: number;
  totalSemanas: number;
  trimestres: TrimestreCuadriculaEpi[];
}

/** Día como número de días desde 1970-01-01 (UTC). */
function diaUtc(anio: number, mes: number, dia: number): number {
  return Date.UTC(anio, mes - 1, dia) / MS_DIA;
}

/** 0 = domingo … 6 = sábado. */
function diaSemana(dia: number): number {
  return (((dia + 4) % 7) + 7) % 7;
}

/** Cantidad de días calendario en un mes determinado. */
export function diasEnMes(anio: number, mes: number): number {
  return new Date(Date.UTC(anio, mes, 0)).getUTCDate();
}

/** Capitaliza la primera letra de un texto. */
function capitalizar(texto: string): string {
  if (!texto) return '';
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/** Rellena con ceros a la izquierda (ej. 1 -> "01"). */
function pad2(num: number): string {
  return String(num).padStart(2, '0');
}

/**
 * Obtiene los detalles cronológicos completos de una semana epidemiológica
 * (fechas de domingo a sábado, etiquetas en español y formateo normalizado).
 */
export function obtenerInfoSemanaEpi(
  anio: number,
  semana: number,
): InfoSemanaEpi {
  const maxSemanas = semanasDelAnio(anio);
  const semanaNormalizada = Math.min(
    maxSemanas,
    Math.max(1, Math.trunc(semana)),
  );
  const epochDomingo = inicioSemanaEpi(anio, semanaNormalizada);
  const epochSabado = epochDomingo + 6;

  const fechaDom = new Date(epochDomingo * MS_DIA);
  const fechaSab = new Date(epochSabado * MS_DIA);

  const diaInicio = fechaDom.getUTCDate();
  const mesInicio = fechaDom.getUTCMonth() + 1;
  const anioInicio = fechaDom.getUTCFullYear();

  const diaFin = fechaSab.getUTCDate();
  const mesFin = fechaSab.getUTCMonth() + 1;
  const anioFin = fechaSab.getUTCFullYear();

  const fechaInicioIso = fechaDom.toISOString().slice(0, 10);
  const fechaFinIso = fechaSab.toISOString().slice(0, 10);

  const mesInicioCorto = NOMBRES_MESES_CORTOS[mesInicio - 1];
  const mesFinCorto = NOMBRES_MESES_CORTOS[mesFin - 1];

  const etiquetaCorta = `${pad2(diaInicio)} ${mesInicioCorto} – ${pad2(diaFin)} ${mesFinCorto}`;

  let etiquetaRango: string;
  if (anioInicio === anioFin) {
    etiquetaRango = `${etiquetaCorta}, ${anioInicio}`;
  } else {
    etiquetaRango = `${pad2(diaInicio)} ${mesInicioCorto}, ${anioInicio} – ${pad2(diaFin)} ${mesFinCorto}, ${anioFin}`;
  }

  const codigo = `SE${pad2(semanaNormalizada)}`;
  const etiquetaCompleta = `Semana ${semanaNormalizada} · ${etiquetaRango}`;

  return {
    anio,
    semana: semanaNormalizada,
    codigo,
    fechaInicioIso,
    fechaFinIso,
    diaInicio,
    mesInicio,
    anioInicio,
    diaFin,
    mesFin,
    anioFin,
    etiquetaRango,
    etiquetaCorta,
    etiquetaCompleta,
  };
}

/**
 * Devuelve el mes calendario (1..12) en el que se ubica el centro (miércoles)
 * de una semana epidemiológica determinada.
 */
export function mesDeSemanaEpi(anio: number, semana: number): number {
  const epochMiercoles = inicioSemanaEpi(anio, semana) + 3;
  return new Date(epochMiercoles * MS_DIA).getUTCMonth() + 1;
}

/**
 * Genera la matriz de semanas y días para la vista de calendario mensual.
 * Cada fila corresponde exactamente a una semana epidemiológica (domingo a sábado).
 */
export function generarMesCalendarioEpi(
  anio: number,
  mes: number,
  semanaActiva?: { anio: number; semana: number },
): MesCalendarioEpi {
  const mesNormalizado = Math.min(12, Math.max(1, Math.trunc(mes)));
  const totalDiasMes = diasEnMes(anio, mesNormalizado);

  const dia1 = diaUtc(anio, mesNormalizado, 1);
  const domingoInicio = dia1 - diaSemana(dia1);

  const ultimoDia = diaUtc(anio, mesNormalizado, totalDiasMes);
  const sabadoFin = ultimoDia + (6 - diaSemana(ultimoDia));

  const filas: FilaSemanaEpi[] = [];

  for (let d = domingoInicio; d <= sabadoFin; d += 7) {
    const domingoIso = new Date(d * MS_DIA).toISOString().slice(0, 10);
    const epi = semanaEpidemiologica(domingoIso);
    const info = obtenerInfoSemanaEpi(epi.anio, epi.semana);

    const diasFila: DiaCalendarioEpi[] = [];
    for (let offset = 0; offset < 7; offset++) {
      const diaEpoch = d + offset;
      const fecha = new Date(diaEpoch * MS_DIA);
      const numeroDia = fecha.getUTCDate();
      const mesDia = fecha.getUTCMonth() + 1;
      const anioDia = fecha.getUTCFullYear();
      const fechaIso = fecha.toISOString().slice(0, 10);

      diasFila.push({
        fechaIso,
        numeroDia,
        mes: mesDia,
        anio: anioDia,
        diaSemana: offset,
        esMesActual: mesDia === mesNormalizado && anioDia === anio,
        semanaEpi: epi.semana,
        anioEpi: epi.anio,
      });
    }

    const esActiva = semanaActiva
      ? semanaActiva.anio === epi.anio && semanaActiva.semana === epi.semana
      : false;

    filas.push({
      semana: epi.semana,
      anio: epi.anio,
      codigo: info.codigo,
      etiquetaRango: info.etiquetaRango,
      etiquetaCorta: info.etiquetaCorta,
      dias: diasFila,
      esActiva,
    });
  }

  const nombreMes = capitalizar(NOMBRES_MESES[mesNormalizado - 1]);
  const nombreMesCorto = NOMBRES_MESES_CORTOS[mesNormalizado - 1];

  return {
    anio,
    mes: mesNormalizado,
    nombreMes,
    nombreMesCorto,
    filas,
  };
}

/**
 * Genera la cuadrícula de todas las semanas del año agrupadas en 4 trimestres
 * para selección numérica directa y rápida.
 */
export function generarCuadriculaAnualEpi(
  anio: number,
  semanaActiva?: number,
): CuadriculaAnualEpi {
  const totalSemanas = semanasDelAnio(anio);

  const trimestresDef = [
    { indice: 1, nombre: 'T1 · Semanas 01 a 13', inicio: 1, fin: 13 },
    { indice: 2, nombre: 'T2 · Semanas 14 a 26', inicio: 14, fin: 26 },
    { indice: 3, nombre: 'T3 · Semanas 27 a 39', inicio: 27, fin: 39 },
    {
      indice: 4,
      nombre: `T4 · Semanas 40 a ${pad2(totalSemanas)}`,
      inicio: 40,
      fin: totalSemanas,
    },
  ];

  const trimestres: TrimestreCuadriculaEpi[] = trimestresDef.map((t) => {
    const semanas = [];
    for (let s = t.inicio; s <= t.fin; s++) {
      const info = obtenerInfoSemanaEpi(anio, s);
      semanas.push({
        ...info,
        esActiva: semanaActiva === s,
      });
    }
    return {
      indice: t.indice,
      nombre: t.nombre,
      semanas,
    };
  });

  return {
    anio,
    totalSemanas,
    trimestres,
  };
}

/**
 * Navega hacia adelante o atrás en meses calendario (ej. +1 mes, -1 mes),
 * gestionando el cambio de año automáticamente.
 */
export function ajustarMes(
  anio: number,
  mes: number,
  delta: number,
): { anio: number; mes: number } {
  const totalMeses = anio * 12 + (mes - 1) + delta;
  const nuevoAnio = Math.floor(totalMeses / 12);
  const nuevoMes = (totalMeses % 12) + 1;
  return { anio: nuevoAnio, mes: nuevoMes };
}

/**
 * Navega hacia adelante o atrás en semanas epidemiológicas (ej. +1 semana, -1 semana),
 * respetando el total de semanas (52 o 53) y cambiando de año de vigilancia.
 */
export function ajustarSemanaEpi(
  anio: number,
  semana: number,
  delta: number,
): SemanaEpi {
  let a = anio;
  let s = semana + delta;

  while (s < 1) {
    a -= 1;
    s += semanasDelAnio(a);
  }

  while (s > semanasDelAnio(a)) {
    s -= semanasDelAnio(a);
    a += 1;
  }

  return { anio: a, semana: s };
}
