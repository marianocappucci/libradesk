"""Equipos (inventario por cliente) + `EquipoMovimiento` (historial de
movimientos/cambios de estado — 75 filas reales migradas desde Postgres,
tabla que ni el backend Node.js viejo exponia via API, encontrada al
inspeccionar el esquema real antes de migrar).

**Escritura del historial (repuesta 2026-07-29).** Entre la reescritura y
esa fecha la tabla quedo de solo lectura: se seguian mostrando las 75
filas migradas pero no se registraba ningun movimiento nuevo. El backend
Node.js lo hacia desde endpoints dedicados (`baja`, `trasladar`,
`desplegar`, `cambiarEstado`); LibraDesk tiene un CRUD generico, asi que
el movimiento se **deriva de lo que efectivamente cambio** en el update,
mismo patron con el que `IncidenciaRepository` ya registra
`IncidenciaEstadoLog`. Un update que no toca ubicacion ni estado no
genera ruido en el historial."""
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
    # El vinculo con el ticket que causo el movimiento. Sin esto la
    # trazabilidad se corta justo en el medio: el historial del equipo
    # dice que salio de Admision el 29/07, pero no por que — y la
    # incidencia dice que se retiro el equipo, pero solo si alguien lo
    # escribio a mano en una nota. Lo escribe `ReemplazoService`.
    #
    # Sin `ondelete`: en las conexiones de SQLAlchemy el pragma
    # `foreign_keys` esta APAGADO (medido), asi que cualquier `ON DELETE`
    # que declararamos aca no se ejecutaria nunca. Al borrar una
    # incidencia, `IncidenciaRepository.delete()` pone esta columna en
    # NULL explicitamente — el movimiento fisico ocurrio igual y no se
    # borra con el ticket.
    incidencia_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidencias.id"), index=True,
    )


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
        "incidencia_id": m.incidencia_id,
    }


def descripcion_equipo(e: Equipo) -> str:
    """"Notebook Lenovo T14" — mismo armado que usaba el backend viejo
    para el texto del movimiento."""
    return " ".join(x for x in (e.tipo, e.marca, e.modelo) if x)


# Alias interno historico: el nombre publico es `descripcion_equipo`, que
# tambien usa `ReemplazoService` para narrar las intervenciones.
_descripcion_equipo = descripcion_equipo


def ubicacion_texto(sector: str | None, ubicacion: str | None) -> str:
    return " · ".join(x for x in (sector, ubicacion) if x) or "sin ubicación"


def movimientos_por_cambio(
    e: Equipo,
    *,
    sector_previo: str | None,
    ubicacion_previa: str | None,
    estado_previo: str,
    usuario: str,
    motivo: str | None = None,
    incidencia_id: int | None = None,
) -> list[EquipoMovimiento]:
    """Deriva los movimientos de lo que efectivamente cambio en el equipo.

    Unico lugar donde se decide que es un movimiento: lo usan tanto el
    `PUT /api/equipos/{id}` (edicion manual) como `ReemplazoService`, para
    que un reemplazo y una edicion a mano produzcan exactamente el mismo
    historial y no dos dialectos distintos.

    - **traslado** si cambio `sector` o `ubicacion_oficina`, guardando
      origen y destino de ambos.
    - **cambio de estado** con `tipo` = el estado nuevo (asi el reporte lo
      etiqueta 'Baja'/'Reparación'/'Reactivado' via `MOV_LABEL`, igual que
      el sistema viejo).

    Los dos pueden darse juntos — el equipo que vuelve del service Y
    cambia de sector genera dos filas, que es lo correcto. Un update que
    solo corrige el serial no genera ninguna.
    """
    movimientos: list[EquipoMovimiento] = []

    if e.sector != sector_previo or e.ubicacion_oficina != ubicacion_previa:
        destino = e.sector or e.ubicacion_oficina or "sin ubicación"
        movimientos.append(EquipoMovimiento(
            equipo_id=e.id,
            tipo="traslado",
            descripcion=f"Traslado → {destino}",
            sector_origen=sector_previo,
            sector_destino=e.sector,
            ubicacion_origen=ubicacion_previa,
            ubicacion_destino=e.ubicacion_oficina,
            motivo=motivo,
            usuario=usuario,
            incidencia_id=incidencia_id,
        ))

    if e.estado != estado_previo:
        movimientos.append(EquipoMovimiento(
            equipo_id=e.id,
            tipo=e.estado,
            descripcion=f"Estado cambiado a: {e.estado}",
            # En un cambio de estado sin traslado, la ubicacion es de donde
            # sale: por eso va como origen y no destino.
            sector_origen=e.sector,
            ubicacion_origen=e.ubicacion_oficina,
            motivo=motivo,
            usuario=usuario,
            incidencia_id=incidencia_id,
        ))

    return movimientos


class EquipoRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def create(self, usuario_actor: str | None = None, **data) -> dict:
        with self.session_factory() as session:
            e = Equipo(**data)
            session.add(e)
            session.flush()
            session.add(EquipoMovimiento(
                equipo_id=e.id,
                tipo="alta",
                descripcion=f"Alta: {_descripcion_equipo(e)}",
                sector_destino=e.sector,
                ubicacion_destino=e.ubicacion_oficina,
                motivo="Alta inicial del equipo",
                usuario=usuario_actor or "Sistema",
            ))
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

    def update(self, equipo_id: int, usuario_actor: str | None = None,
               motivo: str | None = None, incidencia_id: int | None = None,
               **data) -> dict:
        """Registra en el historial lo que el update cambio de verdad —
        ver `movimientos_por_cambio()`, que es donde vive esa decision y
        que comparte con `ReemplazoService`."""
        with self.session_factory() as session:
            e = session.get(Equipo, equipo_id)
            if e is None:
                raise KeyError(equipo_id)

            sector_previo, ubicacion_previa, estado_previo = e.sector, e.ubicacion_oficina, e.estado
            for key, value in data.items():
                setattr(e, key, value)

            for movimiento in movimientos_por_cambio(
                e,
                sector_previo=sector_previo,
                ubicacion_previa=ubicacion_previa,
                estado_previo=estado_previo,
                usuario=usuario_actor or "Sistema",
                motivo=motivo,
                incidencia_id=incidencia_id,
            ):
                session.add(movimiento)

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
                .order_by(EquipoMovimiento.fecha.desc(), EquipoMovimiento.id.desc())
            )
            return [_mov_to_dict(m) for m in session.execute(stmt).scalars()]

    def list_movimientos_por_incidencia(self, incidencia_id: int) -> list[dict]:
        """Los movimientos que causo un ticket — de todos los equipos que
        toco, no de uno solo: un reemplazo mueve dos. Alimenta el timeline
        de `/incidencias/:id`."""
        with self.session_factory() as session:
            stmt = (
                select(EquipoMovimiento)
                .where(EquipoMovimiento.incidencia_id == incidencia_id)
                .order_by(EquipoMovimiento.fecha.desc(), EquipoMovimiento.id.desc())
            )
            return [_mov_to_dict(m) for m in session.execute(stmt).scalars()]
