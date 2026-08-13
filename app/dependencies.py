"""FastAPI dependency providers leyendo estado compartido desde
`request.app.state` — mismo patron que `gestiolibra/app/dependencies.py`."""
from fastapi import Request

from libraauth.auditoria import AuditoriaRepository
from libraauth.auth_events import AuthEventRepository
from libraauth.repository import UserRepository

from .services.activos import ActivoRepository
from .services.categorias import CategoriaRepository
from .services.clientes import ClienteRepository
from .services.contratos import ContratoRepository
from .services.dashboard import DashboardService
from .services.depositos import DepositoRepository
from .services.equipos import EquipoRepository
from .services.equipos_trabajo import EquipoTrabajoRepository
from .services.facturacion_config import ConfiguracionFacturacion
from .services.facturacion_externa import PuenteFacturacion
from .services.firma import FirmaRepository
from .services.incidencias import IncidenciaRepository
from .services.informes import InformeService
from .services.proveedores import ProveedorRepository
from .services.servicios import ServicioRepository
from .services.reemplazo import ReemplazoService
from .services.ingresos import IngresoRepository
from .services.reparaciones import ReparacionRepository
from .services.remitos_presupuestos import PresupuestoService, RemitoService
from .services.reportes import ReportesService
from .services.sectores import SectorRepository
from .services.tecnicos import TecnicoRepository


def get_user_repository(request: Request) -> UserRepository:
    return request.app.state.users


def get_auditoria_repository(request: Request) -> AuditoriaRepository:
    return request.app.state.auditoria


def get_auth_events_repository(request: Request) -> AuthEventRepository:
    return request.app.state.auth_events


def get_cliente_repository(request: Request) -> ClienteRepository:
    return request.app.state.clientes


def get_equipo_repository(request: Request) -> EquipoRepository:
    return request.app.state.equipos


def get_deposito_repository(request: Request) -> DepositoRepository:
    return request.app.state.depositos


def get_incidencia_repository(request: Request) -> IncidenciaRepository:
    return request.app.state.incidencias


def get_firma_repository(request: Request) -> FirmaRepository:
    return request.app.state.firmas


def get_reemplazo_service(request: Request) -> ReemplazoService:
    return request.app.state.reemplazos


def get_tecnico_repository(request: Request) -> TecnicoRepository:
    return request.app.state.tecnicos


def get_sector_repository(request: Request) -> SectorRepository:
    return request.app.state.sectores


def get_categoria_repository(request: Request) -> CategoriaRepository:
    return request.app.state.categorias


def get_proveedor_repository(request: Request) -> ProveedorRepository:
    return request.app.state.proveedores


def get_servicio_repository(request: Request) -> ServicioRepository:
    return request.app.state.servicios


def get_reparacion_repository(request: Request) -> ReparacionRepository:
    return request.app.state.reparaciones


def get_ingreso_repository(request: Request) -> IngresoRepository:
    return request.app.state.ingresos


def get_equipo_trabajo_repository(request: Request) -> EquipoTrabajoRepository:
    return request.app.state.equipos_trabajo


def get_activo_repository(request: Request) -> ActivoRepository:
    return request.app.state.activos


def get_contrato_repository(request: Request) -> ContratoRepository:
    return request.app.state.contratos


def get_dashboard_service(request: Request) -> DashboardService:
    return request.app.state.dashboard


def get_reportes_service(request: Request) -> ReportesService:
    return request.app.state.reportes


def get_informe_service(request: Request) -> InformeService:
    return request.app.state.informes


def get_remito_service(request: Request) -> RemitoService:
    return request.app.state.remitos


def get_presupuesto_service(request: Request) -> PresupuestoService:
    return request.app.state.presupuestos


def get_puente_facturacion(request: Request) -> PuenteFacturacion:
    return request.app.state.puente_facturacion


def get_config_facturacion(request: Request) -> ConfiguracionFacturacion:
    return request.app.state.config_facturacion


def get_data_dir(request: Request) -> str:
    return request.app.state.data_dir
