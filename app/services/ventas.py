"""Ventas, sobre `sales` de LibraCommerce. **Sin emision de factura.**

LibraDesk no emite comprobantes fiscales: eso lo hace [[sos-contador]] a traves
del puente que ya existe (`app/services/facturacion_externa.py` y
`facturacion_sos.py`). Una venta de acá es el **comprobante interno** --que se
vendio, a quien, a que precio y como se cobro-- y es lo que despues se manda a
facturar.

Por eso no hay ARCA, ni CAE, ni tipo A/B/C, ni punto de venta fiscal. Y por eso
`sales` alcanza tal cual: el motor no factura, registra.

## 🔴 Los pagos van a `ventas_pagos`, NO a `sale_payments`

Es el detalle que hace o rompe la cuenta corriente, y no se deduce leyendo el
motor: `get_cc_saldo()` de LibraCore suma los debitos con

    FROM ventas_pagos vp JOIN sales v ON vp.venta_id = v.id
    WHERE v.customer_party_id = ? AND vp.medio = 'cuenta_corriente'

O sea que **lee la tabla de LibraCore aunque las ventas vivan en LibraCommerce**
--eso es lo que significa el origen `VENTAS_LIBRACOMMERCE`--. Un pago guardado
en `sale_payments`, que es la tabla "natural" del motor, **no lo ve nadie**: la
consulta no falla, devuelve cero y el cliente aparece sin deuda.

Contalibra hace exactamente esto (`app/db_ventas.py:122`) desde su migracion
P7. Se replica igual a proposito.

## El descuento de stock

`confirm_sale()` descuenta stock por linea de producto; los servicios no mueven
nada. **LibraDesk si valida disponibilidad**, y eso no es el default del motor:
ahi es `False` por compatibilidad con el mostrador, donde el cliente ya tiene el
producto en la mano y negarse a cobrar es peor que quedar en negativo.

Una mesa de ayuda es el caso contrario --la venta se carga despues del trabajo,
contra un deposito que alguien conto-- asi que un negativo es un error de carga
y conviene que aborte. Decidido para este producto, no heredado.

⚠️ **La validacion se hace explicita en `crear()` en vez de pasar
`validar_stock=True`.** No es lo mismo por una razon mecanica: con ese flag el
motor **abre su propia transaccion**, y `repo.transaction()` no admite
anidamiento --usar los dos juntos tira `RuntimeError: transaction() no admite
anidamiento`, verificado--. Como los pagos tambien tienen que entrar en la
misma transaccion, la abre este modulo y llama a `verificar_disponibilidad()`
antes, que es exactamente lo que el motor hace dentro de la suya.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from libracommerce.db.repository import SqliteCommerceRepository
from libracommerce.domain.catalog import CatalogItemType
from libracommerce.domain.sales import Sale, SaleItem, SaleStatus
from libracommerce.usecases.inventory import (
    StockInsuficienteError,
    verificar_disponibilidad,
)
from libracommerce.usecases.sales import confirm_sale
from libracore import medios_pago
from libracore.db import core as libracore_core
from sqlalchemy import DateTime, Integer, UniqueConstraint, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base, get_session_factory
from . import comercial, iva

from .fecha import ahora as _ahora

#: Como se cobro. `cuenta_corriente` es el unico que genera deuda; los demas
#: son informativos para el reporte de ventas.
#:
#: 🔴 **Del motor, no de una tupla escrita aca.** Era una de las 28 copias del
#: vocabulario de la familia y divergia en las dos direcciones: tenia `tarjeta`
#: --que la lista canonica no ofrecia-- y le faltaban `mercadopago`, `cuenta_dni`
#: y `billetera`, o sea que este producto no podia registrar un cobro por
#: MercadoPago aunque el resto de la casa si.
#:
#: Al adoptar la canonica, `tarjeta` deja de aceptarse AL ESCRIBIR: se parte en
#: `tarjeta_debito` y `tarjeta_credito`, que es como lo declara ARCA. Las ventas
#: viejas con `tarjeta` se siguen LEYENDO --`medios_pago.HISTORICOS` la conoce--
#: y el frontend las muestra bien.
#:
#: Ver `libracore.medios_pago` y wiki/concepts/medios-de-pago-familia-libra.md.
MEDIOS_PAGO = tuple(medios_pago.ELEGIBLES)


class VentaRemito(Base):
    """El vinculo entre una venta y el remito que la lleva a facturacion.

    **Es la unica tabla SQLAlchemy de este modulo**, que por lo demas es todo
    LibraCommerce por conexion cruda. La rareza es a proposito y tiene una razon
    concreta: `sales` es del motor y la cadena de Alembic de este producto no la
    toca nunca, asi que el `remito_id` no puede vivir como columna de la venta
    --como si vive en `incidencias`, en `contratos_cuotas` y en los
    presupuestos--. Ver el docstring de la revision `0026`.

    Que sea SQLAlchemy y no DDL crudo la separa de `materiales`, que es cruda
    porque **necesita** entrar en la misma transaccion que el movimiento de
    stock. Aca no: el remito ya se emitio por la conexion de LibraCore cuando
    esto se escribe, que es la misma no-atomicidad que documentan y aceptan las
    otras tres conversiones.
    """

    __tablename__ = "ventas_remitos"
    # Con nombre y en `__table_args__`, igual que `EnvioFacturacion`: un
    # `unique=True` en la columna deja que el motor le ponga el nombre, y
    # entonces la tabla que arma la migracion y la que arma `create_all()` no
    # son la misma. Lo agarra `test_una_base_vacia_se_construye_entera`.
    __table_args__ = (
        UniqueConstraint("venta_id", name="uq_ventas_remitos_venta"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Las dos van sin FK. Ver la revision `0026`: una apunta a LibraCommerce y
    # la otra a LibraCore, y ninguna de las dos tablas la maneja esta cadena.
    #
    # `venta_id` no lleva `index=True`: el unico de arriba ya crea su indice, y
    # pedir los dos deja un indice redundante que ademas no esta en la migracion.
    venta_id: Mapped[int] = mapped_column(Integer)
    remito_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(),
    )


def _repo(conn) -> SqliteCommerceRepository:
    return SqliteCommerceRepository(conn)


def remito_de(venta_id: int) -> int | None:
    """El remito que ya salio por esta venta, o `None`."""
    with get_session_factory()() as session:
        return session.execute(
            select(VentaRemito.remito_id).where(VentaRemito.venta_id == venta_id)
        ).scalar_one_or_none()


def nacio_de_una_venta(remito_id: int) -> bool:
    """Si este remito lo genero una venta.

    Lo consulta el puente para **no** debitar en cuenta corriente: la venta ya
    registro lo que el cliente pago o debe. Ver
    `facturacion_externa._debitar_en_cuenta_corriente`.
    """
    with get_session_factory()() as session:
        return session.execute(
            select(VentaRemito.id).where(VentaRemito.remito_id == remito_id)
        ).first() is not None


def _sql_recibo_vigente(origen_id: str) -> str:
    """El recibo VIGENTE de una venta, si ya se emitio. `None` = todavia no.

    Sin este dato la pantalla no puede distinguir "emitir" de "ver", y el boton
    termina emitiendo en silencio un comprobante que a veces ya existia.

    Los anulados se excluyen a proposito: un recibo anulado no es el comprobante
    de nada, y la venta vuelve a estar pendiente de recibo.

    `origen_id` es la expresion SQL que identifica la venta -- `s.id` en
    `listar()`, donde esto va como subconsulta correlacionada, y `?` en
    `obtener()`, donde va como parametro. Es un literal de este modulo, nunca
    entrada del usuario.

    Vive en una sola funcion porque la regla es una sola. Con la consulta
    copiada, la lista puede decir "ver recibo" de una venta que el detalle
    muestra como pendiente, y las dos pantallas tienen razon.
    """
    return f"""
        SELECT r.id FROM recibos r
         WHERE r.origen_tipo = 'venta' AND r.origen_id = {origen_id}
           AND r.anulado = 0
         ORDER BY r.id DESC LIMIT 1
    """


def listar(limit: int = 200, sucursal_id: int | None = None) -> list[dict]:
    """Las ventas, opcionalmente recortadas a una sucursal (`sales.branch_id`).

    ⚠️ **La cuenta corriente NO se filtra por sucursal** aunque las ventas si.
    El saldo de un cliente es uno solo entre sucursales --es la decision que
    define todo el eje, ver `comercial.listar_sucursales()`--, asi que la suma
    de `en_cuenta_corriente` de esta lista filtrada **no es** el saldo de nadie:
    es cuanto de lo vendido en esta sucursal fue a cuenta corriente.
    """
    where = "" if sucursal_id is None else "WHERE s.branch_id = ?"
    params: tuple = () if sucursal_id is None else (sucursal_id,)
    with libracore_core.get_connection() as conn:
        filas = conn.execute(
            f"""
            SELECT s.id, s.number, s.status, s.occurred_on, s.total,
                   s.customer_party_id, s.customer_name_snapshot,
                   s.branch_id,
                   c.name AS cliente_nombre,
                   (SELECT COALESCE(SUM(vp.monto), 0) FROM ventas_pagos vp
                     WHERE vp.venta_id = s.id AND vp.medio = 'cuenta_corriente')
                   AS en_cuenta_corriente,
                   ({_sql_recibo_vigente("s.id")}) AS recibo_id
            FROM sales s
            LEFT JOIN clients c ON c.id = s.customer_party_id
            {where}
            ORDER BY s.occurred_on DESC, s.id DESC
            LIMIT ?
            """,
            params + (limit,),
        ).fetchall()
    return [
        {"id": r["id"], "numero": r["number"], "estado": r["status"],
         "fecha": r["occurred_on"], "total": float(r["total"] or 0),
         "cliente_id": r["customer_party_id"],
         # El snapshot gana sobre el JOIN: es lo que se le facturo al cliente
         # ese dia. Si despues le cambiaron la razon social, el comprobante
         # viejo tiene que seguir diciendo lo que decia.
         "cliente": r["customer_name_snapshot"] or r["cliente_nombre"] or "Consumidor final",
         "sucursal_id": r["branch_id"],
         "en_cuenta_corriente": float(r["en_cuenta_corriente"] or 0),
         "recibo_id": r["recibo_id"]}
        for r in filas
    ]


def obtener(venta_id: int) -> dict | None:
    with libracore_core.get_connection() as conn:
        venta = _repo(conn).get_sale(venta_id)
        if venta is None:
            return None
        pagos = conn.execute(
            "SELECT medio, monto, referencia FROM ventas_pagos WHERE venta_id=? ORDER BY id",
            (venta_id,),
        ).fetchall()
        recibo = conn.execute(_sql_recibo_vigente("?"), (venta_id,)).fetchone()
        cliente = None
        if venta.customer_party_id:
            fila = conn.execute(
                "SELECT id, name, cuit_dni, address FROM clients WHERE id=?",
                (venta.customer_party_id,),
            ).fetchone()
            if fila:
                cliente = {"id": fila["id"], "nombre": fila["name"],
                           "cuit": fila["cuit_dni"] or "",
                           "domicilio": fila["address"] or ""}
    return {
        "id": venta.id,
        "numero": venta.number,
        "estado": str(venta.status),
        "fecha": venta.occurred_on,
        "cliente": cliente,
        "cliente_nombre": venta.customer_name_snapshot or (
            cliente["nombre"] if cliente else "Consumidor final"
        ),
        "notas": venta.notes,
        "recibo_id": recibo["id"] if recibo else None,
        # El remito que ya salio por esta venta, o `None`. Mismo criterio que
        # `recibo_id`: sin este dato la pantalla no puede distinguir "generar"
        # de "ver", y el boton termina emitiendo en silencio un comprobante que
        # a veces ya existia.
        "remito_id": remito_de(venta_id),
        "items": [
            {"descripcion": i.description_snapshot, "cantidad": float(i.quantity),
             "precio": float(i.unit_price), "item_id": i.item_id,
             "subtotal": float(i.quantity * i.unit_price)}
            for i in venta.items
        ],
        "pagos": [
            {"medio": p["medio"], "monto": float(p["monto"]),
             "referencia": p["referencia"] or ""}
            for p in pagos
        ],
        "subtotal": float(venta.subtotal),
        "total": float(venta.total),
    }


def crear(cliente_id: int | None, items: list[dict], pagos: list[dict], *,
          deposito_id: int, notas: str = "", sucursal_id: int | None = None,
          usuario_id: int | None = None) -> dict:
    """Crea la venta, la confirma (descuenta stock) y registra los pagos.

    `items` = `[{"item_id": int|None, "descripcion": str, "cantidad": float,
    "precio": float}, ...]`. Un item sin `item_id` es una linea de servicio:
    se cobra y **no mueve stock**, que es como el motor distingue producto de
    servicio (`CatalogItemType.SERVICE`).

    Las tres escrituras --venta, movimientos de stock, pagos-- van en **una
    transaccion**. Si el stock no alcanza no queda grabada ninguna.
    """
    if not items:
        raise ValueError("La venta necesita al menos un item.")
    for p in pagos:
        if p.get("medio") not in MEDIOS_PAGO:
            raise ValueError(f"Medio de pago desconocido: {p.get('medio')!r}")
    # `sales.customer_party_id` tiene FK contra `parties`, y un cliente dado de
    # alta despues del arranque todavia no esta espejado. Ver
    # `comercial.asegurar_parties`.
    comercial.asegurar_parties()

    lineas = tuple(
        SaleItem(
            kind=(CatalogItemType.PRODUCT if i.get("item_id")
                  else CatalogItemType.SERVICE),
            description_snapshot=i["descripcion"],
            quantity=Decimal(str(i["cantidad"])),
            unit_price=Decimal(str(i["precio"])),
            item_id=i.get("item_id"),
        )
        for i in items
    )
    subtotal = sum(l.quantity * l.unit_price for l in lineas)
    hoy = _ahora()

    with libracore_core.get_connection() as conn:
        repo = _repo(conn)
        # `sales.branch_id` no tiene FK contra `sucursales`: sin esta guarda, un
        # id inventado entra y la venta desaparece de toda pantalla filtrada.
        comercial.verificar_sucursal(conn, sucursal_id)
        nombre_cliente = ""
        if cliente_id:
            fila = conn.execute(
                "SELECT name FROM clients WHERE id=?", (cliente_id,)
            ).fetchone()
            if fila is None:
                raise ValueError("El cliente no existe.")
            nombre_cliente = fila["name"]

        try:
            # 🔴 `confirm_sale(validar_stock=True)` abre **su propia**
            # transaccion, y `repo.transaction()` no admite anidamiento: usar
            # las dos cosas juntas revienta con `RuntimeError`. Asi que la
            # transaccion la abre este modulo --que es el que necesita meter
            # tambien los pagos adentro-- y la validacion se hace explicita
            # antes, que es exactamente lo que el motor hace dentro de la suya.
            with repo.transaction():
                for linea in lineas:
                    if linea.item_id is not None:
                        verificar_disponibilidad(
                            repo, linea.item_id, deposito_id, linea.quantity
                        )
                venta = confirm_sale(
                    repo,
                    Sale(
                        None, _proximo_numero(conn), lineas,
                        status=SaleStatus.DRAFT,
                        customer_party_id=cliente_id,
                        branch_id=sucursal_id,
                        source_type="libradesk",
                        subtotal=subtotal, total=subtotal,
                        occurred_on=hoy.date().isoformat(),
                        customer_name_snapshot=nombre_cliente,
                        created_by=usuario_id, notes=notas,
                    ),
                    location_id=deposito_id,
                    occurred_at=hoy,
                    validar_stock=False,
                )
                for p in pagos:
                    conn.execute(
                        "INSERT INTO ventas_pagos (venta_id, medio, monto, referencia) "
                        "VALUES (?,?,?,?)",
                        (venta.id, p["medio"], float(p["monto"]),
                         p.get("referencia", "")),
                    )
        except StockInsuficienteError as e:
            raise ValueError(
                f"Stock insuficiente en el deposito (disponible: {float(e.disponible)})."
            ) from e

    dados_de_alta = _dar_de_alta_equipos(venta, cliente_id, items, usuario_id)
    return {
        "id": venta.id, "numero": venta.number, "total": float(subtotal),
        # Cuántos equipos quedaron en el parque del cliente. La pantalla lo
        # muestra: un alta automática que nadie ve es indistinguible de que no
        # haya pasado, y este dato es lo único que dice que pasó.
        "equipos_dados_de_alta": dados_de_alta,
    }


def _dar_de_alta_equipos(venta, cliente_id, items, usuario_id) -> int:
    """Deja en el parque del cliente los equipos que esta venta le vendió.

    Cierra el segundo corte de la venta (2026-08-16): *"vendés una central, la
    cobrás, la instalás, y el próximo reclamo sobre ese equipo no la
    encuentra"*. Hasta hoy **nadie fuera del router de equipos daba de alta un
    `Equipo`**, así que el circuito venta → instalación → soporte estaba cortado
    justo en la juntura.

    ## Qué se da de alta, y qué no

    Sólo los productos marcados **«es un equipo»** en el catálogo
    (`inventario.es_equipo`). Una ficha RJ11 no deja rastro en el parque; una
    central sí. Decisión del humano: es una propiedad del producto y no de cada
    venta, porque la decisión repetida es la que se olvida.

    **Uno por unidad vendida.** Vender 3 centrales deja 3 equipos, porque son 3
    cosas distintas que después se reparan y se reclaman por separado.

    ## Sin número de serie, a propósito

    El stock es por cantidad y **no sabe las series**: vender 3 no dice cuáles
    son las 3. La serie queda vacía y se completa al instalar. Decisión del
    humano, y es la que resuelve el problema planteado: lo que importaba es que
    el equipo **exista**, no que esté completo. Un formulario que exija las 3
    series en el mostrador, con el cliente esperando, es lo que hace que nadie
    lo use.

    `tipo` sale del nombre del producto porque es el único dato que el catálogo
    tiene: no hay `marca` ni `modelo` en un `catalog_item`. Queda editable.

    ## Lo que NO hace

    🔴 **Una venta sin cliente no da de alta nada.** Un equipo es de alguien
    —`equipos.cliente_id` es NOT NULL— y una venta de mostrador a nombre suelto
    no tiene a quién. **No es silencioso**: devuelve 0 y la pantalla lo dice,
    porque un cero que nadie ve es igual a que no haya pasado.

    ## Lo que NO es atómico

    Los equipos los escribe SQLAlchemy y la venta la conexión de LibraCommerce:
    dos conexiones, sin una transacción que las cubra. Es el mismo compromiso
    que ya documentan las cuatro conversiones a remito. Se da de alta **después**
    de que la venta quedó confirmada, porque el error al revés —equipos de una
    venta que no existe— es peor que una venta cuyos equipos hay que cargar a
    mano.
    """
    if not cliente_id:
        return 0

    from . import inventario
    from .equipos import EquipoRepository

    marcados = inventario.es_equipo_de_items([i.get("item_id") for i in items])
    if not marcados:
        return 0

    # Se arma acá en vez de recibirlo: este módulo son funciones sueltas, no un
    # repositorio con dependencias inyectadas, y ya usa `get_session_factory()`
    # para `VentaRemito`. Pasarlo por parámetro obligaría a que el router lo
    # cablee para una operación que es interna del alta.
    repo = EquipoRepository(get_session_factory())
    creados = 0
    for linea in items:
        if linea.get("item_id") not in marcados:
            continue
        # `int()` y no `round()`: media central no es media central. Una
        # cantidad fraccionaria en un producto marcado como equipo es un error
        # de carga, y de las dos formas de equivocarse conviene la que da de
        # alta de menos.
        for _ in range(int(linea["cantidad"])):
            repo.create(
                usuario_actor=str(usuario_id) if usuario_id else "Sistema",
                cliente_id=int(cliente_id),
                tipo=linea["descripcion"],
                observaciones=f"Alta automática por la venta {venta.number}",
            )
            creados += 1
    return creados


def _proximo_numero(conn) -> str:
    fila = conn.execute("SELECT COUNT(*) AS n FROM sales").fetchone()
    return f"V-{(fila['n'] or 0) + 1:08d}"


#: Una venta en estos estados no se factura: o se anuló o volvió la mercadería.
#: `partially_returned` **sí** se convierte — se devolvió parte y el resto se
#: cobra, que es justo lo que el remito tiene que decir.
ESTADOS_NO_CONVERTIBLES = (SaleStatus.CANCELLED, SaleStatus.RETURNED)


def convertir_a_remito(venta_id: int, remitos, clientes, *,
                       cliente_id: int | None = None,
                       usuario_id: int | None = None) -> dict:
    """El remito de una venta — su camino a facturación.

    Pedido del humano el 2026-08-16: *"la venta de equipo por qué no genera
    remito? debería generarlo porque lo vamos a tener cargado como stock y es una
    venta que después va a ir a SOS Contador"*.

    Es la **cuarta** conversión a remito del producto, y a propósito la misma
    forma que las tres que ya existían (presupuesto, reclamo, cuota): la bandeja
    acepta sólo remitos porque lo que habilita a facturar es la entrega hecha, y
    todo lo demás llega convirtiéndose.

    ## Recibe UNA venta y no una lista, al revés que reclamos y cuotas

    No es un olvido. Allá el agrupado es el caso real —tres visitas del mes en un
    remito, porque una factura sale de ahí— y acá no lo pidió nadie: una venta ya
    es un evento de mostrador con su propio número y su propio cobro. El día que
    haga falta agrupar, esto se convierte en el de largo 1 como se hizo con los
    reclamos; mientras tanto, una lista de un elemento sería una API más difícil
    de usar sin ganar nada.

    Y hay una diferencia que lo justifica: el índice único de `ventas_remitos`
    es sobre `venta_id`, no sobre `remito_id`. O sea que el modelo **ya admite**
    varias ventas en un remito el día que se agrupe; lo que no admite es que una
    venta salga dos veces.

    ## El cliente

    Una venta se puede cargar **a nombre suelto** (`customer_party_id` es
    nullable: es el mostrador). Un remito se emite a nombre de alguien, así que
    en ese caso hay que decir de quién — es lo que trae `cliente_id`. Con la
    venta ya identificada, pasar un `cliente_id` distinto es un error y no una
    corrección: la venta ya dice a quién se le vendió, y emitir el remito a otro
    nombre desharía esa verdad sin dejar rastro.

    ## La alícuota sale del catálogo, no de la venta

    La línea de venta del motor **tiene** un `tax_rate`, y este producto nunca lo
    completa: las ventas se cargan a precio final. Así que el IVA de cada línea
    se resuelve acá, leyendo la alícuota del producto
    (`inventario.alicuota_de`), y una línea sin `item_id` —un servicio ad-hoc del
    mostrador— sale con la de defecto.

    > ⚠️ **Esto no es un snapshot**: si mañana cambia la alícuota de un producto,
    > el remito de una venta vieja sin convertir saldría con la nueva. Se elige
    > así porque la alícuota que le corresponde a la factura es **la del momento
    > de facturar**, no la del día de la venta, y porque completar `tax_rate` en
    > la venta obligaría a tocar cómo se calcula su total — o sea, la plata de
    > todas las ventas que ya existen. El costo de esta decisión es el párrafo
    > que estás leyendo.

    ## Lo que NO es atómico

    Igual que las otras tres: el remito lo escribe la conexión de LibraCore y el
    vínculo lo escribe SQLAlchemy, sin una transacción que cubra las dos. Se
    emite primero el remito y se ata después, porque el error al revés —una venta
    que dice "ya se remitió" apuntando a un remito que no existe— la dejaría sin
    poder facturarse nunca.
    """
    from . import fecha, inventario
    from .remitos_presupuestos import datos_cliente_para_comprobante

    venta = obtener(venta_id)
    if venta is None:
        raise KeyError(venta_id)

    # ── Idempotencia: el doble click ────────────────────────────────────
    # Del dict de `obtener()`, que ya lo trae: pedirlo de nuevo sería la misma
    # consulta dos veces en la misma llamada.
    ya = venta["remito_id"]
    if ya is not None:
        existente = remitos.get(ya)
        if existente is not None:
            return existente
        # El remito que se referenciaba no está: se borró por fuera. Se sigue de
        # largo y se emite uno nuevo en vez de devolver `None`, que dejaría la
        # venta sin camino a facturación. Mismo criterio que las otras tres.
        _desatar(venta_id)

    if venta["estado"] in ESTADOS_NO_CONVERTIBLES:
        raise ValueError(
            f"La venta está «{venta['estado']}» y no hay nada que facturar."
        )
    if not venta["items"]:
        raise ValueError("La venta no tiene ítems, así que el remito saldría vacío.")

    # ── A nombre de quién ───────────────────────────────────────────────
    de_la_venta = (venta["cliente"] or {}).get("id")
    if de_la_venta and cliente_id and int(cliente_id) != int(de_la_venta):
        raise ValueError(
            "La venta ya está a nombre de un cliente y el remito tiene que salir "
            "al mismo. Si está mal, corregí la venta."
        )
    destinatario = de_la_venta or cliente_id
    if not destinatario:
        raise ValueError(
            "Esta venta se cargó sin cliente y un remito se emite a nombre de "
            "alguien. Elegí a quién antes de generarlo."
        )

    cliente = clientes.get(int(destinatario))
    if cliente is None:
        raise ValueError(
            "El cliente de esta venta ya no existe, así que no hay a nombre de "
            "quién emitir el remito."
        )

    # ── Las líneas, con la alícuota del catálogo ────────────────────────
    alicuotas = inventario.alicuotas_de_items(
        [i["item_id"] for i in venta["items"] if i["item_id"]]
    )
    items = [
        {
            "description": i["descripcion"],
            "qty": i["cantidad"],
            "unit_price": i["precio"],
            "tax_rate": float(
                alicuotas.get(i["item_id"], iva.DEFECTO) if i["item_id"]
                else iva.DEFECTO
            ),
        }
        for i in venta["items"]
    ]

    remito = remitos.create(
        # `fecha.hoy()` y no la fecha de la venta: el remito se emite hoy, en
        # hora de Argentina, igual que el de un reclamo y por el mismo motivo.
        date=fecha.hoy(),
        client_id=cliente["id"],
        client_cuit=cliente["cuit"] or "",
        items=items,
        observations=f"Generado de la venta {venta['numero']}",
        usuario_id=usuario_id,
        **datos_cliente_para_comprobante(cliente, cliente["domicilio"] or None),
    )
    _atar(venta_id, remito["id"])
    return remito


def _atar(venta_id: int, remito_id: int) -> None:
    with get_session_factory()() as session:
        session.add(VentaRemito(venta_id=venta_id, remito_id=remito_id))
        session.commit()


def _desatar(venta_id: int) -> None:
    """Saca el vínculo de una venta cuyo remito ya no existe."""
    with get_session_factory()() as session:
        session.execute(delete(VentaRemito).where(VentaRemito.venta_id == venta_id))
        session.commit()
