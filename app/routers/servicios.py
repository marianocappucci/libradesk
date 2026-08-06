"""Catalogo de servicios: ABM y el buscador que alimenta las sugerencias.

El ABM es admin-only; **el buscador no**, porque quien arma un presupuesto es
staff. Cerrarlo dejaria el catalogo cargado y sin nadie que pueda usarlo, que
es el escenario que este pedido viene a evitar. Ver el montaje en `main.py`.
"""
from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel, Field

from ..dependencies import get_servicio_repository
from ..services.servicios import ServicioRepository

router = APIRouter(prefix="/api/servicios", tags=["servicios"])


class ServicioIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    descripcion: str = Field(default="", max_length=500)
    precio: float = Field(default=0, ge=0)


class ServicioUpdate(ServicioIn):
    activo: bool = True


class ServicioOut(BaseModel):
    id: int
    nombre: str
    descripcion: str
    # El texto que va al comprobante, ya resuelto (descripcion, o el nombre si
    # esta vacia). La pantalla no repite la regla.
    texto: str
    precio: float
    activo: bool


@router.get("", response_model=list[ServicioOut])
def listar(
    incluir_inactivos: bool = False,
    servicios: ServicioRepository = Depends(get_servicio_repository),
):
    return servicios.listar(incluir_inactivos=incluir_inactivos)


@router.get("/buscar", response_model=list[ServicioOut])
def buscar(q: str = "", servicios: ServicioRepository = Depends(get_servicio_repository)):
    """Las sugerencias del formulario de comprobante.

    Ruta literal declarada ANTES de `/{servicio_id}` a proposito: las dos
    tienen la misma forma y FastAPI matchea en orden de registro, asi que al
    reves "buscar" caeria en la otra y fallaria al convertirlo a int.
    """
    return servicios.buscar(q)


@router.get("/{servicio_id}", response_model=ServicioOut)
def obtener(servicio_id: int, servicios: ServicioRepository = Depends(get_servicio_repository)):
    s = servicios.get(servicio_id)
    if s is None:
        raise HTTPException(404, "servicio not found")
    return s


@router.post("", status_code=201, response_model=ServicioOut)
def crear(data: ServicioIn, servicios: ServicioRepository = Depends(get_servicio_repository)):
    return servicios.crear(data.nombre, data.descripcion, data.precio)


@router.put("/{servicio_id}", response_model=ServicioOut)
def actualizar(
    servicio_id: int,
    data: ServicioUpdate,
    servicios: ServicioRepository = Depends(get_servicio_repository),
):
    s = servicios.actualizar(
        servicio_id, data.nombre, data.descripcion, data.precio, data.activo,
    )
    if s is None:
        raise HTTPException(404, "servicio not found")
    return s


@router.delete("/{servicio_id}", status_code=204)
def borrar(servicio_id: int, servicios: ServicioRepository = Depends(get_servicio_repository)):
    """Borra de verdad: ningun comprobante lo referencia. Aun asi la pantalla
    ofrece desactivar primero."""
    if not servicios.borrar(servicio_id):
        raise HTTPException(404, "servicio not found")
