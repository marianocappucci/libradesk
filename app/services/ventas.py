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

from decimal import Decimal

from libracommerce.db.repository import SqliteCommerceRepository
from libracommerce.domain.catalog import CatalogItemType
from libracommerce.domain.sales import Sale, SaleItem, SaleStatus
from libracommerce.usecases.inventory import (
    StockInsuficienteError,
    verificar_disponibilidad,
)
from libracommerce.usecases.sales import confirm_sale
from libracore.db import core as libracore_core

from . import comercial

from .fecha import ahora as _ahora

#: Como se cobro. `cuenta_corriente` es el unico que genera deuda; los demas
#: son informativos para el reporte de ventas.
MEDIOS_PAGO = ("efectivo", "transferencia", "cheque", "tarjeta", "cuenta_corriente")


def _repo(conn) -> SqliteCommerceRepository:
    return SqliteCommerceRepository(conn)


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
                   -- El recibo VIGENTE de esta venta, si ya se emitió. Sin
                   -- esto la pantalla no puede distinguir "emitir" de "ver", y
                   -- el botón termina emitiendo en silencio algo que ya
                   -- existía. Se excluyen los anulados a propósito: un recibo
                   -- anulado no es el comprobante de nada, y la venta vuelve a
                   -- estar pendiente de recibo.
                   (SELECT r.id FROM recibos r
                     WHERE r.origen_tipo = 'venta' AND r.origen_id = s.id
                       AND r.anulado = 0
                     ORDER BY r.id DESC LIMIT 1) AS recibo_id
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
    return {"id": venta.id, "numero": venta.number, "total": float(subtotal)}


def _proximo_numero(conn) -> str:
    fila = conn.execute("SELECT COUNT(*) AS n FROM sales").fetchone()
    return f"V-{(fila['n'] or 0) + 1:08d}"
