"""Reparaciones — abrir, listar y cerrar el paso por service de un equipo.

La reparacion tambien se abre desde `POST
/api/incidencias/{id}/reemplazar-equipo` cuando el destino es `service`, que es
el camino normal: el tecnico no entra aca a cargarla a mano, la carga en el
mismo gesto con el que retira el equipo. Este router cubre el resto — el
mantenimiento programado sin ticket, la correccion de un dato y sobre todo el
**cierre**, que ocurre dias despues y desde otra pantalla.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..dependencies import get_reparacion_repository
from ..services.reparaciones import ReparacionRepository

router = APIRouter(prefix="/api/reparaciones", tags=["reparaciones"])


class ReparacionIn(BaseModel):
    equipo_id: int
    proveedor_id: int
    fecha_envio: date
    incidencia_id: int | None = None
    remito_salida: str | None = None
    rma: str | None = None
    en_garantia: bool = False
    observaciones: str | None = None


class ReparacionCierre(BaseModel):
    fecha_retorno: date
    diagnostico: str | None = None
    costo: float | None = None
    observaciones: str | None = None


class ReparacionUpdate(BaseModel):
    proveedor_id: int | None = None
    fecha_envio: date | None = None
    remito_salida: str | None = None
    rma: str | None = None
    en_garantia: bool | None = None
    diagnostico: str | None = None
    costo: float | None = None
    observaciones: str | None = None


class ReparacionOut(BaseModel):
    id: int
    equipo_id: int
    incidencia_id: int | None
    proveedor_id: int
    proveedor_nombre: str | None
    equipo_descripcion: str | None
    equipo_serial: str | None
    cliente_id: int | None
    fecha_envio: str | None
    fecha_retorno: str | None
    abierta: bool
    dias_afuera: int | None
    remito_salida: str | None
    rma: str | None
    en_garantia: bool
    costo: float | None
    diagnostico: str | None
    observaciones: str | None
    usuario: str
    created_at: str | None


@router.post("", status_code=201, response_model=ReparacionOut)
def create_reparacion(
    data: ReparacionIn,
    reparaciones: ReparacionRepository = Depends(get_reparacion_repository),
):
    try:
        return reparaciones.create(**data.model_dump())
    except KeyError as e:
        que, _id = e.args[0]
        raise HTTPException(404, f"{que} not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("", response_model=list[ReparacionOut])
def list_reparaciones(
    equipo_id: int | None = None,
    incidencia_id: int | None = None,
    proveedor_id: int | None = None,
    cliente_id: int | None = None,
    abiertas: bool | None = None,
    reparaciones: ReparacionRepository = Depends(get_reparacion_repository),
):
    """`abiertas=true` responde "que tengo hoy en service". Sin filtro salen
    todas, con las abiertas arriba."""
    return reparaciones.list(
        equipo_id=equipo_id, incidencia_id=incidencia_id,
        proveedor_id=proveedor_id, cliente_id=cliente_id, abiertas=abiertas,
    )


@router.get("/{reparacion_id}", response_model=ReparacionOut)
def get_reparacion(
    reparacion_id: int,
    reparaciones: ReparacionRepository = Depends(get_reparacion_repository),
):
    r = reparaciones.get(reparacion_id)
    if r is None:
        raise HTTPException(404, "reparación not found")
    return r


@router.post("/{reparacion_id}/cerrar", response_model=ReparacionOut)
def cerrar_reparacion(
    reparacion_id: int, data: ReparacionCierre,
    reparaciones: ReparacionRepository = Depends(get_reparacion_repository),
):
    """Registra la vuelta del equipo. **No lo reinstala**: mover el equipo de
    vuelta a su lugar es un movimiento de inventario y lo hace "Reemplazar
    equipo", que ya sabe generar el historial correcto."""
    try:
        return reparaciones.cerrar(reparacion_id, **data.model_dump())
    except KeyError:
        raise HTTPException(404, "reparación not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.put("/{reparacion_id}", response_model=ReparacionOut)
def update_reparacion(
    reparacion_id: int, data: ReparacionUpdate,
    reparaciones: ReparacionRepository = Depends(get_reparacion_repository),
):
    try:
        return reparaciones.update(reparacion_id, **data.model_dump(exclude_unset=True))
    except KeyError:
        raise HTTPException(404, "reparación not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/{reparacion_id}", status_code=204)
def delete_reparacion(
    reparacion_id: int,
    reparaciones: ReparacionRepository = Depends(get_reparacion_repository),
):
    try:
        reparaciones.delete(reparacion_id)
    except KeyError:
        raise HTTPException(404, "reparación not found")
    return Response(status_code=204)
