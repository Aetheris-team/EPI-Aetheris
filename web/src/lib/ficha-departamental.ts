export interface SemanaM1M2 {
  semana_epi: number;
  iv_real: number | null;
  p25_baseline: number | null;
  mediana_baseline: number | null;
  p75_baseline: number | null;
  anomaly_sigma: number | null;
}

export interface DetallePresion {
  casos_observados: number | null;
  percentil: number | null;
  categoria: 'baja' | 'media' | 'alta' | null;
  p50_baseline: number | null;
  p75_baseline: number | null;
  n_obs_baseline: number;
  anios_baseline: number;
  nota?: string;
}

export interface SemanaPresion {
  semana_epi: number;
  probable: DetallePresion;
  confirmado: DetallePresion;
}

export interface RespuestaM1M2 {
  departamento_codigo: string;
  departamento_nombre: string;
  anio: number;
  semanas: SemanaM1M2[];
  aviso: string;
}

export interface RespuestaPresion {
  departamento_codigo: string;
  departamento_nombre: string;
  anio: number;
  semanas: SemanaPresion[];
  aviso: string;
}

export interface RespuestaSerieRespiratoria {
  disponible?: boolean;
  motivo?: string;
  departamento_codigo?: string;
  departamento_nombre?: string;
  anios?: number[];
  series?: Record<string, Array<[number, number]>>;
  aviso?: string;
}

export interface AlertaRespuesta {
  id: number;
  tipo: 'dengue' | 'respiratorio';
  nivel: 'informativo' | 'atencion' | 'intensificacion';
  titulo: string;
  contexto: string;
  indicaciones: string;
  fuente: string;
  autor: string;
  vigente_desde: string;
  vigente_hasta: string | null;
  activa: boolean;
  contacto_vigilancia?: string | null;
  signos_alarma?: string | null;
  criterios_referencia?: string | null;
  acciones_comunitarias?: string | null;
  etiqueta?: string | null;
}

export interface PayloadAlertasRespuesta {
  aviso: string;
  ultima_revision: string;
  alertas: AlertaRespuesta[];
}

// Reservas solo para cuando la respuesta del endpoint no llega (fallo de red).
// Son copia literal de los AVISO_HONESTIDAD_* del backend (backend/api/main.py,
// ira.py, neumonias.py, alertas.py); no se redactan ni se resumen aquí. Si el
// endpoint responde, la ficha usa el campo `aviso` de esa respuesta.
export const AVISO_DEFECTO_IDONEIDAD =
  'Índice de idoneidad biofísica (Iv) para Aedes aegypti, a partir de clima ERA5-Land (temperatura, precipitación a 2 semanas, humedad). Describe condición ambiental, no incidencia ni riesgo: los casos MINSAL y la presión epidemiológica se detienen en 2023. La cobertura climática depende de la última ingesta. Una validación retrospectiva mostró que no anticipa de forma consistente el ascenso de casos; el componente de humedad es una estimación propia del equipo.';

export const AVISO_DEFECTO_PRESION =
  "Percentil del conteo observado (MINSAL, desacumulado) dentro de la historia del propio departamento (años base 2018, 2019, 2021-2023; ventana ±1 semana, leave-one-out). Los cortes P50/P75 son deliberadamente sensibles: 'alta' puede aparecer en años de baja transmisión. 'probable' y 'confirmado' son series separadas.";

export const AVISO_DEFECTO_IRA =
  'Infección Respiratoria Aguda (IRA), boletines MINSAL 2018-2023 (sin 2020). Conteo semanal notificado por departamento, sin desagregación probable/confirmado. Los huecos (semanas sin fila) son ausencias reales de la fuente, nunca ceros interpolados.';

export const AVISO_DEFECTO_NEUMONIAS =
  'Neumonías, boletines MINSAL 2018-2023 (sin 2020). Conteo semanal notificado por departamento, sin split probable/confirmado. Los huecos son ausencias reales de la fuente, nunca ceros interpolados.';

export const AVISO_DEFECTO_PREVENCION =
  'Alertas redactadas por el equipo de vigilancia del proyecto (INSAMT, Equipo 4) a partir de datos públicos históricos (MINSAL, OpenDengue, Open-Meteo). No reemplazan los lineamientos del MINSAL ni el criterio clínico.';

export function encontrarUltimaSemanaM1M2(
  semanas: SemanaM1M2[],
): SemanaM1M2 | null {
  for (let i = semanas.length - 1; i >= 0; i--) {
    if (semanas[i].iv_real !== null || semanas[i].anomaly_sigma !== null) {
      return semanas[i];
    }
  }
  return null;
}

export function encontrarUltimaSemanaPresion(
  semanas: SemanaPresion[],
  serie: 'probable' | 'confirmado',
): { semana_epi: number; detalle: DetallePresion } | null {
  for (let i = semanas.length - 1; i >= 0; i--) {
    const detalle = semanas[i]?.[serie];
    if (detalle && detalle.percentil !== null) {
      return { semana_epi: semanas[i].semana_epi, detalle };
    }
  }
  return null;
}

export function formatearSigma(sigma: number | null | undefined): string {
  if (sigma === null || sigma === undefined || Number.isNaN(sigma)) {
    return 'Sin dato';
  }
  const signo = sigma > 0 ? '+' : '';
  return `${signo}${sigma.toFixed(2)} σ`;
}

export function formatearPercentil(
  percentil: number | null | undefined,
): string {
  if (
    percentil === null ||
    percentil === undefined ||
    Number.isNaN(percentil)
  ) {
    return 'Sin dato';
  }
  return `P${percentil.toFixed(1)}`;
}

export function formatearCategoria(
  categoria: 'baja' | 'media' | 'alta' | null | undefined,
): string {
  if (!categoria) return 'Sin clasificación';
  switch (categoria) {
    case 'baja':
      return 'Baja (≤ P50 histórico)';
    case 'media':
      return 'Media (P50–P75 histórico)';
    case 'alta':
      return 'Alta (> P75 histórico)';
  }
}
