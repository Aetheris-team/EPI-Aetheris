import { defineConfig, devices } from '@playwright/test';

const URL_BASE = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:4321';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  // Un solo worker: el dev server de Vite (Astro) reoptimiza dependencias de
  // forma perezosa; con varios workers pidiendo /dengue y /respiratorio a la
  // vez pueden ocurrir carreras que devuelven 504 y recargan la página a
  // mitad de test. La suite completa tarda ~30 s en serie.
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: 'list',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: URL_BASE,
    // La barra del análisis se contrae sola a los 5 s sin actividad
    // (ToolbarAnalisis.astro); con eso los specs verían los controles
    // desaparecer a mitad de test. Su propio spec arranca sin esta clave.
    storageState: {
      cookies: [],
      origins: [
        {
          origin: new URL(URL_BASE).origin,
          localStorage: [{ name: 'epi:toolbar-fija', value: '1' }],
        },
      ],
    },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
