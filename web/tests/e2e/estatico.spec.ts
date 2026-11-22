import { expect, test } from '@playwright/test';

const vistas = [
  { pagina: '/dengue', archivo: '/datos/casos-nacional.json' },
  { pagina: '/analisis/clima', archivo: '/datos/clima-dengue/por-anio.json' },
  { pagina: '/respiratorio', archivo: '/datos/respiratorios/cobertura.json' },
  { pagina: '/prediccion', archivo: '/datos/nowcast-dengue.json' },
  {
    pagina: '/analisis/ficha/SV-SS',
    archivo: '/datos/v1/presion/temporal/SV-SS/2023.json',
  },
];

for (const { pagina, archivo } of vistas) {
  test(`${pagina} carga datos públicos desde el alojamiento estático`, async ({
    page,
  }) => {
    const datos = page.waitForResponse(
      (respuesta) => new URL(respuesta.url()).pathname === archivo,
    );
    const origenes = new Set<string>();
    page.on('request', (peticion) => {
      if (['fetch', 'xhr'].includes(peticion.resourceType())) {
        origenes.add(new URL(peticion.url()).origin);
      }
    });
    const documento = await page.goto(pagina);
    expect(documento?.status()).toBe(200);
    const respuesta = await datos;
    expect(respuesta.ok()).toBe(true);
    expect(respuesta.headers()['content-type']).toContain('application/json');
    expect([...origenes]).toEqual([new URL(page.url()).origin]);
  });
}

test('el reloj del navegador no cambia los años del corte climático', async ({
  page,
  request,
}) => {
  const metadata = await request.get('/datos/corte.json');
  const { ultimo_anio_clima: ultimoAnioClima } = await metadata.json();
  await page.clock.setFixedTime(new Date(Date.UTC(ultimoAnioClima + 3, 5, 1)));
  const datos = page.waitForResponse(
    `**/datos/v1/temporal/SV-SS/${ultimoAnioClima}.json`,
  );
  await page.goto('/analisis/ficha/SV-SS');
  expect((await datos).ok()).toBe(true);
});

test('el archivo aplica tipo y solapamiento de fechas del enlace', async ({
  page,
  request,
}) => {
  const respuesta = await request.get('/datos/alertas.json');
  const { alertas } = await respuesta.json();
  const cerrada = alertas.find(
    (alerta: { vigente_hasta: string | null }) => alerta.vigente_hasta,
  );
  expect(cerrada).toBeTruthy();
  const filtros = new URLSearchParams({
    tipo: cerrada.tipo,
    desde: cerrada.vigente_hasta,
    hasta: cerrada.vigente_hasta,
  });

  await page.goto(`/alertas/archivo?${filtros}`);
  await expect(page.locator(`#alerta-${cerrada.id}`)).toBeVisible();
  await expect(page.locator('select[name="tipo"]')).toHaveValue(cerrada.tipo);
  await expect(page.locator('input[name="desde"]')).toHaveValue(
    cerrada.vigente_hasta,
  );
  await expect(
    page.locator('[data-alerta]:not([data-alerta-historica])'),
  ).toHaveCount(0);
});
