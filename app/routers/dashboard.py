from fastapi import APIRouter, Depends

from ..dependencies import get_dashboard_service
from ..services.dashboard import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def summary(
    date_from: str | None = None, date_to: str | None = None,
    dashboard: DashboardService = Depends(get_dashboard_service),
):
    return dashboard.summary(date_from, date_to)
