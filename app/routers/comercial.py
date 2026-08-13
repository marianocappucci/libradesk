"""Listas de precios y cuenta corriente.

Dos modulos chicos en un router, porque los dos son lo mismo desde el lado del
transporte: exponer un servicio que ya delega en un motor. Separarlos en dos
archivos de 40 lineas no agregaria nada.

**Las sucursales NO estan aca** aunque sean del mismo paquete de trabajo: no
van gateadas por plan, asi que viven en `app/routers/sucursales.py`. Meterlas
en este router las habria dejado detras del gate de cuenta corriente, y el
selector del encabezado desapareceria en los planes que no la contratan.

El gate por plan lo pone `main.py`, no este archivo.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..services import cuenta_corriente, listas_precio

router = APIRouter(prefix="/api", tags=["comercial"])


# ── Listas de precios ────────────────────────────────────────────────────


class ListaIn(BaseModel):
    nombre: str
    descripcion: str = ""
    es_default: bool = False
    activa: bool = True


class PrecioIn(BaseModel):
    item_id: int
    precio: float = Field(ge=0)


class AjusteMasivoIn(BaseModel):
    #: Puede ser negativo (una baja de precios). Lo que no puede es dejar los
    #: precios en cero o menos — eso lo valida el servicio.
    porcentaje: float


@router.get("/listas-precio")
def listar_listas():
    return listas_precio.listar()


@router.post("/listas-precio", status_code=201)
def crear_lista(payload: ListaIn):
    try:
        return listas_precio.crear(payload.nombre, payload.descripcion,
                                   payload.es_default)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.put("/listas-precio/{lista_id}")
def editar_lista(lista_id: int, payload: ListaIn):
    try:
        listas_precio.editar(lista_id, payload.nombre, payload.descripcion,
                             payload.activa)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


@router.delete("/listas-precio/{lista_id}", status_code=204)
def eliminar_lista(lista_id: int):
    listas_precio.eliminar(lista_id)


@router.get("/listas-precio/{lista_id}/precios")
def precios_de_lista(lista_id: int):
    return listas_precio.precios_de(lista_id)


@router.put("/listas-precio/{lista_id}/precios")
def fijar_precio(lista_id: int, payload: PrecioIn):
    listas_precio.fijar_precio(lista_id, payload.item_id, payload.precio)
    return {"ok": True}


@router.post("/listas-precio/{lista_id}/ajuste")
def ajustar_lista(lista_id: int, payload: AjusteMasivoIn):
    """Sube o baja todos los precios de la lista un porcentaje.

    Devuelve cuantos movio, y ese numero importa: si da 0 la lista estaba
    vacia, no es que el ajuste "no hizo nada".
    """
    try:
        return {"actualizados": listas_precio.ajustar_por_porcentaje(
            lista_id, payload.porcentaje
        )}
    except ValueError as e:
        raise HTTPException(422, str(e))


# ── Cuenta corriente ─────────────────────────────────────────────────────


class MovimientoCCIn(BaseModel):
    cliente_id: int
    monto: float = Field(gt=0)
    fecha: str
    concepto: str = ""
    referencia: str = ""
    medio_pago: str = "efectivo"


@router.get("/cuenta-corriente")
def listar_cuenta_corriente():
    """Los clientes con saldo, mas las tres cifras del encabezado."""
    return {
        "resumen": cuenta_corriente.resumen(),
        "clientes": cuenta_corriente.clientes_con_saldo(),
    }


@router.get("/cuenta-corriente/{cliente_id}")
def detalle_cuenta_corriente(cliente_id: int):
    return {
        "saldo": cuenta_corriente.saldo(cliente_id),
        "movimientos": cuenta_corriente.movimientos(cliente_id),
    }


@router.post("/cuenta-corriente/pagos", status_code=201)
def registrar_pago(payload: MovimientoCCIn, user: dict = Depends(get_current_user)):
    """Un abono del cliente. Resta del saldo."""
    pago_id = cuenta_corriente.create_cc_pago(
        cliente_id=payload.cliente_id, monto=payload.monto, fecha=payload.fecha,
        concepto=payload.concepto, referencia=payload.referencia,
        medio_pago=payload.medio_pago, usuario_id=int(user["id"]),
    )
    return {"id": pago_id}


@router.post("/cuenta-corriente/debitos", status_code=201)
def registrar_debito(payload: MovimientoCCIn, user: dict = Depends(get_current_user)):
    """Deuda que **no** nace de una venta de esta base.

    Es el enganche previsto para lo que se factura por SOS Contador: hoy se
    carga a mano y el dia que se cablee el puente, lo va a escribir el puente.
    Ver `app/services/cuenta_corriente.py`.
    """
    debito_id = cuenta_corriente.create_cc_debito(
        cliente_id=payload.cliente_id, monto=payload.monto, fecha=payload.fecha,
        concepto=payload.concepto, referencia=payload.referencia,
        usuario_id=int(user["id"]),
    )
    return {"id": debito_id}
