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
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text,
    func, select,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base


class Reparacion(Base):
    """El paso por service de **cualquier** equipo, sea del cliente o propio.

    **Polimorfica desde la fase 4 del modulo de alquileres (2026-08-04):** o
    `equipo_id` (parque del cliente) o `activo_id` (stock propio), nunca las dos
    ni ninguna, garantizado por un CHECK — que en SQLite si se ejecuta, a
    diferencia de las FK.

    La alternativa era una tabla `activos_reparaciones` propia. Se descarto
    porque partiria en dos la pregunta que justifica registrar el service:
    *"que tengo hoy afuera"* y *"este proveedor cuanto tarda"* tendrian que unir
    dos tablas en la pantalla, en el reporte y en el informe. Un equipo en
    service es el mismo hecho sea de quien sea el equipo.
    """

    __tablename__ = "equipos_reparaciones"
    __table_args__ = (
        CheckConstraint(
            "(equipo_id IS NOT NULL) <> (activo_id IS NOT NULL)",
            name="ck_reparacion_equipo_xor_activo",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Nullable desde la fase 4. Exactamente uno de los dos, por el CHECK.
    equipo_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipos.id"), index=True,
    )
    activo_id: Mapped[int | None] = mapped_column(
        ForeignKey("activos.id"), index=True,
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


def _to_dict(r: Reparacion, *, proveedor=None, equipo=None, activo=None,
             cliente_id_activo: int | None = None) -> dict:
    """`equipo` y `activo` son excluyentes, igual que las columnas.

    Las claves de salida **no** se duplican (`activo_descripcion` etc.): la
    pantalla de reparaciones muestra "qué está en service", y para eso da igual
    de quién sea el aparato. Que el consumidor tenga que elegir entre dos juegos
    de campos convertiria una tabla unificada en dos listas pegadas.
    """
    fuente = equipo if equipo is not None else activo
    return {
        "id": r.id,
        "equipo_id": r.equipo_id,
        "activo_id": r.activo_id,
        # `equipo` = parque del cliente, `activo` = stock propio alquilado. Lo
        # necesita la UI para linkear a la ficha correcta.
        "es_activo": r.activo_id is not None,
        "incidencia_id": r.incidencia_id,
        "proveedor_id": r.proveedor_id,
        # Resueltos para que la lista no tenga que pedir dos endpoints mas solo
        # para escribir un renglon, mismo criterio que `parent_nombre` en las
        # categorias.
        "proveedor_nombre": proveedor.nombre if proveedor is not None else None,
        "equipo_descripcion": (
            " ".join(x for x in (fuente.tipo, fuente.marca, fuente.modelo) if x)
            if fuente is not None else None
        ),
        "equipo_serial": fuente.serial if fuente is not None else None,
        # De un activo el cliente no sale del aparato sino del contrato en el
        # que esta colocado, y puede no haber ninguno (en deposito). Lo resuelve
        # `resolver()`.
        "cliente_id": (
            equipo.cliente_id if equipo is not None else cliente_id_activo
        ),
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
    from .activos import Activo
    from .equipos import Equipo
    from .proveedores import Proveedor

    if r is None:
        return None
    activo = session.get(Activo, r.activo_id) if r.activo_id is not None else None
    return _to_dict(
        r,
        proveedor=session.get(Proveedor, r.proveedor_id),
        equipo=session.get(Equipo, r.equipo_id) if r.equipo_id is not None else None,
        activo=activo,
        cliente_id_activo=(
            _cliente_del_activo(session, activo.id) if activo is not None else None
        ),
    )


def _cliente_del_activo(session, activo_id: int) -> int | None:
    """En que cliente esta colocado el activo hoy, si esta en alguno.

    Sale de la linea de contrato abierta y no de una columna del activo, por lo
    mismo que el cliente de una reparacion sale del equipo: duplicarlo abriria
    la puerta a que digan cosas distintas cuando el activo se mude de contrato.
    """
    from .contratos import Contrato, ContratoEquipo

    return session.execute(
        select(Contrato.cliente_id)
        .join(ContratoEquipo, ContratoEquipo.contrato_id == Contrato.id)
        .where(
            ContratoEquipo.activo_id == activo_id,
            ContratoEquipo.fecha_retiro.is_(None),
        )
    ).scalars().first()


def _exigir_uno(equipo_id: int | None, activo_id: int | None) -> None:
    """Uno de los dos y solo uno — la misma regla que el CHECK de la tabla.

    Se valida acá además de en la base para que el error sea legible: el CHECK
    levanta un `IntegrityError` crudo que la API traduciría a un 500.
    """
    if (equipo_id is None) == (activo_id is None):
        raise ValueError(
            "una reparación es de un equipo del cliente o de un activo propio: "
            "hay que indicar exactamente uno de los dos"
        )


def _abierta(session, *, equipo_id: int | None = None,
             activo_id: int | None = None) -> Reparacion | None:
    """La reparación abierta de un equipo o de un activo.

    Un único lugar donde se define "está afuera", usado por el alta (para
    rechazar la segunda), por la vuelta del service y por la consulta directa.
    Tenerlo tres veces era lo que hacía que agregar los activos dejara alguno
    sin cubrir.
    """
    q = select(Reparacion).where(Reparacion.fecha_retorno.is_(None))
    if equipo_id is not None:
        q = q.where(Reparacion.equipo_id == equipo_id)
    elif activo_id is not None:
        q = q.where(Reparacion.activo_id == activo_id)
    else:
        return None
    return session.execute(q.order_by(Reparacion.fecha_envio.desc())).scalars().first()


class ReparacionRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def _resolver(self, session, r: Reparacion) -> dict:
        return resolver(session, r)

    def abierta_de(self, equipo_id: int | None = None, *,
                   activo_id: int | None = None) -> dict | None:
        """La reparacion abierta del equipo o del activo, si la tiene. La usa la
        vuelta del service para saber cual cerrar sin que la UI pase el id."""
        with self.session_factory() as session:
            r = _abierta(session, equipo_id=equipo_id, activo_id=activo_id)
            return self._resolver(session, r) if r is not None else None

    def create(
        self,
        *,
        equipo_id: int | None = None,
        activo_id: int | None = None,
        proveedor_id: int,
        fecha_envio: date,
        incidencia_id: int | None = None,
        remito_salida: str | None = None,
        rma: str | None = None,
        en_garantia: bool = False,
        observaciones: str | None = None,
        usuario: str = "Sistema",
    ) -> dict:
        from .activos import Activo
        from .equipos import Equipo
        from .proveedores import Proveedor

        _exigir_uno(equipo_id, activo_id)

        with self.session_factory() as session:
            if equipo_id is not None and session.get(Equipo, equipo_id) is None:
                raise KeyError(("equipo", equipo_id))
            if activo_id is not None and session.get(Activo, activo_id) is None:
                raise KeyError(("activo", activo_id))
            if session.get(Proveedor, proveedor_id) is None:
                raise KeyError(("proveedor", proveedor_id))
            # Ver el docstring del modulo: dos reparaciones abiertas sobre el
            # mismo equipo describen un estado que no puede pasar. Vale igual
            # para un activo.
            if _abierta(session, equipo_id=equipo_id, activo_id=activo_id) is not None:
                raise ValueError("el equipo ya tiene una reparacion abierta")

            r = Reparacion(
                equipo_id=equipo_id, activo_id=activo_id,
                proveedor_id=proveedor_id,
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
        activo_id: int | None = None,
        incidencia_id: int | None = None,
        proveedor_id: int | None = None,
        cliente_id: int | None = None,
        solo_activos: bool | None = None,
        abiertas: bool | None = None,
    ) -> list[dict]:
        """Las abiertas primero y, dentro de cada grupo, la mas reciente arriba
        — que es el orden en que se las mira.

        Sin filtros salen **las dos familias juntas**, que es el punto de la
        tabla unificada: "qué tengo hoy en service" no distingue de quién es el
        aparato. `solo_activos` separa cuando hace falta.
        """
        from .contratos import Contrato, ContratoEquipo
        from .equipos import Equipo

        with self.session_factory() as session:
            q = select(Reparacion)
            if equipo_id is not None:
                q = q.where(Reparacion.equipo_id == equipo_id)
            if activo_id is not None:
                q = q.where(Reparacion.activo_id == activo_id)
            if incidencia_id is not None:
                q = q.where(Reparacion.incidencia_id == incidencia_id)
            if proveedor_id is not None:
                q = q.where(Reparacion.proveedor_id == proveedor_id)
            if solo_activos is True:
                q = q.where(Reparacion.activo_id.is_not(None))
            elif solo_activos is False:
                q = q.where(Reparacion.equipo_id.is_not(None))
            if cliente_id is not None:
                # El cliente lo tiene el equipo, no la reparacion: duplicarlo
                # aca abriria la puerta a que digan cosas distintas si el
                # equipo cambia de duenio.
                #
                # Para un activo el cliente sale del contrato donde esta
                # colocado. Por eso son dos caminos unidos con OR y no un join:
                # un join contra `equipos` dejaria afuera todas las
                # reparaciones de activos, en silencio.
                de_equipos = select(Equipo.id).where(Equipo.cliente_id == cliente_id)
                de_activos = (
                    select(ContratoEquipo.activo_id)
                    .join(Contrato, Contrato.id == ContratoEquipo.contrato_id)
                    .where(
                        Contrato.cliente_id == cliente_id,
                        ContratoEquipo.fecha_retiro.is_(None),
                    )
                )
                q = q.where(
                    Reparacion.equipo_id.in_(de_equipos)
                    | Reparacion.activo_id.in_(de_activos)
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
