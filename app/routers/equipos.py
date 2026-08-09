from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..auth import get_current_user
from ..dependencies import get_equipo_repository
from ..services.depositos import ClienteAjeno
from ..services.equipos import EquipoRepository

router = APIRouter(prefix="/api/equipos", tags=["equipos"])


class EquipoIn(BaseModel):
    cliente_id: int
    tipo: str
    modelo: str | None = None
    marca: str | None = None
    serial: str | None = None
    ubicacion_oficina: str | None = None
    sector: str | None = None
    # Donde esta guardado. None = instalado en el sector del cliente.
    deposito_id: int | None = None
    estado: str = "activo"
    garantia_vence: date | None = None
    observaciones: str | None = None


class EquipoUpdate(EquipoIn):
    # Solo para el historial: si el update genera un traslado o un cambio
    # de estado, este texto queda como motivo del movimiento. No se guarda
    # en el equipo.
    motivo: str | None = None


class EquipoOut(EquipoIn):
    id: int
    # Resuelto por el repositorio: la lista muestra donde esta el equipo sin
    # cruzar `/api/depositos` en el browser.
    deposito_nombre: str | None = None
    fecha_adicion: str | None = None
    garantia_vence: str | None = None


class MovimientoOut(BaseModel):
    id: int
    equipo_id: int
    tipo: str
    descripcion: str | None
    sector_origen: str | None
    sector_destino: str | None
    ubicacion_origen: str | None
    ubicacion_destino: str | None
    motivo: str | None
    usuario: str
    fecha: str | None
    # De que ticket vino este movimiento (None si fue una edicion suelta).
    incidencia_id: int | None


@router.post("", status_code=201, response_model=EquipoOut)
def create_equipo(
    data: EquipoIn,
    equipos: EquipoRepository = Depends(get_equipo_repository),
    user: dict = Depends(get_current_user),
):
    try:
        return equipos.create(usuario_actor=user["username"], **data.model_dump())
    except ClienteAjeno as e:
        raise HTTPException(422, str(e))


@router.get("", response_model=list[EquipoOut])
def list_equipos(
    cliente_id: int | None = None,
    deposito_id: int | None = None,
    equipos: EquipoRepository = Depends(get_equipo_repository),
):
    return equipos.list(cliente_id=cliente_id, deposito_id=deposito_id)


@router.get("/{equipo_id}", response_model=EquipoOut)
def get_equipo(equipo_id: int, equipos: EquipoRepository = Depends(get_equipo_repository)):
    equipo = equipos.get(equipo_id)
    if equipo is None:
        raise HTTPException(404, "equipo not found")
    return equipo


@router.put("/{equipo_id}", response_model=EquipoOut)
def update_equipo(
    equipo_id: int,
    data: EquipoUpdate,
    equipos: EquipoRepository = Depends(get_equipo_repository),
    user: dict = Depends(get_current_user),
):
    payload = data.model_dump()
    motivo = payload.pop("motivo", None)
    try:
        return equipos.update(
            equipo_id, usuario_actor=user["username"], motivo=motivo, **payload
        )
    except KeyError:
        raise HTTPException(404, "equipo not found")
    except ClienteAjeno as e:
        raise HTTPException(422, str(e))


@router.delete("/{equipo_id}", status_code=204)
def delete_equipo(equipo_id: int, equipos: EquipoRepository = Depends(get_equipo_repository)):
    """Borra un equipo **sin papeles**. Con comprobantes de ingreso o
    reparaciones no se borra: para sacarlo de circulacion esta el estado
    `baja`, que conserva la historia.

    Mismo 409 y mismo motivo que el de clientes: hasta el 2026-08-09 el DELETE
    pasaba igual y dejaba esas filas apuntando a un id inexistente, porque el
    pragma de FKs esta apagado en SQLite. Contra PostgreSQL las dos FK
    rechazan el borrado — la base toma la misma decision sola.
    """
    try:
        equipos.delete(equipo_id)
    except KeyError:
        raise HTTPException(404, "equipo not found")
    except ValueError as e:
        colgando = ", ".join(f"{n} {k}" for k, n in e.args[0].items() if n)
        raise HTTPException(
            409,
            f"El equipo tiene {colgando}. Dalo de baja en vez de borrarlo.",
        )
    return Response(status_code=204)


@router.get("/{equipo_id}/movimientos", response_model=list[MovimientoOut])
def list_movimientos(equipo_id: int, equipos: EquipoRepository = Depends(get_equipo_repository)):
    return equipos.list_movimientos(equipo_id)
