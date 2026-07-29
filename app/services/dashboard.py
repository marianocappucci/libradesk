"""Resumen agregado para el Dashboard — lectura pura sobre las tablas
existentes, sin tabla propia. Mismo criterio que
`gestiolibra/app/services/dashboard.py`."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from .clientes import Cliente
from .equipos import Equipo
from .incidencias import Incidencia


class DashboardService:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def summary(self, date_from: str | None = None, date_to: str | None = None) -> dict:
        with self.session_factory() as session:
            incidencias_por_estado = dict(
                session.execute(
                    select(Incidencia.estado, func.count()).group_by(Incidencia.estado)
                ).all()
            )
            incidencias_por_prioridad_abiertas = dict(
                session.execute(
                    select(Incidencia.prioridad, func.count())
                    .where(Incidencia.estado.in_(("abierto", "en_progreso")))
                    .group_by(Incidencia.prioridad)
                ).all()
            )
            total_clientes_activos = session.execute(
                select(func.count()).select_from(Cliente).where(Cliente.activo.is_(True))
            ).scalar_one()
            total_equipos = session.execute(
                select(func.count()).select_from(Equipo)
            ).scalar_one()
            horas_totales = session.execute(
                select(func.coalesce(func.sum(Incidencia.horas_invertidas), 0))
            ).scalar_one()

            stmt = select(Incidencia)
            if date_from:
                stmt = stmt.where(Incidencia.fecha_creacion >= datetime.fromisoformat(date_from))
            if date_to:
                stmt = stmt.where(Incidencia.fecha_creacion <= datetime.fromisoformat(date_to))
            incidencias_en_rango = len(session.execute(stmt).scalars().all())

            return {
                "incidencias_por_estado": incidencias_por_estado,
                "incidencias_por_prioridad_abiertas": incidencias_por_prioridad_abiertas,
                "incidencias_en_rango": incidencias_en_rango,
                "total_clientes_activos": total_clientes_activos,
                "total_equipos": total_equipos,
                "horas_totales_invertidas": float(horas_totales),
            }
