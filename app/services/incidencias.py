"""Incidencias (tickets de soporte) + `ActividadIncidencia` (log de
actividad por ticket) + `IncidenciaEstadoLog` (auditoria de cambios de
estado — 31 filas reales migradas desde Postgres). `tecnico_id`/
`sector_id` reemplazan a las columnas de texto libre `tecnico_asignado`/
`sector` que tenia la version anterior (Node.js) — la migracion de datos
(Fase 4) resuelve el texto libre contra las tablas `tecnicos`/`sectores`
donde haya coincidencia."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    delete,
    func,
    select,
    text,
    update,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base

# Sin riesgo de import circular: `materiales` no importa nada del producto,
# solo los dos motores.
from . import materiales

ESTADOS_VALIDOS = ("abierto", "en_progreso", "resuelta", "cerrado")

#: Los estados de una TAREA, que son otros y a proposito.
#:
#: El reclamo distingue `resuelta` de `cerrado` por una razon concreta:
#: `resuelta` es "el tecnico termino" y `cerrado` es "alguien controlo el
#: comprobante de servicios contra la hoja de ruta y decidio que va a
#: facturacion" -- por eso `convertir_a_remito()` solo convierte `cerrado`.
#:
#: Ese control es del reclamo entero, no de cada tarea. Heredarle el
#: vocabulario a la tarea le dejaria un estado que nunca se usa.
ESTADOS_TAREA = ("pendiente", "en_progreso", "terminada")
PRIORIDADES_VALIDAS = ("alta", "media", "baja")
# Cómo se atendió el ticket (pedido 37). `None` es un valor legítimo: los
# tickets viejos no lo saben.
MODALIDADES_VALIDAS = ("on_site", "remoto")

# Que parte del reclamo cubre el abono del cliente (2026-08-14). `None` es un
# valor legitimo y NO equivale a `fuera`: significa que nadie lo decidio
# todavia, y es lo unico que distingue "se decidio facturarlo" de "no se
# miro". Ver la revision `0024` y `convertir_a_remito()`.
COBERTURAS_ABONO = ("total", "parcial", "fuera")

# El cliente que paga un abono mensual en vez de cada trabajo. Es un valor de
# `clients.tipo_facturacion`, que existe desde la baseline.
TIPO_FACTURACION_ABONO = "mensual"

# Etiquetas legibles. Viven acá —en el dominio— y no en el generador de PDF,
# porque son cómo se llama un estado, no cómo se lo dibuja: el día que haya un
# segundo consumidor (un mail, un export) no tiene que copiarlas.
ESTADO_LABELS = {
    "abierto": "Abierta", "en_progreso": "En progreso",
    "resuelta": "Resuelta", "cerrado": "Cerrada",
}
PRIORIDAD_LABELS = {"alta": "Alta", "media": "Media", "baja": "Baja"}
MODALIDAD_LABELS = {"on_site": "On-site", "remoto": "Remoto"}


class Incidencia(Base):
    __tablename__ = "incidencias"
    __table_args__ = (
        # Generar dos veces el mismo periodo de un contrato tiene que ser
        # imposible en la base, no solo improbable en el codigo. Mismo criterio
        # que `ix_cuota_periodo_recurrente` de la revision `0025`.
        #
        # **Parcial**: deja afuera los reclamos normales, que tienen las dos
        # columnas en NULL y son todos. PostgreSQL es el unico motor de este
        # producto (guarda en `app/database.py`), asi que el indice parcial esta
        # disponible sin condiciones.
        Index(
            "ix_incidencia_visita_periodo",
            "contrato_id", "periodo_visita",
            unique=True,
            # Con `text()` y no una expresion sobre las columnas: todavia no
            # existen como atributos en este punto. Tiene que ser **igual,
            # caracter por caracter**, a la de la migracion — si difieren,
            # `alembic check` reporta el indice como cambio pendiente en cada
            # corrida.
            postgresql_where=text("periodo_visita IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id", ondelete="SET NULL"), index=True)
    # El activo alquilado sobre el que se abre el ticket, cuando el problema es
    # de un equipo NUESTRO puesto en el cliente y no del parque de el.
    #
    # Columna aparte y **sin** CHECK de exclusion mutua con `equipo_id`, a
    # diferencia de `equipos_movimientos` y `equipos_reparaciones`: alla el XOR
    # dice de quien es el historial y ninguna fila puede ser de los dos. Aca un
    # ticket puede tocar legitimamente las dos cosas —"el telefono alquilado no
    # registra en la PC del cliente"— y forzar uno solo obligaria a elegir cual
    # de los dos se pierde.
    activo_id: Mapped[int | None] = mapped_column(
        ForeignKey("activos.id", ondelete="SET NULL"), index=True,
    )
    # Los tres papeles alrededor del ticket (pedido 41, 2026-08-04). Apuntan al
    # MISMO catalogo (`tecnicos`, que es el personal de la empresa): en una
    # empresa chica la misma persona recepciona y ejecuta, y con tablas
    # separadas habria que cargarla dos veces. Ver services/tecnicos.py.
    #
    # `tecnico_id` es quien **ejecuta**, y conserva su nombre porque es la
    # columna que usan los 6 reportes, el informe al cliente y el dashboard
    # desde siempre; renombrarla ahora seria un cambio ancho sin pedido detras.
    tecnico_id: Mapped[int | None] = mapped_column(ForeignKey("tecnicos.id", ondelete="SET NULL"))
    # Quien **toma** el ticket, que puede no ser tecnico.
    recepcionista_id: Mapped[int | None] = mapped_column(
        ForeignKey("tecnicos.id", ondelete="SET NULL"), index=True,
    )
    # Quien habla con el cliente por este trabajo.
    vendedor_id: Mapped[int | None] = mapped_column(
        ForeignKey("tecnicos.id", ondelete="SET NULL"), index=True,
    )
    # `on_site` o `remoto` (pedido 37). Nullable y **sin default**: los 23
    # tickets que ya existen no saben como se atendieron, y ponerles `on_site`
    # seria inventar el dato. En pantalla salen con "—".
    modalidad: Mapped[str | None] = mapped_column(String(20), index=True)
    # La agenda (pedido 42, fase B). Nullable: agendar es opcional — un ticket
    # que entra por telefono y se resuelve en el momento nunca se agenda.
    #
    # `fecha_programada` es CUANDO se va a atender, y no tiene nada que ver con
    # `fecha_creacion` (cuando entro el ticket) ni con `fecha_cierre` (cuando se
    # termino). Sin esta columna la disponibilidad de un equipo solo podia ser
    # "esta o no esta en otro equipo"; con ella, el motor de turnos puede decir
    # si dos trabajos se pisan. Ver services/agenda.py.
    fecha_programada: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    duracion_minutos: Mapped[int | None] = mapped_column(Integer)
    # Que equipo lo hace. El vehiculo NO se guarda aca: sale de lo que ese
    # equipo tenga asignado (fase A), y duplicarlo admitiria que el ticket diga
    # una patente y el equipo otra.
    equipo_trabajo_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipos_trabajo.id", ondelete="SET NULL"), index=True,
    )
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectores.id", ondelete="SET NULL"))
    # Que clase de problema es ("Hardware -> Impresoras"). Apunta siempre a la
    # HOJA del catalogo; el padre se deriva. Nullable y sin `ondelete`: las 23
    # incidencias reales de `compulibra` son previas al catalogo, y el pragma
    # de FKs esta apagado, asi que el desenlace lo hace explicitamente
    # `CategoriaRepository.delete()`. Ver services/categorias.py y migrations.py.
    categoria_id: Mapped[int | None] = mapped_column(
        ForeignKey("categorias_incidencia.id"), index=True,
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    # El numero del talonario preimpreso de Comprobante de Servicios --el
    # papel que el tecnico completa en el lugar y el cliente firma--. Es la
    # unica llave entre esa conformidad y este ticket. String y no entero:
    # `0001-00041996` es un formato de imprenta, no una secuencia de este
    # sistema. Ver la revision `0019`.
    nro_cds: Mapped[str | None] = mapped_column(String(30), index=True)
    # Quien llamo, distinto del cliente. Texto libre porque es lo que hay: un
    # nombre de pila anotado por quien atiende el telefono.
    reclamante: Mapped[str | None] = mapped_column(String(120))
    estado: Mapped[str] = mapped_column(String(50), nullable=False, default="abierto", index=True)
    prioridad: Mapped[str] = mapped_column(String(20), nullable=False, default="media")
    horas_invertidas: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    notas: Mapped[str | None] = mapped_column(Text)
    resolucion: Mapped[str | None] = mapped_column(Text)
    estado_facturacion: Mapped[str | None] = mapped_column(String(20))
    # ── La visita de mantenimiento que generó un contrato ───────────────
    #
    # Las dos en NULL —que es como nacen los reclamos normales— significa que
    # este ticket no es una visita programada. Con las dos puestas, es la visita
    # de ESE contrato para ESE período, y el único parcial de la revisión `0027`
    # impide generar el mismo período dos veces.
    #
    # 🔑 **Una visita es una incidencia y no una entidad nueva.** Decisión del
    # humano del 2026-08-16: una incidencia ya trae agenda, hoja de ruta,
    # cuadrilla, técnico, horas, materiales, cierre con control y camino a
    # facturación. Una entidad propia obligaba a rehacer todo eso y le dejaba
    # dos bandejas al técnico.
    #
    # Sin `ondelete`: el desenlace lo hace `ContratoRepository.delete()`, igual
    # que el resto de las referencias de esta tabla — el pragma de FKs está
    # apagado en las conexiones de SQLAlchemy y los `ondelete` no corren.
    contrato_id: Mapped[int | None] = mapped_column(
        ForeignKey("contratos.id"), index=True,
    )
    periodo_visita: Mapped[date | None] = mapped_column(Date)
    # ── Qué parte de este reclamo cubre el abono del cliente ────────────
    #
    # Sólo tiene sentido si el cliente es `tipo_facturacion='mensual'`. Ver la
    # revision `0024` para el por que de las tres columnas.
    #
    # `total` = no se factura nada; `parcial` = se factura lo que las dos de
    # abajo dejan afuera; `fuera` = se factura entero. **NULL no es `fuera`**:
    # es "nadie lo decidio", y es lo que le permite a `convertir_a_remito()`
    # frenar un reclamo de cliente con abono antes de facturarlo por descuido.
    cobertura_abono: Mapped[str | None] = mapped_column(String(20))
    # Cuantas de las `horas_invertidas` entran al abono. Sólo con `parcial`.
    abono_horas_cubiertas: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # Si los materiales entran al abono o se facturan. Sólo con `parcial`.
    abono_materiales_incluidos: Mapped[bool | None] = mapped_column(Boolean)
    # El remito que se genero de este ticket, si se genero (`convertir_a_remito`).
    #
    # 🔴 **Integer pelado, SIN ForeignKey a `remitos`** — y no es un descuido.
    # `remitos` no es un modelo de SQLAlchemy: la crea el DDL crudo de
    # `remitos_presupuestos.py`, asi que no esta en `Base.metadata`. Declarar la
    # FK haria que Alembic quiera crear una referencia a una tabla que su
    # autogenerate ni siquiera ve (`app/schema.py` `include_name()` filtra por
    # `metadata.tables`). Es el mismo pozo que ya documenta
    # `remitos_presupuestos.py` para `client_id -> clients`, con los dueños al
    # reves.
    #
    # Quien sostiene la integridad es `RemitoService.delete()`, que se niega a
    # borrar un remito que una incidencia referencia — igual que ya hacia con
    # los presupuestos convertidos.
    remito_id: Mapped[int | None] = mapped_column(Integer, index=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime)


class ActividadIncidencia(Base):
    __tablename__ = "actividades_incidencia"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incidencia_id: Mapped[int] = mapped_column(ForeignKey("incidencias.id", ondelete="CASCADE"), nullable=False, index=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    descripcion: Mapped[str | None] = mapped_column(Text)
    usuario: Mapped[str | None] = mapped_column(String(100))


class IncidenciaCargo(Base):
    """Un cargo de mano de obra del reclamo: qué se cobra y cuánto.

    🔑 **El tipo es un ítem del catálogo, no un enum.** `item_id` apunta a un
    `catalog_items` de tipo `SERVICE`, así que «hora normal», «viático» y
    «traslado» son **datos y no constantes**: agregar «hora nocturna» mañana es
    cargar un ítem, sin código ni migración. Y de arrastre el precio sale de la
    lista del cliente (revisión `0028`), la alícuota del `tax_profile` y la
    descripción del nombre — todo lo resuelve el catálogo.

    **Sin cargos, el remito sale como hoy**: las `horas_invertidas` al valor
    hora. Estas filas son para lo que antes no se podía expresar —dos horas de
    trabajo *más* un viático, que no se reemplazan sino que se suman—, no para
    reemplazar el camino que ya funciona.

    Ver la revisión `0029`.
    """

    __tablename__ = "incidencias_cargos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incidencia_id: Mapped[int] = mapped_column(
        ForeignKey("incidencias.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    # Sin FK: `catalog_items` es de LibraCommerce y esta cadena no la toca.
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class IncidenciaTarea(Base):
    """Una tarea del reclamo: que hay que hacer, cuando y en que estado.

    Brecha 4 del relevamiento de Lagrace. La ficha de Integridad tiene una
    grilla `Item / Detalle Tarea / F. Inicio / F. Fin / Estado / Observacion /
    Tipo Servicio`: **N tareas por reclamo, cada una con su propio estado y sus
    propias fechas**. Es el caso normal de ellos -- se va, se diagnostica, se
    pide un repuesto, se vuelve.

    🔑 **No reemplaza a `actividades_incidencia`.** Esa tabla es un *log*: lo
    que paso, con su fecha, sin nada que cerrar. Una tarea es lo contrario: algo
    que se abre, se trabaja y se termina. Las dos conviven porque contestan
    preguntas distintas -- "que se hizo" y "que falta".

    🔑 **`item_id` es el catalogo, no un enum ni una tabla propia.** Apunta a un
    `catalog_items` de tipo `SERVICE`, igual que `IncidenciaCargo` desde la
    revision `0029`: agregar un tipo de servicio nuevo es cargar un item. Este
    producto ya tuvo una tabla `servicios` paralela al catalogo, con 43 precios
    que ningun circuito aplicaba, y la dropeo en la `0031`; una tabla de "tipos
    de tarea" seria el mismo error otra vez. Sin FK, porque `catalog_items` es
    de LibraCommerce.

    **Las fechas son `Date` y no `DateTime`** porque es lo que se vio: la grilla
    muestra `F. Inicio / F. Fin`, y el detalle con hora aparece un nivel mas
    abajo, al tildar un tecnico. Ese nivel es la brecha 5 y va en su propia
    tabla.

    Ver la revision `0033`.
    """

    __tablename__ = "incidencias_tareas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incidencia_id: Mapped[int] = mapped_column(
        ForeignKey("incidencias.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    #: La posicion en la grilla -- la columna `Item` de Integridad. No es un
    #: identificador: el id es `id`.
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    detalle: Mapped[str] = mapped_column(Text, nullable=False)
    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pendiente", index=True,
    )
    observacion: Mapped[str | None] = mapped_column(Text)
    item_id: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class IncidenciaTareaTecnico(Base):
    """Un tecnico asignado a una tarea, con su ventana de trabajo.

    Brechas 3 y 5 del relevamiento de Lagrace. Integridad lista 14 tecnicos con
    checkbox y, al tildar uno, le carga `Fecha Inicio / Hora Inicio / Fecha Fin
    / Hora Fin / Total`: varios ejecutantes por tarea, cada uno con su tramo.

    🔑 **El asignado es un `tecnico`, sin polimorfismo.** El relevamiento habia
    dejado abierto si tercerizaban --la lista mezclaba personas con lo que
    parecian empresas-- y el humano lo cerro el 2026-08-19: **son todos
    personal**.

    🔑 **`tecnico_id` es nullable con `SET NULL`**, igual que
    `incidencias.tecnico_id`: las horas son la base de lo que se cobra, asi que
    borrar a una persona del catalogo no puede borrar el trabajo que hizo.

    🔴 **No hay ninguna columna de plata, y es a proposito.** El importe se
    deriva --horas por el valor hora del catalogo, resuelto por la lista del
    cliente--. Guardarlo seria una segunda fuente de verdad al lado de
    `IncidenciaCargo`, que ya modela la mano de obra como items del catalogo.
    Este producto ya pago ese error con la tabla `servicios` paralela, dropeada
    en la revision `0031`.

    Ver la revision `0034`.
    """

    __tablename__ = "incidencias_tareas_tecnicos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tarea_id: Mapped[int] = mapped_column(
        ForeignKey("incidencias_tareas.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    tecnico_id: Mapped[int | None] = mapped_column(
        ForeignKey("tecnicos.id", ondelete="SET NULL"), index=True,
    )
    desde: Mapped[datetime | None] = mapped_column(DateTime)
    hasta: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    #: Una fila por tecnico y por tarea, que es lo que un checkbox puede
    #: expresar. Dos tramos del mismo tecnico en la misma tarea son, en el
    #: circuito relevado, **otra tarea** -- que es para lo que existe la grilla.
    __table_args__ = (
        UniqueConstraint("tarea_id", "tecnico_id", name="uq_tarea_tecnico"),
    )


class IncidenciaEstadoLog(Base):
    __tablename__ = "incidencias_estados_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incidencia_id: Mapped[int] = mapped_column(ForeignKey("incidencias.id", ondelete="CASCADE"), nullable=False, index=True)
    estado_anterior: Mapped[str | None] = mapped_column(String(50))
    estado_nuevo: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    tecnico: Mapped[str | None] = mapped_column(String(100))


def _to_dict(i: Incidencia) -> dict:
    return {
        "id": i.id,
        "cliente_id": i.cliente_id,
        "equipo_id": i.equipo_id,
        "activo_id": i.activo_id,
        "tecnico_id": i.tecnico_id,
        "recepcionista_id": i.recepcionista_id,
        "vendedor_id": i.vendedor_id,
        # 🔴 De qué contrato salió, si es una visita de mantenimiento. **Se
        # guardaban desde la revisión `0027` y no se devolvían**, así que la
        # pantalla no tenía cómo distinguir una visita preventiva de un reclamo
        # común — y el sentido de que la visita SEA una incidencia es justamente
        # que aparezca en la misma bandeja, distinguible.
        #
        # No lo agarró ningún test: los del generador leen su propia salida, y
        # el de la cobertura mira un campo que ya estaba en este dict. Lo
        # destapó ejercitar el circuito real en dev.
        "contrato_id": i.contrato_id,
        "periodo_visita": (
            i.periodo_visita.isoformat() if i.periodo_visita else None
        ),
        # Derivado, para que la pantalla no tenga que saber que "tiene contrato"
        # significa "es una visita". Si mañana un reclamo común se ata a un
        # contrato, la regla cambia acá y no en cada vista.
        "es_visita_mantenimiento": i.periodo_visita is not None,
        "modalidad": i.modalidad,
        "fecha_programada": (
            i.fecha_programada.isoformat() if i.fecha_programada else None
        ),
        "duracion_minutos": i.duracion_minutos,
        "equipo_trabajo_id": i.equipo_trabajo_id,
        "sector_id": i.sector_id,
        "categoria_id": i.categoria_id,
        "titulo": i.titulo,
        "descripcion": i.descripcion,
        "nro_cds": i.nro_cds,
        "reclamante": i.reclamante,
        "estado": i.estado,
        "prioridad": i.prioridad,
        "horas_invertidas": float(i.horas_invertidas) if i.horas_invertidas is not None else None,
        "notas": i.notas,
        "resolucion": i.resolucion,
        "estado_facturacion": i.estado_facturacion,
        "cobertura_abono": i.cobertura_abono,
        "abono_horas_cubiertas": (
            float(i.abono_horas_cubiertas)
            if i.abono_horas_cubiertas is not None else None
        ),
        "abono_materiales_incluidos": i.abono_materiales_incluidos,
        "remito_id": i.remito_id,
        "activo": i.activo,
        "fecha_creacion": i.fecha_creacion.isoformat() if i.fecha_creacion else None,
        "fecha_cierre": i.fecha_cierre.isoformat() if i.fecha_cierre else None,
    }


def _actividad_to_dict(a: ActividadIncidencia) -> dict:
    return {
        "id": a.id,
        "incidencia_id": a.incidencia_id,
        "fecha": a.fecha.isoformat() if a.fecha else None,
        "descripcion": a.descripcion,
        "usuario": a.usuario,
    }


def _estado_log_to_dict(e: IncidenciaEstadoLog) -> dict:
    return {
        "id": e.id,
        "incidencia_id": e.incidencia_id,
        "estado_anterior": e.estado_anterior,
        "estado_nuevo": e.estado_nuevo,
        "fecha": e.fecha.isoformat() if e.fecha else None,
        "tecnico": e.tecnico,
    }


def _validar_agenda(session, incidencia) -> None:
    """Delega en el motor de turnos. Import local por el ciclo: `agenda` importa
    `Incidencia` de acá para armar los turnos existentes."""
    from .agenda import validar_agenda

    validar_agenda(session, incidencia)


def _validar_modalidad(data: dict) -> None:
    """`modalidad` sí se valida, a diferencia de `estado` y `prioridad`.

    Esas dos tienen sus tuplas declaradas arriba y **nadie las usa** — vienen
    así de antes. No se retrofitean acá porque cambiar qué acepta el endpoint de
    incidencias no es lo que pedía el 37 y podría rechazar datos que hoy entran;
    queda anotado como algo a decidir aparte.
    """
    modalidad = data.get("modalidad")
    if modalidad is not None and modalidad not in MODALIDADES_VALIDAS:
        raise ValueError(f"Modalidad inválida: {modalidad}")


def _cliente_tiene_abono(session, cliente_id: int) -> bool:
    """Si el cliente paga un abono mensual en vez de cada trabajo.

    Import local, como en el resto del modulo: `clientes` no importa a
    `incidencias` y de este modo se mantiene asi.
    """
    from .clientes import Cliente

    tipo = session.execute(
        select(Cliente.tipo_facturacion).where(Cliente.id == cliente_id)
    ).scalar_one_or_none()
    return tipo == TIPO_FACTURACION_ABONO


def _validar_cobertura_abono(session, i: Incidencia) -> None:
    """Que la cobertura del abono sea coherente, y **la normaliza**.

    Se valida sobre la incidencia ya armada —no sobre el `data` que llego— por
    la misma razon que `_validar_agenda`: lo que importa es el estado que va a
    quedar, no el parche.

    ## Por que las columnas de detalle se LIMPIAN en vez de rechazarse

    Cuando la cobertura no es `parcial`, `abono_horas_cubiertas` y
    `abono_materiales_incluidos` no significan nada y se ponen en `None`.
    Rechazar la combinacion seria mas explicito y estaria mal: la pantalla
    guarda sola al salir de cada campo y manda **el objeto entero**, asi que
    pasar de "parcial, 2 horas" a "todo dentro del abono" mandaria las 2 horas
    junto con `total` sin que el usuario haya hecho nada raro. Una guarda que
    salta en uso normal es la guarda equivocada. Normalizando, la regla vive en
    un solo lugar y ningun llamador se la puede olvidar.

    Lo que si se rechaza es lo que **no** se puede resolver solo: un `parcial`
    que no dice que cubre, y horas cubiertas que no cierran contra las
    trabajadas.
    """
    if i.cobertura_abono is None:
        # Sin decision tomada tampoco hay detalle que guardar.
        i.abono_horas_cubiertas = None
        i.abono_materiales_incluidos = None
        return

    if i.cobertura_abono not in COBERTURAS_ABONO:
        raise ValueError(f"Cobertura de abono inválida: {i.cobertura_abono}")

    if not _cliente_tiene_abono(session, i.cliente_id):
        raise ValueError(
            "Este cliente no tiene abono mensual, así que un reclamo suyo no "
            "puede estar cubierto por uno. Se factura por servicio."
        )

    if i.cobertura_abono != "parcial":
        i.abono_horas_cubiertas = None
        i.abono_materiales_incluidos = None
        return

    if i.abono_horas_cubiertas is None and i.abono_materiales_incluidos is None:
        raise ValueError(
            "Una cobertura parcial tiene que decir qué cubre el abono: cuántas "
            "horas, si los materiales, o las dos cosas."
        )

    if i.abono_horas_cubiertas is None:
        return

    # `float()` en las dos: el PUT trae floats y una fila releida de la base
    # trae `Decimal`, asi que sin normalizar la misma comparacion mezcla tipos
    # segun de donde venga la incidencia.
    cubiertas = float(i.abono_horas_cubiertas)
    if cubiertas < 0:
        raise ValueError("Las horas cubiertas por el abono no pueden ser negativas.")

    # Contra las horas del ticket: cubrir 5 de 3 trabajadas no es un caso
    # raro, es un numero mal tipeado, y sin esto el remito saldria con una
    # cantidad negativa que nadie mira hasta que el cliente la reclama.
    trabajadas = float(i.horas_invertidas or 0)
    if cubiertas > trabajadas:
        raise ValueError(
            f"El abono no puede cubrir {cubiertas} horas si el reclamo tiene "
            f"{trabajadas} trabajadas."
        )


def _descripcion_del_trabajo(incidencia_id: int, titulo: str,
                             nro_cds: str | None) -> str:
    """Cómo se llama un reclamo dentro de un remito.

    **El CDS va primero.** Es el mismo criterio con el que está en el encabezado
    de la orden de trabajo: quien tiene el talonario en la mano busca por ese
    número, y si está al final del renglón hay que leer la línea entera para
    encontrarlo. Con tres trabajos en un remito, eso es la diferencia entre
    conciliar de un vistazo y no poder.

    Sin `nro_cds` la línea arranca por el ticket: un reclamo resuelto en remoto
    no tiene papel, y un "CDS —" delante entrenaría a saltear la parte que sí
    importa en los que sí lo tienen.
    """
    etiqueta = f"#{incidencia_id} {titulo}"
    return f"CDS {nro_cds} — {etiqueta}" if nro_cds else etiqueta


def _horas_facturables(trabajo: dict) -> float:
    """Las horas del reclamo que NO cubre el abono.

    Sin cobertura parcial son todas las trabajadas, que es como se comportaba
    el producto antes de que esto existiera. Con `parcial`, la resta — y nunca
    baja de cero porque `_validar_cobertura_abono` ya rechazo cubrir mas horas
    de las trabajadas; el `max` es el cinturon por si una fila vieja o un
    arreglo directo en la base burlaron esa validacion, donde una cantidad
    negativa en el remito seria una **nota de credito silenciosa**.
    """
    if trabajo["cobertura"] != "parcial":
        return trabajo["horas"]
    return max(0.0, trabajo["horas"] - trabajo["horas_cubiertas"])


def _observaciones_del_lote(trabajos: list[dict]) -> str:
    """De qué reclamos salió este remito, en una línea.

    Redundante con las descripciones **a propósito**: el PDF recorta las
    observaciones a 400 caracteres (`pdf_generator`), así que con muchos
    reclamos esta línea se corta — y los CDS siguen estando completos renglón
    por renglón, que es donde se los busca. Acá es el resumen, no la fuente.
    """
    reclamos = ", ".join(f"#{t['id']}" for t in trabajos)
    cabeza = "Generado del reclamo" if len(trabajos) == 1 else "Generado de los reclamos"
    texto = f"{cabeza} {reclamos}"
    cds = [t["nro_cds"] for t in trabajos if t["nro_cds"]]
    if cds:
        # El numero del papel firmado es lo que ata el remito a la conformidad
        # del cliente. Quien concilia despues busca por el.
        texto += f" (CDS {', '.join(cds)})"
    # Los que el abono cubre entero no aparecen en ninguna linea, asi que si no
    # se nombraran aca el remito no diria que existieron — y el reclamo si
    # apunta a el. Que este escrito es lo que hace verificable, contra el papel,
    # que no se los cobro por error.
    cubiertos = [f"#{t['id']}" for t in trabajos if t.get("cobertura") == "total"]
    if cubiertos:
        texto += f". Cubiertos por el abono, sin cargo: {', '.join(cubiertos)}"
    return texto


def _horas_entre(desde, hasta) -> float | None:
    """Las horas decimales de un tramo, o `None` si el tramo no esta completo.

    `None` y no `0.0`: un tecnico asignado al que todavia no se le cargaron las
    horas no trabajo cero horas, **no se sabe cuantas**. Devolver cero borraria
    la diferencia justo donde importa, que es el total que se va a cobrar.

    Se redondea a dos decimales porque es lo que muestra Integridad (se vio
    `0.08 h`), y hacia abajo no: 3 minutos son 0.05 h.
    """
    if desde is None or hasta is None:
        return None
    return round((hasta - desde).total_seconds() / 3600.0, 2)


def _asignacion_to_dict(a, nombres: dict, valor_hora: float | None) -> dict:
    horas = _horas_entre(a.desde, a.hasta)
    return {
        "id": a.id,
        "tarea_id": a.tarea_id,
        "tecnico_id": a.tecnico_id,
        # El tecnico borrado deja su tramo: la fila dice que alguien trabajo esas
        # horas aunque ya no este en el catalogo.
        "tecnico": nombres.get(a.tecnico_id) if a.tecnico_id else None,
        "desde": a.desde.isoformat() if a.desde else None,
        "hasta": a.hasta.isoformat() if a.hasta else None,
        "horas": horas,
        # Derivado, nunca guardado. `None` si falta el tramo o si la instancia
        # no cargo su valor hora -- que no es lo mismo que cobrar cero.
        "importe": (
            round(horas * valor_hora, 2)
            if horas is not None and valor_hora is not None else None
        ),
    }


def _tarea_to_dict(t, datos: dict) -> dict:
    """La fila como la lee la grilla. `tipo_servicio` es el NOMBRE del item.

    Se manda resuelto y no el `item_id` pelado porque la pantalla lo muestra en
    la columna `Tipo Servicio`; que lo resuelva el front obligaria a un segundo
    request por tarea.
    """
    return {
        "id": t.id,
        "incidencia_id": t.incidencia_id,
        "orden": t.orden,
        "detalle": t.detalle,
        "fecha_inicio": t.fecha_inicio.isoformat() if t.fecha_inicio else None,
        "fecha_fin": t.fecha_fin.isoformat() if t.fecha_fin else None,
        "estado": t.estado,
        "observacion": t.observacion,
        "item_id": t.item_id,
        "tipo_servicio": (
            datos.get(t.item_id, {}).get("nombre") if t.item_id else None
        ),
        # Las asignaciones viajan ADENTRO de la tarea y no en un endpoint
        # aparte: la grilla las muestra en la misma fila, y pedirlas por
        # separado seria un request por tarea.
        "tecnicos": [],
        "horas_total": None,
        "importe_total": None,
    }


def _lineas_de_cargos(trabajo: dict, cliente_id: int | None) -> list[dict]:
    """Las líneas del remito que salen de los cargos de mano de obra.

    Una por cargo, encabezada por el **N° CDS** igual que la línea de trabajo
    que reemplaza: con tres cargos en el mismo remito hay que poder leer, renglón
    por renglón, a qué visita corresponde cada uno. Es el mismo motivo por el que
    el CDS va en la descripción y no en un campo aparte.

    El nombre, el precio y la alícuota salen del **catálogo**: por eso agregar un
    tipo de cargo nuevo no toca esta función.
    """
    datos = _datos_de_items([c["item_id"] for c in trabajo["cargos"]], cliente_id)
    salida = []
    for cargo in trabajo["cargos"]:
        info = datos.get(cargo["item_id"], {})
        nombre = info.get("nombre") or f"Ítem #{cargo['item_id']}"
        salida.append({
            "description": _descripcion_del_trabajo(
                trabajo["id"], f"{nombre} — {trabajo['titulo']}",
                trabajo["nro_cds"],
            ),
            "qty": cargo["cantidad"],
            "unit_price": info.get("precio", 0.0),
            "tax_rate": info.get("iva_rate", 0.0),
        })
    return salida


def _datos_de_items(item_ids, cliente_id: int | None) -> dict:
    """`{item_id: {nombre, precio, iva_rate}}` para los ítems del catálogo.

    El precio sale de **la lista que le corresponde al cliente** y la alícuota
    del `tax_profile` del ítem: los dos vienen del catálogo, que es lo que hace
    que agregar un tipo de cargo nuevo no toque una línea de código.

    Una sola conexión para todos los ítems: un reclamo con cuatro cargos abriría
    cuatro llamando a `precios.precio_de()` una por una.
    """
    from libracore.db import core as _core

    from . import inventario, precios
    from . import iva as _iva

    unicos = {int(i) for i in item_ids if i}
    if not unicos:
        return {}

    salida = {}
    with _core.get_connection() as conn:
        repo = inventario._repo(conn)
        for item_id in unicos:
            item = repo.get_catalog_item(item_id)
            if item is None:
                # Un ítem borrado del catálogo. Se devuelve en cero, mismo
                # criterio que `materiales.valorizados()`: inventar un precio
                # sería peor y la bandeja se niega a mandar un total 0.
                salida[item_id] = {"nombre": "", "precio": 0.0,
                                   "iva_rate": float(_iva.DEFECTO)}
                continue
            salida[item_id] = {
                "nombre": item.name,
                "precio": precios._precio_con(conn, item_id, cliente_id=cliente_id),
                "iva_rate": float(inventario.alicuota_de(item)),
            }
    return salida


class IncidenciaRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def create(self, usuario_actor: str | None = None, **data) -> dict:
        _validar_modalidad(data)
        with self.session_factory() as session:
            i = Incidencia(**data)
            # Antes de la primera escritura: si el horario se pisa, el ticket no
            # se crea. Mismo criterio que el service de los activos — lo barato
            # es no empezar.
            _validar_agenda(session, i)
            _validar_cobertura_abono(session, i)
            session.add(i)
            session.flush()
            session.add(IncidenciaEstadoLog(
                incidencia_id=i.id, estado_anterior=None, estado_nuevo=i.estado,
                tecnico=usuario_actor,
            ))
            session.commit()
            session.refresh(i)
            return _to_dict(i)

    def list(self, cliente_id: int | None = None, estado: str | None = None,
             equipo_id: int | None = None, categoria_id: int | None = None,
             activo_id: int | None = None) -> list[dict]:
        """`equipo_id` es lo que hace contestable "¿cuántas veces falló
        este equipo?": el dato estaba desde la migracion, pero no habia
        forma de pedirlo — el listado solo filtraba por cliente y estado,
        asi que la unica manera era abrir incidencia por incidencia.

        `activo_id` contesta lo mismo para un equipo **nuestro** alquilado, que
        es la pregunta que decide si conviene seguir alquilandolo o darlo de
        baja."""
        with self.session_factory() as session:
            stmt = select(Incidencia).order_by(Incidencia.fecha_creacion.desc())
            if cliente_id is not None:
                stmt = stmt.where(Incidencia.cliente_id == cliente_id)
            if estado is not None:
                stmt = stmt.where(Incidencia.estado == estado)
            if equipo_id is not None:
                stmt = stmt.where(Incidencia.equipo_id == equipo_id)
            if activo_id is not None:
                stmt = stmt.where(Incidencia.activo_id == activo_id)
            if categoria_id is not None:
                stmt = stmt.where(Incidencia.categoria_id == categoria_id)
            return [_to_dict(i) for i in session.execute(stmt).scalars()]

    def get(self, incidencia_id: int) -> dict | None:
        with self.session_factory() as session:
            i = session.get(Incidencia, incidencia_id)
            return _to_dict(i) if i else None

    def datos_para_pdf(self, incidencia_id: int) -> dict | None:
        """El ticket con todo lo suyo ya resuelto a texto, para imprimirlo.

        Devuelve **datos, no PDF**: mismo corte que `informes.py` contra
        `informe_pdf.py`, que es lo que permite testear el contenido sin abrir
        un binario. Las etiquetas se resuelven acá y no en el generador porque
        son del dominio (`on_site` → "On-site"), no de la maqueta.
        """
        from .categorias import CategoriaIncidencia
        from .clientes import Cliente
        from .equipos import Equipo
        from .sectores import Sector
        from .tecnicos import Tecnico

        with self.session_factory() as session:
            i = session.get(Incidencia, incidencia_id)
            if i is None:
                return None

            cliente = session.get(Cliente, i.cliente_id)
            equipo = session.get(Equipo, i.equipo_id) if i.equipo_id else None
            sector = session.get(Sector, i.sector_id) if i.sector_id else None
            categoria = (
                session.get(CategoriaIncidencia, i.categoria_id) if i.categoria_id else None
            )

            def persona(pid: int | None) -> str | None:
                p = session.get(Tecnico, pid) if pid else None
                return p.nombre if p is not None else None

            actividad = [
                {
                    "fecha": a.fecha.strftime("%d-%m-%Y %H:%M") if a.fecha else "—",
                    "descripcion": a.descripcion,
                }
                for a in session.execute(
                    select(ActividadIncidencia)
                    .where(ActividadIncidencia.incidencia_id == incidencia_id)
                    .order_by(ActividadIncidencia.fecha, ActividadIncidencia.id)
                ).scalars()
            ]

            return {
                "id": i.id,
                "cliente": {
                    "nombre": cliente.nombre if cliente else "—",
                    "cuit": getattr(cliente, "cuit", None),
                    "domicilio": getattr(cliente, "domicilio", None),
                    "email": getattr(cliente, "email", None),
                },
                "estado_label": ESTADO_LABELS.get(i.estado, i.estado),
                "prioridad_label": PRIORIDAD_LABELS.get(i.prioridad, i.prioridad),
                "modalidad_label": MODALIDAD_LABELS.get(i.modalidad or "", "—"),
                "fecha_creacion": (
                    i.fecha_creacion.strftime("%d-%m-%Y %H:%M") if i.fecha_creacion else "—"
                ),
                "fecha_cierre": (
                    i.fecha_cierre.strftime("%d-%m-%Y %H:%M") if i.fecha_cierre else "—"
                ),
                "categoria": categoria.nombre if categoria is not None else None,
                "horas": str(i.horas_invertidas) if i.horas_invertidas is not None else None,
                "equipo": (
                    " ".join(x for x in (equipo.tipo, equipo.marca, equipo.modelo) if x)
                    if equipo is not None else None
                ),
                "sector": sector.nombre if sector is not None else None,
                "recepcionista": persona(i.recepcionista_id),
                "tecnico": persona(i.tecnico_id),
                "vendedor": persona(i.vendedor_id),
                "titulo": i.titulo,
                "descripcion": i.descripcion,
                "nro_cds": i.nro_cds,
                "reclamante": i.reclamante,
                "resolucion": i.resolucion,
                "notas": i.notas,
                "actividad": actividad,
                # Los materiales consumidos, que es la columna "Materiales
                # Utilizados" del comprobante en papel de Lagrace.
                #
                # 🔴 Se leen por `materiales.listar()` y NO por SQLAlchemy: esa
                # tabla la escribe la conexion de LibraCore, no el ORM (es lo
                # que hace atomico el par "material anotado + stock
                # descontado"). Consultarla desde esta sesion daria una lectura
                # de otra transaccion.
                #
                # Sin `incluir_devueltos`: lo que se devolvio al deposito no se
                # uso, y un comprobante que lo liste esta cobrando algo que
                # volvio.
                "materiales": materiales.listar(i.id),
            }

    def update(self, incidencia_id: int, usuario_actor: str | None = None, **data) -> dict:
        """Si `data` incluye un `estado` distinto al actual, registra el
        cambio en `IncidenciaEstadoLog` y setea `fecha_cierre` al pasar a
        `cerrado`/`resuelta` (limpia `fecha_cierre` si vuelve a abrirse)."""
        _validar_modalidad(data)
        with self.session_factory() as session:
            i = session.get(Incidencia, incidencia_id)
            if i is None:
                raise KeyError(incidencia_id)
            estado_anterior = i.estado
            for key, value in data.items():
                setattr(i, key, value)
            # Después de aplicar los cambios y **antes** del commit: se valida
            # el horario que va a quedar, no el que había. La sesión no se
            # commiteó todavía, así que si esto se planta no queda nada escrito.
            _validar_agenda(session, i)
            _validar_cobertura_abono(session, i)
            if "estado" in data and data["estado"] != estado_anterior:
                session.add(IncidenciaEstadoLog(
                    incidencia_id=i.id, estado_anterior=estado_anterior,
                    estado_nuevo=i.estado, tecnico=usuario_actor,
                ))
                if i.estado in ("resuelta", "cerrado"):
                    i.fecha_cierre = datetime.now(UTC)
                else:
                    i.fecha_cierre = None
            session.commit()
            session.refresh(i)
            return _to_dict(i)

    def agendar_varias(self, incidencia_ids: list[int], *, equipo_trabajo_id: int,
                       inicio: datetime, duracion_minutos: int | None = None,
                       traslado_minutos: int = 0) -> list[dict]:
        """Arma **una salida**: varios reclamos a la misma cuadrilla, encadenados.

        Sale del pedido del humano del 2026-08-15: *"que se puedan elegir varias
        incidencias y armar agenda en una cuadrilla con determinado vehiculo con
        tales tecnicos"*. Antes habia que abrir cada ticket y agendarlo de a uno,
        calculando los horarios a mano.

        **El vehiculo y los tecnicos NO son de la salida: son de la cuadrilla**
        (decision del humano, 2026-08-15). Elegir la cuadrilla ya elige con que
        sale y con quienes, porque eso ya vive en `vehiculos.equipo_id` y en
        `equipos_trabajo_integrantes`. Modelar una salida con su propio vehiculo
        habria sido una entidad nueva y una segunda fuente de verdad sobre lo
        mismo.

        ## Encadenadas, y por que no todas a la misma hora

        Cada parada arranca cuando termina la anterior, mas `traslado_minutos`.
        Es lo unico que **no choca contra la regla que el producto ya tiene**: la
        cuadrilla es el recurso, y dos trabajos encimados del mismo recurso son
        un `409`. Ponerlas todas a la misma hora obligaria a excepcionar esa
        regla — o sea, a admitir que una cuadrilla este en tres lugares a la vez.

        **El ORDEN de `incidencia_ids` es el orden del recorrido.** No se
        reordena por prioridad ni por cercania: quien arma la salida sabe por
        donde conviene arrancar, y adivinarlo seria cambiarle la ruta sin
        decirselo.

        ## Todo o nada

        🔴 **Se valida el bloque ENTERO antes de escribir**, que es lo que este
        metodo agrega sobre llamar N veces a `update()`. Con N llamadas sueltas,
        un choque en la parada 4 dejaria las tres primeras agendadas y las dos
        ultimas no — un estado a medias que nadie pidio y que hay que deshacer a
        mano. Aca se asignan las N sobre la sesion, se validan las N, y recien
        despues se commitea; si algo se planta, no quedo nada escrito.

        Y el chequeo **ve tambien los choques internos del bloque**: al asignar
        antes de validar, el autoflush de SQLAlchemy hace que cada parada vea a
        las otras en la consulta de la agenda del equipo. Sin eso, una duracion
        mas larga que el paso entre paradas se pisaria consigo misma y el 409
        recien aparecería en el proximo alta.
        """
        if not incidencia_ids:
            raise ValueError("No se eligió ninguna incidencia.")
        # Sin esto, mandar el mismo id dos veces daria una salida con menos
        # paradas de las que se pidieron, en silencio: el motor descarta el
        # choque de un turno consigo mismo comparando ids.
        if len(set(incidencia_ids)) != len(incidencia_ids):
            raise ValueError("Hay reclamos repetidos en la salida.")

        # El default sale de `agenda.py`, que es donde vive: una hora es lo que
        # dura una visita tipica. Import local por el mismo ciclo que
        # `_validar_agenda` — `agenda` importa `Incidencia` de este modulo.
        from .agenda import DURACION_POR_DEFECTO

        duracion = duracion_minutos or DURACION_POR_DEFECTO
        if duracion <= 0:
            raise ValueError("La duración de cada parada tiene que ser mayor a cero.")
        if traslado_minutos < 0:
            raise ValueError("El tiempo de traslado no puede ser negativo.")

        with self.session_factory() as session:
            from .equipos_trabajo import EquipoTrabajo

            if session.get(EquipoTrabajo, equipo_trabajo_id) is None:
                raise KeyError(equipo_trabajo_id)

            momento = inicio
            asignadas = []
            for incidencia_id in incidencia_ids:
                i = session.get(Incidencia, incidencia_id)
                if i is None:
                    raise KeyError(incidencia_id)
                # Un ticket cerrado no va a una hoja de ruta: la cuadrilla no
                # tiene nada que ir a hacer ahi, y ocuparia el horario de un
                # trabajo real.
                if i.estado in ("resuelta", "cerrado"):
                    raise ValueError(
                        f"El reclamo #{i.id} está {i.estado}: no se puede agendar "
                        "una visita para algo que ya se resolvió."
                    )
                i.equipo_trabajo_id = equipo_trabajo_id
                i.fecha_programada = momento
                i.duracion_minutos = duracion
                asignadas.append(i)
                momento = momento + timedelta(minutes=duracion + traslado_minutos)

            # Las N ya estan asignadas en la sesion: validarlas ahora es validar
            # el estado que va a quedar, y cada una ve a las otras.
            for i in asignadas:
                _validar_agenda(session, i)

            session.commit()
            for i in asignadas:
                session.refresh(i)
            return [_to_dict(i) for i in asignadas]

    def delete(self, incidencia_id: int) -> None:
        """Borra el ticket con su actividad y su auditoria de estado, y
        **desvincula** los movimientos de equipo que causo.

        Los `ondelete=CASCADE` declarados en los modelos **no alcanzan**:
        el engine de SQLAlchemy de LibraDesk no activa
        `PRAGMA foreign_keys` (verificado con `PRAGMA foreign_keys` sobre
        una conexion real, da 0), asi que hasta ahora un DELETE dejaba
        `actividades_incidencia` e `incidencias_estados_log` huerfanas —
        justo lo contrario de lo que dice el dialogo de confirmacion de la
        UI. Se hace explicito aca en vez de prender el pragma, que es un
        cambio de comportamiento global sobre una base de produccion y
        merece decidirse aparte.

        Los movimientos NO se borran: el equipo salio de Admision de
        verdad, y ese hecho fisico sobrevive al ticket. Solo pierden el
        link. **Lo mismo vale para las reparaciones**: el equipo estuvo en
        service, con su remito y su RMA, aunque el ticket que lo origino ya
        no exista."""
        with self.session_factory() as session:
            i = session.get(Incidencia, incidencia_id)
            if i is None:
                raise KeyError(incidencia_id)

            # Import local: `equipos` no importa a `incidencias`, y de este
            # modo se mantiene asi (sin ciclo) aunque la dependencia exista
            # en esta direccion.
            from .contratos import ContratoEquipo
            from .equipos import EquipoMovimiento
            from .ingresos import IngresoReparacion
            from .reparaciones import Reparacion

            session.execute(
                update(EquipoMovimiento)
                .where(EquipoMovimiento.incidencia_id == incidencia_id)
                .values(incidencia_id=None)
            )
            # Mismo criterio para las lineas de contrato: el equipo se
            # reemplazo de verdad ese dia, y esa historia le sobrevive al
            # ticket. Sin esto la linea quedaria apuntando a un ticket que ya
            # no existe, que es peor que no apuntar a nada.
            session.execute(
                update(ContratoEquipo)
                .where(ContratoEquipo.incidencia_id == incidencia_id)
                .values(incidencia_id=None)
            )
            session.execute(
                update(Reparacion)
                .where(Reparacion.incidencia_id == incidencia_id)
                .values(incidencia_id=None)
            )
            # Y los ingresos a reparación (pedido 43). Acá pesa más que en el
            # resto: el comprobante que quedó en manos del cliente nombra ese
            # número, así que la fila **no se puede borrar** con el ticket. Sólo
            # pierde el link.
            session.execute(
                update(IngresoReparacion)
                .where(IngresoReparacion.incidencia_id == incidencia_id)
                .values(incidencia_id=None)
            )
            session.execute(
                delete(ActividadIncidencia)
                .where(ActividadIncidencia.incidencia_id == incidencia_id)
            )
            session.execute(
                delete(IncidenciaEstadoLog)
                .where(IncidenciaEstadoLog.incidencia_id == incidencia_id)
            )
            session.delete(i)
            session.commit()

    def list_actividades(self, incidencia_id: int) -> list[dict]:
        with self.session_factory() as session:
            stmt = (
                select(ActividadIncidencia)
                .where(ActividadIncidencia.incidencia_id == incidencia_id)
                .order_by(ActividadIncidencia.fecha.desc(), ActividadIncidencia.id.desc())
            )
            return [_actividad_to_dict(a) for a in session.execute(stmt).scalars()]

    def add_actividad(self, incidencia_id: int, descripcion: str, usuario: str | None) -> dict:
        with self.session_factory() as session:
            a = ActividadIncidencia(incidencia_id=incidencia_id, descripcion=descripcion, usuario=usuario)
            session.add(a)
            session.commit()
            session.refresh(a)
            return _actividad_to_dict(a)

    def list_estado_log(self, incidencia_id: int) -> list[dict]:
        with self.session_factory() as session:
            stmt = (
                select(IncidenciaEstadoLog)
                .where(IncidenciaEstadoLog.incidencia_id == incidencia_id)
                .order_by(IncidenciaEstadoLog.fecha.desc(), IncidenciaEstadoLog.id.desc())
            )
            return [_estado_log_to_dict(e) for e in session.execute(stmt).scalars()]

    # ── Los cargos de mano de obra ──────────────────────────────────────

    def list_cargos(self, incidencia_id: int) -> list[dict]:
        """Los cargos del reclamo, con el nombre y el precio ya resueltos.

        El precio sale de **la lista del cliente de ese reclamo**, no del
        catálogo pelado: es el mismo precio con el que después va a salir en el
        remito, y verlo distinto en la pantalla que en el comprobante es cómo
        este producto ya se contradijo antes.
        """
        from . import precios

        with self.session_factory() as session:
            filas = list(session.execute(
                select(IncidenciaCargo)
                .where(IncidenciaCargo.incidencia_id == incidencia_id)
                .order_by(IncidenciaCargo.id)
            ).scalars())
            if not filas:
                return []
            inc = session.get(Incidencia, incidencia_id)
            cliente_id = inc.cliente_id if inc else None

        datos = _datos_de_items([f.item_id for f in filas], cliente_id)
        return [
            {
                "id": f.id,
                "item_id": f.item_id,
                "cantidad": float(f.cantidad),
                "nombre": datos.get(f.item_id, {}).get("nombre", f"Ítem #{f.item_id}"),
                "precio": datos.get(f.item_id, {}).get("precio", 0.0),
                "iva_rate": datos.get(f.item_id, {}).get("iva_rate", 0.0),
                "subtotal": round(
                    float(f.cantidad) * datos.get(f.item_id, {}).get("precio", 0.0), 2
                ),
            }
            for f in filas
        ]

    def add_cargo(self, incidencia_id: int, item_id: int, cantidad: float) -> dict:
        """Agrega un cargo. `cantidad` en cero o negativa no es un cargo."""
        if cantidad <= 0:
            raise ValueError("La cantidad del cargo tiene que ser mayor que cero.")
        with self.session_factory() as session:
            if session.get(Incidencia, incidencia_id) is None:
                raise KeyError(incidencia_id)
            cargo = IncidenciaCargo(
                incidencia_id=incidencia_id, item_id=int(item_id),
                cantidad=Decimal(str(cantidad)),
            )
            session.add(cargo)
            session.commit()
            cargo_id = cargo.id
        return next(c for c in self.list_cargos(incidencia_id) if c["id"] == cargo_id)

    def delete_cargo(self, cargo_id: int) -> None:
        with self.session_factory() as session:
            cargo = session.get(IncidenciaCargo, cargo_id)
            if cargo is None:
                raise KeyError(cargo_id)
            session.delete(cargo)
            session.commit()

    # ── Las tareas del reclamo ──────────────────────────────────────────

    def list_tareas(self, incidencia_id: int) -> list[dict]:
        """Las tareas del reclamo, en el orden en que se muestran.

        El nombre del tipo de servicio se resuelve aca y no en la pantalla, por
        el mismo motivo que en `list_cargos`: que la ficha y el comprobante no
        digan cosas distintas del mismo item.
        """
        with self.session_factory() as session:
            filas = list(session.execute(
                select(IncidenciaTarea)
                .where(IncidenciaTarea.incidencia_id == incidencia_id)
                .order_by(IncidenciaTarea.orden, IncidenciaTarea.id)
            ).scalars())
            if not filas:
                return []
            inc = session.get(Incidencia, incidencia_id)
            cliente_id = inc.cliente_id if inc else None

        con_item = [f.item_id for f in filas if f.item_id]
        datos = _datos_de_items(con_item, cliente_id) if con_item else {}
        tareas = [_tarea_to_dict(f, datos) for f in filas]

        asignaciones, nombres, valor_hora = self._asignaciones_de(
            [f.id for f in filas], cliente_id,
        )
        for t in tareas:
            suyas = asignaciones.get(t["id"], [])
            t["tecnicos"] = [
                _asignacion_to_dict(a, nombres, valor_hora) for a in suyas
            ]
            # 🔑 Los totales suman **sólo los tramos completos**, y son `None`
            # cuando no hay ninguno. Tratar un tramo sin cargar como cero daría
            # un total que parece cerrado y no lo está — que es exactamente el
            # número que alguien miraría antes de facturar.
            horas = [h["horas"] for h in t["tecnicos"] if h["horas"] is not None]
            importes = [i["importe"] for i in t["tecnicos"] if i["importe"] is not None]
            t["horas_total"] = round(sum(horas), 2) if horas else None
            t["importe_total"] = round(sum(importes), 2) if importes else None
        return tareas

    def _asignaciones_de(self, tarea_ids: list[int], cliente_id: int | None):
        """Las asignaciones de varias tareas, en una consulta y no N.

        Devuelve `(por_tarea, nombres, valor_hora)`. El valor hora se resuelve
        **una vez por lote** y por la lista del cliente del reclamo: es el mismo
        precio con el que la mano de obra va a salir en el remito.
        """
        if not tarea_ids:
            return {}, {}, None
        from .tecnicos import Tecnico

        with self.session_factory() as session:
            filas = list(session.execute(
                select(IncidenciaTareaTecnico)
                .where(IncidenciaTareaTecnico.tarea_id.in_(tarea_ids))
                .order_by(IncidenciaTareaTecnico.id)
            ).scalars())
            ids = {f.tecnico_id for f in filas if f.tecnico_id}
            nombres = {}
            if ids:
                nombres = {
                    t.id: t.nombre for t in session.execute(
                        select(Tecnico).where(Tecnico.id.in_(ids))
                    ).scalars()
                }

        por_tarea: dict[int, list] = {}
        for f in filas:
            por_tarea.setdefault(f.tarea_id, []).append(f)
        return por_tarea, nombres, self._valor_hora(cliente_id)

    def _valor_hora(self, cliente_id: int | None) -> float | None:
        """El precio de la hora de trabajo para ese cliente, o `None`.

        `None` es "la instancia no cargó su valor hora", que **no es cero**:
        `convertir_a_remito` ya deja la mano de obra sin precio en ese caso para
        que el operador lo complete, y la bandeja de facturación se niega a
        mandar un comprobante en cero. Inventar un número acá rompería las dos
        defensas.
        """
        from . import precios
        from .servicios_repo_catalogo import ServicioCatalogoRepository

        try:
            hora = ServicioCatalogoRepository(self.session_factory).valor_hora()
        except Exception:
            return None
        if not hora:
            return None
        return precios.precio_de(hora["id"], cliente_id=cliente_id)

    # ── Los técnicos de una tarea ───────────────────────────────────────

    def add_tecnico_a_tarea(self, tarea_id: int, tecnico_id: int,
                            desde=None, hasta=None) -> dict:
        """Asigna un técnico a la tarea. Con o sin horas: se tilda primero y se
        cargan después, que es como funciona la pantalla de Integridad."""
        from .tecnicos import Tecnico

        self._validar_tramo(desde, hasta)
        with self.session_factory() as session:
            tarea = session.get(IncidenciaTarea, tarea_id)
            if tarea is None:
                raise KeyError(tarea_id)
            if session.get(Tecnico, tecnico_id) is None:
                raise ValueError(f"No existe el técnico {tecnico_id}.")
            ya = session.execute(
                select(IncidenciaTareaTecnico).where(
                    IncidenciaTareaTecnico.tarea_id == tarea_id,
                    IncidenciaTareaTecnico.tecnico_id == tecnico_id,
                )
            ).scalar_one_or_none()
            if ya is not None:
                raise LookupError(
                    "Ese técnico ya está asignado a la tarea. Editá su tramo en "
                    "vez de agregarlo de nuevo."
                )
            fila = IncidenciaTareaTecnico(
                tarea_id=tarea_id, tecnico_id=tecnico_id, desde=desde, hasta=hasta,
            )
            session.add(fila)
            session.commit()
            incidencia_id, fila_id = tarea.incidencia_id, fila.id
        return self._asignacion(incidencia_id, tarea_id, fila_id)

    def update_tecnico_de_tarea(self, asignacion_id: int, **data) -> dict:
        """Carga o corrige el tramo de un técnico ya asignado."""
        with self.session_factory() as session:
            fila = session.get(IncidenciaTareaTecnico, asignacion_id)
            if fila is None:
                raise KeyError(asignacion_id)
            desde = data.get("desde", fila.desde)
            hasta = data.get("hasta", fila.hasta)
            self._validar_tramo(desde, hasta)
            for campo, valor in data.items():
                setattr(fila, campo, valor)
            session.commit()
            tarea = session.get(IncidenciaTarea, fila.tarea_id)
            incidencia_id, tarea_id = tarea.incidencia_id, fila.tarea_id
        return self._asignacion(incidencia_id, tarea_id, asignacion_id)

    def delete_tecnico_de_tarea(self, asignacion_id: int) -> None:
        with self.session_factory() as session:
            fila = session.get(IncidenciaTareaTecnico, asignacion_id)
            if fila is None:
                raise KeyError(asignacion_id)
            session.delete(fila)
            session.commit()

    def _asignacion(self, incidencia_id: int, tarea_id: int, asignacion_id: int) -> dict:
        """Relee la asignación por el mismo camino que la lista, para que la
        pantalla reciba exactamente la fila que va a mostrar --con el nombre del
        técnico, las horas y el importe ya resueltos--."""
        for t in self.list_tareas(incidencia_id):
            if t["id"] == tarea_id:
                return next(a for a in t["tecnicos"] if a["id"] == asignacion_id)
        raise KeyError(asignacion_id)

    @staticmethod
    def _validar_tramo(desde, hasta) -> None:
        if desde and hasta and hasta < desde:
            raise ValueError(
                "El fin del tramo no puede ser anterior a su inicio."
            )

    def add_tarea(self, incidencia_id: int, **data) -> dict:
        """Agrega una tarea al final de la grilla.

        `orden` no se recibe: lo pone el repositorio como el siguiente de la
        lista. Dejarlo entrar por la API admitiria dos tareas en la misma
        posicion, que es justo lo que la columna existe para evitar.
        """
        self._validar_tarea(data)
        with self.session_factory() as session:
            if session.get(Incidencia, incidencia_id) is None:
                raise KeyError(incidencia_id)
            ultimo = session.execute(
                select(func.max(IncidenciaTarea.orden))
                .where(IncidenciaTarea.incidencia_id == incidencia_id)
            ).scalar()
            tarea = IncidenciaTarea(
                incidencia_id=incidencia_id,
                orden=(ultimo or 0) + 1,
                detalle=data["detalle"],
                fecha_inicio=data.get("fecha_inicio"),
                fecha_fin=data.get("fecha_fin"),
                estado=data.get("estado") or "pendiente",
                observacion=data.get("observacion"),
                item_id=data.get("item_id"),
            )
            session.add(tarea)
            session.commit()
            tarea_id = tarea.id
        return next(t for t in self.list_tareas(incidencia_id) if t["id"] == tarea_id)

    def update_tarea(self, tarea_id: int, **data) -> dict:
        """Edita una tarea. Se le pasan solo los campos que cambian."""
        with self.session_factory() as session:
            tarea = session.get(IncidenciaTarea, tarea_id)
            if tarea is None:
                raise KeyError(tarea_id)
            fusion = {
                "detalle": tarea.detalle,
                "estado": tarea.estado,
                "fecha_inicio": tarea.fecha_inicio,
                "fecha_fin": tarea.fecha_fin,
                **data,
            }
            self._validar_tarea(fusion)
            for campo, valor in data.items():
                setattr(tarea, campo, valor)
            session.commit()
            incidencia_id = tarea.incidencia_id
        return next(t for t in self.list_tareas(incidencia_id) if t["id"] == tarea_id)

    def delete_tarea(self, tarea_id: int) -> None:
        """Borra la tarea y **recompacta el orden** de las que quedan.

        Sin esto la grilla queda con huecos (1, 2, 4) y la proxima que se
        agregue toma un numero que ya se vio, porque el siguiente sale del
        maximo. El hueco no rompe nada, pero la columna `Item` es lo que el
        usuario lee para decir "la tres".
        """
        with self.session_factory() as session:
            tarea = session.get(IncidenciaTarea, tarea_id)
            if tarea is None:
                raise KeyError(tarea_id)
            incidencia_id = tarea.incidencia_id
            session.delete(tarea)
            session.flush()
            quedan = session.execute(
                select(IncidenciaTarea)
                .where(IncidenciaTarea.incidencia_id == incidencia_id)
                .order_by(IncidenciaTarea.orden, IncidenciaTarea.id)
            ).scalars()
            for posicion, t in enumerate(quedan, start=1):
                t.orden = posicion
            session.commit()

    @staticmethod
    def _validar_tarea(data: dict) -> None:
        if not (data.get("detalle") or "").strip():
            raise ValueError("La tarea necesita un detalle.")
        estado = data.get("estado") or "pendiente"
        if estado not in ESTADOS_TAREA:
            raise ValueError(
                f"Estado de tarea invalido: {estado!r}. "
                f"Los validos son {', '.join(ESTADOS_TAREA)}."
            )
        desde, hasta = data.get("fecha_inicio"), data.get("fecha_fin")
        if desde and hasta and hasta < desde:
            raise ValueError(
                "La fecha de fin de la tarea no puede ser anterior a la de inicio."
            )

    def convertir_a_remito(self, incidencia_ids: list[int], remitos, clientes,
                           servicios, usuario_id: int | None = None) -> dict:
        """Genera **un** remito por los reclamos **cerrados** que se le pasen.

        Es el camino a facturacion de un reclamo, y es el mismo que el de un
        presupuesto aceptado: LibraDesk manda a facturar **solo remitos**,
        porque lo que habilita a facturar es la entrega hecha (ver
        `app/routers/facturacion.py`). Sin esto, un trabajo por servicio no
        tenia como llegar a la bandeja.

        **Recibe una lista y no un id**, aunque el 90% de las veces traiga uno.
        El caso real es el otro: a un cliente se le hacen tres visitas en el mes
        y se le emite **un** remito por las tres, porque es una factura la que
        va a salir de ahi. Con un solo camino no hay dos formas de armar un
        remito que puedan divergir --el de a uno es este con la lista de largo
        1--, que es como el producto termino con el mismo defecto en tres
        pantallas la ultima vez.

        **Solo `cerrado`, no `resuelta`.** Es donde cae en el circuito real de
        [[lagrace-comunicaciones]]: el tecnico trae el comprobante de servicios
        en papel, alguien lo controla contra la hoja de ruta y recien ahi lo
        cierra "decidiendo si va a facturacion". Un ticket `resuelta` todavia no
        paso ese control.

        **Todos del mismo cliente**: un remito se emite a nombre de uno solo.

        **Idempotente por lote**: si TODOS los elegidos ya apuntan al MISMO
        remito, devuelve ese --el doble click--. Una mezcla de remitados y no
        remitados es un error, no una idempotencia: devolver el remito viejo
        dejaria a los nuevos sin facturar y sin decirlo.

        ## Que lleva el remito

        - **Una linea de trabajo por reclamo**, encabezada por el **N° CDS** del
          comprobante en papel cuando lo tiene. Ese numero es lo unico que ata
          la conformidad firmada con el ticket del sistema, y con tres trabajos
          en el mismo remito no alcanza con ponerlo en las observaciones: hay
          que poder leer, renglon por renglon, cual es cual. `qty` son las horas
          invertidas si estan cargadas, y `1` si no --un reclamo se cobra por
          hora o como visita, y las dos formas entran en la misma linea--.
        - **Los materiales de cada reclamo debajo de su trabajo**, al precio de
          venta del catalogo (`materiales.valorizados`), con el reclamo del que
          salieron dicho en la linea.

        El PDF del remito **no imprime precios** (`_draw_items_table` con
        `show_prices=False`): lo que se lee en el papel es la descripcion y la
        cantidad. Por eso el CDS va en la descripcion y no en un campo aparte.

        🔴 **Los precios pueden salir en cero, y esta bien.** El valor hora sale
        del catalogo de servicios (`ServicioCatalogoRepository.valor_hora`) y puede
        estar marcado todavia; un material sin `default_sale_price` tampoco
        tiene precio. El remito nace con los importes que el sistema **sabe**, y
        el operador completa el resto editandolo; inventar un numero seria peor.
        Lo que cierra el circuito es que la bandeja de facturacion **se niega a
        mandar un remito con total 0**, asi que un olvido no llega a facturarse.

        ## Lo que NO es atomico

        El remito lo escribe la conexion de LibraCore y el vinculo lo escribe
        SQLAlchemy: son dos conexiones, asi que no hay una transaccion que las
        cubra (mismo problema que documenta `materiales.py`). Si el proceso se
        cae entre las dos, queda un remito emitido sin vinculo y el proximo
        intento genera un segundo remito por los mismos tickets. Se elige este
        orden --primero el remito, despues el vinculo-- porque el error al
        reves es peor: un ticket que dice "ya se remitio" apuntando a un remito
        que no existe deja el trabajo sin poder facturarse nunca.

        El vinculo de los N si es una sola sentencia (`UPDATE ... WHERE id IN`),
        asi que no hay un estado intermedio donde la mitad del lote quedo atada
        al remito y la otra mitad no.
        """
        from . import fecha, materiales
        from .remitos_presupuestos import datos_cliente_para_comprobante

        # Sin repetidos y en el orden en que los eligieron: el remito se lee en
        # el mismo orden en que la pantalla los mostraba. `dict.fromkeys` es la
        # forma corta de deduplicar conservando el orden; un `set` lo perderia y
        # el remito saldria con los trabajos barajados.
        ids = list(dict.fromkeys(incidencia_ids))
        if not ids:
            raise ValueError("No se eligio ningun reclamo.")

        with self.session_factory() as session:
            filas = {
                i.id: i for i in session.execute(
                    select(Incidencia).where(Incidencia.id.in_(ids))
                ).scalars()
            }
            faltantes = [x for x in ids if x not in filas]
            if faltantes:
                raise KeyError(faltantes[0] if len(faltantes) == 1 else tuple(faltantes))

            # ── Idempotencia del LOTE, no de cada reclamo ────────────────
            #
            # Con uno solo alcanzaba con "si ya tiene remito, devolvelo". Con
            # varios hay un caso que no existia: **algunos** ya remitados y
            # otros no. Devolver el remito viejo dejaria a los nuevos sin
            # facturar --y en silencio--, asi que solo se devuelve el existente
            # cuando TODOS apuntan al MISMO remito, que es lo que produce un
            # doble click. Cualquier mezcla es un error que hay que ver.
            remitados = {x: filas[x].remito_id for x in ids if filas[x].remito_id}
            if remitados:
                unicos = set(remitados.values())
                if len(remitados) == len(ids) and len(unicos) == 1:
                    existente = remitos.get(next(iter(unicos)))
                    if existente is not None:
                        return existente
                    # El remito que se referenciaba no esta: se borro por fuera.
                    # Se sigue de largo y se genera uno nuevo en vez de devolver
                    # None, que dejaria a los tickets sin camino a facturacion.
                else:
                    cuales = ", ".join(f"#{x}" for x in sorted(remitados))
                    raise ValueError(
                        f"Ya tienen remito: {cuales}. Sacalos de la seleccion o "
                        f"emiti el remito de los que faltan."
                    )

            # ── Un remito se emite a nombre de UN cliente ────────────────
            #
            # Antes que el estado: es el error estructural. Que ademas alguno no
            # este cerrado no cambia que el lote no puede existir.
            clientes_del_lote = {filas[x].cliente_id for x in ids}
            if len(clientes_del_lote) > 1:
                raise ValueError(
                    "Los reclamos elegidos son de mas de un cliente y un remito "
                    "se emite a nombre de uno solo."
                )

            # **Solo `cerrado`, no `resuelta`** — ver el docstring.
            abiertos = [x for x in ids if filas[x].estado != "cerrado"]
            if abiertos:
                detalle = ", ".join(
                    f"#{x} («{filas[x].estado}»)" for x in sorted(abiertos)
                )
                raise ValueError(
                    f"Solo se genera el remito de reclamos cerrados, y estos no "
                    f"lo estan: {detalle}."
                )

            cliente_id = clientes_del_lote.pop()

            # ── Lo que el abono cubre no se factura ──────────────────────
            #
            # Antes se emitia el remito sin mirar `tipo_facturacion`, mientras
            # `reportes.facturacion()` ya excluia a estos clientes con la regla
            # escrita: "a los `mensual` se les factura el abono, no la
            # incidencia". Dos modulos del mismo producto con criterios
            # opuestos sobre el mismo cliente.
            #
            # La guarda no es "no se puede remitar a un cliente con abono":
            # eso dejaria sin facturar lo que **si** cae afuera del abono
            # --materiales, horas de excedente-- que es justo lo que hay que
            # poder cobrar. Es "hay que haber decidido que parte entra".
            if _cliente_tiene_abono(session, cliente_id):
                sin_decidir = [x for x in ids if filas[x].cobertura_abono is None]
                if sin_decidir:
                    detalle = ", ".join(f"#{x}" for x in sorted(sin_decidir))
                    raise ValueError(
                        f"Este cliente tiene abono mensual y estos reclamos no "
                        f"dicen todavia que parte cubre: {detalle}. Abrilos y "
                        f"elegi si van por dentro del abono, por fuera o "
                        f"parcial."
                    )
                if all(filas[x].cobertura_abono == "total" for x in ids):
                    detalle = ", ".join(f"#{x}" for x in sorted(ids))
                    raise ValueError(
                        f"El abono cubre por completo {detalle}, asi que no hay "
                        f"nada para facturar en un remito."
                    )

            cliente = clientes.get(cliente_id)
            if cliente is None:
                raise ValueError(
                    "Los reclamos elegidos apuntan a un cliente que ya no existe, "
                    "asi que no hay a nombre de quien emitir el remito."
                )
            # Copia de lo que se necesita afuera de la sesion: los materiales se
            # leen por la conexion de LibraCore, no por esta.
            trabajos = [
                {
                    "id": x,
                    "titulo": filas[x].titulo,
                    "nro_cds": filas[x].nro_cds,
                    "horas": float(filas[x].horas_invertidas) if filas[x].horas_invertidas else 0.0,
                    "cobertura": filas[x].cobertura_abono,
                    "horas_cubiertas": (
                        float(filas[x].abono_horas_cubiertas)
                        if filas[x].abono_horas_cubiertas else 0.0
                    ),
                    "materiales_al_abono": bool(filas[x].abono_materiales_incluidos),
                }
                for x in ids
            ]
            # Los cargos de mano de obra declarados, por reclamo. Se leen dentro
            # de la misma sesión que ya está abierta.
            cargos_por_ticket = {x: [] for x in ids}
            for c in session.execute(
                select(IncidenciaCargo)
                .where(IncidenciaCargo.incidencia_id.in_(ids))
                .order_by(IncidenciaCargo.id)
            ).scalars():
                cargos_por_ticket[c.incidencia_id].append(
                    {"item_id": c.item_id, "cantidad": float(c.cantidad)}
                )
            for t in trabajos:
                t["cargos"] = cargos_por_ticket.get(t["id"], [])

        # El valor hora del catalogo, o `None` si nadie lo marco todavia. Se
        # pide UNA vez para todo el lote: no puede pasar que dos lineas del
        # mismo remito coticen la hora distinto.
        valor_hora = servicios.valor_hora()

        items: list[dict] = []
        for t in trabajos:
            # Cubierto por completo: no aporta ninguna linea. **Igual se
            # vincula al remito** mas abajo, y las observaciones lo nombran —
            # ver `_observaciones_del_lote`. Dejarlo suelto seria peor: podria
            # remitarse otra vez despues, ahora si cobrandolo.
            if t["cobertura"] == "total":
                continue

            horas_facturables = _horas_facturables(t)
            # Con `parcial`, cero horas facturables significa que la visita
            # entera la cubre el abono y lo unico que se cobra son los
            # materiales. **Sin este corte caeria en el `else 1` de abajo** y
            # el remito cobraria una visita que el abono ya paga — que es
            # exactamente el doble cobro que esta guarda viene a impedir.
            visita_cubierta = t["cobertura"] == "parcial" and horas_facturables <= 0
            if not visita_cubierta:
                # ── Los cargos declarados mandan sobre el valor hora ──────
                #
                # Un reclamo con cargos cobra **lo que dicen sus cargos**: dos
                # horas de trabajo, un viatico y el traslado son tres lineas
                # distintas, y el viatico no reemplaza a las horas — se suma.
                #
                # 🔑 **Sin cargos sale exactamente como salia**: las
                # `horas_invertidas` al valor hora, en una sola linea. Es lo que
                # hace que ningun ticket existente cambie de precio y que la
                # visita normal siga siendo un click.
                if t["cargos"]:
                    items.extend(_lineas_de_cargos(t, cliente_id))
                else:
                    linea = {
                        "description": _descripcion_del_trabajo(
                            t["id"], t["titulo"], t["nro_cds"],
                        ),
                        # Sin horas cargadas la linea vale 1: es una visita, no cero
                        # trabajo. Un `qty` en 0 haria un remito que no cobra nada por el
                        # trabajo aunque le pongan precio.
                        "qty": horas_facturables if horas_facturables > 0 else 1,
                        "unit_price": float(valor_hora["precio"]) if valor_hora else 0,
                    }
                    if valor_hora:
                        # La alicuota del servicio, no la del documento: el valor hora
                        # es una linea del catalogo y trae la suya.
                        linea["tax_rate"] = float(valor_hora["iva_rate"])
                    items.append(linea)
            # Los materiales del reclamo, salvo que el abono los cubra.
            if t["cobertura"] == "parcial" and t["materiales_al_abono"]:
                continue
            # Los materiales de ESTE reclamo, debajo de su trabajo. Agrupado por
            # ticket y no todo el trabajo primero: el remito se lee como la
            # lista de visitas que es, y quien concilia contra los papeles va
            # bajando de a un CDS por vez.
            # Con el `cliente_id`: los materiales se valorizan por **la lista de
            # precios de ese cliente**, no por el catálogo pelado (2026-08-16).
            # Un reseller y un cliente de mostrador dejan de pagar lo mismo por
            # el mismo cable. Ver `app/services/precios.py`.
            for m in materiales.valorizados(t["id"], cliente_id=cliente_id):
                nombre = m["descripcion"] or f"Material #{m['item_id']}"
                items.append({
                    # El `\n` no es cosmetico: `_draw_items_table` de LibraCore
                    # parte la descripcion ahi y dibuja la segunda linea en
                    # italica chica, asi que el reclamo del que salio el
                    # material queda dicho sin robarle lugar al nombre.
                    "description": f"{nombre}\nReclamo #{t['id']}",
                    "qty": m["cantidad"],
                    "unit_price": m["precio"],
                })

        # Puede pasar sin que ningun reclamo sea `total`: un `parcial` que cubre
        # todas las horas y ademas los materiales es un `total` escrito de otra
        # forma. Un remito sin lineas seria un comprobante en blanco que la
        # bandeja despues rechaza por total 0, mucho mas lejos del error.
        if not items:
            raise ValueError(
                "El abono cubre todo lo que traen estos reclamos, asi que el "
                "remito saldria sin una sola linea."
            )

        remito = remitos.create(
            # `fecha.hoy()` y no `fecha_cierre`: el cierre se guarda en UTC
            # (`update()` usa `datetime.now(timezone.utc)`), asi que un ticket
            # cerrado a las 22:00 de Chivilcoy daria un remito fechado al dia
            # siguiente. La fecha del remito es la del dia en que se emite, en
            # hora de Argentina, igual que todo lo demas del producto.
            date=fecha.hoy(),
            client_id=cliente["id"],
            client_cuit=cliente["cuit"] or "",
            items=items,
            observations=_observaciones_del_lote(trabajos),
            usuario_id=usuario_id,
            # El domicilio si el cliente lo tiene cargado, y la ciudad si no.
            # Los formularios de remito y presupuesto lo hacen tipear; aca no
            # hay formulario, asi que se toma el mejor dato que haya en la
            # ficha en vez de dejarlo vacio.
            **datos_cliente_para_comprobante(cliente, cliente["domicilio"] or None),
        )

        with self.session_factory() as session:
            session.execute(
                update(Incidencia)
                .where(Incidencia.id.in_(ids))
                .values(remito_id=remito["id"])
            )
            session.commit()
        return remito
