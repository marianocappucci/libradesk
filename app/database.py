"""Engine/session factory propios de LibraDesk (no existia en Gestiolibra
por depender de libragenda) — un solo engine compartido por el
dominio propio (clientes/equipos/incidencias/tecnicos/sectores) y por
`libraauth` (tabla `usuarios`), ver `create_app()` en `main.py`."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: sessionmaker | None = None


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
