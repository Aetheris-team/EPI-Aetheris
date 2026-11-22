import type { Page } from '@playwright/test';

// Contraste de la predicción con lo observado (página /prediccion).
// Las dos respuestas de la predicción se simulan con una serie sintética de
// 2017 a 2019: las 30 primeras semanas no tienen predicción (falta historia),
// 2019 es temporada de prueba y la última semana es el ancla.

export const ANIOS = [2017, 2018, 2019];
const SEMANAS_SIN_MODELO = 30;

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function serieSintetica() {
  const inicio = new Date('2017-01-01T00:00:00Z');
  const semanas: {
    fecha: string;
    anio: number;
    semana: number;
    casos: number;
  }[] = [];
  let i = 0;
  for (const anio of ANIOS) {
    for (let s = 1; s <= 52; s++) {
      const d = new Date(inicio.getTime() + i * 7 * 86_400_000);
      semanas.push({
        fecha: iso(d),
        anio,
        semana: s,
        casos: Math.round(100 + 20 * Math.sin((i / 52) * 2 * Math.PI)),
      });
      i++;
    }
  }
  return semanas;
}

export function respuestas() {
  const semanas = serieSintetica();
  const ancla = semanas[semanas.length - 1];
  const origenes = semanas.slice(0, -1).map((s, idx) => {
    if (idx < SEMANAS_SIN_MODELO) {
      return {
        fecha: s.fecha,
        anio: s.anio,
        semana: s.semana,
        motivo: 'historia_insuficiente',
      };
    }
    const h = [1, 2, 3, 4, 5, 6, 7, 8].map((k) => {
      const med = s.casos;
      const conDato = idx + k < semanas.length;
      return [
        med,
        med - 10,
        med + 10,
        med - 40,
        med + 40,
        conDato ? 12 : null,
        conDato ? 18 : null,
      ];
    });
    return { fecha: s.fecha, anio: s.anio, semana: s.semana, h };
  });
  const estimacion = [1, 2, 3, 4, 5, 6, 7, 8].map((k) => {
    const d = new Date(
      new Date(`${ancla.fecha}T00:00:00Z`).getTime() + k * 7 * 86_400_000,
    );
    return {
      h: k,
      fecha: iso(d),
      anio: 2020,
      semana: k,
      cuantiles: [],
      mediana: 90,
      banda_50: [80, 100],
      banda_95: [50, 140],
    };
  });
  const principal = {
    disponible: true,
    aviso: 'Predicción estadística.',
    ancla: {
      fecha: ancla.fecha,
      anio: ancla.anio,
      semana: ancla.semana,
      casos: ancla.casos,
    },
    horizontes: [1, 2, 3, 4, 5, 6, 7, 8],
    observado: semanas
      .slice(-60)
      .map((s) => ({ fecha: s.fecha, casos: s.casos })),
    estimacion,
    backtest: { horizonte: 4, anios: [2019], puntos: [] },
    desempeno: {
      horizonte: 4,
      baseline: 'persistencia_rw',
      wis_modelo: 12,
      wis_baseline: 18,
      reduccion_wis: 0.33,
      skill_medio_por_anio: 0.33,
      skill_por_anio: { '2019': 0.33 },
      anios_ganados: 1,
      n_anios: 1,
      cobertura_50: 0.5,
      cobertura_95: 0.95,
    },
  };
  const retro = {
    disponible: true,
    aviso: 'Predicción estadística.',
    horizontes: [1, 2, 3, 4, 5, 6, 7, 8],
    anios_prueba: [2019],
    anio_excluido: 2020,
    aviso_anio_excluido: 'Aviso de 2020.',
    referencia_por_horizonte: Object.fromEntries(
      [1, 2, 3, 4, 5, 6, 7, 8].map((h) => [String(h), 'persistencia_rw']),
    ),
    primera_semana_con_prediccion: {
      fecha: semanas[SEMANAS_SIN_MODELO].fecha,
      anio: semanas[SEMANAS_SIN_MODELO].anio,
      semana: semanas[SEMANAS_SIN_MODELO].semana,
    },
    campos_horizonte: [
      'mediana',
      'b50_inf',
      'b50_sup',
      'b95_inf',
      'b95_sup',
      'wis_modelo',
      'wis_referencia',
    ],
    observado: semanas.map((s) => [s.fecha, s.casos]),
    origenes,
    resumen_por_anio: {
      '2019': {
        '4': {
          n: 48,
          wis_modelo: 12,
          wis_referencia: 18,
          skill: 0.333,
          cobertura_50: 0.5,
          cobertura_95: 0.94,
        },
      },
    },
  };
  return { principal, retro };
}

export async function simularApi(page: Page) {
  const { principal, retro } = respuestas();
  await page.route('**/datos/nowcast-dengue/retrospectivo.json', (ruta) =>
    ruta.fulfill({ json: retro }),
  );
  await page.route('**/datos/nowcast-dengue.json', (ruta) =>
    ruta.fulfill({ json: principal }),
  );
}
