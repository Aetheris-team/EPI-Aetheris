"""Exporta el contrato público de lectura a archivos para el sitio Astro."""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from .alertas import construir_feed_atom
from .analisis import ANIOS_ANALISIS_DENGUE
from .main import _abrir_conexion
from .neumonias import ANIOS_NEUMONIAS
from .vigilancia import construir_integridad

API = "http://127.0.0.1:8000"
ARCHIVOS_PUBLICOS = (
    "casos-nacional",
    "riesgo-nacional",
    "nowcast-dengue",
    "nowcast-dengue/retrospectivo",
    "clima-dengue/por-anio",
    "clima-dengue/multipais",
    "ira/nacional",
    "neumonias/nacional",
    "ira/departamental",
    "neumonias/departamental",
    "respiratorios/cobertura",
    "respiratorios/virus",
)


def pedir(ruta, **filtros):
    url = f"{API}/api/{ruta}"
    if filtros:
        url += "?" + urlencode(filtros)
    with urlopen(url, timeout=60) as respuesta:
        cuerpo = json.load(respuesta)
    if isinstance(cuerpo, dict) and cuerpo.get("disponible") is False:
        # Los módulos respiratorios tienen una respuesta degradada con HTTP 200.
        # Un volcado con datos debe poder exportar sus catálogos y series.
        if ruta.startswith(("ira/", "neumonias/", "respiratorios/")):
            raise RuntimeError(f"Falló la exportación de {url}: {cuerpo}")
    return cuerpo


def esperar_api():
    for _ in range(60):
        try:
            with urlopen(f"{API}/health", timeout=2):
                return
        except URLError:
            time.sleep(1)
    raise RuntimeError("La API temporal no pudo conectarse al volcado de datos.")


def obtener_corte():
    with _abrir_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT GREATEST(
                (SELECT max(fecha_ingesta) FROM variables_ambientales),
                (SELECT max(fecha_ingesta) FROM casos_epidemiologicos),
                (SELECT max(fecha_ingesta) FROM vigilancia_virus_respiratorios),
                (SELECT max(fecha_procesado) FROM boletines_procesados)
            ) AT TIME ZONE 'UTC',
            (SELECT max(anio) FROM variables_ambientales)
            """
        )
        ultima_ingesta, ultimo_anio_clima = cur.fetchone()
        if ultima_ingesta is None or ultimo_anio_clima is None:
            raise RuntimeError("El volcado debe contener datos epidemiológicos y climáticos.")
        cur.execute("SELECT codigo FROM regiones WHERE nivel_admin = 1 ORDER BY codigo")
        departamentos = tuple(codigo for (codigo,) in cur.fetchall())
    return ultima_ingesta.date(), ultimo_anio_clima, departamentos


def guardar_json(destino, ruta, cuerpo):
    archivo = destino / f"{ruta}.json"
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(
        json.dumps(cuerpo, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )


def exportar(destino, sitio):
    esperar_api()
    corte, ultimo_anio_clima, departamentos = obtener_corte()
    anios_clima = range(min(ANIOS_ANALISIS_DENGUE), ultimo_anio_clima + 1)

    def exportar_ruta(ruta, archivo=None, **filtros):
        cuerpo = pedir(ruta, **filtros)
        guardar_json(destino, archivo or ruta, cuerpo)
        return cuerpo

    def exportar_semana_anual(anio):
        espacial = {
            semana: pedir("v1/spatial/current", week=semana, year=anio)
            for semana in range(1, 54)
        }
        with _abrir_conexion() as conn:
            integridad = {
                semana: construir_integridad(conn, week=semana, year=anio, hoy=corte)
                for semana in range(1, 54)
            }
        guardar_json(destino, f"v1/spatial/current/{anio}", espacial)
        guardar_json(destino, f"v1/vigilancia/integridad/{anio}", integridad)

    def exportar_procedencia(anio, codigo):
        procedencia = {
            serie: {
                semana: pedir(
                    "v1/analisis/dengue/procedencia",
                    year=anio, week=semana, dept=codigo, serie=serie,
                )
                for semana in range(1, 54)
            }
            for serie in ("probable", "confirmado")
        }
        guardar_json(destino, f"v1/analisis/dengue/procedencia/{anio}/{codigo}", procedencia)

    archivos = {ruta: exportar_ruta(ruta) for ruta in ARCHIVOS_PUBLICOS}
    with _abrir_conexion() as conn:
        resumen = construir_integridad(conn, hoy=corte)
    guardar_json(destino, "v1/vigilancia/integridad", resumen)
    guardar_json(destino, "corte", {
        "fecha": corte.isoformat(),
        "ultimo_anio_clima": ultimo_anio_clima,
        "series": resumen["antiguedad"],
    })
    alertas = exportar_ruta("alertas", incluir_inactivas="true")
    activas = exportar_ruta("alertas", archivo="alertas/registradas-activas")
    fuente = construir_feed_atom(
        alertas["alertas"], alertas["ultima_revision"],
        sitio=sitio, api_url=f"{sitio}/datos/alertas/feed.xml",
        historico=True,
    )
    (destino / "alertas/feed.xml").write_text(fuente + "\n", encoding="utf-8")

    with ThreadPoolExecutor(max_workers=6) as pool:
        trabajos = []
        for anio in anios_clima:
            trabajos.append(pool.submit(exportar_semana_anual, anio))
            for codigo in departamentos:
                ruta = f"v1/temporal/{codigo}"
                trabajos.append(pool.submit(exportar_ruta, ruta, f"{ruta}/{anio}", anio=anio))
        for anio in ANIOS_ANALISIS_DENGUE:
            ruta = "v1/analisis/dengue"
            trabajos.append(pool.submit(exportar_ruta, ruta, f"{ruta}/{anio}", year=anio))
            for codigo in departamentos:
                ruta = f"v1/presion/temporal/{codigo}"
                trabajos.append(pool.submit(exportar_ruta, ruta, f"{ruta}/{anio}", anio=anio))
                trabajos.append(pool.submit(exportar_procedencia, anio, codigo))
        for anio in ANIOS_NEUMONIAS:
            trabajos.append(pool.submit(exportar_ruta, f"neumonias/heatmap/{anio}"))
        for evento in ("ira", "neumonias"):
            for codigo in departamentos:
                trabajos.append(pool.submit(exportar_ruta, f"{evento}/temporal/{codigo}"))
        for serie in archivos["respiratorios/virus"]["series"]:
            virus, metrica = serie["virus"], serie["metrica"]
            trabajos.append(pool.submit(
                exportar_ruta, "respiratorios/temporal", f"respiratorios/temporal/{virus}/{metrica}",
                virus=virus, metrica=metrica,
            ))
        for trabajo in trabajos:
            trabajo.result()

    print(f"Corte {corte}: {len(departamentos)} departamentos y {len(activas['alertas'])} alertas marcadas activas.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destino", type=Path)
    parser.add_argument("--sitio", default="https://epi-aetheris.dev")
    args = parser.parse_args()
    exportar(args.destino, args.sitio.rstrip("/"))
