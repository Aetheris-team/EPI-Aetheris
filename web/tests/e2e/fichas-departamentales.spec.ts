import { expect, test } from '@playwright/test';

const MOCK_TEMPORAL = {
  departamento_codigo: 'SV-SS',
  departamento_nombre: 'San Salvador',
  anio: 2023,
  semanas: [
    {
      semana_epi: 1,
      iv_real: 0.232,
      p25_baseline: 0.221,
      mediana_baseline: 0.232,
      p75_baseline: 0.239,
      anomaly_sigma: -0.02,
    },
    {
      semana_epi: 52,
      iv_real: 0.246,
      p25_baseline: 0.217,
      mediana_baseline: 0.222,
      p75_baseline: 0.231,
      anomaly_sigma: 1.62,
    },
  ],
  aviso: 'Capa descriptiva de idoneidad biofísica.',
};

const MOCK_PRESION = {
  departamento_codigo: 'SV-SS',
  departamento_nombre: 'San Salvador',
  anio: 2023,
  semanas: [
    {
      semana_epi: 50,
      probable: {
        casos_observados: 12,
        percentil: 78.5,
        categoria: 'alta',
        p50_baseline: 5,
        p75_baseline: 10,
        n_obs_baseline: 6,
        anios_baseline: 4,
      },
      confirmado: {
        casos_observados: 2,
        percentil: 45.0,
        categoria: 'baja',
        p50_baseline: 3,
        p75_baseline: 6,
        n_obs_baseline: 6,
        anios_baseline: 4,
      },
    },
  ],
  aviso: 'Capa descriptiva de presión relativa.',
};

const MOCK_IRA = {
  departamento_codigo: 'SV-SS',
  departamento_nombre: 'San Salvador',
  anios: [2023],
  series: {
    '2023': [
      [1, 100],
      [52, 250],
    ],
  },
  aviso: 'Serie descriptiva de IRA.',
};

const MOCK_NEUMONIAS = {
  disponible: true,
  departamento_codigo: 'SV-SS',
  departamento_nombre: 'San Salvador',
  anios: [2023],
  series: {
    '2023': [
      [1, 15],
      [52, 35],
    ],
  },
  aviso: 'Serie descriptiva de neumonías.',
};

const MOCK_ALERTAS = {
  aviso: 'Alertas de vigilancia epidemiológica.',
  ultima_revision: '2026-09-08',
  alertas: [
    {
      id: 101,
      tipo: 'dengue',
      nivel: 'atencion',
      titulo: 'Medidas de control vectorial prioritarias',
      contexto: 'Vigilancia en depósitos de agua.',
      indicaciones: '- Tapar recipientes.\n- Lavar pilas semanalmente.',
      signos_alarma: 'Fiebre persistente, sangrado y dolor abdominal severo.',
      acciones_comunitarias: 'Eliminación activa de criaderos.',
      contacto_vigilancia: 'Vía SIBASI / VIGEPES-01.',
      fuente: 'MINSAL / OPS',
      autor: 'Vigilancia INSAMT',
      vigente_desde: '2026-09-01',
      vigente_hasta: null,
      activa: true,
    },
  ],
};

test.describe('Ficha departamental imprimible', () => {
  test('la ficha carga con datos mockeados, muestra secciones y habilita botón de impresión', async ({
    page,
  }) => {
    // Interceptar llamadas al backend
    await page.route('**/datos/v1/temporal/SV-SS/*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_TEMPORAL),
      }),
    );
    await page.route('**/datos/v1/presion/temporal/SV-SS/*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_PRESION),
      }),
    );
    await page.route('**/datos/ira/temporal/SV-SS*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_IRA),
      }),
    );
    await page.route('**/datos/neumonias/temporal/SV-SS*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_NEUMONIAS),
      }),
    );
    await page.route('**/datos/alertas/registradas-activas.json', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_ALERTAS),
      }),
    );

    await page.goto('/analisis/ficha/SV-SS');

    // Encabezado y metadatos
    await expect(page.locator('h1')).toContainText('San Salvador');
    await expect(page.locator('h1')).toContainText('SV-SS');

    // Gate de impresión: esperar a que termine la carga concurrente
    const ficha = page.locator('[data-ficha]');
    await expect(ficha).toHaveAttribute('data-cargado', '1', {
      timeout: 15_000,
    });

    const botonImprimir = page.locator('[data-imprimir]');
    await expect(botonImprimir).toBeEnabled();
    await expect(botonImprimir).toContainText('Imprimir ficha');

    // Sección 1: M1, M2, M3
    await expect(page.locator('[data-m1-valor]')).toHaveText('0.246');
    await expect(page.locator('[data-m2-valor]')).toContainText('1.62');
    await expect(page.locator('[data-m3-prob-valor]')).toContainText('P78.5');
    await expect(page.locator('[data-m3-conf-valor]')).toContainText('P45.0');

    // Sección 2: Gráficas SVG presentes
    await expect(page.locator('#grafica-m1 svg')).toBeVisible();
    await expect(page.locator('#grafica-m2 svg')).toBeVisible();

    // Sección 3: Infecciones respiratorias
    await expect(page.locator('[data-ira-conteo]')).toHaveText('350');
    await expect(page.locator('[data-neumonias-conteo]')).toHaveText('50');

    // Sección 4: Guías de prevención citadas
    await expect(page.locator('#seccion-prevencion-cuerpo')).toContainText(
      'Medidas de control vectorial prioritarias',
    );
    await expect(page.locator('#seccion-prevencion-cuerpo')).toContainText(
      'Fiebre persistente, sangrado',
    );
    await expect(page.locator('#seccion-prevencion-cuerpo')).toContainText(
      'MINSAL / OPS',
    );
  });

  test('gate de impresión se cumple y muestra no disponible ante fallos de endpoints', async ({
    page,
  }) => {
    // Simular que el endpoint de respiratorios falla con 500 y presión responde 500
    await page.route('**/datos/v1/temporal/SV-SS/*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_TEMPORAL),
      }),
    );
    await page.route('**/datos/v1/presion/temporal/SV-SS/*', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Error interno' }),
      }),
    );
    await page.route('**/datos/ira/temporal/SV-SS*', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Fallo simulado' }),
      }),
    );
    await page.route('**/datos/neumonias/temporal/SV-SS*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          disponible: false,
          motivo: 'Tabla de neumonías no disponible',
        }),
      }),
    );
    await page.route('**/datos/alertas/registradas-activas.json', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_ALERTAS),
      }),
    );

    await page.goto('/analisis/ficha/SV-SS');

    const ficha = page.locator('[data-ficha]');
    await expect(ficha).toHaveAttribute('data-cargado', '1', {
      timeout: 15_000,
    });

    // El botón se habilita igualmente para permitir imprimir con lo que haya
    const botonImprimir = page.locator('[data-imprimir]');
    await expect(botonImprimir).toBeEnabled();

    // Las secciones que fallaron muestran mensaje explícito de no disponible
    await expect(page.locator('[data-m3-prob-valor]')).toHaveText(
      'No disponible',
    );
    await expect(page.locator('[data-corte-probable]')).toHaveText(
      'No disponible',
    );
    await expect(page.locator('[data-ira-detalle]')).toContainText(
      'no disponibles',
    );
    await expect(page.locator('[data-neumonias-detalle]')).toContainText(
      'no disponible',
    );

    // M1 sigue mostrando su dato exitoso
    await expect(page.locator('[data-m1-valor]')).toHaveText('0.246');
  });

  test('la tabla usa la union de semanas: M3 solo no dispara "sin semanas"', async ({
    page,
  }) => {
    // M1/M2 falla, M3 responde: la tabla debe listar las semanas de M3.
    await page.route('**/datos/v1/temporal/SV-SS/*', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Fallo simulado' }),
      }),
    );
    await page.route('**/datos/v1/presion/temporal/SV-SS/*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_PRESION),
      }),
    );
    await page.route('**/datos/ira/temporal/SV-SS*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_IRA),
      }),
    );
    await page.route('**/datos/neumonias/temporal/SV-SS*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_NEUMONIAS),
      }),
    );
    await page.route('**/datos/alertas/registradas-activas.json', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_ALERTAS),
      }),
    );

    await page.goto('/analisis/ficha/SV-SS');
    await expect(page.locator('[data-ficha]')).toHaveAttribute(
      'data-cargado',
      '1',
      { timeout: 15_000 },
    );

    const filas = page.locator('#tabla-semanas-cuerpo tr');
    await expect(filas).toHaveCount(1);
    await expect(filas.first()).toContainText('SE50');
    // Columna M1 (Iv) cae a "—", columna percentil probable trae el dato de M3.
    await expect(filas.first()).toContainText('P78.5');
    await expect(page.locator('#tabla-semanas-cuerpo')).not.toContainText(
      'Sin semanas registradas',
    );
  });

  test('enlace desde /analisis hacia la ficha departamental', async ({
    page,
  }) => {
    await page.goto('/analisis');

    const seccionFichas = page.locator('[data-seccion-fichas]');
    await expect(seccionFichas).toBeVisible();

    const enlaceSanSalvador = page.locator('[data-ficha-enlace=SV-SS]');
    await expect(enlaceSanSalvador).toBeVisible();
    await expect(enlaceSanSalvador).toHaveAttribute(
      'href',
      '/analisis/ficha/SV-SS',
    );

    await enlaceSanSalvador.click();
    await expect(page).toHaveURL(/\/analisis\/ficha\/SV-SS/);
    await expect(page.locator('h1')).toContainText('San Salvador');
  });

  test('reusa el aviso de la respuesta y escapa el contenido de las alertas', async ({
    page,
  }) => {
    await page.route('**/datos/v1/temporal/SV-SS/*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_TEMPORAL),
      }),
    );
    await page.route('**/datos/v1/presion/temporal/SV-SS/*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_PRESION),
      }),
    );
    await page.route('**/datos/ira/temporal/SV-SS*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_IRA),
      }),
    );
    await page.route('**/datos/neumonias/temporal/SV-SS*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_NEUMONIAS),
      }),
    );
    await page.route('**/datos/alertas/registradas-activas.json', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...MOCK_ALERTAS,
          alertas: [
            {
              ...MOCK_ALERTAS.alertas[0],
              titulo: 'Control vectorial <img src=x onerror=alert(1)>',
              indicaciones: '- Tapar recipientes <script>alert(2)</script>',
            },
          ],
        }),
      }),
    );

    const errores: string[] = [];
    page.on('pageerror', (e) => errores.push(String(e)));
    page.on('dialog', (d) => {
      errores.push('dialog');
      void d.dismiss();
    });

    await page.goto('/analisis/ficha/SV-SS');
    await expect(page.locator('[data-ficha]')).toHaveAttribute(
      'data-cargado',
      '1',
      { timeout: 15_000 },
    );

    // El aviso de M1 es el `aviso` de la respuesta, no una constante redactada.
    await expect(page.locator('[data-m1-aviso]')).toHaveText(
      'Capa descriptiva de idoneidad biofísica.',
    );

    // El markup malicioso de la alerta aparece como texto, no como nodo.
    await expect(page.locator('#seccion-prevencion-cuerpo')).toContainText(
      '<img src=x onerror=alert(1)>',
    );
    await expect(page.locator('#seccion-prevencion-cuerpo img')).toHaveCount(0);
    expect(errores).toEqual([]);
  });

  test('sin alertas en el corte muestra un contenedor neutro sin texto de salud', async ({
    page,
  }) => {
    const responder =
      (cuerpo: unknown): Parameters<typeof page.route>[1] =>
      (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(cuerpo),
        });
    await page.route(
      '**/datos/v1/presion/temporal/SV-SS/*',
      responder(MOCK_PRESION),
    );
    await page.route('**/datos/v1/temporal/SV-SS/*', responder(MOCK_TEMPORAL));
    await page.route('**/datos/ira/temporal/SV-SS*', responder(MOCK_IRA));
    await page.route(
      '**/datos/neumonias/temporal/SV-SS*',
      responder(MOCK_NEUMONIAS),
    );
    await page.route('**/datos/alertas/registradas-activas.json', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...MOCK_ALERTAS, alertas: [] }),
      }),
    );

    await page.goto('/analisis/ficha/SV-SS');
    await expect(page.locator('[data-ficha]')).toHaveAttribute(
      'data-cargado',
      '1',
      { timeout: 15_000 },
    );

    const cuerpo = page.locator('#seccion-prevencion-cuerpo');
    await expect(cuerpo).toContainText('Sin alertas en el corte');
    await expect(cuerpo).not.toContainText('lineamientos generales');
    await expect(cuerpo).not.toContainText('OPS/OMS');
  });
  test('solo muestra las alertas que aplican al departamento de la ficha', async ({
    page,
  }) => {
    const base = MOCK_ALERTAS.alertas[0];
    const payload = {
      ...MOCK_ALERTAS,
      alertas: [
        { ...base, id: 201, titulo: 'Alerta nacional', departamentos: null },
        {
          ...base,
          id: 202,
          titulo: 'Alerta de San Salvador',
          departamentos: ['SV-SS'],
        },
        {
          ...base,
          id: 203,
          titulo: 'Alerta de Santa Ana',
          departamentos: ['SV-SA'],
        },
      ],
    };
    await page.route('**/datos/v1/temporal/SV-SS/*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_TEMPORAL),
      }),
    );
    await page.route('**/datos/v1/presion/temporal/SV-SS/*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_PRESION),
      }),
    );
    await page.route('**/datos/ira/temporal/SV-SS*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_IRA),
      }),
    );
    await page.route('**/datos/neumonias/temporal/SV-SS*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_NEUMONIAS),
      }),
    );
    await page.route('**/datos/alertas/registradas-activas.json', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(payload),
      }),
    );
    await page.goto('/analisis/ficha/SV-SS');
    const cuerpo = page.locator('#seccion-prevencion-cuerpo');
    await expect(cuerpo).toContainText('Alerta nacional', { timeout: 15_000 });
    await expect(cuerpo).toContainText('Alerta de San Salvador');
    await expect(cuerpo).not.toContainText('Alerta de Santa Ana');
  });
});
