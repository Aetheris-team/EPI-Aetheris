"""Rutas de las alertas de campo (ADR 0013, ADR 0015, ADR 0022).

Decisiones humanas persistidas: no se calculan desde M1-M3 ni desde el
clasificador retirado. GET público por defecto: activa=TRUE y etiqueta IS
NULL. POST/PATCH exigen Bearer contra ALERTAS_TOKEN y llevan su propio límite
(RATE_LIMIT_WRITE, ADR 0017). Sin DELETE.
"""

import os
from contextlib import AbstractContextManager
from datetime import date
from typing import Callable

from fastapi import APIRouter, Header, HTTPException, Request, Response

from ..alertas import (
    DEPARTAMENTOS_ALERTA,
    TIPOS_ALERTA,
    AlertaCrear,
    AlertaParche,
    comprobar_token_escritura,
    consultar_alertas_publicas,
    construir_feed_atom,
    crear_alerta,
    parchear_alerta,
)
from ..respuestas import CACHE_TTL_ALERTAS, cache_control, fallo_base_datos


def _autorizar_escritura_alertas(authorization: str | None) -> None:
    error = comprobar_token_escritura(authorization)
    if error is not None:
        codigo, detalle = error
        raise HTTPException(status_code=codigo, detail=detalle)


def crear_router(
    *,
    limiter,
    abrir_conexion: Callable[[], AbstractContextManager],
    limite_escritura: str,
) -> APIRouter:
    """`limite_escritura` es RATE_LIMIT_WRITE de main.py."""
    router = APIRouter()

    @router.get("/api/alertas")
    def alertas_publicas(
        response: Response,
        tipo: str | None = None,
        desde: date | None = None,
        hasta: date | None = None,
        incluir_inactivas: bool = False,
        incluir_etiquetadas: bool = False,
        departamento: str | None = None,
    ):
        """Lista alertas. Sin parámetros extra: activa=TRUE y etiqueta IS NULL.

        Filtros opcionales combinados con AND: tipo, desde/hasta (solapamiento
        de vigencia), incluir_inactivas, incluir_etiquetadas, departamento
        (nacionales más las que lo incluyen, ADR 0022).
        """
        if departamento is not None and departamento not in DEPARTAMENTOS_ALERTA:
            raise HTTPException(
                status_code=422,
                detail="El parámetro 'departamento' debe ser un código ISO 3166-2 de El Salvador (SV-AH..SV-US).",
            )
        if tipo is not None and tipo not in TIPOS_ALERTA:
            raise HTTPException(
                status_code=422,
                detail="El parámetro 'tipo' debe ser 'dengue' o 'respiratorio'.",
            )
        try:
            with abrir_conexion() as conn:
                cuerpo = consultar_alertas_publicas(
                    conn,
                    tipo=tipo,
                    desde=desde,
                    hasta=hasta,
                    incluir_inactivas=incluir_inactivas,
                    incluir_etiquetadas=incluir_etiquetadas,
                    departamento=departamento,
                )
        except Exception as exc:
            # Contrato propio ({aviso, ultima_revision, alertas}); no se degrada
            # a {disponible:false} como los endpoints respiratorios. Solo se
            # distingue fallo de conexión (503) del resto (500).
            fallo_base_datos(exc)

        cache_control(response, CACHE_TTL_ALERTAS)
        return cuerpo

    @router.get("/api/alertas/feed.xml")
    def alertas_feed(request: Request):
        """Feed Atom con las alertas activas sin etiqueta (mismo criterio que el GET público)."""
        try:
            with abrir_conexion() as conn:
                cuerpo = consultar_alertas_publicas(conn)
        except Exception as exc:
            fallo_base_datos(exc)

        sitio = os.environ.get("SITIO_PUBLICO", "https://epi-aetheris.dev")
        xml = construir_feed_atom(
            cuerpo["alertas"],
            cuerpo["ultima_revision"],
            sitio=sitio,
            api_url=str(request.url),
        )
        return Response(
            content=xml,
            media_type="application/atom+xml",
            headers={"Cache-Control": f"public, max-age={CACHE_TTL_ALERTAS}"},
        )

    @router.post("/api/alertas", status_code=201)
    @limiter.limit(limite_escritura)
    def alertas_crear(
        request: Request,
        cuerpo: AlertaCrear,
        response: Response,
        authorization: str | None = Header(default=None),
    ):
        """Crea una alerta redactada por el equipo. Exige Bearer ALERTAS_TOKEN."""
        _autorizar_escritura_alertas(authorization)
        response.headers["Cache-Control"] = "no-store"
        try:
            with abrir_conexion() as conn:
                creada = crear_alerta(conn, cuerpo)
                conn.commit()
        except HTTPException:
            raise
        except Exception as exc:
            fallo_base_datos(exc)
        return creada

    @router.patch("/api/alertas/{alerta_id}")
    @limiter.limit(limite_escritura)
    def alertas_parchear(
        alerta_id: int,
        request: Request,
        cuerpo: AlertaParche,
        response: Response,
        authorization: str | None = Header(default=None),
    ):
        """Edita una alerta. Como mínimo puede poner activa=false. Sin DELETE."""
        _autorizar_escritura_alertas(authorization)
        response.headers["Cache-Control"] = "no-store"
        if not cuerpo.model_dump(exclude_unset=True):
            raise HTTPException(
                status_code=422,
                detail="El cuerpo debe incluir al menos un campo a modificar.",
            )
        try:
            with abrir_conexion() as conn:
                actualizada = parchear_alerta(conn, alerta_id, cuerpo)
                if actualizada is None:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No existe una alerta con id {alerta_id}.",
                    )
                conn.commit()
        except HTTPException:
            raise
        except Exception as exc:
            fallo_base_datos(exc)
        return actualizada

    return router
