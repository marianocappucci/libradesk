"""Insumos de un equipo — el toner que entra a la fotocopiadora, y todo lo que
se le parezca.

## Que hueco cierra

El caso que lo motiva (2026-08-24): un cliente **alquila fotocopiadoras a un
tercero**, y ese tercero le provee los toner dentro del contrato. Para pedirlos
hay que darle **su** numero interno de maquina, y cada cambio de toner es un
hecho que hasta hoy no tenia donde anotarse. El sistema sabia que la impresora
existia y que a veces se rompia; no sabia que consume, cuando se le cambio por
ultima vez ni que le deben.

Lo unico que habia era el `motivo` de un `EquipoMovimiento`, texto libre. O sea
la misma situacion que tenia el paso por service antes de `equipos_reparaciones`:
*"a quien se lo pedimos"*, *"con que remito llego"* y *"con que contador se
puso"* dentro de una frase escrita a mano, que no se puede listar, filtrar ni
sumar.

## Por que NO es `incidencias_materiales`

Esa tabla existe y hace otra cosa: descuenta **nuestro** deposito cuando el
tecnico usa algo de la camioneta. El toner del hospital **nunca es nuestro** —lo
pone el proveedor del cliente—, asi que cargarlo por ahi ensuciaria el
inventario con mercaderia que no compramos ni vendimos.

🔴 **Y este modulo no mueve stock, a proposito.** Si el insumo salio de tu
deposito, el camino que corresponde sigue siendo el material de la incidencia,
que descuenta y appendea el movimiento en la misma transaccion (ver
`services/materiales.py`, que explica por que eso no puede hacerse desde el ORM).
Duplicar aca ese circuito daria dos escrituras que pueden desincronizarse; no
hacerlo deja el limite claro: **esto registra el consumo, no el stock**.

## Por que se llama `insumos` y no `toners`

Mismo argumento que ya esta escrito en `services/contratos.py` para el contrato
y la modalidad: si la entidad se llama por el caso, el segundo caso obliga a
rehacer el modulo. Un filtro de un aire acondicionado, un kit de mantenimiento,
una bateria de UPS y un rollo de impresora fiscal son el mismo hecho —**un
equipo consume algo cada tanto y alguien se lo provee**— y entran sin tocar el
schema.

## Una fila = una unidad

Un pedido de dos toner crea **dos filas**, no una con `cantidad = 2`. Es lo que
hace que las dos preguntas de la pantalla se puedan contestar contando: cuantos
te deben, y cuanto rindio cada uno. Con una fila de cantidad 2 la colocacion
tendria que ser de las dos juntas, que no es lo que pasa: llegan juntos y se
ponen en momentos distintos.

## Tres fechas y ningun `estado`

Mismo criterio con el que `equipos_reparaciones` deriva el suyo de
`fecha_retorno` y `contratos_equipos` de `fecha_retiro`: una columna `estado` al
lado de las fechas puede contradecirlas, y despues no hay forma de saber cual
miente.

- `fecha_entrega IS NULL` → **te lo deben**. De ahi sale el reclamo.
- entregado y `fecha_colocacion IS NULL` → esta en el armario del cliente.
- `fecha_colocacion IS NOT NULL` → esta puesto en la maquina.

Ninguna de las tres es obligatoria por separado —un cambio se puede registrar
despues de hecho, sin pedido— pero **al menos una tiene que estar**, y eso lo
garantiza un CHECK: una fila sin ninguna fecha no describe nada.

## El contador, y por que un contador que retrocede no se rechaza

`contador_copias` es la lectura del display al **poner** el insumo, y es lo que
convierte el registro en control: la diferencia contra la colocacion anterior
del mismo insumo en el mismo equipo es lo que rindio el anterior
(`copias_desde_el_anterior`).

⚠️ **Un contador puede bajar en uso normal**: si le cambian la placa a la
maquina, vuelve a cero. Por eso una lectura menor que la anterior **no se
rechaza** —seria una guarda que salta operando bien, y el operador terminaria
inventando un numero para poder guardar—: se acepta y el rendimiento de ese
tramo sale `None`, que es lo unico honesto. Un negativo ahi seria peor que un
vacio, porque promedia.

## `insumo_item_id` no lleva ForeignKey

El catalogo de consumibles es de **LibraCommerce** (`catalog_items`), no de este
producto: vive en otro `MetaData` y se escribe por la conexion cruda de
`libracore.db.core`. Un `ForeignKey("catalog_items.id")` declarado desde este
`Base` ni siquiera resuelve —`NoReferencedTableError` en el `create_all`—, asi
que la columna es un entero y **la existencia la valida el service** contra el
catalogo, antes de escribir.

Y el nombre se **copia** en `insumo_nombre` en vez de leerse siempre del
catalogo, por el mismo motivo que lo copia `materiales._descripcion()`: renombrar
un producto no puede reescribir lo que dice un cambio de toner de marzo. Como
efecto util, el historial se lee entero aunque la instancia no tenga el modulo
`stock` prendido — lo unico que necesita ese modulo es **elegir** el insumo.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base
from .fecha import hoy

#: Los tres estados derivados de las fechas. No hay columna: ver el docstring.
ESTADOS = ("pendiente", "en_poder", "colocado")


class EquipoInsumo(Base):
    __tablename__ = "equipos_insumos"
    __table_args__ = (
        # Una fila sin ninguna fecha no describe ningun hecho.
        CheckConstraint(
            "fecha_pedido IS NOT NULL OR fecha_entrega IS NOT NULL "
            "OR fecha_colocacion IS NOT NULL",
            name="ck_insumo_alguna_fecha",
        ),
        # El orden real de los tres momentos. Con NULLs el CHECK da NULL y pasa,
        # que es lo que se quiere: lo que no se registro no ordena nada.
        CheckConstraint(
            "fecha_entrega IS NULL OR fecha_pedido IS NULL "
            "OR fecha_entrega >= fecha_pedido",
            name="ck_insumo_entrega_despues_del_pedido",
        ),
        CheckConstraint(
            "fecha_colocacion IS NULL OR fecha_entrega IS NULL "
            "OR fecha_colocacion >= fecha_entrega",
            name="ck_insumo_colocacion_despues_de_la_entrega",
        ),
        # Una lectura de contador sin colocacion no significa nada: el contador
        # se lee al poner el insumo en la maquina.
        CheckConstraint(
            "contador_copias IS NULL OR fecha_colocacion IS NOT NULL",
            name="ck_insumo_contador_solo_al_colocar",
        ),
        CheckConstraint(
            "contador_copias IS NULL OR contador_copias >= 0",
            name="ck_insumo_contador_no_negativo",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Sin `ondelete`: el equipo con insumos cargados no se borra —lo rechaza
    # `EquipoRepository.dependencias()`, igual que con las reparaciones— asi que
    # no hay cascada que definir. Y los `ondelete` de este producto no se
    # ejecutan igual: el pragma de FKs esta apagado en SQLite.
    equipo_id: Mapped[int] = mapped_column(
        ForeignKey("equipos.id"), nullable=False, index=True,
    )
    # `catalog_items.id` de LibraCommerce, SIN ForeignKey — ver el docstring del
    # modulo. La existencia la valida `InsumoRepository` contra el catalogo.
    insumo_item_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # Copia del nombre al momento de usarlo, no una lectura del catalogo.
    insumo_nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    # Quien lo entrega. **NULL = lo puso el propio cliente**, y esa es la unica
    # fuente de ese dato: una columna `origen` al lado seria la misma verdad
    # dicha dos veces.
    proveedor_id: Mapped[int | None] = mapped_column(
        ForeignKey("proveedores.id"), index=True,
    )
    fecha_pedido: Mapped[date | None] = mapped_column(Date, index=True)
    fecha_entrega: Mapped[date | None] = mapped_column(Date, index=True)
    fecha_colocacion: Mapped[date | None] = mapped_column(Date, index=True)
    remito_proveedor: Mapped[str | None] = mapped_column(String(100))
    contador_copias: Mapped[int | None] = mapped_column(Integer)
    # El ticket que lo origino, si vino de uno. Mismo criterio que en
    # `equipos_movimientos` y `equipos_reparaciones`: el cambio de toner ocurrio
    # de verdad y le sobrevive al ticket, asi que al borrar la incidencia esto
    # queda en NULL en vez de irse con ella.
    incidencia_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidencias.id"), index=True,
    )
    usuario: Mapped[str] = mapped_column(String(255), nullable=False, default="Sistema")
    observaciones: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def estado_de(i: EquipoInsumo) -> str:
    """Los tres estados, derivados en un solo lugar.

    La colocacion manda sobre la entrega: un cambio registrado despues de hecho
    puede no tener entrega cargada y esta puesto igual.
    """
    if i.fecha_colocacion is not None:
        return "colocado"
    if i.fecha_entrega is not None:
        return "en_poder"
    return "pendiente"


def _dias_esperando(i: EquipoInsumo) -> int | None:
    """Cuantos dias hace que se pidio y no llego. `None` si ya llego o si no
    hubo pedido — lo que interesa mirar en la bandeja es cual se esta demorando,
    igual que `dias_afuera` en las reparaciones."""
    if i.fecha_pedido is None or i.fecha_entrega is not None:
        return None
    return (date.fromisoformat(hoy()) - i.fecha_pedido).days


def fecha_de_referencia(i: EquipoInsumo) -> date | None:
    """Contra que fecha se pregunta si el contrato cubria este insumo.

    **La primera que exista de las tres**, en orden: pedido, entrega,
    colocacion. Es el momento en que nacio la necesidad, que es lo que el
    contrato tiene que estar cubriendo; con la fecha de colocacion se estaria
    preguntando por el dia en que el tecnico paso, que puede ser meses despues
    de que el proveedor entrego.
    """
    return i.fecha_pedido or i.fecha_entrega or i.fecha_colocacion


def _to_dict(i: EquipoInsumo, *, equipo=None, proveedor=None,
             copias_previas: int | None = None, contrato=None) -> dict:
    contador = i.contador_copias
    # Ver el docstring: un contador que retrocede (placa cambiada) da None y no
    # un negativo, que promediaria mal.
    if contador is None or copias_previas is None or contador < copias_previas:
        rendimiento = None
    else:
        rendimiento = contador - copias_previas
    return {
        "id": i.id,
        "equipo_id": i.equipo_id,
        # Resueltos para que la lista no pida un endpoint mas por renglon,
        # mismo criterio que `proveedor_nombre` en las reparaciones.
        "equipo_descripcion": (
            " ".join(x for x in (equipo.tipo, equipo.marca, equipo.modelo) if x)
            if equipo is not None else None
        ),
        "equipo_serial": equipo.serial if equipo is not None else None,
        "cliente_id": equipo.cliente_id if equipo is not None else None,
        "insumo_item_id": i.insumo_item_id,
        "insumo_nombre": i.insumo_nombre,
        "proveedor_id": i.proveedor_id,
        "proveedor_nombre": proveedor.nombre if proveedor is not None else None,
        "fecha_pedido": i.fecha_pedido.isoformat() if i.fecha_pedido else None,
        "fecha_entrega": i.fecha_entrega.isoformat() if i.fecha_entrega else None,
        "fecha_colocacion": (
            i.fecha_colocacion.isoformat() if i.fecha_colocacion else None
        ),
        # Derivados, nunca almacenados.
        "estado": estado_de(i),
        "dias_esperando": _dias_esperando(i),
        "remito_proveedor": i.remito_proveedor,
        "contador_copias": i.contador_copias,
        # Lo que rindio el insumo ANTERIOR de la misma clase en este equipo. El
        # nombre dice el intervalo a proposito: "rendimiento" a secas se lee
        # como una propiedad de esta fila y es la del tramo que cierra.
        "copias_desde_el_anterior": rendimiento,
        # El contrato de proveedor que cubria el equipo en la fecha de esta fila
        # (fase 2). Se resuelve, no se guarda — ver `contratos_proveedor`.
        "contrato_numero": contrato.numero if contrato is not None else None,
        # 🔑 **No es lo mismo que tener contrato.** Un contrato de service cubre
        # la maquina y no los insumos, asi que un toner bajo ese contrato SI se
        # paga. Con un solo campo "tiene contrato" la pantalla diria que esta
        # cubierto justo en el caso en que hay que discutir la factura.
        "cubierto_por_contrato": bool(
            contrato is not None and contrato.incluye_insumos
        ),
        "incidencia_id": i.incidencia_id,
        "usuario": i.usuario,
        "observaciones": i.observaciones,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }


def _copias_previas(session, filas: list[EquipoInsumo]) -> dict[int, int]:
    """Por cada fila colocada, el contador de la colocacion anterior del **mismo
    insumo en el mismo equipo**.

    Una sola consulta para todo el listado y no una por fila: la lista de un
    parque de 20 maquinas con dos anios de cambios son cientos de filas, y la
    version por fila era el N+1 que hace que la pantalla no abra.

    El par (equipo, insumo) es lo que define la cadena, y por eso una maquina
    color no mezcla: el negro y el cyan son dos items del catalogo, o sea dos
    cadenas independientes. Se sobre-lee a proposito —el `IN` cruza los equipos
    con los items en vez de filtrar por pares— para no depender de row values,
    que no todos los motores soportan igual; el par se filtra en Python.
    """
    pares = {
        (f.equipo_id, f.insumo_item_id)
        for f in filas if f.fecha_colocacion is not None
    }
    if not pares:
        return {}

    todas = session.execute(
        select(EquipoInsumo)
        .where(
            EquipoInsumo.fecha_colocacion.is_not(None),
            EquipoInsumo.equipo_id.in_({e for e, _ in pares}),
            EquipoInsumo.insumo_item_id.in_({i for _, i in pares}),
        )
        .order_by(EquipoInsumo.fecha_colocacion, EquipoInsumo.id)
    ).scalars().all()

    cadenas: dict[tuple[int, int], list[EquipoInsumo]] = {}
    for f in todas:
        cadenas.setdefault((f.equipo_id, f.insumo_item_id), []).append(f)

    previas: dict[int, int] = {}
    for cadena in cadenas.values():
        anterior: EquipoInsumo | None = None
        for f in cadena:
            if anterior is not None and anterior.contador_copias is not None:
                previas[f.id] = anterior.contador_copias
            anterior = f
    return previas


def _validar_fechas(pedido: date | None, entrega: date | None,
                    colocacion: date | None) -> None:
    """Las mismas reglas que los CHECK, con el mensaje legible.

    Se valida aca ademas de en la base por lo mismo que en las reparaciones: un
    CHECK levanta un `IntegrityError` crudo que la API traduciria a un 500.

    La tercera comparacion —colocacion contra pedido— **no** esta en la base:
    un CHECK que la incluyera tendria que enumerar los casos con NULL de las
    otras dos, y esto es exactamente lo mismo escrito una vez.
    """
    if pedido is None and entrega is None and colocacion is None:
        raise ValueError(
            "hay que registrar al menos una fecha: el pedido, la entrega o la "
            "colocación"
        )
    if entrega is not None and pedido is not None and entrega < pedido:
        raise ValueError("la fecha de entrega es anterior a la del pedido")
    if colocacion is not None:
        if entrega is not None and colocacion < entrega:
            raise ValueError("la fecha de colocación es anterior a la de entrega")
        if pedido is not None and colocacion < pedido:
            raise ValueError("la fecha de colocación es anterior a la del pedido")


class InsumoRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    # ── Lectura ──────────────────────────────────────────────────────────

    def _resolver(self, session, filas: list[EquipoInsumo]) -> list[dict]:
        from .contratos_proveedor import coberturas_por_equipo, cubre
        from .equipos import Equipo
        from .proveedores import Proveedor

        previas = _copias_previas(session, filas)
        # Dos consultas para todo el listado y no dos por fila: ver
        # `coberturas_por_equipo`.
        coberturas = coberturas_por_equipo(session, {f.equipo_id for f in filas})

        def contrato_de_la_fila(f: EquipoInsumo):
            cuando = fecha_de_referencia(f)
            return cubre(coberturas, f.equipo_id, cuando) if cuando else None

        return [
            _to_dict(
                f,
                equipo=session.get(Equipo, f.equipo_id),
                proveedor=(
                    session.get(Proveedor, f.proveedor_id)
                    if f.proveedor_id is not None else None
                ),
                copias_previas=previas.get(f.id),
                contrato=contrato_de_la_fila(f),
            )
            for f in filas
        ]

    def list(
        self,
        *,
        equipo_id: int | None = None,
        cliente_id: int | None = None,
        proveedor_id: int | None = None,
        insumo_item_id: int | None = None,
        incidencia_id: int | None = None,
        estado: str | None = None,
        desde: date | None = None,
        hasta: date | None = None,
    ) -> list[dict]:
        """Lo pendiente primero y, dentro de cada grupo, lo mas reciente arriba.

        Es el orden en que se lee la pantalla: lo que falta reclamar va antes
        que el historial, igual que las reparaciones abiertas.

        `desde`/`hasta` recortan por la **fecha de referencia** de cada fila
        —la primera que exista de pedido, entrega o colocacion—, que es la misma
        que decide contra que momento se mira el contrato. El `coalesce` de aca
        abajo es esa regla en SQL: si cambia `fecha_de_referencia()`, este
        recorte tiene que cambiar con ella, y hay un test que los cruza.
        """
        from .equipos import Equipo

        if estado is not None and estado not in ESTADOS:
            raise ValueError(f"estado desconocido: {estado!r}")

        with self.session_factory() as session:
            q = select(EquipoInsumo)
            if equipo_id is not None:
                q = q.where(EquipoInsumo.equipo_id == equipo_id)
            if cliente_id is not None:
                # El cliente lo tiene el equipo, no el insumo: duplicarlo aca
                # abriria la puerta a que digan cosas distintas si el equipo
                # cambia de dueño. Mismo criterio que en las reparaciones.
                q = q.where(EquipoInsumo.equipo_id.in_(
                    select(Equipo.id).where(Equipo.cliente_id == cliente_id)
                ))
            if proveedor_id is not None:
                q = q.where(EquipoInsumo.proveedor_id == proveedor_id)
            if insumo_item_id is not None:
                q = q.where(EquipoInsumo.insumo_item_id == insumo_item_id)
            if incidencia_id is not None:
                q = q.where(EquipoInsumo.incidencia_id == incidencia_id)
            if desde is not None or hasta is not None:
                referencia = func.coalesce(
                    EquipoInsumo.fecha_pedido,
                    EquipoInsumo.fecha_entrega,
                    EquipoInsumo.fecha_colocacion,
                )
                if desde is not None:
                    q = q.where(referencia >= desde)
                if hasta is not None:
                    q = q.where(referencia <= hasta)
            if estado == "pendiente":
                q = q.where(EquipoInsumo.fecha_entrega.is_(None),
                            EquipoInsumo.fecha_colocacion.is_(None))
            elif estado == "en_poder":
                q = q.where(EquipoInsumo.fecha_entrega.is_not(None),
                            EquipoInsumo.fecha_colocacion.is_(None))
            elif estado == "colocado":
                q = q.where(EquipoInsumo.fecha_colocacion.is_not(None))

            q = q.order_by(
                EquipoInsumo.fecha_entrega.is_not(None),
                func.coalesce(
                    EquipoInsumo.fecha_colocacion,
                    EquipoInsumo.fecha_entrega,
                    EquipoInsumo.fecha_pedido,
                ).desc(),
                EquipoInsumo.id.desc(),
            )
            return self._resolver(session, list(session.execute(q).scalars()))

    def get(self, insumo_id: int) -> dict | None:
        with self.session_factory() as session:
            i = session.get(EquipoInsumo, insumo_id)
            if i is None:
                return None
            return self._resolver(session, [i])[0]

    # ── Escritura ────────────────────────────────────────────────────────

    def create(
        self,
        *,
        equipo_id: int,
        insumo_item_id: int,
        cantidad: int = 1,
        proveedor_id: int | None = None,
        fecha_pedido: date | None = None,
        fecha_entrega: date | None = None,
        fecha_colocacion: date | None = None,
        remito_proveedor: str | None = None,
        contador_copias: int | None = None,
        incidencia_id: int | None = None,
        observaciones: str | None = None,
        usuario: str = "Sistema",
    ) -> list[dict]:
        """Registra `cantidad` unidades — **una fila por unidad**, ver el
        docstring del modulo. Devuelve la lista, que es lo que se muestra.

        Sin `proveedor_id`, el proveedor **se hereda del equipo** cuando el
        equipo es de un tercero: es de quien se piden los insumos en el caso que
        motivo el modulo, y pedirlo en cada carga seria pedir dos veces el mismo
        dato. El caso contrario —el equipo es de un tercero pero esta vez el
        toner lo puso el cliente— se corrige editando la fila; es raro y no
        justifica una bandera en el alta.
        """
        from . import inventario
        from .equipos import Equipo
        from .proveedores import Proveedor

        if cantidad < 1:
            raise ValueError("la cantidad tiene que ser al menos 1")
        if contador_copias is not None and fecha_colocacion is None:
            raise ValueError(
                "el contador se lee al colocar el insumo: falta la fecha de "
                "colocación"
            )
        _validar_fechas(fecha_pedido, fecha_entrega, fecha_colocacion)

        # El catalogo es del motor y se consulta por su conexion, afuera de la
        # sesion del ORM. Se hace ANTES de abrirla para no tener dos conexiones
        # abiertas a la vez sin necesidad.
        item = inventario.item(insumo_item_id)
        if item is None:
            raise KeyError(("insumo", insumo_item_id))

        with self.session_factory() as session:
            equipo = session.get(Equipo, equipo_id)
            if equipo is None:
                raise KeyError(("equipo", equipo_id))
            if proveedor_id is None:
                proveedor_id = equipo.proveedor_id
            if proveedor_id is not None and session.get(Proveedor, proveedor_id) is None:
                raise KeyError(("proveedor", proveedor_id))

            filas = [
                EquipoInsumo(
                    equipo_id=equipo_id,
                    insumo_item_id=insumo_item_id,
                    insumo_nombre=item["nombre"],
                    proveedor_id=proveedor_id,
                    fecha_pedido=fecha_pedido,
                    fecha_entrega=fecha_entrega,
                    fecha_colocacion=fecha_colocacion,
                    remito_proveedor=remito_proveedor,
                    # El contador es de UNA unidad: si se cargan dos juntas, la
                    # lectura describe la que se puso, no las dos. Se guarda en
                    # la primera y el resto queda sin contador — con la segunda
                    # copiando el mismo numero, el rendimiento del tramo
                    # siguiente daria cero.
                    contador_copias=contador_copias if n == 0 else None,
                    incidencia_id=incidencia_id,
                    observaciones=observaciones,
                    usuario=usuario,
                )
                for n in range(cantidad)
            ]
            session.add_all(filas)
            session.commit()
            for f in filas:
                session.refresh(f)
            return self._resolver(session, filas)

    def entregar(self, insumo_id: int, *, fecha_entrega: date,
                 remito_proveedor: str | None = None) -> dict:
        """Llego. Es el paso que vacia la bandeja de pendientes."""
        with self.session_factory() as session:
            i = session.get(EquipoInsumo, insumo_id)
            if i is None:
                raise KeyError(insumo_id)
            if i.fecha_entrega is not None:
                raise ValueError("el insumo ya figura entregado")
            _validar_fechas(i.fecha_pedido, fecha_entrega, i.fecha_colocacion)
            i.fecha_entrega = fecha_entrega
            if remito_proveedor is not None:
                i.remito_proveedor = remito_proveedor
            session.commit()
            session.refresh(i)
            return self._resolver(session, [i])[0]

    def colocar(self, insumo_id: int, *, fecha_colocacion: date,
                contador_copias: int | None = None) -> dict:
        """Se puso en la maquina, con la lectura del display.

        **No exige que este entregado.** Un insumo que estaba en el armario del
        cliente desde antes de que existiera esta pantalla se pone igual, y
        obligar a inventarle una entrega para poder registrarlo seria empujar a
        cargar un dato falso.
        """
        with self.session_factory() as session:
            i = session.get(EquipoInsumo, insumo_id)
            if i is None:
                raise KeyError(insumo_id)
            if i.fecha_colocacion is not None:
                raise ValueError("el insumo ya figura colocado")
            _validar_fechas(i.fecha_pedido, i.fecha_entrega, fecha_colocacion)
            i.fecha_colocacion = fecha_colocacion
            if contador_copias is not None:
                i.contador_copias = contador_copias
            session.commit()
            session.refresh(i)
            return self._resolver(session, [i])[0]

    def update(self, insumo_id: int, **data) -> dict:
        """Correccion de una carga. No cambia de equipo ni de insumo: eso no es
        corregir un dato, es otra fila —y arrastraria el rendimiento de dos
        cadenas—. Para eso se borra y se carga de nuevo."""
        from .proveedores import Proveedor

        with self.session_factory() as session:
            i = session.get(EquipoInsumo, insumo_id)
            if i is None:
                raise KeyError(insumo_id)

            proveedor_id = data.get("proveedor_id", i.proveedor_id)
            if proveedor_id is not None and session.get(Proveedor, proveedor_id) is None:
                raise KeyError(("proveedor", proveedor_id))

            for campo in (
                "proveedor_id", "fecha_pedido", "fecha_entrega", "fecha_colocacion",
                "remito_proveedor", "contador_copias", "observaciones",
            ):
                if campo in data:
                    setattr(i, campo, data[campo])

            _validar_fechas(i.fecha_pedido, i.fecha_entrega, i.fecha_colocacion)
            if i.contador_copias is not None and i.fecha_colocacion is None:
                raise ValueError(
                    "el contador se lee al colocar el insumo: falta la fecha de "
                    "colocación"
                )
            session.commit()
            session.refresh(i)
            return self._resolver(session, [i])[0]

    def delete(self, insumo_id: int) -> None:
        """Borra una carga hecha por error.

        Se borra de verdad y no se marca, a diferencia de un material del
        ticket: alla la fila es la contracara de un movimiento de stock que ya
        se appendeo y no se puede desaparecer. Aca no hay ledger detras — lo
        unico que se pierde es el renglon mal cargado.
        """
        with self.session_factory() as session:
            i = session.get(EquipoInsumo, insumo_id)
            if i is None:
                raise KeyError(insumo_id)
            session.delete(i)
            session.commit()

    def resumen(self, *, cliente_id: int | None = None,
                equipo_id: int | None = None,
                estado: str | None = None) -> list[dict]:
        """Qué le toca a cada máquina — el consumo resumido por (equipo, insumo).

        Es la fase 3: convierte el historial que ya se venía cargando en algo
        que se puede mirar antes de que la máquina se pare. Cada fila responde
        *"cada cuánto se cambia esto, cuándo fue la última vez y desde cuándo
        conviene ir pidiendo el próximo"*.

        **Ordena por lo que hay que hacer primero**: lo que ya toca pedir
        arriba y, dentro, lo más atrasado. Lo que no tiene historial suficiente
        va al final — no es una omisión, es que todavía no se puede estimar.

        Se calcula en Python y no en SQL a propósito: la aritmética vive en
        `ResumenDeConsumo`, que se puede probar sin base, y una consulta con
        ventanas dejaría la misma regla escrita en dos dialectos.
        """
        from .clientes import Cliente
        from .equipos import Equipo

        if estado is not None and estado not in ESTADOS_RESUMEN:
            raise ValueError(f"estado desconocido: {estado!r}")

        hoy_ = date.fromisoformat(hoy())

        with self.session_factory() as session:
            q = select(EquipoInsumo)
            if equipo_id is not None:
                q = q.where(EquipoInsumo.equipo_id == equipo_id)
            if cliente_id is not None:
                q = q.where(EquipoInsumo.equipo_id.in_(
                    select(Equipo.id).where(Equipo.cliente_id == cliente_id)
                ))
            filas = list(session.execute(q).scalars())
            if not filas:
                return []

            # Un grupo por (equipo, insumo): el negro y el cyan de la misma
            # máquina son dos consumos distintos, con su propia cadencia.
            grupos: dict[tuple[int, int], list] = {}
            for f in filas:
                grupos.setdefault((f.equipo_id, f.insumo_item_id), []).append(f)

            equipos = {
                e.id: e for e in session.execute(
                    select(Equipo).where(
                        Equipo.id.in_({e for e, _ in grupos})
                    )
                ).scalars()
            }
            clientes = dict(session.execute(
                select(Cliente.id, Cliente.nombre).where(
                    Cliente.id.in_({e.cliente_id for e in equipos.values()})
                )
            ).all())

            resultado = []
            for (eq_id, item_id), delgrupo in grupos.items():
                colocaciones = [i for i in delgrupo if i.fecha_colocacion is not None]
                # Pendiente o en el armario del cliente: las dos cuentan como
                # "ya pedido", porque en las dos ya hay un tóner en camino a esa
                # máquina y volver a pedir sería pedir de más.
                pendientes = [i for i in delgrupo if i.fecha_colocacion is None]
                equipo = equipos.get(eq_id)

                resumen = ResumenDeConsumo(
                    equipo_id=eq_id, insumo_item_id=item_id,
                    # El nombre del insumo sale de la fila más reciente: es una
                    # copia del catálogo al momento de usarlo, y si el producto
                    # se renombró, la última es la que el operador reconoce.
                    insumo_nombre=delgrupo[-1].insumo_nombre,
                    colocaciones=colocaciones, pendientes=pendientes,
                    hoy_=hoy_,
                    demora_proveedor=_demora_tipica(delgrupo),
                )
                resultado.append(resumen.to_dict(
                    equipo=equipo,
                    cliente_nombre=(
                        clientes.get(equipo.cliente_id) if equipo is not None else None
                    ),
                ))

        # `pedir_ahora` primero, y dentro de cada estado lo más atrasado arriba.
        # Los `None` de `dias_para_pedir` —sin historial— van al final: no hay
        # nada que hacer con ellos hoy.
        orden = {"pedir_ahora": 0, "ya_pedido": 1, "al_dia": 2, "sin_historial": 3}
        resultado.sort(key=lambda r: (
            orden.get(r["estado"], 9),
            r["dias_para_pedir"] if r["dias_para_pedir"] is not None else 10**6,
        ))
        if estado is not None:
            resultado = [r for r in resultado if r["estado"] == estado]
        return resultado



# ── Fase 3: lo que el historial permite anticipar ────────────────────────

#: Cuánto antes del cambio estimado se considera que "ya toca". Si el promedio
#: son 50 días, a los 45 la máquina entra en la lista aunque todavía no venza:
#: pedir el día exacto es pedir tarde, porque el insumo tarda en llegar.
#:
#: Es un margen sobre la propia cadencia de la máquina y no un número fijo de
#: días: una que se cambia cada 15 días necesita menos anticipación que una que
#: se cambia cada 200.
MARGEN_ANTICIPO = 0.10

#: Con menos de dos colocaciones no hay ningún intervalo que promediar, así que
#: no hay nada que estimar. **No se inventa una duración por defecto**: una
#: predicción sacada de la nada se lee igual que una medida, y la primera vez
#: que falle nadie vuelve a mirar la lista.
MINIMO_COLOCACIONES = 2

ESTADOS_RESUMEN = ("sin_historial", "ya_pedido", "pedir_ahora", "al_dia")


def _promedio(valores: list[int]) -> int | None:
    """`None` cuando no hay nada que promediar, nunca cero: un cero se lee como
    una medición y acá significa "no sé"."""
    return round(sum(valores) / len(valores)) if valores else None


def _demora_tipica(filas: list[EquipoInsumo]) -> int | None:
    """Cuánto tarda el proveedor en entregar **para esta máquina**.

    Se mide de las entregas propias y no de un número global porque es lo que se
    le va a descontar al aviso: la anticipación que necesita una máquina cuyo
    proveedor tarda diez días no es la misma que la de una que se surte del
    armario del cliente el mismo día.

    `None` mientras no haya ninguna entrega registrada — y ahí el aviso sale sin
    descuento, que es lo único que se puede hacer sin inventar un número.
    """
    return _promedio([
        (f.fecha_entrega - f.fecha_pedido).days
        for f in filas
        if f.fecha_pedido is not None and f.fecha_entrega is not None
    ])


class ResumenDeConsumo:
    """El consumo de UN insumo en UNA máquina, ya resumido.

    Es una clase y no un dict armado a mano para que el cálculo —lo único con
    aritmética de todo el módulo— quede en un lugar con nombre y se pueda
    probar sin base de datos.

    ## Qué se puede anticipar con lo que hay, y qué no

    Lo que el producto registra es la **colocación**: la fecha y el contador del
    display en ese momento. De ahí sale cada cuánto se cambia esta máquina y
    cuántas copias rindió cada tóner.

    🔴 **Lo que NO se puede es predecir por copias.** Para saber cuántas copias
    lleva hechas la máquina desde el último cambio haría falta una **lectura de
    hoy**, y el contador se lee sólo al cambiar el tóner. Estimar por días es lo
    único honesto con los datos que existen; el día que alguien tome lecturas
    periódicas, la estimación por copias entra sin cambiar el schema. Es la
    misma razón por la que la fase 2 no trajo el tope de copias del contrato.

    ## Y el intervalo mide el CAMBIO, no la vida del tóner

    Entre que el tóner se acaba y que llega el repuesto pueden pasar días con la
    máquina parada, y ese tiempo está adentro del intervalo. Para lo que se usa
    —*"¿cada cuánto le toca a esta máquina?"*— es el número correcto, porque
    incluye la realidad de la operación. Para *"cuánto dura un tóner"* el número
    honesto es el de **copias**, que no depende de cuándo se pudo cambiar.
    """

    def __init__(self, equipo_id: int, insumo_item_id: int, insumo_nombre: str,
                 colocaciones: list, pendientes: list, hoy_: date,
                 demora_proveedor: int | None = None):
        self.equipo_id = equipo_id
        self.insumo_item_id = insumo_item_id
        self.insumo_nombre = insumo_nombre
        self.hoy = hoy_
        self.demora_proveedor = demora_proveedor
        # Orden cronológico: los intervalos se miden entre consecutivas.
        self.colocaciones = sorted(
            colocaciones, key=lambda i: (i.fecha_colocacion, i.id)
        )
        self.pendientes = pendientes

    @property
    def cambios(self) -> int:
        return len(self.colocaciones)

    @property
    def ultimo_cambio(self) -> date | None:
        return self.colocaciones[-1].fecha_colocacion if self.colocaciones else None

    @property
    def dias_desde_el_ultimo(self) -> int | None:
        return (self.hoy - self.ultimo_cambio).days if self.ultimo_cambio else None

    @property
    def dias_entre_cambios(self) -> int | None:
        """El promedio de los intervalos entre colocaciones consecutivas."""
        intervalos = [
            (b.fecha_colocacion - a.fecha_colocacion).days
            for a, b in zip(self.colocaciones, self.colocaciones[1:])
        ]
        return _promedio(intervalos)

    @property
    def copias_promedio(self) -> int | None:
        """Lo que rindió cada tóner, en copias.

        Sale de la diferencia entre contadores consecutivos, **salteando los
        tramos que no se pueden medir**: sin lectura, o con el contador más bajo
        que el anterior —la placa cambiada—. Un tramo que no se puede medir no
        vale cero, y por eso se descarta en vez de promediarse.
        """
        rindes = []
        for a, b in zip(self.colocaciones, self.colocaciones[1:]):
            if a.contador_copias is None or b.contador_copias is None:
                continue
            if b.contador_copias < a.contador_copias:
                continue
            rindes.append(b.contador_copias - a.contador_copias)
        return _promedio(rindes)

    @property
    def proximo_cambio_estimado(self) -> date | None:
        promedio = self.dias_entre_cambios
        if promedio is None or self.ultimo_cambio is None:
            return None
        return self.ultimo_cambio + timedelta(days=promedio)

    @property
    def pedir_desde(self) -> date | None:
        """Cuándo hay que **pedirlo**, que es antes de que se acabe.

        Al cambio estimado se le descuenta lo que tarda el proveedor —medido de
        las entregas de esta misma máquina— más un margen sobre su propia
        cadencia. Sin ese descuento, la lista avisaría el día en que la máquina
        se queda parada, que es tarde por definición.
        """
        estimado = self.proximo_cambio_estimado
        if estimado is None:
            return None
        promedio = self.dias_entre_cambios or 0
        anticipo = round(promedio * MARGEN_ANTICIPO) + (self.demora_proveedor or 0)
        return estimado - timedelta(days=anticipo)

    @property
    def dias_para_pedir(self) -> int | None:
        """Cuántos días faltan —o sobran, en negativo— para que toque pedirlo.

        Es una propiedad y no una cuenta dentro de `to_dict()` por lo mismo que
        el resto: la aritmética vive toda junta y se puede probar sin armar el
        dict de salida.
        """
        return (self.pedir_desde - self.hoy).days if self.pedir_desde else None

    @property
    def estado(self) -> str:
        """Los cuatro estados, en el orden en que se preguntan.

        🔑 **`ya_pedido` gana sobre `pedir_ahora`**: si para esta máquina hay un
        insumo pendiente o esperando en el armario del cliente, la lista no
        tiene que volver a pedirlo. Sin esa precedencia, una máquina vencida
        seguiría gritando después de que alguien la atendió y la lista se
        convierte en ruido — que es como se deja de mirar una lista.
        """
        if self.pendientes:
            return "ya_pedido"
        if self.cambios < MINIMO_COLOCACIONES or self.pedir_desde is None:
            return "sin_historial"
        return "pedir_ahora" if self.hoy >= self.pedir_desde else "al_dia"

    def to_dict(self, *, equipo=None, cliente_nombre: str | None = None) -> dict:
        return {
            "equipo_id": self.equipo_id,
            "equipo_descripcion": (
                " ".join(x for x in (equipo.tipo, equipo.marca, equipo.modelo) if x)
                if equipo is not None else None
            ),
            "equipo_sector": equipo.sector if equipo is not None else None,
            "cliente_id": equipo.cliente_id if equipo is not None else None,
            "cliente_nombre": cliente_nombre,
            "insumo_item_id": self.insumo_item_id,
            "insumo_nombre": self.insumo_nombre,
            "cambios": self.cambios,
            "ultimo_cambio": (
                self.ultimo_cambio.isoformat() if self.ultimo_cambio else None
            ),
            "dias_desde_el_ultimo": self.dias_desde_el_ultimo,
            "dias_entre_cambios": self.dias_entre_cambios,
            "copias_promedio": self.copias_promedio,
            "demora_proveedor": self.demora_proveedor,
            "proximo_cambio_estimado": (
                self.proximo_cambio_estimado.isoformat()
                if self.proximo_cambio_estimado else None
            ),
            "pedir_desde": (
                self.pedir_desde.isoformat() if self.pedir_desde else None
            ),
            "estado": self.estado,
            # La columna que ordena la lista.
            "dias_para_pedir": self.dias_para_pedir,
        }
