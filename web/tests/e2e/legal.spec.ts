import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

// Capa legal y de confianza: privacidad, términos, aviso legal, contacto,
// acerca de y la 404. Son páginas estáticas -- ninguna toca el backend, así
// que estos tests no gastan la ventana de 30/minuto de los endpoints pesados.
//
// Lo que NO se comprueba aquí: que no queden marcadores sin rellenar en el
// texto legal. Esa es una puerta de despliegue, no de suite: vive en el bloque
// de comprobaciones de build, que sí corre antes de pushear. El patrón tiene
// que nombrar los marcadores, no buscar «» a secas: las comillas angulares son
// puntuación normal en español y aparecen legítimamente en estas páginas
// («tal cual», «Recordar el token en este navegador»).
//
//   grep -rnE "«(RESPONSABLE|DOMICILIO|CORREO_CONTACTO|CORREO_SEGURIDAD|JURISDICCION)»" dist/

const PAGINAS = [
  { ruta: '/legal/privacidad', h1: 'Política de privacidad' },
  { ruta: '/legal/terminos', h1: 'Términos de uso' },
  { ruta: '/legal/aviso-legal', h1: 'Aviso legal' },
  { ruta: '/contacto', h1: 'Contacto' },
  { ruta: '/acerca-de', h1: 'Acerca de EPI-Aetheris' },
];

for (const pagina of PAGINAS) {
  test(`${pagina.ruta} responde con un solo h1 y conserva la navegación`, async ({
    page,
  }) => {
    const respuesta = await page.goto(pagina.ruta);
    expect(respuesta?.status()).toBe(200);

    await expect(page.locator('main h1')).toHaveText(pagina.h1);
    await expect(
      page.locator('nav[aria-label="Navegación principal"]'),
    ).toBeVisible();
    await expect(page.locator('#contenido-principal')).toBeVisible();
  });
}

test('las tres legales se enlazan entre sí y con contacto', async ({
  page,
}) => {
  await page.goto('/legal/privacidad');
  // Los enlaces viven dentro de secciones plegadas: se despliega todo antes.
  await page.getByRole('button', { name: 'Expandir todo' }).click();
  const documento = page.locator('.doc-texto');
  await expect(
    documento.getByRole('link', { name: 'términos de uso' }),
  ).toHaveAttribute('href', '/legal/terminos');
  await expect(
    documento.getByRole('link', { name: 'aviso legal' }).last(),
  ).toHaveAttribute('href', '/legal/aviso-legal');
  await expect(
    documento.getByRole('link', { name: 'contacto' }).last(),
  ).toHaveAttribute('href', '/contacto');
});

test('el pie expone la sección legal en cualquier página', async ({ page }) => {
  await page.goto('/');
  const navFooter = page.locator('footer');
  await expect(
    navFooter.getByRole('link', { name: 'Privacidad' }),
  ).toHaveAttribute('href', '/legal/privacidad');
  await expect(
    navFooter.getByRole('link', { name: 'Términos de uso' }),
  ).toHaveAttribute('href', '/legal/terminos');
  await expect(
    navFooter.getByRole('link', { name: 'Aviso legal' }),
  ).toHaveAttribute('href', '/legal/aviso-legal');
  await expect(
    navFooter.getByRole('link', { name: 'Contacto' }),
  ).toHaveAttribute('href', '/contacto');
});

test('la política de privacidad nombra las transferencias reales a terceros', async ({
  page,
}) => {
  await page.goto('/legal/privacidad');
  const documento = page.locator('.doc-texto');
  // Las teselas de OSM son la única transferencia sustantiva al navegar y la
  // más fácil de omitir al redactar: no hay ningún <script> de terceros que
  // la delate. Si alguien reescribe la política, esto lo frena.
  await expect(documento).toContainText('OpenStreetMap');
  await expect(documento).toContainText('Render');
  await expect(documento).toContainText('no recibe cookies');
});

test('la política de privacidad declara los datos y los encargados de las cuentas', async ({
  page,
}) => {
  await page.goto('/legal/privacidad');
  const documento = page.locator('.doc-texto');
  // Con cuentas hay más encargados que Render y OSM, y una cookie de sesión.
  // Si alguien quita un proveedor del texto sin quitarlo del sistema, esto lo
  // frena. Las cuentas se describen aunque estén apagadas: la política es la
  // condición para la primera invitación (ADR 0024).
  await expect(documento).toContainText('Resend');
  await expect(documento).toContainText('Cloudflare');
  await expect(documento).toContainText('Have I Been Pwned');
  await expect(documento).toContainText('__Host-epi_sid');
  await expect(documento).toContainText('72 horas');
  await expect(documento).toContainText('Agencia de Ciberseguridad del Estado');
});

test('la política y los términos no dejan marcadores pendientes a la vista', async ({
  page,
}) => {
  // Los marcadores «PENDIENTE_…» señalan datos que solo el responsable puede
  // dar. Con el plazo de las copias ya decidido no queda ninguno: si vuelve a
  // aparecer uno, este test falla antes de publicar.
  for (const ruta of ['/legal/privacidad', '/legal/terminos']) {
    await page.goto(ruta);
    await expect(page.locator('.doc-texto')).not.toContainText('PENDIENTE_');
  }
});

test('los términos fijan los deberes de quien publica con una cuenta', async ({
  page,
}) => {
  await page.goto('/legal/terminos');
  await page.getByRole('button', { name: 'Expandir todo' }).click();
  const documento = page.locator('.doc-texto');
  await expect(
    documento.getByRole('heading', {
      level: 2,
      name: /Deberes de quien publica/,
    }),
  ).toBeVisible();
  await expect(documento).toContainText('Sin datos personales de pacientes');
  await expect(documento).toContainText('Firma con nombre e institución');
  await expect(documento).toContainText('ese motivo es público');
  await expect(
    documento.getByRole('link', { name: 'aviso de sensibilidad' }).first(),
  ).toHaveAttribute('href', '/biblioteca/05-sensibilidad-y-honestidad');
});

test('los términos y el aviso legal no presentan violaciones automáticas WCAG A o AA', async ({
  page,
}) => {
  for (const ruta of ['/legal/terminos', '/legal/aviso-legal', '/legal']) {
    await page.goto(ruta);
    const resultados = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(resultados.violations, ruta).toEqual([]);
  }
});

test('la 404 mantiene la navegación y sale del índice', async ({ page }) => {
  await page.goto('/ruta-que-no-existe-jamas');
  // En el dev server Astro sirve su propia página de error, así que este test
  // afirma sobre la 404 propia solo cuando se corre contra el build.
  const esPaginaPropia = await page
    .locator('main h1', { hasText: 'Esta página no existe' })
    .isVisible()
    .catch(() => false);
  test.skip(
    !esPaginaPropia,
    'La 404 propia solo se sirve desde el build (astro preview o producción)',
  );

  await expect(
    page.locator('nav[aria-label="Navegación principal"]'),
  ).toBeVisible();
  await expect(page.locator('head meta[name="robots"]')).toHaveAttribute(
    'content',
    'noindex, nofollow',
  );
});

test('las páginas legales no presentan violaciones automáticas WCAG A o AA', async ({
  page,
}) => {
  await page.goto('/legal/privacidad');
  const resultados = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(resultados.violations).toEqual([]);
});

test('la página de contacto no presenta violaciones automáticas WCAG A o AA', async ({
  page,
}) => {
  await page.goto('/contacto');
  const resultados = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(resultados.violations).toEqual([]);
});

test('las páginas de texto largo se leen por secciones desplegables', async ({
  page,
}) => {
  await page.goto('/legal/terminos');
  const secciones = page.locator('.doc-texto details.acordeon');
  expect(await secciones.count()).toBeGreaterThan(5);
  // Todas arrancan plegadas, y el título sigue siendo un h2.
  await expect(page.locator('.doc-texto details.acordeon[open]')).toHaveCount(
    0,
  );
  await expect(
    secciones.nth(1).locator('summary').getByRole('heading', { level: 2 }),
  ).toBeVisible();

  await secciones.nth(1).locator('summary').click();
  await expect(secciones.nth(1)).toHaveAttribute('open', '');

  const alternar = page.getByRole('button', { name: /Expandir todo/ });
  await alternar.click();
  for (const seccion of await secciones.all()) {
    await expect(seccion).toHaveAttribute('open', '');
  }
  await expect(
    page.getByRole('button', { name: 'Contraer todo' }),
  ).toBeVisible();
});

test('un enlace con ancla abre la sección cerrada que lo contiene', async ({
  page,
}) => {
  await page.goto('/legal/terminos#licencias');
  const seccion = page.locator('details.acordeon:has(#licencias)');
  await expect(seccion).toHaveAttribute('open', '');
  await expect(page.locator('#licencias')).toBeInViewport();
});

test('la documentación no usa la etiqueta code en el texto', async ({
  page,
}) => {
  for (const ruta of [
    '/biblioteca/01-que-es',
    '/biblioteca/03-funciones',
    '/biblioteca/04-fuentes-de-datos',
    '/legal/privacidad',
    '/legal/terminos',
  ]) {
    await page.goto(ruta);
    await expect(page.locator('.doc-texto :not(pre) > code')).toHaveCount(0);
  }
});

test('los acordeones se pliegan y despliegan con animación', async ({
  page,
}) => {
  await page.goto('/legal/terminos');
  await page.evaluate(() => {
    document.documentElement.dataset.animaciones = 'on';
  });
  const seccion = page.locator('.doc-texto details.acordeon').first();
  const cuerpo = seccion.locator('.acordeon-cuerpo');
  await seccion.locator('summary').click();
  // Mientras anima, hay una animación de altura en curso sobre el cuerpo.
  expect(
    await cuerpo.evaluate((el) => el.getAnimations().length),
  ).toBeGreaterThan(0);
  await expect(seccion).toHaveAttribute('open', '');
  await expect
    .poll(() => cuerpo.evaluate((el) => el.getAnimations().length))
    .toBe(0);

  await seccion.locator('summary').click();
  // Al plegar, `open` se mantiene hasta que acaba la animación.
  await expect(seccion).toHaveAttribute('open', '');
  await expect(seccion).not.toHaveAttribute('open', '');
});

test('con las animaciones apagadas el acordeón cambia al instante', async ({
  page,
}) => {
  await page.goto('/legal/terminos');
  await page.evaluate(() => {
    document.documentElement.dataset.animaciones = 'off';
  });
  const seccion = page.locator('.doc-texto details.acordeon').first();
  await seccion.locator('summary').click();
  await expect(seccion).toHaveAttribute('open', '');
  await seccion.locator('summary').click();
  await expect(seccion).not.toHaveAttribute('open', '');
});

test('el buscador filtra secciones, resalta y restaura', async ({ page }) => {
  await page.goto('/biblioteca/03-funciones');
  const secciones = page.locator('.doc-texto details.acordeon');
  const total = await secciones.count();
  const entrada = page.getByLabel('Buscar en este documento');
  await entrada.fill('presion');
  await expect(page.locator('.doc-texto mark').first()).toBeVisible();
  expect(
    await page.locator('.doc-texto details.acordeon:visible').count(),
  ).toBeLessThan(total);
  await expect(page.locator('[data-doc-buscar-estado]')).toContainText(
    'coincidencia',
  );
  await entrada.fill('zzzxqw');
  await expect(page.locator('[data-doc-buscar-estado]')).toHaveText(
    'Sin resultados.',
  );
  await entrada.press('Escape');
  await expect(entrada).toHaveValue('');
  await expect(page.locator('.doc-texto mark')).toHaveCount(0);
  await expect(page.locator('.doc-texto details.acordeon[open]')).toHaveCount(
    0,
  );
  expect(
    await page.locator('.doc-texto details.acordeon:visible').count(),
  ).toBe(total);
});

test('el índice de la página abre y lleva a la sección', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/biblioteca/03-funciones');
  const enlace = page.locator('[data-doc-indice] a').nth(2);
  const id = (await enlace.getAttribute('href'))!.slice(1);
  await enlace.click();
  await expect(page.locator(`details.acordeon:has(#${id})`)).toHaveAttribute(
    'open',
    '',
  );
  await expect(page.locator(`#${id}`)).toBeInViewport();
});

test('la biblioteca enlaza al resto de documentos a la izquierda', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/biblioteca/03-funciones');
  const nav = page.getByRole('navigation', { name: 'Biblioteca' });
  await expect(nav.locator('[aria-current="page"]')).toHaveCount(1);
  expect(await nav.getByRole('link').count()).toBeGreaterThan(3);
  const cajaNav = await nav.boundingBox();
  const cajaTexto = await page.locator('article').boundingBox();
  expect(cajaNav!.x + cajaNav!.width).toBeLessThanOrEqual(cajaTexto!.x);
});
