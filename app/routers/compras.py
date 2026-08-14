"""Compras: ordenes, recepcion de mercaderia y egresos.

Los tres van juntos porque son el mismo circuito visto desde tres momentos: lo
que se pide, lo que llega (y entra al stock) y lo que se paga. El gate por plan
es `compras`, y lo pone `main.py`.

**Los proveedores no estan aca.** Siguen en `app/routers/proveedores.py`, que
es el ABM del producto: el mismo proveedor al que se le manda un equipo a
service es al que se le compra. Duplicarlo en dos pantallas es como se
terminan teniendo dos listas distintas de la misma empresa.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..services import compras, egresos

router = APIRouter(prefix="/api", tags=["compras"])


# ── Payloads ─────────────────────────────────────────────────────────────


class ItemCompraIn(BaseModel):
    item_id: int
    cantidad: float = Field(gt=0)
    costo: float = Field(ge=0, default=0)


class OrdenIn(BaseModel):
    proveedor_id: int
    items: list[ItemCompraIn]
    notas: str = ""
    sucursal_id: int | None = None


class RecepcionIn(BaseModel):
    proveedor_id: int
    #: A que deposito entra la mercaderia. Obligatorio: una recepcion sin
    #: destino es stock que existe en ningun lado.
    deposito_id: int
    items: list[ItemCompraIn]
    documento: str = ""
    orden_id: int | None = None


class EgresoIn(BaseModel):
    fecha: str
    concepto: str
    total: float = Field(gt=0)
    proveedor_id: int | None = None
    proveedor_nombre: str = ""
    tipo_comprobante: str = "factura"
    numero: str = ""
    categoria: str = ""
    monto_neto: float = 0
    iva_pct: float = 0
    iva_monto: float = 0
    observaciones: str = ""


class PagoEgresoIn(BaseModel):
    fecha: str
    monto: float = Field(gt=0)
    medio_pago: str = "efectivo"
    referencia: str = ""


class CategoriaEgresoIn(BaseModel):
    nombre: str


# ── Ordenes de compra ────────────────────────────────────────────────────


@router.get("/ordenes-compra")
def listar_ordenes(sucursal_id: int | None = None):
    return compras.listar_ordenes(sucursal_id=sucursal_id)


@router.get("/ordenes-compra/{orden_id}")
def obtener_orden(orden_id: int):
    orden = compras.obtener_orden(orden_id)
    if orden is None:
        raise HTTPException(404, "La orden de compra no existe.")
    return orden


@router.post("/ordenes-compra", status_code=201)
def crear_orden(payload: OrdenIn, user: dict = Depends(get_current_user)):
    try:
        return compras.crear_orden(
            payload.proveedor_id,
            [i.model_dump() for i in payload.items],
            notas=payload.notas, sucursal_id=payload.sucursal_id,
            usuario_id=int(user["id"]),
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


# ── Recepciones ──────────────────────────────────────────────────────────


@router.get("/recepciones-compra")
def listar_recepciones(sucursal_id: int | None = None):
    """Prefijo `-compra` a proposito: `/api/recepciones` ya es la recepcion de
    equipos en el taller, que es otro circuito y otra pantalla.

    `sucursal_id` filtra por **el depósito donde entró la mercadería**, no por
    la sucursal de la orden: son datos distintos y el que importa acá es dónde
    quedó el stock. Ver `compras._sucursal_de_recepciones()`.
    """
    return compras.listar_recepciones(sucursal_id=sucursal_id)


@router.get("/recepciones-compra/{recepcion_id}")
def obtener_recepcion(recepcion_id: int):
    recepcion = compras.obtener_recepcion(recepcion_id)
    if recepcion is None:
        raise HTTPException(404, "La recepcion no existe.")
    return recepcion


@router.post("/recepciones-compra", status_code=201)
def crear_recepcion(payload: RecepcionIn, user: dict = Depends(get_current_user)):
    """Registra la recepcion **y suma el stock en el acto**. Ver el servicio."""
    try:
        return compras.crear_recepcion(
            payload.proveedor_id, payload.deposito_id,
            [i.model_dump() for i in payload.items],
            documento=payload.documento, orden_id=payload.orden_id,
            usuario_id=int(user["id"]),
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


# ── Egresos ──────────────────────────────────────────────────────────────


@router.get("/egresos")
def listar_egresos(desde: str = "", hasta: str = "", categoria: str = "",
                   estado: str = "", proveedor_id: int = 0):
    return egresos.listar(desde=desde, hasta=hasta, categoria=categoria,
                          estado=estado, proveedor_id=proveedor_id or None)


@router.get("/egresos/resumen")
def resumen_egresos(desde: str = "", hasta: str = ""):
    return egresos.resumen(desde=desde, hasta=hasta)


@router.get("/egresos/{egreso_id}")
def obtener_egreso(egreso_id: int):
    egreso = egresos.obtener(egreso_id)
    if egreso is None:
        raise HTTPException(404, "El egreso no existe.")
    return egreso


@router.post("/egresos", status_code=201)
def crear_egreso(payload: EgresoIn, user: dict = Depends(get_current_user)):
    try:
        return {"id": egresos.crear(
            payload.fecha, payload.concepto, payload.total,
            proveedor_id=payload.proveedor_id,
            proveedor_nombre=payload.proveedor_nombre,
            tipo_comprobante=payload.tipo_comprobante, numero=payload.numero,
            categoria=payload.categoria, monto_neto=payload.monto_neto,
            iva_pct=payload.iva_pct, iva_monto=payload.iva_monto,
            observaciones=payload.observaciones, usuario_id=int(user["id"]),
        )}
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/egresos/{egreso_id}", status_code=204)
def eliminar_egreso(egreso_id: int):
    egresos.eliminar(egreso_id)


@router.post("/egresos/{egreso_id}/pagos", status_code=201)
def pagar_egreso(egreso_id: int, payload: PagoEgresoIn,
                 user: dict = Depends(get_current_user)):
    try:
        return {"id": egresos.registrar_pago(
            egreso_id, payload.fecha, payload.monto,
            medio_pago=payload.medio_pago, referencia=payload.referencia,
            usuario_id=int(user["id"]),
        )}
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/egresos-categorias")
def listar_categorias_egreso():
    return egresos.listar_categorias()


@router.post("/egresos-categorias", status_code=201)
def crear_categoria_egreso(payload: CategoriaEgresoIn):
    try:
        return {"id": egresos.crear_categoria(payload.nombre)}
    except ValueError as e:
        raise HTTPException(422, str(e))
