import { expect, test } from '@playwright/test';

import {
  AVISO_HONESTIDAD_ALERTAS,
  ROTULO_ALERTA_PRUEBA,
  esNivelAlerta,
  renderTextoAccionable,
  SIGNIFICADO_NIVEL,
  textoEstadoVacio,
  textoNoVigente,
  textoSignificadoNivel,
  vistaDeAlertas,
  type AlertaPublica,
} from '../../src/lib/vista-alertas';

const TITULO_DENGUE =
  'Casos probables de dengue por encima de años comparables en 2023';
const TITULO_RESPIRATORIO =
  'IRA y detecciones virales por encima de años comparables en 2023';
const TITULO_INACTIVA =
  'Vigilancia rutinaria de dengue (cerrada el 31/08/2026)';

test('nivel meanings match INDICACIONES §4', () => {
  expect(SIGNIFICADO_NIVEL.informativo).toBe(
    'Sin señal relevante en los datos. Recordatorio de vigilancia rutinaria.',
  );
  expect(SIGNIFICADO_NIVEL.atencion).toBe(
    'Los datos históricos recientes están por encima de lo esperado para la época. Reforzar notificación y búsqueda de casos.',
  );
  expect(SIGNIFICADO_NIVEL.intensificacion).toBe(
    'Señal sostenida varias semanas y/o concentración territorial. Activar medidas locales y coordinar con SIBASI.',
  );
  expect(textoSignificadoNivel('atencion')).toBe(SIGNIFICADO_NIVEL.atencion);
  expect(textoSignificadoNivel('otro')).toBe('');
});

test('esNivelAlerta identifies valid alert levels and rejects invalid values', () => {
  expect(esNivelAlerta('informativo')).toBe(true);
  expect(esNivelAlerta('atencion')).toBe(true);
  expect(esNivelAlerta('intensificacion')).toBe(true);

  expect(esNivelAlerta('')).toBe(false);
  expect(esNivelAlerta('urgente')).toBe(false);
  expect(esNivelAlerta('INFORMATIVO')).toBe(false);
  expect(esNivelAlerta('atención')).toBe(false);
  expect(esNivelAlerta(' atencion ')).toBe(false);
});

test('empty-state copy is the list-empty view branch', () => {
  const vista = vistaDeAlertas([], '2026-09-06');
  expect(vista.tipo).toBe('vacio');
  if (vista.tipo !== 'vacio') return;
  expect(vista.texto).toBe(
    'No hay alertas activas. Última revisión del equipo: 06/09/2026.',
  );
  expect(textoEstadoVacio('06/09/2026')).toBe(vista.texto);
});

test('accionable text escapes HTML', () => {
  const html = renderTextoAccionable(
    '<script>alert(1)</script>\n- item <b>x</b>',
  );
  expect(html).toContain('&lt;script&gt;');
  expect(html).not.toContain('<script>');
  expect(html).toContain('&lt;b&gt;x&lt;/b&gt;');
  expect(html).toContain('<li>');
});

test('/alertas muestra aviso verbatim, campos de una alerta sembrada y sin copy predictivo', async ({
  page,
}) => {
  await page.goto('/alertas');
  await expect(page.locator('[data-aviso-honestidad]')).toContainText(
    AVISO_HONESTIDAD_ALERTAS,
  );
  await expect(page.locator('[data-alertas]')).toHaveAttribute(
    'data-cargado',
    '1',
    { timeout: 15_000 },
  );
  await expect(page.locator('[data-alerta]').first()).toBeVisible();
  const dengue = page.locator('[data-alerta][data-tipo="dengue"]');
  await expect(dengue).toContainText(TITULO_DENGUE);
  await expect(dengue.locator('[data-alerta-tipo]')).toContainText('Dengue');
  await expect(dengue.locator('[data-alerta-nivel]')).toContainText('Atención');
  await expect(dengue.locator('[data-alerta-nivel-significado]')).toHaveText(
    SIGNIFICADO_NIVEL.atencion,
  );
  await expect(dengue.locator('[data-alerta-indicaciones]')).toContainText(
    'No indicar AINE ni intramusculares en febriles sin diagnóstico.',
  );
  await expect(page.locator('[data-niveles-leyenda]')).toBeVisible();
  await expect(page.locator('[data-nivel-leyenda="atencion"]')).toContainText(
    SIGNIFICADO_NIVEL.atencion,
  );
  await expect(
    page.locator('[data-nivel-leyenda="intensificacion"]'),
  ).toContainText(SIGNIFICADO_NIVEL.intensificacion);
  await expect(dengue.locator('[data-alerta-emision]')).toContainText(
    '01/09/2026',
  );
  await expect(dengue.locator('[data-alerta-vigencia]')).toContainText(
    'Vigencia',
  );
  await expect(dengue.locator('[data-alerta-fuente]')).not.toBeEmpty();
  await expect(dengue.locator('[data-alerta-autor]')).not.toBeEmpty();
  await expect(page.locator('main')).not.toContainText(TITULO_INACTIVA);
  await expect(page.locator('main')).not.toContainText('va a haber brote');
  await expect(page.locator('main')).not.toContainText(/predic/i);
});

test('empty list branch of the shipped view on /alertas', async ({ page }) => {
  await page.goto('/alertas');
  await expect(page.locator('[data-alertas]')).toHaveAttribute(
    'data-cargado',
    '1',
    { timeout: 15_000 },
  );
  await page.locator('[data-alertas]').evaluate((el) => {
    const pintar = (
      el as HTMLElement & {
        pintarAlertas?: (payload: {
          aviso: string;
          ultima_revision: string;
          alertas: [];
        }) => void;
      }
    ).pintarAlertas;
    if (!pintar) throw new Error('pintarAlertas no está en el contenedor');
    pintar({
      aviso: '',
      ultima_revision: '2026-09-06',
      alertas: [],
    });
  });
  await expect(page.locator('[data-alertas-vacio]')).toBeVisible();
  await expect(page.locator('[data-alertas-vacio]')).toHaveText(
    'No hay alertas activas. Última revisión del equipo: 06/09/2026.',
  );
});

test('dengue y respiratorio enlazan a /alertas filtrado; la tarjeta vuelve al módulo', async ({
  page,
}) => {
  await page.goto('/dengue');
  const enlaceDengue = page.locator('[data-enlace-alertas="dengue"]');
  await expect(enlaceDengue).toHaveText('¿Alerta activa? →');
  await expect(enlaceDengue).toHaveAttribute('href', '/alertas?tipo=dengue');

  await page.goto('/respiratorio');
  const enlaceResp = page.locator('[data-enlace-alertas="respiratorio"]');
  await expect(enlaceResp).toHaveText('¿Alerta activa? →');
  await expect(enlaceResp).toHaveAttribute(
    'href',
    '/alertas?tipo=respiratorio',
  );

  await page.goto('/alertas?tipo=dengue');
  await expect(page.locator('[data-alertas]')).toHaveAttribute(
    'data-cargado',
    '1',
    { timeout: 15_000 },
  );
  const tarjetaDengue = page.locator('[data-alerta][data-tipo="dengue"]');
  await expect(tarjetaDengue).toBeVisible();
  await expect(
    page.locator('[data-alerta][data-tipo="respiratorio"]'),
  ).toHaveCount(0);
  await expect(
    tarjetaDengue.locator('[data-enlace-modulo="dengue"]'),
  ).toHaveAttribute('href', '/dengue');

  await page.goto('/alertas?tipo=respiratorio');
  await expect(page.locator('[data-alertas]')).toHaveAttribute(
    'data-cargado',
    '1',
    { timeout: 15_000 },
  );
  const tarjetaResp = page.locator('[data-alerta][data-tipo="respiratorio"]');
  await expect(tarjetaResp).toBeVisible();
  await expect(tarjetaResp).toContainText(TITULO_RESPIRATORIO);
  await expect(tarjetaResp.locator('[data-alerta-indicaciones]')).toContainText(
    'Usar oximetría de pulso en todo paciente con dificultad respiratoria; documentar SatO2.',
  );
  await expect(
    tarjetaResp.locator('[data-alerta-nivel-significado]'),
  ).toHaveText(SIGNIFICADO_NIVEL.atencion);
  await expect(page.locator('[data-alerta][data-tipo="dengue"]')).toHaveCount(
    0,
  );
  await expect(
    tarjetaResp.locator('[data-enlace-modulo="respiratorio"]'),
  ).toHaveAttribute('href', '/respiratorio');
});

const alertaBase: AlertaPublica = {
  id: 9001,
  tipo: 'dengue',
  nivel: 'informativo',
  titulo: 'Fila de prueba para rótulo',
  contexto: 'No usar.',
  indicaciones: '- No actuar.',
  fuente: 'suite e2e',
  autor: 'suite',
  vigente_desde: '2026-08-01',
  vigente_hasta: '2026-08-31',
  activa: false,
  etiqueta: null,
};

test('shipped renderer: labeled row shows prueba marker; expired row shows NO VIGENTE', () => {
  expect(ROTULO_ALERTA_PRUEBA).toBe(
    'ALERTA DE PRUEBA — NO ACTUAR SOBRE ESTA INFORMACIÓN',
  );
  expect(textoNoVigente(alertaBase)).toBe('NO VIGENTE — venció el 31/08/2026');
  expect(
    textoNoVigente({
      ...alertaBase,
      activa: true,
      vigente_hasta: null,
      etiqueta: 'test',
    }),
  ).toBeNull();
});

test('labeled row in the DOM shows ALERTA DE PRUEBA', async ({ page }) => {
  await page.goto('/alertas');
  await expect(page.locator('[data-alertas]')).toHaveAttribute(
    'data-cargado',
    '1',
    { timeout: 15_000 },
  );
  await page.locator('[data-alertas]').evaluate((el, rotulo) => {
    const pintar = (
      el as HTMLElement & {
        pintarAlertas?: (payload: {
          aviso: string;
          ultima_revision: string;
          alertas: AlertaPublica[];
        }) => void;
      }
    ).pintarAlertas;
    if (!pintar) throw new Error('pintarAlertas no está en el contenedor');
    pintar({
      aviso: '',
      ultima_revision: '2026-09-07',
      alertas: [
        {
          id: 9001,
          tipo: 'dengue',
          nivel: 'informativo',
          titulo: 'Fila etiquetada inyectada',
          contexto: 'No usar.',
          indicaciones: '- No actuar.',
          fuente: 'suite e2e',
          autor: 'suite',
          vigente_desde: '2026-09-01',
          vigente_hasta: null,
          activa: true,
          etiqueta: 'test',
        },
      ],
    });
    if (!el.textContent?.includes(rotulo)) {
      throw new Error('el renderer no pintó el rótulo de prueba');
    }
  }, ROTULO_ALERTA_PRUEBA);
  const tarjeta = page.locator('[data-alerta][data-alerta-etiqueta="test"]');
  await expect(tarjeta).toContainText(ROTULO_ALERTA_PRUEBA);
  await expect(tarjeta.locator('[data-alerta-prueba]')).toHaveText(
    ROTULO_ALERTA_PRUEBA,
  );
});

test('archive non-vigente row shows NO VIGENTE', async ({ page }) => {
  await page.goto('/alertas/archivo');
  await expect(page.locator('[data-alertas]')).toHaveAttribute(
    'data-cargado',
    '1',
    { timeout: 15_000 },
  );
  const inactiva = page.locator('[data-alerta]').filter({
    hasText: TITULO_INACTIVA,
  });
  await expect(inactiva).toBeVisible();
  await expect(inactiva.locator('[data-alerta-no-vigente]')).toContainText(
    'NO VIGENTE',
  );
  await expect(inactiva.locator('[data-alerta-no-vigente]')).toContainText(
    '31/08/2026',
  );
});

test('/alertas anuncia el feed Atom en la cabecera y con un enlace visible', async ({
  page,
}) => {
  await page.route('**/api/alertas?**', (ruta) =>
    ruta.fulfill({
      json: {
        aviso: AVISO_HONESTIDAD_ALERTAS,
        ultima_revision: null,
        alertas: [],
      },
    }),
  );
  await page.goto('/alertas');
  const cabecera = page.locator(
    'head link[rel="alternate"][type="application/atom+xml"]',
  );
  await expect(cabecera).toHaveAttribute('href', /\/api\/alertas\/feed\.xml$/);
  await expect(page.locator('[data-enlace-feed]')).toBeVisible();
});

test('filtrado por síndrome en el cliente actualiza URL y lista sin recarga de página', async ({
  page,
}) => {
  await page.goto('/alertas');
  await expect(page.locator('[data-alertas]')).toHaveAttribute(
    'data-cargado',
    '1',
    { timeout: 15_000 },
  );

  await expect(page.locator('[data-alerta][data-tipo="dengue"]')).toBeVisible();
  await expect(
    page.locator('[data-alerta][data-tipo="respiratorio"]'),
  ).toBeVisible();

  // Marcamos un atributo en la cabecera (zona estática) para comprobar que la página NO se recarga
  await page.evaluate(() => {
    document
      .querySelector('[data-zona="cabecera"]')
      ?.setAttribute('data-prueba-sin-recarga', '1');
  });

  // Clic en Dengue
  await page.locator('[data-filtro-tipo="dengue"]').click();
  await expect(page).toHaveURL(/tipo=dengue/);
  await expect(page.locator('[data-alerta][data-tipo="dengue"]')).toBeVisible();
  await expect(
    page.locator('[data-alerta][data-tipo="respiratorio"]'),
  ).toHaveCount(0);
  await expect(page.locator('[data-filtro-tipo="dengue"]')).toHaveAttribute(
    'aria-current',
    'page',
  );

  // La cabecera conserva la marca (no hubo navegación dura ni recarga de página)
  const marca = await page
    .locator('[data-zona="cabecera"]')
    .getAttribute('data-prueba-sin-recarga');
  expect(marca).toBe('1');

  // Clic en Respiratorio
  await page.locator('[data-filtro-tipo="respiratorio"]').click();
  await expect(page).toHaveURL(/tipo=respiratorio/);
  await expect(
    page.locator('[data-alerta][data-tipo="respiratorio"]'),
  ).toBeVisible();
  await expect(page.locator('[data-alerta][data-tipo="dengue"]')).toHaveCount(
    0,
  );

  // Volver a Todas
  await page.locator('[data-filtro-tipo="todas"]').click();
  await expect(page.locator('[data-alerta][data-tipo="dengue"]')).toBeVisible();
  await expect(
    page.locator('[data-alerta][data-tipo="respiratorio"]'),
  ).toBeVisible();

  // Historial del navegador (Back)
  await page.goBack();
  await expect(page).toHaveURL(/tipo=respiratorio/);
  await expect(
    page.locator('[data-alerta][data-tipo="respiratorio"]'),
  ).toBeVisible();
  await expect(page.locator('[data-alerta][data-tipo="dengue"]')).toHaveCount(
    0,
  );
});
