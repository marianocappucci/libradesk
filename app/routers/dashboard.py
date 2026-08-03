from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_cliente_repository, get_dashboard_service
from ..services.clientes import ClienteRepository
from ..services.dashboard import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def summary(
    date_from: str | None = None, date_to: str | None = None,
    dashboard: DashboardService = Depends(get_dashboard_service),
):
    return dashboard.summary(date_from, date_to)


@router.get("/cliente/{cliente_id}")
def cliente(
    cliente_id: int,
    dias_garantia: int = 60,
    dashboard: DashboardService = Depends(get_dashboard_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    """La ficha de `/clientes/:id`.

    Cuelga del router de **dashboard** y no de `/api/clientes/{id}/resumen`
    a proposito: asi queda detras del mismo `require_module("dashboard")`
    que el resumen global (ver `main.py`). Bajo `/api/clientes` seria parte
    del core de tickets, que no se gatea, y un plan sin dashboard igual
    tendria el dashboard del cliente.
    """
    ficha = clientes.get(cliente_id)
    if ficha is None:
        raise HTTPException(404, "cliente not found")
    return {"cliente": ficha, **dashboard.cliente(cliente_id, dias_garantia)}
