// Opciones de ECharts para las gráficas de la predicción de dengue: abanico
// hacia adelante, validación a cuatro semanas y contraste con lo observado.
// Solo importa tipos de ECharts (ver echarts-base.ts): el registro modular se
// carga con montarGrafico.
//
// Convenciones de lectura, iguales en las tres gráficas:
//   tinta, línea continua      casos publicados por la fuente
//   azul de estimación, punteada   mediana de la predicción
//   bandas azules              rango del 50 % (más intensa) y del 95 %
// Las bandas son áreas apiladas (base transparente más ancho del rango): así
// ECharts las revela de izquierda a derecha con su animación de entrada.
import type { OpcionEcharts } from './echarts-base';
import { crearOpcionBase } from './echarts-tema.ts';
import type { TokensGrafico } from './echarts-tema.ts';
import {
  coberturaDe,
  conHuecos,
  fecha,
  fmtFecha,
  fmtFechaCorta,
  fmtNum,
  marcaTiempo,
  SEMANA_MS,
} from './nowcast-datos.ts';
import type {
  Cobertura,
  DatosAbanico,
  DatosValidacion,
  Horizonte,
  ModeloContraste,
  Origen,
  Rango,
} from './nowcast-datos.ts';
import { escapeHtml } from '../utils/security.ts';

export const SERIE = {
  publicado: 'Casos publicados',
  mediana: 'Mediana de la predicción',
  rango50: 'Rango 50 %',
  rango95: 'Rango 95 %',
  fuera: 'Fuera del rango 95 %',
  diferencia: 'Diferencia con lo observado',
} as const;

export type NombreSerie = (typeof SERIE)[keyof typeof SERIE];
export type Visibles = Partial<Record<NombreSerie, boolean>>;

/** Encuadre del abanico: tres meses, un año o toda la serie que trae la API. */
export type VistaAbanico = 'cerca' | 'anio' | 'todo';
export const SEMANAS_VISTA: Record<VistaAbanico, number | null> = {
  cerca: 13,
  anio: 52,
  todo: null,
};

const MESES = [
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
];

export function conAlfa(color: string, alfa: number): string {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(color.trim());
  if (!m) return color;
  const hex =
    m[1].length === 3
      ? m[1]
          .split('')
          .map((c) => c + c)
          .join('')
      : m[1];
  const n = parseInt(hex, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alfa})`;
}

/** Más intenso al centro que en los bordes de la banda. */
function degradadoBanda(color: string, extremo: number, centro: number) {
  return {
    type: 'linear' as const,
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: conAlfa(color, extremo) },
      { offset: 0.5, color: conAlfa(color, centro) },
      { offset: 1, color: conAlfa(color, extremo) },
    ],
  };
}

// --- piezas comunes ---------------------------------------------------------

interface FilaTooltip {
  nombre: string;
  valor: string;
  /** muestra de la serie a la izquierda del nombre */
  muestra?: { color: string; estilo: 'continua' | 'punteada' | 'banda' };
  secundaria?: boolean;
}

function muestraHtml(m: NonNullable<FilaTooltip['muestra']>): string {
  if (m.estilo === 'banda') {
    return `<span style="display:inline-block;width:14px;height:8px;border-radius:2px;background:${m.color};margin-right:8px;flex:none"></span>`;
  }
  const borde = m.estilo === 'punteada' ? 'dashed' : 'solid';
  return `<span style="display:inline-block;width:14px;height:0;border-top:2px ${borde} ${m.color};margin-right:8px;flex:none"></span>`;
}

/** Tarjeta del tooltip: encabezado con la semana, una fila por dato y nota opcional. */
export function tooltipHtml(
  t: TokensGrafico,
  contenido: {
    titulo: string;
    estado?: string;
    filas: FilaTooltip[];
    nota?: string;
  },
): string {
  const estado = contenido.estado
    ? `<span style="margin-left:12px;padding:1px 8px;border-radius:999px;border:1px solid ${t.borde};font-size:11px;font-weight:600;color:${t.tintaSuave};white-space:nowrap">${escapeHtml(contenido.estado)}</span>`
    : '';
  const filas = contenido.filas
    .map(
      (f) =>
        `<div style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:5px;${f.secundaria ? `color:${t.tintaSuave};` : ''}">` +
        `<span style="display:inline-flex;align-items:center">${f.muestra ? muestraHtml(f.muestra) : ''}${escapeHtml(f.nombre)}</span>` +
        `<span style="font-family:${t.fuente};font-variant-numeric:tabular-nums;font-weight:600;color:${f.secundaria ? t.tintaSuave : t.tinta}">${escapeHtml(f.valor)}</span></div>`,
    )
    .join('');
  const nota = contenido.nota
    ? `<div style="margin-top:8px;padding-top:6px;border-top:1px solid ${t.borde};max-width:230px;white-space:normal;line-height:1.4;font-size:11px;color:${t.tintaSuave}">${escapeHtml(contenido.nota)}</div>`
    : '';
  return (
    `<div style="font-family:${t.fuenteTexto};font-size:12px;line-height:1.35;color:${t.tinta};min-width:200px">` +
    `<div style="display:flex;align-items:center;justify-content:space-between;font-weight:600">` +
    `<span>${escapeHtml(contenido.titulo)}</span>${estado}</div>${filas}${nota}</div>`
  );
}

function textoCobertura(c: Cobertura): string {
  if (c === 'rango 50 %') return 'dentro del rango del 50 %';
  if (c === 'rango 95 %') return 'dentro del rango del 95 %';
  return 'fuera del rango del 95 %';
}

const rango = (r: Rango) => `${fmtNum.format(r[0])} a ${fmtNum.format(r[1])}`;

function opcionBase(
  t: TokensGrafico,
  movil: boolean,
  formatter: (params: unknown) => string,
  grid: Record<string, unknown>,
  visibles: Visibles,
  nombres: string[],
) {
  const base = crearOpcionBase(t, {
    grid,
    tooltip: {
      formatter,
      padding: [10, 12],
      borderWidth: 1,
      extraCssText:
        'border-radius:10px;box-shadow:0 10px 28px -8px rgba(0,0,0,0.28);',
      axisPointer: {
        type: 'line',
        snap: true,
        lineStyle: { color: t.tintaSuave, width: 1, opacity: 0.55 },
      },
    },
    legend: { show: false, data: nombres },
  }) as Record<string, unknown>;
  const legend = base.legend as Record<string, unknown>;
  legend.selected = Object.fromEntries(
    nombres.map((n) => [n, visibles[n as NombreSerie] !== false]),
  );
  return {
    ...base,
    animationDuration: 700,
    animationEasing: 'cubicOut' as const,
    animationDurationUpdate: movil ? 200 : 320,
  };
}

/** Eje de tiempo con meses abreviados en español; el año marca enero. */
function ejeTiempo(
  t: TokensGrafico,
  movil: boolean,
  minimo: number,
  maximo: number,
  semanasVisibles: number,
): OpcionEcharts {
  const corto = semanasVisibles <= 24;
  return {
    type: 'time',
    min: minimo,
    max: maximo,
    splitNumber: movil ? 4 : 8,
    axisLine: { lineStyle: { color: t.borde } },
    axisTick: { lineStyle: { color: t.borde } },
    splitLine: { show: false },
    axisLabel: {
      color: t.tintaSuave,
      fontFamily: t.fuente,
      fontSize: movil ? 10 : 11,
      hideOverlap: true,
      margin: 10,
      formatter: (valor: number) => {
        const d = new Date(valor);
        if (corto) return `${d.getDate()} ${MESES[d.getMonth()]}`;
        return d.getMonth() === 0 && d.getDate() <= 7
          ? String(d.getFullYear())
          : MESES[d.getMonth()];
      },
    },
    axisPointer: { label: { show: false } },
  };
}

function ejeCasos(
  t: TokensGrafico,
  movil: boolean,
  maximo?: number,
): OpcionEcharts {
  return {
    type: 'value',
    min: 0,
    max: maximo,
    splitNumber: movil ? 3 : 4,
    axisLabel: {
      color: t.tintaSuave,
      fontFamily: t.fuente,
      fontSize: movil ? 10 : 11,
      // con el máximo fijado, ECharts rotula también el tope aunque no caiga en una marca
      formatter: (v: number) =>
        maximo !== undefined && v === maximo && maximo % 100 !== 0
          ? ''
          : fmtNum.format(v),
    },
    splitLine: { lineStyle: { color: t.borde, opacity: 0.7 } },
    axisLine: { show: false },
    axisTick: { show: false },
  };
}

function gridDe(movil: boolean, conEtiquetaFinal: boolean) {
  return movil
    ? { left: 40, right: 12, top: 50, bottom: 26 }
    : { left: 50, right: conEtiquetaFinal ? 92 : 20, top: 50, bottom: 28 };
}

interface SeriesBanda {
  base95: OpcionEcharts;
  banda95: OpcionEcharts;
  base50: OpcionEcharts;
  banda50: OpcionEcharts;
}

/** Cuatro series apiladas: base transparente y ancho del rango, por cada banda. */
function seriesBandas(
  t: TokensGrafico,
  puntos: { t: number; b50: Rango | null; b95: Rango | null }[],
): SeriesBanda {
  const comun = {
    type: 'line' as const,
    symbol: 'none',
    silent: true,
    smooth: false,
    lineStyle: { width: 0, opacity: 0 },
    z: 1,
  };
  const par = (r: 'b50' | 'b95') => ({
    base: puntos.map(
      (p) => [p.t, p[r] ? p[r][0] : null] as [number, number | null],
    ),
    ancho: puntos.map(
      (p) => [p.t, p[r] ? p[r][1] - p[r][0] : null] as [number, number | null],
    ),
  });
  const d95 = par('b95');
  const d50 = par('b50');
  return {
    base95: {
      ...comun,
      id: 'base-95',
      name: 'Base del rango 95 %',
      stack: 'r95',
      data: d95.base,
    },
    banda95: {
      ...comun,
      id: 'banda-95',
      name: SERIE.rango95,
      stack: 'r95',
      areaStyle: { color: degradadoBanda(t.estimacion, 0.07, 0.2) },
      data: d95.ancho,
    },
    base50: {
      ...comun,
      id: 'base-50',
      name: 'Base del rango 50 %',
      stack: 'r50',
      z: 2,
      data: d50.base,
    },
    banda50: {
      ...comun,
      id: 'banda-50',
      name: SERIE.rango50,
      stack: 'r50',
      z: 2,
      areaStyle: { color: degradadoBanda(t.estimacion, 0.2, 0.42) },
      data: d50.ancho,
    },
  };
}

function lineaPublicada(
  t: TokensGrafico,
  datos: [number, number | null][],
  ancho = 2.2,
): OpcionEcharts {
  return {
    id: 'publicado',
    name: SERIE.publicado,
    type: 'line',
    symbol: 'none',
    z: 5,
    connectNulls: false,
    lineStyle: { width: ancho, color: t.tinta, cap: 'round', join: 'round' },
    itemStyle: { color: t.tinta },
    emphasis: { focus: 'series', lineStyle: { width: ancho + 0.8 } },
    data: datos,
  };
}

function lineaMediana(
  t: TokensGrafico,
  datos: [number, number | null][],
  extra: Record<string, unknown> = {},
): OpcionEcharts {
  return {
    id: 'mediana',
    name: SERIE.mediana,
    type: 'line',
    z: 6,
    showSymbol: true,
    symbol: 'circle',
    symbolSize: 6,
    lineStyle: {
      width: 2.4,
      type: [7, 4],
      color: t.estimacion,
      cap: 'round',
    },
    itemStyle: {
      color: t.estimacion,
      borderColor: t.superficie,
      borderWidth: 1.5,
    },
    emphasis: { focus: 'series', lineStyle: { width: 3.2 } },
    data: datos,
    ...extra,
  };
}

function nombreSemana(iso: string): string {
  return `Semana del ${fmtFecha.format(fecha(iso))}`;
}

// --- abanico hacia adelante -------------------------------------------------

export interface OpcionesAbanico {
  movil: boolean;
  vista: VistaAbanico;
  visibles?: Visibles;
  /** false: solo lo publicado, sin abanico (arranque de la presentación) */
  revelado?: boolean;
}

function maximoAbanico(
  datos: DatosAbanico,
  vista: VistaAbanico,
): number | undefined {
  if (vista !== 'cerca') return undefined;
  // El rango del 95 % puede llegar a varias veces el valor observado: en el
  // encuadre cercano se ciñe a lo observado y al rango del 50 %, y la banda
  // del 95 % sale por arriba (su valor queda en el resumen y en la tabla).
  const obs = datos.observado.map((o) => o.casos ?? 0);
  const tope = Math.max(
    ...obs,
    ...datos.prediccion.map((p) => Math.max(p.b50[1], p.mediana)),
  );
  return Math.ceil((tope * 1.18) / 10) * 10;
}

export function opcionAbanico(
  t: TokensGrafico,
  datos: DatosAbanico,
  opciones: OpcionesAbanico,
): OpcionEcharts {
  const { movil, vista, revelado = true } = opciones;
  const visibles = opciones.visibles ?? {};
  const { ancla, observado, prediccion } = datos;
  const tFinal = prediccion[prediccion.length - 1].t;
  const tInicio = observado[0].t;

  // lo que muestra el tooltip, indexado por semana
  const porSemana = new Map<
    number,
    { o?: (typeof observado)[0]; p?: (typeof prediccion)[0] }
  >();
  for (const o of observado) porSemana.set(o.t, { o });
  for (const p of prediccion) porSemana.set(p.t, { ...porSemana.get(p.t), p });

  const formatter = (params: unknown): string => {
    const lista = Array.isArray(params) ? params : [params];
    const eje = (lista[0] as { axisValue?: number } | undefined)?.axisValue;
    if (eje === undefined) return '';
    let cercano: number | null = null;
    let dist = Infinity;
    for (const k of porSemana.keys()) {
      if (Math.abs(k - eje) < dist) {
        dist = Math.abs(k - eje);
        cercano = k;
      }
    }
    const fila = cercano === null ? undefined : porSemana.get(cercano);
    if (!fila || dist > 3.5 * 86_400_000) return '';
    const filas: FilaTooltip[] = [];
    if (fila.o) {
      filas.push({
        nombre: SERIE.publicado,
        valor:
          fila.o.casos === null ? 'sin publicar' : fmtNum.format(fila.o.casos),
        muestra: { color: t.tinta, estilo: 'continua' },
      });
    }
    if (fila.p) {
      filas.push(
        {
          nombre: SERIE.mediana,
          valor: fmtNum.format(fila.p.mediana),
          muestra: { color: t.estimacion, estilo: 'punteada' },
        },
        {
          nombre: SERIE.rango50,
          valor: rango(fila.p.b50),
          muestra: { color: conAlfa(t.estimacion, 0.5), estilo: 'banda' },
          secundaria: true,
        },
        {
          nombre: SERIE.rango95,
          valor: rango(fila.p.b95),
          muestra: { color: conAlfa(t.estimacion, 0.22), estilo: 'banda' },
          secundaria: true,
        },
      );
    }
    const esAncla = fila.o && cercano === ancla.t;
    return tooltipHtml(t, {
      titulo: nombreSemana(fila.o?.fecha ?? fila.p?.fecha ?? ancla.fecha),
      estado:
        fila.p && !esAncla
          ? `Predicción +${fila.p.h}`
          : esAncla
            ? 'Última publicada'
            : 'Publicado',
      filas,
    });
  };

  // el abanico arranca pegado al último punto publicado
  const desdeAncla = revelado
    ? [
        {
          t: ancla.t,
          mediana: ancla.casos,
          b50: [ancla.casos, ancla.casos] as Rango,
          b95: [ancla.casos, ancla.casos] as Rango,
        },
        ...prediccion,
      ]
    : [];
  const bandas = seriesBandas(
    t,
    desdeAncla.map((p) => ({ t: p.t, b50: p.b50, b95: p.b95 })),
  );

  // máximo de lo publicado en el encuadre, si no es de las últimas semanas
  let pico: { t: number; v: number } | null = null;
  for (const o of observado) {
    if (o.casos !== null && (!pico || o.casos > pico.v))
      pico = { t: o.t, v: o.casos };
  }
  const mostrarPico =
    observado.length >= 26 &&
    pico !== null &&
    pico.t < observado[Math.max(0, observado.length - 4)].t &&
    pico.v > ancla.casos * 1.1;

  const tope = maximoAbanico(datos, vista);
  const maxB95 = Math.max(...prediccion.map((p) => p.b95[1]));
  const recortada = revelado && tope !== undefined && maxB95 > tope;

  const marcas = {
    id: 'marcas',
    name: 'Marcas',
    type: 'line',
    silent: true,
    data: [],
    markArea: {
      silent: true,
      itemStyle: { color: conAlfa(t.estimacion, 0.05) },
      label: {
        show: !movil,
        position: 'insideTopLeft',
        offset: [6, 2],
        color: t.estimacion,
        fontFamily: t.fuenteTexto,
        fontSize: 11,
        fontWeight: 600,
      },
      data: revelado
        ? [
            [
              {
                xAxis: ancla.t,
                name: `Predicción · ${prediccion.length} sem.`,
              },
              { xAxis: tFinal },
            ],
          ]
        : [],
    },
    markLine: {
      silent: true,
      symbol: 'none',
      animation: false,
      lineStyle: { color: t.tintaSuave, type: [3, 3], width: 1 },
      label: {
        show: true,
        position: 'end',
        align: 'right',
        distance: 6,
        offset: [-6, 0],
        color: t.tintaSuave,
        fontFamily: t.fuenteTexto,
        fontSize: movil ? 10 : 11,
        lineHeight: movil ? 13 : 15,
        formatter: () =>
          `Última semana publicada\n${fmtFechaCorta.format(fecha(ancla.fecha))} · ${fmtNum.format(ancla.casos)} casos`,
      },
      data: [
        { xAxis: ancla.t },
        // el encuadre cercano recorta la banda del 95 %: se avisa en la gráfica
        ...(recortada
          ? [
              {
                yAxis: tope,
                lineStyle: { color: 'transparent', width: 0 },
                label: {
                  position: 'insideEndBottom',
                  fontFamily: t.fuenteTexto,
                  align: 'right',
                  formatter: `El rango del 95 % llega a ${fmtNum.format(maxB95)} casos`,
                },
              },
            ]
          : []),
      ],
    },
  };

  const puntoAncla = {
    id: 'punto-ancla',
    name: 'Última semana publicada',
    type: 'scatter',
    silent: true,
    z: 8,
    symbolSize: 11,
    itemStyle: { color: t.tinta, borderColor: t.superficie, borderWidth: 2.5 },
    data: [[ancla.t, ancla.casos]],
  };

  const series: OpcionEcharts[] = [
    marcas,
    bandas.base95,
    bandas.banda95,
    bandas.base50,
    bandas.banda50,
    lineaPublicada(
      t,
      observado.map((o) => [o.t, o.casos] as [number, number | null]),
    ),
    lineaMediana(
      t,
      desdeAncla.map((p) => [p.t, p.mediana] as [number, number | null]),
      {
        symbolSize: (_v: unknown, p: { dataIndex: number }) =>
          p.dataIndex === 0 ? 0 : movil ? 5 : 6,
        endLabel: movil
          ? { show: false }
          : {
              show: true,
              distance: 8,
              color: t.estimacion,
              fontFamily: t.fuenteTexto,
              fontSize: 11,
              fontWeight: 600,
              formatter: (p: { value: [number, number] }) =>
                `Mediana\n${fmtNum.format(p.value[1])}`,
              lineHeight: 14,
            },
      },
    ),
    puntoAncla,
  ];
  {
    const etiquetaPico = pico;
    series.push({
      id: 'pico',
      name: 'Máximo del periodo',
      type: 'scatter',
      silent: true,
      z: 7,
      symbolSize: 7,
      itemStyle: {
        color: t.superficie,
        borderColor: t.tinta,
        borderWidth: 1.8,
      },
      label: {
        show: true,
        position: 'top',
        distance: 6,
        color: t.tintaSuave,
        fontFamily: t.fuenteTexto,
        fontSize: movil ? 10 : 11,
        formatter: () => `Máximo ${fmtNum.format(etiquetaPico?.v ?? 0)}`,
      },
      data: mostrarPico && pico ? [[pico.t, pico.v]] : [],
    });
  }

  return {
    ...opcionBase(t, movil, formatter, gridDe(movil, true), visibles, [
      SERIE.publicado,
      SERIE.mediana,
      SERIE.rango50,
      SERIE.rango95,
    ]),
    xAxis: ejeTiempo(t, movil, tInicio, tFinal, observado.length),
    yAxis: ejeCasos(t, movil, tope),
    series,
  };
}

// --- validación a cuatro semanas -------------------------------------------

export function opcionValidacion(
  t: TokensGrafico,
  datos: DatosValidacion,
  opciones: { movil: boolean; visibles?: Visibles },
): OpcionEcharts {
  const { movil } = opciones;
  const visibles = opciones.visibles ?? {};
  const semanas = datos.semanas;
  const porT = new Map(semanas.map((s) => [s.t, s]));

  const formatter = (params: unknown): string => {
    const lista = Array.isArray(params) ? params : [params];
    const eje = (lista[0] as { axisValue?: number } | undefined)?.axisValue;
    if (eje === undefined) return '';
    let fila = porT.get(eje);
    if (!fila) {
      let dist = Infinity;
      for (const s of semanas) {
        if (Math.abs(s.t - eje) < dist) {
          dist = Math.abs(s.t - eje);
          fila = s;
        }
      }
      if (dist > 3.5 * 86_400_000) return '';
    }
    if (!fila) return '';
    return tooltipHtml(t, {
      titulo: nombreSemana(fila.fecha),
      estado: 'Publicado',
      filas: [
        {
          nombre: SERIE.publicado,
          valor: fmtNum.format(fila.observado),
          muestra: { color: t.tinta, estilo: 'continua' },
        },
        {
          nombre: SERIE.mediana,
          valor: fmtNum.format(fila.mediana),
          muestra: { color: t.estimacion, estilo: 'punteada' },
        },
        {
          nombre: SERIE.rango50,
          valor: rango(fila.b50),
          muestra: { color: conAlfa(t.estimacion, 0.5), estilo: 'banda' },
          secundaria: true,
        },
        {
          nombre: SERIE.rango95,
          valor: rango(fila.b95),
          muestra: { color: conAlfa(t.estimacion, 0.22), estilo: 'banda' },
          secundaria: true,
        },
      ],
      nota: `Predicción a cuatro semanas con los datos anteriores a esa semana. Lo publicado quedó ${textoCobertura(fila.cobertura)}.`,
    });
  };

  const bandas = seriesBandas(
    t,
    conHuecos(semanas, (s) => s.mediana).map(([x]) => {
      const s = porT.get(x);
      return { t: x, b50: s ? s.b50 : null, b95: s ? s.b95 : null };
    }),
  );
  const fuera = semanas.filter((s) => s.cobertura === 'fuera');

  return {
    ...opcionBase(t, movil, formatter, gridDe(movil, false), visibles, [
      SERIE.publicado,
      SERIE.mediana,
      SERIE.rango50,
      SERIE.rango95,
      SERIE.fuera,
    ]),
    xAxis: ejeTiempo(
      t,
      movil,
      semanas[0].t,
      semanas[semanas.length - 1].t,
      semanas.length,
    ),
    yAxis: ejeCasos(t, movil),
    series: [
      bandas.base95,
      bandas.banda95,
      bandas.base50,
      bandas.banda50,
      lineaPublicada(
        t,
        conHuecos(semanas, (s) => s.observado),
        2,
      ),
      lineaMediana(
        t,
        conHuecos(semanas, (s) => s.mediana),
        {
          showSymbol: false,
          lineStyle: {
            width: 2,
            type: [6, 4],
            color: t.estimacion,
            cap: 'round',
          },
        },
      ),
      {
        id: 'fuera',
        name: SERIE.fuera,
        type: 'scatter',
        silent: true,
        z: 7,
        symbolSize: movil ? 7 : 8,
        itemStyle: {
          color: t.superficie,
          borderColor: t.tinta,
          borderWidth: 2,
        },
        data: fuera.map((s) => [s.t, s.observado]),
      },
    ],
  };
}

// --- contraste con lo observado --------------------------------------------

export interface GeometriaContraste {
  /** índices del modelo que cubre la gráfica del año */
  iIni: number;
  iFin: number;
  tMin: number;
  tMax: number;
  yMax: number;
}

const MARGEN_SEMANAS = 8; // contexto antes y después del año elegido

/** Escala fija para todo el año elegido: no salta al mover la semana de partida. */
export function geometriaContraste(
  modelo: ModeloContraste,
  origen: Origen,
): GeometriaContraste {
  const delAnio = modelo.porAnio.get(origen.anio) ?? [origen];
  const iIni = Math.max(0, delAnio[0].idx - MARGEN_SEMANAS);
  const iFin = Math.min(
    modelo.observado.length - 1,
    delAnio[delAnio.length - 1].idx + MARGEN_SEMANAS,
  );
  const obs = modelo.observado.slice(iIni, iFin + 1);
  let yMax = Math.max(...obs.map((p) => p.casos ?? 0));
  let tMax = marcaTiempo(obs[obs.length - 1].fecha);
  for (const o of delAnio) {
    for (const hz of o.horizontes ?? []) {
      if (!hz) continue;
      yMax = Math.max(yMax, hz.b95[1]);
      tMax = Math.max(tMax, marcaTiempo(hz.fecha));
    }
  }
  return {
    iIni,
    iFin,
    tMin: marcaTiempo(obs[0].fecha),
    tMax,
    yMax: Math.ceil((yMax * 1.1) / 50) * 50,
  };
}

export function opcionContraste(
  t: TokensGrafico,
  modelo: ModeloContraste,
  origen: Origen,
  opciones: { movil: boolean; visibles?: Visibles },
): OpcionEcharts {
  const { movil } = opciones;
  const visibles = opciones.visibles ?? {};
  const geo = geometriaContraste(modelo, origen);
  const obs = modelo.observado.slice(geo.iIni, geo.iFin + 1);
  const abanico = (origen.horizontes ?? []).filter(
    (h): h is Horizonte => h !== null,
  );
  const casosOrigen = origen.casos ?? 0;
  const tOrigen = marcaTiempo(origen.fecha);

  const porHorizonte = new Map(abanico.map((h) => [marcaTiempo(h.fecha), h]));
  const observadoPorT = new Map(
    obs.map((p) => [marcaTiempo(p.fecha), p.casos]),
  );

  const formatter = (params: unknown): string => {
    const lista = Array.isArray(params) ? params : [params];
    const eje = (lista[0] as { axisValue?: number } | undefined)?.axisValue;
    if (eje === undefined) return '';
    let cercano: number | null = null;
    let dist = Infinity;
    for (const k of observadoPorT.keys()) {
      if (Math.abs(k - eje) < dist) {
        dist = Math.abs(k - eje);
        cercano = k;
      }
    }
    for (const k of porHorizonte.keys()) {
      if (Math.abs(k - eje) < dist) {
        dist = Math.abs(k - eje);
        cercano = k;
      }
    }
    if (cercano === null || dist > 3.5 * 86_400_000) return '';
    const hz = porHorizonte.get(cercano);
    const casos = observadoPorT.get(cercano);
    const filas: FilaTooltip[] = [];
    if (casos !== undefined) {
      filas.push({
        nombre: SERIE.publicado,
        valor: casos === null ? 'sin publicar' : fmtNum.format(casos),
        muestra: { color: t.tinta, estilo: 'continua' },
      });
    }
    let estado = cercano === tOrigen ? 'Semana de partida' : 'Publicado';
    if (hz) {
      estado = `Predicción +${hz.h}`;
      filas.push(
        {
          nombre: SERIE.mediana,
          valor: fmtNum.format(hz.mediana),
          muestra: { color: t.estimacion, estilo: 'punteada' },
        },
        {
          nombre: SERIE.rango50,
          valor: rango(hz.b50),
          muestra: { color: conAlfa(t.estimacion, 0.5), estilo: 'banda' },
          secundaria: true,
        },
        {
          nombre: SERIE.rango95,
          valor: rango(hz.b95),
          muestra: { color: conAlfa(t.estimacion, 0.22), estilo: 'banda' },
          secundaria: true,
        },
      );
      if (hz.observado !== null) {
        const dif = hz.observado - hz.mediana;
        filas.push({
          nombre: 'Diferencia con la mediana',
          valor: `${dif > 0 ? '+' : dif < 0 ? '−' : ''}${fmtNum.format(Math.abs(dif))}`,
          secundaria: true,
        });
      }
    }
    return tooltipHtml(t, {
      titulo: nombreSemana(isoLocal(cercano)),
      estado,
      filas,
      nota:
        hz && hz.observado !== null
          ? `Lo publicado quedó ${textoCobertura(coberturaDe(hz.observado, hz.b50, hz.b95))}.`
          : undefined,
    });
  };

  const desdeOrigen = [
    {
      t: tOrigen,
      mediana: casosOrigen,
      b50: [casosOrigen, casosOrigen] as Rango,
      b95: [casosOrigen, casosOrigen] as Rango,
    },
    ...abanico.map((h) => ({
      t: marcaTiempo(h.fecha),
      mediana: h.mediana,
      b50: h.b50,
      b95: h.b95,
    })),
  ];
  const hayAbanico = abanico.length > 0;
  // En pantallas estrechas el año completo deja el abanico en unos pocos
  // píxeles: se encuadra la semana de partida con 20 semanas previas.
  const ventanaMin = movil
    ? Math.max(geo.tMin, tOrigen - 20 * SEMANA_MS)
    : geo.tMin;
  const ventanaMax = movil
    ? Math.min(geo.tMax, tOrigen + 10 * SEMANA_MS)
    : geo.tMax;
  const semanasVentana = movil
    ? Math.round((ventanaMax - ventanaMin) / SEMANA_MS)
    : geo.iFin - geo.iIni + 1 + 8;
  const bandas = seriesBandas(
    t,
    hayAbanico
      ? desdeOrigen.map((p) => ({ t: p.t, b50: p.b50, b95: p.b95 }))
      : [],
  );

  const conObservado = abanico.filter((h) => h.observado !== null);

  const marcas = {
    id: 'marcas',
    name: 'Marcas',
    type: 'line',
    silent: true,
    data: [],
    markLine: {
      silent: true,
      symbol: 'none',
      animation: false,
      lineStyle: {
        color: t.estimacion,
        type: [3, 3],
        width: 1.2,
        opacity: 0.85,
      },
      label: {
        show: true,
        position: 'end',
        align: tOrigen > (geo.tMin + geo.tMax) / 2 ? 'right' : 'left',
        distance: 16,
        color: t.tinta,
        fontFamily: t.fuenteTexto,
        fontSize: movil ? 10 : 11,
        fontWeight: 600,
        formatter: () =>
          `S${origen.semana} · ${fmtFechaCorta.format(fecha(origen.fecha))}`,
      },
      data: [{ xAxis: tOrigen }],
    },
  };

  return {
    ...opcionBase(
      t,
      movil,
      formatter,
      { ...gridDe(movil, false), top: 54 },
      visibles,
      [
        SERIE.publicado,
        SERIE.mediana,
        SERIE.rango50,
        SERIE.rango95,
        SERIE.diferencia,
      ],
    ),
    // la animación de entrada solo sirve al abrir: al arrastrar la semana de
    // partida la gráfica cambia de golpe, sin repetir el barrido
    animationDuration: 450,
    xAxis: ejeTiempo(t, movil, ventanaMin, ventanaMax, semanasVentana),
    yAxis: ejeCasos(t, movil, geo.yMax),
    series: [
      marcas,
      bandas.base95,
      bandas.banda95,
      bandas.base50,
      bandas.banda50,
      {
        id: 'diferencia',
        name: SERIE.diferencia,
        type: 'custom',
        silent: true,
        z: 4,
        encode: { x: 0, y: [1, 2] },
        renderItem: (
          _p: unknown,
          api: {
            value: (i: number) => number;
            coord: (v: number[]) => number[];
          },
        ) => {
          const a = api.coord([api.value(0), api.value(1)]);
          const b = api.coord([api.value(0), api.value(2)]);
          return {
            type: 'line',
            shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] },
            style: { stroke: t.estimacion, lineWidth: 2.5, opacity: 0.55 },
          };
        },
        data: conObservado.map((h) => [
          marcaTiempo(h.fecha),
          h.mediana,
          h.observado,
        ]),
      },
      lineaPublicada(
        t,
        obs.map(
          (p) => [marcaTiempo(p.fecha), p.casos] as [number, number | null],
        ),
        2,
      ),
      lineaMediana(
        t,
        hayAbanico
          ? desdeOrigen.map((p) => [p.t, p.mediana] as [number, number | null])
          : [],
        {
          symbolSize: (_v: unknown, p: { dataIndex: number }) =>
            p.dataIndex === 0 ? 0 : movil ? 4 : 5,
          lineStyle: {
            width: 2.2,
            type: [6, 4],
            color: t.estimacion,
            cap: 'round',
          },
        },
      ),
      {
        id: 'observado-horizontes',
        name: 'Observado en las semanas predichas',
        type: 'scatter',
        silent: true,
        z: 7,
        symbolSize: movil ? 7 : 8,
        itemStyle: {
          color: t.tinta,
          borderColor: t.superficie,
          borderWidth: 1.5,
        },
        data: conObservado.map((h) => [marcaTiempo(h.fecha), h.observado]),
      },
      {
        id: 'punto-origen',
        name: 'Semana de partida',
        type: 'scatter',
        silent: true,
        z: 9,
        symbolSize: 12,
        itemStyle: {
          color: t.estimacion,
          borderColor: t.superficie,
          borderWidth: 2.5,
        },
        data: origen.casos === null ? [] : [[tOrigen, origen.casos]],
      },
      {
        // asa para arrastrar, sobre el borde superior de la gráfica
        id: 'asa',
        name: 'Asa de la semana de partida',
        type: 'scatter',
        silent: true,
        z: 10,
        symbol: 'roundRect',
        symbolSize: [12, 16],
        itemStyle: {
          color: t.estimacion,
          borderColor: t.superficie,
          borderWidth: 1.5,
        },
        data: [[tOrigen, geo.yMax]],
      },
    ],
  };
}

function isoLocal(ts: number): string {
  const d = new Date(ts);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}
