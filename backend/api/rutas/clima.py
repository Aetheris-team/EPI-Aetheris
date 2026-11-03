"""Ruta interna del refresco recurrente de clima (ADR 0027, A2 del ADR 0018).

Bearer contra CLIMA_REFRESCO_TOKEN. En la versión para Dockyard no hay
workflow que la dispare y sin el token responde 503. Encola cargar_clima.py en segundo plano
y responde 202 de inmediato: el backoff por rate-limit de Open-Meteo puede
tardar varios minutos.
"""

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, Response

from ..clima_refresco import comprobar_token_refresco, ejecutar_refresco_clima


def crear_router(*, limiter, limite_escritura: str) -> APIRouter:
    """`limite_escritura` es RATE_LIMIT_WRITE de main.py."""
    router = APIRouter()

    @router.post("/internal/clima/refrescar", status_code=202)
    @limiter.limit(limite_escritura)
    def clima_refrescar(
        request: Request,
        response: Response,
        tareas: BackgroundTasks,
        authorization: str | None = Header(default=None),
    ):
        """Dispara cargar_clima.py en segundo plano. No expone el resultado."""
        error = comprobar_token_refresco(authorization)
        if error is not None:
            codigo, detalle = error
            raise HTTPException(status_code=codigo, detail=detalle)
        response.headers["Cache-Control"] = "no-store"
        tareas.add_task(ejecutar_refresco_clima)
        return {"detail": "Refresco de clima encolado."}

    return router
