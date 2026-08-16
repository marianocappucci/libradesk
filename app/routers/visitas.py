"""Las visitas de mantenimiento de los contratos: previsualizar y generar.

Gemelo del router de cuotas, y a proposito: son el mismo acto sobre el mismo
contrato —uno devenga la plata del periodo, el otro programa el trabajo—, asi que
tienen la misma forma, el mismo parametro y la misma regla.

**`previsualizar` y `generar` son dos endpoints y no un flag**, por el mismo
motivo que alla: uno se puede llamar cuantas veces haga falta y no cambia nada,
el otro escribe. Un `dry_run=true` deja la escritura a un caracter de distancia
del que solo mira.

El parametro es una **fecha ancla** y no un "mes": la cadencia la define el
contrato (`frecuencia_visita`), asi que un trimestral cubre un bloque de tres
meses y el ancla puede caer en cualquiera de los tres.
"""
from datetime import date

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..dependencies import get_visita_service
from ..services.visitas import VisitaService

router = APIRouter(prefix="/api/visitas", tags=["visitas"])


class GenerarVisitasIn(BaseModel):
    #: El dia que cae dentro del periodo a visitar. La pantalla manda el 1 del
    #: mes elegido; el servicio resuelve de ahi el periodo real de cada contrato.
    ancla: date
    #: Para generar la visita de un contrato suelto en vez de la tanda entera.
    contrato_id: int | None = None


@router.get("/previsualizar")
def previsualizar(
    ancla: date,
    contrato_id: int | None = None,
    visitas: VisitaService = Depends(get_visita_service),
):
    """Lo que se generaria. **No escribe nada** — es un GET a proposito.

    Devuelve tambien las que ya estan generadas, marcadas: que un periodo ya
    este agendado es informacion, y una pantalla que simplemente no lo lista se
    lee como "este contrato no visita".
    """
    return visitas.previsualizar(ancla, contrato_id=contrato_id)


@router.post("/generar")
def generar(
    datos: GenerarVisitasIn,
    request: Request,
    visitas: VisitaService = Depends(get_visita_service),
):
    """Escribe las visitas que faltan del periodo.

    Idempotente: las que ya existen se saltean, y el unico parcial de la
    revision `0027` lo sostiene ademas en la base.
    """
    sesion = getattr(request.state, "usuario", None)
    usuario_id = getattr(sesion, "id", None)
    return visitas.generar(
        datos.ancla, contrato_id=datos.contrato_id,
        usuario_id=int(usuario_id) if usuario_id else None,
    )
