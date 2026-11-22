/** Ruta de un archivo JSON del corte público. */
export function urlDato(ruta: string): string {
  return `/datos/${ruta}.json`;
}

const archivos = new Map<string, Promise<unknown>>();

/** Comparte un archivo entre distintas selecciones dentro del mismo corte. */
export function leerDato<T>(ruta: string): Promise<T> {
  const url = urlDato(ruta);
  let solicitud = archivos.get(url);
  if (!solicitud) {
    solicitud = fetch(url)
      .then((respuesta) => {
        if (!respuesta.ok) {
          throw new Error(`No se pudo leer ${url} (${respuesta.status}).`);
        }
        return respuesta.json();
      })
      .catch((error: unknown) => {
        archivos.delete(url);
        throw error;
      });
    archivos.set(url, solicitud);
  }
  return solicitud as Promise<T>;
}

export function ultimoAnioClima(): number {
  return import.meta.env?.PUBLIC_ULTIMO_ANIO_CLIMA ?? new Date().getFullYear();
}
