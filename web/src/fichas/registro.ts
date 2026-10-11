// Fichas enriquecidas de la Biblioteca (ruta /biblioteca/fichas/[slug]).
// Cada ficha complementa a un documento con acordeones, que sigue siendo la
// referencia formal. Para sumar una ficha: crear su componente en src/fichas/,
// añadirla aquí y enlazarla desde el documento («ver ficha enriquecida de …»).

export interface MetadatosFicha {
  slug: string;
  titulo: string;
  subtitulo: string;
  etiquetas: string[];
  descripcion: string;
  documentacion: { href: string; etiqueta: string };
  disposicion?: 'centrada' | 'dividida';
}

export const FICHAS: MetadatosFicha[] = [
  {
    slug: 'm1-idoneidad-biofisica',
    titulo: 'Idoneidad biofísica (M1)',
    subtitulo:
      'Cómo el clima de una semana se convierte en un número de 0 a 1 y en el color de un departamento.',
    etiquetas: ['Módulo M1', 'Variable compuesta', 'Clima', 'Escala de 0 a 1'],
    descripcion:
      'Recorrido de la fuente al mapa: de dónde salen la temperatura, la humedad y la lluvia, cómo cada una pasa por su función, cómo se combinan en el Iv y cómo ese valor pinta un departamento. Al final, un laboratorio para mover los valores.',
    documentacion: {
      href: '/biblioteca/03-funciones#m1-idoneidad-biofísica-iv',
      etiqueta: 'Ver documentación de M1',
    },
  },
  {
    slug: 'm2-anomalia-climatica',
    titulo: 'Anomalía climática (M2)',
    subtitulo:
      'Cuánto se aparta la idoneidad de una semana de lo habitual en ese departamento.',
    etiquetas: [
      'Módulo M2',
      'Variable derivada',
      'Clima',
      'Desviaciones estándar',
    ],
    descripcion:
      'Recorrido del Iv de una semana a su anomalía: con qué años se compara, cómo se obtienen lo habitual y la dispersión, la fórmula de σ y el color del mapa. Al final, un laboratorio para mover los valores.',
    documentacion: {
      href: '/biblioteca/03-funciones#m2-anomalía-climática-continua',
      etiqueta: 'Ver documentación de M2',
    },
  },
  {
    slug: 'm3-presion-epidemiologica',
    titulo: 'Presión epidemiológica relativa (M3)',
    subtitulo:
      'Qué tan alta es la cifra de casos de una semana comparada con la historia del mismo departamento.',
    etiquetas: ['Módulo M3', 'Variable derivada', 'Casos', 'Percentil'],
    descripcion:
      'Recorrido de los casos de una semana a su percentil: qué años y semanas se comparan, cuándo no se calcula, cómo se obtienen el percentil y los cortes, el color del mapa y el canal endémico. Al final, un laboratorio para mover los casos.',
    documentacion: {
      href: '/biblioteca/03-funciones#m3-presión-epidemiológica-relativa',
      etiqueta: 'Ver documentación de M3',
    },
  },
  {
    slug: 'm4-integridad-vigilancia',
    titulo: 'Integridad de la vigilancia (M4)',
    subtitulo:
      'Qué tan completo, consistente y reciente es el dato con el que se hacen los demás módulos.',
    etiquetas: [
      'Módulo M4',
      'Calidad del dato',
      'Tres métricas',
      'Sin índice único',
    ],
    descripcion:
      'Los tres hechos que M4 da por separado: de cuántos departamentos hay fila, si el boletín cuadra con su total nacional y cuántas semanas pasaron desde el último dato de cada serie. Después, el color del mapa y un laboratorio para probarlos.',
    documentacion: {
      href: '/biblioteca/03-funciones#m4-integridad-de-la-vigilancia',
      etiqueta: 'Ver documentación de M4',
    },
  },
  {
    slug: 'modelo-predictivo',
    titulo: 'Modelo predictivo de dengue (Nowcast)',
    subtitulo:
      'Cómo los datos históricos de El Salvador, el clima departamental y 23 cuantiles de incertidumbre proyectan las próximas 8 semanas.',
    etiquetas: [
      'Nowcast',
      'Gradient Boosting',
      '23 cuantiles CDC/OPS',
      'Calibración CQR-r',
      'Regla de tendencia',
      'Horizonte a 8 semanas',
    ],
    descripcion:
      'Recorrido visual completo desde los insumos territoriales de El Salvador hasta el abanico probabilístico futuro. A la izquierda, formalidades, explicaciones detalladas y fórmulas matemáticas crudas; a la derecha, un escenario interactivo con barra de progreso y animaciones vívidas del flujo de variables y resultados.',
    documentacion: {
      href: '/biblioteca/05-sensibilidad-y-honestidad#predicción-de-casos-a-corto-plazo',
      etiqueta: 'Ver documentación formal de la predicción',
    },
    disposicion: 'dividida',
  },
];

export const RUTA_FICHAS = '/biblioteca/fichas';

export function rutaFicha(slug: string): string {
  return `${RUTA_FICHAS}/${slug}`;
}

export function fichaPorSlug(slug: string): MetadatosFicha | undefined {
  return FICHAS.find((f) => f.slug === slug);
}
