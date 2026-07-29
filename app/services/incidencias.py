"""Incidencias (tickets de soporte) + `ActividadIncidencia` (log de
actividad por ticket) + `IncidenciaEstadoLog` (auditoria de cambios de
estado — 31 filas reales migradas desde Postgres). `tecnico_id`/
`sector_id` reemplazan a las columnas de texto libre `tecnico_asignado`/
`sector` que tenia la version anterior (Node.js) — la migracion de datos
(Fase 4) resuelve el texto libre contra las tablas `tecnicos`/`sectores`
donde haya coincidencia."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, func, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base

ESTADOS_VALIDOS = ("abierto", "en_progreso", "resuelta", "cerrado")
PRIORIDADES_VALIDAS = ("alta", "media", "baja")


class Incidencia(Base):
    __tablename__ = "incidencias"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True)
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id", ondelete="SET NULL"), index=True)
    tecnico_id: Mapped[int | None] = mapped_column(ForeignKey("tecnicos.id", ondelete="SET NULL"))
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectores.id", ondelete="SET NULL"))
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(50), nullable=False, default="abierto", index=True)
    prioridad: Mapped[str] = mapped_column(String(20), nullable=False, default="media")
    horas_invertidas: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    notas: Mapped[str | None] = mapped_column(Text)
    resolucion: Mapped[str | None] = mapped_column(Text)
    estado_facturacion: Mapped[str | None] = mapped_column(String(20))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime)


class ActividadIncidencia(Base):
    __tablename__ = "actividades_incidencia"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incidencia_id: Mapped[int] = mapped_column(ForeignKey("incidencias.id", ondelete="CASCADE"), nullable=False, index=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    descripcion: Mapped[str | None] = mapped_column(Text)
    usuario: Mapped[str | None] = mapped_column(String(100))


class IncidenciaEstadoLog(Base):
    __tablename__ = "incidencias_estados_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incidencia_id: Mapped[int] = mapped_column(ForeignKey("incidencias.id", ondelete="CASCADE"), nullable=False, index=True)
    estado_anterior: Mapped[str | None] = mapped_column(String(50))
    estado_nuevo: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    tecnico: Mapped[str | None] = mapped_column(String(100))


def _to_dict(i: Incidencia) -> dict:
    return {
        "id": i.id,
        "cliente_id": i.cliente_id,
        "equipo_id": i.equipo_id,
        "tecnico_id": i.tecnico_id,
        "sector_id": i.sector_id,
        "titulo": i.titulo,
        "descripcion": i.descripcion,
        "estado": i.estado,
        "prioridad": i.prioridad,
        "horas_invertidas": float(i.horas_invertidas) if i.horas_invertidas is not None else None,
        "notas": i.notas,
        "resolucion": i.resolucion,
        "estado_facturacion": i.estado_facturacion,
        "activo": i.activo,
        "fecha_creacion": i.fecha_creacion.isoformat() if i.fecha_creacion else None,
        "fecha_cierre": i.fecha_cierre.isoformat() if i.fecha_cierre else None,
    }


def _actividad_to_dict(a: ActividadIncidencia) -> dict:
    return {
        "id": a.id,
        "incidencia_id": a.incidencia_id,
        "fecha": a.fecha.isoformat() if a.fecha else None,
        "descripcion": a.descripcion,
        "usuario": a.usuario,
    }


def _estado_log_to_dict(e: IncidenciaEstadoLog) -> dict:
    return {
        "id": e.id,
        "incidencia_id": e.incidencia_id,
        "estado_anterior": e.estado_anterior,
        "estado_nuevo": e.estado_nuevo,
        "fecha": e.fecha.isoformat() if e.fecha else None,
        "tecnico": e.tecnico,
    }


class IncidenciaRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def create(self, usuario_actor: str | None = None, **data) -> dict:
        with self.session_factory() as session:
            i = Incidencia(**data)
            session.add(i)
            session.flush()
            session.add(IncidenciaEstadoLog(
                incidencia_id=i.id, estado_anterior=None, estado_nuevo=i.estado,
                tecnico=usuario_actor,
            ))
            session.commit()
            session.refresh(i)
            return _to_dict(i)

    def list(self, cliente_id: int | None = None, estado: str | None = None) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(Incidencia).order_by(Incidencia.fecha_creacion.desc())
            if cliente_id is not None:
                stmt = stmt.where(Incidencia.cliente_id == cliente_id)
            if estado is not None:
                stmt = stmt.where(Incidencia.estado == estado)
            return [_to_dict(i) for i in session.execute(stmt).scalars()]

    def get(self, incidencia_id: int) -> dict | None:
        with self.session_factory() as session:
            i = session.get(Incidencia, incidencia_id)
            return _to_dict(i) if i else None

    def update(self, incidencia_id: int, usuario_actor: str | None = None, **data) -> dict:
        """Si `data` incluye un `estado` distinto al actual, registra el
        cambio en `IncidenciaEstadoLog` y setea `fecha_cierre` al pasar a
        `cerrado`/`resuelta` (limpia `fecha_cierre` si vuelve a abrirse)."""
        with self.session_factory() as session:
            i = session.get(Incidencia, incidencia_id)
            if i is None:
                raise KeyError(incidencia_id)
            estado_anterior = i.estado
            for key, value in data.items():
                setattr(i, key, value)
            if "estado" in data and data["estado"] != estado_anterior:
                session.add(IncidenciaEstadoLog(
                    incidencia_id=i.id, estado_anterior=estado_anterior,
                    estado_nuevo=i.estado, tecnico=usuario_actor,
                ))
                if i.estado in ("resuelta", "cerrado"):
                    i.fecha_cierre = datetime.utcnow()
                else:
                    i.fecha_cierre = None
            session.commit()
            session.refresh(i)
            return _to_dict(i)

    def delete(self, incidencia_id: int) -> None:
        with self.session_factory() as session:
            i = session.get(Incidencia, incidencia_id)
            if i is None:
                raise KeyError(incidencia_id)
            session.delete(i)
            session.commit()

    def list_actividades(self, incidencia_id: int) -> list[dict]:
        with self.session_factory() as session:
            stmt = (
                select(ActividadIncidencia)
                .where(ActividadIncidencia.incidencia_id == incidencia_id)
                .order_by(ActividadIncidencia.fecha.desc())
            )
            return [_actividad_to_dict(a) for a in session.execute(stmt).scalars()]

    def add_actividad(self, incidencia_id: int, descripcion: str, usuario: str | None) -> dict:
        with self.session_factory() as session:
            a = ActividadIncidencia(incidencia_id=incidencia_id, descripcion=descripcion, usuario=usuario)
            session.add(a)
            session.commit()
            session.refresh(a)
            return _actividad_to_dict(a)

    def list_estado_log(self, incidencia_id: int) -> list[dict]:
        with self.session_factory() as session:
            stmt = (
                select(IncidenciaEstadoLog)
                .where(IncidenciaEstadoLog.incidencia_id == incidencia_id)
                .order_by(IncidenciaEstadoLog.fecha.desc())
            )
            return [_estado_log_to_dict(e) for e in session.execute(stmt).scalars()]
