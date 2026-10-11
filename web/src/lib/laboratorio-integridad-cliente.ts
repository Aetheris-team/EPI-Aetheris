// Comportamiento del laboratorio de la ficha de integridad de la vigilancia
// (LaboratorioIntegridad.astro). Cada cambio vuelve a calcular al instante;
// «Calcular paso a paso» recorre el método en orden (cuadrícula, cuadre,
// estado, color) sobre un cálculo ya hecho. Con las animaciones apagadas se
// salta y se muestra el resultado.

import {
  esNoDisponible,
  motivoNoDisponible,
  renderErrorFuente,
  renderSinDato,
} from '../components/estado-async';
import { obtenerIntegridadVigilancia } from './analisis-api';
import { animacionesActivas } from './animaciones';
import { colorIntegridad } from './colores';
import { DEPARTAMENTOS, obtenerDepartamento } from './departamentos';
import { nombreSerie, textoRezago, textoUltimaSemana } from './frescura';
import {
  ETIQUETAS_ESTADO,
  PRESETS_INTEGRIDAD,
  completitudSemana,
  discrepancia,
  estadoIntegridad,
  type EstadoIntegridad,
} from './integridad';
import {
  MS_ETAPA,
  activarEtapa,
  cerrarEtapa,
  esperar,
  limpiarEtapas,
  prepararEtapas,
} from './recorrido';

const CATALOGO = DEPARTAMENTOS.map((d) => [d.codigo, d.nombre] as const);

function conSigno(n: number | null): string {
  if (n === null) return 'vacía';
  if (n > 0) return `+${n}`;
  if (n < 0) return `−${Math.abs(n)}`;
  return '0';
}

export function iniciarLaboratorioIntegridad(raiz: HTMLElement): void {
  const q = <T extends Element>(selector: string): T => {
    const elemento = raiz.querySelector<T>(selector);
    if (!elemento) throw new Error(`Laboratorio de M4: falta ${selector}`);
    return elemento;
  };

  const controles = q<HTMLFieldSetElement>('[data-lab-controles]');
  const selectorDepto = q<HTMLSelectElement>('[data-lab-depto]');
  const entradaSemana = q<HTMLInputElement>('[data-lab-semana]');
  const selectorSerie = q<HTMLSelectElement>('[data-lab-serie]');
  const entradaSuma = q<HTMLInputElement>('[data-lab-suma]');
  const entradaPublicado = q<HTMLInputElement>('[data-lab-publicado]');
  const casillas = Array.from(
    raiz.querySelectorAll<HTMLInputElement>('[data-cuadricula-casilla]'),
  );
  const botonCalcular = q<HTMLButtonElement>('[data-lab-calcular]');
  const estado = q<HTMLElement>('[data-lab-estado]');
  const textoCompletitud = q<HTMLElement>('[data-lab-completitud]');
  const textoN = q<HTMLElement>('[data-lab-n]');
  const textoDiferencia = q<HTMLElement>('[data-lab-diferencia]');
  const textoEstado = q<HTMLElement>('[data-lab-estado-depto]');
  const frase = q<HTMLElement>('[data-lab-frase]');
  const real = q<HTMLElement>('[data-lab-real]');
  const mapa = q<SVGElement>('[data-mapa-ficha-svg]');
  const etapas = ['cuadricula', 'cuadre', 'estado', 'color'].map((nombre) =>
    q<HTMLElement>(`[data-lab-etapa="${nombre}"]`),
  );

  let codigo = raiz.dataset.codigoInicial ?? 'SV-SS';
  let enSecuencia = false;
  let temporizadorAnuncio: ReturnType<typeof setTimeout> | undefined;

  const nombreDepto = () => obtenerDepartamento(codigo)?.nombre ?? codigo;
  const leerNumero = (campo: HTMLInputElement): number | null => {
    if (campo.value.trim() === '') return null;
    const n = Number(campo.value);
    return Number.isFinite(n) ? n : null;
  };

  function leer() {
    const presentes = casillas.filter((c) => c.checked).map((c) => c.value);
    const completitud = completitudSemana(CATALOGO, presentes);
    const diferencia = discrepancia(
      leerNumero(entradaSuma),
      leerNumero(entradaPublicado),
    );
    // En el laboratorio el boletín cuadra si la diferencia es cero; sin uno
    // de los dos lados, el cuadre queda sin dato.
    const cuadra = diferencia === null ? null : diferencia === 0;
    const presente = presentes.includes(codigo);
    const estadoDepto = estadoIntegridad(presente, cuadra);
    return { completitud, diferencia, cuadra, estadoDepto };
  }

  function anunciar(mensaje: string, retraso = 0): void {
    clearTimeout(temporizadorAnuncio);
    temporizadorAnuncio = setTimeout(() => {
      estado.textContent = mensaje;
    }, retraso);
  }

  function pintarMapa(estadoDepto: EstadoIntegridad | null): void {
    mapa.querySelectorAll<SVGPathElement>('[data-codigo]').forEach((ruta) => {
      const activo = ruta.dataset.codigo === codigo;
      ruta.classList.toggle('seleccionado', activo);
      if (activo && estadoDepto !== null) {
        ruta.style.setProperty('--relleno', colorIntegridad(estadoDepto));
      } else ruta.style.removeProperty('--relleno');
    });
    mapa.setAttribute(
      'aria-label',
      estadoDepto === null
        ? `Mapa de El Salvador con ${nombreDepto()} sin estado`
        : `Mapa de El Salvador con ${nombreDepto()} en el estado «${ETIQUETAS_ESTADO[estadoDepto]}»`,
    );
  }

  function textoCuadre(c: ReturnType<typeof leer>): string {
    if (c.cuadra === null)
      return 'falta un lado del boletín y el cuadre queda sin dato';
    return c.cuadra ? 'el boletín cuadra' : 'el boletín no cuadra';
  }

  function textoResultado(c: ReturnType<typeof leer>): string {
    const serie =
      selectorSerie.value === 'confirmado' ? 'confirmado' : 'probable';
    return (
      `Semana ${entradaSemana.value}, serie ${serie}: ${c.completitud.n} de ${c.completitud.esperado} departamentos con fila; ` +
      `${textoCuadre(c)}. ${nombreDepto()}: ${ETIQUETAS_ESTADO[c.estadoDepto]}.`
    );
  }

  function pintarCompletitud(c: ReturnType<typeof leer>): void {
    const faltan = c.completitud.departamentos
      .filter((d) => !d.presente)
      .map((d) => d.nombre);
    textoN.textContent = `${c.completitud.n} de ${c.completitud.esperado}`;
    textoCompletitud.textContent =
      faltan.length === 0
        ? `${c.completitud.n} de ${c.completitud.esperado} departamentos con fila.`
        : `${c.completitud.n} de ${c.completitud.esperado} departamentos con fila. Sin fila (huecos, no ceros): ${faltan.join(', ')}.`;
  }

  function actualizar(): void {
    const c = leer();
    pintarCompletitud(c);
    textoDiferencia.textContent = conSigno(c.diferencia);
    textoEstado.textContent = ETIQUETAS_ESTADO[c.estadoDepto];
    frase.textContent = textoResultado(c);
    pintarMapa(c.estadoDepto);
  }

  const resumen = () => textoResultado(leer());

  // ---- Recorrido paso a paso -------------------------------------------

  async function calcular(): Promise<void> {
    if (enSecuencia) return;
    if (!animacionesActivas()) {
      actualizar();
      anunciar(resumen());
      return;
    }
    enSecuencia = true;
    controles.disabled = true;
    casillas.forEach((c) => (c.disabled = true));
    botonCalcular.setAttribute('aria-busy', 'true');
    const c = leer();
    prepararEtapas(etapas);
    for (const t of [textoN, textoDiferencia, textoEstado]) t.textContent = '·';
    textoCompletitud.textContent = '';
    frase.textContent = '';
    pintarMapa(null);

    const textos = [
      `Paso 1 de 4: ${c.completitud.n} de ${c.completitud.esperado} departamentos tienen fila.`,
      `Paso 2 de 4: la diferencia es ${conSigno(c.diferencia)}; ${textoCuadre(c)}.`,
      `Paso 3 de 4: ${nombreDepto()} queda en «${ETIQUETAS_ESTADO[c.estadoDepto]}».`,
      `Paso 4 de 4: ese estado pinta ${nombreDepto()}.`,
    ];
    for (let i = 0; i < etapas.length; i += 1) {
      activarEtapa(etapas[i]);
      anunciar(textos[i]);
      if (i === 0) pintarCompletitud(c);
      else if (i === 1) textoDiferencia.textContent = conSigno(c.diferencia);
      else if (i === 2)
        textoEstado.textContent = ETIQUETAS_ESTADO[c.estadoDepto];
      else pintarMapa(c.estadoDepto);
      await esperar(MS_ETAPA);
      cerrarEtapa(etapas[i]);
    }

    limpiarEtapas(etapas);
    actualizar();
    anunciar(resumen());
    controles.disabled = false;
    casillas.forEach((x) => (x.disabled = false));
    botonCalcular.removeAttribute('aria-busy');
    botonCalcular.focus();
    enSecuencia = false;
  }

  // ---- Integridad que publica el sistema --------------------------------

  async function cargarReal(): Promise<void> {
    real.setAttribute('aria-busy', 'true');
    const p = document.createElement('p');
    p.className = 'lab-cargando';
    p.textContent = 'Consultando la integridad de la vigilancia…';
    real.replaceChildren(p);
    try {
      const datos = await obtenerIntegridadVigilancia();
      if (esNoDisponible(datos)) {
        renderSinDato(real, motivoNoDisponible(datos));
        return;
      }
      const filas = Object.entries(datos.antiguedad ?? {});
      if (filas.length === 0) {
        renderSinDato(real, 'La API no informa la antigüedad de las series.');
        return;
      }
      real.removeAttribute('aria-busy');
      // Nodos de texto y no innerHTML: claves y valores llegan de la API.
      const titulo = document.createElement('p');
      titulo.textContent = 'Antigüedad actual de cada serie:';
      const tabla = document.createElement('table');
      const cabecera = tabla.createTHead().insertRow();
      for (const texto of ['Serie', 'Última semana', 'Antigüedad']) {
        const th = document.createElement('th');
        th.scope = 'col';
        th.textContent = texto;
        cabecera.appendChild(th);
      }
      const cuerpo = tabla.createTBody();
      for (const [clave, a] of filas) {
        const fila = cuerpo.insertRow();
        const th = document.createElement('th');
        th.scope = 'row';
        th.textContent = nombreSerie(clave);
        fila.appendChild(th);
        fila.insertCell().textContent = textoUltimaSemana(a) ?? 'sin datos';
        fila.insertCell().textContent = textoRezago(a) ?? '—';
      }
      const partes: Node[] = [titulo, tabla];
      const resumenes = datos.resumen_anual ?? [];
      const ultimo = [...resumenes].sort((x, y) => y.anio - x.anio)[0];
      if (ultimo) {
        const nota = document.createElement('small');
        nota.textContent =
          `Resumen de ${ultimo.anio}: probable, ${ultimo.probable.semanas_completas} semanas completas y ` +
          `${ultimo.probable.semanas_con_dato} con dato de ${ultimo.probable.semanas_nominales}; ` +
          `confirmado, ${ultimo.confirmado.semanas_completas} completas y ${ultimo.confirmado.semanas_con_dato} con dato.`;
        partes.push(nota);
      }
      real.setAttribute('role', 'status');
      real.replaceChildren(...partes);
    } catch {
      renderErrorFuente(
        real,
        () => void cargarReal(),
        'No se pudo consultar la integridad de la vigilancia. La simulación sigue funcionando.',
      );
    }
  }

  // ---- Eventos ----------------------------------------------------------

  const alCambiar = () => {
    if (enSecuencia) return;
    actualizar();
    anunciar(resumen(), 500);
  };
  const selectorSemana = raiz.querySelector<HTMLElement>(
    '#lab-integridad-selector-semana',
  );
  selectorSemana?.addEventListener('cambio-semana', ((
    ev: CustomEvent<{ anio: number; semana: number }>,
  ) => {
    entradaSemana.value = String(ev.detail.semana);
    alCambiar();
  }) as EventListener);

  for (const campo of [entradaSemana, entradaSuma, entradaPublicado]) {
    campo.addEventListener('input', alCambiar);
  }
  casillas.forEach((c) => c.addEventListener('change', alCambiar));
  selectorSerie.addEventListener('change', alCambiar);
  selectorDepto.addEventListener('change', () => {
    codigo = selectorDepto.value;
    actualizar();
    anunciar(resumen(), 200);
  });

  raiz.querySelectorAll<HTMLButtonElement>('[data-lab-preset]').forEach((b) => {
    b.addEventListener('click', () => {
      const preset = PRESETS_INTEGRIDAD.find(
        (p) => p.clave === b.dataset.labPreset,
      );
      if (!preset || enSecuencia) return;
      casillas.forEach((c) => {
        c.checked = !preset.faltantes.includes(c.value);
      });
      entradaSuma.value = preset.suma === null ? '' : String(preset.suma);
      entradaPublicado.value =
        preset.publicado === null ? '' : String(preset.publicado);
      actualizar();
      anunciar(resumen());
    });
  });

  botonCalcular.addEventListener('click', () => void calcular());

  actualizar();
  void cargarReal();
}
