from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from ..dependencies import get_cliente_repository
from ..services.clientes import ClienteRepository

router = APIRouter(prefix="/api/clientes", tags=["clientes"])


class ClienteIn(BaseModel):
    nombre: str
    empresa: str | None = None
    email: str | None = None
    telefono: str | None = None
    ciudad: str | None = None
    observaciones: str | None = None
    tipo_facturacion: str = "por_servicio"
    activo: bool = True


class ClienteOut(ClienteIn):
    id: int
    fecha_creacion: str | None = None


@router.post("", status_code=201, response_model=ClienteOut)
def create_cliente(data: ClienteIn, clientes: ClienteRepository = Depends(get_cliente_repository)):
    try:
        return clientes.create(**data.model_dump())
    except IntegrityError:
        raise HTTPException(409, "cliente ya existe (email duplicado)")


@router.get("", response_model=list[ClienteOut])
def list_clientes(solo_activos: bool = False, clientes: ClienteRepository = Depends(get_cliente_repository)):
    return clientes.list(solo_activos=solo_activos)


@router.get("/{cliente_id}", response_model=ClienteOut)
def get_cliente(cliente_id: int, clientes: ClienteRepository = Depends(get_cliente_repository)):
    cliente = clientes.get(cliente_id)
    if cliente is None:
        raise HTTPException(404, "cliente not found")
    return cliente


@router.put("/{cliente_id}", response_model=ClienteOut)
def update_cliente(cliente_id: int, data: ClienteIn, clientes: ClienteRepository = Depends(get_cliente_repository)):
    try:
        return clientes.update(cliente_id, **data.model_dump())
    except KeyError:
        raise HTTPException(404, "cliente not found")
    except IntegrityError:
        raise HTTPException(409, "cliente ya existe (email duplicado)")


@router.delete("/{cliente_id}", status_code=204)
def delete_cliente(cliente_id: int, clientes: ClienteRepository = Depends(get_cliente_repository)):
    try:
        clientes.delete(cliente_id)
    except KeyError:
        raise HTTPException(404, "cliente not found")
    except IntegrityError:
        raise HTTPException(409, "cliente tiene equipos/incidencias asociadas")
    return Response(status_code=204)
