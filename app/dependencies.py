"""FastAPI dependency providers leyendo estado compartido desde
`request.app.state` — mismo patron que `gestiolibra/app/dependencies.py`."""
from fastapi import Request

from libraauth.repository import UserRepository

from .services.clientes import ClienteRepository
from .services.dashboard import DashboardService
from .services.equipos import EquipoRepository
from .services.incidencias import IncidenciaRepository
from .services.sectores import SectorRepository
from .services.tecnicos import TecnicoRepository


def get_user_repository(request: Request) -> UserRepository:
    return request.app.state.users


def get_cliente_repository(request: Request) -> ClienteRepository:
    return request.app.state.clientes


def get_equipo_repository(request: Request) -> EquipoRepository:
    return request.app.state.equipos


def get_incidencia_repository(request: Request) -> IncidenciaRepository:
    return request.app.state.incidencias


def get_tecnico_repository(request: Request) -> TecnicoRepository:
    return request.app.state.tecnicos


def get_sector_repository(request: Request) -> SectorRepository:
    return request.app.state.sectores


def get_dashboard_service(request: Request) -> DashboardService:
    return request.app.state.dashboard
