import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test.describe('Selector interactivo de semana epidemiológica (Epi-Calendar)', () => {
  test.beforeEach(async ({ page }) => {
    // Interceptar llamadas pesadas para que la prueba cargue de inmediato
    await page.route('**/api/**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '[]',
      }),
    );
    await page.goto('/dengue');
  });

  test('el disparador muestra la semana activa y abre el popover del calendario', async ({
    page,
  }) => {
    const selectorToolbar = page.locator('#toolbar-selector-semana');
    await expect(selectorToolbar).toBeVisible();

    const disparador = selectorToolbar.locator('[data-disparador]');
    await expect(disparador).toHaveAttribute('aria-expanded', 'false');
    await expect(disparador).toContainText('SE01');

    // Al hacer clic abre el popover
    await disparador.click();
    await expect(disparador).toHaveAttribute('aria-expanded', 'true');

    const popover = selectorToolbar.locator('[data-panel-popover]');
    await expect(popover).toBeVisible();

    // Contiene encabezado de navegación de meses y pestañas
    await expect(popover.locator('[data-boton-mes-prev]')).toBeVisible();
    await expect(popover.locator('[data-boton-mes-next]')).toBeVisible();
    await expect(popover.locator('[data-select-mes]')).toBeVisible();
    await expect(popover.locator('[data-select-anio]')).toBeVisible();

    // Pestañas disponibles
    const pestanaCalendario = popover.locator('[data-pestana="calendario"]');
    const pestanaCuadricula = popover.locator('[data-pestana="cuadricula"]');
    await expect(pestanaCalendario).toBeVisible();
    await expect(pestanaCuadricula).toBeVisible();
  });

  test('permite navegar entre meses y seleccionar una semana en el calendario', async ({
    page,
  }) => {
    const selectorToolbar = page.locator('#toolbar-selector-semana');
    const disparador = selectorToolbar.locator('[data-disparador]');
    await disparador.click();

    const popover = selectorToolbar.locator('[data-panel-popover]');
    const selectMes = popover.locator('[data-select-mes]');

    // Cambiar a Agosto (mes 8)
    await selectMes.selectOption('8');

    // Buscar la fila de la SE32 y seleccionarla
    const fila32 = popover.locator('[data-fila-semana="32"]').first();
    await expect(fila32).toBeVisible();
    await fila32.click();

    // El popover se cierra y el disparador actualiza a SE32
    await expect(disparador).toHaveAttribute('aria-expanded', 'false');
    await expect(disparador).toContainText('SE32');
    await expect(page).toHaveURL(/week=32/);
  });

  test('permite seleccionar semanas directamente desde la cuadrícula anual (52 semanas)', async ({
    page,
  }) => {
    const selectorToolbar = page.locator('#toolbar-selector-semana');
    const disparador = selectorToolbar.locator('[data-disparador]');
    await disparador.click();

    const popover = selectorToolbar.locator('[data-panel-popover]');
    const pestanaCuadricula = popover.locator('[data-pestana="cuadricula"]');
    await pestanaCuadricula.click();

    const vistaCuadricula = popover.locator('[data-vista-cuadricula]');
    await expect(vistaCuadricula).toBeVisible();

    // Seleccionar SE15 desde la cuadrícula
    const chip15 = popover.locator('[data-chip-semana="15"]').first();
    await expect(chip15).toBeVisible();
    await chip15.click();

    // Verifica que se seleccionó la SE15 y sincronizó con la URL
    await expect(disparador).toContainText('SE15');
    await expect(page).toHaveURL(/week=15/);
  });

  test('soporta cierre accesible con la tecla Escape', async ({ page }) => {
    const selectorToolbar = page.locator('#toolbar-selector-semana');
    const disparador = selectorToolbar.locator('[data-disparador]');
    await disparador.click();

    await expect(disparador).toHaveAttribute('aria-expanded', 'true');
    await page.keyboard.press('Escape');
    await expect(disparador).toHaveAttribute('aria-expanded', 'false');
  });

  test('cumple con los estándares de accesibilidad WCAG / axe-core', async ({
    page,
  }) => {
    const selectorToolbar = page.locator('#toolbar-selector-semana');
    const disparador = selectorToolbar.locator('[data-disparador]');
    await disparador.click();

    // Auditoría de a11y sobre el selector abierto
    const resultados = await new AxeBuilder({ page })
      .include('#toolbar-selector-semana')
      .analyze();

    expect(resultados.violations).toEqual([]);
  });
});
