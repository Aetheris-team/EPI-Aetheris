import test from 'node:test';
import assert from 'node:assert/strict';
import {
  obtenerInfoSemanaEpi,
  mesDeSemanaEpi,
  generarMesCalendarioEpi,
  generarCuadriculaAnualEpi,
  ajustarMes,
  ajustarSemanaEpi,
  diasEnMes,
} from '../../src/lib/calendario-epidemico.ts';

test('obtenerInfoSemanaEpi formatea correctamente semanas normales y de cambio de año', () => {
  // 2023 SE01: 01 ene 2023 (domingo) a 07 ene 2023 (sábado)
  const se01_2023 = obtenerInfoSemanaEpi(2023, 1);
  assert.equal(se01_2023.codigo, 'SE01');
  assert.equal(se01_2023.fechaInicioIso, '2023-01-01');
  assert.equal(se01_2023.fechaFinIso, '2023-01-07');
  assert.equal(se01_2023.diaInicio, 1);
  assert.equal(se01_2023.mesInicio, 1);
  assert.equal(se01_2023.diaFin, 7);
  assert.equal(se01_2023.mesFin, 1);
  assert.equal(se01_2023.etiquetaCorta, '01 ene – 07 ene');
  assert.equal(se01_2023.etiquetaRango, '01 ene – 07 ene, 2023');
  assert.equal(se01_2023.etiquetaCompleta, 'Semana 1 · 01 ene – 07 ene, 2023');

  // 2023 SE32: 06 ago 2023 a 12 ago 2023
  const se32_2023 = obtenerInfoSemanaEpi(2023, 32);
  assert.equal(se32_2023.codigo, 'SE32');
  assert.equal(se32_2023.fechaInicioIso, '2023-08-06');
  assert.equal(se32_2023.fechaFinIso, '2023-08-12');
  assert.equal(se32_2023.etiquetaCorta, '06 ago – 12 ago');
  assert.equal(se32_2023.etiquetaRango, '06 ago – 12 ago, 2023');

  // 2024 SE01 cruza año: 31 dic 2023 (domingo) a 06 ene 2024 (sábado)
  const se01_2024 = obtenerInfoSemanaEpi(2024, 1);
  assert.equal(se01_2024.codigo, 'SE01');
  assert.equal(se01_2024.fechaInicioIso, '2023-12-31');
  assert.equal(se01_2024.fechaFinIso, '2024-01-06');
  assert.equal(se01_2024.etiquetaRango, '31 dic, 2023 – 06 ene, 2024');

  // Limita semanas fuera de rango
  const limitadaBaja = obtenerInfoSemanaEpi(2023, -5);
  assert.equal(limitadaBaja.semana, 1);
  const limitadaAlta = obtenerInfoSemanaEpi(2023, 99);
  assert.equal(limitadaAlta.semana, 52);
});

test('mesDeSemanaEpi asocia la semana a su mes principal (miércoles)', () => {
  assert.equal(mesDeSemanaEpi(2023, 1), 1); // Enero
  assert.equal(mesDeSemanaEpi(2023, 32), 8); // Agosto
  assert.equal(mesDeSemanaEpi(2023, 52), 12); // Diciembre
});

test('diasEnMes calcula días calendario incluidos bisiestos', () => {
  assert.equal(diasEnMes(2023, 2), 28);
  assert.equal(diasEnMes(2024, 2), 29); // Bisiesto
  assert.equal(diasEnMes(2023, 8), 31);
  assert.equal(diasEnMes(2023, 4), 30);
});

test('generarMesCalendarioEpi crea cuadrícula mensual con filas epidemiológicas exactas', () => {
  const mesAgosto = generarMesCalendarioEpi(2023, 8, {
    anio: 2023,
    semana: 32,
  });

  assert.equal(mesAgosto.anio, 2023);
  assert.equal(mesAgosto.mes, 8);
  assert.equal(mesAgosto.nombreMes, 'Agosto');
  assert.equal(mesAgosto.nombreMesCorto, 'ago');

  // Cada fila tiene exactamente 7 días y empieza en domingo (diaSemana=0)
  for (const fila of mesAgosto.filas) {
    assert.equal(fila.dias.length, 7);
    assert.equal(fila.dias[0].diaSemana, 0); // Domingo
    assert.equal(fila.dias[6].diaSemana, 6); // Sábado
    assert.match(fila.codigo, /^SE\d{2}$/);
  }

  // La semana 32 debe estar marcada como activa
  const fila32 = mesAgosto.filas.find((f) => f.semana === 32);
  assert.ok(fila32, 'Debe incluir la SE32');
  assert.equal(fila32.esActiva, true);

  // La primera fila contiene días de julio (mes anterior como padding)
  const primeraFila = mesAgosto.filas[0];
  const dia30Jul = primeraFila.dias.find((d) => d.fechaIso === '2023-07-30');
  assert.ok(dia30Jul);
  assert.equal(dia30Jul.esMesActual, false);

  // Días de agosto están marcados con esMesActual = true
  const dia06Ago = fila32.dias.find((d) => d.fechaIso === '2023-08-06');
  assert.ok(dia06Ago);
  assert.equal(dia06Ago.esMesActual, true);
});

test('generarCuadriculaAnualEpi divide las 52 o 53 semanas en 4 trimestres', () => {
  const anual2023 = generarCuadriculaAnualEpi(2023, 32);

  assert.equal(anual2023.totalSemanas, 52);
  assert.equal(anual2023.trimestres.length, 4);

  assert.equal(anual2023.trimestres[0].semanas.length, 13); // T1: 1 a 13
  assert.equal(anual2023.trimestres[1].semanas.length, 13); // T2: 14 a 26
  assert.equal(anual2023.trimestres[2].semanas.length, 13); // T3: 27 a 39
  assert.equal(anual2023.trimestres[3].semanas.length, 13); // T4: 40 a 52

  // Verificar semana activa
  const sem32 = anual2023.trimestres[2].semanas.find((s) => s.semana === 32);
  assert.ok(sem32);
  assert.equal(sem32.esActiva, true);

  // Verificar que la SE01 de 2023 no está activa
  const sem01 = anual2023.trimestres[0].semanas.find((s) => s.semana === 1);
  assert.ok(sem01);
  assert.equal(sem01.esActiva, false);
});

test('ajustarMes y ajustarSemanaEpi navegan correctamente con saltos de año', () => {
  // Ajustar mes
  assert.deepEqual(ajustarMes(2023, 1, -1), { anio: 2022, mes: 12 });
  assert.deepEqual(ajustarMes(2023, 12, 1), { anio: 2024, mes: 1 });
  assert.deepEqual(ajustarMes(2023, 6, 2), { anio: 2023, mes: 8 });

  // Ajustar semana
  assert.deepEqual(ajustarSemanaEpi(2023, 1, -1), { anio: 2022, semana: 52 });
  assert.deepEqual(ajustarSemanaEpi(2023, 52, 1), { anio: 2024, semana: 1 });
  assert.deepEqual(ajustarSemanaEpi(2023, 32, 2), { anio: 2023, semana: 34 });
});
