"""El acta de entrega y la de devolución — **el papel que se firma**.

Un solo generador para las dos, con `tipo` decidiendo qué secciones entran, por
el mismo motivo que lo tiene `ingreso_pdf.py`: no son dos documentos sino los
dos lados del mismo hecho, y separarlos en dos archivos garantiza que dentro de
tres meses tengan membretes, márgenes y redacciones distintas.

**La maqueta sale de `ingreso_pdf.py`, no se vuelve a inventar.** Ese generador
ya resolvió el comprobante que el cliente firma en el mostrador —membrete
compartido, secciones de estado físico y accesorios, línea de firma, leyenda
legal— y esto es el mismo documento para el equipo que se entrega en alquiler.
Dos archivos con dos redacciones es cómo el cliente se da cuenta de que los
papeles no parecen del mismo lugar.

**Lo que este PDF tiene y el del ingreso no: dos firmas.** En el taller firma
uno solo —el que trae el equipo o el que lo retira—; acá la entrega tiene dos
partes presentes, el técnico que instala y quien recibe en el cliente, y el
acta vale por las dos. Siguen siendo firmas de **papel**: el sistema guarda las
aclaraciones tipeadas (`entrega_nombre`, `recibe_nombre`) y nada más. No hay
firma digital y no debería haberla — precedente explícito en la revisión
`0023`, que dropeó `incidencias_firmas` justamente por esto.

**Y una sección por equipo, no una tabla.** El estado físico y los accesorios
son texto libre que el técnico tipea en el lugar; en una tabla de ancho fijo
entran tres palabras y el resto se recorta, que en un papel que se firma
significa perder justo el detalle que después se discute.

**La leyenda legal no es decorativa** y está acá abajo, en un solo lugar, para
que se pueda discutir y cambiar sin tocar el dibujo. Igual que la de
`ingreso_pdf`, **la redactó el LLM y espera revisión humana**: es texto que el
cliente firma.
"""
from __future__ import annotations

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

_LINEA = 4.5
# 🔴 **18 y no 14, y el número está medido, no copiado.** `ingreso_pdf.py`
# reserva 14 para este mismo aviso; `_draw_no_fiscal_notice` avanza **18 mm**
# —medido sobre el PDF generado, con la altura antes y después de la llamada—,
# así que con la `y` justo en esa franja de 4 mm la reserva alcanza para el
# chequeo y no para el dibujo: el recuadro se traza y el texto se lo lleva el
# salto automático a la carilla siguiente. Es exactamente el defecto que el
# comentario de abajo dice haber pagado ya en el informe.
_ALTO_AVISO = 18
# Lo que ocupa el par de firmas con su aire. Se reserva antes de empezarlas:
# ver `_firmas`.
_ALTO_FIRMAS = 32

_ENCABEZADOS = {
    "entrega": ("ACT", "Acta de entrega de equipos"),
    "devolucion": ("ACT", "Acta de devolución de equipos"),
}

_TITULO_EQUIPOS = {
    "entrega": "Equipos entregados",
    "devolucion": "Equipos devueltos",
}

_LEYENDA = {
    "entrega": (
        "El cliente recibe los equipos detallados en este acta, en el estado y "
        "con los accesorios consignados para cada uno, y los tiene por "
        "aceptados con la firma del presente. "
        "Los equipos son propiedad del locador salvo indicación expresa en el "
        "contrato de referencia y deben restituirse en las mismas condiciones, "
        "salvo el desgaste normal de uso. "
        "El cliente se obliga a no cederlos, prendarlos ni trasladarlos a otro "
        "domicilio sin aviso previo, y a permitir su inspección y "
        "mantenimiento. "
        "La pérdida, el faltante de accesorios o el daño no atribuible al uso "
        "normal se facturan al valor de reposición vigente."
    ),
    "devolucion": (
        "El locador recibe los equipos detallados en este acta en el estado "
        "consignado para cada uno. "
        "Los faltantes y daños asentados arriba se tienen por aceptados por "
        "ambas partes con la firma del presente y se facturan al valor de "
        "reposición indicado. "
        "La recepción no implica conformidad sobre defectos no visibles en "
        "este acto, que se notificarán dentro de los 10 días corridos. "
        "No nos responsabilizamos por la información almacenada en los "
        "equipos: el cliente declara haber realizado copia de resguardo y "
        "autoriza su borrado."
    ),
}


class _ActaPDF(_TextoSeguroPDF, FPDF):
    """`_TextoSeguroPDF` primero en el MRO: es quien hace que el guión largo,
    las comillas curvas y los puntos suspensivos se **dibujen** en vez de tumbar
    la request.

    Igual que en el comprobante del taller, acá no es teórico: el estado físico
    y los faltantes los tipea el técnico en el domicilio del cliente, y pegar
    algo desde WhatsApp alcanza para meter un `—`.
    """

    def __init__(self, empresa: dict, datos: dict) -> None:
        super().__init__()
        self.empresa = empresa
        self.datos = datos
        self.tipo = datos["tipo"]
        # El mismo marco que dibujan la cabecera, las reglas de sección y el
        # pie. Sin esto queda el margen de fpdf2 —10 mm— y todo el cuerpo sale
        # 8 mm a la izquierda del recuadro recién dibujado, firmas incluidas.
        self.set_margins(_LX, _LX, _LX)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self) -> None:  # noqa: D102 — la firma la impone fpdf2
        if self.page_no() != 1:
            self.set_y(_LX)
            return
        letra, titulo = _ENCABEZADOS[self.tipo]
        info = [
            ("Acta:", self.datos["numero"]),
            ("Fecha:", _sello(self.datos["fecha"])),
            # El número de contrato en el encabezado y no perdido en el cuerpo:
            # es el dato por el que se cruzan el papel y el sistema, y es lo
            # primero que se busca cuando aparece un reclamo.
            ("Contrato:", self.datos["contrato"]["numero"]),
        ]
        self.set_y(_draw_header_block(
            self, letra, titulo, "", info, self.empresa,
        ))

    def footer(self) -> None:  # noqa: D102
        self.set_y(-15)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_MUTED)
        self.cell(_CW, 5, f"Página {self.page_no()} de {{nb}}", align="C")


def _sello(iso: str | None) -> str:
    """`2026-08-17` → `17-08-2026`.

    Sin hora, a diferencia del comprobante del taller: un acta es de un día —se
    firma en el domicilio del cliente— y `contratos_actas.fecha` es un `Date`.
    El formato es el `dd-mm-aaaa` que fijó el estándar de la familia.
    """
    if not iso:
        return "—"
    fecha = iso.partition("T")[0]
    a, m, d = fecha.split("-")
    return f"{d}-{m}-{a}"


def _pesos(valor: float | None, moneda: str = "ARS") -> str:
    """`12345.6` → `$ 12.345,60`. Separadores de acá, no los de Python.

    Se formatea en el generador y no se manda ya armado desde el repositorio
    porque es presentación pura — el mismo criterio con el que
    `frontend/src/lib/format.ts` tiene su propio `pesos()` para la pantalla.
    """
    if valor is None:
        return "—"
    entero, _, decimales = f"{valor:,.2f}".partition(".")
    entero = entero.replace(",", ".")
    simbolo = "US$" if moneda == "USD" else "$"
    return f"{simbolo} {entero},{decimales}"


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
    pdf.cell(ancho - 30, _LINEA, recortar(pdf, valor or "—", ancho - 30))


def _parrafo(pdf: FPDF, texto: str | None, *, sangria: float = 0) -> None:
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*_INK)
    ancho = _CW - sangria
    if not texto:
        pdf.set_text_color(*_MUTED)
        pdf.set_x(_LX + sangria)
        pdf.cell(ancho, _LINEA, "—")
        pdf.ln(_LINEA)
        return
    for linea in _wrap_text(pdf, texto, ancho_util(ancho)):
        # El renglón que devuelve `_wrap_text` se mide igual antes de dibujarlo:
        # sostiene la invariante —nada se dibuja sin medirse— con cualquier pin
        # de LibraCore.
        pdf.set_x(_LX + sangria)
        pdf.cell(ancho, _LINEA, recortar(pdf, linea, ancho))
        pdf.ln(_LINEA)


def _etiqueta_de_bloque(pdf: FPDF, texto: str) -> None:
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*_MUTED)
    pdf.cell(_CW, _LINEA, texto.upper())
    pdf.ln(_LINEA)
    pdf.set_text_color(*_INK)


def _equipo(pdf: FPDF, linea: dict, *, tipo: str, moneda: str) -> None:
    """El bloque de un equipo. Ver el docstring: es una sección, no una fila.

    Se reserva un alto mínimo antes de empezarlo para que el nombre del equipo
    no quede en una carilla y su estado en la siguiente — un acta partida así
    no dice de qué equipo habla la mitad de abajo.
    """
    if pdf.get_y() > pdf.h - 60:
        pdf.add_page()

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 9.5)
    for renglon in _wrap_text(pdf, linea["activo_descripcion"] or "—", ancho_util(_CW)):
        pdf.cell(_CW, 5, recortar(pdf, renglon, _CW))
        pdf.ln(5)
    _campo(pdf, "N.º de serie", linea["activo_serial"])
    _campo(pdf, "Cód. interno", linea["activo_codigo_interno"])
    pdf.ln(_LINEA + 1)

    _etiqueta_de_bloque(pdf, "Estado físico")
    _parrafo(pdf, linea["estado_fisico"], sangria=4)
    _etiqueta_de_bloque(pdf, "Accesorios")
    _parrafo(pdf, linea["accesorios"], sangria=4)

    if tipo == "devolucion":
        # Los tres que sólo existen devolviendo. En la entrega ni siquiera se
        # imprimen los títulos: un acta con "Faltantes: —" invita a discutir
        # sobre algo que no aplica.
        _etiqueta_de_bloque(pdf, "Faltantes")
        _parrafo(pdf, linea["faltantes"], sangria=4)
        _etiqueta_de_bloque(pdf, "Daños")
        _parrafo(pdf, linea["danios"], sangria=4)
        if linea["cargo_reposicion"]:
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.cell(_CW, _LINEA, recortar(
                pdf,
                f"Cargo de reposición: {_pesos(linea['cargo_reposicion'], moneda)}",
                _CW,
            ))
            pdf.ln(_LINEA)

    if linea["observaciones"]:
        _etiqueta_de_bloque(pdf, "Observaciones")
        _parrafo(pdf, linea["observaciones"], sangria=4)

    pdf.ln(1)
    pdf.set_draw_color(*_LINE)
    pdf.line(_LX, pdf.get_y(), _RX, pdf.get_y())


def _firmas(pdf: FPDF, izquierda: tuple[str, str | None],
            derecha: tuple[str, str | None]) -> None:
    """Las dos firmas, una al lado de la otra. Es para lo que existe el papel.

    Se reserva el alto **antes** de dibujar y se abre página si no entra: una
    firma partida entre dos hojas deja la línea en una y el nombre en la otra, y
    eso no es un problema de estética sino un comprobante que no sirve.
    """
    if pdf.get_y() > pdf.h - (_ALTO_FIRMAS + 25):
        pdf.add_page()
    pdf.ln(14)

    ancho = _CW / 2 - 10
    y = pdf.get_y()
    pdf.set_draw_color(*_LINE)
    pdf.line(_LX, y, _LX + ancho, y)
    pdf.line(_LX + _CW / 2 + 10, y, _RX, y)

    for x, (etiqueta, aclaracion) in (
        (_LX, izquierda), (_LX + _CW / 2 + 10, derecha),
    ):
        pdf.set_xy(x, y + 1)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*_MUTED)
        pdf.cell(ancho, _LINEA, etiqueta)
        pdf.set_xy(x, y + 1 + _LINEA)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*_INK)
        pdf.cell(ancho, _LINEA, recortar(pdf, aclaracion or "", ancho))

    pdf.set_y(y + 1 + _LINEA * 2)


def _leyenda(pdf: FPDF, tipo: str) -> None:
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_text_color(*_MUTED)
    for linea in _wrap_text(pdf, _LEYENDA[tipo], ancho_util(_CW)):
        pdf.cell(_CW, 3.2, linea)
        pdf.ln(3.2)
    pdf.set_text_color(*_INK)


def _sello_anulada(pdf: FPDF) -> None:
    """Un acta anulada que se imprime tiene que decirlo, y arriba de todo.

    Sin esto el PDF de una anulada es idéntico al de la vigente: el estado vive
    en la pantalla y el papel que queda sobre el escritorio no lo sabe.
    """
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(190, 30, 45)
    pdf.cell(_CW, 6, "ACTA ANULADA — SIN VALIDEZ", align="C")
    pdf.ln(8)
    pdf.set_text_color(*_INK)


def generar_pdf_acta(datos: dict) -> bytes:
    """`datos` viene de `ActaRepository.datos_para_pdf()`.

    Los datos y la presentación van separados por el mismo motivo que en el
    informe y en el comprobante del taller: así el contenido se testea sin abrir
    un binario.
    """
    tipo = datos["tipo"]
    if tipo not in _ENCABEZADOS:
        raise ValueError(f"tipo de acta desconocido: {tipo!r}")

    empresa = _empresa()
    pdf = _ActaPDF(empresa, datos)
    pdf.alias_nb_pages()
    pdf.add_page()

    if datos.get("anulada"):
        _sello_anulada(pdf)

    cli = datos["cliente"]
    _draw_emisor_cliente(pdf, empresa, [
        ("Cliente", cli["nombre"]),
        ("CUIT", cli.get("cuit")),
        ("Domicilio", cli.get("domicilio")),
        ("Teléfono", cli.get("telefono")),
    ])

    contrato = datos["contrato"]
    _titulo_seccion(pdf, "Contrato")
    _campo(pdf, "Número", contrato["numero"])
    _campo(pdf, "Modalidad", contrato["tipo"])
    pdf.ln(_LINEA)
    _campo(pdf, "Vigente desde", _sello(contrato["fecha_inicio"]))
    _campo(pdf, "Instalado en", contrato["domicilio_instalacion"])
    pdf.ln(_LINEA + 1)

    moneda = contrato.get("moneda") or "ARS"
    _titulo_seccion(pdf, _TITULO_EQUIPOS[tipo])
    for linea in datos["lineas"]:
        _equipo(pdf, linea, tipo=tipo, moneda=moneda)

    if tipo == "devolucion" and datos.get("cargo_total"):
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(_CW, 5, f"Total a reponer: {_pesos(datos['cargo_total'], moneda)}",
                 align="R")
        pdf.ln(6)

    _titulo_seccion(pdf, "Observaciones")
    _parrafo(pdf, datos["observaciones"])

    _firmas(
        pdf,
        ("Firma y aclaración de quien entrega", datos.get("entrega_nombre")),
        ("Firma y aclaración de quien recibe", datos.get("recibe_nombre")),
    )
    _leyenda(pdf, tipo)

    # Lugar reservado antes del aviso, por el defecto ya pagado en el informe y
    # en el comprobante del taller: `_draw_no_fiscal_notice` traza el recuadro y
    # recién después escribe, así que un salto automático deja el marco en una
    # carilla y el texto en la otra.
    if pdf.get_y() + _ALTO_AVISO > pdf.h - 20:
        pdf.add_page()
    else:
        pdf.ln(4)
    _draw_no_fiscal_notice(pdf)
    return bytes(pdf.output())
