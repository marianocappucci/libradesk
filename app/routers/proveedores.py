from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from ..dependencies import get_proveedor_repository
from ..services.proveedores import ProveedorRepository

router = APIRouter(prefix="/api/proveedores", tags=["proveedores"])


class ProveedorIn(BaseModel):
    nombre: str
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None
    observaciones: str | None = None


class ProveedorUpdate(BaseModel):
    nombre: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None
    observaciones: str | None = None


class ProveedorOut(BaseModel):
    id: int
    nombre: str
    contacto: str | None
    telefono: str | None
    email: str | None
    observaciones: str | None
    activo: bool


@router.post("", status_code=201, response_model=ProveedorOut)
def create_proveedor(
    data: ProveedorIn, proveedores: ProveedorRepository = Depends(get_proveedor_repository),
):
    try:
        return proveedores.create(
            data.nombre, contacto=data.contacto, telefono=data.telefono,
            email=data.email, observaciones=data.observaciones,
        )
    except IntegrityError:
        raise HTTPException(409, "ya existe un proveedor con ese nombre")


@router.get("", response_model=list[ProveedorOut])
def list_proveedores(
    solo_activos: bool = False,
    proveedores: ProveedorRepository = Depends(get_proveedor_repository),
):
    """`solo_activos=true` es lo que piden los selects: un proveedor dado de
    baja no se ofrece para una reparacion nueva, pero sigue existiendo en las
    viejas."""
    return proveedores.list(solo_activos=solo_activos)


@router.get("/{proveedor_id}", response_model=ProveedorOut)
def get_proveedor(
    proveedor_id: int, proveedores: ProveedorRepository = Depends(get_proveedor_repository),
):
    p = proveedores.get(proveedor_id)
    if p is None:
        raise HTTPException(404, "proveedor not found")
    return p


@router.put("/{proveedor_id}", response_model=ProveedorOut)
def update_proveedor(
    proveedor_id: int, data: ProveedorUpdate,
    proveedores: ProveedorRepository = Depends(get_proveedor_repository),
):
    try:
        return proveedores.update(proveedor_id, **data.model_dump(exclude_unset=True))
    except KeyError:
        raise HTTPException(404, "proveedor not found")
    except IntegrityError:
        raise HTTPException(409, "ya existe un proveedor con ese nombre")


@router.post("/{proveedor_id}/desactivar", response_model=ProveedorOut)
def desactivar_proveedor(
    proveedor_id: int, proveedores: ProveedorRepository = Depends(get_proveedor_repository),
):
    """Baja logica, que es la operacion normal para un proveedor con historial
    — mismo criterio que `clientes`."""
    try:
        return proveedores.set_activo(proveedor_id, False)
    except KeyError:
        raise HTTPException(404, "proveedor not found")


@router.post("/{proveedor_id}/activar", response_model=ProveedorOut)
def activar_proveedor(
    proveedor_id: int, proveedores: ProveedorRepository = Depends(get_proveedor_repository),
):
    try:
        return proveedores.set_activo(proveedor_id, True)
    except KeyError:
        raise HTTPException(404, "proveedor not found")


@router.delete("/{proveedor_id}", status_code=204)
def delete_proveedor(
    proveedor_id: int, proveedores: ProveedorRepository = Depends(get_proveedor_repository),
):
    """Borra un proveedor **sin reparaciones** — uno cargado por error. Para uno
    con historial esta `/desactivar`.

    El 409 lo decide el repositorio contando, no un `except IntegrityError`: el
    pragma `foreign_keys` esta apagado, asi que la base nunca levantaria ese
    error. Es la trampa que este producto ya pago con el 409 de `clientes`.
    """
    try:
        proveedores.delete(proveedor_id)
    except KeyError:
        raise HTTPException(404, "proveedor not found")
    except ValueError as e:
        colgando = e.args[0]
        raise HTTPException(
            409,
            f"Tiene {colgando['reparaciones']} reparaciones registradas. "
            f"Desactivalo en vez de borrarlo.",
        )
    return Response(status_code=204)
