"""Activos — los equipos **propios** que la empresa entrega a sus clientes.

**Por que es una tabla aparte de `equipos`** (decidido con el usuario el
2026-08-04, ver `wiki/analyses/libradesk-alquiler-de-equipos-diseno.md`):
`equipos.cliente_id` es `NOT NULL` porque un equipo *pertenece a* un cliente —
es el parque que la mesa de ayuda atiende. Un activo es la relacion inversa: es
**nuestro** y esta *colocado en* un cliente, y antes de instalarse esta en
deposito sin cliente ninguno.

Lo que se gana con la tabla separada, y es el motivo de la decision: el informe
que ve el cliente, los 6 reportes XLSX y el dashboard cuentan `equipos`, asi que
el stock propio **no entra en el parque de nadie sin escribir una sola
condicion**. Con un `cliente_id` nullable habria habido que auditar cada
consulta del producto.

Lo que cuesta, y esta anotado para la fase 4: la cadena de service esta tipada
contra `equipos` (`equipos_reparaciones.equipo_id` y
`equipos_movimientos.equipo_id` son FK `NOT NULL` a `equipos.id`), asi que hoy
un activo **no puede pasar por service**. En esta fase se lo pone en
`en_reparacion` a mano y nada mas.

**La modalidad NO es un estado del activo.** "Alquilado", "en comodato" y
"prestado" son el `tipo_contrato` de la linea vigente, no situaciones del
equipo. Tenerlos en los dos lados crea dos fuentes de verdad para el mismo
hecho, y el dia que el contrato diga comodato y el activo diga alquilado no hay
forma de saber cual miente. El estado responde **donde esta**; la modalidad la
responde el contrato.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
    update,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base

# `colocado` significa "tiene una linea de contrato abierta". Se guarda en vez
# de derivarse, igual que `equipos.estado`, pero con **un solo escritor**:
# ninguna via manual puede ponerlo ni sacarlo (ver `_ESTADOS_MANUALES` abajo),
# solo `ContratoRepository.colocar()` y `.retirar()`. La invariante —no hay
# activo `colocado` sin linea abierta ni linea abierta con el activo en otro
# estado— la vigila un test dedicado, que es la unica forma de que no se
# desincronice en silencio.
ESTADOS_ACTIVO = (
    "disponible",
    "reservado",
    "en_instalacion",
    "colocado",
    "en_reparacion",
    "retirado_a_revisar",
    "baja",
    "perdido",
)

# Los que se pueden setear a mano por la API. `colocado` queda afuera a
# proposito: lo escribe la colocacion en un contrato, no un PUT.
_ESTADOS_MANUALES = tuple(e for e in ESTADOS_ACTIVO if e != "colocado")

# Con el activo en uno de estos no se lo puede colocar en un contrato. `baja` y
# `perdido` porque no existe mas como equipo entregable; `en_reparacion` porque
# esta fisicamente afuera; `colocado` porque ya esta en otro lado.
ESTADOS_NO_COLOCABLES = ("colocado", "en_reparacion", "baja", "perdido")


class Activo(Base):
    __tablename__ = "activos"
    # Los dos identificadores del activo, `UNIQUE` y nullable. En SQLite dos
    # NULL son distintos entre si, que es exactamente lo que se quiere: muchos
    # activos pueden no tener serial cargado, pero dos que lo tengan no pueden
    # tener el mismo — es el numero por el que se lo reconoce cuando vuelve.
    __table_args__ = (
        UniqueConstraint("serial"),
        UniqueConstraint("codigo_interno"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    marca: Mapped[str | None] = mapped_column(String(255))
    modelo: Mapped[str | None] = mapped_column(String(255))
    serial: Mapped[str | None] = mapped_column(String(255))
    # Codigo patrimonial interno, el que va en la etiqueta.
    codigo_interno: Mapped[str | None] = mapped_column(String(100))

    # Identificadores de red. Los tres nullable porque dependen del tipo de
    # equipo: un router tiene MAC e IP, un celular IMEI, una central las tres.
    mac: Mapped[str | None] = mapped_column(String(50))
    imei: Mapped[str | None] = mapped_column(String(50))
    ip: Mapped[str | None] = mapped_column(String(50))

    accesorios: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(50), nullable=False, default="disponible")

    # Base de la rentabilidad (fase 5). Se carga al comprar el equipo, no al
    # contratarlo: es lo que se invirtio, no lo que se cobra.
    costo_compra: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    fecha_compra: Mapped[date | None] = mapped_column(Date)
    proveedor_compra_id: Mapped[int | None] = mapped_column(
        ForeignKey("proveedores.id"), index=True,
    )
    # Lo que se le cobra al cliente si el equipo no vuelve o vuelve roto. No es
    # el costo de compra: un equipo amortizado sigue teniendo valor de
    # reposicion.
    valor_reposicion: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    garantia_vence: Mapped[date | None] = mapped_column(Date, index=True)
    observaciones: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def descripcion_activo(a: Activo) -> str:
    """"Central telefonica Yeastar S20" — mismo armado que
    `equipos.descripcion_equipo`, para que las dos familias de equipos se
    nombren igual en pantalla."""
    return " ".join(x for x in (a.tipo, a.marca, a.modelo) if x)


def _to_dict(a: Activo, *, colocacion: dict | None = None) -> dict:
    return {
        "id": a.id,
        "tipo": a.tipo,
        "marca": a.marca,
        "modelo": a.modelo,
        "serial": a.serial,
        "codigo_interno": a.codigo_interno,
        "descripcion": descripcion_activo(a),
        "mac": a.mac,
        "imei": a.imei,
        "ip": a.ip,
        "accesorios": a.accesorios,
        "estado": a.estado,
        "costo_compra": float(a.costo_compra) if a.costo_compra is not None else None,
        "fecha_compra": a.fecha_compra.isoformat() if a.fecha_compra else None,
        "proveedor_compra_id": a.proveedor_compra_id,
        "valor_reposicion": (
            float(a.valor_reposicion) if a.valor_reposicion is not None else None
        ),
        "garantia_vence": a.garantia_vence.isoformat() if a.garantia_vence else None,
        "observaciones": a.observaciones,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        # Donde esta colocado, resuelto por el repositorio. `None` cuando el
        # activo no tiene linea abierta: la lista de disponibles tiene que
        # poder escribirse sin pedir un endpoint mas por fila.
        "contrato_id": (colocacion or {}).get("contrato_id"),
        "contrato_numero": (colocacion or {}).get("contrato_numero"),
        "cliente_id": (colocacion or {}).get("cliente_id"),
        "cliente_nombre": (colocacion or {}).get("cliente_nombre"),
    }


def _colocaciones(session, activo_ids) -> dict[int, dict]:
    """Para cada activo, la linea de contrato abierta que lo tiene puesto.

    Import local por el ciclo: `contratos` importa de este modulo para validar
    que el activo se pueda colocar.
    """
    ids = [i for i in activo_ids if i is not None]
    if not ids:
        return {}

    from .clientes import Cliente
    from .contratos import Contrato, ContratoEquipo

    filas = session.execute(
        select(
            ContratoEquipo.activo_id, Contrato.id, Contrato.numero,
            Contrato.cliente_id, Cliente.nombre,
        )
        .join(Contrato, Contrato.id == ContratoEquipo.contrato_id)
        .join(Cliente, Cliente.id == Contrato.cliente_id, isouter=True)
        .where(
            ContratoEquipo.activo_id.in_(ids),
            ContratoEquipo.fecha_retiro.is_(None),
        )
    ).all()
    return {
        activo_id: {
            "contrato_id": contrato_id,
            "contrato_numero": numero,
            "cliente_id": cliente_id,
            "cliente_nombre": cliente_nombre,
        }
        for activo_id, contrato_id, numero, cliente_id, cliente_nombre in filas
    }


class ActivoRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def _normalizar(self, data: dict) -> dict:
        """Los identificadores vacios entran como NULL, no como cadena vacia.

        Es lo que hace que el `UNIQUE` sirva: dos activos con `serial=""` son un
        choque de unicidad, dos con `serial=NULL` no. Y un formulario web manda
        cadena vacia, no null, cuando el usuario no completa el campo.
        """
        limpio = dict(data)
        for campo in ("serial", "codigo_interno", "mac", "imei", "ip"):
            valor = limpio.get(campo)
            if isinstance(valor, str) and not valor.strip():
                limpio[campo] = None
            elif isinstance(valor, str):
                limpio[campo] = valor.strip()
        return limpio

    def _chequear_unicos(self, session, data: dict, *, excluyendo: int | None = None) -> None:
        """Rechaza serial o codigo interno repetido con un mensaje que se
        entiende, en vez del `IntegrityError` crudo del `UNIQUE`."""
        for campo, etiqueta in (("serial", "serial"), ("codigo_interno", "código interno")):
            valor = data.get(campo)
            if not valor:
                continue
            stmt = select(Activo.id).where(getattr(Activo, campo) == valor)
            if excluyendo is not None:
                stmt = stmt.where(Activo.id != excluyendo)
            if session.execute(stmt).first() is not None:
                raise ValueError(f"Ya existe un activo con ese {etiqueta}: {valor}")

    def create(self, **data) -> dict:
        data = self._normalizar(data)
        estado = data.get("estado") or "disponible"
        if estado not in _ESTADOS_MANUALES:
            raise ValueError(f"Estado inválido para un alta: {estado}")
        data["estado"] = estado

        with self.session_factory() as session:
            self._chequear_unicos(session, data)
            a = Activo(**data)
            session.add(a)
            session.commit()
            session.refresh(a)
            return _to_dict(a)

    def list(
        self, *, estado: str | None = None, disponibles: bool | None = None,
        cliente_id: int | None = None, tipo: str | None = None,
    ) -> list[dict]:
        """`disponibles=true` responde "que tengo para colocar" — que no es
        `estado='disponible'` a secas: `reservado` y `en_instalacion` tampoco
        estan puestos en ningun lado pero no se pueden ofrecer."""
        with self.session_factory() as session:
            stmt = select(Activo).order_by(Activo.tipo, Activo.marca, Activo.modelo)
            if estado is not None:
                stmt = stmt.where(Activo.estado == estado)
            if disponibles is True:
                stmt = stmt.where(Activo.estado == "disponible")
            if tipo is not None:
                stmt = stmt.where(Activo.tipo == tipo)

            activos = list(session.execute(stmt).scalars())
            colocaciones = _colocaciones(session, (a.id for a in activos))
            if cliente_id is not None:
                activos = [
                    a for a in activos
                    if colocaciones.get(a.id, {}).get("cliente_id") == cliente_id
                ]
            return [_to_dict(a, colocacion=colocaciones.get(a.id)) for a in activos]

    def get(self, activo_id: int) -> dict | None:
        with self.session_factory() as session:
            a = session.get(Activo, activo_id)
            if a is None:
                return None
            return _to_dict(a, colocacion=_colocaciones(session, [a.id]).get(a.id))

    def update(self, activo_id: int, **data) -> dict:
        data = self._normalizar(data)
        if "estado" in data and data["estado"] not in _ESTADOS_MANUALES:
            raise ValueError(
                f"El estado {data['estado']!r} no se setea a mano: lo escribe la "
                "colocación en un contrato."
            )

        with self.session_factory() as session:
            a = session.get(Activo, activo_id)
            if a is None:
                raise KeyError(activo_id)

            colocacion = _colocaciones(session, [a.id]).get(a.id)
            if "estado" in data and colocacion is not None:
                raise ValueError(
                    f"El activo está colocado en el contrato {colocacion['contrato_numero']}. "
                    "Retiralo del contrato antes de cambiarle el estado."
                )

            self._chequear_unicos(session, data, excluyendo=activo_id)
            for campo, valor in data.items():
                setattr(a, campo, valor)
            session.commit()
            session.refresh(a)
            return _to_dict(a, colocacion=colocacion)

    def dependencias(self, activo_id: int) -> dict[str, int]:
        """Los DOCUMENTOS del activo, que impiden borrarlo.

        Las reparaciones se sumaron el 2026-08-09: ese modulo llego despues de
        este metodo y el activo se borraba dejandolas apuntando a un id
        inexistente. No entran las incidencias ni los movimientos, que son
        asignacion e historial y los resuelve `delete()`.
        """
        from .contratos import ContratoEquipo
        from .reparaciones import Reparacion

        with self.session_factory() as session:
            return {
                "lineas_de_contrato": session.execute(
                    select(func.count()).select_from(ContratoEquipo)
                    .where(ContratoEquipo.activo_id == activo_id)
                ).scalar_one(),
                "reparaciones": session.execute(
                    select(func.count()).select_from(Reparacion)
                    .where(Reparacion.activo_id == activo_id)
                ).scalar_one(),
            }

    def delete(self, activo_id: int) -> None:
        """Borra solo un activo **sin historial de contratos ni reparaciones** —
        uno cargado por error. Para uno con historia esta el estado `baja`, que
        la conserva.

        La negativa es explicita y no via `IntegrityError`: el pragma
        `foreign_keys` esta apagado en las conexiones de SQLAlchemy (medido en
        este mismo producto), asi que la base nunca levantaria el error y el
        DELETE pasaria dejando lineas de contrato apuntando a un id inexistente.
        Misma trampa que ya documenta `ProveedorRepository.delete`.

        🔴 **Ampliado el 2026-08-09** con lo que faltaba: sus movimientos de
        equipo (que sin el activo no describen nada, igual que en
        `EquipoRepository.delete`) y la desasignacion de las incidencias que lo
        tenian. Los dos estaban declarados como `ondelete` y ninguno corria.
        """
        colgando = self.dependencias(activo_id)
        if any(colgando.values()):
            raise ValueError(colgando)

        with self.session_factory() as session:
            a = session.get(Activo, activo_id)
            if a is None:
                raise KeyError(activo_id)

            from .equipos import EquipoMovimiento
            from .incidencias import Incidencia

            session.execute(
                update(Incidencia)
                .where(Incidencia.activo_id == activo_id)
                .values(activo_id=None)
            )
            session.execute(
                EquipoMovimiento.__table__.delete()
                .where(EquipoMovimiento.activo_id == activo_id)
            )
            session.delete(a)
            session.commit()

    def resumen(self) -> dict:
        """Cuantos activos hay en cada estado — el encabezado de la pantalla.

        Sale de un `GROUP BY` y no de contar en Python sobre `list()`: la lista
        se pagina y el resumen tiene que contar todo.
        """
        with self.session_factory() as session:
            conteos = dict(
                session.execute(
                    select(Activo.estado, func.count()).group_by(Activo.estado)
                ).all()
            )
            return {
                "total": sum(conteos.values()),
                "por_estado": {e: conteos.get(e, 0) for e in ESTADOS_ACTIVO},
            }

    def crear_desde_stock(self, item_id: int, deposito_stock_id: int, *,
                          usuario_id: int | None = None, **data) -> dict:
        """Saca una unidad del stock y la convierte en un activo serializado.

        ## El problema que cierra

        El stock es **por cantidad** y los activos son **unidades
        serializadas**, y hasta hoy nada cruzaba de uno al otro. Dar de alta un
        activo a mano dejaba la unidad **contada dos veces**: seguía sumando en
        el stock del depósito *y* aparecía como activo disponible para colocar.
        Nadie lo notaba, porque las dos pantallas dicen la verdad por separado.

        Es la contraparte del alta automática de equipos que hace
        `ventas._dar_de_alta_equipos()`: allá el cruce lo dispara la venta, acá
        lo dispara una persona que decide que esta unidad se va a alquilar en
        vez de venderse.

        > 🔑 **Por qué acá y no en la recepción de la compra.** Decidido por el
        > humano el 2026-08-16: *"todo entra como stock; el activo se crea
        > aparte"*. El destino no es una propiedad del producto —la misma
        > central se compra para vender o para alquilar según el caso— y
        > tampoco se sabe siempre al recibirla. Lo que faltaba no era decidirlo
        > antes, sino que decidirlo después **descuente**.

        ## El orden, y la compensación

        Son dos conexiones distintas contra la misma base —el activo lo escribe
        SQLAlchemy, el movimiento de stock lo escribe LibraCommerce— así que no
        hay una transacción que cubra las dos. Acá **sí** se compensa, a
        diferencia de las cuatro conversiones a remito, porque los dos
        desenlaces posibles son malos de verdad:

        - Descontar y que falle el alta → la unidad **desaparece**: no está en
          stock ni es un activo.
        - Dar de alta y que falle el descuento → queda **contada dos veces**,
          que es exactamente el defecto que esto viene a cerrar, y encima en
          silencio.

        Así que: se valida disponibilidad, se crea el activo, se descuenta, y
        **si el descuento falla se borra el activo recién creado** y se propaga
        el error. `delete()` es seguro acá porque el activo tiene un segundo de
        vida y no puede tener historial.
        """
        from . import inventario

        # Antes de escribir nada: sin stock no hay unidad que convertir, y el
        # error tiene que llegar antes de crear un activo que después hay que
        # borrar.
        disponible = inventario.stock_actual(item_id, deposito_stock_id)
        if disponible < 1:
            raise ValueError(
                f"No hay stock de ese producto en el depósito "
                f"(disponible: {disponible}). No se puede convertir en activo."
            )

        activo = self.create(**data)
        try:
            inventario.ajustar(
                item_id, deposito_stock_id, -1,
                nota=f"Pasa a activo #{activo['id']}"
                     + (f" ({activo['serial']})" if activo.get("serial") else ""),
                usuario_id=usuario_id,
            )
        except Exception:
            # La compensación. Sin esto, un fallo acá deja la unidad contada dos
            # veces — el defecto original, reintroducido por la ventana entre
            # las dos conexiones.
            self.delete(activo["id"])
            raise

        return activo
