import type { Page } from '@playwright/test';
import type {
  ClimaDengueAnio,
  ClimaDengueMultipais,
  VariableAsociacion,
  VariableClimaDengue,
} from '../../src/lib/tipos-analisis';

// Respuestas simuladas de GET /api/clima-dengue/por-anio y /multipais
// (ADR 0023 del monorepo). Tienen la forma de los artefactos reales con cifras
// sintéticas y cuatro países: El Salvador, Colombia, Panamá y Bermudas, que no
// tiene años evaluables. Sirven para probar la página sin tocar el backend.

export const ANIOS_SEMANALES = [
  2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023,
];
const ANIOS_PRUEBA = [2019, 2021, 2022, 2023, 2024];
const ANIOS_ANUALES = [
  2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024,
];
const VARIABLES_CLIMA: VariableClimaDengue[] = [
  'temp_media',
  'temp_max',
  'temp_min',
  'precipitation_sum',
  'precipitation_hours',
  'humedad_relativa_media',
  'punto_rocio',
];
const VARIABLES: VariableAsociacion[] = [...VARIABLES_CLIMA, 'oni'];
const AVISO = 'Descripción de datos de 2014 a 2024, sin atribución de causa.';

function correlacion(r: number): { r: number; ic95: [number, number] } {
  return { r, ic95: [r - 0.15, r + 0.15] };
}

function porVariable<T>(
  variables: readonly string[],
  construir: (variable: string, indice: number) => T,
): Record<string, T> {
  return Object.fromEntries(variables.map((v, i) => [v, construir(v, i)]));
}

function ciclo(base: number, amplitud: number): number[] {
  return Array.from(
    { length: 52 },
    (_, i) => base + amplitud * Math.sin((i / 52) * 2 * Math.PI),
  );
}

export function climaPorAnio(): ClimaDengueAnio {
  const aporte = (h: number) => {
    const rasgo = (valores: number[]) => ({
      por_anio: Object.fromEntries(
        ANIOS_PRUEBA.map((anio, i) => [anio, valores[i] * (h === 4 ? 1 : 0.5)]),
      ),
      anios_a_favor: valores.filter((v) => v > 0).length,
      anios: ANIOS_PRUEBA.length,
    });
    return {
      skill_I0: Object.fromEntries(ANIOS_PRUEBA.map((a) => [a, 0.1])),
      clima: rasgo([-0.04, 0.075, 0.314, -0.029, -0.227]),
      oni: rasgo([-0.027, 0.021, 0.004, -0.018, -0.012]),
      clima_y_oni: rasgo([-0.062, 0.098, 0.334, -0.053, -0.221]),
      anio: rasgo([0.013, 0.071, 0.032, 0.007, -0.034]),
    };
  };
  const asociacion = (desplazamiento: number) => ({
    pares: 48,
    ...(porVariable(VARIABLES, (_, i) =>
      correlacion(0.06 * i - 0.2 + desplazamiento),
    ) as Record<VariableAsociacion, { r: number; ic95: [number, number] }>),
  });
  return {
    disponible: true,
    aviso: AVISO,
    parametros: { anios: ANIOS_SEMANALES, horizonte: 4 },
    A1: Object.fromEntries(
      [1, 2, 3, 4, 5, 6, 7, 8].map((h) => [String(h), aporte(h)]),
    ),
    A2: {
      casos_r2_estacional: 0.5,
      casos_climatologia: ciclo(5, 0.5),
      por_variable: porVariable(VARIABLES_CLIMA, (_, i) => ({
        r2_estacional: 0.3 + 0.05 * i,
        desfase_mejor_semanas: i + 1,
        correlacion_en_el_mejor: 0.5,
        correlacion_por_desfase: { '0': 0.1, '1': 0.2 },
        climatologia: ciclo(25, 3),
      })),
    },
    A3: {
      por_anio: Object.fromEntries(
        ANIOS_SEMANALES.map((anio, i) => [anio, asociacion(0.01 * i)]),
      ),
      agrupado: { ...asociacion(0), pares: 433 },
    },
    A4: {
      por_anio: Object.fromEntries(
        ANIOS_SEMANALES.map((anio, i) => [
          anio,
          {
            casos_totales: 5000 + 1000 * i,
            semana_del_pico: 30 + i,
            valor_del_pico: 400 + 10 * i,
            oni_medio: 0.1 * i - 0.4,
            ...porVariable(VARIABLES_CLIMA, () => ({
              media: 25,
              anomalia_media: 0.1,
            })),
          },
        ]),
      ) as ClimaDengueAnio['A4']['por_anio'],
      spearman_total_vs_anomalia_media: porVariable(
        VARIABLES,
        () => 0.1,
      ) as ClimaDengueAnio['A4']['spearman_total_vs_anomalia_media'],
      n: ANIOS_SEMANALES.length,
    },
    A5: porVariable(VARIABLES, (variable) => {
      const lluvia =
        variable === 'precipitation_sum' || variable === 'precipitation_hours';
      return {
        anios_positivos: lluvia ? 1 : 5,
        anios_negativos: lluvia ? 8 : 4,
        anios_con_ic_sin_cero: lluvia ? 1 : 0,
        r_minimo: -0.4,
        r_maximo: 0.3,
        consistente: lluvia,
      };
    }) as ClimaDengueAnio['A5'],
  };
}

const PAISES = ['EL SALVADOR', 'COLOMBIA', 'PANAMA', 'BERMUDA'];
const PAISES_CON_ESTIMACION = ['EL SALVADOR', 'COLOMBIA', 'PANAMA'];

export function climaMultipais(): ClimaDengueMultipais {
  const perfil = (clave: string, i: number) => {
    const islaSinClima = clave === 'BERMUDA';
    return {
      centroide: [13.8, -88.9] as [number, number],
      total_anual: Object.fromEntries(
        ANIOS_ANUALES.map((a, k) => [a, 1000 * (i + 1) + 100 * k]),
      ),
      casos_semanales_medios: 100 * (i + 1),
      fraccion_semanas_cero: 0.02,
      r2_estacional: 0.2,
      semana_del_maximo: 36,
      desviacion_log_total_anual: 0.8,
      cociente_maximo_mediana: 3,
      baja_incidencia: islaSinClima,
      pais_extenso: clave === 'COLOMBIA',
      variables_climaticas: islaSinClima
        ? ([
            'precipitation_sum',
            'precipitation_hours',
          ] as VariableClimaDengue[])
        : VARIABLES_CLIMA,
    };
  };
  const rSenal: Record<string, number> = {
    'EL SALVADOR': 0.28,
    COLOMBIA: 0.95,
    PANAMA: 0.62,
    BERMUDA: 0.8,
  };
  const r9: Record<string, number> = {
    'EL SALVADOR': 0.46,
    COLOMBIA: 0.9,
    PANAMA: 0.5,
    BERMUDA: 0.7,
  };
  const anomalia = (k: number) =>
    Object.fromEntries(ANIOS_ANUALES.map((a, j) => [a, (j - 5) * 0.2 + k]));
  const p3 = (clave: string, i: number) => {
    if (clave === 'BERMUDA') {
      return {
        anios_evaluables: [],
        estimacion: false,
        por_variable: {},
      };
    }
    return {
      anios_evaluables: ANIOS_SEMANALES,
      estimacion: true,
      pares: Object.fromEntries(ANIOS_SEMANALES.map((a) => [a, 48])),
      por_variable: porVariable(VARIABLES, (variable, k) => {
        const lluviaSalvador =
          clave === 'EL SALVADOR' && variable === 'precipitation_hours';
        const r = lluviaSalvador ? -0.21 : 0.04 * k - 0.1 + 0.02 * i;
        return {
          agrupado: lluviaSalvador
            ? { r, ic95: [-0.38, -0.11] as [number, number] }
            : correlacion(r),
          por_anio: Object.fromEntries(
            ANIOS_SEMANALES.map((a) => [a, correlacion(r)]),
          ),
          anios_positivos: lluviaSalvador ? 1 : 5,
          anios_negativos: lluviaSalvador ? 8 : 4,
          consistente: lluviaSalvador,
        };
      }),
    };
  };
  const p4 = (clave: string) => ({
    casos: { r2_estacional: 0.17, climatologia: ciclo(5, 0.6) },
    variables: porVariable(
      clave === 'BERMUDA'
        ? ['precipitation_sum', 'precipitation_hours']
        : VARIABLES_CLIMA,
      (_, i) => ({
        r2_estacional: 0.4,
        desfase_mejor_semanas: 2 + i,
        correlacion_en_el_mejor: 0.5,
        en_el_borde: false,
        climatologia: ciclo(30, 20),
      }),
    ),
  });
  const corrida = (descripcion: string) => ({
    descripcion,
    disponible: true,
    anios: {
      '2014': {
        soporte_alto: 38,
        f1_modelo: 0.03,
        recall_alto_modelo: 0,
        f1_climatologia: 0.03,
        recall_alto_climatologia: 0,
        semillas_que_superan: 0,
        semillas: 1,
      },
    },
    anios_con_mayoria_que_supera: 0,
    anios_total: 1,
  });
  const posicion = (valor: number, paises: number) => ({
    posicion_de_menor_a_mayor: 1,
    paises,
    valor,
  });
  return {
    disponible: true,
    aviso: AVISO,
    parametros: {
      anios_anuales: ANIOS_ANUALES,
      anios_semanales: ANIOS_SEMANALES,
    },
    entradas: {
      casos: { archivo: 'casos.csv', sha256: 'a'.repeat(64) },
      clima: { archivo: 'clima.json', sha256: 'b'.repeat(64) },
    },
    P1: Object.fromEntries(PAISES.map((p, i) => [p, perfil(p, i)])),
    P2: {
      correlacion_media_pares: 0.45,
      primer_componente: 0.52,
      correlacion_senal_oni: 0.5,
      correlacion_media_pares_9_anios: 0.39,
      primer_componente_9_anios: 0.47,
      senal_regional: anomalia(0),
      por_pais: Object.fromEntries(
        PAISES.map((p, k) => [
          p,
          {
            r_con_senal: rSenal[p],
            ic95: [rSenal[p] - 0.4, Math.min(1, rSenal[p] + 0.3)] as [
              number,
              number,
            ],
            r_con_otros: rSenal[p] - 0.05,
            r_con_senal_9_anios: r9[p],
            r_con_otros_9_anios: r9[p] - 0.05,
            anomalia_anual: anomalia(0.1 * k),
          },
        ]),
      ),
      posicion_r_con_senal: {
        'EL SALVADOR': 1,
        PANAMA: 2,
        BERMUDA: 3,
        COLOMBIA: 4,
      },
      posicion_r_con_senal_9_anios: {
        PANAMA: 1,
        BERMUDA: 2,
        'EL SALVADOR': 3,
        COLOMBIA: 4,
      },
      estabilidad_el_salvador: {
        sin_cada_anio: { '2017': 0.16, '2024': 0.46 },
        sin_cada_pais: { COLOMBIA: 0.25, PANAMA: 0.32 },
        minimo: 0.16,
        maximo: 0.46,
      },
      centroamerica: { PANAMA: 0.55, 'EL SALVADOR': 0.12 },
      centroamerica_9_anios: { PANAMA: 0.34, 'EL SALVADOR': 0.19 },
      sin_baja_incidencia: {
        excluidos: ['BERMUDA'],
        r_con_senal: rSenal,
        posicion: { 'EL SALVADOR': 1 },
        correlacion_media_pares: 0.45,
        primer_componente: 0.5,
      },
    },
    P3: Object.fromEntries(PAISES.map((p, i) => [p, p3(p, i)])),
    P4: Object.fromEntries(PAISES.map((p) => [p, p4(p)])),
    P5: {
      A: corrida('solo El Salvador, entrenando con los otros paises'),
      B: corrida('regional'),
      C: corrida('regional con ONI'),
    },
    P6: {
      r_con_senal: posicion(0.28, PAISES.length),
      r_con_otros: posicion(0.2, PAISES.length),
      desviacion_log_total_anual: posicion(0.86, PAISES.length),
      r2_estacional_casos: posicion(0.17, PAISES.length),
      r_agrupado_precipitation_sum: posicion(
        -0.16,
        PAISES_CON_ESTIMACION.length,
      ),
      r_agrupado_oni: posicion(-0.09, PAISES_CON_ESTIMACION.length),
    },
    referencia_el_salvador_base_de_datos: {
      agrupado: {
        pares: 433,
        ...(porVariable(VARIABLES, () => correlacion(0.05)) as Record<
          VariableAsociacion,
          { r: number; ic95: [number, number] }
        >),
      },
      consistencia: porVariable(VARIABLES, () => ({
        anios_positivos: 5,
        anios_negativos: 4,
        anios_con_ic_sin_cero: 0,
        r_minimo: -0.2,
        r_maximo: 0.3,
        consistente: false,
      })) as NonNullable<
        ClimaDengueMultipais['referencia_el_salvador_base_de_datos']
      >['consistencia'],
    },
  };
}

export type ModoRespuesta = 'datos' | 'no-disponible' | 'error';

/** Simula los dos endpoints; `modo` decide si responden datos, "sin dato" o 500. */
export async function simularClimaDengue(
  page: Page,
  modo: { porAnio?: ModoRespuesta; multipais?: ModoRespuesta } = {},
): Promise<void> {
  const responder =
    (cuerpo: () => unknown, estado: ModoRespuesta) =>
    async (ruta: import('@playwright/test').Route) => {
      if (estado === 'error') {
        await ruta.fulfill({ status: 500, body: 'error' });
        return;
      }
      await ruta.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          estado === 'no-disponible'
            ? {
                disponible: false,
                motivo: 'El análisis aún no está generado en este despliegue.',
                aviso: AVISO,
              }
            : cuerpo(),
        ),
      });
    };
  await page.route(
    '**/datos/clima-dengue/por-anio.json',
    responder(climaPorAnio, modo.porAnio ?? 'datos'),
  );
  await page.route(
    '**/datos/clima-dengue/multipais.json',
    responder(climaMultipais, modo.multipais ?? 'datos'),
  );
}
