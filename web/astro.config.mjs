import { defineConfig, fontProviders } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import icon from 'astro-icon';
import sitemap from '@astrojs/sitemap';

// El único origen de datos al que el navegador puede conectarse además del
// propio sitio: la API. Sale de la misma variable que usa el código (build).
const apiBase = process.env.PUBLIC_API_URL ?? 'http://localhost:8000';

// Configuración principal del framework Astro
export default defineConfig({
  // Dominio de producción de ESTE repo. aetheris-nitor es el fork-vitrina de
  // web/: se despliega solo, en su propio Static Site de Render, y su dominio
  // propio es epi-aetheris.dev (ya listado en CORS_ALLOWED_ORIGINS del
  // backend). El valor anterior, epi-aetheris-web.onrender.com, es el
  // despliegue del monorepo: con él, cada página emitía canonical y og:url
  // apuntando a OTRO sitio, y el sitemap habría heredado el error.
  site: 'https://epi-aetheris.dev',
  // Precarga el HTML de cualquier enlace del sitio al pasar el cursor /
  // entrar en viewport -- navegación casi instantánea entre las 5 vistas.
  prefetch: {
    prefetchAll: true,
  },
  // /panel se renombró a /dengue (#70). La ruta vieja estuvo en producción
  // (bookmarks, enlaces compartidos, indexación) -- este redirect la preserva.
  // En build estático Astro genera una página de redirección por cada entrada.
  redirects: {
    '/panel': '/dengue',
    // No hay índice de fichas: el listado vive en la Biblioteca.
    '/biblioteca/fichas': '/biblioteca',
  },
  // Fonts API de Astro (estable desde v6): auto-hospeda los ficheros en
  // build y genera fallbacks con métricas ajustadas (size-adjust vía
  // capsize, optimizedFallbacks por defecto). Sin preconnect a Google ni
  // hojas render-blocking. No se usa preload -- #87 (a576b3a) difirió las
  // fuentes del render crítico a propósito; el swap lo cubre el fallback
  // ajustado.
  fonts: [
    {
      provider: fontProviders.google(),
      name: 'Inter',
      cssVariable: '--font-inter',
      // 400 cuerpo · 500 font-medium · 600 font-semibold · 700 monograma.
      weights: [400, 500, 600, 700],
      display: 'swap',
      // Sin restringir `styles`: /biblioteca renderiza markdown y puede
      // contener <em>; se conserva la itálica real de Inter.
      fallbacks: ['Arial', 'sans-serif'],
    },
    {
      provider: fontProviders.google(),
      name: 'IBM Plex Mono',
      cssVariable: '--font-plex-mono',
      // Solo peso normal en uso (etiquetas de ejes, valores, código inline).
      weights: [400],
      display: 'swap',
      styles: ['normal'],
      fallbacks: ['ui-monospace', 'monospace'],
    },
    {
      provider: fontProviders.google(),
      name: 'Fraunces',
      cssVariable: '--font-fraunces',
      // Voz de titular. Se fija el eje óptico alto (opsz 144) para conservar
      // el serif editorial de alto contraste; solo H1/H2 de la landing.
      weights: [600, 700],
      display: 'swap',
      styles: ['normal'],
      variationSettings: '"opsz" 144',
      fallbacks: ['Georgia', 'serif'],
    },
  ],
  // Iconos: Tabler (MIT) y Simple Icons (CC0, logotipos) via astro-icon. El SVG se inserta inline en build,
  // solo los iconos usados, sin JavaScript ni fuente de iconos en cliente.
  // Se usan a traves de src/components/Icono.astro, no de <Icon> directo.
  integrations: [
    icon({ include: { tabler: ['*'], 'simple-icons': ['*'] } }),
    // Sitemap a partir de `site`. Quedan fuera las rutas que no son
    // contenido público: /alertas/nueva (formulario de operadores, además
    // marcado noindex en su propia página), /cuenta y /admin (pantallas de
    // cuentas, también noindex), /demos (recorridos animados para
    // enseñar o grabar, también noindex) y /panel, que no es una página sino
    // la redirección generada por `redirects` a /dengue.
    sitemap({
      filter: (pagina) =>
        !pagina.includes('/alertas/nueva') &&
        !pagina.includes('/cuenta') &&
        !pagina.includes('/admin') &&
        !pagina.includes('/panel') &&
        !pagina.endsWith('/biblioteca/fichas/') &&
        !pagina.includes('/configuracion') &&
        !pagina.includes('/demos') &&
        !pagina.includes('/incrustar'),
    }),
  ],
  // Política de contenido (cuentas con sesión y llaves de acceso: un XSS aquí
  // tiene más alcance que antes). Astro calcula los hashes de los scripts y
  // estilos que emite y la inserta como <meta>; las cabeceras de Render no
  // se pueden versionar con el sitio. frame-ancestors no admite <meta>: se
  // pone como cabecera en el panel (ver docs de despliegue).
  // Consecuencia: un <script is:inline> con código no se ejecuta, porque Astro no
  // lo hashea. Los scripts van sin is:inline (se empaquetan); los JSON de datos
  // (type="application/json") no cuentan como script.
  security: {
    csp: {
      directives: [
        "default-src 'self'",
        `connect-src 'self' ${apiBase}`,
        // Teselas de OpenStreetMap en los mapas de Leaflet; data: y blob: para
        // las imágenes que generan los gráficos al exportar.
        "img-src 'self' data: blob: https://*.tile.openstreetmap.org",
        "font-src 'self' data:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
      ],
      // ECharts y Leaflet escriben atributos style en línea; los estilos en
      // <style> y los scripts siguen limitados a los hashes calculados.
      styleDirective: {
        resources: [{ resource: "'unsafe-inline'", kind: 'attribute' }],
      },
    },
  },
  server: {
    // Permite que el servidor sea accesible desde fuera del contenedor Docker
    host: true,
    // Puerto estándar expuesto para la interfaz de desarrollo web
    port: 4321,
  },
  vite: {
    // Tailwind v4 se integra como plugin de Vite directamente -- @astrojs/tailwind
    // (la integración anterior) no soporta Tailwind v4 ni Astro 6+.
    plugins: [tailwindcss()],
  },
});
