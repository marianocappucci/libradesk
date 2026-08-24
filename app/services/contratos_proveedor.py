"""Contratos con el PROVEEDOR — el papel que hay detrás del insumo que llega
gratis.

Fase 2 del control de consumibles (fase 1: `services/insumos.py`).

## Qué contesta que la fase 1 no podía

La fase 1 registra que un tóner se pidió, llegó y se puso. Lo que no sabía es
**por qué llegaba sin cobrar**: eso está en un contrato entre el cliente y un
tercero, y hasta ahora vivía afuera del sistema. Con esta tabla se puede
contestar:

- *"¿Este insumo lo cubre el contrato o hay que pagarlo?"* — es la pregunta que
  aparece cuando el proveedor manda una factura inesperada.
- *"¿A quién le pido?"* — el contacto de pedidos deja de estar en la cabeza del
  que atiende el teléfono.
- *"¿Hasta cuándo?"* — un contrato vencido que nadie miró es el motivo por el
  que un día dejan de mandar tóner.
- *"¿Qué máquinas cubre?"* — y cuáles del parque quedaron afuera.

## Por qué NO entra en `contratos`

`contratos` es la dirección inversa y además es el dominio de la plata: son
**nuestros** activos colocados en un cliente, con `contratos_precios`,
`contratos_cuotas`, actas y el puente a facturación. Acá el contrato es **entre
el cliente y un tercero**; nosotros lo administramos, no lo cobramos.

Meterlos en la misma tabla obligaría a filtrar en cada consulta de cuotas, de
liquidación y de facturación para no contar contratos que no son nuestros — que
es exactamente el argumento con el que `activos` se separó de `equipos`, y por
el mismo motivo: lo que se gana es que **ninguna consulta de plata necesita
saber que esta tabla existe**.

## La cobertura es una tabla aparte, con fechas

`contratos_proveedor_equipos`, igual que `contratos_equipos`: el proveedor
cambia una máquina por otra y el contrato sigue siendo el mismo. Con fechas, la
pregunta *"¿qué contrato cubría esta máquina cuando se puso ese tóner?"* tiene
respuesta; con una columna en `equipos` habría una sola verdad, la de hoy.

**Línea vigente = `fecha_baja IS NULL`**, mismo criterio derivado que usan
`equipos_reparaciones` con `fecha_retorno` y `contratos_equipos` con
`fecha_retiro`.

## El contrato NO dice de quién es el equipo

`equipos.proveedor_id` (fase 1) sigue siendo el dueño tercero, y **son dos
hechos distintos**: un contrato de service puede cubrir equipos que son
**del cliente**, y un equipo de un tercero puede no tener contrato cargado
todavía —que es el estado en el que quedó todo el parque después de la fase 1—.
Derivar uno del otro perdería los dos casos.

Por eso tampoco se valida que el proveedor del contrato sea el dueño del
equipo: que una máquina de un tercero la atienda un cuarto es raro pero
posible, y una guarda que salta en un caso legítimo termina en un operador
inventando datos para poder guardar.

## Lo que NO tiene, y es a propósito

**Ninguna columna de plata.** Ni abono mensual, ni precio por copia. El día que
haga falta, el precio de un contrato de proveedor es un egreso —dominio de
`compras`— y no una columna acá; duplicarlo sería la segunda fuente de verdad
sobre la plata que este producto ya pagó una vez con la tabla `servicios`.

**Ningún tope de copias incluidas.** El contrato real dice "10.000 copias por
mes", pero medir eso pide una lectura periódica del contador que hoy **nadie
toma**: el contador se lee al cambiar el tóner y nada más. Una columna con el
tope sin la lectura que la compare es una promesa que la primera pantalla
desmiente.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base
from .fecha import hoy

_PREFIJO_NUMERO = "CPR-"

#: Qué clase de acuerdo es. Vocabulario propio y no el de `contratos`: allá las
#: modalidades son de lo que nosotros entregamos (alquiler, comodato, préstamo,
#: leasing); acá lo que importa es **qué obliga al proveedor**.
TIPOS = ("alquiler", "comodato", "service", "mantenimiento")


class ContratoProveedor(Base):
    __tablename__ = "contratos_proveedor"
    __table_args__ = (UniqueConstraint("numero"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    #: `CPR-00000001`, correlativo propio. Misma forma que `CTR-` y `PRES-`
    #: porque es la misma clase de identificador: uno que se lee en voz alta.
    numero: Mapped[str] = mapped_column(String(50), nullable=False)
    proveedor_id: Mapped[int] = mapped_column(
        ForeignKey("proveedores.id"), nullable=False, index=True,
    )
    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id"), nullable=False, index=True,
    )
    tipo: Mapped[str] = mapped_column(String(30), nullable=False, default="alquiler")
    #: El número que le da EL PROVEEDOR al contrato — el que hay que citar
    #: cuando se lo llama. Es el mismo problema que resuelve
    #: `equipos_referencias` con las máquinas, un nivel más arriba.
    numero_externo: Mapped[str | None] = mapped_column(String(100))
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    #: NULL = sin vencimiento pactado. No es lo mismo que vencido.
    fecha_fin: Mapped[date | None] = mapped_column(Date, index=True)
    renovacion_automatica: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )
    #: Lo que el contrato obliga. `incluye_insumos` es el que contesta la
    #: pregunta que motivó todo esto; `incluye_service` existe porque el mismo
    #: papel suele cubrir las dos cosas y separarlas es lo que permite saber
    #: cuál de las dos te están incumpliendo.
    incluye_insumos: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )
    incluye_service: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )
    #: A quién se le pide. Va acá y no en `proveedores` porque es el contacto
    #: **de este contrato**: el mismo proveedor puede tener un contrato con el
    #: hospital y otro con la clínica, cada uno con su interlocutor.
    contacto_nombre: Mapped[str | None] = mapped_column(String(255))
    contacto_telefono: Mapped[str | None] = mapped_column(String(100))
    contacto_email: Mapped[str | None] = mapped_column(String(255))
    observaciones: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ContratoProveedorEquipo(Base):
    """Qué máquina cubre el contrato, y desde cuándo.

    Sin `ondelete` en `equipo_id`: un equipo con cobertura cargada no se borra
    —lo rechaza `EquipoRepository.dependencias()`—, así que no hay cascada que
    definir. En `contrato_proveedor_id` sí va CASCADE, porque una línea sin su
    contrato no describe nada; lo ejecuta el repositorio a mano, como en todo
    este producto (el pragma de FKs está apagado).
    """

    __tablename__ = "contratos_proveedor_equipos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    contrato_proveedor_id: Mapped[int] = mapped_column(
        ForeignKey("contratos_proveedor.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    equipo_id: Mapped[int] = mapped_column(
        ForeignKey("equipos.id"), nullable=False, index=True,
    )
    fecha_alta: Mapped[date] = mapped_column(Date, nullable=False)
    #: NULL = el contrato la sigue cubriendo. Ver el docstring del módulo.
    fecha_baja: Mapped[date | None] = mapped_column(Date, index=True)
    observaciones: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def vigente_al(c: ContratoProveedor, cuando: date) -> bool:
    """Si el contrato está vigente en esa fecha.

    En un solo lugar porque lo usan la lista, la ficha y el cruce con cada
    insumo — y con tres copias, el día que se agregue el preaviso una de las
    tres se queda con el criterio viejo.
    """
    if c.fecha_inicio > cuando:
        return False
    return c.fecha_fin is None or c.fecha_fin >= cuando


def _dias_para_vencer(c: ContratoProveedor, hoy_: date) -> int | None:
    """`None` si no tiene vencimiento pactado — que no es lo mismo que cero."""
    if c.fecha_fin is None:
        return None
    return (c.fecha_fin - hoy_).days


def _to_dict(c: ContratoProveedor, *, proveedor_nombre: str | None = None,
             cliente_nombre: str | None = None, equipos_vigentes: int = 0,
             hoy_: date | None = None) -> dict:
    hoy_ = hoy_ or date.fromisoformat(hoy())
    return {
        "id": c.id,
        "numero": c.numero,
        "proveedor_id": c.proveedor_id,
        "proveedor_nombre": proveedor_nombre,
        "cliente_id": c.cliente_id,
        "cliente_nombre": cliente_nombre,
        "tipo": c.tipo,
        "numero_externo": c.numero_externo,
        "fecha_inicio": c.fecha_inicio.isoformat() if c.fecha_inicio else None,
        "fecha_fin": c.fecha_fin.isoformat() if c.fecha_fin else None,
        "renovacion_automatica": bool(c.renovacion_automatica),
        "incluye_insumos": bool(c.incluye_insumos),
        "incluye_service": bool(c.incluye_service),
        "contacto_nombre": c.contacto_nombre,
        "contacto_telefono": c.contacto_telefono,
        "contacto_email": c.contacto_email,
        "observaciones": c.observaciones,
        # Derivados, nunca almacenados.
        "vigente": vigente_al(c, hoy_),
        "dias_para_vencer": _dias_para_vencer(c, hoy_),
        "equipos_vigentes": equipos_vigentes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _linea_to_dict(l: ContratoProveedorEquipo, *, equipo=None,
                   referencias: list[dict] | None = None) -> dict:
    return {
        "id": l.id,
        "contrato_proveedor_id": l.contrato_proveedor_id,
        "equipo_id": l.equipo_id,
        "equipo_descripcion": (
            " ".join(x for x in (equipo.tipo, equipo.marca, equipo.modelo) if x)
            if equipo is not None else None
        ),
        "equipo_serial": equipo.serial if equipo is not None else None,
        "equipo_sector": equipo.sector if equipo is not None else None,
        # El número con el que el proveedor llama a esa máquina, resuelto acá:
        # es el dato con el que se pide el insumo, y en la ficha del contrato es
        # justamente la columna que se lee.
        "referencias": referencias or [],
        "fecha_alta": l.fecha_alta.isoformat() if l.fecha_alta else None,
        "fecha_baja": l.fecha_baja.isoformat() if l.fecha_baja else None,
        "vigente": l.fecha_baja is None,
        "observaciones": l.observaciones,
    }


def contrato_de(session, equipo_id: int, cuando: date) -> ContratoProveedor | None:
    """El contrato que cubría ese equipo en esa fecha, si había alguno.

    **Se resuelve, no se guarda**: `equipos_insumos` no lleva
    `contrato_proveedor_id`. Guardarlo sería una segunda fuente de verdad sobre
    la cobertura, y la primera —la línea con sus fechas— ya la puede contestar
    para cualquier momento, incluido el pasado. Es el mismo criterio con el que
    la reparación de un activo saca su cliente del contrato abierto en vez de
    copiárselo.

    Delega en `cubre()` en vez de traer la misma condición escrita en SQL: la
    regla —la línea abarca la fecha **y** el contrato está vigente ese día—
    tiene que estar en un solo lugar, si no la versión de una fila y la del
    listado se separan con el primer cambio.
    """
    return cubre(coberturas_por_equipo(session, [equipo_id]), equipo_id, cuando)


def coberturas_por_equipo(session, equipo_ids) -> dict[int, list[tuple]]:
    """`{equipo_id: [(desde, hasta, contrato), ...]}` para resolver la cobertura
    de MUCHAS filas sin una consulta por fila.

    Existe para el listado de insumos, que cruza cada fila contra su contrato:
    con `contrato_de()` por renglón eso serían dos consultas por insumo, que es
    el N+1 que hace que la pantalla no abra. Acá son dos consultas para todo el
    listado y el cruce se hace en Python — mismo criterio que `_copias_previas`
    en `services/insumos.py`.
    """
    ids = {e for e in equipo_ids if e is not None}
    if not ids:
        return {}

    # Ordenadas por alta descendente: `cubre()` devuelve la primera que matchea,
    # así que este orden ES el desempate documentado —si dos contratos cubrieran
    # la misma máquina el mismo día, gana el de alta más reciente—.
    lineas = list(session.execute(
        select(ContratoProveedorEquipo)
        .where(ContratoProveedorEquipo.equipo_id.in_(ids))
        .order_by(ContratoProveedorEquipo.fecha_alta.desc(),
                  ContratoProveedorEquipo.id.desc())
    ).scalars())
    if not lineas:
        return {}

    contratos = {
        c.id: c for c in session.execute(
            select(ContratoProveedor).where(
                ContratoProveedor.id.in_({l.contrato_proveedor_id for l in lineas})
            )
        ).scalars()
    }

    por_equipo: dict[int, list[tuple]] = {}
    for l in lineas:
        c = contratos.get(l.contrato_proveedor_id)
        if c is not None:
            por_equipo.setdefault(l.equipo_id, []).append((l.fecha_alta, l.fecha_baja, c))
    return por_equipo


def cubre(coberturas: dict[int, list[tuple]], equipo_id: int,
          cuando: date) -> ContratoProveedor | None:
    """El contrato que cubría ese equipo en esa fecha, sobre el mapa ya cargado.

    La misma regla que `contrato_de()`, escrita una sola vez para las dos
    formas de preguntarla: la línea tiene que abarcar la fecha **y** el contrato
    tiene que estar vigente ese día. Un contrato vencido con la línea abierta no
    cubre nada, que es justamente el caso que hay que poder ver.
    """
    for desde, hasta, c in coberturas.get(equipo_id, []):
        if desde <= cuando and (hasta is None or hasta >= cuando) and vigente_al(c, cuando):
            return c
    return None


class ContratoProveedorRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    # ── Helpers ──────────────────────────────────────────────────────────

    def _siguiente_numero(self, session) -> str:
        """`CPR-00000001`. Mismo mecanismo que `ContratoRepository`: el máximo
        se calcula dentro de la transacción que inserta, con el `UNIQUE` de
        abajo como red."""
        ultimo = session.execute(
            select(func.max(ContratoProveedor.numero)).where(
                ContratoProveedor.numero.like(f"{_PREFIJO_NUMERO}%")
            )
        ).scalar_one_or_none()
        siguiente = 1 if not ultimo else int(ultimo.removeprefix(_PREFIJO_NUMERO)) + 1
        return f"{_PREFIJO_NUMERO}{siguiente:08d}"

    def _resolver(self, session, contratos: list[ContratoProveedor]) -> list[dict]:
        """Los dicts con proveedor, cliente y cantidad de equipos cubiertos.

        Tres consultas para toda la lista y no tres por contrato: es el mismo
        N+1 que `_extras` evita en el listado de equipos.
        """
        from .clientes import Cliente
        from .proveedores import Proveedor

        if not contratos:
            return []

        hoy_ = date.fromisoformat(hoy())
        proveedores = dict(session.execute(
            select(Proveedor.id, Proveedor.nombre)
            .where(Proveedor.id.in_({c.proveedor_id for c in contratos}))
        ).all())
        clientes = dict(session.execute(
            select(Cliente.id, Cliente.nombre)
            .where(Cliente.id.in_({c.cliente_id for c in contratos}))
        ).all())
        cubiertos = dict(session.execute(
            select(
                ContratoProveedorEquipo.contrato_proveedor_id,
                func.count(ContratoProveedorEquipo.id),
            )
            .where(
                ContratoProveedorEquipo.contrato_proveedor_id.in_(
                    [c.id for c in contratos]
                ),
                ContratoProveedorEquipo.fecha_baja.is_(None),
            )
            .group_by(ContratoProveedorEquipo.contrato_proveedor_id)
        ).all())

        return [
            _to_dict(
                c,
                proveedor_nombre=proveedores.get(c.proveedor_id),
                cliente_nombre=clientes.get(c.cliente_id),
                equipos_vigentes=cubiertos.get(c.id, 0),
                hoy_=hoy_,
            )
            for c in contratos
        ]

    # ── Lectura ──────────────────────────────────────────────────────────

    def list(self, *, cliente_id: int | None = None,
             proveedor_id: int | None = None,
             vigentes: bool | None = None) -> list[dict]:
        """Los vigentes primero y, dentro de cada grupo, el que vence antes.

        Es el orden en que se lee la pantalla: lo que hay que renovar arriba.
        El filtro `vigentes` se aplica **en Python** y no en SQL porque la
        vigencia la define `vigente_al()`, que es donde vive el criterio — un
        `WHERE` equivalente sería el mismo criterio escrito dos veces.
        """
        with self.session_factory() as session:
            q = select(ContratoProveedor)
            if cliente_id is not None:
                q = q.where(ContratoProveedor.cliente_id == cliente_id)
            if proveedor_id is not None:
                q = q.where(ContratoProveedor.proveedor_id == proveedor_id)
            contratos = list(session.execute(q).scalars())
            filas = self._resolver(session, contratos)

        if vigentes is not None:
            filas = [f for f in filas if f["vigente"] is vigentes]
        # `dias_para_vencer` en None (sin vencimiento pactado) va al final del
        # grupo: no hay nada que renovar ahí.
        filas.sort(key=lambda f: (
            not f["vigente"],
            f["dias_para_vencer"] is None,
            f["dias_para_vencer"] if f["dias_para_vencer"] is not None else 0,
        ))
        return filas

    def get(self, contrato_id: int) -> dict | None:
        with self.session_factory() as session:
            c = session.get(ContratoProveedor, contrato_id)
            if c is None:
                return None
            ficha = self._resolver(session, [c])[0]
            ficha["equipos"] = self._lineas(session, contrato_id)
            return ficha

    def _lineas(self, session, contrato_id: int) -> list[dict]:
        from .equipos import EquipoReferencia, _ref_to_dict
        from .equipos import Equipo

        lineas = list(session.execute(
            select(ContratoProveedorEquipo)
            .where(ContratoProveedorEquipo.contrato_proveedor_id == contrato_id)
            .order_by(ContratoProveedorEquipo.fecha_baja.is_not(None),
                      ContratoProveedorEquipo.fecha_alta.desc(),
                      ContratoProveedorEquipo.id.desc())
        ).scalars())
        if not lineas:
            return []

        ids = {l.equipo_id for l in lineas}
        equipos = {
            e.id: e for e in session.execute(
                select(Equipo).where(Equipo.id.in_(ids))
            ).scalars()
        }
        referencias: dict[int, list[dict]] = {}
        for r in session.execute(
            select(EquipoReferencia).where(EquipoReferencia.equipo_id.in_(ids))
        ).scalars():
            referencias.setdefault(r.equipo_id, []).append(_ref_to_dict(r))

        return [
            _linea_to_dict(
                l, equipo=equipos.get(l.equipo_id),
                referencias=referencias.get(l.equipo_id, []),
            )
            for l in lineas
        ]

    def cobertura_de_equipo(self, equipo_id: int, cuando: date | None = None) -> dict | None:
        """El contrato que cubre hoy —o en la fecha dada— a ese equipo.

        Lo consume la ficha del equipo, para decir *"cubierto por CPR-0001 hasta
        el 31-12-2026"* sin que la pantalla tenga que cruzar nada.
        """
        cuando = cuando or date.fromisoformat(hoy())
        with self.session_factory() as session:
            c = contrato_de(session, equipo_id, cuando)
            return self._resolver(session, [c])[0] if c is not None else None

    # ── Escritura ────────────────────────────────────────────────────────

    def create(self, *, proveedor_id: int, cliente_id: int, fecha_inicio: date,
               tipo: str = "alquiler", **data) -> dict:
        from .clientes import Cliente
        from .proveedores import Proveedor

        if tipo not in TIPOS:
            raise ValueError(f"tipo de contrato desconocido: {tipo!r}")

        fecha_fin = data.get("fecha_fin")
        if fecha_fin is not None and fecha_fin < fecha_inicio:
            raise ValueError("la fecha de fin es anterior a la de inicio")

        with self.session_factory() as session:
            if session.get(Proveedor, proveedor_id) is None:
                raise KeyError(("proveedor", proveedor_id))
            if session.get(Cliente, cliente_id) is None:
                raise KeyError(("cliente", cliente_id))

            c = ContratoProveedor(
                numero=self._siguiente_numero(session),
                proveedor_id=proveedor_id, cliente_id=cliente_id,
                tipo=tipo, fecha_inicio=fecha_inicio,
                **{k: v for k, v in data.items() if v is not None},
            )
            session.add(c)
            session.commit()
            session.refresh(c)
            return self._resolver(session, [c])[0]

    def update(self, contrato_id: int, **data) -> dict:
        with self.session_factory() as session:
            c = session.get(ContratoProveedor, contrato_id)
            if c is None:
                raise KeyError(contrato_id)

            if "tipo" in data and data["tipo"] not in TIPOS:
                raise ValueError(f"tipo de contrato desconocido: {data['tipo']!r}")

            for campo in (
                "tipo", "numero_externo", "fecha_inicio", "fecha_fin",
                "renovacion_automatica", "incluye_insumos", "incluye_service",
                "contacto_nombre", "contacto_telefono", "contacto_email",
                "observaciones",
            ):
                if campo in data:
                    setattr(c, campo, data[campo])

            if c.fecha_fin is not None and c.fecha_fin < c.fecha_inicio:
                raise ValueError("la fecha de fin es anterior a la de inicio")

            session.commit()
            session.refresh(c)
            return self._resolver(session, [c])[0]

    def delete(self, contrato_id: int) -> None:
        """Borra el contrato **con sus líneas de cobertura**.

        Las líneas se van con él —el `ondelete` declarado no se ejecuta, el
        pragma está apagado— porque sin el contrato no describen nada. Los
        insumos NO se tocan: son hechos que ocurrieron, y la cobertura se
        resuelve al momento de preguntarla, así que un insumo viejo simplemente
        pasa a figurar sin contrato.
        """
        from sqlalchemy import delete as sa_delete

        with self.session_factory() as session:
            c = session.get(ContratoProveedor, contrato_id)
            if c is None:
                raise KeyError(contrato_id)
            session.execute(
                sa_delete(ContratoProveedorEquipo).where(
                    ContratoProveedorEquipo.contrato_proveedor_id == contrato_id
                )
            )
            session.delete(c)
            session.commit()

    # ── Cobertura ────────────────────────────────────────────────────────

    def cubrir(self, contrato_id: int, *, equipo_id: int,
               fecha_alta: date | None = None,
               observaciones: str | None = None) -> dict:
        """Agrega una máquina al contrato.

        **Rechaza cubrir un equipo que ya está cubierto** por este u otro
        contrato en la misma fecha: dos coberturas simultáneas hacen que
        *"¿quién tiene que poner este tóner?"* tenga dos respuestas, que es
        justo la pregunta que el módulo vino a contestar. Es la misma clase de
        invariante que "una sola reparación abierta por equipo".
        """
        from .equipos import Equipo

        with self.session_factory() as session:
            c = session.get(ContratoProveedor, contrato_id)
            if c is None:
                raise KeyError(("contrato", contrato_id))
            equipo = session.get(Equipo, equipo_id)
            if equipo is None:
                raise KeyError(("equipo", equipo_id))

            desde = fecha_alta or max(c.fecha_inicio, date.fromisoformat(hoy()))
            if desde < c.fecha_inicio:
                raise ValueError(
                    "la cobertura no puede empezar antes que el contrato"
                )

            ya = contrato_de(session, equipo_id, desde)
            if ya is not None:
                raise ValueError(
                    f"ese equipo ya está cubierto por {ya.numero} en esa fecha: "
                    "dos coberturas a la vez dejan sin respuesta quién pone el "
                    "insumo"
                )

            linea = ContratoProveedorEquipo(
                contrato_proveedor_id=contrato_id, equipo_id=equipo_id,
                fecha_alta=desde, observaciones=observaciones,
            )
            session.add(linea)
            session.commit()
            session.refresh(linea)
            # Por id y no "la primera": el orden de `_lineas` es el de lectura
            # (vigentes arriba, más reciente primero) y atarse a él haría que
            # cambiar ese orden devuelva otra línea sin que nada avise.
            nueva_id = linea.id
            return next(
                l for l in self._lineas(session, contrato_id) if l["id"] == nueva_id
            )

    def retirar(self, linea_id: int, *, fecha_baja: date | None = None,
                observaciones: str | None = None) -> dict:
        """Saca la máquina del contrato. **Cierra la línea, no la borra**: que
        el contrato la haya cubierto entre marzo y agosto es lo que hace
        contestable si el tóner de junio entraba o no."""
        with self.session_factory() as session:
            linea = session.get(ContratoProveedorEquipo, linea_id)
            if linea is None:
                raise KeyError(linea_id)
            if linea.fecha_baja is not None:
                raise ValueError("esa cobertura ya está cerrada")

            hasta = fecha_baja or date.fromisoformat(hoy())
            if hasta < linea.fecha_alta:
                raise ValueError(
                    "la fecha de baja es anterior a la de alta de la cobertura"
                )
            linea.fecha_baja = hasta
            if observaciones is not None:
                linea.observaciones = observaciones
            session.commit()
            session.refresh(linea)
            contrato_id = linea.contrato_proveedor_id
            return next(
                l for l in self._lineas(session, contrato_id) if l["id"] == linea_id
            )
