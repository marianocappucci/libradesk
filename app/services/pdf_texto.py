"""Medir el texto antes de dibujarlo. Un solo lugar para los tres PDF.

`cell` de fpdf2 **no recorta ni envuelve**: si el texto es más ancho que la
celda lo dibuja igual, encima de la columna de al lado y, si no hay nada al
lado, afuera del papel. Y el texto de estos documentos lo escribe el usuario
—títulos de ticket, marcas, modelos, seriales, sectores—, así que el largo no
lo acota nada.

**Por qué en un módulo propio y no una copia por documento.** `informe_pdf`,
`incidencia_pdf` e `ingreso_pdf` nacieron copiándose los helpers de maquetado
(`_titulo_seccion`, `_campo`, `_parrafo`) y así fue como se separaron: el
informe llamaba a `set_margins` y las dos copias no, y esas dos sacaban el
cuerpo entero 8 mm afuera del marco. Una defensa que cada documento tiene que
acordarse de copiar es una defensa que el próximo documento no va a tener.
"""
from __future__ import annotations

from fpdf import FPDF

#: El aire que `cell` deja adentro de la celda, a cada lado.
_AIRE = 1.0


def ancho_util(ancho: float) -> float:
    """Lo que se puede escribir adentro de una celda de ancho `ancho`.

    Un texto medido contra el ancho pelado se pasa 1 mm por lado — poco para
    verlo de un vistazo y suficiente para pisar la columna siguiente.
    """
    return ancho - 2 * _AIRE


def recortar(pdf: FPDF, texto: str, ancho: float) -> str:
    """El texto que entra en una celda de ancho `ancho`, con elipsis si sobra.

    Recorta por carácter y no por palabra a propósito: un serial, una URL o un
    código de orden de compra es una sola palabra, y el corte por palabra lo
    dejaría entero — que es exactamente el caso que se iba del papel.
    """
    util = ancho_util(ancho)
    if pdf.get_string_width(texto) <= util:
        return texto
    elipsis = pdf.get_string_width("…")
    recorte = texto
    while recorte and pdf.get_string_width(recorte) + elipsis > util:
        recorte = recorte[:-1]
    return recorte.rstrip() + "…"
