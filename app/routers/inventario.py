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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..services import inventario, materiales
from ..services.fecha import ahora as _ahora
from ..auth import get_current_user

router = APIRouter(prefix="/api", tags=["stock"])


# ── Payloads ─────────────────────────────────────────────────────────────


class ConsumibleIn(BaseModel):
    nombre: str
    costo: float = 0.0
    stock_minimo: float = 0.0
    precio: float = 0.0
    unidad: str = "u"
    descripcion: str = ""
    categoria_id: int | None = None
    #: Solo en el alta. Para agregar otro codigo hay endpoint dedicado.
    codigo: str = ""
    activo: bool = True


class DepositoStockIn(BaseModel):
    nombre: str
    descripcion: str = ""
    es_default: bool = False
    #: La sucursal a la que pertenece. Va a `locations.branch_id`, que el motor
    #: ya declara sin FK. Ver `app/services/comercial.py`.
    sucursal_id: int | None = None
    activo: bool = True


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
        return inventario.crear_item(
            payload.nombre, payload.costo, payload.stock_minimo,
            precio=payload.precio, unidad=payload.unidad,
            descripcion=payload.descripcion, categoria_id=payload.categoria_id,
            codigo=payload.codigo,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.put("/consumibles/{item_id}")
def editar_consumible(item_id: int, payload: ConsumibleIn):
    try:
        inventario.editar_item(
            item_id, nombre=payload.nombre, costo=payload.costo,
            stock_minimo=payload.stock_minimo, precio=payload.precio,
            unidad=payload.unidad, descripcion=payload.descripcion,
            categoria_id=payload.categoria_id, activo=payload.activo,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


@router.delete("/consumibles/{item_id}", status_code=204)
def dar_de_baja_consumible(item_id: int):
    """Baja **logica**: el consumible deja de ofrecerse y sus movimientos
    historicos quedan intactos. Ver `inventario.baja_item()`."""
    try:
        inventario.baja_item(item_id)
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
            payload.nombre, payload.descripcion, payload.es_default,
            sucursal_id=payload.sucursal_id,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.put("/depositos-stock/{deposito_id}")
def editar_deposito_stock(deposito_id: int, payload: DepositoStockIn):
    try:
        inventario.editar_deposito(
            deposito_id, payload.nombre, payload.descripcion,
            activo=payload.activo, sucursal_id=payload.sucursal_id,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


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
            nota=payload.nota, usuario_id=int(user["id"]), fecha=_ahora(),
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
            nota=payload.nota, usuario_id=int(user["id"]), fecha=_ahora(),
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
            usuario_id=int(user["id"]), cuando=_ahora(),
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
        materiales.quitar(material_id, usuario_id=int(user["id"]), cuando=_ahora())
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── Categorias ───────────────────────────────────────────────────────────


class CategoriaIn(BaseModel):
    nombre: str
    parent_id: int | None = None


@router.get("/consumibles-categorias")
def listar_categorias():
    return inventario.listar_categorias()


@router.post("/consumibles-categorias", status_code=201)
def crear_categoria(payload: CategoriaIn):
    try:
        return inventario.crear_categoria(payload.nombre, payload.parent_id)
    except ValueError as e:
        raise HTTPException(422, str(e))


# ── Codigos ──────────────────────────────────────────────────────────────


class CodigoIn(BaseModel):
    codigo: str
    principal: bool = False


@router.get("/consumibles/{item_id}/codigos")
def listar_codigos(item_id: int):
    return inventario.codigos_de(item_id)


@router.post("/consumibles/{item_id}/codigos", status_code=201)
def agregar_codigo(item_id: int, payload: CodigoIn):
    try:
        return inventario.agregar_codigo(item_id, payload.codigo, payload.principal)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/consumibles-buscar")
def buscar_por_codigo(codigo: str):
    """Busqueda exacta por codigo. 404 si no hay, para que el front distinga
    "no existe" de "existe y esta en cero" sin mirar el cuerpo."""
    item = inventario.buscar_por_codigo(codigo)
    if item is None:
        raise HTTPException(404, "No hay ningun consumible con ese codigo.")
    return item


# ── La vista de conjunto ─────────────────────────────────────────────────


@router.get("/stock/grilla")
def grilla_stock():
    return inventario.grilla_stock()


@router.get("/stock/bajo-minimo")
def stock_bajo_minimo():
    return inventario.bajo_minimo()
