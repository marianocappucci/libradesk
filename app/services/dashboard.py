"""Resumen agregado para el Dashboard — lectura pura sobre las tablas
existentes, sin tabla propia. Mismo criterio que
`gestiolibra/app/services/dashboard.py`.

Dos vistas: `summary()` (global, la del Dashboard) y `cliente()` (la ficha
de un cliente, `/clientes/:id`)."""
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from .clientes import Cliente
from .equipos import Equipo, descripcion_equipo
from .incidencias import Incidencia
from .sectores import Sector
from .tecnicos import Tecnico

# Lo que cuenta como "abierta" en todo el dashboard. Estaba inline en
# `summary()`; la ficha del cliente tiene que usar exactamente el mismo par,
# porque si no el total global y el del cliente no cierran entre si.
ESTADOS_ABIERTOS = ("abierto", "en_progreso")


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
                    .where(Incidencia.estado.in_(ESTADOS_ABIERTOS))
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

    def cliente(self, cliente_id: int, dias_garantia: int = 60) -> dict:
        """Lo mismo que `summary()` pero de un solo cliente, mas las dos
        listas que su ficha muestra en pantalla.

        Las tres cosas que pedia el pendiente 24 —parque, incidencias
        abiertas y garantias por vencer— ya las calculaba `ReportesService`
        (reportes de Equipamiento y Garantias), pero solo para volcarlas a un
        xlsx. Aca se responden en una llamada, en vez de que la ficha se baje
        las tres tablas enteras y las filtre en el browser.

        **No valida que el cliente exista**: eso lo hace el router contra
        `ClienteRepository`, que es el que sabe devolver el 404 y la ficha.
        """
        with self.session_factory() as session:
            equipos_por_estado = dict(
                session.execute(
                    select(Equipo.estado, func.count())
                    .where(Equipo.cliente_id == cliente_id)
                    .group_by(Equipo.estado)
                ).all()
            )
            incidencias_por_estado = dict(
                session.execute(
                    select(Incidencia.estado, func.count())
                    .where(Incidencia.cliente_id == cliente_id)
                    .group_by(Incidencia.estado)
                ).all()
            )
            horas = session.execute(
                select(func.coalesce(func.sum(Incidencia.horas_invertidas), 0))
                .where(Incidencia.cliente_id == cliente_id)
            ).scalar_one()
            total_sectores = session.execute(
                select(func.count()).select_from(Sector).where(Sector.cliente_id == cliente_id)
            ).scalar_one()

            # Equipo y tecnico por outerjoin: los dos son opcionales en una
            # incidencia, y en `compulibra` la mayoria de las migradas no
            # tienen ninguno de los dos (ver la nota del pendiente 21).
            abiertas = [
                {
                    "id": i.id,
                    "titulo": i.titulo,
                    "estado": i.estado,
                    "prioridad": i.prioridad,
                    "fecha_creacion": i.fecha_creacion.isoformat() if i.fecha_creacion else None,
                    "equipo_id": i.equipo_id,
                    "equipo": descripcion_equipo(e) if e else None,
                    "tecnico": t.nombre if t else None,
                }
                for i, e, t in session.execute(
                    select(Incidencia, Equipo, Tecnico)
                    .outerjoin(Equipo, Incidencia.equipo_id == Equipo.id)
                    .outerjoin(Tecnico, Incidencia.tecnico_id == Tecnico.id)
                    .where(Incidencia.cliente_id == cliente_id)
                    .where(Incidencia.estado.in_(ESTADOS_ABIERTOS))
                    .order_by(Incidencia.fecha_creacion.desc(), Incidencia.id.desc())
                ).all()
            ]

            # Mismo criterio que el reporte de Garantias: se excluyen las
            # bajas (la garantia de un equipo dado de baja no le importa a
            # nadie) y entran tambien las YA vencidas, que son justamente las
            # que hay que ver primero.
            hoy = date.today()
            limite = hoy + timedelta(days=dias_garantia)
            garantias = []
            for e in session.execute(
                select(Equipo)
                .where(Equipo.cliente_id == cliente_id)
                .where(Equipo.garantia_vence.is_not(None))
                .where(Equipo.estado != "baja")
                .where(Equipo.garantia_vence <= limite)
                .order_by(Equipo.garantia_vence.asc())
            ).scalars():
                vence = e.garantia_vence
                vence_date = vence.date() if isinstance(vence, datetime) else vence
                garantias.append({
                    "id": e.id,
                    "descripcion": descripcion_equipo(e),
                    "serial": e.serial,
                    "sector": e.sector,
                    "ubicacion_oficina": e.ubicacion_oficina,
                    "estado": e.estado,
                    "garantia_vence": vence_date.isoformat(),
                    "dias_restantes": (vence_date - hoy).days,
                })

            return {
                "equipos_por_estado": equipos_por_estado,
                "total_equipos": sum(equipos_por_estado.values()),
                "incidencias_por_estado": incidencias_por_estado,
                "total_incidencias": sum(incidencias_por_estado.values()),
                "incidencias_abiertas": abiertas,
                "garantias": garantias,
                "dias_garantia": dias_garantia,
                "total_sectores": total_sectores,
                "horas_invertidas": float(horas),
            }
