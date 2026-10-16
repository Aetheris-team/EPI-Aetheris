import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  TablaAlternativa,
  type ColumnaTabla,
} from '../../src/lib/tabla-alternativa.ts';

// Dobles mínimos del DOM: la clase solo usa addEventListener y open del
// <details>, y classList e innerHTML del contenedor.
function crearDetails() {
  return {
    open: false,
    addEventListener() {},
  } as unknown as HTMLDetailsElement;
}

function crearContenedor() {
  const clases = new Set<string>();
  return {
    innerHTML: '',
    clases,
    classList: {
      add: (c: string) => clases.add(c),
      toggle: (c: string, forzar: boolean) => {
        if (forzar) clases.add(c);
        else clases.delete(c);
        return forzar;
      },
    },
  };
}

function construir(columnas: ColumnaTabla[], datos: object[]) {
  const contenedor = crearContenedor();
  new TablaAlternativa({
    details: crearDetails(),
    contenedorTabla: contenedor as unknown as HTMLElement,
    caption: 'Casos por semana',
    columnas,
    obtenerDatos: () => datos,
  }).construir();
  return contenedor;
}

const TRES_COLUMNAS: ColumnaTabla[] = [
  { clave: 'semana', encabezado: 'Semana' },
  { clave: 'casos', encabezado: 'Casos', alineacion: 'derecha' },
  { clave: 'tasa', encabezado: 'Tasa', alineacion: 'derecha' },
];

test('la primera columna es el encabezado de la fila', () => {
  const { innerHTML } = construir(TRES_COLUMNAS, [
    { semana: 'SE 12', casos: 40, tasa: 1.5 },
  ]);
  assert.match(innerHTML, /<th scope="row"[^>]*>SE 12<\/th>/);
  assert.doesNotMatch(innerHTML, /<td[^>]*>SE 12<\/td>/);
  assert.equal(innerHTML.match(/<td /g)?.length, 2);
});

test('cada celda lleva su encabezado de columna en data-etiqueta', () => {
  const { innerHTML } = construir(TRES_COLUMNAS, [
    { semana: 'SE 12', casos: 40, tasa: 1.5 },
  ]);
  assert.match(innerHTML, /<td [^>]*data-etiqueta="Casos"[^>]*>40<\/td>/);
  assert.match(innerHTML, /<td [^>]*data-etiqueta="Tasa"[^>]*>1.5<\/td>/);
});

test('data-etiqueta y el encabezado de fila escapan el HTML', () => {
  const { innerHTML } = construir(
    [
      { clave: 'nombre', encabezado: 'Depto' },
      { clave: 'casos', encabezado: 'Casos "x" <b>' },
    ],
    [{ nombre: '<img src=x onerror=alert(1)>', casos: 1 }],
  );
  assert.match(innerHTML, /data-etiqueta="Casos &quot;x&quot; &lt;b&gt;"/);
  assert.match(innerHTML, /&lt;img src=x onerror=alert\(1\)&gt;<\/th>/);
  assert.doesNotMatch(innerHTML, /<img/);
});

test('con tres columnas o más la tabla es apilable', () => {
  const { clases } = construir(TRES_COLUMNAS, [
    { semana: 'SE 12', casos: 40, tasa: 1.5 },
  ]);
  assert.ok(clases.has('tabla-alternativa'));
  assert.ok(clases.has('tabla-apilable'));
});

test('con dos columnas la tabla se queda como tabla', () => {
  const { clases, innerHTML } = construir(TRES_COLUMNAS.slice(0, 2), [
    { semana: 'SE 12', casos: 40 },
  ]);
  assert.ok(clases.has('tabla-alternativa'));
  assert.ok(!clases.has('tabla-apilable'));
  assert.match(innerHTML, /class="tabla-alternativa-region /);
});

test('sin datos muestra el aviso y no arma la tabla', () => {
  const { innerHTML } = construir(TRES_COLUMNAS, []);
  assert.match(innerHTML, /No hay datos disponibles/);
  assert.doesNotMatch(innerHTML, /<table/);
});
