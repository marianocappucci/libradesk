"""FastAPI dependency providers leyendo estado compartido desde
`request.app.state` — mismo patron que `gestiolibra/app/dependencies.py`."""
from fastapi import Request

from libraauth.repository import UserRepository

from .services.categorias import CategoriaRepository
from .services.clientes import ClienteRepository
from .services.dashboard import DashboardService
from .services.equipos import EquipoRepository
from .services.incidencias import IncidenciaRepository
from .services.reemplazo import ReemplazoService
from .services.remitos_presupuestos import PresupuestoService, RemitoService
from .services.reportes import ReportesService
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


def get_reemplazo_service(request: Request) -> ReemplazoService:
    return request.app.state.reemplazos


def get_tecnico_repository(request: Request) -> TecnicoRepository:
    return request.app.state.tecnicos


def get_sector_repository(request: Request) -> SectorRepository:
    return request.app.state.sectores


def get_categoria_repository(request: Request) -> CategoriaRepository:
    return request.app.state.categorias


def get_dashboard_service(request: Request) -> DashboardService:
    return request.app.state.dashboard


def get_reportes_service(request: Request) -> ReportesService:
    return request.app.state.reportes


def get_remito_service(request: Request) -> RemitoService:
    return request.app.state.remitos


def get_presupuesto_service(request: Request) -> PresupuestoService:
    return request.app.state.presupuestos


def get_data_dir(request: Request) -> str:
    return request.app.state.data_dir
