"""Clientes: modelo SQLAlchemy + `ClienteRepository(session_factory)`, mismo
patron que `service_prices.py` de Gestiolibra. Mismas columnas que la
tabla real de la Postgres que reemplaza (`clientes`), sin
`google_contact_id` (integracion eliminada en el rebrand a LibraDesk)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    empresa: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    telefono: Mapped[str | None] = mapped_column(String(20))
    ciudad: Mapped[str | None] = mapped_column(String(100))
    observaciones: Mapped[str | None] = mapped_column(Text)
    tipo_facturacion: Mapped[str] = mapped_column(String(20), nullable=False, default="por_servicio")
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _to_dict(c: Cliente) -> dict:
    return {
        "id": c.id,
        "nombre": c.nombre,
        "empresa": c.empresa,
        "email": c.email,
        "telefono": c.telefono,
        "ciudad": c.ciudad,
        "observaciones": c.observaciones,
        "tipo_facturacion": c.tipo_facturacion,
        "activo": c.activo,
        "fecha_creacion": c.fecha_creacion.isoformat() if c.fecha_creacion else None,
    }


class ClienteRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def create(self, **data) -> dict:
        with self.session_factory() as session:
            c = Cliente(**data)
            session.add(c)
            session.commit()
            session.refresh(c)
            return _to_dict(c)

    def list(self, solo_activos: bool = False) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(Cliente).order_by(Cliente.nombre)
            if solo_activos:
                stmt = stmt.where(Cliente.activo.is_(True))
            return [_to_dict(c) for c in session.execute(stmt).scalars()]

    def get(self, cliente_id: int) -> dict | None:
        with self.session_factory() as session:
            c = session.get(Cliente, cliente_id)
            return _to_dict(c) if c else None

    def update(self, cliente_id: int, **data) -> dict:
        with self.session_factory() as session:
            c = session.get(Cliente, cliente_id)
            if c is None:
                raise KeyError(cliente_id)
            for key, value in data.items():
                setattr(c, key, value)
            session.commit()
            session.refresh(c)
            return _to_dict(c)

    def delete(self, cliente_id: int) -> None:
        with self.session_factory() as session:
            c = session.get(Cliente, cliente_id)
            if c is None:
                raise KeyError(cliente_id)
            session.delete(c)
            session.commit()
