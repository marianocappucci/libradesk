"""Egresos: gastos y facturas de proveedor, con estado de pago.

Cero dominio propio: todo sale de `libracore.db.egresos`, el mismo codigo que
usa Contalibra. Este modulo existe para dos cosas que el motor no puede saber:

1. **Que los proveedores de LibraDesk son los suyos.** El motor trae su propio
   CRUD de proveedores (`create_proveedor`, `update_proveedor`, ...) y LibraDesk
   **no lo usa**: tiene su `ProveedorRepository` por SQLAlchemy, para que la
   auditoria por flush de libraauth vea las escrituras --mismo criterio que
   clientes--. Desde la revision `0018` las dos vistas de la tabla son
   compatibles, asi que el motor puede LEER lo que escribe el producto.
2. **Que un egreso pagado no es lo mismo que un egreso cerrado.** El estado lo
   deriva el motor sumando `egresos_pagos`; aca solo se expone.

> ⚠️ **Lo que este modulo NO hace: tocar caja.** En Contalibra un pago de
> egreso puede impactar en una caja (`egresos_pagos.caja_id`). LibraDesk no
> tiene caja ni tesoreria, asi que la columna queda en NULL y el pago registra
> **que se pago**, no de donde salio la plata. Si algun dia entra tesoreria,
> este es el punto de enganche.
"""

from __future__ import annotations

from libracore.db import egresos as _eg

#: Los tipos de comprobante que se cargan como egreso. Salen del relevamiento
#: de Lagrace: lo que entra por factura de proveedor y lo que entra sin
#: factura (el caso de las garantias/RMA, que se mueve por remito).
TIPOS_COMPROBANTE = ("factura", "nota_credito", "recibo", "remito", "otro")

ESTADOS = ("pendiente", "parcial", "pagado")


def listar(desde: str = "", hasta: str = "", categoria: str = "",
           estado: str = "", proveedor_id: int | None = None) -> list[dict]:
    return _eg.get_all_egresos(
        desde=desde, hasta=hasta, categoria=categoria, estado=estado,
        proveedor_id=proveedor_id,
    )


def obtener(egreso_id: int) -> dict | None:
    egreso = _eg.get_egreso(egreso_id)
    if egreso is None:
        return None
    pagos = _eg.get_pagos_egreso(egreso_id)
    pagado = sum(float(p["monto"]) for p in pagos)
    return {
        **egreso,
        "pagos": pagos,
        "pagado": round(pagado, 2),
        # El saldo se calcula aca y no en la pantalla, por el mismo motivo que
        # el margen en `listas_precio.py`: una sola definicion de "cuanto falta".
        "saldo": round(float(egreso["total"]) - pagado, 2),
    }


def crear(fecha: str, concepto: str, total: float, *, proveedor_id=None,
          proveedor_nombre: str = "", tipo_comprobante: str = "factura",
          numero: str = "", categoria: str = "", monto_neto: float = 0,
          iva_pct: float = 0, iva_monto: float = 0, observaciones: str = "",
          usuario_id: int | None = None) -> int:
    if not (concepto or "").strip():
        raise ValueError("El egreso necesita un concepto.")
    if total <= 0:
        raise ValueError("El total del egreso tiene que ser mayor a cero.")
    if tipo_comprobante not in TIPOS_COMPROBANTE:
        raise ValueError(f"Tipo de comprobante desconocido: {tipo_comprobante!r}")
    return _eg.create_egreso(
        fecha=fecha, concepto=concepto.strip(), total=total,
        proveedor_id=proveedor_id, proveedor_nombre=proveedor_nombre,
        tipo_comprobante=tipo_comprobante, numero=numero, categoria=categoria,
        monto_neto=monto_neto, iva_pct=iva_pct, iva_monto=iva_monto,
        observaciones=observaciones, usuario_id=usuario_id,
    )


def eliminar(egreso_id: int) -> None:
    _eg.delete_egreso(egreso_id)


def registrar_pago(egreso_id: int, fecha: str, monto: float, *,
                   medio_pago: str = "efectivo", referencia: str = "",
                   usuario_id: int | None = None) -> int:
    """Un pago, total o parcial.

    **No valida que no se pague de mas**, y es a proposito: el motor deriva el
    estado del total pagado, y un pago que excede puede ser un anticipo o una
    correccion. Lo que si hace la pantalla es mostrar el saldo, para que
    pasarse sea una decision y no un descuido.
    """
    if monto <= 0:
        raise ValueError("El pago tiene que ser mayor a cero.")
    return _eg.create_pago_egreso(
        egreso_id=egreso_id, fecha=fecha, monto=monto,
        medio_pago=medio_pago, referencia=referencia, usuario_id=usuario_id,
    )


def resumen(desde: str = "", hasta: str = "") -> dict:
    return _eg.get_resumen_egresos(desde=desde, hasta=hasta)


# ── Categorias ───────────────────────────────────────────────────────────


def listar_categorias() -> list[dict]:
    return _eg.get_categorias_egreso()


def crear_categoria(nombre: str) -> int:
    if not (nombre or "").strip():
        raise ValueError("La categoria necesita un nombre.")
    return _eg.create_categoria_egreso(nombre.strip())


def eliminar_categoria(categoria_id: int) -> None:
    _eg.delete_categoria_egreso(categoria_id)
