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
    # `pool_pre_ping` evita entregar una conexión que el sidecar cerró durante
    # un restart.
    _engine = create_engine(database_url, pool_pre_ping=True)
    _session_factory = sessionmaker(bind=_engine)


def get_engine():
    return _engine


def get_session_factory() -> sessionmaker:
    return _session_factory
