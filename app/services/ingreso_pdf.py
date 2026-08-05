"""Los dos comprobantes del pedido 43: **recepción** y **entrega**.

Un solo generador para los dos, con `tipo` decidiendo qué secciones entran. No
son dos documentos: son los dos lados del mismo hecho, y separarlos en dos
archivos garantizaría que dentro de tres meses tengan membretes, márgenes y
redacciones distintas — que es cómo un cliente se da cuenta de que el papel de
la entrega no es "del mismo lugar" que el de la recepción.

Mismo membrete que los remitos, presupuestos e informes, por el motivo ya
documentado en `informe_pdf.py`: tres documentos con logos distintos se leen
como salidos de tres empresas.

**Lo que este PDF tiene y la orden de trabajo no: una línea de firma.** Es el
punto del documento. El cliente firma el papel de puño y letra; el sistema
guarda la aclaración (`entregado_por` / `retirado_por`) y nada más. **No hay
firma digital y no debería haberla acá** — una casilla "aceptado" que marca el
operador no prueba nada y llamarla firma sería peor que no tenerla.

**La leyenda legal no es decorativa.** Un comprobante de recepción sin plazo de
retiro es un depósito indefinido: el taller se llena de equipos que nadie viene
a buscar y no hay nada firmado que lo respalde. El texto está acá abajo, en un
solo lugar, para que se pueda discutir y cambiar sin tocar el dibujo.
"""
from __future__ import annotations

from fpdf import FPDF
from libracore.pdf_generator import (
    _ACCENT_DARK, _CW, _INK, _LINE, _LX, _MUTED, _RX,
    _draw_emisor_cliente, _draw_header_block, _draw_no_fiscal_notice, _empresa,
    _TextoSeguroPDF, _wrap_text,
)

_LINEA = 4.5
_ALTO_AVISO = 14

# La caja de la letra del membrete. `_draw_header_block` le aplica `.title()`,
# así que los títulos van sin preposiciones.
_ENCABEZADOS = {
    "recepcion": ("REC", "Comprobante de recepción de equipo"),
    "entrega": ("ENT", "Comprobante de entrega de equipo"),
}

_LEYENDA = {
    "recepcion": (
        "El equipo se recibe exclusivamente para diagnóstico y/o reparación. "
        "El detalle de accesorios y el estado físico consignados arriba son los "
        "verificados al momento de la recepción y se tienen por aceptados por "
        "ambas partes con la firma de este comprobante. "
        "El equipo debe retirarse dentro de los 30 días corridos de notificada "
        "su finalización, presentando este comprobante. "
        "Pasado ese plazo se devengarán gastos de depósito. "
        "No nos responsabilizamos por la información almacenada: el cliente "
        "declara haber realizado copia de resguardo."
    ),
    "entrega": (
        "El cliente retira el equipo detallado y declara recibirlo conforme, "
        "con los accesorios consignados en el comprobante de recepción "
        "correspondiente. "
        "La garantía del trabajo realizado cubre exclusivamente la falla "
        "reparada y las piezas reemplazadas, por 90 días desde esta fecha. "
        "No alcanza a fallas distintas ni a daños posteriores a la entrega."
    ),
}


class _IngresoPDF(_TextoSeguroPDF, FPDF):
    """`_TextoSeguroPDF` primero en el MRO: es quien hace que el guión largo, las
    comillas curvas y los puntos suspensivos se **dibujen** en vez de tumbar la
    request.

    Acá no es teórico ni por asomo: la falla declarada y el estado físico los
    tipea el mostrador con el cliente enfrente, y pegar algo desde WhatsApp
    alcanza para meter un `—`.
    """

    def __init__(self, empresa: dict, datos: dict, tipo: str) -> None:
        super().__init__()
        self.empresa = empresa
        self.datos = datos
        self.tipo = tipo
        self.set_auto_page_break(auto=True, margin=20)

    def header(self) -> None:  # noqa: D102 — la firma la impone fpdf2
        if self.page_no() != 1:
            self.set_y(_LX)
            return
        letra, titulo = _ENCABEZADOS[self.tipo]
        if self.tipo == "recepcion":
            info = [
                ("Comprobante:", self.datos["numero"]),
                ("Fecha:", _sello(self.datos["fecha_recepcion"])),
            ]
        else:
            info = [
                ("Comprobante:", self.datos["numero_entrega"]),
                ("Fecha:", _sello(self.datos["fecha_entrega"])),
                # El número de recepción en el encabezado y no perdido en el
                # cuerpo: es el dato por el que se cruzan los dos papeles, y es
                # lo primero que se busca cuando aparece un reclamo.
                ("Recepción:", self.datos["numero"]),
            ]
        if self.datos.get("incidencia_id"):
            info.append(("Ticket:", f"#{self.datos['incidencia_id']}"))
        self.set_y(_draw_header_block(
            self, letra, titulo, "", info, self.empresa,
        ))

    def footer(self) -> None:  # noqa: D102
        self.set_y(-15)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_MUTED)
        self.cell(_CW, 5, f"Página {self.page_no()} de {{nb}}", align="C")


def _sello(iso: str | None) -> str:
    """`2026-08-05T14:30:00` → `05/08/2026 14:30`.

    Con hora, siempre. Es lo que distingue dos ingresos del mismo cliente el
    mismo día, y es lo que se discute en un reclamo.
    """
    if not iso:
        return "—"
    fecha, _, resto = iso.partition("T")
    a, m, d = fecha.split("-")
    return f"{d}/{m}/{a} {resto[:5]}".strip()


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
    pdf.cell(30, _LINEA, f"{etiqueta}:")
    pdf.set_text_color(*_INK)
    pdf.cell(ancho - 30, _LINEA, valor or "—")


def _parrafo(pdf: FPDF, texto: str | None) -> None:
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*_INK)
    if not texto:
        pdf.set_text_color(*_MUTED)
        pdf.cell(_CW, _LINEA, "—")
        pdf.ln(_LINEA)
        return
    for linea in _wrap_text(pdf, texto, _CW):
        pdf.cell(_CW, _LINEA, linea)
        pdf.ln(_LINEA)


def _bloque_firma(pdf: FPDF, etiqueta: str, aclaracion: str | None) -> None:
    """La línea de firma. Es para lo que existe el papel.

    Se reserva el alto **antes** de dibujar y se abre página si no entra: una
    firma partida entre dos hojas deja la línea en una y el nombre en la otra, y
    eso no es un problema de estética sino un comprobante que no sirve.
    """
    if pdf.get_y() > pdf.h - 55:
        pdf.add_page()
    pdf.ln(14)
    ancho = _CW / 2 - 10
    pdf.set_draw_color(*_LINE)
    y = pdf.get_y()
    pdf.line(_LX, y, _LX + ancho, y)
    pdf.ln(1)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(*_MUTED)
    pdf.cell(ancho, _LINEA, etiqueta)
    pdf.ln(_LINEA)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*_INK)
    pdf.cell(ancho, _LINEA, aclaracion or "")
    pdf.ln(_LINEA)


def _leyenda(pdf: FPDF, tipo: str) -> None:
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_text_color(*_MUTED)
    for linea in _wrap_text(pdf, _LEYENDA[tipo], _CW):
        pdf.cell(_CW, 3.2, linea)
        pdf.ln(3.2)
    pdf.set_text_color(*_INK)


def generar_pdf_ingreso(datos: dict, *, tipo: str) -> bytes:
    """`datos` viene de `IngresoRepository.datos_para_pdf()`.

    Los datos y la presentación van separados por el mismo motivo que en el
    informe y en la orden de trabajo: así el contenido se testea sin abrir un
    binario.
    """
    if tipo not in _ENCABEZADOS:
        raise ValueError(f"tipo de comprobante desconocido: {tipo!r}")

    empresa = _empresa()
    pdf = _IngresoPDF(empresa, datos, tipo)
    pdf.alias_nb_pages()
    pdf.add_page()

    cli = datos["cliente"]
    _draw_emisor_cliente(pdf, empresa, [
        ("Cliente", cli["nombre"]),
        ("CUIT", cli.get("cuit")),
        ("Domicilio", cli.get("domicilio")),
        ("Contacto", datos.get("contacto")),
        ("Teléfono", cli.get("telefono")),
    ])

    # "Equipo recibido" sólo en la recepción: en el comprobante de entrega ese
    # título se lee al revés de lo que pasa —el cliente se lo está llevando— y
    # en un papel que se firma la palabra importa. Se vio leyendo el PDF de
    # verdad, no el código.
    _titulo_seccion(pdf, "Equipo recibido" if tipo == "recepcion" else "Equipo")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(_CW, 5, datos["equipo_descripcion"] or "—")
    pdf.ln(6)
    _campo(pdf, "Tipo", datos["equipo_tipo"])
    _campo(pdf, "Marca", datos["equipo_marca"])
    pdf.ln(_LINEA)
    _campo(pdf, "Modelo", datos["equipo_modelo"])
    _campo(pdf, "N.º de serie", datos["equipo_serial"])
    pdf.ln(_LINEA + 1)

    if tipo == "recepcion":
        # Las cuatro secciones que hacen que el papel sirva para algo cuando
        # aparece una discusión. Van completas y en este orden: qué vino con el
        # equipo, cómo estaba, qué dijo que le pasaba, y qué vimos nosotros.
        _titulo_seccion(pdf, "Accesorios entregados")
        _parrafo(pdf, datos["accesorios"])

        _titulo_seccion(pdf, "Estado físico al recibirlo")
        _parrafo(pdf, datos["estado_fisico"])

        _titulo_seccion(pdf, "Falla declarada por el cliente")
        _parrafo(pdf, datos["falla_declarada"])

        _titulo_seccion(pdf, "Observaciones y daños preexistentes")
        _parrafo(pdf, datos["observaciones"])

        _titulo_seccion(pdf, "Recepción")
        _campo(pdf, "Técnico receptor", datos["tecnico_nombre"], _CW)
        pdf.ln(_LINEA)
    else:
        _titulo_seccion(pdf, "Trabajo realizado")
        _parrafo(pdf, datos["trabajo_realizado"])

        _titulo_seccion(pdf, "Observaciones")
        _parrafo(pdf, datos["observaciones_entrega"])

        _titulo_seccion(pdf, "Entrega")
        _campo(pdf, "Recibido el", _sello(datos["fecha_recepcion"]))
        _campo(pdf, "Días en taller", str(datos["dias_en_taller"]))
        pdf.ln(_LINEA)
        _campo(pdf, "Técnico", datos["tecnico_entrega_nombre"], _CW)
        pdf.ln(_LINEA)

    if tipo == "recepcion":
        _bloque_firma(pdf, "Firma y aclaración de quien entrega el equipo",
                      datos.get("entregado_por"))
    else:
        _bloque_firma(pdf, "Firma y aclaración de quien retira el equipo",
                      datos.get("retirado_por"))

    _leyenda(pdf, tipo)

    # Lugar reservado antes del aviso, por el defecto ya pagado en el informe y
    # en la orden de trabajo: `_draw_no_fiscal_notice` traza el recuadro y
    # recién después escribe, así que un salto automático deja el marco en una
    # carilla y el texto en la otra.
    if pdf.get_y() + _ALTO_AVISO > pdf.h - 20:
        pdf.add_page()
    else:
        pdf.ln(4)
    _draw_no_fiscal_notice(pdf)
    return bytes(pdf.output())
