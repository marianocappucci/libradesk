"""Informe de servicio para el cliente.

**Router propio, y no un endpoint mas de `/api/reportes`, a proposito.** Los
seis reportes de ahi son internos: llevan tecnico, estado de cobro y costos de
service. Este es lo unico que sale de LibraDesk hacia afuera de la empresa. Que
no compartan prefijo ni modulo es la senal de que no comparten audiencia — y
evita que un campo agregado a un reporte interno se filtre al informe del
cliente por vivir en el mismo archivo.
"""
import re
import unicodedata
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ..dependencies import get_informe_service
from ..services import informe_pdf
from ..services.informes import InformeService

router = APIRouter(prefix="/api/informes", tags=["informes"])


def _slug(texto: str) -> str:
    """Nombre de archivo seguro: el del cliente puede traer tildes, barras o
    puntos, y va directo al `Content-Disposition`."""
    plano = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plano.lower()).strip("-") or "cliente"


@router.get("/cliente/{cliente_id}.pdf")
def informe_cliente_pdf(
    cliente_id: int,
    desde: str = Query(..., description="Inicio del período, ISO (YYYY-MM-DD)"),
    hasta: str = Query(..., description="Fin del período, ISO (YYYY-MM-DD)"),
    informes: InformeService = Depends(get_informe_service),
):
    try:
        desde_d = date.fromisoformat(desde)
        hasta_d = date.fromisoformat(hasta)
    except ValueError:
        raise HTTPException(422, "Fechas inválidas: se esperan ISO (YYYY-MM-DD)")
    if hasta_d < desde_d:
        raise HTTPException(422, "El fin del período es anterior al inicio")

    informe = informes.cliente(cliente_id, desde, hasta)
    if informe is None:
        raise HTTPException(404, "Cliente no encontrado")

    pdf = informe_pdf.generar(informe)
    nombre = f"informe-{_slug(informe['cliente']['nombre'])}-{desde}-{hasta}.pdf"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
