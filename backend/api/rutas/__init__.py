"""Routers de la API por dominio. Cada módulo expone crear_router(), que
main.py llama al importarse con el limiter y la conexión de la app: así un
importlib.reload(api.main) (los tests de rate limiting, CORS y docs) vuelve a
crear las rutas con la configuración nueva, igual que api/cuentas/rutas.py.
"""
