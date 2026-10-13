// Proyecta la geometría de los departamentos (GeoJSON) a trazados SVG. Usa una
// proyección equirectangular con el ancho corregido por la latitud media, que
// a la escala de un país pequeño como El Salvador se ve idéntica a proyecciones
// conformes y cartográficas estándar.
//
// Proporciona trazados limpios (d), centroides visuales y puntos interiores
// óptimos para etiquetas legibles (centroX, centroY), nombres normalizados y
// códigos cortos/abreviaturas oficiales (ISO 3166-2:SV) para pantallas estrechas.

import { redondear } from './estadistica.ts';

export type Anillo = number[][];

export interface GeometriaDepartamento {
  type: 'Polygon' | 'MultiPolygon';
  coordinates: Anillo[] | Anillo[][];
}

export interface GeoDepartamentos {
  features: {
    properties: {
      codigo: string;
      shapeName?: string;
      nombre?: string;
      [key: string]: unknown;
    };
    geometry: GeometriaDepartamento;
  }[];
}

export interface DepartamentoSvg {
  codigo: string;
  nombre?: string;
  /** Abreviatura oficial de 2 letras (ej. 'AH', 'SS', 'SA') */
  abreviatura?: string;
  /** Código corto (alias de abreviatura para compatibilidad) */
  codigoCorto?: string;
  d: string;
  centroX?: number;
  centroY?: number;
}

export interface BoundingBoxGeo {
  lonMin: number;
  lonMax: number;
  latMin: number;
  latMax: number;
}

export interface MapaSvg {
  ancho: number;
  alto: number;
  viewBox: string;
  limitesGeo?: BoundingBoxGeo;
  departamentos: DepartamentoSvg[];
}

/**
 * Abreviaturas oficiales de los 14 departamentos de El Salvador (ISO 3166-2:SV).
 */
export const ABREVIATURAS_DEPARTAMENTOS: Readonly<Record<string, string>> = {
  'SV-AH': 'AH',
  'SV-CA': 'CA',
  'SV-CH': 'CH',
  'SV-CU': 'CU',
  'SV-LI': 'LI',
  'SV-MO': 'MO',
  'SV-PA': 'PA',
  'SV-SA': 'SA',
  'SV-SM': 'SM',
  'SV-SO': 'SO',
  'SV-SS': 'SS',
  'SV-SV': 'SV',
  'SV-UN': 'UN',
  'SV-US': 'US',
};

/**
 * Puntos interiores óptimos (longitud, latitud) calibrados para colocar etiquetas
 * de texto armoniosamente dentro de cada departamento de El Salvador.
 *
 * Resuelven colisiones y concavidades críticas:
 * - Cuscatlán (SV-CU): centrado en la zona oriental para no solaparse con San Salvador
 *   ni invadir la cuenca del Lago de Ilopango.
 * - San Salvador (SV-SS): centrado en el área metropolitana despejada, manteniendo
 *   distancia armónica de Cuscatlán y La Libertad.
 * - La Paz (SV-PA): centrado en el amplio sector central meridional, evitando el
 *   istmo estrecho colindante con Ilopango.
 * - Usulután (SV-US): ubicado en el cuerpo continental central, evitando que la
 *   alta densidad de vértices de la Bahía de Jiquilisco desplace la etiqueta a la costa.
 * - La Unión (SV-UN): centrado en tierra firme continental, excluyendo el arrastre
 *   de las islas del Golfo de Fonseca.
 */
export const CENTROIDES_EL_SALVADOR: Readonly<
  Record<string, [number, number]>
> = {
  'SV-AH': [-89.9119, 13.8516],
  'SV-CA': [-88.6794, 13.9002],
  'SV-CH': [-89.1487, 14.2039],
  'SV-CU': [-88.9579, 13.7639],
  'SV-LI': [-89.3832, 13.6261],
  'SV-MO': [-88.1033, 13.7814],
  'SV-PA': [-88.9922, 13.4953],
  'SV-SA': [-89.5728, 14.0636],
  'SV-SM': [-88.2274, 13.4657],
  'SV-SO': [-89.6767, 13.6787],
  'SV-SS': [-89.1517, 13.7211],
  'SV-SV': [-88.7344, 13.6634],
  'SV-UN': [-87.9038, 13.4982],
  'SV-US': [-88.5503, 13.3549],
};

function anillos(g: GeometriaDepartamento): Anillo[] {
  return g.type === 'Polygon'
    ? (g.coordinates as Anillo[])
    : (g.coordinates as Anillo[][]).flat();
}

/**
 * Determina si un punto en coordenadas 2D cae dentro de un anillo de polígono
 * usando ray casting estándar.
 */
function puntoEnAnillo(
  px: number,
  py: number,
  anillo: [number, number][],
): boolean {
  let dentro = false;
  for (let i = 0, j = anillo.length - 1; i < anillo.length; j = i++) {
    const xi = anillo[i][0];
    const yi = anillo[i][1];
    const xj = anillo[j][0];
    const yj = anillo[j][1];
    const intersecta =
      yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi;
    if (intersecta) dentro = !dentro;
  }
  return dentro;
}

/**
 * Calcula el centroide geométrico ponderado por área (fórmula del área de Gauss / Green)
 * de un conjunto de anillos proyectados. Si el centroide cae fuera del polígono
 * (geometría cóncava o multipolígono), busca el punto interior con mejor holgura.
 */
function centroideAnillos(
  anillosProyectados: [number, number][][],
): [number, number] {
  let areaTotal = 0;
  let sumaCx = 0;
  let sumaCy = 0;
  let verticesTotales = 0;
  let sumaVx = 0;
  let sumaVy = 0;

  for (const anillo of anillosProyectados) {
    if (anillo.length < 3) continue;
    let areaAnillo = 0;
    let cxAnillo = 0;
    let cyAnillo = 0;
    for (let i = 0; i < anillo.length - 1; i++) {
      const [x0, y0] = anillo[i];
      const [x1, y1] = anillo[i + 1];
      const cruz = x0 * y1 - x1 * y0;
      areaAnillo += cruz;
      cxAnillo += (x0 + x1) * cruz;
      cyAnillo += (y0 + y1) * cruz;
      sumaVx += x0;
      sumaVy += y0;
      verticesTotales += 1;
    }
    areaAnillo /= 2;
    const absArea = Math.abs(areaAnillo);
    if (absArea > 1e-6) {
      areaTotal += absArea;
      sumaCx += (cxAnillo / (6 * areaAnillo)) * absArea;
      sumaCy += (cyAnillo / (6 * areaAnillo)) * absArea;
    }
  }

  if (areaTotal > 1e-6) {
    const cx = sumaCx / areaTotal;
    const cy = sumaCy / areaTotal;

    // Si el centroide cae dentro del polígono, es el punto óptimo
    const caeDentro = anillosProyectados.some((a) => puntoEnAnillo(cx, cy, a));
    if (caeDentro) {
      return [cx, cy];
    }

    // Para formas cóncavas cuyo centroide cae fuera, buscar el punto medio
    // entre el centroide y los vértices interiores que maximice la interioridad
    for (const anillo of anillosProyectados) {
      for (let i = 0; i < anillo.length - 1; i++) {
        const px = (anillo[i][0] + cx) / 2;
        const py = (anillo[i][1] + cy) / 2;
        if (anillosProyectados.some((a) => puntoEnAnillo(px, py, a))) {
          return [px, py];
        }
      }
    }
    return [cx, cy];
  }

  if (verticesTotales > 0) {
    return [sumaVx / verticesTotales, sumaVy / verticesTotales];
  }

  return [0, 0];
}

/**
 * Normaliza el nombre de un departamento eliminando prefijos como 'Departamento de '.
 */
export function normalizarNombreDepartamento(
  nombre?: string,
): string | undefined {
  if (!nombre) return undefined;
  return nombre.replace(/^Departamento de /i, '').trim();
}

/**
 * Obtiene la abreviatura oficial o código corto (ej. 'AH', 'SS', 'SA') a partir
 * del código de departamento (ej. 'SV-AH', 'SV-SS').
 */
export function obtenerAbreviaturaDepartamento(codigo: string): string {
  if (ABREVIATURAS_DEPARTAMENTOS[codigo]) {
    return ABREVIATURAS_DEPARTAMENTOS[codigo];
  }
  return codigo.includes('-') ? codigo.split('-').pop()! : codigo;
}

/**
 * Proyecta la colección de departamentos (GeoJSON) en un sistema de coordenadas SVG.
 *
 * - `ancho`: ancho total del viewBox en píxeles. El alto se deriva de la proporción
 *   geográfica real corregida por el coseno de la latitud media.
 * - `margen`: margen de seguridad en píxeles para evitar recortes en bordes y trazos gruesos.
 * - `tolerancia`: umbral en píxeles para descartar vértices redundantes muy próximos.
 */
export function proyectarDepartamentos(
  geo: GeoDepartamentos,
  ancho: number,
  margen = 6,
  tolerancia = 0.5,
): MapaSvg {
  if (!geo.features || geo.features.length === 0) {
    const altoVacio = Math.round(ancho * 0.6);
    return {
      ancho,
      alto: altoVacio,
      viewBox: `0 0 ${ancho} ${altoVacio}`,
      departamentos: [],
    };
  }

  let lonMin = Infinity;
  let lonMax = -Infinity;
  let latMin = Infinity;
  let latMax = -Infinity;

  for (const f of geo.features) {
    for (const anillo of anillos(f.geometry)) {
      for (const [lon, lat] of anillo) {
        lonMin = Math.min(lonMin, lon);
        lonMax = Math.max(lonMax, lon);
        latMin = Math.min(latMin, lat);
        latMax = Math.max(latMax, lat);
      }
    }
  }

  const factor = Math.cos((((latMin + latMax) / 2) * Math.PI) / 180);
  const anchoGeo = (lonMax - lonMin) * factor;
  const altoGeo = latMax - latMin;
  const escala = (ancho - 2 * margen) / (anchoGeo || 1);
  const alto = Math.round(altoGeo * escala + 2 * margen);

  const x = (lon: number) => margen + (lon - lonMin) * factor * escala;
  const y = (lat: number) => margen + (latMax - lat) * escala;

  const departamentos: DepartamentoSvg[] = geo.features.map((f) => {
    let d = '';
    const anillosProyectados: [number, number][][] = [];

    for (const anillo of anillos(f.geometry)) {
      let ultimo: [number, number] | null = null;
      let trazo = '';
      const anilloPx: [number, number][] = [];

      for (const [lon, lat] of anillo) {
        const px = x(lon);
        const py = y(lat);
        anilloPx.push([px, py]);

        if (ultimo && Math.hypot(px - ultimo[0], py - ultimo[1]) < tolerancia) {
          continue;
        }
        trazo += `${trazo === '' ? 'M' : 'L'}${redondear(px, 1)} ${redondear(py, 1)}`;
        ultimo = [px, py];
      }
      if (trazo !== '') d += `${trazo}Z`;
      if (anilloPx.length > 0) anillosProyectados.push(anilloPx);
    }

    const codigo = f.properties.codigo;
    const abreviatura = obtenerAbreviaturaDepartamento(codigo);
    const codigoCorto = abreviatura;

    const rawNombre = f.properties.nombre ?? f.properties.shapeName;
    const nombre = normalizarNombreDepartamento(
      typeof rawNombre === 'string' ? rawNombre : undefined,
    );

    let centroX: number | undefined;
    let centroY: number | undefined;

    if (codigo && CENTROIDES_EL_SALVADOR[codigo]) {
      const [lonC, latC] = CENTROIDES_EL_SALVADOR[codigo];
      centroX = redondear(x(lonC), 1);
      centroY = redondear(y(latC), 1);
    } else {
      const [cx, cy] = centroideAnillos(anillosProyectados);
      centroX = redondear(cx, 1);
      centroY = redondear(cy, 1);
    }

    return {
      codigo,
      nombre,
      abreviatura,
      codigoCorto,
      d,
      centroX,
      centroY,
    };
  });

  return {
    ancho,
    alto,
    viewBox: `0 0 ${ancho} ${alto}`,
    limitesGeo: {
      lonMin,
      lonMax,
      latMin,
      latMax,
    },
    departamentos,
  };
}
