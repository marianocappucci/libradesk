"""Depositos propios y de cliente, y el movimiento de equipos entre ellos.

La transferencia cuelga de aca y no de `/api/equipos` porque es la operacion
de la pantalla de depositos —"sacar estos doce del taller"—, y porque mover
un lote es un solo hecho: ver `EquipoRepository.mover_a_deposito()`.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..dependencies import get_deposito_repository, get_equipo_repository
from ..services.depositos import (
    ClienteAjeno, DepositoEnUso, DepositoRepository, NombreRepetido,
)
from ..services.equipos import EquipoRepository

router = APIRouter(prefix="/api/depositos", tags=["depositos"])


class DepositoIn(BaseModel):
    nombre: str = Field(min_length=1)
    # None = deposito propio de la empresa. Ver services/depositos.py.
    cliente_id: int | None = None
    descripcion: str | None = None


class DepositoUpdate(BaseModel):
    nombre: str = Field(min_length=1)
    descripcion: str | None = None
    activo: bool = True


class DepositoOut(BaseModel):
    id: int
    cliente_id: int | None
    cliente_nombre: str | None
    nombre: str
    descripcion: str | None
    activo: bool
    es_default: bool
    total_equipos: int | None
    created_at: str | None


class TransferenciaIn(BaseModel):
    equipo_ids: list[int] = Field(min_length=1)
    # None = sacarlos del deposito y devolverlos al puesto del cliente.
    destino_id: int | None = None
    motivo: str | None = None


@router.get("", response_model=list[DepositoOut])
def list_depositos(
    cliente_id: int | None = None,
    propios: bool = False,
    solo_activos: bool = False,
    depositos: DepositoRepository = Depends(get_deposito_repository),
):
    return depositos.list(cliente_id=cliente_id, propios=propios, solo_activos=solo_activos)


@router.post("", status_code=201, response_model=DepositoOut)
def create_deposito(
    data: DepositoIn,
    depositos: DepositoRepository = Depends(get_deposito_repository),
):
    try:
        return depositos.create(**data.model_dump())
    except NombreRepetido as e:
        raise HTTPException(409, str(e))


@router.get("/{deposito_id}", response_model=DepositoOut)
def get_deposito(
    deposito_id: int,
    depositos: DepositoRepository = Depends(get_deposito_repository),
):
    deposito = depositos.get(deposito_id)
    if deposito is None:
        raise HTTPException(404, "depósito no encontrado")
    return deposito


@router.put("/{deposito_id}", response_model=DepositoOut)
def update_deposito(
    deposito_id: int,
    data: DepositoUpdate,
    depositos: DepositoRepository = Depends(get_deposito_repository),
):
    try:
        return depositos.update(deposito_id, **data.model_dump())
    except KeyError:
        raise HTTPException(404, "depósito no encontrado")
    except NombreRepetido as e:
        raise HTTPException(409, str(e))


@router.post("/{deposito_id}/set-default", response_model=DepositoOut)
def set_default(
    deposito_id: int,
    depositos: DepositoRepository = Depends(get_deposito_repository),
):
    try:
        return depositos.set_default(deposito_id)
    except KeyError:
        raise HTTPException(404, "depósito no encontrado")
    except ClienteAjeno as e:
        raise HTTPException(422, str(e))


@router.delete("/{deposito_id}", status_code=204)
def delete_deposito(
    deposito_id: int,
    depositos: DepositoRepository = Depends(get_deposito_repository),
):
    try:
        depositos.delete(deposito_id)
    except KeyError:
        raise HTTPException(404, "depósito no encontrado")
    except DepositoEnUso as e:
        raise HTTPException(409, str(e))
    return Response(status_code=204)


@router.get("/{deposito_id}/equipos")
def equipos_del_deposito(
    deposito_id: int,
    depositos: DepositoRepository = Depends(get_deposito_repository),
):
    if depositos.get(deposito_id) is None:
        raise HTTPException(404, "depósito no encontrado")
    return depositos.equipos(deposito_id)


@router.post("/transferir")
def transferir(
    data: TransferenciaIn,
    equipos: EquipoRepository = Depends(get_equipo_repository),
    user: dict = Depends(get_current_user),
):
    """Mueve un lote de equipos a un deposito, o los saca de todos.

    Devuelve los equipos ya movidos —no un `{"ok": true}`— para que la
    pantalla pinte el resultado sin volver a pedir la lista, y para que un
    test pueda afirmar donde quedo cada uno.
    """
    try:
        return equipos.mover_a_deposito(
            data.equipo_ids, data.destino_id,
            usuario_actor=user["username"], motivo=data.motivo,
        )
    except KeyError as e:
        raise HTTPException(404, f"equipo {e.args[0]} no encontrado")
    except ClienteAjeno as e:
        raise HTTPException(422, str(e))
