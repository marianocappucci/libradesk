"""Reparaciones — el paso por service de un equipo, con su proveedor, su
remito, su RMA y su garantia.

**El hueco que cierra.** Hasta ahora mandar un equipo a service dejaba
exactamente dos rastros: el equipo en estado `en_reparacion` y un movimiento
cuyo `motivo` era texto libre. O sea que *"a quien se lo mandamos"*, *"con que
remito salio"*, *"que numero de RMA nos dieron"* y *"entro por garantia"*
vivian —cuando vivian— dentro de una frase escrita a mano. Nada de eso se
podia listar, filtrar ni sumar.

**El estado es derivado, no una columna**: `fecha_retorno` en NULL significa
que el equipo **sigue afuera**. Una columna `estado` aparte podria contradecir
a la fecha (cerrada sin fecha de retorno, abierta con fecha) y habria que
mantener las dos en sincronia; asi la pregunta "que tengo hoy en service" es
un `WHERE fecha_retorno IS NULL` y no puede mentir.

**Una sola reparacion abierta por equipo.** Un equipo no puede estar en dos
services a la vez, y sin la regla el historial admite estados imposibles que
despues nadie sabe interpretar. Se valida al abrir.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func, select,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base


class Reparacion(Base):
    __tablename__ = "equipos_reparaciones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    equipo_id: Mapped[int] = mapped_column(
        ForeignKey("equipos.id"), nullable=False, index=True,
    )
    # El ticket que la origino. Nullable porque un equipo puede salir a service
    # sin que haya ticket de por medio (mantenimiento programado), y porque al
    # borrar la incidencia el desenlace es el mismo que en
    # `equipos_movimientos`: el paso por service ocurrio de verdad y le
    # sobrevive al ticket. Lo pone en NULL `IncidenciaRepository.delete()`.
    incidencia_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidencias.id"), index=True,
    )
    proveedor_id: Mapped[int] = mapped_column(
        ForeignKey("proveedores.id"), nullable=False, index=True,
    )
    fecha_envio: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # NULL = el equipo sigue en service. Ver el docstring del modulo: el estado
    # se deriva de esta columna en vez de duplicarse en una propia.
    fecha_retorno: Mapped[date | None] = mapped_column(Date, index=True)
    remito_salida: Mapped[str | None] = mapped_column(String(100))
    rma: Mapped[str | None] = mapped_column(String(100))
    en_garantia: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Se carga al cerrar: cuanto salio. NULL con la reparacion ya cerrada
    # significa "no se registro", no "gratis" — para eso esta `en_garantia`.
    costo: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Que informo el proveedor al devolver el equipo.
    diagnostico: Mapped[str | None] = mapped_column(Text)
    observaciones: Mapped[str | None] = mapped_column(Text)
    usuario: Mapped[str] = mapped_column(String(255), nullable=False, default="Sistema")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _to_dict(r: Reparacion, *, proveedor=None, equipo=None) -> dict:
    return {
        "id": r.id,
        "equipo_id": r.equipo_id,
        "incidencia_id": r.incidencia_id,
        "proveedor_id": r.proveedor_id,
        # Resueltos para que la lista no tenga que pedir dos endpoints mas solo
        # para escribir un renglon, mismo criterio que `parent_nombre` en las
        # categorias.
        "proveedor_nombre": proveedor.nombre if proveedor is not None else None,
        "equipo_descripcion": (
            " ".join(x for x in (equipo.tipo, equipo.marca, equipo.modelo) if x)
            if equipo is not None else None
        ),
        "equipo_serial": equipo.serial if equipo is not None else None,
        "cliente_id": equipo.cliente_id if equipo is not None else None,
        "fecha_envio": r.fecha_envio.isoformat() if r.fecha_envio else None,
        "fecha_retorno": r.fecha_retorno.isoformat() if r.fecha_retorno else None,
        # Derivado, nunca almacenado.
        "abierta": r.fecha_retorno is None,
        "dias_afuera": _dias_afuera(r),
        "remito_salida": r.remito_salida,
        "rma": r.rma,
        "en_garantia": bool(r.en_garantia),
        "costo": float(r.costo) if r.costo is not None else None,
        "diagnostico": r.diagnostico,
        "observaciones": r.observaciones,
        "usuario": r.usuario,
        # El sello real, con milisegundos. `fecha_envio` es un `date` que carga
        # el usuario y puede ser de hace una semana; para ordenar la reparacion
        # dentro del timeline del ticket hace falta el instante en que se
        # registro, que es el que `_sellar_cronologia` deja sin empatar.
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _dias_afuera(r: Reparacion) -> int | None:
    """Cuantos dias estuvo (o lleva) el equipo en service.

    Con la reparacion abierta se cuenta contra **hoy**, que es lo que hace util
    la lista de abiertas: lo que interesa mirar ahi es cual se esta demorando.
    """
    if r.fecha_envio is None:
        return None
    fin = r.fecha_retorno or date.today()
    return (fin - r.fecha_envio).days


def resolver(session, r: Reparacion | None) -> dict | None:
    """El dict de una reparacion con su proveedor y su equipo ya resueltos.

    A nivel de modulo y no metodo del repositorio porque `ReemplazoService`
    tambien lo necesita, y desde **su** sesion: la reparacion recien creada
    todavia no esta commiteada cuando hay que devolverla. Tenerlo dos veces
    —que fue como salio primero— hace que un test cubra un camino y deje el
    otro sin cubrir, sin que se note.
    """
    from .equipos import Equipo
    from .proveedores import Proveedor

    if r is None:
        return None
    return _to_dict(
        r,
        proveedor=session.get(Proveedor, r.proveedor_id),
        equipo=session.get(Equipo, r.equipo_id),
    )


class ReparacionRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def _resolver(self, session, r: Reparacion) -> dict:
        return resolver(session, r)

    def abierta_de(self, equipo_id: int) -> dict | None:
        """La reparacion abierta del equipo, si la tiene. La usa la vuelta del
        service para saber cual cerrar sin que la UI tenga que pasar el id."""
        with self.session_factory() as session:
            r = session.execute(
                select(Reparacion)
                .where(Reparacion.equipo_id == equipo_id)
                .where(Reparacion.fecha_retorno.is_(None))
                .order_by(Reparacion.fecha_envio.desc())
            ).scalars().first()
            return self._resolver(session, r) if r is not None else None

    def create(
        self,
        *,
        equipo_id: int,
        proveedor_id: int,
        fecha_envio: date,
        incidencia_id: int | None = None,
        remito_salida: str | None = None,
        rma: str | None = None,
        en_garantia: bool = False,
        observaciones: str | None = None,
        usuario: str = "Sistema",
    ) -> dict:
        from .equipos import Equipo
        from .proveedores import Proveedor

        with self.session_factory() as session:
            if session.get(Equipo, equipo_id) is None:
                raise KeyError(("equipo", equipo_id))
            if session.get(Proveedor, proveedor_id) is None:
                raise KeyError(("proveedor", proveedor_id))
            # Ver el docstring del modulo: dos reparaciones abiertas sobre el
            # mismo equipo describen un estado que no puede pasar.
            ya_abierta = session.execute(
                select(func.count()).select_from(Reparacion)
                .where(Reparacion.equipo_id == equipo_id)
                .where(Reparacion.fecha_retorno.is_(None))
            ).scalar_one()
            if ya_abierta:
                raise ValueError("el equipo ya tiene una reparacion abierta")

            r = Reparacion(
                equipo_id=equipo_id, proveedor_id=proveedor_id,
                fecha_envio=fecha_envio, incidencia_id=incidencia_id,
                remito_salida=remito_salida, rma=rma, en_garantia=en_garantia,
                observaciones=observaciones, usuario=usuario,
            )
            session.add(r)
            session.commit()
            session.refresh(r)
            return self._resolver(session, r)

    def list(
        self,
        *,
        equipo_id: int | None = None,
        incidencia_id: int | None = None,
        proveedor_id: int | None = None,
        cliente_id: int | None = None,
        abiertas: bool | None = None,
    ) -> list[dict]:
        """Las abiertas primero y, dentro de cada grupo, la mas reciente arriba
        — que es el orden en que se las mira."""
        from .equipos import Equipo

        with self.session_factory() as session:
            q = select(Reparacion)
            if equipo_id is not None:
                q = q.where(Reparacion.equipo_id == equipo_id)
            if incidencia_id is not None:
                q = q.where(Reparacion.incidencia_id == incidencia_id)
            if proveedor_id is not None:
                q = q.where(Reparacion.proveedor_id == proveedor_id)
            if cliente_id is not None:
                # El cliente lo tiene el equipo, no la reparacion: duplicarlo
                # aca abriria la puerta a que digan cosas distintas si el
                # equipo cambia de duenio.
                q = q.join(Equipo, Equipo.id == Reparacion.equipo_id).where(
                    Equipo.cliente_id == cliente_id
                )
            if abiertas is True:
                q = q.where(Reparacion.fecha_retorno.is_(None))
            elif abiertas is False:
                q = q.where(Reparacion.fecha_retorno.is_not(None))

            q = q.order_by(
                Reparacion.fecha_retorno.is_not(None),
                Reparacion.fecha_envio.desc(),
                Reparacion.id.desc(),
            )
            return [self._resolver(session, r) for r in session.execute(q).scalars()]

    def get(self, reparacion_id: int) -> dict | None:
        with self.session_factory() as session:
            r = session.get(Reparacion, reparacion_id)
            return self._resolver(session, r) if r is not None else None

    def cerrar(
        self,
        reparacion_id: int,
        *,
        fecha_retorno: date,
        diagnostico: str | None = None,
        costo: Decimal | float | None = None,
        observaciones: str | None = None,
    ) -> dict:
        """Registra la vuelta del equipo. **No toca el equipo**: reinstalarlo
        (o mandarlo a deposito) es un movimiento de inventario y lo hace
        `ReemplazoService`, que ya sabe generar el historial. Mezclar las dos
        cosas aca produciria movimientos que la edicion manual no produce, que
        es justo lo que ese service evita."""
        with self.session_factory() as session:
            r = session.get(Reparacion, reparacion_id)
            if r is None:
                raise KeyError(reparacion_id)
            if r.fecha_retorno is not None:
                raise ValueError("la reparacion ya esta cerrada")
            if fecha_retorno < r.fecha_envio:
                # Sin esto `dias_afuera` da negativo y la lista de demoras
                # queda sin sentido.
                raise ValueError("la fecha de retorno es anterior a la de envio")
            r.fecha_retorno = fecha_retorno
            if diagnostico is not None:
                r.diagnostico = diagnostico
            if costo is not None:
                r.costo = Decimal(str(costo))
            if observaciones is not None:
                r.observaciones = observaciones
            session.commit()
            session.refresh(r)
            return self._resolver(session, r)

    def update(self, reparacion_id: int, **campos) -> dict:
        """Corregir los datos de salida (proveedor, remito, RMA, garantia).
        La fecha de retorno no entra por aca — para eso esta `cerrar()`, que
        valida el orden de las fechas."""
        editables = {
            "proveedor_id", "fecha_envio", "remito_salida", "rma",
            "en_garantia", "diagnostico", "costo", "observaciones",
        }
        with self.session_factory() as session:
            r = session.get(Reparacion, reparacion_id)
            if r is None:
                raise KeyError(reparacion_id)
            for campo, valor in campos.items():
                if campo in editables and valor is not None:
                    setattr(r, campo, Decimal(str(valor)) if campo == "costo" else valor)
            if r.fecha_retorno is not None and r.fecha_retorno < r.fecha_envio:
                raise ValueError("la fecha de retorno es anterior a la de envio")
            session.commit()
            session.refresh(r)
            return self._resolver(session, r)

    def delete(self, reparacion_id: int) -> None:
        with self.session_factory() as session:
            r = session.get(Reparacion, reparacion_id)
            if r is None:
                raise KeyError(reparacion_id)
            session.delete(r)
            session.commit()
