"""FastAPI dependency providers leyendo estado compartido desde
`request.app.state` — mismo patron que `gestiolibra/app/dependencies.py`."""
from fastapi import Request
from libraauth.auditoria import AuditoriaRepository
from libraauth.auth_events import AuthEventRepository
from libraauth.repository import UserRepository

from .services.actas import ActaRepository
from .services.activos import ActivoRepository
from .services.categorias import CategoriaRepository
from .services.clientes import ClienteRepository
from .services.contratos import ContratoRepository
from .services.contratos_proveedor import ContratoProveedorRepository
from .services.cuotas import CuotaRepository
from .services.dashboard import DashboardService
from .services.depositos import DepositoRepository
from .services.equipos import EquipoRepository
from .services.equipos_trabajo import EquipoTrabajoRepository
from .services.facturacion_config import ConfiguracionFacturacion
from .services.facturacion_externa import PuenteFacturacion
from .services.incidencias import IncidenciaRepository
from .services.informes import InformeService
from .services.ingresos import IngresoRepository
from .services.insumos import InsumoRepository
from .services.proveedores import ProveedorRepository
from .services.reemplazo import ReemplazoService
from .services.remitos_presupuestos import PresupuestoService, RemitoService
from .services.reparaciones import ReparacionRepository
from .services.reportes import ReportesService
from .services.sectores import SectorRepository
from .services.servicios_repo_catalogo import ServicioCatalogoRepository
from .services.tecnicos import TecnicoRepository
from .services.visitas import VisitaService


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


def get_servicio_repository(request: Request) -> ServicioCatalogoRepository:
    """El catálogo de servicios, que desde la revisión `0031` es **el del
    motor** y no una tabla propia.

    🔑 **La anotación decía `ServicioRepository` y estaba mintiendo.** Desde la
    fase 2, `main.py` inyecta acá un `ServicioCatalogoRepository`; como los dos
    exponen el mismo contrato de 8 métodos, nada se rompía y nadie lo notaba. Una
    anotación que nombra la clase equivocada es peor que ninguna: el que la lee
    se va a buscar el comportamiento al archivo que no corre.
    """
    return request.app.state.servicios


def get_reparacion_repository(request: Request) -> ReparacionRepository:
    return request.app.state.reparaciones


def get_insumo_repository(request: Request) -> InsumoRepository:
    return request.app.state.insumos


def get_contrato_proveedor_repository(request: Request) -> ContratoProveedorRepository:
    return request.app.state.contratos_proveedor


def get_ingreso_repository(request: Request) -> IngresoRepository:
    return request.app.state.ingresos


def get_equipo_trabajo_repository(request: Request) -> EquipoTrabajoRepository:
    return request.app.state.equipos_trabajo


def get_activo_repository(request: Request) -> ActivoRepository:
    return request.app.state.activos


def get_contrato_repository(request: Request) -> ContratoRepository:
    return request.app.state.contratos


def get_cuota_repository(request: Request) -> CuotaRepository:
    return request.app.state.cuotas


def get_acta_repository(request: Request) -> ActaRepository:
    return request.app.state.actas


def get_visita_service(request: Request) -> VisitaService:
    return request.app.state.visitas


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
