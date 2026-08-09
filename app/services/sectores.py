"""Sectores/areas de un cliente (ej. "Administracion", "Ventas"), usados
para clasificar incidencias por sector de origen. FK a `clientes`, un
sector pertenece a un solo cliente (nombre unico por cliente)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func, select, update
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

    def dependencias(self, sector_id: int) -> dict[str, int]:
        """Lo que impide borrar el sector. Las incidencias no entran: esas se
        desasignan (ver `delete`); un contrato, en cambio, pacto ese sector."""
        from .contratos import Contrato

        with self.session_factory() as session:
            return {
                "contratos": session.execute(
                    select(func.count()).select_from(Contrato)
                    .where(Contrato.sector_id == sector_id)
                ).scalar_one(),
            }

    def delete(self, sector_id: int) -> None:
        """Borra el sector y **desasigna** las incidencias que lo usaban.

        `incidencias.sector_id` declara `ondelete="SET NULL"`, pero ese
        ondelete no se ejecuta nunca: el engine de SQLAlchemy de LibraDesk
        no activa `PRAGMA foreign_keys` (medido sobre una conexion real, da
        0 — ver el mismo caso en `IncidenciaRepository.delete`). Sin esto,
        borrar un sector dejaba tickets apuntando a un id inexistente, y el
        reporte de Incidencias resuelve el sector por join: la fila
        aparecia sin sector y sin forma de saber por que.

        Se hace explicito aca, como en el borrado de incidencias, en vez de
        prender el pragma para todo el engine — eso es un cambio de
        comportamiento global sobre una base de produccion y merece
        decidirse aparte.

        🔴 **Y se niega si el sector esta en un contrato** (2026-08-09). Esa
        FK llego con el modulo de contratos, despues de este metodo: borrar el
        sector dejaba el contrato apuntando a un id inexistente, y el sector
        de un contrato es parte de lo pactado, no una etiqueta.
        """
        colgando = self.dependencias(sector_id)
        if any(colgando.values()):
            raise ValueError(colgando)

        with self.session_factory() as session:
            s = session.get(Sector, sector_id)
            if s is None:
                raise KeyError(sector_id)

            # Import local para no crear un ciclo: `incidencias` ya importa
            # cosas de este modulo en la direccion contraria.
            from .incidencias import Incidencia

            session.execute(
                update(Incidencia)
                .where(Incidencia.sector_id == sector_id)
                .values(sector_id=None)
            )
            session.delete(s)
            session.commit()
