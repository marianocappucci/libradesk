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
    global _engine, _session_factory
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    # `pool_pre_ping` evita entregar una conexión PostgreSQL que el sidecar
    # cerró durante un restart. En SQLite no cambia la semántica y mantiene
    # el mismo camino de configuración durante la transición.
    _engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    _session_factory = sessionmaker(bind=_engine)


def get_engine():
    return _engine


def get_session_factory() -> sessionmaker:
    return _session_factory
