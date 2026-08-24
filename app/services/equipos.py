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
    CheckConstraint, Date, DateTime, ForeignKey, String, Text, UniqueConstraint,
    delete, func, select, update,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base


class Equipo(Base):
    __tablename__ = "equipos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
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
    # De quien es el equipo cuando NO es del cliente: el tercero que se lo
    # alquila o se lo dio en comodato y que, en general, le provee los insumos
    # (`services/insumos.py` hereda de aca el proveedor de cada toner).
    # **NULL = es del cliente**, que es el caso normal del parque.
    #
    # No hay columna `propiedad` al lado, por lo mismo que `activos` no guarda
    # la modalidad del contrato: seria la misma verdad escrita dos veces, y el
    # dia que discrepen no hay forma de saber cual miente.
    #
    # Reusa `proveedores`, que hasta hoy solo nombraba al service. Es la misma
    # empresa del mundo real —Sistemas Junin alquila las fotocopiadoras Y
    # entrega los toner—, asi que una tabla `terceros` paralela seria el mismo
    # catalogo cargado dos veces, con "Compu Service" y "compuservice" otra vez.
    proveedor_id: Mapped[int | None] = mapped_column(
        ForeignKey("proveedores.id"), index=True,
    )
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


class EquipoReferencia(Base):
    """Como llama OTRO a este equipo.

    El caso que la motiva: el cliente le alquila fotocopiadoras a un tercero, y
    para pedirle un toner hay que darle **el numero interno de ese tercero**. Ese
    numero no es el serial —el serial esta en la etiqueta del fabricante— ni el
    patrimonial del cliente: son tres identificadores distintos para la misma
    maquina, y hasta hoy el equipo tenia lugar para uno solo.

    **Por que una tabla y no una columna `codigo_interno`**, como la que si tiene
    `activos`: una columna alcanza para el primer tercero y se rompe con el
    segundo, o con el numero patrimonial del cliente, que llega siempre. La tabla
    cuesta lo mismo y contesta las dos direcciones —*"que numero le paso a Junin
    por esta maquina"* y *"me dicen 4471, cual es"*—, que es lo unico que se le
    pide a un identificador ajeno.

    (En `activos` la columna se queda donde esta: ahi el codigo es **nuestro**,
    el que va en la etiqueta que ponemos nosotros. Si algun dia un tercero le
    pone nombre a un activo propio, esta tabla se hace polimorfica con el mismo
    XOR que ya usan `equipos_movimientos` y `equipos_reparaciones`.)

    **`UNIQUE (proveedor_id, valor)`** es la constraint que evita el error que
    justifica todo esto: dos maquinas con el mismo numero del mismo proveedor es
    como llega el toner equivocado. Con `proveedor_id` NULL —el numero del propio
    cliente— la base **no** garantiza nada, porque dos clientes distintos pueden
    repetir el patrimonial sin que eso sea un error; esa unicidad la valida el
    repositorio contra el cliente del equipo, que es el alcance en que el numero
    significa algo.
    """

    __tablename__ = "equipos_referencias"
    __table_args__ = (
        UniqueConstraint("proveedor_id", "valor", name="uq_referencia_proveedor_valor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    equipo_id: Mapped[int] = mapped_column(
        ForeignKey("equipos.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    # NULL = es el numero del propio cliente (patrimonial, inventario interno).
    proveedor_id: Mapped[int | None] = mapped_column(
        ForeignKey("proveedores.id"), index=True,
    )
    # Como se lo llama: "N° interno", "Patrimonial", "N° de contrato".
    etiqueta: Mapped[str] = mapped_column(String(100), nullable=False)
    valor: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _ref_to_dict(r: EquipoReferencia, proveedor_nombre: str | None = None) -> dict:
    return {
        "id": r.id,
        "equipo_id": r.equipo_id,
        "proveedor_id": r.proveedor_id,
        "proveedor_nombre": proveedor_nombre,
        "etiqueta": r.etiqueta,
        "valor": r.valor,
    }


def _extras(session, equipos: list[Equipo]) -> tuple[dict[int, str], dict[int, list[dict]]]:
    """El nombre del proveedor dueño y las referencias de cada equipo.

    **Dos consultas para toda la lista**, no dos por equipo: un parque de 200
    maquinas es exactamente donde el N+1 hace que la pantalla no abra, y es el
    mismo criterio con el que `_nombres_depositos` resuelve el deposito.
    """
    from .proveedores import Proveedor

    if not equipos:
        return {}, {}

    ids = [e.id for e in equipos]
    referencias = list(session.execute(
        select(EquipoReferencia)
        .where(EquipoReferencia.equipo_id.in_(ids))
        .order_by(EquipoReferencia.id)
    ).scalars())

    proveedor_ids = {e.proveedor_id for e in equipos if e.proveedor_id is not None}
    proveedor_ids |= {r.proveedor_id for r in referencias if r.proveedor_id is not None}
    nombres: dict[int, str] = {}
    if proveedor_ids:
        nombres = {
            p_id: nombre
            for p_id, nombre in session.execute(
                select(Proveedor.id, Proveedor.nombre)
                .where(Proveedor.id.in_(proveedor_ids))
            ).all()
        }

    por_equipo: dict[int, list[dict]] = {}
    for r in referencias:
        por_equipo.setdefault(r.equipo_id, []).append(
            _ref_to_dict(r, nombres.get(r.proveedor_id))
        )
    return nombres, por_equipo


def _to_dict(e: Equipo, deposito_nombre: str | None = None,
             proveedor_nombre: str | None = None,
             referencias: list[dict] | None = None) -> dict:
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
        # De quien es, si no es del cliente. Resuelto acá para que la lista no
        # cruce `/api/proveedores` sólo para escribir "es de Sistemas Junín".
        "proveedor_id": e.proveedor_id,
        "proveedor_nombre": proveedor_nombre,
        # Cómo lo llaman los demás — ver `EquipoReferencia`. Viaja con el equipo
        # y no por un endpoint aparte porque es lo primero que se busca cuando
        # hay que pedir un insumo: una segunda llamada por fila lo escondería
        # detrás de un click.
        "referencias": referencias if referencias is not None else [],
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
            return self._resolver(session, e, deposito)

    def _resolver(self, session, e: Equipo, deposito_nombre: str | None) -> dict:
        """El dict de UN equipo con el proveedor y las referencias resueltos.

        Existe para que las cinco vias que devuelven un equipo —alta, listado,
        ficha, edicion y el movimiento entre depositos— den exactamente el mismo
        JSON. Cuando cada una armaba el suyo, agregar un campo dejaba tres
        contestando lo viejo, que es como la UI termina creyendo que un equipo
        se quedo sin referencias despues de editarlo.
        """
        nombres, referencias = _extras(session, [e])
        return _to_dict(
            e, deposito_nombre, nombres.get(e.proveedor_id), referencias.get(e.id, []),
        )

    def list(self, cliente_id: int | None = None,
             deposito_id: int | None = None,
             referencia: str | None = None) -> list[dict]:
        """`referencia` busca por el numero con el que **otro** llama al equipo
        — ver `EquipoReferencia`.

        Coincidencia exacta (sin distinguir mayusculas ni espacios al borde) y
        no parcial: el numero llega dicho por telefono y entero, y un `contains`
        sobre "44" devolveria media flota. La busqueda por texto libre sobre lo
        que ya esta en pantalla la hace la tabla del frontend.
        """
        with self.session_factory() as session:
            stmt = select(Equipo).order_by(Equipo.tipo)
            if cliente_id is not None:
                stmt = stmt.where(Equipo.cliente_id == cliente_id)
            if deposito_id is not None:
                stmt = stmt.where(Equipo.deposito_id == deposito_id)
            if referencia is not None:
                stmt = stmt.where(Equipo.id.in_(
                    select(EquipoReferencia.equipo_id).where(
                        func.lower(EquipoReferencia.valor) == referencia.strip().lower()
                    )
                ))
            equipos = list(session.execute(stmt).scalars())
            depositos = _nombres_depositos(session, (e.deposito_id for e in equipos))
            nombres, referencias = _extras(session, equipos)
            return [
                _to_dict(
                    e, depositos.get(e.deposito_id), nombres.get(e.proveedor_id),
                    referencias.get(e.id, []),
                )
                for e in equipos
            ]

    def get(self, equipo_id: int) -> dict | None:
        with self.session_factory() as session:
            e = session.get(Equipo, equipo_id)
            if e is None:
                return None
            deposito = _nombres_depositos(session, [e.deposito_id]).get(e.deposito_id)
            return self._resolver(session, e, deposito)

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
            return self._resolver(session, e, deposito_actual)

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
                movidos.append(self._resolver(session, e, actual))

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
        Tampoco las referencias: un numero ajeno **es** un nombre del equipo y
        no sobrevive a que el equipo deje de existir.

        🔴 **Los insumos si entran** (2026-08-24). Cada fila dice que un
        proveedor entrego algo un dia, con su remito: es un papel, igual que un
        comprobante de ingreso. Y es el caso que a esta lista se le escapo dos
        veces —las reparaciones y los ingresos llegaron despues del metodo y
        nadie volvio a mirarlo—, asi que la tabla nueva entra el mismo dia.
        """
        from .ingresos import IngresoReparacion
        from .insumos import EquipoInsumo
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
                "insumos": session.execute(
                    select(func.count()).select_from(EquipoInsumo)
                    .where(EquipoInsumo.equipo_id == equipo_id)
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

        🔴 **Y se niega si hay comprobantes, reparaciones o insumos**
        (2026-08-09, los insumos desde el 2026-08-24).
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
            # Mismo motivo que los movimientos, y misma razon para escribirlo a
            # mano: el `ondelete="CASCADE"` declarado en `EquipoReferencia` no
            # se ejecuta nunca con el pragma de FKs apagado, y una referencia
            # huerfana es peor que un movimiento huerfano — sostiene un UNIQUE
            # que despues rechaza cargar ese mismo numero en el equipo nuevo.
            session.execute(
                delete(EquipoReferencia).where(EquipoReferencia.equipo_id == equipo_id)
            )
            session.delete(e)
            session.commit()

    # ── Referencias: como llaman los demas a este equipo ─────────────────

    def list_referencias(self, equipo_id: int) -> list[dict]:
        with self.session_factory() as session:
            e = session.get(Equipo, equipo_id)
            if e is None:
                raise KeyError(equipo_id)
            _, referencias = _extras(session, [e])
            return referencias.get(equipo_id, [])

    def crear_referencia(self, equipo_id: int, *, etiqueta: str, valor: str,
                         proveedor_id: int | None = None) -> dict:
        """Le agrega al equipo un identificador ajeno.

        El duplicado se detecta **acá y no en el `IntegrityError`** por lo mismo
        que en las reparaciones: la constraint da un 500 sin decir con qué
        chocó, y acá lo que hace falta es justamente eso — cuál es el otro
        equipo que ya tiene ese número.
        """
        from .proveedores import Proveedor

        etiqueta = (etiqueta or "").strip()
        valor = (valor or "").strip()
        if not etiqueta:
            raise ValueError("la referencia necesita una etiqueta (ej. «N° interno»)")
        if not valor:
            raise ValueError("la referencia necesita un valor")

        with self.session_factory() as session:
            e = session.get(Equipo, equipo_id)
            if e is None:
                raise KeyError(("equipo", equipo_id))
            if proveedor_id is not None and session.get(Proveedor, proveedor_id) is None:
                raise KeyError(("proveedor", proveedor_id))

            duplicado = self._duplicado(session, e, proveedor_id, valor)
            if duplicado is not None:
                raise ValueError(
                    f"«{valor}» ya identifica al equipo #{duplicado.equipo_id} "
                    "para ese mismo destinatario: dos equipos con el mismo "
                    "número es como llega el insumo equivocado."
                )

            r = EquipoReferencia(
                equipo_id=equipo_id, proveedor_id=proveedor_id,
                etiqueta=etiqueta, valor=valor,
            )
            session.add(r)
            session.commit()
            session.refresh(r)
            proveedor = (
                session.get(Proveedor, proveedor_id) if proveedor_id is not None else None
            )
            return _ref_to_dict(r, proveedor.nombre if proveedor else None)

    @staticmethod
    def _duplicado(session, equipo: Equipo, proveedor_id: int | None,
                   valor: str) -> EquipoReferencia | None:
        """El alcance en que un número ajeno tiene que ser único.

        Con proveedor, **global**: el número interno de Sistemas Junín lo lleva
        Sistemas Junín, y es el mismo aunque las máquinas estén en dos clientes
        distintos. Es lo que además garantiza el `UNIQUE` de la tabla.

        Sin proveedor —el número del propio cliente— el alcance es **ese
        cliente**: dos clientes pueden numerar su patrimonio desde 1 sin que eso
        sea un error, y por eso la base no lo puede vigilar sola. Ver el
        docstring de `EquipoReferencia`.
        """
        q = select(EquipoReferencia).where(
            func.lower(EquipoReferencia.valor) == valor.lower(),
            EquipoReferencia.equipo_id != equipo.id,
        )
        if proveedor_id is not None:
            q = q.where(EquipoReferencia.proveedor_id == proveedor_id)
        else:
            q = q.where(
                EquipoReferencia.proveedor_id.is_(None),
                EquipoReferencia.equipo_id.in_(
                    select(Equipo.id).where(Equipo.cliente_id == equipo.cliente_id)
                ),
            )
        return session.execute(q).scalars().first()

    def borrar_referencia(self, referencia_id: int) -> None:
        """Se borra y se vuelve a cargar; no hay edición.

        Son dos campos y ninguno es historia: una referencia mal tipeada es un
        error de carga, no un hecho que haya pasado. Un PUT acá sólo agregaría
        un segundo camino para escribir lo mismo.
        """
        with self.session_factory() as session:
            r = session.get(EquipoReferencia, referencia_id)
            if r is None:
                raise KeyError(referencia_id)
            session.delete(r)
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
