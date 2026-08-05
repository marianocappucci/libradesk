"""LibraDesk app factory: motor propio (clientes/equipos/incidencias/
tecnicos/sectores/dashboard) + `libraauth` para sesion/usuarios +
`libracore` para remitos/presupuestos y sus PDF. Mismo patron que
`gestiolibra/app/main.py`."""
from fastapi import Depends, FastAPI

import os

from libraauth.auditoria import (
    AuditoriaBase, AuditoriaRepository, agregar_middleware_de_usuario, build_logs_router,
    configurar_auditoria,
)
from libraauth.auth_events import AuthEventRepository
from libraauth.models import Base as AuthBase
from libraauth.password_reset import PasswordResetService
from libraauth.repository import UserRepository
from libraauth.session_auth import build_smtp_settings_router
from libraauth.smtp_settings import SmtpSettingsRepository, resolver_smtp_config

from . import database, schema
from .auth import build_session_auth, require_admin, require_admin_o_servicio, require_staff
from .database import configure, get_engine, get_session_factory
from .modules_gate import require_module
from .routers import auth as auth_router
from .routers import (
    activos, agenda, categorias, clientes, config_empresa, contratos, dashboard,
    depositos, equipos, equipos_trabajo, health, incidencias, informes, ingresos,
    presupuestos, proveedores, remitos, reparaciones, reportes, sectores,
    tecnicos, users,
)
from .auditoria import AUDITABLES
from .services.activos import ActivoRepository
from .services.categorias import CategoriaRepository
from .services.clientes import ClienteRepository
from .services.contratos import ContratoRepository
from .services.dashboard import DashboardService
from .services.depositos import DepositoRepository
from .services.equipos import EquipoRepository
from .services.equipos_trabajo import EquipoTrabajoRepository
from .services.incidencias import IncidenciaRepository
from .services.informes import InformeService
from .services.modules import ModuleRepository
from .services.proveedores import ProveedorRepository
from .services.reemplazo import ReemplazoService
from .services.ingresos import IngresoRepository
from .services.reparaciones import ReparacionRepository
from .services import remitos_presupuestos as rp_service
from .services.reportes import ReportesService
from .services.sectores import SectorRepository
from .services.tecnicos import TecnicoRepository
from .services.users import ensure_default_admin


def create_app(database_url: str, data_dir: str) -> FastAPI:
    configure(database_url)
    engine = get_engine()
    # Tres esquemas contra el mismo engine, en este orden y por este motivo.
    #
    # 1. El dominio propio, por Alembic (`migrations/`). Reemplaza al par
    #    `create_all()` + `app/migrations.py` que habia hasta el 2026-08-03:
    #    `create_all()` no altera tablas existentes, asi que todo cambio de
    #    schema que no fuera una columna nullable no tenia camino a produccion.
    #    Una base anterior a Alembic se adopta sola en el primer arranque; ver
    #    app/schema.py.
    schema.ensure_schema(engine)
    # 2. `libraauth` (tabla `usuarios`) sigue con `create_all()`: su schema lo
    #    versiona el motor, no este producto.
    AuthBase.metadata.create_all(engine)

    # 3. `libracore.db` en sqlite3 crudo, para reusar el dominio de remitos/
    #    presupuestos tal cual. Va ultimo a proposito — `remitos`/`presupuestos`
    #    declaran una FK a `usuarios`, que crea `libraauth` en el paso 2.
    rp_service.configure(database_url, data_dir)
    rp_service.ensure_schema()

    sessions = get_session_factory()
    user_repository = UserRepository(sessions)
    ensure_default_admin(user_repository)
    module_repository = ModuleRepository(sessions)
    module_repository.ensure_seeded()

    # Log de actividad (libraauth v0.9.0): cuelga del `flush` de SQLAlchemy, así
    # que se engancha al session_factory y no a la app — cualquier escritura del
    # producto pasa por acá, incluidas las que todavía no existen. Lo único que
    # queda en el producto es la lista blanca, en `app/auditoria.py`.
    #
    # `create_all` acá es para una base nueva: en las que ya existen la tabla la
    # creó la revisión `0010`, de cuando este código vivía en el producto.
    AuditoriaBase.metadata.create_all(engine)
    configurar_auditoria(sessions, AUDITABLES)

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
    app.state.depositos = DepositoRepository(sessions)
    app.state.incidencias = IncidenciaRepository(sessions)
    app.state.reemplazos = ReemplazoService(sessions)
    app.state.tecnicos = TecnicoRepository(sessions)
    app.state.sectores = SectorRepository(sessions)
    app.state.categorias = CategoriaRepository(sessions)
    app.state.proveedores = ProveedorRepository(sessions)
    app.state.reparaciones = ReparacionRepository(sessions)
    app.state.ingresos = IngresoRepository(sessions)
    app.state.equipos_trabajo = EquipoTrabajoRepository(sessions)
    app.state.activos = ActivoRepository(sessions)
    app.state.contratos = ContratoRepository(sessions)
    app.state.dashboard = DashboardService(sessions)
    app.state.reportes = ReportesService(sessions)
    app.state.informes = InformeService(sessions)
    app.state.remitos = rp_service.RemitoService()
    app.state.presupuestos = rp_service.PresupuestoService()
    app.state.modules = module_repository
    app.state.auditoria = AuditoriaRepository(sessions)
    # Log de accesos (libraauth v0.8.0). Es opt-in por ausencia en el motor:
    # setearlo acá es lo único que hace falta para que login, logout e intentos
    # fallidos queden registrados.
    app.state.auth_events = AuthEventRepository(sessions)
    app.state.data_dir = data_dir

    # Sella el usuario de la cookie para que la auditoría sepa quién escribió,
    # tres capas más abajo. Lo pone el motor (libraauth v0.9.0).
    agregar_middleware_de_usuario(app)

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
    # Depositos: parte del core por el mismo motivo que sectores y categorias —
    # es donde esta un equipo cuando no esta instalado, y el parque es core. No
    # se gatea por plan.
    app.include_router(depositos.router, dependencies=staff_or_admin)
    # Equipos de trabajo y flota: parte del core por el mismo motivo que
    # depositos y sectores — es como se organiza el trabajo, no una feature
    # de plan. No se gatea.
    app.include_router(equipos_trabajo.router, dependencies=staff_or_admin)
    # La agenda cuelga del mismo lado que los equipos: es como se organiza
    # el trabajo, no una feature de plan.
    app.include_router(agenda.router, dependencies=staff_or_admin)
    app.include_router(incidencias.router, dependencies=staff_or_admin)
    app.include_router(tecnicos.router, dependencies=staff_or_admin)
    app.include_router(sectores.router, dependencies=staff_or_admin)
    # Categorias: parte del core por el mismo motivo que sectores — clasificar
    # un ticket no es una feature de plan, es como se usa una mesa de ayuda.
    app.include_router(categorias.router, dependencies=staff_or_admin)
    # Reparaciones y sus proveedores: tampoco se gatean. Son la continuación de
    # `equipos` —el activo sale a service y vuelve—, y el parque es core. Si
    # alguna vez se decide venderlo como tier, agregar el módulo a `plans.py`
    # es una línea; ponerlo ahí ahora sería inventar una decisión comercial que
    # nadie tomó.
    app.include_router(proveedores.router, dependencies=staff_or_admin)
    app.include_router(reparaciones.router, dependencies=staff_or_admin)
    # Los ingresos a reparacion cuelgan del mismo lado que reparaciones:
    # es el mostrador operando, no una feature de plan.
    app.include_router(ingresos.router, dependencies=staff_or_admin)

    # Lo que sí depende del plan (ver `plans.py`). Las instancias que ya
    # existen no se enteran: sin plan asignado, `ModuleRepository` deja todo
    # habilitado.
    app.include_router(
        dashboard.router, dependencies=staff_or_admin + [Depends(require_module("dashboard"))]
    )
    app.include_router(
        reportes.router, dependencies=staff_or_admin + [Depends(require_module("reportes"))]
    )
    # El informe para el cliente cuelga del MISMO modulo que los reportes
    # internos, aunque sea un router aparte. Reusar el modulo existente en vez
    # de inventar uno nuevo evita tomar una decision comercial que nadie tomo:
    # si "reportes" separa a Basico de Estandar, poder emitirle un informe al
    # cliente cae del mismo lado de esa linea.
    app.include_router(
        informes.router, dependencies=staff_or_admin + [Depends(require_module("reportes"))]
    )
    # Alquiler y cesión de equipos. SÍ se gatea, a diferencia de reparaciones:
    # es funcionalidad comercial —contratos, precios, y en la fase 2 las cuotas—
    # y no la continuación del parque. Un LibraDesk sin alquileres sigue siendo
    # LibraDesk. Los dos routers cuelgan del MISMO módulo: un activo sin
    # contratos no tiene para qué existir, así que separarlos ofrecería un
    # inventario de stock a quien no puede entregarlo.
    app.include_router(
        activos.router, dependencies=staff_or_admin + [Depends(require_module("alquileres"))]
    )
    app.include_router(
        contratos.router, dependencies=staff_or_admin + [Depends(require_module("alquileres"))]
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

    # Logs: admin y nada más. Es la pantalla que dice quién borró qué y desde
    # qué IP entró cada uno; el staff no tiene por qué ver la actividad de sus
    # compañeros. No lleva `staff_or_admin` a propósito — sería un permiso más
    # ancho, no más angosto.
    #
    # El router lo arma el motor (libraauth v0.10.0) pero **el gate lo pone el
    # producto**: el vocabulario de roles es de acá, no del paquete.
    app.include_router(
        build_logs_router(AUDITABLES, prefix="/api/logs"),
        dependencies=[Depends(require_admin)],
    )

    return app
