"""Exports xlsx.

Dos familias, deliberadamente distintas:

- **Reportes analiticos** (6): reconstruidos desde el backend Node.js viejo
  (`reportesXlsxController.ts`) — con filtros, resaltados por celda,
  agrupacion y filas de totales. Son los que se ofrecen en `/reportes`.
- **Volcados planos** (3): un listado por dominio, sin filtros ni formato
  analitico. Nacieron con la reescritura como export minimo y se conservan
  porque sirven para bajar la tabla cruda.
"""
from fastapi import APIRouter, Depends, Query

from ..dependencies import (
    get_categoria_repository, get_cliente_repository, get_equipo_repository,
    get_incidencia_repository, get_reportes_service,
)
from ..services.categorias import CategoriaRepository
from ..services.clientes import ClienteRepository
from ..services.equipos import EquipoRepository
from ..services.incidencias import IncidenciaRepository
from ..services.reportes import ReportesService
from ..services.xlsx_helper import (
    ESTADO_COLOR, ESTADO_LABEL, FACT_COLOR, FACT_LABEL, MOV_LABEL,
    PRIO_COLOR, PRIO_LABEL,
    add_data_row, add_group_header, add_header_row, add_meta_header,
    add_totals_row, build_sheet, create_sheet, fmt_date, xlsx_response,
)

router = APIRouter(prefix="/api/reportes", tags=["reportes"])

VENCIDA = "FFFEE2E2"
URGENTE = "FFFEF9C3"
CON_INCIDENCIAS = "FFFFEDD5"
MENSUAL = "FFEDE9FE"
SIN_FACTURAR = "FFF3F4F6"


def _hoja(titulo: str, filtros: list[str], headers: list[str], widths: list[int]):
    """Arma la hoja con encabezado + fila de headers y devuelve la primera
    fila de datos, que es donde arrancan todos los reportes analiticos."""
    wb, ws = create_sheet(titulo, filtros)
    header_row = add_meta_header(ws, titulo, filtros, len(headers))
    add_header_row(ws, header_row, headers, widths)
    return wb, ws, header_row + 1


def _label_cliente(cliente_id: int | None, clientes: ClienteRepository) -> str | None:
    if not cliente_id:
        return None
    c = clientes.get(cliente_id)
    return (c["empresa"] or c["nombre"]) if c else f"#{cliente_id}"


# ── Reportes analiticos ────────────────────────────────────────────

@router.get("/equipamiento.xlsx")
def equipamiento_xlsx(
    cliente_id: int | None = None,
    estado: str | None = None,
    tipo: str | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    data = reportes.equipamiento(cliente_id=cliente_id, estado=estado, tipo=tipo)

    filtros = []
    if (label := _label_cliente(cliente_id, clientes)):
        filtros.append(f"Cliente: {label}")
    if estado:
        filtros.append(f"Estado: {ESTADO_LABEL.get(estado, estado)}")
    if tipo:
        filtros.append(f"Tipo: {tipo}")

    headers = ["Cliente", "Tipo", "Marca", "Modelo", "Serial", "Sector",
               "Ubicación", "Estado", "Garantía vence", "Inc.", "Alta"]
    widths = [28, 14, 14, 18, 15, 18, 16, 14, 14, 6, 12]
    wb, ws, fila = _hoja("Equipamiento", filtros, headers, widths)

    from datetime import datetime as _dt
    ahora = _dt.now()
    for i, r in enumerate(data):
        vence = r["garantia_vence"]
        vencida = bool(vence) and (
            (vence if isinstance(vence, _dt) else _dt.combine(vence, _dt.min.time())) < ahora
        )
        add_data_row(ws, fila + i, [
            r["cliente"], r["tipo"], r["marca"], r["modelo"], r["serial"],
            r["sector"], r["ubicacion_oficina"],
            ESTADO_LABEL.get(r["estado"], r["estado"]),
            fmt_date(vence),
            r["incidencias_count"] or None,
            fmt_date(r["fecha_adicion"]),
        ], [
            None, None, None, None, None, None, None,
            ESTADO_COLOR.get(r["estado"]),
            VENCIDA if vencida else None,
            CON_INCIDENCIAS if r["incidencias_count"] else None,
            None,
        ], is_alt=i % 2 == 1)

    return xlsx_response(wb, "equipamiento.xlsx")


@router.get("/incidencias-periodo.xlsx")
def incidencias_periodo_xlsx(
    desde: str = Query(...),
    hasta: str = Query(...),
    cliente_id: int | None = None,
    estado: str | None = None,
    prioridad: str | None = None,
    sector_id: int | None = None,
    keyword: str | None = None,
    categoria_id: int | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
    categorias: CategoriaRepository = Depends(get_categoria_repository),
):
    data = reportes.incidencias(
        desde=desde, hasta=hasta, cliente_id=cliente_id, estado=estado,
        prioridad=prioridad, sector_id=sector_id, keyword=keyword,
        categoria_id=categoria_id,
    )

    filtros = [f"Período: {fmt_date(desde)} – {fmt_date(hasta)}"]
    if (label := _label_cliente(cliente_id, clientes)):
        filtros.append(f"Cliente: {label}")
    if estado:
        filtros.append(f"Estado: {ESTADO_LABEL.get(estado, estado)}")
    if prioridad:
        filtros.append(f"Prioridad: {PRIO_LABEL.get(prioridad, prioridad)}")
    if categoria_id and (cat := categorias.get(categoria_id)):
        filtros.append(f"Categoría: {cat['ruta']}")
    if keyword:
        filtros.append(f'Búsqueda: "{keyword}"')

    # Sin columna "Tar.": la tabla incidencia_tareas ya no existe.
    headers = ["#", "Cliente", "Sector", "Categoría", "Título", "Descripción", "Estado",
               "Prioridad", "Técnico", "Creación", "Cierre", "Act.", "Hs.", "Cobro"]
    widths = [6, 24, 18, 24, 30, 38, 14, 11, 20, 12, 12, 6, 6, 16]
    wb, ws, fila = _hoja("Incidencias", filtros, headers, widths)

    for i, r in enumerate(data):
        if r["tipo_facturacion"] == "mensual":
            cobro_text, cobro_color = "Mensual", MENSUAL
        elif r["estado_facturacion"]:
            cobro_text = FACT_LABEL.get(r["estado_facturacion"], r["estado_facturacion"])
            cobro_color = FACT_COLOR.get(r["estado_facturacion"])
        elif r["estado"] in ("cerrado", "resuelta"):
            cobro_text, cobro_color = "Sin facturar", SIN_FACTURAR
        else:
            cobro_text, cobro_color = None, None

        add_data_row(ws, fila + i, [
            r["id"], r["cliente"], r["sector"], r["categoria"],
            r["titulo"], r["descripcion"],
            ESTADO_LABEL.get(r["estado"], r["estado"]),
            PRIO_LABEL.get(r["prioridad"], r["prioridad"]),
            r["tecnico"],
            fmt_date(r["fecha_creacion"]), fmt_date(r["fecha_cierre"]),
            r["actividades_count"] or None,
            f"{r['horas_resolucion']}h" if r["horas_resolucion"] is not None else None,
            cobro_text,
        ], [
            None, None, None, None, None, None,
            ESTADO_COLOR.get(r["estado"]),
            PRIO_COLOR.get(r["prioridad"]),
            None, None, None, None, None,
            cobro_color,
        ], is_alt=i % 2 == 1)

    total_act = sum(r["actividades_count"] for r in data)
    con_horas = [r["horas_resolucion"] for r in data if r["horas_resolucion"] is not None]
    prom = f"{round(sum(con_horas) / len(con_horas))}h prom" if con_horas else None
    add_totals_row(ws, fila + len(data), [
        None, None, None, None, None, None, None, None, None,
        f"{len(data)} incidencias", None, total_act, prom, None,
    ])

    return xlsx_response(wb, "incidencias-periodo.xlsx")


@router.get("/facturacion.xlsx")
def facturacion_xlsx(
    desde: str = Query(...),
    hasta: str = Query(...),
    cliente_id: int | None = None,
    estado_facturacion: str | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    data = reportes.facturacion(
        desde=desde, hasta=hasta, cliente_id=cliente_id,
        estado_facturacion=estado_facturacion,
    )

    filtros = [f"Período: {fmt_date(desde)} – {fmt_date(hasta)}"]
    if (label := _label_cliente(cliente_id, clientes)):
        filtros.append(f"Cliente: {label}")
    if estado_facturacion:
        filtros.append(f"Cobro: {FACT_LABEL.get(estado_facturacion, estado_facturacion)}")

    headers = ["#", "Cliente", "Título", "Técnico", "Cierre", "Estado cobro"]
    widths = [6, 28, 42, 20, 12, 18]
    wb, ws, fila = _hoja("Facturación", filtros, headers, widths)

    grupos: dict[int, list[dict]] = {}
    for r in data:
        grupos.setdefault(r["cliente_id"], []).append(r)

    for filas in grupos.values():
        cantidad = len(filas)
        etiqueta = f"{filas[0]['cliente']} — {cantidad} incidencia{'s' if cantidad != 1 else ''}"
        add_group_header(ws, fila, etiqueta, len(headers))
        fila += 1
        for i, r in enumerate(filas):
            if r["estado_facturacion"]:
                texto = FACT_LABEL.get(r["estado_facturacion"], r["estado_facturacion"])
                color = FACT_COLOR.get(r["estado_facturacion"], SIN_FACTURAR)
            else:
                texto, color = "Sin facturar", SIN_FACTURAR
            add_data_row(ws, fila, [
                r["id"], r["cliente"], r["titulo"], r["tecnico"],
                fmt_date(r["fecha_cierre"]), texto,
            ], [None, None, None, None, None, color], is_alt=i % 2 == 1)
            fila += 1

    sin_fact = sum(1 for r in data if not r["estado_facturacion"])
    pend = sum(1 for r in data if r["estado_facturacion"] == "pendiente_cobro")
    facturadas = sum(1 for r in data if r["estado_facturacion"] == "facturada")
    add_totals_row(ws, fila, [
        None, None,
        f"Total: {len(data)}  |  Sin facturar: {sin_fact}  |  "
        f"Pend. cobro: {pend}  |  Facturadas: {facturadas}",
        None, None, None,
    ])

    return xlsx_response(wb, "facturacion.xlsx")


@router.get("/garantias.xlsx")
def garantias_xlsx(
    dias: int = 60,
    cliente_id: int | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    data = reportes.garantias(dias=dias, cliente_id=cliente_id)

    filtros = [f"Próximos {dias} días"]
    if (label := _label_cliente(cliente_id, clientes)):
        filtros.append(f"Cliente: {label}")

    headers = ["Cliente", "Tipo", "Marca", "Modelo", "Serial", "Sector",
               "Estado", "Garantía vence", "Días restantes"]
    widths = [28, 14, 14, 18, 15, 18, 14, 14, 13]
    wb, ws, fila = _hoja("Garantías", filtros, headers, widths)

    for i, r in enumerate(data):
        restantes = r["dias_restantes"]
        vencida = restantes < 0
        urgente = 0 <= restantes <= 14
        texto = f"Vencida hace {abs(restantes)}d" if vencida else f"{restantes}d"
        color = VENCIDA if vencida else (URGENTE if urgente else None)
        add_data_row(ws, fila + i, [
            r["cliente"], r["tipo"], r["marca"], r["modelo"], r["serial"],
            r["sector"], ESTADO_LABEL.get(r["estado"], r["estado"]),
            fmt_date(r["garantia_vence"]), texto,
        ], [
            None, None, None, None, None, None,
            ESTADO_COLOR.get(r["estado"]), color, color,
        ], is_alt=i % 2 == 1)

    return xlsx_response(wb, "garantias.xlsx")


@router.get("/tecnico.xlsx")
def tecnico_xlsx(
    desde: str = Query(...),
    hasta: str = Query(...),
    reportes: ReportesService = Depends(get_reportes_service),
):
    data = reportes.por_tecnico(desde=desde, hasta=hasta)

    filtros = [f"Período: {fmt_date(desde)} – {fmt_date(hasta)}"]
    headers = ["Técnico", "Total", "Abiertas", "En progreso", "Cerradas",
               "% Resolución", "Actividades", "Prom. horas"]
    widths = [28, 9, 10, 13, 10, 14, 13, 13]
    wb, ws, fila = _hoja("Por técnico", filtros, headers, widths)

    for i, r in enumerate(data):
        pct = f"{round(r['cerradas'] / r['total'] * 100)}%" if r["total"] else "0%"
        add_data_row(ws, fila + i, [
            r["tecnico"], r["total"], r["abiertas"] or None,
            r["en_progreso"] or None, r["cerradas"] or None, pct,
            r["total_actividades"] or None,
            f"{r['promedio_horas_resolucion']}h" if r["promedio_horas_resolucion"] is not None else None,
        ], is_alt=i % 2 == 1)

    total = sum(r["total"] for r in data)
    cerradas = sum(r["cerradas"] for r in data)
    add_totals_row(ws, fila + len(data), [
        "TOTAL", total,
        sum(r["abiertas"] for r in data), sum(r["en_progreso"] for r in data),
        cerradas,
        f"{round(cerradas / total * 100)}%" if total else "0%",
        sum(r["total_actividades"] for r in data), None,
    ])

    return xlsx_response(wb, "tecnico.xlsx")


@router.get("/movimientos.xlsx")
def movimientos_xlsx(
    desde: str = Query(...),
    hasta: str = Query(...),
    cliente_id: int | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    data = reportes.movimientos(desde=desde, hasta=hasta, cliente_id=cliente_id)

    filtros = [f"Período: {fmt_date(desde)} – {fmt_date(hasta)}"]
    if (label := _label_cliente(cliente_id, clientes)):
        filtros.append(f"Cliente: {label}")

    headers = ["Fecha", "Cliente", "Equipo", "Tipo",
               "Sector / Ubic. origen", "Sector / Ubic. destino", "Motivo"]
    widths = [12, 26, 28, 12, 24, 24, 28]
    wb, ws, fila = _hoja("Movimientos de equipos", filtros, headers, widths)

    for i, r in enumerate(data):
        origen = " · ".join(x for x in (r["sector_origen"], r["ubicacion_origen"]) if x) or None
        destino = " · ".join(x for x in (r["sector_destino"], r["ubicacion_destino"]) if x) or None
        add_data_row(ws, fila + i, [
            fmt_date(r["fecha"]), r["cliente"], r["equipo"],
            MOV_LABEL.get(r["tipo"], r["tipo"]),
            origen, destino, r["motivo"],
        ], is_alt=i % 2 == 1)

    return xlsx_response(wb, "movimientos.xlsx")


# ── Volcados planos ────────────────────────────────────────────────

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
