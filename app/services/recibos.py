"""Recibos: el comprobante de que entro plata. Dominio entero de LibraCore.

Dos origenes en LibraDesk: una **venta** cobrada y un **pago a cuenta
corriente**. El tercero que soporta el motor --factura-- no aplica: este
producto no factura.

## Lo unico propio, y sin esto el recibo sale vacio

`emitir_recibo_venta()` del motor busca la venta con
`libracore.db.ventas.get_venta`, que lee **la tabla `ventas`**. En LibraDesk esa
tabla existe (la crea el schema del motor) y **esta vacia**, porque las ventas
viven en `sales` de LibraCommerce.

> 🔴 Si se dejara el default, el recibo de una venta no saldria **y no por un
> error visible**: `get_venta` devolveria `None` y el motor tiraria `SinCobros`,
> que se lee como "esta venta no tiene cobros" en vez de "estas mirando la tabla
> equivocada". Por eso se le inyecta el `get_venta` de este producto. Mismo
> patron y mismo motivo que `app/db_recibos.py` de Contalibra.

El motor es **idempotente** por origen: pedir dos veces el recibo de la misma
venta devuelve el mismo recibo, no emite un segundo. Eso es lo que hace que
reimprimir sea seguro.
"""

from __future__ import annotations

from libracore import recibos as _emision
from libracore.db import recibos as _db

from . import ventas as _ventas

#: Punto de venta de la numeracion interna del recibo. **No es fiscal** --el
#: recibo no lleva CAE ni pasa por ARCA-- asi que queda en 1 mientras LibraDesk
#: sea una empresa por instancia. El dia que entren sucursales de verdad, este
#: es el numero que hay que abrir por sucursal.
PUNTO_VENTA = 1


def _get_venta_libradesk(venta_id: int) -> dict | None:
    """Adapta la venta de este producto a la forma que espera el motor.

    El motor pide `cliente_id`/`cliente_cuit`/`cliente_domicilio` **planos**, y
    `ventas.obtener()` los devuelve anidados en `cliente`. Aplanarlos aca y no
    cambiar `obtener()` es a proposito: la forma anidada es la que consume la
    pantalla, y el motor no deberia dictar el contrato de la API.
    """
    venta = _ventas.obtener(venta_id)
    if venta is None:
        return None
    cliente = venta.get("cliente") or {}
    return {
        **venta,
        "cliente_nombre": venta.get("cliente_nombre"),
        "cliente_id": cliente.get("id"),
        "cliente_cuit": cliente.get("cuit", ""),
        "cliente_domicilio": cliente.get("domicilio", ""),
    }


def listar(desde: str = "", hasta: str = "", q: str = "",
           cliente_id: int | None = None, limit: int = 200) -> list[dict]:
    return _db.get_recibos(desde=desde, hasta=hasta, q=q,
                           cliente_id=cliente_id, limit=limit)


def obtener(recibo_id: int) -> dict | None:
    return _db.get_recibo(recibo_id)


def emitir_de_venta(venta_id: int, usuario_id: int | None = None,
                    observaciones: str = "") -> dict:
    return _emision.emitir_recibo_venta(
        venta_id, punto_venta=PUNTO_VENTA, usuario_id=usuario_id,
        observaciones=observaciones, get_venta=_get_venta_libradesk,
    )


def emitir_de_cobranza(cc_pago_id: int, usuario_id: int | None = None,
                       observaciones: str = "") -> dict:
    """El recibo de un pago a cuenta corriente.

    Acá **no** hace falta inyectar nada: `get_cc_pago` lee `cc_pagos`, que es
    una tabla de LibraCore y en este producto es la real. La asimetria con
    `emitir_de_venta()` es exactamente el mapa de que motor tiene cada cosa.
    """
    return _emision.emitir_recibo_cobranza(
        cc_pago_id, punto_venta=PUNTO_VENTA, usuario_id=usuario_id,
        observaciones=observaciones,
    )


def anular(recibo_id: int, motivo: str = "", usuario_id: int | None = None) -> bool:
    """Un recibo no se borra: se anula. Igual que una factura."""
    return _db.anular_recibo(recibo_id, motivo=motivo, usuario_id=usuario_id)
