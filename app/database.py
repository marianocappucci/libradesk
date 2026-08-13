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
