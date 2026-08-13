"""Compras: orden de compra y recepcion de mercaderia, sobre LibraCommerce.

**La recepcion es la operacion que genera inventario, no la orden.** Es la
regla del motor (`usecases/purchasing.confirm_purchase_receipt`) y es tambien
como opera Lagrace hoy: la mercaderia entra por *recepcion de mercaderia de
proveedores* --con factura o sin ella, que es el caso de las garantias--.

Confirmar una recepcion hace tres cosas en una: movimiento de stock de entrada,
actualizacion del costo del producto (ultimo costo, no promedio ponderado) y
avance de la orden de compra si estaba enganchada.

## El puente con los proveedores del producto

`purchase_orders.supplier_party_id` y `purchase_receipts.supplier_party_id` son
**NOT NULL** contra `parties`, y los proveedores de LibraDesk viven en su propia
tabla `proveedores`. El espejo lo mantiene `app/services/comercial.py`; aca solo
se traduce el id en las dos direcciones con `party_de_proveedor()` /
`proveedor_de_party()`.

> ⚠️ **Nunca guardar un `proveedor_id` crudo en una columna `*_party_id`.** El
> id existiria igual --seria el de un cliente-- y la FK no se quejaria: la
> compra quedaria a nombre de otro. Por eso la traduccion esta en un solo lugar.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from libracommerce.db.repository import SqliteCommerceRepository
from libracommerce.domain.purchasing import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderStatus,
    PurchaseReceipt,
    PurchaseReceiptItem,
    PurchaseReceiptStatus,
)
from libracommerce.usecases.purchasing import confirm_purchase_receipt
from libracore.db import core as libracore_core

from . import comercial

#: Los seis tipos de movimiento que usa Integridad se mapean asi: `RP`
#: (recepcion de proveedores) es una recepcion de compra; `EP` (envio a
#: proveedores, el caso RMA) es una salida de stock y se hace por ajuste, no
#: por acá. Ver `wiki/sources/lagrace-relevamiento-whatsapp.md`.
ESTADOS_ORDEN = tuple(s.value for s in PurchaseOrderStatus)


def _repo(conn) -> SqliteCommerceRepository:
    return SqliteCommerceRepository(conn)


def _nombre_proveedores(conn) -> dict[int, str]:
    return {
        r["id"]: r["nombre"]
        for r in conn.execute("SELECT id, nombre FROM proveedores").fetchall()
    }


# ── Ordenes de compra ────────────────────────────────────────────────────


def listar_ordenes() -> list[dict]:
    with libracore_core.get_connection() as conn:
        nombres = _nombre_proveedores(conn)
        ordenes = _repo(conn).list_purchase_orders()
        return [
            {
                "id": o.id,
                "numero": o.number,
                "estado": str(o.status),
                "proveedor_id": comercial.proveedor_de_party(o.supplier_party_id),
                "proveedor": nombres.get(
                    comercial.proveedor_de_party(o.supplier_party_id), "—"
                ),
                "fecha": o.ordered_at.isoformat() if o.ordered_at else None,
                "items": len(o.items),
                "total": float(
                    sum(i.quantity_ordered * i.unit_cost for i in o.items)
                ),
                "recibido_pct": _recibido_pct(o),
            }
            for o in ordenes
        ]


def _recibido_pct(orden: PurchaseOrder) -> int:
    """Cuanto de la orden ya entro por recepciones, en porcentaje.

    Se calcula sobre **cantidades** y no sobre importes: una orden puede tener
    lineas de precios muy distintos y lo que se pregunta mirando la grilla es
    "cuanto falta que llegue", no "cuanta plata falta".
    """
    pedido = sum(i.quantity_ordered for i in orden.items)
    if not pedido:
        return 0
    recibido = sum(i.quantity_received for i in orden.items)
    return int(min(recibido / pedido, 1) * 100)


def obtener_orden(orden_id: int) -> dict | None:
    with libracore_core.get_connection() as conn:
        orden = _repo(conn).get_purchase_order(orden_id)
        if orden is None:
            return None
        nombres = _nombre_proveedores(conn)
        proveedor_id = comercial.proveedor_de_party(orden.supplier_party_id)
        items = _detalle_items(conn, orden.items)
    return {
        "id": orden.id,
        "numero": orden.number,
        "estado": str(orden.status),
        "proveedor_id": proveedor_id,
        "proveedor": nombres.get(proveedor_id, "—"),
        "fecha": orden.ordered_at.isoformat() if orden.ordered_at else None,
        "notas": orden.notes,
        "items": items,
        "total": float(sum(i.quantity_ordered * i.unit_cost for i in orden.items)),
    }


def _detalle_items(conn, items) -> list[dict]:
    if not items:
        return []
    repo = _repo(conn)
    salida = []
    for linea in items:
        producto = repo.get_catalog_item(linea.item_id)
        salida.append({
            "item_id": linea.item_id,
            "producto": producto.name if producto else "(borrado)",
            "cantidad": float(linea.quantity_ordered),
            "recibido": float(linea.quantity_received),
            "costo": float(linea.unit_cost),
            "subtotal": float(linea.quantity_ordered * linea.unit_cost),
        })
    return salida


def crear_orden(proveedor_id: int, items: list[dict], *, notas: str = "",
                sucursal_id: int | None = None,
                usuario_id: int | None = None) -> dict:
    """`items` = `[{"item_id": int, "cantidad": float, "costo": float}, ...]`."""
    if not items:
        raise ValueError("La orden de compra necesita al menos un item.")
    lineas = tuple(
        PurchaseOrderItem(
            item_id=int(i["item_id"]),
            quantity_ordered=Decimal(str(i["cantidad"])),
            unit_cost=Decimal(str(i.get("costo", 0))),
        )
        for i in items
    )
    with libracore_core.get_connection() as conn:
        orden = _repo(conn).save_purchase_order(
            PurchaseOrder(
                None, _proximo_numero(conn, "purchase_orders", "OC"),
                comercial.party_de_proveedor(proveedor_id), lineas,
                status=PurchaseOrderStatus.DRAFT, branch_id=sucursal_id,
                ordered_at=datetime.now(), notes=notas, created_by=usuario_id,
            )
        )
        return {"id": orden.id, "numero": orden.number}


def _proximo_numero(conn, tabla: str, prefijo: str) -> str:
    """Numeracion interna correlativa, con el prefijo del comprobante.

    ⚠️ **No es numeracion fiscal.** Ese comprobante lo emite SOS Contador y
    tiene su propio punto de venta; este numero es para que un humano pueda
    nombrar la orden por telefono. Ver la seccion "La numeracion de LibraCore no
    es fiscal" en `wiki/analyses/libradesk-brechas-para-lagrace.md`.
    """
    fila = conn.execute(f"SELECT COUNT(*) AS n FROM {tabla}").fetchone()
    return f"{prefijo}-{(fila['n'] or 0) + 1:08d}"


# ── Recepciones ──────────────────────────────────────────────────────────


def listar_recepciones() -> list[dict]:
    with libracore_core.get_connection() as conn:
        nombres = _nombre_proveedores(conn)
        recepciones = _repo(conn).list_purchase_receipts()
        return [
            {
                "id": r.id,
                "estado": str(r.status),
                "proveedor_id": comercial.proveedor_de_party(r.supplier_party_id),
                "proveedor": nombres.get(
                    comercial.proveedor_de_party(r.supplier_party_id), "—"
                ),
                "fecha": r.received_at.isoformat() if r.received_at else None,
                "documento": r.document_reference or "",
                "orden_id": r.purchase_order_id,
                "items": len(r.items),
                "total": float(sum(i.quantity * i.unit_cost for i in r.items)),
            }
            for r in recepciones
        ]


def crear_recepcion(proveedor_id: int, deposito_id: int, items: list[dict], *,
                    documento: str = "", orden_id: int | None = None,
                    usuario_id: int | None = None) -> dict:
    """Crea la recepcion **y la confirma**: entra al stock en el acto.

    No se guarda en borrador a proposito. Una recepcion en borrador es
    mercaderia que ya esta fisicamente en el deposito pero que el sistema no
    cuenta, y esa diferencia es exactamente lo que un inventario tiene que
    evitar. Si algun dia hace falta el borrador --recepcion parcial que se
    completa despues-- el motor ya lo soporta y el cambio es de pantalla.
    """
    if not items:
        raise ValueError("La recepcion necesita al menos un item.")
    lineas = tuple(
        PurchaseReceiptItem(
            item_id=int(i["item_id"]),
            quantity=Decimal(str(i["cantidad"])),
            unit_cost=Decimal(str(i.get("costo", 0))),
        )
        for i in items
    )
    with libracore_core.get_connection() as conn:
        repo = _repo(conn)
        with repo.transaction():
            recepcion = confirm_purchase_receipt(
                repo,
                PurchaseReceipt(
                    None, comercial.party_de_proveedor(proveedor_id), lineas,
                    purchase_order_id=orden_id,
                    status=PurchaseReceiptStatus.DRAFT,
                    document_reference=documento or None,
                    created_by=usuario_id,
                ),
                location_id=deposito_id,
                occurred_at=datetime.now(),
            )
        return {"id": recepcion.id, "items": len(recepcion.items)}


def obtener_recepcion(recepcion_id: int) -> dict | None:
    with libracore_core.get_connection() as conn:
        recepcion = _repo(conn).get_purchase_receipt(recepcion_id)
        if recepcion is None:
            return None
        nombres = _nombre_proveedores(conn)
        proveedor_id = comercial.proveedor_de_party(recepcion.supplier_party_id)
        repo = _repo(conn)
        items = []
        for linea in recepcion.items:
            producto = repo.get_catalog_item(linea.item_id)
            items.append({
                "item_id": linea.item_id,
                "producto": producto.name if producto else "(borrado)",
                "cantidad": float(linea.quantity),
                "costo": float(linea.unit_cost),
                "subtotal": float(linea.quantity * linea.unit_cost),
            })
    return {
        "id": recepcion.id,
        "estado": str(recepcion.status),
        "proveedor_id": proveedor_id,
        "proveedor": nombres.get(proveedor_id, "—"),
        "fecha": recepcion.received_at.isoformat() if recepcion.received_at else None,
        "documento": recepcion.document_reference or "",
        "orden_id": recepcion.purchase_order_id,
        "items": items,
        "total": float(sum(i.quantity * i.unit_cost for i in recepcion.items)),
    }
