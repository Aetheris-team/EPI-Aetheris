import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  proyectarDepartamentos,
  normalizarNombreDepartamento,
  obtenerAbreviaturaDepartamento,
  ABREVIATURAS_DEPARTAMENTOS,
  type GeoDepartamentos,
} from '../../src/lib/geo-svg.ts';

const geoSlv = JSON.parse(
  readFileSync(join(process.cwd(), 'public/geo/slv-adm1.geojson'), 'utf8'),
) as GeoDepartamentos;

test('normalizarNombreDepartamento elimina el prefijo Departamento de', () => {
  assert.equal(
    normalizarNombreDepartamento('Departamento de Cuscatlán'),
    'Cuscatlán',
  );
  assert.equal(
    normalizarNombreDepartamento('Departamento de San Salvador'),
    'San Salvador',
  );
  assert.equal(
    normalizarNombreDepartamento('Departamento de La Paz'),
    'La Paz',
  );
  assert.equal(normalizarNombreDepartamento('La Libertad'), 'La Libertad');
  assert.equal(normalizarNombreDepartamento(undefined), undefined);
});

test('obtenerAbreviaturaDepartamento devuelve el código ISO o sufijo corto', () => {
  assert.equal(obtenerAbreviaturaDepartamento('SV-SS'), 'SS');
  assert.equal(obtenerAbreviaturaDepartamento('SV-CU'), 'CU');
  assert.equal(obtenerAbreviaturaDepartamento('SV-AH'), 'AH');
  assert.equal(obtenerAbreviaturaDepartamento('SV-SA'), 'SA');
  assert.equal(obtenerAbreviaturaDepartamento('SV-X'), 'X');
});

test('proyectarDepartamentos proyecta los 14 departamentos de El Salvador con alta fidelidad', () => {
  const ancho = 680;
  const margen = 14;
  const mapa = proyectarDepartamentos(geoSlv, ancho, margen, 0.4);

  assert.equal(mapa.ancho, ancho);
  assert.ok(mapa.alto > 300 && mapa.alto < 450);
  assert.equal(mapa.viewBox, `0 0 ${ancho} ${mapa.alto}`);
  assert.equal(mapa.departamentos.length, 14);

  // Comprobar códigos y normalización de nombres
  const codigos = new Set(mapa.departamentos.map((d) => d.codigo));
  assert.equal(codigos.size, 14);
  assert.ok(codigos.has('SV-SS'));
  assert.ok(codigos.has('SV-CU'));
  assert.ok(codigos.has('SV-PA'));
  assert.ok(codigos.has('SV-US'));
  assert.ok(codigos.has('SV-UN'));

  for (const d of mapa.departamentos) {
    // Trazados válidos y cerrados
    assert.match(d.d, /^M[\d.]+ [\d.]+L.*Z$/);
    assert.ok(d.d.length > 50);

    // Nombres sin prefijo 'Departamento de '
    assert.ok(d.nombre);
    assert.doesNotMatch(d.nombre, /^Departamento de /);

    // Abreviaturas de 2 caracteres coincidentes con ISO
    assert.equal(d.abreviatura, ABREVIATURAS_DEPARTAMENTOS[d.codigo]);
    assert.equal(d.codigoCorto, d.abreviatura);
    assert.equal(d.abreviatura?.length, 2);

    // Centroides dentro de los límites del viewBox
    assert.ok(typeof d.centroX === 'number');
    assert.ok(typeof d.centroY === 'number');
    assert.ok(d.centroX > margen && d.centroX < ancho - margen);
    assert.ok(d.centroY > margen && d.centroY < mapa.alto - margen);
  }
});

test('centroides de geometrías irregulares (Cuscatlán, San Salvador, La Paz) se posicionan armónicamente', () => {
  const mapa = proyectarDepartamentos(geoSlv, 680, 14, 0.4);
  const ss = mapa.departamentos.find((d) => d.codigo === 'SV-SS')!;
  const cu = mapa.departamentos.find((d) => d.codigo === 'SV-CU')!;
  const pa = mapa.departamentos.find((d) => d.codigo === 'SV-PA')!;
  const us = mapa.departamentos.find((d) => d.codigo === 'SV-US')!;

  assert.ok(ss && cu && pa && us);

  // San Salvador queda al oeste de Cuscatlán
  assert.ok(ss.centroX! < cu.centroX!);

  // Cuscatlán queda al norte de La Paz
  assert.ok(cu.centroY! < pa.centroY!);

  // Distancia espacial suficiente entre San Salvador y Cuscatlán para evitar colisión de rótulos
  const distSsCu = Math.hypot(
    cu.centroX! - ss.centroX!,
    cu.centroY! - ss.centroY!,
  );
  assert.ok(distSsCu > 45, `Distancia SS-CU (${distSsCu}) debe ser > 45px`);

  // Distancia espacial suficiente entre Cuscatlán y La Paz
  const distCuPa = Math.hypot(
    pa.centroX! - cu.centroX!,
    pa.centroY! - cu.centroY!,
  );
  assert.ok(distCuPa > 60, `Distancia CU-PA (${distCuPa}) debe ser > 60px`);

  // Usulután no se desvía a la costa sur/bahía de Jiquilisco
  assert.ok(us.centroX! > 400 && us.centroX! < 460);
  assert.ok(us.centroY! > 290 && us.centroY! < 340);
});

test('maneja colecciones vacías de forma segura', () => {
  const vacio = proyectarDepartamentos({ features: [] }, 500);
  assert.equal(vacio.ancho, 500);
  assert.equal(vacio.alto, 300);
  assert.equal(vacio.viewBox, '0 0 500 300');
  assert.deepEqual(vacio.departamentos, []);
});
