"""Ingreso de un equipo a reparación, con sus dos comprobantes (pedido 43).

El papel que se le da al cliente cuando deja un equipo en el mostrador, y el que
firma cuando se lo lleva. En la UI: **"Comprobante de recepción de equipo"** y
**"Comprobante de entrega"** — no "recibo", que se lee como recibo de pago.

**Qué NO es.** No es `[[reparaciones]]` (`equipos_reparaciones`), que es el
equipo saliendo **hacia un proveedor externo**. Acá el equipo entra **desde el
cliente**. Son direcciones opuestas y contrapartes distintas, y conviven: entra
la notebook (ingreso) → se la manda al service (reparación) → vuelve → se la
devuelve al cliente (entrega del mismo ingreso).

---

## Una fila por episodio de custodia, no dos comprobantes enlazados

El pedido habla de dos comprobantes ("*si el equipo se devuelve después, debería
existir también un comprobante de entrega, vinculado al de recepción*"). La
forma obvia sería dos filas con una FK entre ellas. **Es una fila sola**, y la
entrega vive en las mismas columnas.

Por qué:

- **El vínculo pasa a ser estructural.** Con dos filas, el modelo admite una
  entrega huérfana, o apuntando al ingreso equivocado, y hay que defenderse de
  eso en cada escritura. Con una fila no se puede ni escribir.
- **`fecha_entrega IS NULL` contesta "qué tengo hoy en el taller"** y no puede
  mentir. Es el mismo criterio, ya probado acá, que `reparaciones` usa para "qué
  tengo hoy en service": el estado se **deriva**, no se guarda en una columna
  que después haya que mantener en sincronía.
- Los dos comprobantes son **dos renderizados de la misma fila**, no dos
  documentos con datos propios que puedan discrepar.

Lo que sí son dos son los **números**: `REC-NNNNNNNN` se emite al recibir,
`ENT-NNNNNNNN` al entregar. Cada papel tiene su correlativo, que es lo que el
cliente busca cuando llama.

## Los datos del equipo se COPIAN, no se leen por FK

`equipo_tipo`, `equipo_marca`, `equipo_modelo` y `equipo_serial` son columnas de
esta tabla, aunque `equipo_id` también exista.

**Un comprobante es la foto de lo que se declaró ese día.** Si mañana alguien
corrige el modelo en el inventario, el papel que el cliente ya firmó no puede
cambiar retroactivamente — y si el equipo se borra, el comprobante tiene que
seguir diciendo qué se recibió. Leerlos por FK convertiría un documento en una
consulta, que es exactamente lo que un comprobante no es.

Y hay un caso que la FK no cubre: **la notebook que trae un cliente de mostrador
no está en su inventario**. Por eso `equipo_id` es opcional y los cuatro campos
son la fuente de verdad del papel.

> Es la misma distinción que ya hace `incidencia_pdf.py`, del otro lado: una
> orden de trabajo *"no persiste el archivo… es una consulta materializada, no
> un comprobante numerado"*. Éste sí es un comprobante numerado. Lo que se
> persiste igual **no es el PDF sino la fila**: el PDF se regenera de ella, pero
> los datos que imprime están congelados.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base

_PREFIJO_RECEPCION = "REC-"
_PREFIJO_ENTREGA = "ENT-"


class IngresoReparacion(Base):
    """Un equipo del cliente en nuestro poder, de la recepción a la entrega."""

    __tablename__ = "ingresos_reparacion"
    # El UNIQUE de `numero_entrega` convive con **muchos NULL a la vez**, y eso
    # es lo buscado: mientras el equipo está en el taller la columna es NULL, y
    # ni SQLite ni el estándar comparan NULLs entre sí. Lo que el UNIQUE
    # garantiza es lo que importa — que dos entregas no compartan número.
    __table_args__ = (
        UniqueConstraint("numero", name="uq_ingreso_numero"),
        UniqueConstraint("numero_entrega", name="uq_ingreso_numero_entrega"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # --- el comprobante de recepción ---------------------------------------
    numero: Mapped[str] = mapped_column(String(50), nullable=False)
    # DateTime y no Date: el pedido pide "fecha y hora de recepción", y con
    # razón — dos ingresos del mismo día del mismo cliente se distinguen por la
    # hora, y en un reclamo eso es lo que se discute.
    fecha_recepcion: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True,
    )
    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id"), nullable=False, index=True,
    )
    # El contacto del papel, escrito a mano: puede no ser el contacto que figura
    # en la ficha del cliente (manda a un empleado a dejar el equipo), y el
    # comprobante tiene que decir quién vino de verdad.
    contacto: Mapped[str | None] = mapped_column(String(255))
    contacto_telefono: Mapped[str | None] = mapped_column(String(50))

    # --- el equipo, congelado (ver el docstring del módulo) -----------------
    equipo_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipos.id"), index=True,
    )
    equipo_tipo: Mapped[str] = mapped_column(String(255), nullable=False)
    equipo_marca: Mapped[str | None] = mapped_column(String(255))
    equipo_modelo: Mapped[str | None] = mapped_column(String(255))
    equipo_serial: Mapped[str | None] = mapped_column(String(255), index=True)

    # --- lo que hace útil el papel en un reclamo ----------------------------
    # Los tres son texto libre a propósito. Un catálogo de accesorios o de
    # daños tendría que anticipar el mundo, y lo que hace valer el comprobante
    # es justamente el detalle que nadie previó ("cargador genérico, sin
    # funda, tapa rayada en la esquina inferior derecha").
    accesorios: Mapped[str | None] = mapped_column(Text)
    estado_fisico: Mapped[str | None] = mapped_column(Text)
    falla_declarada: Mapped[str | None] = mapped_column(Text)
    observaciones: Mapped[str | None] = mapped_column(Text)

    tecnico_id: Mapped[int | None] = mapped_column(
        ForeignKey("tecnicos.id"), index=True,
    )
    # Quién trajo el equipo, y quién se lo lleva. Los dos son el nombre escrito
    # en el papel: la firma es de puño y letra sobre el impreso, acá se guarda
    # la aclaración. **No hay firma digital y no debería haberla** — una casilla
    # "aceptado" que marca el operador no prueba nada, y llamarla firma sería
    # peor que no tenerla.
    entregado_por: Mapped[str | None] = mapped_column(String(255))

    # El ticket. Nullable porque el mostrador recibe equipos antes de que el
    # ticket exista, y porque al borrar la incidencia el desenlace es el mismo
    # que en `equipos_movimientos`: el equipo entró de verdad y el comprobante
    # le sobrevive al ticket. Lo pone en NULL `IncidenciaRepository.delete()`.
    incidencia_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidencias.id"), index=True,
    )

    # --- el comprobante de entrega (NULL = sigue en el taller) --------------
    numero_entrega: Mapped[str | None] = mapped_column(String(50))
    fecha_entrega: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    retirado_por: Mapped[str | None] = mapped_column(String(255))
    trabajo_realizado: Mapped[str | None] = mapped_column(Text)
    observaciones_entrega: Mapped[str | None] = mapped_column(Text)
    tecnico_entrega_id: Mapped[int | None] = mapped_column(
        ForeignKey("tecnicos.id"), index=True,
    )

    usuario: Mapped[str] = mapped_column(String(255), nullable=False, default="Sistema")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _dias_en_taller(i: IngresoReparacion) -> int | None:
    """Cuántos días estuvo (o lleva) el equipo acá.

    Con el ingreso abierto se cuenta contra **hoy**, igual que `reparaciones`:
    lo que interesa mirar en la lista de abiertos es cuál se está demorando.
    """
    if i.fecha_recepcion is None:
        return None
    fin = i.fecha_entrega.date() if i.fecha_entrega else date.today()
    return (fin - i.fecha_recepcion.date()).days


def _to_dict(i: IngresoReparacion, *, cliente_nombre=None, tecnico_nombre=None,
             tecnico_entrega_nombre=None) -> dict:
    return {
        "id": i.id,
        "numero": i.numero,
        "fecha_recepcion": i.fecha_recepcion.isoformat() if i.fecha_recepcion else None,
        "cliente_id": i.cliente_id,
        "cliente_nombre": cliente_nombre,
        "contacto": i.contacto,
        "contacto_telefono": i.contacto_telefono,
        "equipo_id": i.equipo_id,
        "equipo_tipo": i.equipo_tipo,
        "equipo_marca": i.equipo_marca,
        "equipo_modelo": i.equipo_modelo,
        "equipo_serial": i.equipo_serial,
        # Armada acá y no en cada pantalla, mismo criterio que `reparaciones`.
        "equipo_descripcion": " ".join(
            x for x in (i.equipo_tipo, i.equipo_marca, i.equipo_modelo) if x
        ),
        "accesorios": i.accesorios,
        "estado_fisico": i.estado_fisico,
        "falla_declarada": i.falla_declarada,
        "observaciones": i.observaciones,
        "tecnico_id": i.tecnico_id,
        "tecnico_nombre": tecnico_nombre,
        "entregado_por": i.entregado_por,
        "incidencia_id": i.incidencia_id,
        "numero_entrega": i.numero_entrega,
        "fecha_entrega": i.fecha_entrega.isoformat() if i.fecha_entrega else None,
        "retirado_por": i.retirado_por,
        "trabajo_realizado": i.trabajo_realizado,
        "observaciones_entrega": i.observaciones_entrega,
        "tecnico_entrega_id": i.tecnico_entrega_id,
        "tecnico_entrega_nombre": tecnico_entrega_nombre,
        # Derivados, nunca almacenados.
        "en_taller": i.fecha_entrega is None,
        "dias_en_taller": _dias_en_taller(i),
        "usuario": i.usuario,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }


class IngresoRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    # --- helpers -----------------------------------------------------------

    def _siguiente_numero(self, session, prefijo: str, columna) -> str:
        """Correlativo por prefijo, misma forma que `CTR-` y `PRES-`.

        Se calcula del máximo **dentro de la misma transacción que inserta**, que
        es lo que evita el duplicado entre dos altas simultáneas; el
        `UniqueConstraint` está como red, y en SQLite **sí** se ejecuta (el
        pragma apagado es `foreign_keys`, no las constraints de unicidad).
        """
        ultimo = session.execute(
            select(func.max(columna)).where(columna.like(f"{prefijo}%"))
        ).scalar_one_or_none()
        siguiente = 1 if not ultimo else int(ultimo.removeprefix(prefijo)) + 1
        return f"{prefijo}{siguiente:08d}"

    def _nombres(self, session, i: IngresoReparacion) -> dict:
        """Los tres nombres que la pantalla necesita, resueltos de una vez."""
        from .clientes import Cliente
        from .tecnicos import Tecnico

        def tecnico(tid):
            if tid is None:
                return None
            t = session.get(Tecnico, tid)
            return t.nombre if t is not None else None

        cliente = session.get(Cliente, i.cliente_id)
        return {
            "cliente_nombre": cliente.nombre if cliente is not None else None,
            "tecnico_nombre": tecnico(i.tecnico_id),
            "tecnico_entrega_nombre": tecnico(i.tecnico_entrega_id),
        }

    # --- lectura -----------------------------------------------------------

    def list(self, *, cliente_id: int | None = None, incidencia_id: int | None = None,
             en_taller: bool | None = None) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(IngresoReparacion)
            if cliente_id is not None:
                stmt = stmt.where(IngresoReparacion.cliente_id == cliente_id)
            if incidencia_id is not None:
                stmt = stmt.where(IngresoReparacion.incidencia_id == incidencia_id)
            if en_taller is True:
                stmt = stmt.where(IngresoReparacion.fecha_entrega.is_(None))
            elif en_taller is False:
                stmt = stmt.where(IngresoReparacion.fecha_entrega.is_not(None))
            # Más reciente primero: lo que se mira es lo que acaba de entrar.
            stmt = stmt.order_by(IngresoReparacion.fecha_recepcion.desc())
            filas = list(session.execute(stmt).scalars())
            return [_to_dict(i, **self._nombres(session, i)) for i in filas]

    def get(self, ingreso_id: int) -> dict | None:
        with self.session_factory() as session:
            i = session.get(IngresoReparacion, ingreso_id)
            if i is None:
                return None
            return _to_dict(i, **self._nombres(session, i))

    # --- escritura ---------------------------------------------------------

    def create(self, usuario_actor: str | None = None, **data) -> dict:
        """Recibe el equipo y emite el comprobante de recepción.

        Los campos del equipo se copian **acá y ahora**: si viene `equipo_id` y
        el que carga no los completó, se toman del inventario en este instante
        y quedan congelados. No se releen después — ver el docstring del módulo.
        """
        from .equipos import Equipo, EquipoMovimiento

        with self.session_factory() as session:
            equipo = (
                session.get(Equipo, data["equipo_id"])
                if data.get("equipo_id") else None
            )
            if data.get("equipo_id") and equipo is None:
                raise KeyError("equipo not found")
            if equipo is not None:
                for campo, valor in (
                    ("equipo_tipo", equipo.tipo), ("equipo_marca", equipo.marca),
                    ("equipo_modelo", equipo.modelo), ("equipo_serial", equipo.serial),
                ):
                    if not data.get(campo):
                        data[campo] = valor

            if not data.get("equipo_tipo"):
                raise ValueError(
                    "Falta el tipo de equipo: sin eso el comprobante no dice qué "
                    "se recibió."
                )
            # `if not` y NO `setdefault`: el router manda la clave siempre, con
            # `None` cuando el mostrador no la cargó, así que `setdefault` no
            # dispararía nunca y el INSERT moriría contra el NOT NULL. Es el
            # mismo defecto de "el default declarado en dos capas" que ya se
            # pagó con `estado_activo` en el módulo de alquileres.
            if not data.get("fecha_recepcion"):
                data["fecha_recepcion"] = datetime.now()
            data["usuario"] = usuario_actor or "Sistema"

            i = IngresoReparacion(**data)
            i.numero = self._siguiente_numero(
                session, _PREFIJO_RECEPCION, IngresoReparacion.numero,
            )
            session.add(i)
            session.flush()

            # El movimiento del equipo, que es lo que pidió el pedido: "asociar
            # el comprobante a la incidencia y al movimiento del equipo". Sólo
            # si el equipo está en el inventario — el de mostrador no tiene
            # historial que anotar.
            if equipo is not None:
                session.add(EquipoMovimiento(
                    equipo_id=equipo.id,
                    incidencia_id=i.incidencia_id,
                    tipo="ingreso_reparacion",
                    descripcion=f"Recibido para reparación ({i.numero})",
                    motivo=data.get("falla_declarada"),
                    usuario=i.usuario,
                ))

            session.commit()
            session.refresh(i)
            return _to_dict(i, **self._nombres(session, i))

    def update(self, ingreso_id: int, usuario_actor: str | None = None, **data) -> dict:
        """Corrige los datos de la recepción.

        **No toca los campos de la entrega**: para eso está `entregar()`, que es
        el que emite el segundo número. Si esto los aceptara, se podría fabricar
        una entrega sin comprobante — y el cliente se iría sin el papel.

        **Tampoco el `numero`.** Es el correlativo que ya se imprimió.

        Semántica de objeto entero, igual que el resto del producto: lo que no
        viaja se borra. Con **una excepción**, las tres columnas `NOT NULL`: ahí
        un `None` sólo puede significar "el que llama no lo mandó", porque
        vaciarlas no es un estado que la tabla admita. Sin esto, un PUT que
        corrige los accesorios tumbaba la fila entera contra el `NOT NULL` de
        `fecha_recepcion`.
        """
        with self.session_factory() as session:
            i = session.get(IngresoReparacion, ingreso_id)
            if i is None:
                raise KeyError(ingreso_id)
            for campo in (
                "numero", "numero_entrega", "fecha_entrega", "retirado_por",
                "trabajo_realizado", "observaciones_entrega", "tecnico_entrega_id",
            ):
                data.pop(campo, None)
            for campo in ("fecha_recepcion", "cliente_id", "equipo_tipo"):
                if data.get(campo) is None:
                    data.pop(campo, None)
            for campo, valor in data.items():
                setattr(i, campo, valor)
            session.commit()
            session.refresh(i)
            return _to_dict(i, **self._nombres(session, i))

    def entregar(self, ingreso_id: int, usuario_actor: str | None = None,
                 **data) -> dict:
        """Devuelve el equipo y emite el comprobante de entrega.

        Idempotente **no** es: entregar dos veces daría dos números para la
        misma devolución, y el segundo papel diría algo que no pasó. Se rechaza.
        """
        from .equipos import EquipoMovimiento

        with self.session_factory() as session:
            i = session.get(IngresoReparacion, ingreso_id)
            if i is None:
                raise KeyError(ingreso_id)
            if i.fecha_entrega is not None:
                raise ValueError(
                    f"El equipo ya se entregó el "
                    f"{i.fecha_entrega.strftime('%d-%m-%Y %H:%M')} con el "
                    f"comprobante {i.numero_entrega}."
                )

            i.fecha_entrega = data.get("fecha_entrega") or datetime.now()
            i.retirado_por = data.get("retirado_por")
            i.trabajo_realizado = data.get("trabajo_realizado")
            i.observaciones_entrega = data.get("observaciones_entrega")
            i.tecnico_entrega_id = data.get("tecnico_entrega_id")
            i.numero_entrega = self._siguiente_numero(
                session, _PREFIJO_ENTREGA, IngresoReparacion.numero_entrega,
            )

            if i.equipo_id is not None:
                session.add(EquipoMovimiento(
                    equipo_id=i.equipo_id,
                    incidencia_id=i.incidencia_id,
                    tipo="entrega_reparacion",
                    descripcion=f"Entregado al cliente ({i.numero_entrega})",
                    motivo=i.trabajo_realizado,
                    usuario=usuario_actor or "Sistema",
                ))

            session.commit()
            session.refresh(i)
            return _to_dict(i, **self._nombres(session, i))

    def delete(self, ingreso_id: int) -> None:
        """Sólo si todavía no se entregó.

        Un comprobante de entrega ya emitido está **en manos del cliente**:
        borrar la fila dejaría un número correlativo apuntando a la nada, y el
        próximo reusaría ese número. Corregir una recepción se hace con
        `update`; deshacer una entrega no se hace.
        """
        with self.session_factory() as session:
            i = session.get(IngresoReparacion, ingreso_id)
            if i is None:
                raise KeyError(ingreso_id)
            if i.fecha_entrega is not None:
                raise ValueError(
                    f"No se puede borrar: ya se emitió el comprobante de entrega "
                    f"{i.numero_entrega}, que está en manos del cliente."
                )
            session.delete(i)
            session.commit()

    def datos_para_pdf(self, ingreso_id: int, *, tipo: str) -> dict | None:
        """Los datos del comprobante ya resueltos a texto, para imprimirlo.

        `tipo` es `recepcion` o `entrega`. Las etiquetas se resuelven acá y no en
        el generador por el mismo motivo que en `incidencia_pdf`: el generador
        dibuja, no decide.
        """
        with self.session_factory() as session:
            i = session.get(IngresoReparacion, ingreso_id)
            if i is None:
                return None
            if tipo == "entrega" and i.fecha_entrega is None:
                raise ValueError(
                    "Todavía no se entregó: no hay comprobante de entrega que "
                    "imprimir."
                )
            from .clientes import Cliente

            cliente = session.get(Cliente, i.cliente_id)
            datos = _to_dict(i, **self._nombres(session, i))
            datos["cliente"] = {
                "nombre": cliente.nombre if cliente else "—",
                "cuit": (cliente.cuit if cliente else None) or "",
                "domicilio": (cliente.domicilio if cliente else None) or "",
                "telefono": i.contacto_telefono or (cliente.telefono if cliente else None) or "",
                "email": (cliente.email if cliente else None) or "",
            }
            return datos
