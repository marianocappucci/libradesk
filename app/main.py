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
from libraauth.demo_codigos import DemoCodigoRepository
from libraauth.session_auth import (
    build_demo_codigos_router, build_smtp_settings_router, demo_username,
)
from libraauth.smtp_settings import SmtpSettingsRepository, resolver_smtp_config
from libraauth.terminos import TerminosRepository, build_terminos_router
from libracore.config_router import (
    build_backup_router, build_empresa_admin_router, build_empresa_router,
)
from libracore.respaldo import Instancia
from sqlalchemy.engine import make_url

from . import database, schema
from .auth import build_session_auth, require_admin, require_admin_o_servicio, require_staff
from .database import configure, get_engine, get_session_factory
from .modules_gate import require_module
from .routers import auth as auth_router
from .routers import (
    activos, agenda, categorias, clientes, comercial, compras, contratos,
    cuotas, dashboard, depositos, equipos, equipos_trabajo, facturacion,
    facturacion_config, health, incidencias,
    informes, ingresos, insumos, presupuestos, proveedores, remitos,
    reparaciones,
    reportes, sectores, servicios, sucursales, tecnicos, users, visitas,
)
from .routers import inventario as inventario_router
# Alias por el mismo motivo que `inventario_router`: `app.services.ventas` ya
# ocupa el nombre en este módulo.
from .routers import ventas as ventas_router
from .auditoria import AUDITABLES
from .services.actas import ActaRepository
from .services.activos import ActivoRepository
from .services.categorias import CategoriaRepository
from .services.clientes import ClienteRepository
from .services.contratos import ContratoRepository
from .services.cuotas import CuotaRepository
from .services.visitas import VisitaService
from .services.dashboard import DashboardService
from .services.depositos import DepositoRepository
from .services.equipos import EquipoRepository
from .services.equipos_trabajo import EquipoTrabajoRepository
from .services.facturacion_config import ConfiguracionFacturacion, configurar_lectura
from .services.facturacion_externa import PuenteFacturacion
from .services.incidencias import IncidenciaRepository
from .services.informes import InformeService
from .services.modules import ModuleRepository
from .services.proveedores import ProveedorRepository
from .services.servicios_repo_catalogo import ServicioCatalogoRepository
from .services.reemplazo import ReemplazoService
from .services.ingresos import IngresoRepository
# La clase, no el módulo: `insumos` ya nombra al router en este archivo.
from .services.insumos import InsumoRepository
from .services.reparaciones import ReparacionRepository
from .services import comercial as comercial_service
from .services import inventario, materiales
from .services import remitos_presupuestos as rp_service
from .services.reportes import ReportesService
from .services.sectores import SectorRepository
from .services.tecnicos import TecnicoRepository
from libraauth.bootstrap import ensure_demo_user
from .services.users import ensure_default_admin


def _es_postgres(database_url: str) -> bool:
    """Si esta instancia corre sobre PostgreSQL en vez de SQLite.

    Mismo criterio que usa `libracore.db.core.configure()` para elegir backend,
    a proposito: si los dos no coinciden, la app y su backup mirarian a bases
    distintas.
    """
    return database_url.startswith(("postgresql://", "postgresql+psycopg://"))


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

    # 4. `libracommerce`, el stock de consumibles (2026-08-12). Reusa la
    #    conexion que acaba de configurar el paso 3 — por eso va despues y no
    #    vuelve a llamar a `libracore_core.configure()`.
    #
    #    Sus tablas se crean en TODA instancia, contrate o no el modulo
    #    `stock`: el plan enciende la funcionalidad, no ramifica el schema.
    #    Ver el comentario de `_PREMIUM` en `plans.py`.
    inventario.ensure_schema()

    # 5. `incidencias_materiales`, el enganche entre el ticket y el stock. Va
    #    despues del motor porque referencia sus `catalog_items`/`locations`
    #    por id, y se escribe por ESTA conexion y no por SQLAlchemy: es lo
    #    unico que hace atomico el par "material anotado + stock descontado".
    materiales.ensure_schema()

    # 6. El schema comercial: las tablas que LibraDesk le toma prestadas a
    #    LibraCore (egresos, recibos, cuenta corriente) más `sucursales`. Va
    #    DESPUÉS del motor de comercio porque `ventas_pagos` referencia
    #    `sales`. Ver `app/services/comercial.py`.
    comercial_service.ensure_schema()

    # 7. El espejo de `parties`. Sin esto no hay ni una venta ni una recepción
    #    de compra: sus FK contra esa tabla son NOT NULL y está vacía, porque
    #    LibraDesk escribe clientes y proveedores por SQLAlchemy y el espejo de
    #    LibraCore nunca se dispara. Es idempotente y barato (dos INSERT ...
    #    SELECT con anti-join), así que corre en cada arranque y así adopta
    #    también los clientes que ya existían.
    comercial_service.sincronizar_parties()

    # 🔑 **Acá había un paso 8** —`servicios_catalogo.migrar()`, la copia de la
    #    tabla propia de servicios al catálogo del motor— y se fue con la
    #    revisión `0031`, que dropea el origen. Una copia sin origen no tiene
    #    nada que hacer, y dejarla puesta la convertiría en una consulta por
    #    arranque que siempre da cero.
    #
    #    Se deja dicho porque el paso existió por un motivo que sigue siendo
    #    cierto y que la próxima mudanza va a volver a necesitar: **no podía ser
    #    una migración de Alembic**, porque `ensure_schema()` corre en el paso 1
    #    y `catalog_items` recién existe después del paso 6. Una migración que
    #    insertara ahí andaría en toda instancia que ya tuviera el motor y
    #    fallaría en la primera nueva.

    sessions = get_session_factory()
    user_repository = UserRepository(sessions)
    ensure_default_admin(user_repository)
    # Crea al visitante de la demo, **solo si esta instancia es una demo**: se
    # guia por `DEMO_MODE` + `DEMO_USERNAME`, las mismas dos variables que
    # registran `POST /auth/demo`. En la instancia de un cliente devuelve None
    # y no toca la base.
    #
    # 🔴 Sin esta llamada la ruta existe y no tiene a quien loguear: contesta
    # `503 demo user not provisioned`. Cablear `incluir_demo=True` en el router
    # no alcanza — la ruta y la siembra las conecta el producto, cada una por
    # su lado.
    ensure_demo_user(user_repository)
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
    # Terminos y Condiciones del Servicio: la prueba de la aceptacion y lo que
    # enciende el gate. MISMA fabrica de sesiones que el SMTP y los usuarios --
    # la tabla tiene FK a `usuarios`, que no siempre vive en la base del dominio.
    #
    # 🔴 Sin esta linea el gate NO corta y la instancia no falla: se queda sin
    # gate, en silencio. Por eso cada producto tiene un test que lo prueba.
    app.state.terminos = TerminosRepository(sessions)
    # Codigos de acceso a la demo (libraauth v0.26.0). **Solo si esta
    # instancia es una demo**, guiado por las mismas dos variables que
    # siembran al visitante y registran `POST /auth/demo`: en la instancia de
    # un cliente no hay demo que abrir, y dejar el repositorio cableado ahi
    # publicaria un ABM que no significa nada.
    #
    # 🔴 Y al reves: una instancia demo que llegue hasta aca SIN el
    # repositorio deja de dejar entrar. El endpoint falla cerrado a proposito
    # — ver su docstring en el motor. Si un dia la demo devuelve
    # `503 demo access codes not configured`, lo que falta es esta linea, no
    # un codigo.
    if demo_username():
        app.state.demo_codigos = DemoCodigoRepository(sessions)
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
    # 🔑 **El catálogo de servicios se lee del CATÁLOGO DEL MOTOR** desde el
    # 2026-08-16 (segunda release del expand/contract). El contrato es idéntico
    # —los ocho métodos devuelven los mismos dicts— así que el router, la
    # pantalla de configuración y el formulario de comprobantes no se tocan.
    #
    # Es seguro porque **el comprobante nunca guardó un `servicio_id`**: el
    # catálogo sugiere y el comprobante copia texto y precio, así que los ids
    # nuevos no los referencia nada ya emitido.
    #
    # La tercera release llegó: la revisión `0031` dropeó `servicios` y con ella
    # se fue `ServicioRepository`. **Ya no hay vuelta atrás por esta línea**, y
    # es la consecuencia querida de haber partido la mudanza en tres — la red
    # existió las dos releases en que hubo algo que pudiera salir mal, y se
    # levantó recién cuando las cuatro instancias quedaron verificadas.
    app.state.servicios = ServicioCatalogoRepository(sessions)
    app.state.reparaciones = ReparacionRepository(sessions)
    app.state.insumos = InsumoRepository(sessions)
    app.state.ingresos = IngresoRepository(sessions)
    app.state.equipos_trabajo = EquipoTrabajoRepository(sessions)
    app.state.activos = ActivoRepository(sessions)
    app.state.contratos = ContratoRepository(sessions)
    app.state.cuotas = CuotaRepository(sessions)
    # Las actas cuelgan del contrato y salen por su router, con el mismo gate
    # de módulo: son el papel de la entrega, no una entidad aparte.
    app.state.actas = ActaRepository(sessions)
    app.state.visitas = VisitaService(sessions)
    app.state.dashboard = DashboardService(sessions)
    app.state.reportes = ReportesService(sessions)
    app.state.informes = InformeService(sessions)
    app.state.remitos = rp_service.RemitoService()
    app.state.presupuestos = rp_service.PresupuestoService()
    # El puente hacia la instancia de Contalibra del mismo cliente. Se
    # construye siempre: si el emparejamiento no está configurado, el servicio
    # lo dice y el router contesta 409 — no hay una app distinta según haya o
    # no puente.
    app.state.puente_facturacion = PuenteFacturacion(sessions)
    app.state.config_facturacion = ConfiguracionFacturacion(sessions)
    # 🔴 Sin esta línea la pantalla de Configuración → Facturación es
    # decorativa: guarda en `config_facturacion` y el camino de envío sigue
    # leyendo el entorno. Pasó en `lagrace` — la fila `sos` habilitada y
    # cargada, y la pantalla insistiendo con que la instancia "no está enlazada
    # con Contalibra". Ver `facturacion_config.configurar_lectura`.
    configurar_lectura(app.state.config_facturacion)
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
    # `GET /terminos`, `POST /terminos/aceptar`, `GET /terminos/historial`.
    # NO se gatea desde afuera: es el unico camino para salir del gate.
    app.include_router(build_terminos_router())
    # `GET`/`POST`/`DELETE /admin/demo-codigos`, solo en la demo. Exige rol
    # admin o token de servicio por dentro, igual que el de SMTP: es por donde
    # el backoffice emite los codigos que se le pasan a un cliente potencial.
    if demo_username():
        app.include_router(build_demo_codigos_router())

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
    # Catalogo de servicios: `staff_or_admin` y no admin-only, aunque el ABM
    # sea cosa del dueño. Quien arma un presupuesto es staff, y el catalogo
    # existe justamente para que lo use al cargarlo — cerrarlo dejaria una
    # lista cargada que nadie puede consultar, que es lo contrario del pedido.
    # El ABM se esconde de la pantalla por rol, como en depositos y categorias.
    app.include_router(servicios.router, dependencies=staff_or_admin)
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
    # El devengado (fase 2). Mismo módulo que los contratos y por el mismo
    # motivo: una cuota sin contrato no existe, así que gatearla aparte
    # ofrecería una bandeja de cobros de algo que no se puede contratar.
    app.include_router(
        cuotas.router, dependencies=staff_or_admin + [Depends(require_module("alquileres"))]
    )
    # Las visitas de mantenimiento cuelgan del mismo módulo que las cuotas, y por
    # el mismo motivo: salen de un contrato, así que gatearlas aparte ofrecería
    # programar el trabajo de algo que no se puede contratar.
    app.include_router(
        visitas.router, dependencies=staff_or_admin + [Depends(require_module("alquileres"))]
    )
    # Stock de consumibles. Un solo router para el catálogo, los depósitos, los
    # movimientos Y los materiales de una incidencia: los cuatro cuelgan del
    # mismo módulo porque sin stock no hay nada de lo cual descontar, así que
    # separar el enganche del ticket ofrecería medio circuito.
    app.include_router(
        inventario_router.router,
        dependencies=staff_or_admin + [Depends(require_module("stock"))],
    )
    # Insumos por equipo: el tóner que le entra a la fotocopiadora. Módulo
    # propio y no colgado de `stock`, aunque el insumo salga de ese catálogo:
    # lo que este circuito registra es **lo que consume el parque del cliente**,
    # que en el caso que lo motivó no sale de ningún depósito nuestro —lo pone
    # el tercero que le alquila las máquinas—. Un LibraDesk sin insumos sigue
    # siendo LibraDesk, mismo criterio que `alquileres` y que `stock`.
    #
    # ⚠️ **Necesita el catálogo, o sea que `insumos` implica `stock`**, igual
    # que `compras`: elegir qué tóner es se hace contra `/api/consumibles`, que
    # está gateado por `stock`. Lo garantiza el plan y no el código —los dos
    # están en premium—, exactamente como está escrito para las compras.
    app.include_router(
        insumos.router,
        dependencies=staff_or_admin + [Depends(require_module("insumos"))],
    )
    # Compras: órdenes, recepción de mercadería y egresos. Gate propio y no
    # colgado de `stock` a propósito: se puede llevar inventario sin registrar
    # a quién se le compró, y de hecho es como arranca la mayoría. Al revés no
    # —una recepción sin depósito no tiene dónde entrar—, así que `compras`
    # implica `stock` y eso lo garantiza el plan, no el código.
    app.include_router(
        compras.router,
        dependencies=staff_or_admin + [Depends(require_module("compras"))],
    )
    # Ventas y recibos. **Sin emisión de factura**: el comprobante fiscal lo
    # emite SOS Contador por el puente de `facturacion_externa`.
    app.include_router(
        ventas_router.router,
        dependencies=staff_or_admin + [Depends(require_module("ventas"))],
    )
    # Listas de precios y cuenta corriente.
    app.include_router(
        comercial.router,
        dependencies=staff_or_admin + [Depends(require_module("cuenta_corriente"))],
    )
    # Sucursales: SIN gate de módulo, igual que sectores y categorías. Son
    # estructura de la empresa; lo que se contrata es poder vender o comprar en
    # ellas, no que existan.
    app.include_router(sucursales.router, dependencies=staff_or_admin)
    app.include_router(
        remitos.router, dependencies=staff_or_admin + [Depends(require_module("remitos"))]
    )
    app.include_router(
        presupuestos.router,
        dependencies=staff_or_admin + [Depends(require_module("presupuestos"))],
    )
    # El puente hacia Contalibra. Módulo propio y no colgado de `remitos`
    # —ver `plans.py`—, y **admin-only**: mandar algo a facturar es una
    # decisión comercial, no parte de armar el comprobante. Quien arma un
    # remito es staff; quien decide que se le cobre al cliente, no.
    app.include_router(
        facturacion.router,
        dependencies=[
            Depends(require_admin), Depends(require_module("facturacion_externa")),
        ],
    )
    # A qué destinos manda esta instancia y con qué credenciales. Mismas dos
    # guardas que el puente, por el mismo motivo — y con más razón, porque acá
    # se cargan credenciales de otro sistema.
    app.include_router(
        facturacion_config.router,
        dependencies=[
            Depends(require_admin), Depends(require_module("facturacion_externa")),
        ],
    )
    # Datos de la empresa, logo y backup. Los tres routers salen de LibraCore
    # v1.10.0: el de empresa reemplaza a `app/routers/config_empresa.py`, que
    # hacia exactamente esto y ahora lo hacen los seis productos igual.
    #
    # La LECTURA queda con `staff_or_admin` —no admin— porque el generador de
    # PDF la usa: cerrarla romperia la previsualizacion de un remito para
    # cualquiera que no sea admin. La escritura, el logo y el backup si son
    # admin: un backup es una copia completa de los datos del cliente.
    app.include_router(build_empresa_router(), dependencies=staff_or_admin)
    app.include_router(build_empresa_admin_router(), dependencies=[Depends(require_admin)])
    app.include_router(
        build_backup_router(
            # 🔴 En PostgreSQL se pasa la URL, NO `make_url(...).database`.
            # Ahi ese campo es el NOMBRE de la base, no una ruta de archivo, y
            # `libracore.respaldo` lo trataba como ruta: no encontraba el
            # archivo, se lo saltaba por el caso "instancia recien creada" y el
            # cliente se bajaba un ZIP **con los logos y sin datos**, sin ningun
            # error. Recien se notaba al restaurar ("El backup no contiene
            # ninguna base de datos"). Lo encontro la suite corriendo contra
            # PostgreSQL el 2026-08-09.
            Instancia(
                nombre="libradesk",
                # Una sola base: a diferencia de Gestiolibra, MedLibra y
                # VentaLibra, aca `usuarios` vive en el MISMO archivo que el
                # dominio (`AuthBase.metadata.create_all(engine)`, arriba).
                bases=(
                    [] if _es_postgres(database_url)
                    else [make_url(database_url).database]
                ),
                postgres_url=database_url if _es_postgres(database_url) else None,
                # 🔴 `contratos` va aca junto con `logos`, y no es decorativo:
                # los contratos firmados escaneados son **documentos del
                # cliente que solo existen en este volumen**. Un backup que no
                # los lleve se descarga igual, pesa parecido y al restaurar
                # deja las fichas apuntando a archivos que no estan. Es el
                # mismo modo de fallar que el de la base en PostgreSQL, dos
                # comentarios mas arriba: incompleto se ve igual que completo.
                directorios=[
                    os.path.join(data_dir, "logos"),
                    os.path.join(data_dir, "contratos"),
                ],
            ),
            os.path.join(data_dir, "backups"),
            # 🔴 Sin estos dos el restore devuelve `ok` y **no tiene efecto**
            # hasta que alguien reinicie el contenedor: el pool sigue con el
            # archivo viejo abierto y la app sirve la base anterior. Lo
            # encontro `test_config_backup.py::test_crear_listar_y_restaurar`,
            # que restauraba y despues preguntaba por los clientes.
            #
            # `dispose()` sirve para los dos momentos: cierra el pool y deja
            # que se vuelva a abrir solo en la proxima conexion.
            cerrar_conexiones=engine.dispose,
            reabrir_conexiones=engine.dispose,
        ),
        dependencies=[Depends(require_admin)],
    )

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
