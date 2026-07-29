"""Tecnicos: staff asignable a incidencias. Tabla propia sin equivalente
en el schema.sql historico (se agrego despues por ALTER TABLE, sin
migracion formal) — modelada acá con las columnas reales verificadas en
la Postgres de produccion."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base


class Tecnico(Base):
    __tablename__ = "tecnicos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _to_dict(t: Tecnico) -> dict:
    return {"id": t.id, "nombre": t.nombre, "activo": t.activo}


class TecnicoRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def create(self, nombre: str, activo: bool = True) -> dict:
        with self.session_factory() as session:
            t = Tecnico(nombre=nombre.strip(), activo=activo)
            session.add(t)
            session.commit()
            session.refresh(t)
            return _to_dict(t)

    def list(self, solo_activos: bool = False) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(Tecnico).order_by(Tecnico.nombre)
            if solo_activos:
                stmt = stmt.where(Tecnico.activo.is_(True))
            return [_to_dict(t) for t in session.execute(stmt).scalars()]

    def get(self, tecnico_id: int) -> dict | None:
        with self.session_factory() as session:
            t = session.get(Tecnico, tecnico_id)
            return _to_dict(t) if t else None

    def update(self, tecnico_id: int, nombre: str, activo: bool) -> dict:
        with self.session_factory() as session:
            t = session.get(Tecnico, tecnico_id)
            if t is None:
                raise KeyError(tecnico_id)
            t.nombre = nombre.strip()
            t.activo = activo
            session.commit()
            session.refresh(t)
            return _to_dict(t)

    def delete(self, tecnico_id: int) -> None:
        with self.session_factory() as session:
            t = session.get(Tecnico, tecnico_id)
            if t is None:
                raise KeyError(tecnico_id)
            session.delete(t)
            session.commit()
