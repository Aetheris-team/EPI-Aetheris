/* PWA de solo lectura: prioriza la edición publicada y conserva lo ya consultado. */
const corte =
  new URL(self.location.href).searchParams.get('corte') ?? 'sin-corte';
const CACHE = `epi-estatico-v3-${corte}`;
const PREVIO = ['/', '/alertas', '/datos/alertas/registradas-activas.json'];

self.addEventListener('install', (evento) => {
  evento.waitUntil(guardar(PREVIO).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((claves) =>
        Promise.all(
          claves
            .filter(
              (clave) =>
                /^(epi-estatico-|epi-shell-|epi-api-)/.test(clave) &&
                clave !== CACHE,
            )
            .map((clave) => caches.delete(clave)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

function esLocal(url) {
  const destino = new URL(url, self.location.origin);
  return (
    destino.origin === self.location.origin &&
    !destino.pathname.startsWith('/api/')
  );
}

async function guardar(urls) {
  const cache = await caches.open(CACHE);
  await Promise.allSettled(
    urls
      .filter((url) => typeof url === 'string' && esLocal(url))
      .map((url) => cache.add(new Request(url, { cache: 'reload' }))),
  );
}

self.addEventListener('message', (evento) => {
  const datos = evento.data;
  if (datos?.tipo !== 'precache' || !Array.isArray(datos.urls)) return;
  evento.waitUntil(
    guardar(datos.urls).then(
      () => evento.ports[0]?.postMessage({ ok: true }),
      () => evento.ports[0]?.postMessage({ ok: false }),
    ),
  );
});

async function desdeRed(peticion, cache) {
  const respuesta = await fetch(peticion);
  if (respuesta.ok) {
    await cache.put(peticion, respuesta.clone()).catch(() => undefined);
  }
  return respuesta;
}

async function responder(peticion, ruta) {
  const cache = await caches.open(CACHE);
  // Los recursos compilados de Astro ya incluyen un hash en el nombre.
  if (ruta.startsWith('/_astro/')) {
    const guardada = await cache.match(peticion, { ignoreVary: true });
    if (guardada) return guardada;
  }

  try {
    // HTML y datos se revalidan primero para evitar mostrar un corte antiguo
    // mientras hay red. Un 404 nuevo también prevalece sobre la copia anterior.
    return await desdeRed(peticion, cache);
  } catch (error) {
    const guardada = await cache.match(peticion, { ignoreVary: true });
    if (!guardada) throw error;
    if (!ruta.startsWith('/datos/')) return guardada;

    const cabeceras = new Headers(guardada.headers);
    cabeceras.set('X-EPI-Cache', 'sw');
    cabeceras.delete('Content-Encoding');
    cabeceras.delete('Content-Length');
    return new Response(guardada.body, {
      status: guardada.status,
      statusText: guardada.statusText,
      headers: cabeceras,
    });
  }
}

self.addEventListener('fetch', (evento) => {
  const peticion = evento.request;
  if (peticion.method !== 'GET' || !esLocal(peticion.url)) return;
  const ruta = new URL(peticion.url).pathname;
  evento.respondWith(responder(peticion, ruta));
});
