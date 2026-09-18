"""Engine/session factory propios de LibraDesk (no existia en Gestiolibra
por depender de libragenda) — un solo engine compartido por el
dominio propio (clientes/equipos/incidencias/tecnicos/sectores) y por
`libraauth` (tabla `usuarios`), ver `create_app()` en `main.py`."""
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: sessionmaker | None = None
#: El almacen cifrado de secretos de terceros (`mp_access_token`,
#: `mp_webhook_secret`, `email_smtp_password`), una vez enganchado por
#: `enganchar_secretos()`. `None` hasta que `create_app()` corre.
_secretos = None


def configure(database_url: str) -> None:
    """Configura el engine. **LibraDesk corre sobre PostgreSQL y nada más**
    (decidido el 2026-08-12; las tres instancias ya lo hacían desde el
    2026-08-11).

    Se rechaza cualquier otro destino en vez de aceptarlo callado: una URL
    `sqlite://` acá levantaba la app con un motor donde las FK no se chequean
    y los tipos son dinámicos, o sea que los defectos que PostgreSQL rechaza
    de entrada pasaban desapercibidos hasta producción.
    """
    global _engine, _session_factory
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ValueError(
            f"LibraDesk requiere PostgreSQL y recibió: {database_url.split('://')[0]}://…"
        )
    # 🔴 `postgresql://` a secas HAY QUE NORMALIZARLO ANTES DE `create_engine`.
    #
    # SQLAlchemy resuelve el esquema pelado al dialecto **psycopg2**, que este
    # producto no instala: la dependencia es `psycopg[binary]` (psycopg 3). Y no
    # falla al conectarse sino al IMPORTARSE, con `ModuleNotFoundError: No
    # module named 'psycopg2'`, así que el contenedor ni siquiera llega a
    # levantar — crash loop y healthcheck que nunca pasa.
    #
    # Las dos formas entran a la guarda de arriba porque las dos existen en el
    # parque: LibraCore conecta con `psycopg.connect()`, que acepta la forma
    # libpq, así que sus composes la escriben pelada y para él está bien. El que
    # necesita el sufijo es SQLAlchemy. Normalizar acá —en vez de exigir que el
    # compose venga perfecto— es lo que hace que este producto arranque
    # cualquiera sea la forma en que se lo escribieron.
    #
    # Encontrado el 2026-08-13 en `libradesk-lagrace`, la primera instancia
    # creada por el alta del backoffice: 28 reinicios. Las anteriores tenían el
    # sufijo puesto A MANO, que es por qué nadie lo había visto.
    url_sqlalchemy = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    # `pool_pre_ping` evita entregar una conexión que el sidecar cerró durante
    # un restart.
    _engine = create_engine(url_sqlalchemy, pool_pre_ping=True)
    _session_factory = sessionmaker(bind=_engine)


def get_engine():
    return _engine


def get_session_factory() -> sessionmaker:
    return _session_factory


# 🔴 Los secretos de terceros de `config.json` —el access token y la firma de
# webhook de MercadoPago (LibraDesk no monta `mp_config_router`, pero
# `config_manager` sí guarda esas claves por consistencia con el resto de la
# familia) y la contraseña SMTP de presupuestos, resuelta por
# `libracore.facturas_router.smtp_efectivo()`— dejan de vivir en texto plano
# (libracore v1.108.0 + libraauth v0.46.0, 2026-09-17). Se enganchan ACA, justo
# después de `_session_factory`, porque es el mismo session factory que recibe
# `UserRepository` en `create_app()` — la base donde viven las tablas de
# libraauth (tabla `usuarios`). La tabla `secretos_instancia` la crea la
# revisión `0002` de la cadena de libraauth, no un `create_all`; por eso
# `enganchar_secretos()`/`migrar_secretos()` se llaman en `create_app()`
# DESPUÉS de `exigir_schema_al_dia(...)` (ver `main.py`), nunca antes.
#
# LibraCore no importa libraauth: recibe el almacén. Por eso el enganche es
# del producto, que es el único que tiene los dos paquetes.
def enganchar_secretos() -> None:
    """Conecta `config_manager` al almacén cifrado. Idempotente: llamarla de
    nuevo (cada `create_app()`, ej. en tests) sólo reemplaza el almacén por
    uno que apunta al mismo session factory."""
    global _secretos
    from libraauth.secretos import SecretosRepository
    from libracore import config_manager as _lc_config_manager

    _secretos = SecretosRepository(_session_factory)
    _lc_config_manager.usar_almacen_de_secretos(_secretos)


def migrar_secretos() -> dict:
    """Saca de `config.json` los secretos que quedaron en claro. Idempotente.

    Corre en cada arranque (dentro de `create_app()`, después de
    `enganchar_secretos()`), así que la migración de una instancia viva **es
    su deploy**. Loguea NOMBRES de claves, nunca valores: un log con el
    secreto lo muda del archivo a una superficie peor, porque los logs se
    copian y se mandan.

    Si cifrar falla, el `config.json` **no se toca** —la instancia sigue
    mandando el mail con la credencial que tiene— y se loguea como error, que
    es lo que después ve la sonda `auditar_secretos.py`.
    """
    from libracore import config_manager as _lc_config_manager

    informe = _lc_config_manager.migrar_secretos_al_almacen()
    if informe["migradas"]:
        _log.warning(
            "secretos movidos de config.json al almacen cifrado: %s",
            ", ".join(informe["migradas"]),
        )
    if informe["ya_estaban"]:
        _log.warning(
            "config.json tenia una copia vieja de %s; se vacio (el almacen manda)",
            ", ".join(informe["ya_estaban"]),
        )
    if informe["fallaron"]:
        _log.error(
            "no se pudieron cifrar y QUEDAN EN CLARO en config.json: %s",
            ", ".join(f"{k} ({v})" for k, v in informe["fallaron"].items()),
        )
    return informe


# ── módulos y add-ons: el contrato que espera el backoffice ─────────────────────
#
# 🔴 El backoffice prende/apaga add-ons y lee su estado corriendo un snippet
# DENTRO de este contenedor (`libracore.admin.services`), y ese snippet importa
# `app.database.get_modulos` / `app.database.set_addon`. Es el contrato que
# LibraDesk tiene que cumplir desde que declaró `ADDONS = {"modo_simple"}` en
# `plans.py` (2026-09-09, para Lagrace).
#
# No estaba cumplido: este módulo es la *engine factory* de SQLAlchemy y nunca
# exportó nada de módulos. El `docker exec` moría con `ImportError: cannot
# import name 'get_modulos' from 'app.database'`, y como la lectura del
# backoffice traducía cualquier error a `False`, la pantalla mostró
# `modo_simple` **destildado en una instancia que lo tenía prendido**. El
# `ImportError` no lo veía nadie: se lo comía el fallback.
#
# Delegan en `libracore.db.modulos`, que es donde vive la implementación única
# de la familia. Acá no se copia lógica: se cumple el contrato.
def _asegurar_core_configurado() -> None:
    """Apunta `libracore.db.core` a la base de ESTA instancia si nadie lo hizo.

    Estas dos funciones tienen dos vidas muy distintas:

    - Dentro de la app, `create_app()` ya configuró el core (vía
      `services.remitos_presupuestos.configure`) y acá no hay nada que hacer.
    - Bajo `docker exec python3 -c "from app.database import get_modulos"` no
      corrió ningún arranque, así que el core está sin configurar y
      `get_connection()` levanta `RuntimeError`. Ese es el caso que necesita
      resolverse solo, sin pedirle al backoffice que bootee la app entera.

    Se pregunta antes de configurar (`esta_configurado()`) para no pisarle la
    configuración a una app viva.
    """
    from libracore.db import core as libracore_core
    from libracore.db.url_de_instancia import url_de_instancia

    if not libracore_core.esta_configurado():
        libracore_core.configure(url_de_instancia("libradesk", requerida=True))


def get_modulos() -> dict[str, bool]:
    """`{modulo: habilitado}` de esta instancia. Ver `_asegurar_core_configurado`."""
    _asegurar_core_configurado()
    from libracore.db.modulos import get_modulos as _get_modulos

    return _get_modulos()


def set_addon(nombre: str, habilitado: bool) -> None:
    """Prende/apaga un add-on suelto en esta instancia. Efecto inmediato:
    `require_module` relee `get_modulos()` en cada request."""
    _asegurar_core_configurado()
    from libracore.db.modulos import set_addon as _set_addon

    _set_addon(nombre, habilitado)
