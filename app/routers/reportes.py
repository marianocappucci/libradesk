"""Exports xlsx de los 3 dominios preservados. Alcance reducido respecto
a los 12 reportes que tenia `xlsxHelper.ts` (backend Node.js viejo) — se
reconstruyeron los 3 mas representativos (uno por dominio) con el mismo
diseno visual; sumar el resto queda como mejora incremental, no bloquea
el cutover de produccion."""
from fastapi import APIRouter, Depends

from ..dependencies import get_cliente_repository, get_equipo_repository, get_incidencia_repository
from ..services.clientes import ClienteRepository
from ..services.equipos import EquipoRepository
from ..services.incidencias import IncidenciaRepository
from ..services.xlsx_helper import build_sheet, xlsx_response

router = APIRouter(prefix="/api/reportes", tags=["reportes"])


@router.get("/clientes.xlsx")
def export_clientes(clientes: ClienteRepository = Depends(get_cliente_repository)):
    data = clientes.list()
    rows = [
        [c["id"], c["nombre"], c["empresa"], c["email"], c["telefono"], c["ciudad"],
         "Activo" if c["activo"] else "Inactivo"]
        for c in data
    ]
    wb = build_sheet(
        "Clientes", [f"Total: {len(data)}"],
        ["ID", "Nombre", "Empresa", "Email", "Telefono", "Ciudad", "Estado"],
        [6, 28, 24, 26, 16, 16, 12], rows,
    )
    return xlsx_response(wb, "clientes.xlsx")


@router.get("/equipos.xlsx")
def export_equipos(equipos: EquipoRepository = Depends(get_equipo_repository)):
    data = equipos.list()
    rows = [
        [e["id"], e["cliente_id"], e["tipo"], e["marca"], e["modelo"], e["serial"], e["estado"]]
        for e in data
    ]
    wb = build_sheet(
        "Equipos", [f"Total: {len(data)}"],
        ["ID", "Cliente", "Tipo", "Marca", "Modelo", "Serial", "Estado"],
        [6, 10, 18, 18, 20, 20, 12], rows,
    )
    return xlsx_response(wb, "equipos.xlsx")


@router.get("/incidencias.xlsx")
def export_incidencias(
    estado: str | None = None,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
):
    data = incidencias.list(estado=estado)
    rows = [
        [i["id"], i["cliente_id"], i["titulo"], i["estado"], i["prioridad"],
         i["horas_invertidas"], i["fecha_creacion"]]
        for i in data
    ]
    filtros = [f"Total: {len(data)}"] + ([f"Estado: {estado}"] if estado else [])
    wb = build_sheet(
        "Incidencias", filtros,
        ["ID", "Cliente", "Titulo", "Estado", "Prioridad", "Horas", "Fecha"],
        [6, 10, 32, 14, 12, 10, 18], rows,
    )
    return xlsx_response(wb, "incidencias.xlsx")
