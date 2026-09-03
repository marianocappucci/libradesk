"""El PDF de **una** incidencia (pedido 39 del usuario, 2026-08-04).

Es la orden de trabajo del ticket: lo que se imprime para llevar a la visita, o
para dejarle al cliente al terminar. Sale con el mismo membrete que los remitos,
presupuestos e informes que ese cliente ya recibe, por el mismo motivo que
`informe_pdf.py` — tres documentos con logos distintos se leen como salidos de
tres empresas.

**Qué lo diferencia del informe de servicio** (`informe_pdf.py`), que ya existe:
aquél resume **un período entero** de un cliente y es un entregable comercial;
éste es **un ticket** y sirve para operar. Por eso incluye lo que el informe
omite a propósito —las notas internas, el detalle de la actividad, quién lo
recepcionó y quién lo ejecutó— y no lleva ni totales ni nada que parezca una
liquidación.

**Reusa el andamiaje privado de LibraCore**, con el mismo criterio ya
documentado en `informe_pdf.py`: el pin es exacto y hay un test que afirma que
cada nombre importado existe, así que un bump que se lleve uno puesto pone el CI
en rojo en el momento del bump.

**No persiste el archivo.** Un ticket impreso es una consulta materializada, no
un comprobante numerado: se regenera de los mismos datos cuando haga falta.
"""
from __future__ import annotations

from datetime import datetime

from fpdf import FPDF
from libracore.pdf_generator import (
    _ACCENT_DARK,
    _CW,
    _INK,
    _LINE,
    _LX,
    _MUTED,
    _RX,
    _draw_emisor_cliente,
    _draw_header_block,
    _draw_no_fiscal_notice,
    _empresa,
    _TextoSeguroPDF,
    _wrap_text,
)

from .pdf_texto import ancho_util, recortar

# La caja de la letra del membrete. `_draw_header_block` le aplica `.title()`
# al título, así que va sin preposiciones.
_LETRA = "OT"
_TITULO = "Orden de trabajo"

_LINEA = 4.5
# 🔴 **18 y no 14, y el número está medido, no copiado.** Ver el comentario
# gemelo en `ingreso_pdf.py`: lo que el cierre dibuja por debajo de la `y` que
# se chequea son 18 mm —4 del `ln(4)`, 4 de aire y 10 de recuadro—, así que con
# 14 quedaba una franja de 4 mm donde el chequeo pasaba y el dibujo no entraba.
#
# **Acá el defecto no era teórico: salía con datos de todos los días.** Una
# orden con una nota de un renglón y dos entradas de actividad deja la `y` en
# 261,8 y el aviso salía partido —el recuadro en la carilla 1 y su texto en la
# 2—. Medido el 2026-08-17 sobre el PDF generado, barriendo la cantidad de
# entradas de actividad: 31 combinaciones partidas de las que caen en la franja.
_ALTO_AVISO = 18


class _IncidenciaPDF(_TextoSeguroPDF, FPDF):
    """`_TextoSeguroPDF` primero en el MRO: es quien sobreescribe
    `normalize_text` para que el guión largo, las comillas curvas y los puntos
    suspensivos se **dibujen** en vez de tumbar la request.

    No es teórico en esta pantalla: el título y la descripción de un ticket los
    escribe el usuario, y pegar un texto desde Word alcanza para meter un `—`.
    """

    def __init__(self, empresa: dict, datos: dict) -> None:
        super().__init__()
        self.empresa = empresa
        self.datos = datos
        # El mismo marco que dibujan la cabecera, las reglas de sección y el
        # pie. Sin esto queda el margen de fpdf2 —10 mm— y **todo el cuerpo
        # sale 8 mm a la izquierda del recuadro que este documento acaba de
        # dibujar**: los títulos de sección y las etiquetas arrancan afuera de
        # la línea que los subraya. `InformePDF` ya lo hacía; acá faltaba.
        # Desde LibraCore v1.37.0 lo pone la base y esta línea es redundante —
        # se deja explícita igual, como en el informe, para no depender del pin.
        self.set_margins(_LX, _LX, _LX)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self) -> None:  # noqa: D102 — la firma la impone fpdf2
        # Sólo en la primera carilla, igual que el informe: repetir el membrete
        # entero en cada hoja de un ticket largo lo vuelve ilegible.
        if self.page_no() == 1:
            info = [
                ("Ticket:", f"#{self.datos['id']}"),
                ("Fecha:", self.datos["fecha_creacion"]),
                ("Estado:", self.datos["estado_label"]),
            ]
            # El N° CDS va en el encabezado, al lado del número de ticket, y no
            # enterrado en una sección: **es la llave con el papel firmado**.
            # Quien tiene el talonario en la mano busca por ese número, y abajo
            # de todo el documento no sirve para eso.
            #
            # Sólo si existe: un reclamo resuelto en remoto no tiene
            # comprobante, y una etiqueta con un guión al lado del número de
            # ticket se lee como "acá falta algo" en vez de "no corresponde".
            if self.datos.get("nro_cds"):
                info.append(("N° CDS:", self.datos["nro_cds"]))
            self.set_y(_draw_header_block(
                self, _LETRA, _TITULO, "", info, self.empresa,
            ))
            return
        self.set_y(_LX)

    def footer(self) -> None:  # noqa: D102
        self.set_y(-15)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_MUTED)
        self.cell(_CW, 5, f"Página {self.page_no()} de {{nb}}", align="C")


def _titulo_seccion(pdf: FPDF, texto: str) -> None:
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_ACCENT_DARK)
    pdf.cell(_CW, 5, texto.upper())
    pdf.ln(6)
    pdf.set_draw_color(*_LINE)
    pdf.line(_LX, pdf.get_y() - 1, _RX, pdf.get_y() - 1)
    pdf.set_text_color(*_INK)


def _campo(pdf: FPDF, etiqueta: str, valor: str | None, ancho: float = _CW / 2) -> None:
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*_MUTED)
    pdf.cell(28, _LINEA, f"{etiqueta}:")
    pdf.set_text_color(*_INK)
    pdf.cell(ancho - 28, _LINEA, recortar(pdf, valor or "—", ancho - 28))


def _materiales(pdf: FPDF, materiales: list[dict]) -> None:
    """La columna «Materiales Utilizados» del comprobante en papel.

    **Si no hay materiales la sección no se dibuja**, a diferencia de
    Descripción o Resolución, que sí muestran un guión. El criterio no es
    estético: la mayoría de los tickets de una mesa de ayuda no consumen nada
    —un diagnóstico, una configuración remota— y un encabezado «MATERIALES
    UTILIZADOS» seguido de un guión en todos ellos entrena a saltear la
    sección justo en los que sí la tienen.

    ⚠️ **No lleva importes.** Los materiales salen del inventario con su costo,
    no con un precio de venta, y este documento es una orden de trabajo: poner
    plata acá lo volvería un presupuesto sin serlo. Lo que se cobra sale de la
    venta, que es otro comprobante.
    """
    if not materiales:
        return
    _titulo_seccion(pdf, "Materiales utilizados")
    pdf.set_font("Helvetica", "", 8)
    for m in materiales:
        pdf.set_text_color(*_INK)
        # La cantidad primero y alineada: la pregunta que se le hace a esta
        # tabla es "cuánto salió del depósito", no "qué había".
        cantidad = f"{m['cantidad']:g}"
        pdf.cell(16, _LINEA, cantidad, align="R")
        pdf.cell(4, _LINEA, "")
        lineas = _wrap_text(pdf, m.get("descripcion") or "—", ancho_util(_CW - 20))
        pdf.cell(_CW - 20, _LINEA, recortar(pdf, lineas[0] if lineas else "—", _CW - 20))
        pdf.ln(_LINEA)
        for extra in lineas[1:]:
            pdf.cell(20, _LINEA, "")
            pdf.cell(_CW - 20, _LINEA, recortar(pdf, extra, _CW - 20))
            pdf.ln(_LINEA)


def _parrafo(pdf: FPDF, texto: str | None) -> None:
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*_INK)
    if not texto:
        pdf.set_text_color(*_MUTED)
        pdf.cell(_CW, _LINEA, "—")
        pdf.ln(_LINEA)
        return
    for linea in _wrap_text(pdf, texto, ancho_util(_CW)):
        # El renglón que devuelve `_wrap_text` se mide igual antes de dibujarlo:
        # el corte por carácter para una palabra sola más ancha que el renglón
        # lo hace LibraCore desde v1.37.0, y esto sostiene la invariante —nada
        # se dibuja sin medirse— con el pin anterior también.
        pdf.cell(_CW, _LINEA, recortar(pdf, linea, _CW))
        pdf.ln(_LINEA)


def generar_pdf_incidencia(datos: dict) -> bytes:
    """`datos` viene armado por `IncidenciaPdfService`, que junta el ticket con
    su cliente, su equipo, su personal y su actividad.

    Los datos y la presentación van separados por el mismo motivo que en el
    informe: así los números se testean sin abrir un binario.
    """
    empresa = _empresa()
    pdf = _IncidenciaPDF(empresa, datos)
    pdf.alias_nb_pages()
    pdf.add_page()

    # `_draw_emisor_cliente` espera pares (etiqueta, valor) y descarta los
    # vacíos por su cuenta, así que los nulos del cliente no hace falta
    # filtrarlos acá.
    cli = datos["cliente"]
    _draw_emisor_cliente(pdf, empresa, [
        ("Cliente", cli["nombre"]),
        ("CUIT", cli.get("cuit")),
        ("Domicilio", cli.get("domicilio")),
        ("Email", cli.get("email")),
    ])

    _titulo_seccion(pdf, "Ticket")
    pdf.set_font("Helvetica", "B", 10)
    # El título lo escribe quien abre el ticket y no tiene tope de largo. Con
    # `cell` a secas, uno que fuera una frase entera se dibujaba **fuera del
    # papel**: medido, 295 mm de borde derecho en una hoja de 210. Va repartido
    # en renglones, como la descripción.
    for linea in _wrap_text(pdf, datos["titulo"] or "—", ancho_util(_CW)):
        pdf.cell(_CW, 5, recortar(pdf, linea, _CW))
        pdf.ln(5)
    pdf.ln(1)
    _campo(pdf, "Prioridad", datos["prioridad_label"])
    _campo(pdf, "Modalidad", datos["modalidad_label"])
    pdf.ln(_LINEA)
    _campo(pdf, "Cerrada", datos["fecha_cierre"])
    _campo(pdf, "Horas", datos["horas"])
    pdf.ln(_LINEA)
    _campo(pdf, "Categoría", datos["categoria"], _CW)
    pdf.ln(_LINEA + 1)

    _titulo_seccion(pdf, "Equipo")
    _campo(pdf, "Equipo", datos["equipo"], _CW)
    pdf.ln(_LINEA)
    _campo(pdf, "Sector", datos["sector"], _CW)
    pdf.ln(_LINEA + 1)

    _titulo_seccion(pdf, "Personal")
    _campo(pdf, "Recepcionó", datos["recepcionista"])
    _campo(pdf, "Ejecutó", datos["tecnico"])
    pdf.ln(_LINEA)
    _campo(pdf, "Vendedor", datos["vendedor"], _CW)
    pdf.ln(_LINEA)
    # Quien llamó, cuando no es el contacto habitual. Va en Personal y no en
    # Ticket porque es una persona, no un atributo del reclamo.
    _campo(pdf, "Reclamante", datos.get("reclamante"), _CW)
    pdf.ln(_LINEA + 1)

    _titulo_seccion(pdf, "Descripción")
    _parrafo(pdf, datos["descripcion"])

    # Entre la descripción y la resolución a propósito: es el orden del papel
    # que ellos completan (reclamo efectuado → materiales utilizados →
    # observaciones del técnico). Ver
    # `wiki/sources/lagrace-relevamiento-whatsapp.md`.
    _materiales(pdf, datos.get("materiales") or [])

    _titulo_seccion(pdf, "Resolución")
    _parrafo(pdf, datos["resolucion"])

    if datos["notas"]:
        _titulo_seccion(pdf, "Notas internas")
        _parrafo(pdf, datos["notas"])

    if datos["actividad"]:
        _titulo_seccion(pdf, "Actividad")
        pdf.set_font("Helvetica", "", 8)
        for a in datos["actividad"]:
            pdf.set_text_color(*_MUTED)
            pdf.cell(32, _LINEA, recortar(pdf, a["fecha"], 32))
            pdf.set_text_color(*_INK)
            lineas = _wrap_text(pdf, a["descripcion"] or "—", ancho_util(_CW - 32))
            pdf.cell(_CW - 32, _LINEA, recortar(pdf, lineas[0] if lineas else "—", _CW - 32))
            pdf.ln(_LINEA)
            for extra in lineas[1:]:
                pdf.cell(32, _LINEA, "")
                pdf.cell(_CW - 32, _LINEA, recortar(pdf, extra, _CW - 32))
                pdf.ln(_LINEA)

    # El aviso va al final y con lugar reservado, por el defecto que ya se pagó
    # en el informe: `_draw_no_fiscal_notice` traza el recuadro y recién después
    # escribe, así que un salto automático dejaba el marco en una carilla y el
    # texto en la otra.
    if pdf.get_y() + _ALTO_AVISO > pdf.h - 20:
        pdf.add_page()
    else:
        pdf.ln(4)
    _draw_no_fiscal_notice(pdf)

    return bytes(pdf.output())


def _fecha(valor: str | None) -> str:
    """`2026-08-04T13:20:11` → `04/08/2026 13:20`. Acepta fecha sola."""
    if not valor:
        return "—"
    try:
        dt = datetime.fromisoformat(valor)
    except ValueError:
        return valor
    return dt.strftime("%d-%m-%Y %H:%M") if "T" in valor else dt.strftime("%d-%m-%Y")
