"""Sucursales de la empresa.

**No va gateado por plan**, y por eso es un router propio en vez de viajar con
los modulos comerciales: una sucursal es estructura de la empresa, igual que un
sector o una categoria. Un LibraDesk basico puede tener dos sucursales; lo que
se contrata es que se pueda vender o comprar en ellas, no que existan.

El alcance de hoy es corto a proposito --tabla, ABM y selector en el
encabezado; **ninguna pantalla filtra por sucursal todavia**-- porque la
decision de fondo depende del cliente. Ver `app/services/comercial.py`.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import comercial

router = APIRouter(prefix="/api", tags=["sucursales"])


class SucursalIn(BaseModel):
    nombre: str
    codigo: str = ""
    direccion: str = ""


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
