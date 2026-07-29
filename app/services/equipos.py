"""Equipos (inventario por cliente) + `EquipoMovimiento` (historial de
movimientos/cambios de estado — 75 filas reales migradas desde Postgres,
tabla que ni el backend Node.js viejo exponia via API, encontrada al
inspeccionar el esquema real antes de migrar)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base


class Equipo(Base):
    __tablename__ = "equipos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    modelo: Mapped[str | None] = mapped_column(String(255))
    marca: Mapped[str | None] = mapped_column(String(255))
    serial: Mapped[str | None] = mapped_column(String(255))
    ubicacion_oficina: Mapped[str | None] = mapped_column(String(255))
    sector: Mapped[str | None] = mapped_column(String(255))
    estado: Mapped[str] = mapped_column(String(50), nullable=False, default="activo")
    fecha_adicion: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    garantia_vence: Mapped[date | None] = mapped_column(Date)
    observaciones: Mapped[str | None] = mapped_column(Text)


class EquipoMovimiento(Base):
    __tablename__ = "equipos_movimientos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    equipo_id: Mapped[int] = mapped_column(ForeignKey("equipos.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    sector_origen: Mapped[str | None] = mapped_column(String(255))
    sector_destino: Mapped[str | None] = mapped_column(String(255))
    ubicacion_origen: Mapped[str | None] = mapped_column(String(255))
    ubicacion_destino: Mapped[str | None] = mapped_column(String(255))
    motivo: Mapped[str | None] = mapped_column(String(500))
    usuario: Mapped[str] = mapped_column(String(255), nullable=False, default="Sistema")
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _to_dict(e: Equipo) -> dict:
    return {
        "id": e.id,
        "cliente_id": e.cliente_id,
        "tipo": e.tipo,
        "modelo": e.modelo,
        "marca": e.marca,
        "serial": e.serial,
        "ubicacion_oficina": e.ubicacion_oficina,
        "sector": e.sector,
        "estado": e.estado,
        "fecha_adicion": e.fecha_adicion.isoformat() if e.fecha_adicion else None,
        "garantia_vence": e.garantia_vence.isoformat() if e.garantia_vence else None,
        "observaciones": e.observaciones,
    }


def _mov_to_dict(m: EquipoMovimiento) -> dict:
    return {
        "id": m.id,
        "equipo_id": m.equipo_id,
        "tipo": m.tipo,
        "descripcion": m.descripcion,
        "sector_origen": m.sector_origen,
        "sector_destino": m.sector_destino,
        "ubicacion_origen": m.ubicacion_origen,
        "ubicacion_destino": m.ubicacion_destino,
        "motivo": m.motivo,
        "usuario": m.usuario,
        "fecha": m.fecha.isoformat() if m.fecha else None,
    }


class EquipoRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def create(self, **data) -> dict:
        with self.session_factory() as session:
            e = Equipo(**data)
            session.add(e)
            session.commit()
            session.refresh(e)
            return _to_dict(e)

    def list(self, cliente_id: int | None = None) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(Equipo).order_by(Equipo.tipo)
            if cliente_id is not None:
                stmt = stmt.where(Equipo.cliente_id == cliente_id)
            return [_to_dict(e) for e in session.execute(stmt).scalars()]

    def get(self, equipo_id: int) -> dict | None:
        with self.session_factory() as session:
            e = session.get(Equipo, equipo_id)
            return _to_dict(e) if e else None

    def update(self, equipo_id: int, **data) -> dict:
        with self.session_factory() as session:
            e = session.get(Equipo, equipo_id)
            if e is None:
                raise KeyError(equipo_id)
            for key, value in data.items():
                setattr(e, key, value)
            session.commit()
            session.refresh(e)
            return _to_dict(e)

    def delete(self, equipo_id: int) -> None:
        with self.session_factory() as session:
            e = session.get(Equipo, equipo_id)
            if e is None:
                raise KeyError(equipo_id)
            session.delete(e)
            session.commit()

    def list_movimientos(self, equipo_id: int) -> list[dict]:
        with self.session_factory() as session:
            stmt = (
                select(EquipoMovimiento)
                .where(EquipoMovimiento.equipo_id == equipo_id)
                .order_by(EquipoMovimiento.fecha.desc())
            )
            return [_mov_to_dict(m) for m in session.execute(stmt).scalars()]
