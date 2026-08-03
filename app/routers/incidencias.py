from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..dependencies import (
    get_equipo_repository, get_incidencia_repository, get_reemplazo_service,
)
from ..services.equipos import EquipoRepository
from ..services.incidencias import IncidenciaRepository
from ..services.reemplazo import DESTINOS, ReemplazoService

router = APIRouter(prefix="/api/incidencias", tags=["incidencias"])


class IncidenciaIn(BaseModel):
    cliente_id: int
    equipo_id: int | None = None
    tecnico_id: int | None = None
    sector_id: int | None = None
    # Hoja del catalogo de categorias ("Hardware -> Impresoras"), 2026-08-02.
    # Opcional a proposito: las 23 incidencias reales son previas al catalogo.
    categoria_id: int | None = None
    titulo: str
    descripcion: str | None = None
    estado: str = "abierto"
    prioridad: str = "media"
    horas_invertidas: float | None = None
    notas: str | None = None
    resolucion: str | None = None
    estado_facturacion: str | None = None
    activo: bool = True


class IncidenciaOut(IncidenciaIn):
    id: int
    fecha_creacion: str | None = None
    fecha_cierre: str | None = None


class ActividadIn(BaseModel):
    descripcion: str


class ActividadOut(BaseModel):
    id: int
    incidencia_id: int
    fecha: str | None
    descripcion: str | None
    usuario: str | None


class EstadoLogOut(BaseModel):
    id: int
    incidencia_id: int
    estado_anterior: str | None
    estado_nuevo: str
    fecha: str | None
    tecnico: str | None


@router.post("", status_code=201, response_model=IncidenciaOut)
def create_incidencia(
    data: IncidenciaIn,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
    user: dict = Depends(get_current_user),
):
    return incidencias.create(usuario_actor=user["username"], **data.model_dump())


@router.get("", response_model=list[IncidenciaOut])
def list_incidencias(
    cliente_id: int | None = None, estado: str | None = None,
    equipo_id: int | None = None, categoria_id: int | None = None,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
):
    return incidencias.list(
        cliente_id=cliente_id, estado=estado, equipo_id=equipo_id,
        categoria_id=categoria_id,
    )


@router.get("/{incidencia_id}", response_model=IncidenciaOut)
def get_incidencia(incidencia_id: int, incidencias: IncidenciaRepository = Depends(get_incidencia_repository)):
    incidencia = incidencias.get(incidencia_id)
    if incidencia is None:
        raise HTTPException(404, "incidencia not found")
    return incidencia


@router.put("/{incidencia_id}", response_model=IncidenciaOut)
def update_incidencia(
    incidencia_id: int, data: IncidenciaIn,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
    user: dict = Depends(get_current_user),
):
    try:
        return incidencias.update(incidencia_id, usuario_actor=user["username"], **data.model_dump())
    except KeyError:
        raise HTTPException(404, "incidencia not found")


@router.delete("/{incidencia_id}", status_code=204)
def delete_incidencia(incidencia_id: int, incidencias: IncidenciaRepository = Depends(get_incidencia_repository)):
    try:
        incidencias.delete(incidencia_id)
    except KeyError:
        raise HTTPException(404, "incidencia not found")
    from fastapi import Response
    return Response(status_code=204)


@router.get("/{incidencia_id}/actividades", response_model=list[ActividadOut])
def list_actividades(incidencia_id: int, incidencias: IncidenciaRepository = Depends(get_incidencia_repository)):
    return incidencias.list_actividades(incidencia_id)


@router.post("/{incidencia_id}/actividades", status_code=201, response_model=ActividadOut)
def add_actividad(
    incidencia_id: int, data: ActividadIn,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
    user: dict = Depends(get_current_user),
):
    return incidencias.add_actividad(incidencia_id, data.descripcion, user["username"])


@router.get("/{incidencia_id}/estados", response_model=list[EstadoLogOut])
def list_estados(incidencia_id: int, incidencias: IncidenciaRepository = Depends(get_incidencia_repository)):
    return incidencias.list_estado_log(incidencia_id)


@router.get("/{incidencia_id}/movimientos")
def list_movimientos_de_la_incidencia(
    incidencia_id: int,
    equipos: EquipoRepository = Depends(get_equipo_repository),
):
    """Los movimientos de equipo que causo este ticket — de todos los
    equipos que toco. Es la tercera fuente del timeline, junto con las
    actividades y la auditoria de estado."""
    return equipos.list_movimientos_por_incidencia(incidencia_id)


class ReemplazoIn(BaseModel):
    equipo_retirado_id: int
    equipo_sustituto_id: int | None = None
    destino: str = "service"
    motivo: str | None = None
    # Si no vienen, el destino define el sector (Service/Depósito/Baja) y
    # la ubicacion queda vacia — ver `DESTINOS` en services/reemplazo.py.
    sector_destino: str | None = None
    ubicacion_destino: str | None = None


@router.post("/{incidencia_id}/reemplazar-equipo", status_code=201)
def reemplazar_equipo(
    incidencia_id: int,
    data: ReemplazoIn,
    reemplazos: ReemplazoService = Depends(get_reemplazo_service),
    user: dict = Depends(get_current_user),
):
    """Una sola operacion actualiza los dos activos, deja los movimientos
    ligados al ticket y narra las intervenciones. Ver el docstring de
    `ReemplazoService` para el por que."""
    if data.destino not in DESTINOS:
        raise HTTPException(422, f"destino invalido: {data.destino}")
    try:
        return reemplazos.reemplazar(
            incidencia_id,
            equipo_retirado_id=data.equipo_retirado_id,
            equipo_sustituto_id=data.equipo_sustituto_id,
            destino=data.destino,
            motivo=data.motivo,
            sector_destino=data.sector_destino,
            ubicacion_destino=data.ubicacion_destino,
            usuario_actor=user["username"],
        )
    except KeyError as err:
        que, cual = err.args[0]
        raise HTTPException(404, f"{que} {cual} not found")
    except ValueError as err:
        raise HTTPException(422, str(err))
