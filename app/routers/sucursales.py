"""Sucursales de la empresa.

**No va gateado por plan**, y por eso es un router propio en vez de viajar con
los modulos comerciales: una sucursal es estructura de la empresa, igual que un
sector o una categoria. Un LibraDesk basico puede tener dos sucursales; lo que
se contrata es que se pueda vender o comprar en ellas, no que existan.

**Que filtra por sucursal y que no** esta decidido y documentado en
`comercial.listar_sucursales()`: filtran los modulos comerciales --stock,
depositos, ventas, compras, listas de precio-- y no filtran ni la mesa de ayuda
ni la cuenta corriente, que es unica por cliente entre sucursales.

**No hay borrado, solo baja logica**, porque las cuatro columnas `branch_id`
del motor no tienen FK contra esta tabla. Ver
`comercial.cambiar_estado_sucursal()`.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import comercial

router = APIRouter(prefix="/api", tags=["sucursales"])


class SucursalIn(BaseModel):
    nombre: str
    codigo: str = ""
    direccion: str = ""


class EstadoIn(BaseModel):
    activa: bool


@router.get("/sucursales")
def listar(solo_activas: bool = True):
    return comercial.listar_sucursales(solo_activas=solo_activas)


@router.post("/sucursales", status_code=201)
def crear(payload: SucursalIn):
    try:
        return comercial.crear_sucursal(payload.nombre, payload.codigo,
                                        payload.direccion)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.put("/sucursales/{sucursal_id}")
def editar(sucursal_id: int, payload: SucursalIn):
    try:
        comercial.editar_sucursal(sucursal_id, payload.nombre, payload.codigo,
                                  payload.direccion)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


@router.post("/sucursales/{sucursal_id}/estado")
def cambiar_estado(sucursal_id: int, payload: EstadoIn):
    """Baja y alta lógicas. **No hay `DELETE` a propósito** — ver el servicio."""
    try:
        comercial.cambiar_estado_sucursal(sucursal_id, payload.activa)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}
