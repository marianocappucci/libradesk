"""Ventas y recibos. **Sin emision de factura** — eso lo hace SOS Contador.

Una venta de LibraDesk es el comprobante interno: que se vendio, a quien, a que
precio y como se cobro. El comprobante fiscal sale despues, por el puente de
`facturacion_externa`. Ver `app/services/ventas.py`.

Gate por plan: `ventas`, puesto en `main.py`.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from libracore import medios_pago
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..dependencies import get_cliente_repository, get_remito_service
from ..services import recibos, ventas
from ..services.clientes import ClienteRepository
from ..services.remitos_presupuestos import RemitoService

router = APIRouter(prefix="/api", tags=["ventas"])


class ItemVentaIn(BaseModel):
    #: `None` = linea de servicio: se cobra y no mueve stock.
    item_id: int | None = None
    descripcion: str
    cantidad: float = Field(gt=0)
    precio: float = Field(ge=0)


class PagoVentaIn(BaseModel):
    medio: str
    monto: float = Field(gt=0)
    referencia: str = ""


class VentaIn(BaseModel):
    cliente_id: int | None = None
    items: list[ItemVentaIn]
    pagos: list[PagoVentaIn] = []
    #: De que deposito sale la mercaderia. Obligatorio aunque la venta sea toda
    #: de servicios: el motor lo pide igual y una venta sin deposito no se
    #: puede corregir despues.
    deposito_id: int
    notas: str = ""
    sucursal_id: int | None = None


class AnulacionIn(BaseModel):
    motivo: str = ""


class ConversionIn(BaseModel):
    #: Solo para una venta cargada sin cliente. Ver el endpoint.
    cliente_id: int | None = None


# ── Ventas ───────────────────────────────────────────────────────────────


@router.get("/medios-pago")
def medios_de_pago() -> list[dict]:
    """`[{id, label}]` para el selector de cobro.

    🔴 **La lista es del motor.** El frontend tenía la suya —`MEDIOS` en
    `VentasComercial.tsx`, espejo de la tupla del backend— y las dos divergían
    de la canónica en las dos direcciones: tenían `tarjeta` (que ya no se
    escribe, se parte en débito y crédito) y les faltaban `mercadopago`,
    `cuenta_dni` y `billetera`.

    La cuenta corriente **sí** se ofrece acá, a diferencia de los productos de
    turnos: en este POS es un medio real —"se lo lleva a cuenta"— y es el único
    que genera deuda. Ver `services/ventas.MEDIOS_PAGO`.
    """
    return medios_pago.para_selector()


@router.get("/ventas")
def listar_ventas(limit: int = 200, sucursal_id: int | None = None):
    """`sucursal_id` filtra por `sales.branch_id`.

    ⚠️ **Los recibos y la cuenta corriente de más abajo NO filtran**, y no es un
    olvido: el saldo de un cliente es uno solo entre sucursales. Ver
    `comercial.listar_sucursales()`.
    """
    return ventas.listar(limit=limit, sucursal_id=sucursal_id)


@router.get("/ventas/{venta_id}")
def obtener_venta(venta_id: int):
    venta = ventas.obtener(venta_id)
    if venta is None:
        raise HTTPException(404, "La venta no existe.")
    return venta


@router.post("/ventas", status_code=201)
def crear_venta(payload: VentaIn, user: dict = Depends(get_current_user)):
    """Crea, confirma (descuenta stock) y registra los pagos, en una transaccion.

    Devuelve 422 con el disponible cuando el stock no alcanza — la venta no
    queda a medias.
    """
    try:
        return ventas.crear(
            payload.cliente_id,
            [i.model_dump() for i in payload.items],
            [p.model_dump() for p in payload.pagos],
            deposito_id=payload.deposito_id, notas=payload.notas,
            sucursal_id=payload.sucursal_id, usuario_id=int(user["id"]),
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/ventas/{venta_id}/convertir-en-remito", status_code=201)
def convertir_venta_en_remito(
    venta_id: int,
    payload: ConversionIn | None = None,
    remitos: RemitoService = Depends(get_remito_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
    user: dict = Depends(get_current_user),
):
    """El remito de una venta, que es su camino a facturacion.

    Es el gemelo de `/api/presupuestos/{id}/convertir-en-remito` y del de
    reclamos: la bandeja acepta solo remitos, asi que todo lo facturable llega
    convirtiendose.

    `cliente_id` en el cuerpo es **opcional y solo se usa cuando la venta se
    cargo sin cliente** — el mostrador. Con la venta ya identificada, mandar uno
    distinto da 409: la venta dice a quien se le vendio.

    Idempotente: el segundo click devuelve el remito que ya existe, con 201
    igual. Devolver 200 en ese caso obligaria a la pantalla a distinguir dos
    respuestas que significan lo mismo — "el remito de esta venta es este".
    """
    try:
        return ventas.convertir_a_remito(
            venta_id, remitos, clientes,
            cliente_id=payload.cliente_id if payload else None,
            usuario_id=int(user["id"]),
        )
    except KeyError:
        raise HTTPException(404, "La venta no existe.")
    except ValueError as e:
        raise HTTPException(409, str(e))


# ── Recibos ──────────────────────────────────────────────────────────────


@router.get("/recibos")
def listar_recibos(desde: str = "", hasta: str = "", q: str = "",
                   cliente_id: int = 0, limit: int = 200):
    return recibos.listar(desde=desde, hasta=hasta, q=q,
                          cliente_id=cliente_id or None, limit=limit)


@router.get("/recibos/{recibo_id}")
def obtener_recibo(recibo_id: int):
    recibo = recibos.obtener(recibo_id)
    if recibo is None:
        raise HTTPException(404, "El recibo no existe.")
    return recibo


@router.get("/recibos/{recibo_id}/pdf")
def recibo_pdf(recibo_id: int):
    """El comprobante para entregar o mandar por mail.

    `inline` y no `attachment`, igual que remitos y la orden de trabajo: lo
    normal es mirarlo y mandarlo a la impresora.
    """
    contenido = recibos.pdf(recibo_id)
    if contenido is None:
        raise HTTPException(404, "El recibo no existe.")
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="recibo-{recibo_id}.pdf"',
        },
    )


@router.post("/ventas/{venta_id}/recibo", status_code=201)
def emitir_recibo_de_venta(venta_id: int, user: dict = Depends(get_current_user)):
    """Idempotente: pedirlo dos veces devuelve el mismo recibo, no emite otro."""
    try:
        return recibos.emitir_de_venta(venta_id, usuario_id=int(user["id"]))
    except Exception as e:
        # `SinCobros` del motor entre otras. 422 y no 500: el pedido es
        # valido, lo que no se puede es emitir un recibo de algo sin cobros.
        raise HTTPException(422, str(e))


@router.post("/cuenta-corriente/pagos/{pago_id}/recibo", status_code=201)
def emitir_recibo_de_cobranza(pago_id: int, user: dict = Depends(get_current_user)):
    try:
        return recibos.emitir_de_cobranza(pago_id, usuario_id=int(user["id"]))
    except Exception as e:
        raise HTTPException(422, str(e))


@router.post("/recibos/{recibo_id}/anular")
def anular_recibo(recibo_id: int, payload: AnulacionIn,
                  user: dict = Depends(get_current_user)):
    """Un recibo no se borra: se anula, y queda."""
    if not recibos.anular(recibo_id, motivo=payload.motivo,
                          usuario_id=int(user["id"])):
        raise HTTPException(404, "El recibo no existe o ya estaba anulado.")
    return {"ok": True}
