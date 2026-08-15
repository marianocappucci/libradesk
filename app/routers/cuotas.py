"""El devengado de los contratos: previsualizar, generar y consultar cuotas.

**`previsualizar` y `generar` son dos endpoints y no un flag**, porque son dos
actos distintos: uno se puede llamar cuantas veces haga falta y no cambia nada;
el otro escribe. Un `POST /generar?dry_run=true` habría dejado la escritura a un
carácter de distancia del que sólo mira, y la regla del producto es que **nada se
factura sin confirmación humana** (decisión del 2026-08-07).

El parámetro de los dos es una **fecha ancla**, no un "mes": el período lo define
el contrato —periodicidad y fecha de inicio—, así que un trimestral que arranca
en febrero devenga feb-abr aunque el ancla caiga en marzo. Pedir "2026-08" habría
obligado a asumir que todos los contratos son mensuales y calendarios, y ninguna
de las dos cosas es cierta.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..dependencies import get_cuota_repository
from ..services.cuotas import CuotaRepository

router = APIRouter(prefix="/api/cuotas", tags=["cuotas"])


class GenerarIn(BaseModel):
    # El día que cae dentro del período a devengar. La pantalla manda el 1 del
    # mes elegido; el servicio resuelve de ahí el período real de cada contrato.
    ancla: date
    # Para devengar un contrato suelto en vez de la tanda entera.
    contrato_id: int | None = None


class CargoIn(BaseModel):
    tipo_cargo: str
    concepto: str
    importe: float
    fecha: date
    observaciones: str | None = None


class AnularIn(BaseModel):
    motivo: str | None = None


def _usuario(request: Request) -> str:
    sesion = getattr(request.state, "usuario", None)
    return getattr(sesion, "name", None) or getattr(sesion, "username", None) or "Sistema"


@router.get("")
def listar(
    contrato_id: int | None = None,
    estado: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    repo: CuotaRepository = Depends(get_cuota_repository),
):
    return repo.list(contrato_id=contrato_id, estado=estado, desde=desde, hasta=hasta)


@router.get("/previsualizar")
def previsualizar(
    ancla: date,
    contrato_id: int | None = None,
    repo: CuotaRepository = Depends(get_cuota_repository),
):
    """Lo que se generaría. **No escribe nada** — es un GET a propósito."""
    return repo.previsualizar(ancla, contrato_id=contrato_id)


@router.post("/generar")
def generar(
    datos: GenerarIn,
    request: Request,
    repo: CuotaRepository = Depends(get_cuota_repository),
):
    return repo.generar(
        datos.ancla, contrato_id=datos.contrato_id, usuario=_usuario(request),
    )


@router.get("/{cuota_id}")
def obtener(cuota_id: int, repo: CuotaRepository = Depends(get_cuota_repository)):
    cuota = repo.get(cuota_id)
    if cuota is None:
        raise HTTPException(404, "Cuota no encontrada")
    return cuota


@router.post("/contrato/{contrato_id}/cargo", status_code=201)
def agregar_cargo(
    contrato_id: int,
    datos: CargoIn,
    repo: CuotaRepository = Depends(get_cuota_repository),
):
    """Un cargo suelto sobre el contrato: instalación, reparación, reposición.

    Los cargos del período —`alquiler`, `proporcional`, `mantenimiento`— los
    rechaza el servicio: esos los emite «Generar cuotas», y cargarlos a mano
    dejaría dos cobros del mismo mes.
    """
    try:
        return repo.agregar_cargo(contrato_id, **datos.model_dump())
    except KeyError:
        raise HTTPException(404, "Contrato no encontrado")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/{cuota_id}/anular")
def anular(
    cuota_id: int,
    datos: AnularIn,
    repo: CuotaRepository = Depends(get_cuota_repository),
):
    try:
        return repo.anular(cuota_id, motivo=datos.motivo)
    except KeyError:
        raise HTTPException(404, "Cuota no encontrada")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
