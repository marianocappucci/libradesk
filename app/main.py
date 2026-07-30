"""LibraDesk app factory: motor propio (clientes/equipos/incidencias/
tecnicos/sectores/dashboard) + `libraauth` para sesion/usuarios +
`libracore` para remitos/presupuestos y sus PDF. Mismo patron que
`gestiolibra/app/main.py`."""
from fastapi import Depends, FastAPI

from libraauth.models import Base as AuthBase
from libraauth.repository import UserRepository

from . import database
from .auth import build_session_auth, require_admin, require_staff
from .database import Base, configure, get_engine, get_session_factory
from .routers import auth as auth_router
from .routers import (
    clientes, config_empresa, dashboard, equipos, health, incidencias,
    presupuestos, remitos, reportes, sectores, tecnicos, users,
)
from .services.clientes import ClienteRepository
from .services.dashboard import DashboardService
from .services.equipos import EquipoRepository
from .services.incidencias import IncidenciaRepository
from .services import remitos_presupuestos as rp_service
from .services.reportes import ReportesService
from .services.sectores import SectorRepository
from .services.tecnicos import TecnicoRepository
from .services.users import ensure_default_admin


def create_app(database_url: str, data_dir: str) -> FastAPI:
    configure(database_url)
    engine = get_engine()
    # Dos metadatas contra el mismo engine: el dominio propio de LibraDesk
    # y el de libraauth (tabla `usuarios`) — conviven en el mismo archivo
    # SQLite, sin una segunda base de datos separada.
    Base.metadata.create_all(engine)
    AuthBase.metadata.create_all(engine)

    # Tercera capa sobre el MISMO archivo SQLite: `libracore.db` en sqlite3
    # crudo, para reusar el dominio de remitos/presupuestos tal cual. Va
    # despues de los `create_all()` a proposito — `remitos`/`presupuestos`
    # declaran una FK a `usuarios`, que crea `libraauth`.
    rp_service.configure(database_url, data_dir)
    rp_service.ensure_schema()

    sessions = get_session_factory()
    user_repository = UserRepository(sessions)
    ensure_default_admin(user_repository)

    app = FastAPI(title="LibraDesk")
    app.state.users = user_repository
    app.state.session_auth = build_session_auth(user_repository)
    app.state.clientes = ClienteRepository(sessions)
    app.state.equipos = EquipoRepository(sessions)
    app.state.incidencias = IncidenciaRepository(sessions)
    app.state.tecnicos = TecnicoRepository(sessions)
    app.state.sectores = SectorRepository(sessions)
    app.state.dashboard = DashboardService(sessions)
    app.state.reportes = ReportesService(sessions)
    app.state.remitos = rp_service.RemitoService()
    app.state.presupuestos = rp_service.PresupuestoService()
    app.state.data_dir = data_dir

    app.include_router(health.router)
    app.include_router(auth_router.router)

    admin_only = [Depends(require_admin)]
    # Sin planes/gating (instancia unica): cualquier usuario logueado
    # (admin o staff) lee y opera el dominio; solo el ABM de usuarios es
    # admin-only.
    staff_or_admin = [Depends(require_staff)]
    app.include_router(users.router, dependencies=admin_only)
    app.include_router(clientes.router, dependencies=staff_or_admin)
    app.include_router(equipos.router, dependencies=staff_or_admin)
    app.include_router(incidencias.router, dependencies=staff_or_admin)
    app.include_router(tecnicos.router, dependencies=staff_or_admin)
    app.include_router(sectores.router, dependencies=staff_or_admin)
    app.include_router(dashboard.router, dependencies=staff_or_admin)
    app.include_router(reportes.router, dependencies=staff_or_admin)
    app.include_router(remitos.router, dependencies=staff_or_admin)
    app.include_router(presupuestos.router, dependencies=staff_or_admin)
    # Datos de la empresa (encabezado de los PDF): los edita solo admin,
    # el resto del staff los lee para previsualizar.
    app.include_router(config_empresa.router, dependencies=staff_or_admin)

    return app
