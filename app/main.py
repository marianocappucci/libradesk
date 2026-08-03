"""LibraDesk app factory: motor propio (clientes/equipos/incidencias/
tecnicos/sectores/dashboard) + `libraauth` para sesion/usuarios +
`libracore` para remitos/presupuestos y sus PDF. Mismo patron que
`gestiolibra/app/main.py`."""
from fastapi import Depends, FastAPI

import os

from libraauth.models import Base as AuthBase
from libraauth.password_reset import PasswordResetService
from libraauth.repository import UserRepository
from libraauth.session_auth import build_smtp_settings_router
from libraauth.smtp_settings import SmtpSettingsRepository, resolver_smtp_config

from . import database
from .auth import build_session_auth, require_admin_o_servicio, require_staff
from .database import Base, configure, get_engine, get_session_factory
from .migrations import run_migrations
from .modules_gate import require_module
from .routers import auth as auth_router
from .routers import (
    categorias, clientes, config_empresa, dashboard, equipos, health, incidencias,
    presupuestos, remitos, reportes, sectores, tecnicos, users,
)
from .services.categorias import CategoriaRepository
from .services.clientes import ClienteRepository
from .services.dashboard import DashboardService
from .services.equipos import EquipoRepository
from .services.incidencias import IncidenciaRepository
from .services.modules import ModuleRepository
from .services.reemplazo import ReemplazoService
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
    # `create_all()` no altera tablas que ya existen: sin esto, una columna
    # nueva solo aparece en bases creadas desde cero y nunca llega a
    # produccion. Ver app/migrations.py.
    run_migrations(engine)
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
    module_repository = ModuleRepository(sessions)
    module_repository.ensure_seeded()

    app = FastAPI(title="LibraDesk")
    app.state.users = user_repository
    app.state.session_auth = build_session_auth(user_repository)
    # Recuperación de contraseña por correo (libraauth v0.5.0). Acá `sessions`
    # es el único session_factory del producto: LibraDesk tiene `usuarios` en
    # el mismo archivo que su dominio, así que la FK de la tabla de tokens
    # resuelve igual. Sin SMTP configurado la app levanta igual y el endpoint
    # devuelve 503.
    # Config SMTP editable por backoffice (libraauth v0.6.0), con la contraseña
    # cifrada en reposo. Mismo `sessions` que el resto del motor.
    app.state.smtp_settings = SmtpSettingsRepository(sessions)
    app.state.password_reset = PasswordResetService(
        sessions,
        product_name="LibraDesk",
        reset_url_base=os.environ.get(
            "LIBRADESK_RESET_URL_BASE", "https://dev.libradesk.com.ar/reset-password"
        ),
        # CALLABLE, no un valor: se resuelve en cada envío. Con un valor fijo,
        # guardar el SMTP por pantalla no tendría efecto hasta recrear el
        # contenedor. Sin nada guardado cae a las variables de entorno, así que
        # la instancia se comporta igual que antes hasta que se cargue algo.
        smtp_config=lambda: resolver_smtp_config(sessions),
    )
    app.state.clientes = ClienteRepository(sessions)
    app.state.equipos = EquipoRepository(sessions)
    app.state.incidencias = IncidenciaRepository(sessions)
    app.state.reemplazos = ReemplazoService(sessions)
    app.state.tecnicos = TecnicoRepository(sessions)
    app.state.sectores = SectorRepository(sessions)
    app.state.categorias = CategoriaRepository(sessions)
    app.state.dashboard = DashboardService(sessions)
    app.state.reportes = ReportesService(sessions)
    app.state.remitos = rp_service.RemitoService()
    app.state.presupuestos = rp_service.PresupuestoService()
    app.state.modules = module_repository
    app.state.data_dir = data_dir

    app.include_router(health.router)
    app.include_router(auth_router.router)
    # `GET`/`PUT`/`DELETE /admin/smtp`. El router exige rol admin por dentro:
    # quien pueda escribir ahí puede redirigir a dónde salen los enlaces de
    # recuperación de contraseña de todos los usuarios.
    app.include_router(build_smtp_settings_router())

    # Sin `admin_only`: el unico router admin-only de LibraDesk era el de
    # usuarios, y ahora usa `require_admin_o_servicio`. Dejar la lista sin
    # consumidores hacia fallar el lint (F841).
    staff_or_admin = [Depends(require_staff)]

    # Usuarios acepta ADEMÁS el token de servicio (libraauth v0.7.0): es lo
    # único que el backoffice de la suite necesita y que no puede salir del
    # motor, porque el router de usuarios es propio de cada producto.
    #
    # Deliberadamente sólo éste: el resto de los routers admin-only siguen
    # exigiendo sesión de un usuario del producto. El backoffice no tiene por
    # qué poder tocar el resto del dominio, y colgar la dependencia de
    # `admin_only` sería ampliar el permiso sin necesidad.
    app.include_router(users.router, dependencies=[Depends(require_admin_o_servicio)])

    # El core de tickets NO se gatea: un LibraDesk sin incidencias no es un
    # plan más barato, es otra cosa. Mismo criterio que "turnos" en Contalibra.
    app.include_router(clientes.router, dependencies=staff_or_admin)
    app.include_router(equipos.router, dependencies=staff_or_admin)
    app.include_router(incidencias.router, dependencies=staff_or_admin)
    app.include_router(tecnicos.router, dependencies=staff_or_admin)
    app.include_router(sectores.router, dependencies=staff_or_admin)
    # Categorias: parte del core por el mismo motivo que sectores — clasificar
    # un ticket no es una feature de plan, es como se usa una mesa de ayuda.
    app.include_router(categorias.router, dependencies=staff_or_admin)

    # Lo que sí depende del plan (ver `plans.py`). Las instancias que ya
    # existen no se enteran: sin plan asignado, `ModuleRepository` deja todo
    # habilitado.
    app.include_router(
        dashboard.router, dependencies=staff_or_admin + [Depends(require_module("dashboard"))]
    )
    app.include_router(
        reportes.router, dependencies=staff_or_admin + [Depends(require_module("reportes"))]
    )
    app.include_router(
        remitos.router, dependencies=staff_or_admin + [Depends(require_module("remitos"))]
    )
    app.include_router(
        presupuestos.router,
        dependencies=staff_or_admin + [Depends(require_module("presupuestos"))],
    )
    # Datos de la empresa (encabezado de los PDF): los edita solo admin,
    # el resto del staff los lee para previsualizar.
    app.include_router(config_empresa.router, dependencies=staff_or_admin)

    return app
