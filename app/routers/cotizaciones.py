"""La cotización del dólar, por día.

Router chico a propósito: la tabla es la **fuente** que la pantalla ofrece al
armar una pre-factura, y el comprobante congela la que usó. Ver
`app/services/cotizaciones.py` para por qué esas dos cosas son distintas.
"""
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..dependencies import get_cotizacion_repository
from ..services.cotizaciones import CotizacionRepository

router = APIRouter(prefix="/api/cotizaciones", tags=["cotizaciones"])


class CotizacionIn(BaseModel):
    fecha: date_type = Field(default_factory=date_type.today)
    #: Pesos por dólar. `gt=0` acá y también en el servicio: la pantalla no es
    #: el único llamador — el día que otro proceso la escriba, la guarda sigue.
    valor: float = Field(gt=0)
    observaciones: str | None = None


@router.get("")
def listar(
    limite: int = Query(90, ge=1, le=365),
    cotizaciones: CotizacionRepository = Depends(get_cotizacion_repository),
):
    return cotizaciones.list(limite)


# Antes de `/{cotizacion_id}`: FastAPI resuelve por orden de declaración.
@router.get("/vigente")
def vigente(
    fecha: str | None = Query(None, description="ISO (YYYY-MM-DD); default hoy"),
    cotizaciones: CotizacionRepository = Depends(get_cotizacion_repository),
):
    """La cotización de esa fecha, o **la última anterior**, o `null`.

    🔴 **Devuelve la fila entera, con su `fecha`.** Es lo que le permite a la
    pantalla decir *"cotización del 03-09"* cuando la de hoy no está cargada.
    Contestar sólo el número dejaría un tipo de cambio de doce días presentado
    como el de hoy, sin que nadie pueda notarlo.

    `null` cuando no hay ninguna cargada. **No cae a 1**: convertir a un peso
    por dólar dejaría el comprobante por una fracción de lo que vale.
    """
    if fecha is not None:
        try:
            objetivo = date_type.fromisoformat(fecha)
        except ValueError:
            raise HTTPException(422, "Fecha inválida: se espera ISO (YYYY-MM-DD)")
    else:
        objetivo = None
    return cotizaciones.vigente_a(objetivo)


@router.put("", status_code=200)
def guardar(
    data: CotizacionIn,
    cotizaciones: CotizacionRepository = Depends(get_cotizacion_repository),
    user: dict = Depends(get_current_user),
):
    """Carga o **corrige** la del día. `PUT` y no `POST` porque hay una sola por
    fecha: cargarla de nuevo es corregirla, no agregar una segunda."""
    try:
        return cotizaciones.guardar(
            data.fecha, data.valor,
            usuario=str(user.get("username") or user.get("id") or "Sistema"),
            observaciones=data.observaciones,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/{cotizacion_id}", status_code=204)
def borrar(
    cotizacion_id: int,
    cotizaciones: CotizacionRepository = Depends(get_cotizacion_repository),
):
    """Borrar una cotización **no toca ningún comprobante**: los que la usaron
    la tienen congelada adentro de sus ítems."""
    try:
        cotizaciones.delete(cotizacion_id)
    except KeyError:
        raise HTTPException(404, "cotizacion not found")
