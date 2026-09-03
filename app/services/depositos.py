"""Depositos: donde esta un equipo cuando no esta instalado en el puesto.

**Dos duenos posibles y una sola tabla.** `cliente_id` en NULL es un deposito
**propio** (el taller, el deposito central de la empresa); con `cliente_id` es
un deposito **del cliente** (su propio panol, su sala de racks). Son la misma
cosa —un lugar donde un equipo espera— y separarlos en dos tablas obligaria a
duplicar el CRUD, la transferencia y la resolucion de nombres para no ganar
nada: lo unico que cambia entre uno y otro es quien es el dueno.

**Que reemplaza.** Hasta ahora "esta en el deposito" era texto libre en
`equipos.sector` — el placeholder del formulario decia literalmente
"Deposito, Admision...", y `ReemplazoService` escribia la constante
`"Deposito"` al mandar un equipo ahi. O sea que no habia forma de listar que
hay en cada deposito, ni de mover un equipo de uno a otro, ni de saber si
"Deposito" y "deposito central" eran el mismo lugar.

**La ubicacion de un equipo es una de dos, nunca las dos.** Si `deposito_id`
esta seteado, el equipo esta **en ese deposito**; si no, esta en el
`sector`/`ubicacion_oficina` del cliente. Por eso todo lo que muestra "donde
esta" pasa por `lugar_de()`, aca abajo, en vez de leer una u otra columna
segun se acuerde.

**El historial no guarda el id del deposito, guarda su nombre** (en los
`sector_origen`/`sector_destino` de `equipos_movimientos`, que son texto). Es
deliberado: un movimiento dice donde estaba el equipo **entonces**, y una FK
haria que renombrar un deposito reescribiera hacia atras todos los
movimientos que lo nombran. Ademas deja las 75 filas migradas del Node.js
viejo —que ya son texto— en el mismo dialecto que las nuevas.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    func,
    select,
    update,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base


class Deposito(Base):
    __tablename__ = "depositos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # NULL = deposito propio de la empresa. Ver el docstring del modulo.
    #
    # Sin `UniqueConstraint("cliente_id", "nombre")`: en SQLite dos NULL son
    # distintos entre si, asi que la constraint dejaria pasar dos depositos
    # propios con el mismo nombre — justo el caso que mas importa. La unicidad
    # se valida en el repositorio, que puede tratar el NULL como un valor.
    cliente_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True,
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(500))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # El deposito al que va a parar un equipo cuando no se elige ninguno —
    # lo usa `ReemplazoService` para el destino "vuelve a deposito". Solo
    # entre los propios: un deposito de un cliente no puede ser el default
    # de la empresa. Ver `set_default()`.
    es_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _to_dict(d: Deposito, *, total_equipos: int | None = None,
             cliente_nombre: str | None = None) -> dict:
    return {
        "id": d.id,
        "cliente_id": d.cliente_id,
        # Resuelto por el repositorio para que la lista no tenga que pedir
        # `/api/clientes` solo para escribir un renglon — mismo criterio que
        # `proveedor_nombre` en las reparaciones.
        "cliente_nombre": cliente_nombre,
        "nombre": d.nombre,
        "descripcion": d.descripcion,
        "activo": d.activo,
        "es_default": d.es_default,
        "total_equipos": total_equipos,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def lugar_de(deposito_nombre: str | None, sector: str | None) -> str | None:
    """Donde esta el equipo: el deposito si esta en uno, si no su sector.

    Unica definicion de "donde esta", usada por el historial, los reportes y
    la ficha. Sin esto cada pantalla elige una de las dos columnas y la que
    elija mal muestra el sector viejo de un equipo que hace un mes esta
    guardado en el taller.
    """
    return deposito_nombre or sector


class DepositoEnUso(ValueError):
    """No se puede borrar: todavia tiene equipos adentro."""


class NombreRepetido(ValueError):
    """Ya hay un deposito con ese nombre para el mismo dueno."""


class ClienteAjeno(ValueError):
    """Se intento guardar un equipo en el deposito de otro cliente."""


class DepositoRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    # ── Lectura ─────────────────────────────────────────────────────

    def list(self, cliente_id: int | None = None, propios: bool | None = None,
             solo_activos: bool = False) -> list[dict]:
        """`cliente_id` acota a los de un cliente; `propios=True`, a los de la
        empresa. Sin ninguno de los dos, devuelve todos — que es lo que
        necesita el selector de "mover equipo", donde los dos tipos conviven.
        """
        from .clientes import Cliente
        from .equipos import Equipo

        with self.session_factory() as session:
            stmt = (
                select(Deposito, Cliente.nombre)
                .outerjoin(Cliente, Deposito.cliente_id == Cliente.id)
                # Los propios primero, y dentro de cada dueno por nombre.
                .order_by(Deposito.cliente_id.is_not(None), Cliente.nombre, Deposito.nombre)
            )
            if cliente_id is not None:
                stmt = stmt.where(Deposito.cliente_id == cliente_id)
            elif propios:
                stmt = stmt.where(Deposito.cliente_id.is_(None))
            if solo_activos:
                stmt = stmt.where(Deposito.activo.is_(True))

            conteos = dict(
                session.execute(
                    select(Equipo.deposito_id, func.count())
                    .where(Equipo.deposito_id.is_not(None))
                    .group_by(Equipo.deposito_id)
                ).all()
            )
            return [
                _to_dict(d, total_equipos=conteos.get(d.id, 0), cliente_nombre=nombre)
                for d, nombre in session.execute(stmt).all()
            ]

    def get(self, deposito_id: int) -> dict | None:
        from .clientes import Cliente
        from .equipos import Equipo

        with self.session_factory() as session:
            d = session.get(Deposito, deposito_id)
            if d is None:
                return None
            total = session.execute(
                select(func.count()).select_from(Equipo)
                .where(Equipo.deposito_id == deposito_id)
            ).scalar_one()
            nombre = None
            if d.cliente_id is not None:
                c = session.get(Cliente, d.cliente_id)
                nombre = c.nombre if c else None
            return _to_dict(d, total_equipos=total, cliente_nombre=nombre)

    def nombres(self, ids: set[int]) -> dict[int, str]:
        """`{id: nombre}` de una tanda de depositos, para resolver los nombres
        de un listado de equipos sin una consulta por fila."""
        if not ids:
            return {}
        with self.session_factory() as session:
            return dict(
                session.execute(
                    select(Deposito.id, Deposito.nombre).where(Deposito.id.in_(ids))
                ).all()
            )

    # ── Escritura ───────────────────────────────────────────────────

    def _chequear_nombre(self, session, nombre: str, cliente_id: int | None,
                         excluir: int | None = None) -> None:
        stmt = select(Deposito).where(func.lower(Deposito.nombre) == nombre.lower())
        stmt = (
            stmt.where(Deposito.cliente_id.is_(None)) if cliente_id is None
            else stmt.where(Deposito.cliente_id == cliente_id)
        )
        if excluir is not None:
            stmt = stmt.where(Deposito.id != excluir)
        if session.execute(stmt).first() is not None:
            duenio = "la empresa" if cliente_id is None else "ese cliente"
            raise NombreRepetido(f"Ya existe un depósito «{nombre}» para {duenio}.")

    def create(self, nombre: str, cliente_id: int | None = None,
               descripcion: str | None = None) -> dict:
        with self.session_factory() as session:
            nombre = nombre.strip()
            self._chequear_nombre(session, nombre, cliente_id)
            d = Deposito(
                nombre=nombre,
                cliente_id=cliente_id,
                descripcion=(descripcion or "").strip() or None,
            )
            # El primer deposito propio queda como default solo: si no, el
            # reemplazo "vuelve a deposito" no tendria a donde mandar el
            # equipo hasta que alguien se acuerde de marcar uno.
            if cliente_id is None:
                ya_hay = session.execute(
                    select(Deposito.id).where(Deposito.cliente_id.is_(None))
                ).first()
                d.es_default = ya_hay is None
            session.add(d)
            session.commit()
            session.refresh(d)
            return _to_dict(d, total_equipos=0)

    def update(self, deposito_id: int, nombre: str, descripcion: str | None = None,
               activo: bool = True) -> dict:
        with self.session_factory() as session:
            d = session.get(Deposito, deposito_id)
            if d is None:
                raise KeyError(deposito_id)
            nombre = nombre.strip()
            self._chequear_nombre(session, nombre, d.cliente_id, excluir=deposito_id)
            d.nombre = nombre
            d.descripcion = (descripcion or "").strip() or None
            d.activo = activo
            session.commit()
            session.refresh(d)
            return self.get(deposito_id)

    def set_default(self, deposito_id: int) -> dict:
        """Marca el deposito propio al que va lo que no elige destino.

        **Solo entre los propios.** El default lo consulta `ReemplazoService`
        cuando un equipo "vuelve a deposito" sin que nadie diga a cual, y ahi
        el equipo puede ser de cualquier cliente: si el default fuera el
        deposito de un cliente, la mitad de los reemplazos terminarian
        guardando el equipo de un cliente en el pañol de otro.
        """
        with self.session_factory() as session:
            d = session.get(Deposito, deposito_id)
            if d is None:
                raise KeyError(deposito_id)
            if d.cliente_id is not None:
                raise ClienteAjeno(
                    "Solo un depósito propio de la empresa puede ser el predeterminado."
                )
            session.execute(
                update(Deposito)
                .where(Deposito.cliente_id.is_(None))
                .values(es_default=False)
            )
            d.es_default = True
            session.commit()
            return self.get(deposito_id)

    def default(self) -> dict | None:
        """El deposito propio marcado como default, o el primero que haya.

        El fallback importa: una instancia que todavia no creo ningun
        deposito, o que borro el que era default, no puede quedarse sin
        destino para "vuelve a deposito".
        """
        with self.session_factory() as session:
            stmt = (
                select(Deposito)
                .where(Deposito.cliente_id.is_(None))
                .where(Deposito.activo.is_(True))
                .order_by(Deposito.es_default.desc(), Deposito.id)
            )
            d = session.execute(stmt).scalars().first()
            return _to_dict(d) if d else None

    def delete(self, deposito_id: int) -> None:
        """Borra el deposito **vacio**.

        Con equipos adentro no se borra ni se vacia solo: sacarlos seria
        moverlos a ninguna parte, y dejarlos apuntando a un id inexistente es
        lo que ya paso con los sectores (ver `SectorRepository.delete`). Mismo
        criterio que Contalibra, que tampoco deja borrar un deposito con
        stock.
        """
        from .equipos import Equipo

        with self.session_factory() as session:
            d = session.get(Deposito, deposito_id)
            if d is None:
                raise KeyError(deposito_id)
            cuantos = session.execute(
                select(func.count()).select_from(Equipo)
                .where(Equipo.deposito_id == deposito_id)
            ).scalar_one()
            if cuantos:
                raise DepositoEnUso(
                    f"El depósito «{d.nombre}» tiene {cuantos} equipo"
                    f"{'s' if cuantos != 1 else ''} adentro. Moverlos antes de borrarlo."
                )
            session.delete(d)
            session.commit()

    # ── Equipos que hay adentro ─────────────────────────────────────

    def equipos(self, deposito_id: int) -> list[dict]:
        """El contenido del deposito, con el cliente de cada equipo resuelto:
        en un deposito propio conviven equipos de varios clientes y sin esa
        columna la lista no se puede leer."""
        from .clientes import Cliente
        from .equipos import Equipo, descripcion_equipo
        from .equipos import _to_dict as _equipo_to_dict

        with self.session_factory() as session:
            filas = session.execute(
                select(Equipo, Cliente)
                .join(Cliente, Equipo.cliente_id == Cliente.id)
                .where(Equipo.deposito_id == deposito_id)
                .order_by(Cliente.nombre, Equipo.tipo, Equipo.marca)
            ).all()
            return [
                {
                    **_equipo_to_dict(e),
                    "descripcion": descripcion_equipo(e),
                    "cliente_nombre": c.empresa or c.nombre,
                }
                for e, c in filas
            ]
