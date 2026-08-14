"""La hoja de ruta de un equipo en un día: lo que la cuadrilla se lleva.

**Por qué existe.** El circuito de Lagrace la nombra dos veces —el técnico sale
con el talonario de CDS *y la hoja de ruta*, y al volver el parte se controla
**contra ella** más el satelital de las camionetas— pero LibraDesk no la sabía
emitir. O sea que el sistema no producía uno de los dos insumos del control que
después habilita a cerrar el reclamo y facturarlo. Ver
`wiki/analyses/circuito-reclamo-a-factura-lagrace.md` en el wiki del proyecto.

**Qué la diferencia de la orden de trabajo** (`incidencia_pdf.py`): aquélla es
**un ticket** y se imprime para dejarle algo al cliente; ésta es **una salida**
—un equipo, un día, N paradas— y no sale de la empresa. Por eso la unidad es
`equipo × día` y no la incidencia, y por eso no lleva membrete de cara al
cliente ni el aviso de "no válido como factura": el aviso está para que nadie
confunda un comprobante con una factura, y este papel no es un comprobante de
nada — vuelve a la oficina y muere ahí.

**Y por eso, al revés que todos los otros PDF del producto, éste sale con
renglones en blanco a propósito.** `incidencia_pdf._conformidad` documenta lo
contrario para su caso —no dibuja un recuadro de firma vacío, porque volvería el
PDF un formulario para completar a mano, que es el circuito que viene a
reemplazar—. Acá el formulario **es** el producto: la hoja se va llena de lo que
el sistema sabe (a quién visitar, dónde, a qué hora) y vuelve llena de lo que
sólo la calle sabe (a qué hora se llegó de verdad, con cuántos kilómetros se
salió y se volvió). Sin esos renglones, el control de María sigue siendo contra
un papel de afuera.

> ⚠️ **Diseñada sin haber visto una hoja de ruta real de Lagrace.** Los
> renglones de kilometraje, hora de llegada y hora de salida salen de cómo
> describieron el control, no de un modelo en mano. Es la pregunta 1 del
> resumen que se les mandó. Si la de ellos tiene otros renglones, lo que cambia
> es este archivo y nada más.

**No persiste el archivo**, igual que la orden de trabajo: es una consulta
materializada, no un comprobante numerado. Se regenera de los mismos datos.
"""
from __future__ import annotations

from datetime import date, datetime

from fpdf import FPDF
from libracore.pdf_generator import (
    _ACCENT_DARK, _CW, _INK, _LINE, _LX, _MUTED, _RX,
    _draw_header_block, _empresa, _TextoSeguroPDF, _wrap_text,
)

from .pdf_texto import ancho_util, recortar

# `_draw_header_block` le aplica `.title()` al título, así que va sin
# preposiciones que se le vayan a capitalizar.
_LETRA = "HR"
_TITULO = "Hoja de ruta"

_LINEA = 4.5

# Las cuatro columnas fijas de la grilla de paradas. El resto —cliente,
# domicilio, trabajo— se reparte lo que sobra, que es lo único que puede crecer.
_C_NUM = 9
_C_HORA = 15
_C_LLEGADA = 22
_C_SALIDA = 22
_C_TEXTO = _CW - _C_NUM - _C_HORA - _C_LLEGADA - _C_SALIDA

#: Alto de una parada con sus dos renglones de detalle, en mm. Se mide antes de
#: dibujarla: una parada partida por el salto de página deja el domicilio en una
#: carilla y la hora de llegada en la otra, que es justo el renglón que alguien
#: tiene que completar parado al lado de la camioneta.
_ALTO_PARADA = _LINEA * 3 + 2

#: Alto del bloque de cierre (kilometraje + firma). Mismo criterio.
_ALTO_CIERRE = 38


class _HojaRutaPDF(_TextoSeguroPDF, FPDF):
    """`_TextoSeguroPDF` primero en el MRO, por lo mismo que en los otros tres:
    es quien hace que un guión largo o una comilla curva se **dibujen** en vez
    de tumbar la request. Acá entra por el título del ticket y por el domicilio
    del cliente, los dos texto libre.
    """

    def __init__(self, empresa: dict, datos: dict) -> None:
        super().__init__()
        self.empresa = empresa
        self.datos = datos
        # El marco que dibujan la cabecera, las reglas y el pie. Sin esto queda
        # el margen de fpdf2 —10 mm— y el cuerpo entero sale 8 mm a la
        # izquierda del recuadro. Es el defecto que ya se pagó dos veces en
        # este producto; ver `pdf_texto.py`.
        self.set_margins(_LX, _LX, _LX)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self) -> None:  # noqa: D102 — la firma la impone fpdf2
        if self.page_no() == 1:
            info = [
                ("Equipo:", self.datos["equipo"]),
                ("Fecha:", _dia(self.datos["dia"])),
                ("Paradas:", str(len(self.datos["paradas"]))),
            ]
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


def _renglon(pdf: FPDF, ancho: float) -> None:
    """Una línea para completar a mano, del ancho que se le pida.

    Se dibuja **sobre la línea de base del texto**, no debajo del bloque: una
    raya suelta más abajo se lee como un separador de sección y no como un
    campo vacío.
    """
    y = pdf.get_y() + _LINEA - 1
    x = pdf.get_x()
    pdf.set_draw_color(*_LINE)
    pdf.line(x + 1, y, x + ancho - 2, y)


def _cabecera_grilla(pdf: FPDF) -> None:
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(*_MUTED)
    pdf.cell(_C_NUM, _LINEA, "N°")
    pdf.cell(_C_HORA, _LINEA, "HORA")
    pdf.cell(_C_TEXTO, _LINEA, "CLIENTE Y TRABAJO")
    pdf.cell(_C_LLEGADA, _LINEA, "LLEGADA", align="C")
    pdf.cell(_C_SALIDA, _LINEA, "SALIDA", align="C")
    pdf.ln(_LINEA)
    pdf.set_draw_color(*_LINE)
    pdf.line(_LX, pdf.get_y(), _RX, pdf.get_y())
    pdf.ln(1.5)


def _parada(pdf: FPDF, orden: int, p: dict) -> None:
    """Una parada: el renglón que el sistema sabe, y los dos que no.

    El orden es el de la agenda —cronológico— y va numerado porque la cuadrilla
    lo nombra por número cuando avisa por radio o por WhatsApp. **No es un orden
    de recorrido optimizado**: si ellos arman el recorrido por cercanía, esto
    hay que repensarlo, y es una de las preguntas abiertas.
    """
    if pdf.get_y() + _ALTO_PARADA > pdf.h - 20:
        pdf.add_page()
        _cabecera_grilla(pdf)

    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*_INK)
    pdf.cell(_C_NUM, _LINEA, f"{orden:02d}")
    pdf.cell(_C_HORA, _LINEA, _hora(p["desde"]))
    pdf.cell(_C_TEXTO, _LINEA, recortar(pdf, p.get("cliente_nombre") or "—", _C_TEXTO))
    # Los dos renglones para completar en la calle. Van en la MISMA fila que el
    # cliente y no al pie de la parada: quien anota la hora la busca a la altura
    # del nombre del lugar donde está parado.
    _renglon(pdf, _C_LLEGADA)
    pdf.cell(_C_LLEGADA, _LINEA, "")
    _renglon(pdf, _C_SALIDA)
    pdf.cell(_C_SALIDA, _LINEA, "")
    pdf.ln(_LINEA)

    _detalle(pdf, p.get("cliente_domicilio"), p.get("cliente_ciudad"))

    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(*_MUTED)
    pdf.cell(_C_NUM + _C_HORA, _LINEA, "")
    trabajo = f"#{p['incidencia_id']} {p.get('titulo') or ''}".strip()
    duracion = _duracion(p.get("duracion_minutos"))
    pdf.cell(_C_TEXTO, _LINEA, recortar(pdf, f"{trabajo} · {duracion}", _C_TEXTO))
    pdf.ln(_LINEA + 2)

    pdf.set_draw_color(*_LINE)
    pdf.line(_LX, pdf.get_y() - 1, _RX, pdf.get_y() - 1)


def direccion(domicilio: str | None, ciudad: str | None) -> str:
    """`domicilio` + `ciudad`, sin repetir la ciudad si ya viene adentro.

    🔴 **Salió de mirar la demo desplegada, no de un test.** Los clientes reales
    cargan la ciudad **dentro** del domicilio —`Av. Pueyrredón 1640, CABA`— y
    además tienen el campo `ciudad` con lo mismo, así que pegar los dos daba
    `Av. Pueyrredón 1640, CABA, CABA` en las tres paradas de la hoja. Con los
    datos inventados de los tests (`Av. San Martín 1240` + `Suipacha`) no
    aparecía: el defecto necesitaba **la forma de los datos de producción**.

    La comparación es por contención y sin distinguir mayúsculas. No intenta
    normalizar direcciones —eso es otro problema y más grande—: sólo evita el
    caso en que la ciudad ya está escrita.

    Pública y no `_privada` porque la usa el test, y porque es la clase de regla
    que va a querer reusar el próximo documento que imprima un domicilio.
    """
    if not domicilio:
        return ciudad or ""
    if ciudad and ciudad.strip().lower() not in domicilio.lower():
        return f"{domicilio}, {ciudad}"
    return domicilio


def _detalle(pdf: FPDF, domicilio: str | None, ciudad: str | None) -> None:
    """El domicilio, que es lo que convierte la agenda en una hoja de ruta.

    Sin esto la hoja dice a quién visitar y no dónde queda — que es la mitad que
    hace falta arriba de la camioneta. Se envuelve en vez de recortarse: una
    dirección cortada con elipsis es una dirección a la que no se llega.
    """
    texto = direccion(domicilio, ciudad) or "sin domicilio cargado"
    pdf.set_font("Helvetica", "", 8)
    # En gris si no hay domicilio: la hoja igual sale —el trabajo existe— pero
    # el renglón se lee como "falta un dato" y no como una dirección.
    pdf.set_text_color(*(_INK if domicilio else _MUTED))
    for i, linea in enumerate(_wrap_text(pdf, texto, ancho_util(_C_TEXTO))):
        pdf.cell(_C_NUM + _C_HORA, _LINEA, "")
        pdf.cell(_C_TEXTO, _LINEA, recortar(pdf, linea, _C_TEXTO))
        pdf.ln(_LINEA)
        if i == 0:
            pdf.set_text_color(*_MUTED)


def _cierre(pdf: FPDF) -> None:
    """Kilometraje de salida y regreso, y la firma de quien devuelve la hoja.

    Es el bloque contra el que se cruza el satelital de la flota: sin un
    kilometraje declarado no hay nada que comparar con lo que la camioneta
    recorrió de verdad, y el control queda en "el horario parece razonable".
    """
    if pdf.get_y() + _ALTO_CIERRE > pdf.h - 20:
        pdf.add_page()

    _titulo_seccion(pdf, "Cierre de la salida")

    pdf.set_font("Helvetica", "", 8)
    for etiqueta in ("Km al salir", "Km al regresar", "Km recorridos"):
        pdf.set_text_color(*_MUTED)
        pdf.cell(30, _LINEA, f"{etiqueta}:")
        _renglon(pdf, 34)
        pdf.cell(34, _LINEA, "")
        pdf.cell(6, _LINEA, "")
    pdf.ln(_LINEA + 6)

    pdf.set_draw_color(*_LINE)
    pdf.line(_LX, pdf.get_y(), _LX + 70, pdf.get_y())
    pdf.line(_LX + 90, pdf.get_y(), _LX + 160, pdf.get_y())
    pdf.ln(1.5)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*_MUTED)
    pdf.cell(90, _LINEA, "Firma del responsable del equipo")
    pdf.cell(70, _LINEA, "Recibido en oficina / fecha")
    pdf.ln(_LINEA)


def generar_pdf_hoja_ruta(datos: dict) -> bytes:
    """`datos` viene de `agenda.datos_hoja_ruta()`.

    Datos y presentación separados, por lo mismo que en los otros tres: así lo
    que la hoja *dice* se testea sin abrir un binario, y lo que hay que abrir el
    binario para ver —que el domicilio salió impreso— se testea leyendo el texto
    extraído del PDF, no el `Content-Type`.
    """
    empresa = _empresa()
    pdf = _HojaRutaPDF(empresa, datos)
    pdf.alias_nb_pages()
    pdf.add_page()

    _titulo_seccion(pdf, "Sale")
    _campo(pdf, "Responsable", datos.get("responsable"))
    _campo(pdf, "Vehículo", _vehiculos(datos.get("vehiculos") or []))
    pdf.ln(_LINEA)
    _campo(pdf, "Integrantes", ", ".join(datos.get("integrantes") or []) or None, _CW)
    pdf.ln(_LINEA + 1)

    _titulo_seccion(pdf, "Recorrido")
    if not datos["paradas"]:
        # Una hoja sin paradas es legítima —el equipo no sale— y se dice con
        # todas las letras. Una grilla con el encabezado y nada abajo se lee
        # como que la consulta falló.
        pdf.set_font("Helvetica", "I", 8.5)
        pdf.set_text_color(*_MUTED)
        pdf.cell(_CW, _LINEA, "Sin trabajos agendados para este día.")
        pdf.ln(_LINEA)
    else:
        _cabecera_grilla(pdf)
        for orden, parada in enumerate(datos["paradas"], start=1):
            _parada(pdf, orden, parada)

    _cierre(pdf)

    return bytes(pdf.output())


def _vehiculos(vehiculos: list[dict]) -> str | None:
    """`AB123CD (Renault Kangoo)`, y varios separados por coma.

    La patente primero porque es lo que se busca en el playón; la marca y el
    modelo van entre paréntesis y sólo si están cargados.
    """
    if not vehiculos:
        return None
    partes = []
    for v in vehiculos:
        descripcion = " ".join(x for x in (v.get("marca"), v.get("modelo")) if x)
        partes.append(f"{v['patente']} ({descripcion})" if descripcion else v["patente"])
    return ", ".join(partes)


def _duracion(minutos: int | None) -> str:
    """`90` → `1 h 30 min`. Es lo previsto, no lo que tardó."""
    if not minutos:
        return "—"
    horas, resto = divmod(minutos, 60)
    if horas and resto:
        return f"{horas} h {resto} min"
    return f"{horas} h" if horas else f"{resto} min"


def _hora(iso: str) -> str:
    """`2026-08-14T08:30:00` → `08:30`."""
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M")
    except ValueError:
        return iso


def _dia(iso: str) -> str:
    """`2026-08-14` → `14-08-2026`, que es el formato del estándar."""
    try:
        return date.fromisoformat(iso).strftime("%d-%m-%Y")
    except ValueError:
        return iso
