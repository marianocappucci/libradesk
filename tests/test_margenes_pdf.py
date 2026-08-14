"""**Nada se dibuja fuera del marco del papel**, en los tres PDF propios de
LibraDesk: la orden de trabajo, los dos comprobantes de ingreso y el informe.

El marco lo definen `_LX` y `_RX` de LibraCore: entre esos dos milímetros
dibujan el membrete, las tarjetas de emisor/cliente, las reglas de sección y el
pie. El cuerpo, en cambio, se escribe con el flujo de fpdf2 (`cell` + `ln`), y
ahí había dos agujeros, los dos medidos sobre un PDF de producción:

1. **El documento no fijaba su margen.** `_IncidenciaPDF` y `_IngresoPDF`
   heredaban de `_TextoSeguroPDF` y nunca llamaban a `set_margins`, así que
   quedaba el default de fpdf2 —10 mm— y **todo el cuerpo salía 8 mm a la
   izquierda del marco que su propia cabecera acababa de dibujar**: los títulos
   de sección arrancaban afuera de la línea que los subraya. `InformePDF`, su
   hermana en este mismo repo, sí lo llamaba.
2. **Texto más ancho que su celda.** `cell` no recorta ni envuelve: el título
   del ticket, que lo escribe quien lo abre, se dibujaba entero. Medido en una
   hoja de 210 mm: 295 mm de borde derecho con un título de una frase, 536 mm
   con un texto sin espacios.

Los tests **miden el PDF terminado** parseando el content stream. Un `assert`
sobre `_LX` pasaría igual con el defecto puesto: el defecto nunca estuvo en el
valor de `_LX`, sino en quién lo usa.
"""
from datetime import date
from io import BytesIO

import pytest
from fpdf.fonts import CORE_FONTS_CHARWIDTHS
from libracore import pdf_generator as pg
from pypdf import PdfReader
from pypdf.generic import ByteStringObject, ContentStream

from app.services import incidencia_pdf, informe_pdf, ingreso_pdf, pdf_texto

MM = 72 / 25.4

#: Una "palabra" sin espacios más ancha que cualquier renglón: un serial
#: pegado, una URL, un código de orden de compra. Es el caso que el corte por
#: palabra no puede resolver solo.
MONSTRUO = "X" * 220

#: Texto largo pero normal: así es un título de ticket real.
LARGO = ("Tendido de red de voz y datos categoria 6 para el edificio nuevo de "
         "administracion, incluyendo enlace troncal con el Data Center")

EMPRESA = {
    "nombre": "Adolfo Lagrace Comunicaciones S.R.L.",
    "direccion": "Av. Carlos Gardel 172, Suipacha, Buenos Aires",
    "cuit": "30-65903401-4", "telefono": "02324-44-1234",
    "email": "administracion@lagrace.com.ar", "logo_path": None,
    "iibb": "902-677083-3", "iva_condition": "IVA Responsable Inscripto",
    "inicio_actividades": "25-06-1993",
}

_FUENTES = {
    "/Helvetica": "helvetica", "/Helvetica-Bold": "helveticaB",
    "/Helvetica-Oblique": "helveticaI", "/Helvetica-BoldOblique": "helveticaBI",
    "/Times-Roman": "times", "/Courier": "courier",
}


@pytest.fixture(autouse=True)
def empresa(monkeypatch):
    """El membrete sin tocar la config de disco. Se parchea en los tres módulos
    porque cada uno importó `_empresa` por nombre."""
    for modulo in (pg, incidencia_pdf, ingreso_pdf, informe_pdf):
        if hasattr(modulo, "_empresa"):
            monkeypatch.setattr(modulo, "_empresa", lambda: dict(EMPRESA))


# ── La medición ────────────────────────────────────────────────────

def _ancho(txt, fuente, size):
    """El ancho del texto en mm, con las métricas de la fuente core que el PDF
    declara. Con un promedio, la medición no podría distinguir "entra justo" de
    "se pasa por poco"."""
    cw = CORE_FONTS_CHARWIDTHS.get(fuente) or CORE_FONTS_CHARWIDTHS["helvetica"]
    return sum(cw.get(c, 500) for c in txt) * 0.001 * size / MM


def _dibujado(page):
    """[(que, x_izq_mm, x_der_mm, texto)] de todo lo que la página dibuja.

    Se parsea el content stream —`Tm`/`Td`/`TD`/`T*`/`Tj`/`TJ` para el texto,
    `m`/`l`/`re` para líneas y recuadros— en vez de usar `extract_text`, que no
    informa la coordenada de arranque: una medición sobre `extract_text` compara
    `0 + ancho` contra el borde y pasa con el defecto entero puesto.
    """
    fuentes = {
        k: _FUENTES.get(str(v.get_object().get("/BaseFont")), "helvetica")
        for k, v in (page.get("/Resources", {}).get("/Font", {}) or {}).items()
    }
    tm = lm = [1, 0, 0, 1, 0, 0]
    size, fuente, leading, x_traz = 0.0, "helvetica", 0.0, 0.0
    out = []
    for ops, op in ContentStream(page.get_contents(), page.pdf).operations:
        o = op.decode() if isinstance(op, bytes) else op
        if o == "BT":
            tm = lm = [1, 0, 0, 1, 0, 0]
        elif o == "Tf":
            fuente, size = fuentes.get(str(ops[0]), "helvetica"), float(ops[1])
        elif o == "TL":
            leading = float(ops[0])
        elif o == "Tm":
            tm = lm = [float(v) for v in ops]
        elif o in ("Td", "TD"):
            if o == "TD":
                leading = -float(ops[1])
            lm = lm[:4] + [lm[4] + float(ops[0]), lm[5] + float(ops[1])]
            tm = list(lm)
        elif o == "T*":
            lm = lm[:5] + [lm[5] - leading]
            tm = list(lm)
        elif o in ("Tj", "TJ"):
            partes = [ops[0]] if o == "Tj" else [
                e for e in ops[0] if not isinstance(e, (int, float))]
            txt = "".join(
                p.decode("cp1252", "replace")
                if isinstance(p, (bytes, ByteStringObject)) else str(p)
                for p in partes)
            w = _ancho(txt, fuente, size)
            if txt.strip():
                out.append(("texto", tm[4] / MM, tm[4] / MM + w, txt))
            tm = tm[:4] + [tm[4] + w * MM, tm[5]]
        elif o == "m":
            x_traz = float(ops[0])
        elif o == "l":
            x = float(ops[0])
            out.append(("linea", min(x_traz, x) / MM, max(x_traz, x) / MM, ""))
            x_traz = x
        elif o == "re":
            x, w = float(ops[0]), float(ops[2])
            out.append(("recuadro", min(x, x + w) / MM, max(x, x + w) / MM, ""))
    return out


def _desbordes(pdf: bytes, tolerancia: float = 0.6) -> list[str]:
    """Lo que se dibuja afuera de [`_LX`, `_RX`]."""
    fuera = []
    for n, page in enumerate(PdfReader(BytesIO(pdf)).pages, 1):
        for que, izq, der, txt in _dibujado(page):
            if izq < pg._LX - tolerancia or der > pg._RX + tolerancia:
                fuera.append(f"p{n} {que} {izq:.1f}..{der:.1f}mm {txt[:50]!r}")
    return fuera


# ── Los documentos ─────────────────────────────────────────────────

def _incidencia(texto: str) -> bytes:
    return incidencia_pdf.generar_pdf_incidencia({
        "id": 13, "fecha_creacion": "13-08-2026 04:22", "estado_label": "Abierta",
        "nro_cds": "0001-00041989",
        "cliente": {"nombre": texto, "cuit": "30-71234567-9",
                    "domicilio": texto, "email": "sistemas@arrebeef.com.ar"},
        "titulo": texto, "prioridad_label": texto, "modalidad_label": texto,
        "fecha_cierre": None, "horas": "3.50", "categoria": texto,
        "equipo": texto, "sector": texto, "recepcionista": texto,
        "tecnico": texto, "vendedor": texto, "reclamante": texto,
        "descripcion": texto, "resolucion": texto, "notas": texto,
        "materiales": [{"cantidad": 305, "descripcion": texto}],
        "actividad": [{"fecha": "13-08-2026 09:15", "descripcion": texto}],
        "firma": None,
    })


def _ingreso(texto: str, tipo: str) -> bytes:
    return ingreso_pdf.generar_pdf_ingreso({
        "numero": "REC-00000123", "numero_entrega": "ENT-00000123",
        "fecha_recepcion": "2026-08-05T14:30:00",
        "fecha_entrega": "2026-08-12T10:05:00", "incidencia_id": 13,
        "cliente": {"nombre": texto, "cuit": "30-71234567-9",
                    "domicilio": texto, "telefono": "02346-49-1200"},
        "contacto": texto, "equipo_descripcion": texto, "equipo_tipo": texto,
        "equipo_marca": texto, "equipo_modelo": texto, "equipo_serial": texto,
        "accesorios": texto, "estado_fisico": texto, "falla_declarada": texto,
        "observaciones": texto, "tecnico_nombre": texto,
        "trabajo_realizado": texto, "observaciones_entrega": texto,
        "dias_en_taller": 7, "tecnico_entrega_nombre": texto,
        "entregado_por": texto, "retirado_por": texto,
    }, tipo=tipo)


def _informe(texto: str) -> bytes:
    return informe_pdf.generar({
        "cliente": {"nombre": texto, "contacto": texto, "cuit": "30-71234567-9",
                    "domicilio": texto, "ciudad": texto, "email": texto,
                    "telefono": "02346-49-1200"},
        "periodo": {"desde": "2026-07-01", "hasta": "2026-07-31",
                    "emitido": "2026-08-01"},
        "resumen": {"recibidas": 22, "resueltas": 18, "pendientes": 4,
                    "horas": 96.5, "promedio_resolucion_horas": 2.4,
                    "actividades": 37, "por_categoria": [(texto, 9)]},
        "incidencias": [
            {"id": 101 + n, "fecha_creacion": date(2026, 7, 5), "titulo": texto,
             "equipo": texto, "estado": "cerrada", "cerrada": True,
             "fecha_cierre": date(2026, 7, 8), "horas": 3.5}
            for n in range(6)
        ],
        "parque": {"total": 48, "bajas": 3,
                   "por_estado": {"operativo": 40, "en_reparacion": 5},
                   "por_tipo": [(texto, 20)], "por_sector": [(texto, 18)]},
        "garantias": [
            {"equipo": texto, "serial": texto, "sector": texto,
             "garantia_vence": date(2026, 8, 20), "dias_restantes": 7},
            {"equipo": texto, "serial": texto, "sector": texto,
             "garantia_vence": date(2026, 6, 1), "dias_restantes": -60},
        ],
        "dias_garantia": 30,
        "service": [
            {"equipo": texto, "serial": texto, "proveedor": texto,
             "fecha_envio": date(2026, 7, 10), "abierta": True,
             "dias_afuera": 25, "fecha_retorno": None},
        ],
    })


DOCUMENTOS = [
    ("orden de trabajo", _incidencia),
    ("comprobante de recepción", lambda t: _ingreso(t, "recepcion")),
    ("comprobante de entrega", lambda t: _ingreso(t, "entrega")),
    ("informe de servicio", _informe),
]
IDS = [d[0] for d in DOCUMENTOS]


@pytest.mark.parametrize("nombre,generar", DOCUMENTOS, ids=IDS)
def test_ningun_documento_se_sale_del_marco(nombre, generar):
    """Con datos reales: títulos de una frase, equipos con marca, modelo y
    serie. Con "Cliente Test" no se sale nada — y el PDF de producción que
    destapó esto tenía el cuerpo entero 7 mm afuera."""
    fuera = _desbordes(generar(LARGO))
    assert not fuera, f"{nombre} dibuja fuera del marco:\n" + "\n".join(fuera)


@pytest.mark.parametrize("nombre,generar", DOCUMENTOS, ids=IDS)
def test_ningun_documento_se_sale_con_un_texto_sin_espacios(nombre, generar):
    """El caso que el corte por palabra no puede resolver: un solo "término"
    más ancho que el renglón. Llega de verdad — un serial pegado, una URL."""
    fuera = _desbordes(generar(MONSTRUO))
    assert not fuera, f"{nombre} dibuja fuera del marco:\n" + "\n".join(fuera)


#: Lo mínimo que `header()` necesita para dibujar el membrete.
_DATOS_MINIMOS = {"id": 1, "fecha_creacion": "13-08-2026 04:22",
                  "estado_label": "Abierta"}


@pytest.mark.parametrize("clase,args", [
    (incidencia_pdf._IncidenciaPDF, (dict(EMPRESA), _DATOS_MINIMOS)),
    (ingreso_pdf._IngresoPDF, (dict(EMPRESA), {"numero": "REC-1"}, "recepcion")),
])
def test_el_documento_arranca_en_el_margen_del_marco(clase, args):
    """La causa del desborde de la izquierda, aislada: sin esto el cuerpo
    arranca en los 10 mm de fpdf2 y la cabecera dibuja en 18."""
    doc = clase(*args)
    assert (doc.l_margin, doc.r_margin) == (pg._LX, pg._LX)


def test_el_titulo_del_ticket_se_reparte_en_renglones():
    """El defecto de la derecha, aislado: un título largo entra en dos
    renglones en vez de salirse. Se mide el ancho de cada renglón, no la
    cantidad: partir en dos y que el segundo también se pase no arregla nada."""
    pdf = incidencia_pdf._IncidenciaPDF(dict(EMPRESA), _DATOS_MINIMOS)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 10)

    renglones = pg._wrap_text(pdf, LARGO, pdf_texto.ancho_util(pg._CW))

    assert len(renglones) > 1
    for renglon in renglones:
        assert pdf.get_string_width(renglon) <= pg._CW - 2


def test_el_recorte_avisa_con_elipsis_y_no_toca_lo_que_entra():
    pdf = incidencia_pdf._IncidenciaPDF(dict(EMPRESA), _DATOS_MINIMOS)
    pdf.add_page()
    pdf.set_font("Helvetica", "", 8)

    recorte = pdf_texto.recortar(pdf, MONSTRUO, 40)

    assert recorte.endswith("…"), "sin elipsis, el texto cortado se lee como completo"
    assert pdf.get_string_width(recorte) <= 38
    assert pdf_texto.recortar(pdf, "corto", 40) == "corto"
