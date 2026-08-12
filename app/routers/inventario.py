"""Stock de consumibles — catalogo, depositos, existencias y movimientos.

Todo lo que hay debajo sale de LibraCommerce (ver `app/services/inventario.py`);
este router solo lo expone. Va gateado por el modulo `stock`, que se registra en
`main.py`.

**No hay un endpoint para editar un movimiento ni para borrarlo**, y es a
proposito: el ledger es aditivo. Un ajuste mal cargado se corrige con otro
ajuste, que es lo que deja el rastro de que hubo una correccion.

Los materiales de una incidencia viven aca y no en el router de incidencias
porque **comparten el gate**: sin el modulo `stock` no hay stock del cual
descontar, asi que el endpoint no tendria que existir.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..services import inventario, materiales
from ..auth import get_current_user

router = APIRouter(prefix="/api", tags=["stock"])


# ── Payloads ─────────────────────────────────────────────────────────────


class ConsumibleIn(BaseModel):
    nombre: str
    costo: float = 0.0
    stock_minimo: float = 0.0


class DepositoStockIn(BaseModel):
    nombre: str
    descripcion: str = ""
    es_default: bool = False


class AjusteIn(BaseModel):
    deposito_id: int
    #: Positiva entra, negativa sale. No admite cero — un movimiento en cero
    #: no dice nada y el motor lo rechaza por CHECK.
    cantidad: float
    nota: str = ""


class TransferenciaIn(BaseModel):
    item_id: int
    origen_id: int
    destino_id: int
    cantidad: float = Field(gt=0)
    nota: str = ""


class MaterialIn(BaseModel):
    item_id: int
    deposito_id: int
    cantidad: float = Field(gt=0)


# ── Catalogo de consumibles ──────────────────────────────────────────────


@router.get("/consumibles")
def listar_consumibles(solo_activos: bool = True):
    return inventario.listar_items(solo_activos=solo_activos)


@router.post("/consumibles", status_code=201)
def crear_consumible(payload: ConsumibleIn):
    try:
        return inventario.crear_item(payload.nombre, payload.costo, payload.stock_minimo)
    except ValueError as e:
        raise HTTPException(422, str(e))


# ── Depositos de consumibles ─────────────────────────────────────────────


@router.get("/depositos-stock")
def listar_depositos_stock():
    """Prefijo distinto de `/api/depositos` a proposito.

    Aquel es el de equipos serializados —donde esta un equipo cuando no esta
    instalado— y este es el de existencias por cantidad. Son dos conceptos
    distintos que en castellano se llaman igual; colgarlos de la misma ruta
    seria pedir que alguien los confunda.
    """
    return inventario.listar_depositos()


@router.post("/depositos-stock", status_code=201)
def crear_deposito_stock(payload: DepositoStockIn):
    try:
        return inventario.crear_deposito(
            payload.nombre, payload.descripcion, payload.es_default
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


# ── Existencias ──────────────────────────────────────────────────────────


@router.get("/consumibles/{item_id}/stock")
def stock_de(item_id: int):
    """El stock del consumible en cada deposito, incluidos los que estan en 0.

    Se devuelven los ceros a proposito: la pregunta que se le hace a esta
    pantalla es "¿de donde saco un plug?", y un deposito que falta de la lista
    es indistinguible de uno que existe y esta vacio.
    """
    return [
        {**dep, "stock": inventario.stock_actual(item_id, dep["id"])}
        for dep in inventario.listar_depositos()
    ]


@router.get("/consumibles/{item_id}/movimientos")
def movimientos_de(item_id: int, deposito_id: int):
    return inventario.movimientos(item_id, deposito_id)


@router.post("/consumibles/{item_id}/ajuste")
def ajustar(item_id: int, payload: AjusteIn, user: dict = Depends(get_current_user)):
    try:
        inventario.ajustar(
            item_id, payload.deposito_id, payload.cantidad,
            nota=payload.nota, usuario_id=int(user["id"]), fecha=datetime.now(),
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"stock": inventario.stock_actual(item_id, payload.deposito_id)}


@router.post("/consumibles/transferir")
def transferir(payload: TransferenciaIn, user: dict = Depends(get_current_user)):
    if payload.origen_id == payload.destino_id:
        raise HTTPException(422, "El depósito origen y destino deben ser distintos.")
    try:
        inventario.transferir(
            payload.item_id, payload.origen_id, payload.destino_id, payload.cantidad,
            nota=payload.nota, usuario_id=int(user["id"]), fecha=datetime.now(),
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


# ── Materiales de una incidencia ─────────────────────────────────────────


@router.get("/incidencias/{incidencia_id}/materiales")
def listar_materiales(incidencia_id: int, incluir_devueltos: bool = False):
    return materiales.listar(incidencia_id, incluir_devueltos=incluir_devueltos)


@router.post("/incidencias/{incidencia_id}/materiales", status_code=201)
def cargar_material(incidencia_id: int, payload: MaterialIn,
                    user: dict = Depends(get_current_user)):
    """Registra material consumido y **lo descuenta en el acto**.

    No espera al cierre del ticket: si el material salio de la camioneta,
    salio. Ver el docstring de `app/services/materiales.py`.
    """
    try:
        return materiales.cargar(
            incidencia_id, payload.item_id, payload.deposito_id, payload.cantidad,
            usuario_id=int(user["id"]), cuando=datetime.now(),
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/incidencias/{incidencia_id}/materiales/{material_id}", status_code=204)
def quitar_material(incidencia_id: int, material_id: int,
                    user: dict = Depends(get_current_user)):
    """Devuelve el material al deposito. **No borra la fila**: la marca y
    appendea la reversion, para que quede el rastro de quien lo saco."""
    del incidencia_id
    try:
        materiales.quitar(material_id, usuario_id=int(user["id"]), cuando=datetime.now())
    except ValueError as e:
        raise HTTPException(404, str(e))
