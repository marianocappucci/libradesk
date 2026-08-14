"""La agenda de los equipos de trabajo (pedido 42, fase B).

Router propio y no un endpoint más de `/api/equipos-trabajo`: la agenda se
consulta por **rango de fechas**, que es una pregunta distinta de "qué equipos
hay". Ver `app/services/agenda.py` para por qué LibraGenda se usa como librería
de reglas y no de persistencia.
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ..dependencies import get_equipo_trabajo_repository, get_incidencia_repository
from ..services import agenda as agenda_service
from ..services import hoja_ruta_pdf
from ..services.equipos_trabajo import EquipoTrabajoRepository
from ..services.incidencias import IncidenciaRepository

router = APIRouter(prefix="/api/agenda", tags=["agenda"])


@router.get("/equipo/{equipo_id}")
def agenda_de_equipo(
    equipo_id: int,
    desde: str = Query(..., description="Primer día, ISO (YYYY-MM-DD)"),
    dias: int = Query(1, ge=1, le=31, description="Cuántos días mostrar"),
    equipos: EquipoTrabajoRepository = Depends(get_equipo_trabajo_repository),
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
):
    """Qué tiene el equipo en ese rango, más temprano primero.

    `dias` y no un `hasta`: la pregunta real es "qué hace el martes" o "qué hace
    esta semana", y un rango abierto invita a pedir el año entero por accidente.
    """
    if equipos.get(equipo_id) is None:
        raise HTTPException(404, "equipo not found")
    try:
        primer_dia = date.fromisoformat(desde)
    except ValueError:
        raise HTTPException(422, "Fecha inválida: se espera ISO (YYYY-MM-DD)")

    inicio = datetime.combine(primer_dia, datetime.min.time())
    with incidencias.session_factory() as session:
        return agenda_service.agenda_del_equipo(
            session, equipo_id, inicio, inicio + timedelta(days=dias),
        )


@router.get("/equipo/{equipo_id}/hoja-de-ruta")
def hoja_de_ruta(
    equipo_id: int,
    dia: str = Query(..., description="El día de la salida, ISO (YYYY-MM-DD)"),
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
):
    """La hoja de ruta del equipo para ese día, en PDF y lista para imprimir.

    **Un día y no un rango**, a diferencia del endpoint de arriba: una hoja de
    ruta es una salida, y una salida es de un día. Pedirla por rango produciría
    un papel que la cuadrilla no puede usar —¿con cuántos kilómetros salió, los
    del martes o los del jueves?— y una sola firma para tres jornadas.

    `inline` y no `attachment`, igual que la orden de trabajo: se abre y se
    manda a la impresora.
    """
    try:
        el_dia = date.fromisoformat(dia)
    except ValueError:
        raise HTTPException(422, "Fecha inválida: se espera ISO (YYYY-MM-DD)")

    with incidencias.session_factory() as session:
        datos = agenda_service.datos_hoja_ruta(session, equipo_id, el_dia)
    if datos is None:
        raise HTTPException(404, "equipo not found")

    return Response(
        content=hoja_ruta_pdf.generar_pdf_hoja_ruta(datos),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="hoja-de-ruta-{equipo_id}-{dia}.pdf"'
            ),
        },
    )
