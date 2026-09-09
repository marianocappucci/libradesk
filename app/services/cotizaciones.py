"""La cotización del dólar: cuántos pesos vale, cada día.

Sale del pedido del humano del 2026-09-09. Lagrace factura en pesos y en
dólares, y el circuito que describieron es: la **pre-factura** admite renglones
en las dos monedas, y **la factura sale unificada en pesos**.

🔑 **Esta tabla es la fuente, no la verdad del comprobante.** El comprobante
congela la cotización que usó, adentro del JSON de sus ítems (ver
`remitos_presupuestos._normalizar_items`). Corregir el valor de hoy acá **no le
mueve el total a nada ya emitido**, que es justamente el punto: si el importe en
pesos se derivara al leer, reimprimir en diciembre una factura de agosto la
convertiría al dólar de diciembre.

🔴 **`vigente_a()` NO inventa una cotización, y por eso devuelve la fecha.** Si
al 15 la última cargada es del 3, contesta la del 3 **diciendo que es del 3**.
Devolver el número solo dejaría a la pantalla mostrando un tipo de cambio de
doce días como si fuera el de hoy, y nadie tendría cómo notarlo. Decidir si
sirve es de la persona que factura, no de esta función.
"""
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base
from . import fecha as fecha_helper


class Cotizacion(Base):
    __tablename__ = "cotizaciones"
    __table_args__ = (UniqueConstraint("fecha", name="uq_cotizacion_fecha"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: Una por dia. Cargarla de nuevo el mismo dia **corrige**, no agrega.
    fecha: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    #: Pesos por dolar. Cuatro decimales: el tipo de cambio se publica con mas
    #: precision que un precio, y redondear a dos arrastra el error a cada
    #: renglon convertido.
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    #: `server_default` y no solo `default`: el default vive EN LA BASE porque
    #: lo puso la revision `0039`. Con solo el de Python, el modelo describe una
    #: tabla sin default, `create_all()` la crea asi, y modelo y cadena dejan de
    #: coincidir -- que es justo lo que mide
    #: `test_alembic_construye_lo_mismo_que_create_all`. Es la misma trampa que
    #: ya documenta `clientes.activo`, y volvio a caer acá.
    usuario: Mapped[str] = mapped_column(
        String(255), nullable=False, default="Sistema", server_default="Sistema",
    )
    observaciones: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _to_dict(c: Cotizacion) -> dict:
    return {
        "id": c.id,
        "fecha": c.fecha.isoformat() if c.fecha else None,
        "valor": float(c.valor),
        "usuario": c.usuario,
        "observaciones": c.observaciones,
    }


class CotizacionRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def list(self, limite: int = 90) -> list[dict]:
        """Las últimas, más reciente primero. Es un historial corto a propósito:
        la pantalla sirve para ver qué se cargó y corregirlo, no para analizar
        la serie del dólar."""
        with self.session_factory() as session:
            filas = session.execute(
                select(Cotizacion).order_by(Cotizacion.fecha.desc()).limit(limite)
            ).scalars()
            return [_to_dict(c) for c in filas]

    def get_por_fecha(self, fecha: date_type) -> dict | None:
        with self.session_factory() as session:
            c = session.execute(
                select(Cotizacion).where(Cotizacion.fecha == fecha)
            ).scalar_one_or_none()
            return _to_dict(c) if c else None

    def vigente_a(self, fecha: date_type | None = None) -> dict | None:
        """La cotización de esa fecha, o **la última anterior**, o `None`.

        🔴 Devuelve el registro entero —con su `fecha`— y no el número, para que
        quien la use pueda decir *"cotización del 03-09"*. Ver el docstring del
        módulo: una cotización vieja presentada como la de hoy es un error que
        nadie ve hasta que la factura sale mal.

        `None` cuando **no hay ninguna cargada todavía**. No cae a 1: un dólar a
        un peso convertiría los renglones en dólares a su valor nominal y el
        comprobante saldría por una fracción de lo que vale, sin fallar.
        """
        objetivo = fecha or date_type.fromisoformat(fecha_helper.hoy())
        with self.session_factory() as session:
            c = session.execute(
                select(Cotizacion)
                .where(Cotizacion.fecha <= objetivo)
                .order_by(Cotizacion.fecha.desc())
                .limit(1)
            ).scalar_one_or_none()
            return _to_dict(c) if c else None

    def guardar(self, fecha: date_type, valor: float, *, usuario: str = "Sistema",
                observaciones: str | None = None) -> dict:
        """Alta o corrección del día. Una por fecha, así que es un upsert.

        Sin `create` y `update` separados: la pantalla carga "la cotización de
        hoy", y que eso falle con un 409 porque alguien ya la puso a la mañana
        obligaría a mirar antes de escribir para hacer siempre lo mismo.
        """
        if valor <= 0:
            raise ValueError("La cotización tiene que ser mayor que cero.")
        with self.session_factory() as session:
            c = session.execute(
                select(Cotizacion).where(Cotizacion.fecha == fecha)
            ).scalar_one_or_none()
            if c is None:
                c = Cotizacion(fecha=fecha)
                session.add(c)
            c.valor = Decimal(str(valor))
            c.usuario = usuario
            c.observaciones = observaciones
            session.commit()
            session.refresh(c)
            return _to_dict(c)

    def delete(self, cotizacion_id: int) -> None:
        with self.session_factory() as session:
            c = session.get(Cotizacion, cotizacion_id)
            if c is None:
                raise KeyError(cotizacion_id)
            session.delete(c)
            session.commit()
