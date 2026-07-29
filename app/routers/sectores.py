from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from ..dependencies import get_sector_repository
from ..services.sectores import SectorRepository

router = APIRouter(prefix="/api/sectores", tags=["sectores"])


class SectorIn(BaseModel):
    cliente_id: int
    nombre: str


class SectorUpdate(BaseModel):
    nombre: str


class SectorOut(BaseModel):
    id: int
    cliente_id: int
    nombre: str


@router.post("", status_code=201, response_model=SectorOut)
def create_sector(data: SectorIn, sectores: SectorRepository = Depends(get_sector_repository)):
    try:
        return sectores.create(data.cliente_id, data.nombre)
    except IntegrityError:
        raise HTTPException(409, "sector ya existe para este cliente")


@router.get("", response_model=list[SectorOut])
def list_sectores(cliente_id: int | None = None, sectores: SectorRepository = Depends(get_sector_repository)):
    return sectores.list(cliente_id=cliente_id)


@router.put("/{sector_id}", response_model=SectorOut)
def update_sector(sector_id: int, data: SectorUpdate, sectores: SectorRepository = Depends(get_sector_repository)):
    try:
        return sectores.update(sector_id, data.nombre)
    except KeyError:
        raise HTTPException(404, "sector not found")


@router.delete("/{sector_id}", status_code=204)
def delete_sector(sector_id: int, sectores: SectorRepository = Depends(get_sector_repository)):
    try:
        sectores.delete(sector_id)
    except KeyError:
        raise HTTPException(404, "sector not found")
    return Response(status_code=204)
