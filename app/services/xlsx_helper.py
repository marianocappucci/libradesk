"""Helpers de export a Excel con openpyxl — reconstruye el diseno visual
de `xlsxHelper.ts` (paleta indigo, encabezado con titulo+filtros, header
congelado) en Python. No hay precedente de export xlsx en la familia
Libra (Gestiolibra no exporta) — es una pieza nueva, misma idea
reimplementada."""
from datetime import datetime
from io import BytesIO

from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

PRIMARY = "FF4338CA"  # indigo-700
HDR_BG = "FFE0E7FF"  # indigo-100
WHITE = "FFFFFFFF"


def build_sheet(titulo: str, filtros: list[str], headers: list[str], widths: list[int], rows: list[list]):
    wb = Workbook()
    wb.properties.creator = "LibraDesk"
    ws = wb.active
    ws.title = titulo[:31]

    col_count = len(headers)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=col_count)
    c1 = ws.cell(row=1, column=1, value=f"LibraDesk — {titulo}")
    c1.font = Font(bold=True, size=13, color=WHITE)
    c1.fill = PatternFill("solid", fgColor=PRIMARY)
    c1.alignment = Alignment(vertical="center", horizontal="left", indent=1)
    ws.row_dimensions[1].height = 26

    info = "   |   ".join([f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", *filtros])
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=col_count)
    c2 = ws.cell(row=2, column=1, value=info)
    c2.font = Font(size=9, italic=True, color="FF6B7280")
    c2.fill = PatternFill("solid", fgColor="FFF1F5F9")
    c2.alignment = Alignment(vertical="center", horizontal="left", indent=1)
    ws.row_dimensions[2].height = 15
    ws.row_dimensions[3].height = 5

    header_row = 4
    for i, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=i, value=h)
        cell.font = Font(bold=True, size=10, color="FF1E1B4B")
        cell.fill = PatternFill("solid", fgColor=HDR_BG)
        cell.alignment = Alignment(vertical="center", horizontal="left")
        ws.column_dimensions[get_column_letter(i)].width = widths[i - 1] if i - 1 < len(widths) else 14
    ws.row_dimensions[header_row].height = 20
    ws.freeze_panes = f"A{header_row + 1}"

    for r, row_values in enumerate(rows, start=header_row + 1):
        for c, value in enumerate(row_values, start=1):
            cell = ws.cell(row=r, column=c, value=value if value is not None else "—")
            cell.font = Font(size=10)
            cell.alignment = Alignment(vertical="center")

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
