"""Baja una `Vista` (ver `reporte_vista.py`) a un libro de Excel.

Es la mitad "papel" del reporte: la otra mitad es la tabla que dibuja el
frontend con el mismo JSON. Ninguna de las dos decide **que** columnas hay ni
que se resalta — eso ya vino decidido en la vista, y por eso no pueden
divergir.
"""
from openpyxl import Workbook

from .reporte_vista import MARCA_ARGB, Vista
from .xlsx_helper import (
    add_data_row,
    add_group_header,
    add_header_row,
    add_meta_header,
    add_totals_row,
    create_sheet,
)


def renderizar(vista: Vista) -> Workbook:
    wb, ws = create_sheet(vista.titulo, vista.filtros)
    header_row = add_meta_header(ws, vista.titulo, vista.filtros, len(vista.columnas))
    add_header_row(
        ws, header_row,
        [c.label for c in vista.columnas],
        [c.ancho for c in vista.columnas],
    )

    fila = header_row + 1
    for grupo in vista.grupos:
        if grupo.etiqueta:
            add_group_header(ws, fila, grupo.etiqueta, len(vista.columnas))
            fila += 1
        # El alternado de filas se cuenta **dentro** de cada grupo, no corrido:
        # es como salia antes de la extraccion, con el `enumerate` por grupo del
        # reporte de Facturacion.
        for i, celdas in enumerate(grupo.filas):
            add_data_row(
                ws, fila,
                # El numero crudo cuando lo hay, para que la planilla lo trate
                # como numero y no como texto. Ver `Celda.numero`.
                [c.numero if c.numero is not None else c.texto for c in celdas],
                [MARCA_ARGB.get(c.marca) if c.marca else None for c in celdas],
                is_alt=i % 2 == 1,
            )
            fila += 1

    if vista.totales:
        add_totals_row(
            ws, fila,
            [c.numero if c.numero is not None else c.texto for c in vista.totales],
        )

    return wb
