"""Helpers de export a Excel con openpyxl — reconstruye el diseno visual
de `xlsxHelper.ts` (backend Node.js viejo) en Python: paleta indigo,
encabezado con titulo+filtros, header congelado, filas alternadas,
resaltado por celda, fila de totales y encabezados de grupo. No hay
precedente de export xlsx en la familia Libra (Gestiolibra no exporta) —
es una pieza propia de LibraDesk."""
from datetime import date, datetime
from io import BytesIO

from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

PRIMARY = "FF4338CA"  # indigo-700
HDR_BG = "FFE0E7FF"  # indigo-100
ALT_ROW = "FFFAFAFA"
WHITE = "FFFFFFFF"
GROUP_BG = "FFEEF2FF"
GROUP_FG = "FF3730A3"
HDR_FG = "FF1E1B4B"
BORDE_HDR = "FFC7D2FE"

# Resaltados de celda, portados tal cual del helper viejo para que los
# archivos se sigan viendo igual.
ESTADO_LABEL = {
    "activo": "Activo", "baja": "Baja", "en_reparacion": "En reparación",
    "almacenado": "En depósito",
    "abierto": "Abierto", "en_progreso": "En progreso",
    "resuelta": "Resuelta", "cerrado": "Cerrado",
}
ESTADO_COLOR = {
    "activo": "FFD1FAE5", "baja": "FFFEE2E2", "en_reparacion": "FFFED7AA",
    "almacenado": "FFEDE9FE",
    "abierto": "FFDBEAFE", "en_progreso": "FFFED7AA",
    "resuelta": "FFD1FAE5", "cerrado": "FFF3F4F6",
}
PRIO_COLOR = {"alta": "FFFEE2E2", "media": "FFFEF9C3", "baja": "FFD1FAE5"}
PRIO_LABEL = {"alta": "Alta", "media": "Media", "baja": "Baja"}
FACT_COLOR = {
    "pendiente_cobro": "FFFEF9C3", "facturada": "FFD1FAE5",
    "sin_facturar": "FFF3F4F6",
}
FACT_LABEL = {"pendiente_cobro": "Pend. cobro", "facturada": "Facturada"}
MOV_LABEL = {
    "alta": "Alta", "baja": "Baja", "traslado": "Traslado",
    "en_reparacion": "Reparación", "almacenado": "Almacenado",
    "activo": "Reactivado",
}

_HAIR = Border(bottom=Side(style="hair", color="FFEDEDED"))
_BOTTOM_HDR = Border(bottom=Side(style="thin", color=BORDE_HDR))
_TOP_HDR = Border(top=Side(style="thin", color=BORDE_HDR))


def fmt_date(value) -> str:
    """dd/mm/aa, o '—' si no hay valor. Acepta datetime, date o el ISO
    string que devuelven los repositories."""
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, (datetime, date)):
        return value.strftime("%d/%m/%y")
    return str(value)


def _fill(argb: str) -> PatternFill:
    return PatternFill("solid", fgColor=argb)


def create_sheet(titulo: str, filtros: list[str], sheet_name: str | None = None):
    """Devuelve (wb, ws) con el encabezado de titulo+filtros ya puesto.
    La primera fila util (la de headers) es la 4."""
    wb = Workbook()
    wb.properties.creator = "LibraDesk"
    ws = wb.active
    ws.title = (sheet_name or titulo)[:31]
    # Apaisado y ajustado al ancho: estos reportes tienen muchas columnas.
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    return wb, ws


def add_meta_header(ws: Worksheet, titulo: str, filtros: list[str], col_count: int) -> int:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=col_count)
    c1 = ws.cell(row=1, column=1, value=f"LibraDesk — {titulo}")
    c1.font = Font(bold=True, size=13, color=WHITE)
    c1.fill = _fill(PRIMARY)
    c1.alignment = Alignment(vertical="center", horizontal="left", indent=1)
    ws.row_dimensions[1].height = 26

    info = "   |   ".join(
        [f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", *filtros]
    )
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=col_count)
    c2 = ws.cell(row=2, column=1, value=info)
    c2.font = Font(size=9, italic=True, color="FF6B7280")
    c2.fill = _fill("FFF1F5F9")
    c2.alignment = Alignment(vertical="center", horizontal="left", indent=1)
    ws.row_dimensions[2].height = 15
    ws.row_dimensions[3].height = 5
    return 4


def add_header_row(ws: Worksheet, row_num: int, headers: list[str], widths: list[int]) -> None:
    for i, h in enumerate(headers, start=1):
        cell = ws.cell(row=row_num, column=i, value=h)
        cell.font = Font(bold=True, size=10, color=HDR_FG)
        cell.fill = _fill(HDR_BG)
        cell.border = _BOTTOM_HDR
        cell.alignment = Alignment(vertical="center", horizontal="left")
        ws.column_dimensions[get_column_letter(i)].width = (
            widths[i - 1] if i - 1 < len(widths) else 14
        )
    ws.row_dimensions[row_num].height = 20
    ws.freeze_panes = f"A{row_num + 1}"


def add_data_row(
    ws: Worksheet,
    row_num: int,
    values: list,
    cell_fills: list[str | None] | None = None,
    is_alt: bool = False,
) -> None:
    row_bg = ALT_ROW if is_alt else WHITE
    for i, v in enumerate(values, start=1):
        cell = ws.cell(row=row_num, column=i, value=v if v is not None else "—")
        cell.font = Font(size=10)
        propio = cell_fills[i - 1] if cell_fills and i - 1 < len(cell_fills) else None
        cell.fill = _fill(propio or row_bg)
        cell.alignment = Alignment(vertical="center")
        cell.border = _HAIR
    ws.row_dimensions[row_num].height = 16


def add_totals_row(ws: Worksheet, row_num: int, values: list) -> None:
    for i, v in enumerate(values, start=1):
        cell = ws.cell(row=row_num, column=i, value=v if v is not None else "")
        cell.font = Font(bold=True, size=10, color=HDR_FG)
        cell.fill = _fill(HDR_BG)
        cell.border = _TOP_HDR
        cell.alignment = Alignment(vertical="center")
    ws.row_dimensions[row_num].height = 18


def add_group_header(ws: Worksheet, row_num: int, text: str, col_count: int) -> None:
    ws.merge_cells(start_row=row_num, start_column=1, end_row=row_num, end_column=col_count)
    cell = ws.cell(row=row_num, column=1, value=text)
    cell.font = Font(bold=True, size=10, color=GROUP_FG)
    cell.fill = _fill(GROUP_BG)
    cell.border = _TOP_HDR
    cell.alignment = Alignment(vertical="center", horizontal="left", indent=1)
    ws.row_dimensions[row_num].height = 18


def build_sheet(titulo: str, filtros: list[str], headers: list[str], widths: list[int], rows: list[list]):
    """Atajo para los reportes simples (volcado plano, sin resaltados ni
    totales): arma la hoja entera de una."""
    wb, ws = create_sheet(titulo, filtros)
    header_row = add_meta_header(ws, titulo, filtros, len(headers))
    add_header_row(ws, header_row, headers, widths)
    for i, row_values in enumerate(rows):
        add_data_row(ws, header_row + 1 + i, row_values, is_alt=i % 2 == 1)
    return wb


def xlsx_response(wb: Workbook, filename: str) -> StreamingResponse:
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
