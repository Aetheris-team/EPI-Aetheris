import assert from 'node:assert/strict';
import { test } from 'node:test';
import { celdaCsv, lineaCsv } from '../../src/lib/exportar-csv.ts';

test('una celda sin caracteres especiales sale tal cual', () => {
  assert.equal(celdaCsv('San Salvador'), 'San Salvador');
  assert.equal(celdaCsv(0), '0');
  assert.equal(celdaCsv(-0.25), '-0.25');
});

test('las celdas vacías quedan en blanco y el cero no se pierde', () => {
  assert.equal(celdaCsv(null), '');
  assert.equal(celdaCsv(undefined), '');
  assert.equal(celdaCsv(0), '0');
  assert.equal(celdaCsv(''), '');
});

test('una celda con coma, comilla o salto de línea va entre comillas', () => {
  assert.equal(celdaCsv('La Unión, centro'), '"La Unión, centro"');
  assert.equal(celdaCsv('dijo "hola"'), '"dijo ""hola"""');
  assert.equal(celdaCsv('a\nb'), '"a\nb"');
});

test('una línea une las celdas con comas', () => {
  assert.equal(
    lineaCsv(['SV-SS', 2023, null, 'a,b', true]),
    'SV-SS,2023,,"a,b",true',
  );
});
