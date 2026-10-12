"""Clientes: modelo SQLAlchemy + `ClienteRepository(session_factory)`, mismo
patron que `service_prices.py` de Gestiolibra.

🔴 **Desde el 2026-08-12 la tabla es `clients`, la de LibraCore** (revision
`0017`). LibraDesk era el unico producto de la familia con tabla de clientes
propia; ahora comparte la del motor, como Contalibra, Restolibra y VentaLibra.

🔴 **Desde el 2026-10-12 `Cliente` es un mapeo de SOLO LECTURA** (ADR-013): las escrituras
de `clients` van por `libracore.db.clients` (`crear_cliente`, `actualizar_cliente`,
`desactivar_cliente`, `activar_cliente`, `delete_client`), que le avisa a
`libracore.auditoria` cada cambio dentro de la misma transaccion. El modelo se queda
porque lo usan siete FK y unos veinticinco joins; ver `_cliente_es_de_solo_lectura`.

Los **atributos** siguen siendo los de este producto —`nombre`, `telefono`,
`cuit`, `domicilio`, `condicion_iva`, `fecha_creacion`— y solo cambia a que
columna real apunta cada uno. Es deliberado: los usa medio producto y el
contrato de `/api/clientes` los expone tal cual, asi que renombrarlos habria
mezclado una migracion de datos con un cambio de API que el frontend ve.
"""
from __future__ import annotations

from datetime import datetime
from functools import cache

from libracore.db import clients as motor
from libracore.db.clients import validar_cuit_no_duplicado
from sqlalchemy import Integer, String, Text, event, func, inspect, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from ..database import Base
from . import iva


class Cliente(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column("name", String(255), nullable=False)
    empresa: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    telefono: Mapped[str | None] = mapped_column("phone", String(20))
    ciudad: Mapped[str | None] = mapped_column(String(100))
    # CUIT y domicilio (2026-08-02). Hasta ahora el cliente solo tenia
    # `ciudad`, asi que los dos datos fiscales se tipeaban a mano **en cada
    # comprobante** aunque fueran siempre los mismos. Nullable porque las 9
    # filas reales de `compulibra` existen desde la migracion del Node.js
    # viejo y no los tienen — ver app/migrations.py.
    cuit: Mapped[str | None] = mapped_column("cuit_dni", String(20))
    # Decide si el comprobante muestra el IVA discriminado o el precio final.
    # **No** decide la alicuota: esa es del servicio. Ver `app/services/iva.py`.
    #
    # Nullable a proposito: los clientes que ya existen no la tienen cargada, y
    # `iva.discrimina(None)` cae a "precio final", que es lo que espera la
    # mayoria de los clientes de una mesa de ayuda. Un default de "Responsable
    # Inscripto" le habria cambiado el comprobante a todos de golpe.
    condicion_iva: Mapped[str | None] = mapped_column("iva_condition", String(50))
    domicilio: Mapped[str | None] = mapped_column("address", String(255))
    observaciones: Mapped[str | None] = mapped_column(Text)
    tipo_facturacion: Mapped[str] = mapped_column(String(20), nullable=False, default="por_servicio")
    # ── Con qué lista de precios cotiza este cliente ────────────────────
    #
    # Sin FK: `price_lists` es de LibraCommerce y la cadena de Alembic de este
    # producto no la toca. Ver la revisión `0028`.
    #
    # 🔑 **NULL = la lista por defecto**, que es cómo cotizan todos hoy. La
    # adopción es explícita: asignarle una lista a un cliente es un acto, no un
    # efecto de la migración, y ningún precio cambia por haberla corrido.
    price_list_id: Mapped[int | None] = mapped_column(Integer)
    # `Integer` y no `Boolean`: `libracore.db.clients` consulta `WHERE activo = 1`
    # y PostgreSQL no acepta un entero contra un BOOLEAN. Ver la revision `0017`.
    # `server_default` y no sólo `default`: la columna tiene el default EN LA
    # BASE (lo puso la revisión `0017`). Con sólo el default de Python, el
    # modelo describe una tabla sin default y `create_all()` la crea así — o
    # sea que el modelo y la cadena dejan de coincidir, y eso es exactamente
    # lo que mide `test_alembic_construye_lo_mismo_que_create_all`.
    activo: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # El motor la declara TEXT, no TIMESTAMP — se pierde el tipo y la precision
    # de sub-segundo, y se paga para que la tabla sea la del motor sin
    # divergencias por producto. `_to_dict` la serializa mirando el tipo.
    #
    # 🔴 **El `server_default` no es decorativo, y son dos cosas distintas.**
    #
    # 1. La columna es NOT NULL y su valor lo pone la base. Sin declarar que
    #    tiene default, SQLAlchemy la trata como una columna comun sin valor y
    #    **manda NULL explicito** en el INSERT, que viola el NOT NULL. El
    #    `IntegrityError` resultante lo cazaba el `except` del router y lo
    #    reportaba como "email duplicado" — o sea que el sintoma mandaba a
    #    buscar el problema al otro lado del producto.
    # 2. Va el literal y no un `FetchedValue()`: el modelo tiene que poder
    #    RECREAR la tabla igual a como la deja la cadena, no solo saber que la
    #    base la completa. `FetchedValue()` no emite DDL, asi que `create_all()`
    #    creaba la columna sin default y el modelo se separaba de la cadena.
    #
    # El literal es el que genera el adaptador PostgreSQL de LibraCore para su
    # `TEXT DEFAULT (datetime('now','-3 hours'))` --el `AHORA_AR` del motor--, y
    # `nullable=False` viene del `fecha_creacion TIMESTAMP ... NOT NULL` de antes
    # de la `0017`, que solo le cambio el tipo.
    #
    # 🔴 El `- interval '3 hours'` es hora de Argentina, y hasta la revision
    # `0037` este literal decia UTC: el alta de un cliente quedaba 3 h adelantada
    # como todo lo demas de la familia. Que este literal y el que deja la cadena
    # tengan que coincidir NO se cuida a mano -- lo cuida
    # `test_alembic_construye_lo_mismo_que_create_all`, que fue el que se puso
    # rojo al cambiar la revision y sin el cual esta linea se habria quedado en
    # UTC en silencio.
    fecha_creacion: Mapped[str] = mapped_column(
        "created_at", Text, nullable=False,
        server_default=text(
            "to_char((CURRENT_TIMESTAMP AT TIME ZONE 'UTC') + interval '-3 hours', "
            "'YYYY-MM-DD HH24:MI:SS')"
        ),
    )

    # --- Las dos columnas que son del motor y este producto no usa -----------
    #
    # `clients` es una tabla compartida: la revision `0017` la trajo con todo
    # lo que LibraCore le pone, incluida la cuenta corriente y el espejo de
    # LibraCommerce, que aca no se usan. Se declaran igual porque el modelo
    # tiene que describir la tabla ENTERA: si no,
    # `test_los_modelos_no_se_separan_de_la_cadena` ve columnas de mas y
    # `--autogenerate` propone **borrarlas** -- que es como se destapo esto.
    #
    # Es el costo, previsto, de compartir la tabla: una columna nueva en el
    # motor obliga a declararla aca tambien. Ver
    # `wiki/analyses/clientes-transversal-familia-libra.md`.
    auto_facturar: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    external_ref: Mapped[str | None] = mapped_column(Text)


@event.listens_for(Session, "before_flush")
def _cliente_es_de_solo_lectura(session: Session, flush_context, instances) -> None:  # noqa: ARG001
    """Un `Cliente` que llega al `flush` es un defecto, y se dice en voz alta.

    Las escrituras de `clients` van por `libracore.db.clients` (ADR-013), que es lo que
    las audita. Un `session.add(Cliente(...))` o un `cliente.nombre = ...` seguiria
    andando --el modelo escribe la tabla igual que antes-- pero **sin dejar fila en el
    log**, y un log incompleto se ve igual que uno completo: nadie se entera. Antes de
    la mudanza el listener de `libraauth` lo cubria solo; ahora lo cubre esta guarda.

    Va a nivel de `Session` (y no del `sessionmaker`) para que valga tambien para una
    sesion que arme un script o un test por su cuenta. `dirty` se filtra con
    `is_modified(include_collections=False)`: una coleccion tocada por una relacion no es
    una escritura de la fila.
    """
    tocados = [o for o in (*session.new, *session.deleted) if isinstance(o, Cliente)]
    tocados += [
        o for o in session.dirty
        if isinstance(o, Cliente) and session.is_modified(o, include_collections=False)
    ]
    if tocados:
        raise RuntimeError(
            "`Cliente` es de solo lectura: las escrituras de `clients` van por "
            "`ClienteRepository` (que usa `libracore.db.clients`) para quedar en el log de "
            "actividad. Se intento escribir por la sesion: " + ", ".join(map(repr, tocados))
        )


@cache
def columnas_por_atributo() -> dict[str, str]:
    """`{atributo del modelo: columna de clients}`, derivado del mapeo y no escrito a mano.

    Es lo que traduce la API (`nombre`, `telefono`, `cuit`...) a las columnas que escribe el
    motor (`name`, `phone`, `cuit_dni`...). Se calcula la primera vez que se pide y no al
    importar el modulo: `column_attrs` configura todos los mapeos, y a esa altura de los
    imports faltan modelos por cargar.
    """
    return {a.key: a.columns[0].name for a in inspect(Cliente).column_attrs}


def atributos_por_columna() -> dict[str, str]:
    """La inversa de `columnas_por_atributo()`: lo que necesita el registrador del log, que
    recibe columnas del motor y tiene que mostrar el vocabulario del producto."""
    return {columna: atributo for atributo, columna in columnas_por_atributo().items()}


def _to_dict(c: Cliente) -> dict:
    return {
        "id": c.id,
        "nombre": c.nombre,
        "empresa": c.empresa,
        "email": c.email,
        "telefono": c.telefono,
        "ciudad": c.ciudad,
        "cuit": c.cuit,
        "condicion_iva": c.condicion_iva,
        # Derivado, no almacenado. Va en la respuesta para que la regla de
        # quien discrimina viva en UN solo lugar: si la pantalla la reprodujera
        # comparando contra "Responsable Inscripto", agregar una condicion
        # cambiaria el PDF y no la pantalla, y nadie se enteraria hasta ver un
        # comprobante mal.
        "iva_discriminado": iva.discrimina(c.condicion_iva),
        "domicilio": c.domicilio,
        "observaciones": c.observaciones,
        "tipo_facturacion": c.tipo_facturacion,
        "price_list_id": c.price_list_id,
        # La columna es INTEGER en la base (ver el modelo) pero la API venia
        # devolviendo booleano y el frontend lo usa como tal: se convierte acá
        # para no arrastrar el detalle del motor hasta la pantalla.
        "activo": bool(c.activo),
        "fecha_creacion": _fecha_iso(c.fecha_creacion),
    }


def _fecha_iso(valor) -> str | None:
    """`created_at` del motor es TEXT (`'YYYY-MM-DD HH:MM:SS'`), no TIMESTAMP.

    Se acepta igual un `datetime` porque las filas que ya estaban se leyeron
    como tal hasta la revision `0017`, y porque un modelo mapeado a TEXT puede
    recibir cualquiera de los dos segun quien haya escrito la fila.
    """
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.isoformat()
    return str(valor).replace(" ", "T")


def _al_motor(data: dict) -> dict:
    """Traduce lo que llega de la API a lo que escribe el motor: atributos -> columnas, y
    los tipos de la API a los de la tabla.

    - Las claves son **exactamente** las recibidas, y `None` llega como `NULL`: vaciar un
      campo desde la pantalla lo deja vacio de verdad. (`update_client` del motor, en
      cambio, toma `None` por «no tocar»; por eso no se usa.)
    - `activo` es booleano en `/api/clientes` e INTEGER en `clients` desde la revision
      `0017`. Sin la conversion, psycopg adapta el `True` de Python a un `boolean` y
      PostgreSQL rechaza la escritura entera con "column activo is of type integer but
      expression is of type boolean" --lo que puso en rojo 183 tests la primera vez--.

    Va aca, en el borde del repositorio, por simetria con `_to_dict`, que hace la
    conversion inversa al salir. Un atributo que el modelo no tiene es un defecto de quien
    llama y levanta `TypeError` antes de escribir.
    """
    columnas = columnas_por_atributo()
    desconocidos = sorted(set(data) - set(columnas))
    if desconocidos:
        raise TypeError(f"Cliente no tiene los atributos: {', '.join(desconocidos)}")
    escribir = {columnas[k]: v for k, v in data.items()}
    if escribir.get("activo") is not None:
        escribir["activo"] = int(escribir["activo"])
    return escribir


class ClienteConDocumentos(Exception):
    """El motor se nego a borrar: el cliente tiene remitos o presupuestos (`delete_client`).

    Lleva el mensaje del motor, que ya dice cuantos y de que tipo. El router lo devuelve
    como 409.
    """


class ClienteRepository:
    """CRUD de clientes sobre la tabla `clients` del motor.

    🔴 **Las escrituras van por `libracore.db.clients` y las lecturas por SQLAlchemy**
    (ADR-013, 2026-10-12). Hasta entonces era al reves, y a proposito: el log de
    actividad de `libraauth` colgaba del `flush` de la sesion, y `db/clients.py` escribe
    por una conexion DB-API cruda, asi que delegarle el CRUD dejaba el alta, la edicion y
    la baja **sin auditar y sin que nadie se enterara**. Desde `libracore` v1.157.0 el
    motor le avisa cada escritura de `clients` a `libracore.auditoria`, dentro de la misma
    transaccion, y `app/main.py` le enchufa el registrador de `libraauth`
    (`registrador_dbapi`): mismo formato de log, mismo usuario, misma pantalla. Una
    escritura que se salte esto por la sesion la frena `_cliente_es_de_solo_lectura`.

    Lo que se gana de paso: el espejo en `parties` y el asiento al libro de clientes
    (`_espejar_party`, `_al_libro`) pasan a mantenerse solos en cada alta y edicion, como
    en los otros productos. La logica de CUIT duplicado ya era del motor
    (`validar_cuit_no_duplicado`) y sigue siendolo.
    """

    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def create(self, **data) -> dict:
        validar_cuit_no_duplicado(data.get("cuit"))
        return self.get(motor.crear_cliente(_al_motor(data)))

    def list(self, solo_activos: bool = False) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(Cliente).order_by(Cliente.nombre)
            if solo_activos:
                # `== 1` y no `.is_(True)`: la columna es INTEGER desde la
                # revision `0017`, y `IS TRUE` contra un entero lo rechaza
                # PostgreSQL.
                stmt = stmt.where(Cliente.activo == 1)
            return [_to_dict(c) for c in session.execute(stmt).scalars()]

    def get(self, cliente_id: int) -> dict | None:
        with self.session_factory() as session:
            c = session.get(Cliente, cliente_id)
            return _to_dict(c) if c else None

    def update(self, cliente_id: int, **data) -> dict:
        # `excluir_id`: un cliente no choca consigo mismo. Sin eso, guardarle
        # el nombre a un cliente que tiene CUIT fallaria siempre.
        if "cuit" in data:
            validar_cuit_no_duplicado(data.get("cuit"), excluir_id=cliente_id)
        # `actualizar_cliente` devuelve False si no hay un cliente con ese id (no escribe
        # ni avisa nada); con `data` vacio el motor se niega, asi que ese caso se resuelve
        # mirando si existe.
        if not data:
            cliente = self.get(cliente_id)
            if cliente is None:
                raise KeyError(cliente_id)
            return cliente
        if not motor.actualizar_cliente(cliente_id, _al_motor(data)):
            raise KeyError(cliente_id)
        return self.get(cliente_id)

    def set_activo(self, cliente_id: int, activo: bool) -> dict:
        """Baja/alta logica. **Es la operacion normal**: un cliente no se
        borra, se desactiva — igual que en Contalibra, decidido el
        2026-08-01.

        Asi el problema de los huerfanos deja de existir en vez de
        resolverse: si no hay DELETE, no hay nada que quede colgado, y
        ademas la baja es reversible.

        Se pregunta por el cliente antes porque `desactivar_cliente`/`activar_cliente` no
        distinguen un id que no existe. Dejar el cliente como esta (activar a uno activo)
        no deja fila en el log: el registrador no registra una edicion sin cambios."""
        if self.get(cliente_id) is None:
            raise KeyError(cliente_id)
        (motor.activar_cliente if activo else motor.desactivar_cliente)(cliente_id)
        return self.get(cliente_id)

    def dependencias(self, cliente_id: int) -> dict[str, int]:
        """Cuenta lo que cuelga del cliente, para poder negarse a borrarlo.

        🔴 **Esta lista tiene que estar completa, y se quedo atras dos veces.**
        Hasta el 2026-08-09 contaba equipos, incidencias y sectores — los tres
        modulos que existian cuando se escribio — y no contaba contratos,
        depositos ni comprobantes de ingreso, que llegaron despues. Un cliente
        que tuviera SOLO un contrato se borraba sin chistar y dejaba el
        contrato apuntando a un id inexistente.

        No se notaba porque el pragma `foreign_keys` esta apagado en SQLite.
        Contra PostgreSQL, tres de esas FK rechazan el borrado y **una
        (`depositos.cliente_id`) es CASCADE: borraria los depositos de
        verdad**. Lo encontro el analisis de FK del 2026-08-09, no un test:
        ningun test borraba un cliente con contratos.

        Al agregar una tabla nueva que referencie a `clientes`, **agregarla
        aca**. La medicion que encuentra los huecos esta en
        `wiki/analyses/migracion-postgresql-familia-libra.md`.
        """
        from .contratos import Contrato
        from .depositos import Deposito
        from .equipos import Equipo
        from .incidencias import Incidencia
        from .ingresos import IngresoReparacion
        from .sectores import Sector

        def _contar(session, modelo, *condiciones):
            return session.execute(
                select(func.count()).select_from(modelo).where(*condiciones)
            ).scalar_one()

        with self.session_factory() as session:
            return {
                "equipos": _contar(session, Equipo, Equipo.cliente_id == cliente_id),
                # La clave es la palabra que termina viendo el usuario en el
                # 409 de `delete_cliente` (`f"{n} {k}"`, router de clientes) —
                # "reclamos" y no "incidencias" desde la unificación de
                # vocabulario del 2026-09-13.
                "reclamos": _contar(session, Incidencia, Incidencia.cliente_id == cliente_id),
                "sectores": _contar(session, Sector, Sector.cliente_id == cliente_id),
                # Las dos columnas de `contratos`: el cliente puede ser el
                # titular o el propietario del equipamiento, y las dos son FK.
                "contratos": _contar(
                    session, Contrato,
                    (Contrato.cliente_id == cliente_id)
                    | (Contrato.propietario_cliente_id == cliente_id),
                ),
                "depositos": _contar(session, Deposito, Deposito.cliente_id == cliente_id),
                "comprobantes_de_ingreso": _contar(
                    session, IngresoReparacion, IngresoReparacion.cliente_id == cliente_id
                ),
            }

    def delete(self, cliente_id: int) -> None:
        """Borra un cliente **solo si no tiene nada colgando**.

        El router siempre declaro un `409 "cliente tiene equipos/incidencias
        asociadas"` en un `except IntegrityError`, pero **esa rama nunca se
        ejecutaba**: el engine no activa `PRAGMA foreign_keys`, asi que la
        base jamas levantaba el IntegrityError y el DELETE se llevaba puesto
        al cliente dejando equipos, incidencias y sectores apuntando a un id
        inexistente. La promesa estaba escrita en el codigo desde el dia 1 y
        no la cumplia nadie.

        Ahora el chequeo es explicito. Para dar de baja a un cliente **con**
        historial esta `set_activo`, que es el camino normal.
        """
        if self.get(cliente_id) is None:
            raise KeyError(cliente_id)

        colgando = self.dependencias(cliente_id)
        if any(colgando.values()):
            raise ValueError(colgando)

        # Los remitos y presupuestos son del motor, no de este modelo: `delete_client` los
        # cuenta y se niega (ValueError, sin escribir ni registrar nada). Ese es el unico
        # chequeo que le faltaba a `dependencias`.
        try:
            motor.delete_client(cliente_id)
        except ValueError as e:
            raise ClienteConDocumentos(str(e)) from e
