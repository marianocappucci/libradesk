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

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, String, Text, delete, func,
    select, update,
)
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
    # Donde esta guardado, cuando no esta instalado en el puesto. Con esto en
    # NULL el equipo esta en el `sector`/`ubicacion_oficina` del cliente; con
    # un valor, esta **en ese deposito** y el sector es de donde salio. La
    # ubicacion efectiva la resuelve `depositos.lugar_de()`, que es la unica
    # definicion de "donde esta" — ver el docstring de `services/depositos.py`.
    #
    # Sin `ondelete`: los ondelete no se ejecutan (el pragma `foreign_keys`
    # esta apagado, ver `delete()` mas abajo) y ademas no haria falta —
    # `DepositoRepository.delete()` no deja borrar un deposito con equipos
    # adentro, justamente para que esta columna no quede colgando.
    deposito_id: Mapped[int | None] = mapped_column(
        ForeignKey("depositos.id"), index=True,
    )
    estado: Mapped[str] = mapped_column(String(50), nullable=False, default="activo")
    fecha_adicion: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    garantia_vence: Mapped[date | None] = mapped_column(Date)
    observaciones: Mapped[str | None] = mapped_column(Text)


class EquipoMovimiento(Base):
    """El historial de **cualquier** equipo, sea del cliente o propio.

    **Polimorfica desde la fase 4 del modulo de alquileres (2026-08-04):** o
    tiene `equipo_id` (parque del cliente) o `activo_id` (stock propio), nunca
    las dos ni ninguna — lo garantiza un CHECK, que en SQLite **si** se ejecuta,
    a diferencia de las FK (el pragma `foreign_keys` esta apagado).

    Se eligio esto sobre una tabla `activos_movimientos` aparte porque un
    movimiento es el mismo hecho en los dos casos —esto se movio de aca a alla
    tal dia, por tal ticket— y duplicarlo obligaria a unir dos tablas en cada
    listado, cada reporte y cada timeline. El costo se midio antes de decidir:
    reconstruir una tabla de 77 filas en produccion y 53 en dev.
    """

    __tablename__ = "equipos_movimientos"
    __table_args__ = (
        CheckConstraint(
            "(equipo_id IS NOT NULL) <> (activo_id IS NOT NULL)",
            name="ck_movimiento_equipo_xor_activo",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Nullable desde la fase 4: el movimiento de un activo propio no tiene
    # equipo. Exactamente uno de los dos, por el CHECK de arriba.
    equipo_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipos.id", ondelete="CASCADE"), index=True,
    )
    activo_id: Mapped[int | None] = mapped_column(
        ForeignKey("activos.id", ondelete="CASCADE"), index=True,
    )
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


def _to_dict(e: Equipo, deposito_nombre: str | None = None) -> dict:
    return {
        "id": e.id,
        "cliente_id": e.cliente_id,
        "tipo": e.tipo,
        "modelo": e.modelo,
        "marca": e.marca,
        "serial": e.serial,
        "ubicacion_oficina": e.ubicacion_oficina,
        "sector": e.sector,
        "deposito_id": e.deposito_id,
        # Resuelto para que ninguna pantalla tenga que cruzar la lista de
        # depositos solo para escribir donde esta el equipo.
        "deposito_nombre": deposito_nombre,
        "estado": e.estado,
        "fecha_adicion": e.fecha_adicion.isoformat() if e.fecha_adicion else None,
        "garantia_vence": e.garantia_vence.isoformat() if e.garantia_vence else None,
        "observaciones": e.observaciones,
    }


def _mov_to_dict(m: EquipoMovimiento) -> dict:
    return {
        "id": m.id,
        "equipo_id": m.equipo_id,
        # Exactamente uno de los dos tiene valor. Los consumidores que sólo
        # miran equipos del cliente pueden seguir ignorando `activo_id`.
        "activo_id": m.activo_id,
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
    deposito_previo: str | None = None,
    deposito_actual: str | None = None,
    motivo: str | None = None,
    incidencia_id: int | None = None,
) -> list[EquipoMovimiento]:
    """Deriva los movimientos de lo que efectivamente cambio en el equipo.

    Unico lugar donde se decide que es un movimiento: lo usan tanto el
    `PUT /api/equipos/{id}` (edicion manual) como `ReemplazoService` y el
    movimiento entre depositos, para que las tres operaciones produzcan
    exactamente el mismo historial y no tres dialectos distintos.

    - **traslado** si cambio el lugar (sector del cliente **o** deposito) o
      la `ubicacion_oficina`, guardando origen y destino de ambos.
    - **cambio de estado** con `tipo` = el estado nuevo (asi el reporte lo
      etiqueta 'Baja'/'Reparación'/'Reactivado' via `MOV_LABEL`, igual que
      el sistema viejo).

    Los dos pueden darse juntos — el equipo que vuelve del service Y
    cambia de sector genera dos filas, que es lo correcto. Un update que
    solo corrige el serial no genera ninguna.

    **Los depositos entran como nombre, no como id** (`deposito_previo` /
    `deposito_actual`, que el llamador resuelve): el movimiento describe
    donde estaba el equipo *entonces*, y guardar la FK haria que renombrar
    un deposito reescribiera el pasado. Ver `services/depositos.py`.
    """
    from .depositos import lugar_de

    movimientos: list[EquipoMovimiento] = []

    lugar_previo = lugar_de(deposito_previo, sector_previo)
    lugar_actual = lugar_de(deposito_actual, e.sector)

    if lugar_previo != lugar_actual or e.ubicacion_oficina != ubicacion_previa:
        destino = lugar_actual or e.ubicacion_oficina or "sin ubicación"
        movimientos.append(EquipoMovimiento(
            equipo_id=e.id,
            tipo="traslado",
            descripcion=f"Traslado → {destino}",
            sector_origen=lugar_previo,
            sector_destino=lugar_actual,
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
            sector_origen=lugar_actual,
            ubicacion_origen=e.ubicacion_oficina,
            motivo=motivo,
            usuario=usuario,
            incidencia_id=incidencia_id,
        ))

    return movimientos


def _nombres_depositos(session, ids) -> dict[int, str]:
    """`{id: nombre}` de una tanda, para no consultar el deposito por fila."""
    from .depositos import Deposito

    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return dict(
        session.execute(
            select(Deposito.id, Deposito.nombre).where(Deposito.id.in_(ids))
        ).all()
    )


def _validar_deposito(session, cliente_id: int, deposito_id: int | None) -> str | None:
    """Devuelve el nombre del deposito, validando que el equipo pueda entrar.

    Un equipo solo puede guardarse en un deposito **propio de la empresa** o
    en uno **de su propio cliente**. Sin este chequeo, el selector de la
    pantalla alcanza para dejar el equipo de un cliente en el pañol de otro,
    y eso no se ve despues en ningun lado: el equipo sigue figurando como del
    cliente correcto y solo la ubicacion miente.
    """
    from .depositos import ClienteAjeno, Deposito

    if deposito_id is None:
        return None
    d = session.get(Deposito, deposito_id)
    if d is None:
        raise ClienteAjeno("El depósito indicado no existe.")
    if d.cliente_id is not None and d.cliente_id != cliente_id:
        raise ClienteAjeno(
            f"El depósito «{d.nombre}» es de otro cliente: un equipo solo puede "
            "guardarse en un depósito propio de la empresa o en uno de su cliente."
        )
    return d.nombre


class EquipoRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def create(self, usuario_actor: str | None = None, **data) -> dict:
        with self.session_factory() as session:
            e = Equipo(**data)
            deposito = _validar_deposito(session, e.cliente_id, e.deposito_id)
            session.add(e)
            session.flush()
            session.add(EquipoMovimiento(
                equipo_id=e.id,
                tipo="alta",
                descripcion=f"Alta: {_descripcion_equipo(e)}",
                sector_destino=deposito or e.sector,
                ubicacion_destino=e.ubicacion_oficina,
                motivo="Alta inicial del equipo",
                usuario=usuario_actor or "Sistema",
            ))
            session.commit()
            session.refresh(e)
            return _to_dict(e, deposito)

    def list(self, cliente_id: int | None = None,
             deposito_id: int | None = None) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(Equipo).order_by(Equipo.tipo)
            if cliente_id is not None:
                stmt = stmt.where(Equipo.cliente_id == cliente_id)
            if deposito_id is not None:
                stmt = stmt.where(Equipo.deposito_id == deposito_id)
            equipos = list(session.execute(stmt).scalars())
            nombres = _nombres_depositos(session, (e.deposito_id for e in equipos))
            return [_to_dict(e, nombres.get(e.deposito_id)) for e in equipos]

    def get(self, equipo_id: int) -> dict | None:
        with self.session_factory() as session:
            e = session.get(Equipo, equipo_id)
            if e is None:
                return None
            return _to_dict(e, _nombres_depositos(session, [e.deposito_id]).get(e.deposito_id))

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
            nombres = _nombres_depositos(session, [e.deposito_id])
            deposito_previo = nombres.get(e.deposito_id)
            for key, value in data.items():
                setattr(e, key, value)
            deposito_actual = _validar_deposito(session, e.cliente_id, e.deposito_id)

            for movimiento in movimientos_por_cambio(
                e,
                sector_previo=sector_previo,
                ubicacion_previa=ubicacion_previa,
                estado_previo=estado_previo,
                usuario=usuario_actor or "Sistema",
                deposito_previo=deposito_previo,
                deposito_actual=deposito_actual,
                motivo=motivo,
                incidencia_id=incidencia_id,
            ):
                session.add(movimiento)

            session.commit()
            session.refresh(e)
            return _to_dict(e, deposito_actual)

    def mover_a_deposito(self, equipo_ids: list[int], deposito_id: int | None,
                         usuario_actor: str | None = None,
                         motivo: str | None = None) -> list[dict]:
        """Mueve varios equipos a un deposito de una vez, o los saca de todos
        (`deposito_id=None`, "vuelve al puesto del cliente").

        **En una transaccion y no un PUT por equipo**: sacar 12 equipos de un
        deposito que se esta cerrando es un solo hecho, y hacerlo de a uno
        admite que la mitad quede movida y la otra mitad no, sin nada que
        diga cual fue el corte.

        El estado no se toca acá a proposito. Un equipo puede entrar al
        deposito porque se lo retiro (`almacenado`) o porque volvio de service
        y espera instalacion, y adivinarlo desde el destino escribiria un
        cambio de estado que nadie pidio. Para eso esta la edicion del equipo,
        que registra las dos cosas juntas.
        """
        with self.session_factory() as session:
            movidos: list[dict] = []
            for equipo_id in equipo_ids:
                e = session.get(Equipo, equipo_id)
                if e is None:
                    raise KeyError(equipo_id)

                previo = _nombres_depositos(session, [e.deposito_id]).get(e.deposito_id)
                sector_previo = e.sector
                e.deposito_id = deposito_id
                actual = _validar_deposito(session, e.cliente_id, deposito_id)

                for movimiento in movimientos_por_cambio(
                    e,
                    sector_previo=sector_previo,
                    ubicacion_previa=e.ubicacion_oficina,
                    estado_previo=e.estado,
                    usuario=usuario_actor or "Sistema",
                    deposito_previo=previo,
                    deposito_actual=actual,
                    motivo=motivo,
                ):
                    session.add(movimiento)
                movidos.append(_to_dict(e, actual))

            session.commit()
            return movidos

    def dependencias(self, equipo_id: int) -> dict[str, int]:
        """Los DOCUMENTOS que cuelgan del equipo y que impiden borrarlo.

        Un comprobante de ingreso y una reparacion son papeles: dicen que
        alguien trajo algo y que se le hizo tal cosa. Sobreviven al equipo por
        definicion, asi que el equipo no se borra mientras existan — para
        sacarlo de circulacion esta el estado `baja`, que conserva la historia.

        No entran aca los movimientos ni las incidencias: esos son
        asignaciones e historial *del equipo*, y `delete()` los resuelve.
        """
        from .ingresos import IngresoReparacion
        from .reparaciones import Reparacion

        with self.session_factory() as session:
            return {
                "comprobantes_de_ingreso": session.execute(
                    select(func.count()).select_from(IngresoReparacion)
                    .where(IngresoReparacion.equipo_id == equipo_id)
                ).scalar_one(),
                "reparaciones": session.execute(
                    select(func.count()).select_from(Reparacion)
                    .where(Reparacion.equipo_id == equipo_id)
                ).scalar_one(),
            }

    def delete(self, equipo_id: int) -> None:
        """Borra el equipo con **su historial de movimientos** y
        **desasigna** las incidencias que lo tenian.

        Los dos `ondelete` declarados en los modelos (CASCADE en
        `equipos_movimientos`, SET NULL en `incidencias.equipo_id`) no se
        ejecutan nunca: el engine no activa `PRAGMA foreign_keys`. **No es
        teorico** — el 2026-07-30 un script de verificacion borro sus
        equipos de prueba por la API y los 10 movimientos sobrevivieron
        huerfanos en dev, y hubo que limpiarlos a mano.

        Los movimientos SI se borran aca, a diferencia de los del ticket
        (ver `IncidenciaRepository.delete`, donde solo pierden el link):
        son el historial *del equipo*, y sin el equipo no describen nada.

        🔴 **Y se niega si hay comprobantes o reparaciones** (2026-08-09).
        Faltaba: esas dos tablas llegaron despues de este metodo y nadie
        volvio a mirarlo, asi que el DELETE pasaba y las dejaba apuntando a un
        id inexistente. Contra PostgreSQL las dos FK rechazan el borrado, que
        es la misma decision — sólo que la base la toma sola.
        """
        colgando = self.dependencias(equipo_id)
        if any(colgando.values()):
            raise ValueError(colgando)

        with self.session_factory() as session:
            e = session.get(Equipo, equipo_id)
            if e is None:
                raise KeyError(equipo_id)

            # Import local, mismo criterio que en el resto: evita el ciclo
            # con `incidencias`, que si importa cosas de este modulo.
            from .incidencias import Incidencia

            session.execute(
                update(Incidencia)
                .where(Incidencia.equipo_id == equipo_id)
                .values(equipo_id=None)
            )
            session.execute(
                delete(EquipoMovimiento).where(EquipoMovimiento.equipo_id == equipo_id)
            )
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
