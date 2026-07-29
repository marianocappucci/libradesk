"""Sectores/areas de un cliente (ej. "Administracion", "Ventas"), usados
para clasificar incidencias por sector de origen. FK a `clientes`, un
sector pertenece a un solo cliente (nombre unico por cliente)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base


class Sector(Base):
    __tablename__ = "sectores"
    __table_args__ = (UniqueConstraint("cliente_id", "nombre"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _to_dict(s: Sector) -> dict:
    return {"id": s.id, "cliente_id": s.cliente_id, "nombre": s.nombre}


class SectorRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def create(self, cliente_id: int, nombre: str) -> dict:
        with self.session_factory() as session:
            s = Sector(cliente_id=cliente_id, nombre=nombre.strip())
            session.add(s)
            session.commit()
            session.refresh(s)
            return _to_dict(s)

    def list(self, cliente_id: int | None = None) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(Sector).order_by(Sector.nombre)
            if cliente_id is not None:
                stmt = stmt.where(Sector.cliente_id == cliente_id)
            return [_to_dict(s) for s in session.execute(stmt).scalars()]

    def get(self, sector_id: int) -> dict | None:
        with self.session_factory() as session:
            s = session.get(Sector, sector_id)
            return _to_dict(s) if s else None

    def update(self, sector_id: int, nombre: str) -> dict:
        with self.session_factory() as session:
            s = session.get(Sector, sector_id)
            if s is None:
                raise KeyError(sector_id)
            s.nombre = nombre.strip()
            session.commit()
            session.refresh(s)
            return _to_dict(s)

    def delete(self, sector_id: int) -> None:
        with self.session_factory() as session:
            s = session.get(Sector, sector_id)
            if s is None:
                raise KeyError(sector_id)
            session.delete(s)
            session.commit()
