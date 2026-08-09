"""Personal de la empresa: quien recepciona, quien ejecuta y quien vende.

El prefijo sigue siendo `/api/tecnicos` — es contrato público que consume
también el backoffice de la suite, y renombrarlo sería un cambio ancho que el
pedido 41 no pedía. En la UI el módulo se llama **Personal**. Ver el docstring
de `services/tecnicos.py` para por qué el catálogo es uno solo y por qué los
roles son banderas y no un campo `rol`.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from ..dependencies import get_tecnico_repository
from ..services.tecnicos import TecnicoRepository

router = APIRouter(prefix="/api/tecnicos", tags=["tecnicos"])


class TecnicoIn(BaseModel):
    nombre: str
    activo: bool = True
    # Los roles son independientes: la misma persona puede ser técnica y
    # vendedora. `es_tecnico` arranca en True para que un alta sin roles
    # explícitos se comporte igual que antes del pedido 41.
    es_tecnico: bool = True
    es_recepcionista: bool = False
    es_vendedor: bool = False
    # Quien manda un equipo de trabajo (pedido 42, 2026-08-04).
    es_responsable: bool = False


def _roles(data: "TecnicoIn") -> dict[str, bool]:
    """Las banderas de rol, sacadas del modelo por nombre.

    Enumerarlas a mano en cada endpoint era lo que hacía que sumar la cuarta
    tocara ocho lugares; el servicio también las resuelve desde `ROLES`.
    """
    return {campo: getattr(data, campo) for campo in vars(data) if campo.startswith("es_")}


class TecnicoOut(TecnicoIn):
    id: int
    # Derivado, para no armar el texto en cada fila de la tabla.
    roles: list[str]


@router.post("", status_code=201, response_model=TecnicoOut)
def create_tecnico(data: TecnicoIn, tecnicos: TecnicoRepository = Depends(get_tecnico_repository)):
    try:
        return tecnicos.create(data.nombre, data.activo, **_roles(data))
    except ValueError as e:
        raise HTTPException(409, str(e))
    except IntegrityError:
        raise HTTPException(409, "tecnico ya existe")


@router.get("", response_model=list[TecnicoOut])
def list_tecnicos(
    solo_activos: bool = False, rol: str | None = None,
    tecnicos: TecnicoRepository = Depends(get_tecnico_repository),
):
    """`rol` (`tecnico` | `recepcionista` | `vendedor` | `responsable`) es lo que
    alimenta cada selector: el de recepcionista del ticket sólo ofrece
    recepcionistas, y el de responsable del equipo sólo responsables."""
    try:
        return tecnicos.list(solo_activos=solo_activos, rol=rol)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.put("/{tecnico_id}", response_model=TecnicoOut)
def update_tecnico(tecnico_id: int, data: TecnicoIn, tecnicos: TecnicoRepository = Depends(get_tecnico_repository)):
    try:
        return tecnicos.update(tecnico_id, data.nombre, data.activo, **_roles(data))
    except KeyError:
        raise HTTPException(404, "tecnico not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/{tecnico_id}", status_code=204)
def delete_tecnico(tecnico_id: int, tecnicos: TecnicoRepository = Depends(get_tecnico_repository)):
    """Borra un tecnico **sin papeles firmados**. Con comprobantes de ingreso o
    instalaciones en contratos no se borra: para sacarlo de circulacion esta
    `activo=False`, que conserva la historia. Mismo 409 y mismo motivo que el
    de clientes y equipos.
    """
    try:
        tecnicos.delete(tecnico_id)
    except KeyError:
        raise HTTPException(404, "tecnico not found")
    except ValueError as e:
        colgando = ", ".join(f"{n} {k}" for k, n in e.args[0].items() if n)
        raise HTTPException(
            409,
            f"El técnico tiene {colgando}. Desactivalo en vez de borrarlo.",
        )
    return Response(status_code=204)
