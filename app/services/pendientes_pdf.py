"""El listado de reclamos pendientes: el papel con el que se arma el día.

**Por qué existe, y por qué no lo cubría la hoja de ruta.** El circuito de
Lagrace empieza al revés de como lo asumía el producto: la oficina imprime
**todo lo que está esperando**, los técnicos se acomodan mirando ese papel y
recién ahí se arma el día. `hoja_ruta_pdf` es el otro extremo del mismo
circuito —una cuadrilla, un día, N paradas— y **exige haber asignado antes**:
sin `equipo_trabajo_id` y sin `fecha_programada` no hay hoja que emitir. O sea
que el sistema sabía imprimir el resultado de la planificación y no el insumo.

**Y por eso lleva teléfono y reclamante, que la hoja de ruta no tiene.** El
pedido fue textual: el teléfono va *"por si llegan y está cerrado"*, y el
reclamante es a quién preguntarle por el problema al llegar. Los dos son datos
de `clients` y de `incidencias` que hasta ahora no salían impresos en ningún
lado.

**El casillero de la izquierda es parte del producto, no decoración.** Es el
mismo criterio que ya documenta `hoja_ruta_pdf`: este papel se va lleno de lo
que el sistema sabe y vuelve marcado con lo que sólo la cuadrilla decide —qué
toma cada uno—. Sin el casillero, esa marca se hace igual, encima del texto.

**No persiste el archivo**, igual que la orden de trabajo y la hoja de ruta: es
una consulta materializada, no un comprobante numerado.
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
    _RIGHT_W,
    _RX,
    _draw_header_block,
    _empresa,
    _TextoSeguroPDF,
    _wrap_text,
)

from .hoja_ruta_pdf import direccion
from .pdf_texto import ancho_util, recortar

# `_draw_header_block` le aplica `.title()` al título, así que va sin
# preposiciones que se le vayan a capitalizar.
_LETRA = "RP"
_TITULO = "Reclamos pendientes"

#: El ancho de la celda del VALOR en las filas meta del membrete, derivado y no
#: medido. Mismo motivo que en `hoja_ruta_pdf`: `_draw_header_block` escribe con
#: un `cell()` que no recorta, y acá entra la **localidad**, que es texto libre.
_ANCHO_VALOR_MEMBRETE = _RIGHT_W - 35

_LINEA = 4.5

#: El casillero que se tilda al repartir el trabajo, en mm.
_LADO_CASILLERO = 3.2

# Las cuatro columnas fijas de la grilla. El resto —cliente, domicilio,
# teléfono, trabajo— se reparte lo que sobra, que es lo único que puede crecer.
_C_BOX = 8
_C_NUM = 13
_C_FECHA = 26
_C_PRIO = 15
_C_TEXTO = _CW - _C_BOX - _C_NUM - _C_FECHA - _C_PRIO

#: La sangría de los renglones de detalle: quedan alineados bajo el nombre del
#: cliente, no bajo el casillero.
_SANGRIA = _C_BOX + _C_NUM + _C_FECHA + _C_PRIO

#: Cuántos renglones de la descripción larga se imprimen antes de cortar.
#:
#: 🔴 **Hay un tope y es a propósito, aunque el pedido diga "descripción
#: larga".** `incidencias.descripcion` es un `Text` sin límite y lo escribe
#: quien atiende el teléfono; una descripción pegada de un mail se lleva la
#: carilla entera y deja los otros reclamos abajo de todo, que es justo lo que
#: este papel viene a evitar. Diez renglones son ~900 caracteres: de sobra para
#: un reclamo tomado por teléfono. Lo que se corta se ve completo en la ficha.
_MAX_LINEAS_DESCRIPCION = 10


class _PendientesPDF(_TextoSeguroPDF, FPDF):
    """`_TextoSeguroPDF` primero en el MRO, por lo mismo que en los otros
    cuatro: es quien hace que un guión largo o una comilla curva se **dibujen**
    en vez de tumbar la request. Acá entra por casi todo —nombre del cliente,
    domicilio, título y descripción del reclamo, nombre del reclamante—, que es
    texto libre de punta a punta.
    """

    def __init__(self, empresa: dict, datos: dict) -> None:
        super().__init__()
        self.empresa = empresa
        self.datos = datos
        # El marco que dibujan la cabecera, las reglas y el pie. Sin esto queda
        # el margen de fpdf2 —10 mm— y el cuerpo entero sale 8 mm a la
        # izquierda del recuadro. Es el defecto que ya se pagó tres veces en
        # este producto; ver `pdf_texto.py`.
        self.set_margins(_LX, _LX, _LX)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self) -> None:  # noqa: D102 — la firma la impone fpdf2
        if self.page_no() == 1:
            # Con la MISMA fuente que usa el membrete para los valores
            # (`Helvetica-Bold 7`), porque `recortar` mide con la fuente activa.
            self.set_font("Helvetica", "B", 7)
            info = [
                ("Emitido:", self.datos["emitido"]),
                ("Reclamos:", str(len(self.datos["reclamos"]))),
                ("Orden:", self.datos["orden_label"]),
            ]
            if self.datos.get("ciudad"):
                info.append(("Localidad:", recortar(
                    self, self.datos["ciudad"], _ANCHO_VALOR_MEMBRETE,
                )))
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


def _cabecera_grilla(pdf: FPDF) -> None:
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(*_MUTED)
    pdf.cell(_C_BOX, _LINEA, "")
    pdf.cell(_C_NUM, _LINEA, "N°")
    pdf.cell(_C_FECHA, _LINEA, "INGRESO")
    pdf.cell(_C_PRIO, _LINEA, "PRIOR.")
    pdf.cell(_C_TEXTO, _LINEA, "CLIENTE, CONTACTO Y TRABAJO")
    pdf.ln(_LINEA)
    pdf.set_draw_color(*_LINE)
    pdf.line(_LX, pdf.get_y(), _RX, pdf.get_y())
    pdf.ln(1.5)


def _casillero(pdf: FPDF) -> None:
    """El cuadradito que se tilda al repartir el trabajo entre las cuadrillas.

    Se dibuja a mano y no con un carácter `☐`: la fuente core de fpdf2 es
    Latin-1 y ese glifo no existe en ella, así que saldría como un signo de
    interrogación o lo reemplazaría `_TextoSeguroPDF`.
    """
    y = pdf.get_y() + (_LINEA - _LADO_CASILLERO) / 2
    pdf.set_draw_color(*_MUTED)
    pdf.rect(pdf.get_x() + 1, y, _LADO_CASILLERO, _LADO_CASILLERO)


def _lineas_detalle(pdf: FPDF, r: dict) -> list[tuple[str, str, tuple[int, int, int]]]:
    """Los renglones que van debajo del encabezado de la fila, ya envueltos.

    Se arman **antes** de dibujar nada para poder medir el alto del bloque: un
    reclamo partido por el salto de página deja el domicilio en una carilla y el
    teléfono en la otra, que son los dos datos que se miran juntos.

    Devuelve `(texto, estilo, color)`. 🔑 **El estilo viaja con el renglón y no
    lo decide el dibujante**: el título va en negrita, que es más ancha, así que
    la línea se envuelve acá con la misma fuente con la que se va a dibujar. Si
    el dibujante la eligiera aparte, el título envuelto con la fuente normal se
    pasaría de la columna al salir en negrita.
    """
    ancho = ancho_util(_C_TEXTO)
    lineas: list[tuple[str, str, tuple[int, int, int]]] = []

    # El domicilio se envuelve en vez de recortarse: una dirección cortada con
    # elipsis es una dirección a la que no se llega. Mismo criterio que la hoja
    # de ruta, y la regla de no repetir la ciudad se reusa de allá.
    pdf.set_font("Helvetica", "", 8)
    domicilio = direccion(r.get("cliente_domicilio"), r.get("cliente_ciudad"))
    if domicilio:
        lineas += [(linea, "", _INK) for linea in _wrap_text(pdf, domicilio, ancho)]
    else:
        # En gris y dicho con todas las letras: el reclamo existe igual, pero
        # el renglón se lee como "falta un dato" y no como una dirección.
        lineas.append(("sin domicilio cargado", "", _MUTED))

    # 🔑 El teléfono también se dice cuando NO está. Es el dato que el pedido
    # justificó explícitamente —"por si llegan y está cerrado"— así que un
    # renglón que lo omita en silencio deja creer que se llamó y no atendieron.
    contacto = [f"Tel. {r['cliente_telefono']}" if r.get("cliente_telefono")
                else "sin teléfono cargado"]
    if r.get("reclamante"):
        contacto.append(f"Reclamó: {r['reclamante']}")
    if r.get("modalidad_label"):
        contacto.append(r["modalidad_label"])
    if r.get("nro_cds"):
        contacto.append(f"CDS {r['nro_cds']}")
    lineas.append((
        recortar(pdf, " · ".join(contacto), _C_TEXTO), "",
        _INK if r.get("cliente_telefono") else _MUTED,
    ))

    pdf.set_font("Helvetica", "B", 8)
    lineas += [(linea, "B", _INK) for linea in _wrap_text(pdf, r["titulo"], ancho)]

    if r.get("descripcion"):
        pdf.set_font("Helvetica", "", 8)
        envueltas = _wrap_text(pdf, r["descripcion"], ancho)
        cortadas = envueltas[:_MAX_LINEAS_DESCRIPCION]
        if len(envueltas) > _MAX_LINEAS_DESCRIPCION:
            cortadas[-1] = cortadas[-1].rstrip() + " […]"
        lineas += [(linea, "", _MUTED) for linea in cortadas]

    if r.get("agendado"):
        pdf.set_font("Helvetica", "", 8)
        equipo = f" · {r['equipo_trabajo']}" if r.get("equipo_trabajo") else ""
        lineas.append((
            recortar(pdf, f"Ya agendado: {r['agendado']}{equipo}", _C_TEXTO), "",
            _MUTED,
        ))

    return lineas


def _reclamo(pdf: FPDF, r: dict) -> None:
    """Un reclamo: el encabezado en la grilla y su detalle debajo."""
    lineas = _lineas_detalle(pdf, r)
    alto = _LINEA * (1 + len(lineas)) + 3

    # Sólo se adelanta la página si el bloque **entra** en una vacía. Uno más
    # alto que la carilla entera —una descripción de diez renglones en un papel
    # ya empezado— se dibuja donde está y lo parte el salto automático: pasarlo
    # de página no lo haría entrar, y el `while` que lo intentara no terminaría.
    disponible = pdf.h - 20 - _LX
    if pdf.get_y() + alto > pdf.h - 20 and alto <= disponible:
        pdf.add_page()
        _cabecera_grilla(pdf)

    _casillero(pdf)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*_INK)
    pdf.cell(_C_BOX, _LINEA, "")
    pdf.cell(_C_NUM, _LINEA, f"#{r['id']}")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(_C_FECHA, _LINEA, _ingreso(r))
    pdf.cell(_C_PRIO, _LINEA, r.get("prioridad_label") or "—")
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(_C_TEXTO, _LINEA, recortar(pdf, r["cliente_nombre"], _C_TEXTO))
    pdf.ln(_LINEA)

    for texto, estilo, color in lineas:
        pdf.set_font("Helvetica", estilo, 8)
        pdf.set_text_color(*color)
        pdf.cell(_SANGRIA, _LINEA, "")
        pdf.cell(_C_TEXTO, _LINEA, recortar(pdf, texto, _C_TEXTO))
        pdf.ln(_LINEA)

    pdf.ln(1)
    pdf.set_draw_color(*_LINE)
    pdf.line(_LX, pdf.get_y() - 1, _RX, pdf.get_y() - 1)


def _ingreso(r: dict) -> str:
    """`05-09-2026 (3 d)` — la fecha y hace cuánto que espera.

    Los días van entre paréntesis y no en una columna propia: es el mismo dato
    dicho dos veces, y separarlos gastaría ancho que necesita el domicilio.
    """
    dias = r.get("dias")
    if dias is None:
        return r.get("fecha_creacion") or "—"
    return f"{r['fecha_creacion']} ({dias} d)"


def _titulo_seccion(pdf: FPDF, texto: str) -> None:
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_ACCENT_DARK)
    pdf.cell(_CW, 5, texto.upper())
    pdf.ln(6)
    pdf.set_draw_color(*_LINE)
    pdf.line(_LX, pdf.get_y() - 1, _RX, pdf.get_y() - 1)
    pdf.set_text_color(*_INK)


def generar_pdf_pendientes(datos: dict) -> bytes:
    """`datos` viene de `IncidenciaRepository.datos_listado_pendientes()`.

    Datos y presentación separados, por lo mismo que en los otros cuatro: así lo
    que el listado *dice* se testea sin abrir un binario, y lo que hay que abrir
    el binario para ver —que el teléfono salió impreso— se testea leyendo el
    texto extraído del PDF, no el `Content-Type`.
    """
    empresa = _empresa()
    pdf = _PendientesPDF(empresa, datos)
    pdf.alias_nb_pages()
    pdf.add_page()

    _titulo_seccion(pdf, "Pendientes")
    if not datos["reclamos"]:
        # Una bandeja vacía es legítima y se dice con todas las letras. Una
        # grilla con el encabezado y nada abajo se lee como que la consulta
        # falló, y este papel se imprime justo para saber qué hay que hacer.
        pdf.set_font("Helvetica", "I", 8.5)
        pdf.set_text_color(*_MUTED)
        pdf.cell(_CW, _LINEA, _vacio(datos))
        pdf.ln(_LINEA)
        return bytes(pdf.output())

    _cabecera_grilla(pdf)
    for reclamo in datos["reclamos"]:
        _reclamo(pdf, reclamo)

    return bytes(pdf.output())


def _vacio(datos: dict) -> str:
    """El mensaje de la bandeja vacía, que dice si hubo filtro.

    Sin esto, filtrar por una localidad mal escrita produce el mismo papel que
    no tener nada pendiente, y son dos cosas muy distintas de leer un lunes a
    la mañana.
    """
    if datos.get("ciudad"):
        return f"Sin reclamos pendientes en {datos['ciudad']}."
    return "Sin reclamos pendientes."
