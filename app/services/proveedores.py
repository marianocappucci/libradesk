"""Proveedores de reparacion — a quien se le manda un equipo cuando sale a
service.

**Por que es una tabla y no un texto libre en la reparacion** (decidido con el
usuario el 2026-08-03): un campo de texto se llena de "Compu Service",
"compuservice" y "Compu Service SRL", que para SQL son tres proveedores. Con
eso, la pregunta que justifica registrar el service —*"este proveedor cuanto
tarda en devolver"*— no se puede contestar nunca.

**Global y no por cliente**, mismo criterio que `categorias_incidencia`: el
service al que manda la empresa es el mismo sea cual sea el cliente duenio del
equipo.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base


class Proveedor(Base):
    __tablename__ = "proveedores"
    # Dos proveedores con el mismo nombre no se distinguen en ningun select,
    # que es justo el problema que esta tabla viene a resolver.
    __table_args__ = (UniqueConstraint("nombre"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    contacto: Mapped[str | None] = mapped_column(String(255))
    telefono: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255))
    observaciones: Mapped[str | None] = mapped_column(String(500))
    # Baja logica, mismo criterio que `clientes.activo` (ver la seccion "Un
    # cliente se desactiva, no se borra"): un proveedor con reparaciones
    # historicas no se puede borrar sin romper esa historia, pero si dejar de
    # ofrecerse en los selects.
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # --- Las tres columnas que son del motor (revision `0018`) ---------------
    #
    # `proveedores` paso a ser una tabla compartida: `libracore.db.egresos` la
    # lee para el circuito de compras, y su version declara `cuit_dni`,
    # `address` e `iva_condition`. El ABM de service de LibraDesk no las usa.
    #
    # 🔴 **Se declaran igual porque el modelo tiene que describir la tabla
    # ENTERA.** Si no, la base queda distinta segun la haya hecho Alembic o
    # `create_all()`, y `--autogenerate` propone **borrarlas**. Es el mismo
    # costo, previsto, que ya paga `clientes.py` desde que `clients` es
    # compartida — y aca lo destapo
    # `test_alembic_construye_lo_mismo_que_create_all`, no una revision a ojo.
    cuit_dni: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    address: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    iva_condition: Mapped[str] = mapped_column(Text, nullable=False, server_default="")


def _to_dict(p: Proveedor) -> dict:
    return {
        "id": p.id,
        "nombre": p.nombre,
        "contacto": p.contacto,
        "telefono": p.telefono,
        "email": p.email,
        "observaciones": p.observaciones,
        "activo": bool(p.activo),
    }


class ProveedorRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def create(
        self,
        nombre: str,
        *,
        contacto: str | None = None,
        telefono: str | None = None,
        email: str | None = None,
        observaciones: str | None = None,
    ) -> dict:
        with self.session_factory() as session:
            p = Proveedor(
                nombre=nombre.strip(), contacto=contacto, telefono=telefono,
                email=email, observaciones=observaciones,
            )
            session.add(p)
            session.commit()
            session.refresh(p)
            return _to_dict(p)

    def list(self, *, solo_activos: bool = False) -> list[dict]:
        with self.session_factory() as session:
            q = select(Proveedor).order_by(Proveedor.nombre)
            if solo_activos:
                q = q.where(Proveedor.activo.is_(True))
            return [_to_dict(p) for p in session.execute(q).scalars()]

    def get(self, proveedor_id: int) -> dict | None:
        with self.session_factory() as session:
            p = session.get(Proveedor, proveedor_id)
            return _to_dict(p) if p is not None else None

    def update(self, proveedor_id: int, **campos) -> dict:
        with self.session_factory() as session:
            p = session.get(Proveedor, proveedor_id)
            if p is None:
                raise KeyError(proveedor_id)
            for campo, valor in campos.items():
                if valor is not None and hasattr(p, campo):
                    setattr(p, campo, valor.strip() if campo == "nombre" else valor)
            session.commit()
            session.refresh(p)
            return _to_dict(p)

    def set_activo(self, proveedor_id: int, activo: bool) -> dict:
        with self.session_factory() as session:
            p = session.get(Proveedor, proveedor_id)
            if p is None:
                raise KeyError(proveedor_id)
            p.activo = activo
            session.commit()
            session.refresh(p)
            return _to_dict(p)

    def dependencias(self, proveedor_id: int) -> dict[str, int]:
        """Lo que cuelga del proveedor y le impide borrarse.

        Los activos comprados se sumaron el 2026-08-09: esa columna
        (`activos.proveedor_compra_id`) llego despues de este metodo, asi que
        borrar al proveedor dejaba el activo diciendo que se lo compro a un id
        inexistente — y de donde salio un equipo es justo el dato que se busca
        cuando hay que reclamar una garantia.
        """
        from .activos import Activo
        from .reparaciones import Reparacion

        with self.session_factory() as session:
            return {
                "reparaciones": session.execute(
                    select(func.count()).select_from(Reparacion)
                    .where(Reparacion.proveedor_id == proveedor_id)
                ).scalar_one(),
                "activos_comprados": session.execute(
                    select(func.count()).select_from(Activo)
                    .where(Activo.proveedor_compra_id == proveedor_id)
                ).scalar_one(),
            }

    def delete(self, proveedor_id: int) -> None:
        """Borra solo un proveedor **sin reparaciones** — uno cargado por error.
        Para uno con historial esta la baja logica (`set_activo`).

        La negativa es explicita y no via `IntegrityError`: el pragma
        `foreign_keys` esta apagado en las conexiones de SQLAlchemy (medido),
        asi que la base nunca levantaria el error y el DELETE pasaria dejando
        las reparaciones apuntando a un id inexistente. Es exactamente la
        trampa que este producto ya pago con el 409 de `clientes`, que estaba
        declarado en un `except IntegrityError` que no se ejecutaba nunca.
        """
        colgando = self.dependencias(proveedor_id)
        if any(colgando.values()):
            raise ValueError(colgando)

        with self.session_factory() as session:
            p = session.get(Proveedor, proveedor_id)
            if p is None:
                raise KeyError(proveedor_id)
            session.delete(p)
            session.commit()
