"""Activos — ABM del stock propio de equipos para entregar a clientes.

Deliberadamente **no** expone un endpoint para colocar o retirar: eso ocurre
contra un contrato (`/api/contratos/{id}/equipos`), que es donde vive la fecha
y el motivo. Un activo colocado desde acá sería un activo que dice estar en un
cliente sin ninguna línea que diga en cuál.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..dependencies import get_activo_repository, get_contrato_repository
from ..services.activos import ActivoRepository
from ..services.contratos import ContratoRepository

router = APIRouter(prefix="/api/activos", tags=["activos"])


class ActivoIn(BaseModel):
    tipo: str
    marca: str | None = None
    modelo: str | None = None
    serial: str | None = None
    codigo_interno: str | None = None
    mac: str | None = None
    imei: str | None = None
    ip: str | None = None
    accesorios: str | None = None
    estado: str | None = None
    costo_compra: float | None = None
    fecha_compra: date | None = None
    proveedor_compra_id: int | None = None
    valor_reposicion: float | None = None
    garantia_vence: date | None = None
    observaciones: str | None = None


class ActivoUpdate(BaseModel):
    tipo: str | None = None
    marca: str | None = None
    modelo: str | None = None
    serial: str | None = None
    codigo_interno: str | None = None
    mac: str | None = None
    imei: str | None = None
    ip: str | None = None
    accesorios: str | None = None
    estado: str | None = None
    costo_compra: float | None = None
    fecha_compra: date | None = None
    proveedor_compra_id: int | None = None
    valor_reposicion: float | None = None
    garantia_vence: date | None = None
    observaciones: str | None = None


class ActivoOut(BaseModel):
    id: int
    tipo: str
    marca: str | None
    modelo: str | None
    serial: str | None
    codigo_interno: str | None
    descripcion: str
    mac: str | None
    imei: str | None
    ip: str | None
    accesorios: str | None
    estado: str
    costo_compra: float | None
    fecha_compra: str | None
    proveedor_compra_id: int | None
    valor_reposicion: float | None
    garantia_vence: str | None
    observaciones: str | None
    created_at: str | None
    # Dónde está colocado, derivado de la línea de contrato abierta.
    contrato_id: int | None
    contrato_numero: str | None
    cliente_id: int | None
    cliente_nombre: str | None


@router.post("", status_code=201, response_model=ActivoOut)
def create_activo(
    data: ActivoIn, activos: ActivoRepository = Depends(get_activo_repository),
):
    try:
        return activos.create(**data.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("", response_model=list[ActivoOut])
def list_activos(
    estado: str | None = None,
    disponibles: bool | None = None,
    cliente_id: int | None = None,
    tipo: str | None = None,
    activos: ActivoRepository = Depends(get_activo_repository),
):
    """`disponibles=true` es lo que alimenta el selector de "colocar equipo":
    sólo lo que se puede entregar hoy."""
    return activos.list(
        estado=estado, disponibles=disponibles, cliente_id=cliente_id, tipo=tipo,
    )


@router.get("/resumen")
def resumen_activos(activos: ActivoRepository = Depends(get_activo_repository)):
    """Cuántos hay en cada estado. **Antes que `/{activo_id}`** en el archivo:
    con el orden invertido, FastAPI matchea `/resumen` contra la ruta con
    parámetro y devuelve un 422 por "resumen" no siendo un int."""
    return activos.resumen()


@router.get("/{activo_id}", response_model=ActivoOut)
def get_activo(
    activo_id: int, activos: ActivoRepository = Depends(get_activo_repository),
):
    a = activos.get(activo_id)
    if a is None:
        raise HTTPException(404, "activo not found")
    return a


@router.get("/{activo_id}/historial")
def historial_activo(
    activo_id: int,
    activos: ActivoRepository = Depends(get_activo_repository),
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    """Por dónde pasó: cada contrato en el que estuvo, con sus fechas."""
    if activos.get(activo_id) is None:
        raise HTTPException(404, "activo not found")
    return contratos.historial_activo(activo_id)


@router.get("/{activo_id}/linea-de-tiempo")
def linea_de_tiempo(
    activo_id: int,
    activos: ActivoRepository = Depends(get_activo_repository),
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    """Todo lo que le pasó, en una sola secuencia: contratos, movimientos y
    pasos por service. Es lo que `/historial` no puede contestar por sí solo —
    dice en qué contratos estuvo, pero no qué le pasó entre dos de ellos."""
    if activos.get(activo_id) is None:
        raise HTTPException(404, "activo not found")
    return contratos.linea_de_tiempo(activo_id)


@router.put("/{activo_id}", response_model=ActivoOut)
def update_activo(
    activo_id: int, data: ActivoUpdate,
    activos: ActivoRepository = Depends(get_activo_repository),
):
    try:
        return activos.update(activo_id, **data.model_dump(exclude_unset=True))
    except KeyError:
        raise HTTPException(404, "activo not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/{activo_id}", status_code=204)
def delete_activo(
    activo_id: int, activos: ActivoRepository = Depends(get_activo_repository),
):
    try:
        activos.delete(activo_id)
    except KeyError:
        raise HTTPException(404, "activo not found")
    except ValueError as e:
        raise HTTPException(409, str(e))
    return Response(status_code=204)
