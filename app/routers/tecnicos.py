from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from ..dependencies import get_tecnico_repository
from ..services.tecnicos import TecnicoRepository

router = APIRouter(prefix="/api/tecnicos", tags=["tecnicos"])


class TecnicoIn(BaseModel):
    nombre: str
    activo: bool = True


class TecnicoOut(TecnicoIn):
    id: int


@router.post("", status_code=201, response_model=TecnicoOut)
def create_tecnico(data: TecnicoIn, tecnicos: TecnicoRepository = Depends(get_tecnico_repository)):
    try:
        return tecnicos.create(data.nombre, data.activo)
    except IntegrityError:
        raise HTTPException(409, "tecnico ya existe")


@router.get("", response_model=list[TecnicoOut])
def list_tecnicos(solo_activos: bool = False, tecnicos: TecnicoRepository = Depends(get_tecnico_repository)):
    return tecnicos.list(solo_activos=solo_activos)


@router.put("/{tecnico_id}", response_model=TecnicoOut)
def update_tecnico(tecnico_id: int, data: TecnicoIn, tecnicos: TecnicoRepository = Depends(get_tecnico_repository)):
    try:
        return tecnicos.update(tecnico_id, data.nombre, data.activo)
    except KeyError:
        raise HTTPException(404, "tecnico not found")


@router.delete("/{tecnico_id}", status_code=204)
def delete_tecnico(tecnico_id: int, tecnicos: TecnicoRepository = Depends(get_tecnico_repository)):
    try:
        tecnicos.delete(tecnico_id)
    except KeyError:
        raise HTTPException(404, "tecnico not found")
    return Response(status_code=204)
