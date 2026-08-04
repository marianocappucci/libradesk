"""Equipos de trabajo y flota de vehículos (pedido 42, fase A).

Dos recursos bajo el mismo router porque son la misma pregunta —quién sale y en
qué— y la asignación los cruza. Ver `app/services/equipos_trabajo.py` para por
qué la disponibilidad de esta fase es la asignación equipo↔vehículo y no una
agenda.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..dependencies import get_equipo_trabajo_repository
from ..services.equipos_trabajo import EquipoTrabajoRepository

router = APIRouter(prefix="/api/equipos-trabajo", tags=["equipos-trabajo"])


class EquipoIn(BaseModel):
    nombre: str
    responsable_id: int | None = None
    observaciones: str | None = None
    # La lista completa, no un diff: la pantalla manda el juego entero y así no
    # quedan integrantes fantasma al sacar dos personas a la vez.
    integrantes: list[int] = []
    activo: bool = True


class VehiculoIn(BaseModel):
    patente: str
    marca: str | None = None
    modelo: str | None = None
    anio: int | None = None
    observaciones: str | None = None
    # `asignado` no entra: lo escribe la asignación.
    estado: str | None = None


class VehiculoUpdate(BaseModel):
    patente: str | None = None
    marca: str | None = None
    modelo: str | None = None
    anio: int | None = None
    observaciones: str | None = None
    estado: str | None = None


class AsignarIn(BaseModel):
    equipo_id: int


class DesasignarIn(BaseModel):
    # Un vehículo que sale del equipo porque se rompió va a `en_taller`, no a
    # `disponible`.
    estado: str = "disponible"


def _404(e: KeyError) -> HTTPException:
    que = e.args[0][0] if isinstance(e.args[0], tuple) else "recurso"
    return HTTPException(404, f"{que} not found")


# ── Equipos ──────────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_equipo(
    data: EquipoIn, equipos: EquipoTrabajoRepository = Depends(get_equipo_trabajo_repository),
):
    try:
        return equipos.create(
            data.nombre, responsable_id=data.responsable_id,
            observaciones=data.observaciones, integrantes=data.integrantes,
        )
    except KeyError as e:
        raise _404(e)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("")
def list_equipos(
    solo_activos: bool = False,
    equipos: EquipoTrabajoRepository = Depends(get_equipo_trabajo_repository),
):
    return equipos.list(solo_activos=solo_activos)


# Antes de `/{equipo_id}`: con el orden invertido FastAPI matchea "vehiculos"
# contra la ruta con parámetro y devuelve un 422 por no ser un int.
@router.get("/vehiculos")
def list_vehiculos(
    estado: str | None = None, equipo_id: int | None = None,
    disponibles: bool | None = None,
    equipos: EquipoTrabajoRepository = Depends(get_equipo_trabajo_repository),
):
    """`disponibles=true` es lo que alimenta el selector de asignar: sólo los
    que pueden salir hoy."""
    return equipos.list_vehiculos(
        estado=estado, equipo_id=equipo_id, disponibles=disponibles,
    )


@router.post("/vehiculos", status_code=201)
def create_vehiculo(
    data: VehiculoIn, equipos: EquipoTrabajoRepository = Depends(get_equipo_trabajo_repository),
):
    try:
        return equipos.create_vehiculo(**data.model_dump())
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/vehiculos/{vehiculo_id}")
def get_vehiculo(
    vehiculo_id: int, equipos: EquipoTrabajoRepository = Depends(get_equipo_trabajo_repository),
):
    v = equipos.get_vehiculo(vehiculo_id)
    if v is None:
        raise HTTPException(404, "vehiculo not found")
    return v


@router.put("/vehiculos/{vehiculo_id}")
def update_vehiculo(
    vehiculo_id: int, data: VehiculoUpdate,
    equipos: EquipoTrabajoRepository = Depends(get_equipo_trabajo_repository),
):
    try:
        return equipos.update_vehiculo(vehiculo_id, **data.model_dump(exclude_unset=True))
    except KeyError:
        raise HTTPException(404, "vehiculo not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/vehiculos/{vehiculo_id}", status_code=204)
def delete_vehiculo(
    vehiculo_id: int, equipos: EquipoTrabajoRepository = Depends(get_equipo_trabajo_repository),
):
    try:
        equipos.delete_vehiculo(vehiculo_id)
    except KeyError:
        raise HTTPException(404, "vehiculo not found")
    except ValueError as e:
        raise HTTPException(409, str(e))
    return Response(status_code=204)


@router.post("/vehiculos/{vehiculo_id}/asignar")
def asignar(
    vehiculo_id: int, data: AsignarIn,
    equipos: EquipoTrabajoRepository = Depends(get_equipo_trabajo_repository),
):
    """Le da el vehículo a un equipo. Es lo que contesta "en qué vehículo
    sale"."""
    try:
        return equipos.asignar(vehiculo_id, data.equipo_id)
    except KeyError as e:
        raise _404(e)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/vehiculos/{vehiculo_id}/desasignar")
def desasignar(
    vehiculo_id: int, data: DesasignarIn,
    equipos: EquipoTrabajoRepository = Depends(get_equipo_trabajo_repository),
):
    try:
        return equipos.desasignar(vehiculo_id, estado=data.estado)
    except KeyError as e:
        raise _404(e)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/{equipo_id}")
def get_equipo(
    equipo_id: int, equipos: EquipoTrabajoRepository = Depends(get_equipo_trabajo_repository),
):
    e = equipos.get(equipo_id)
    if e is None:
        raise HTTPException(404, "equipo not found")
    return e


@router.put("/{equipo_id}")
def update_equipo(
    equipo_id: int, data: EquipoIn,
    equipos: EquipoTrabajoRepository = Depends(get_equipo_trabajo_repository),
):
    try:
        return equipos.update(equipo_id, **data.model_dump())
    except KeyError as e:
        raise _404(e) if isinstance(e.args[0], tuple) else HTTPException(404, "equipo not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/{equipo_id}", status_code=204)
def delete_equipo(
    equipo_id: int, equipos: EquipoTrabajoRepository = Depends(get_equipo_trabajo_repository),
):
    """Borra el equipo y **libera sus vehículos**: quedan `disponible`, no
    apuntando a un equipo que ya no existe."""
    try:
        equipos.delete(equipo_id)
    except KeyError:
        raise HTTPException(404, "equipo not found")
    return Response(status_code=204)
