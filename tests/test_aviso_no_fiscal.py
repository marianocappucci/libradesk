"""El aviso de "documento no válido como factura" entra entero o no entra.

`_draw_no_fiscal_notice` traza las cuatro líneas punteadas del recuadro y
**recién después** escribe adentro. Si el salto automático de página se dispara
entre una cosa y la otra, el marco queda en una carilla y su texto en la
siguiente: un recuadro vacío al pie de una hoja y una frase suelta arriba de la
otra. Por eso los tres documentos que lo llevan le reservan lugar antes de
llamarlo.

**El defecto que este archivo fija es que la reserva estaba mal medida.** El
cierre de `ingreso_pdf` y de `incidencia_pdf` dibuja 18 mm por debajo de la `y`
que chequea —4 del `ln(4)` de la rama `else`, 4 de aire y 10 de recuadro— y
reservaba 14. Los 4 mm de diferencia son una franja en la que el chequeo pasa y
el dibujo no entra.

**Por qué se barre en vez de apostar a un punto.** La franja donde el texto
efectivamente se va de carilla mide 1,4 mm de las 297 de una hoja A4, y las `y`
que un documento alcanza con datos de verdad caen en una grilla gruesa —los
renglones miden 4,5 y 5 mm—. Un test escrito sobre un ingreso cualquiera pasa
con el defecto puesto sin siquiera rozar el borde: se verificó, y el
comprobante de recepción **no llega a la franja por 0,2 mm** con las perillas
que expone `datos`. Es el mismo error que ya se cometió en
`test_informe_cliente.py`, donde un test de paginación se escribió con 12
incidencias y pasaba porque caía en la zona sana.

Se mide el PDF terminado —el content stream, no el código—: un `assert` sobre
`_ALTO_AVISO` pasaría igual con el defecto puesto, porque el defecto nunca
estuvo en leer la constante sino en cuánto vale.
"""
from io import BytesIO

import pytest
from libracore import pdf_generator as pg
from pypdf import PdfReader
from pypdf.generic import ContentStream

from app.services import incidencia_pdf, informe_pdf, ingreso_pdf

MM = 72 / 25.4

#: El borde inferior útil: `set_auto_page_break(margin=20)`. Lo que se dibuje
#: más abajo que esto se lo lleva el salto de página.
CORTE = 297 - 20

EMPRESA = {
    "nombre": "Adolfo Lagrace Comunicaciones S.R.L.",
    "direccion": "Av. Carlos Gardel 172, Suipacha, Buenos Aires",
    "cuit": "30-65903401-4", "telefono": "02324-44-1234",
    "email": "administracion@lagrace.com.ar", "logo_path": None,
    "iibb": "902-677083-3", "iva_condition": "IVA Responsable Inscripto",
    "inicio_actividades": "25-06-1993",
}


@pytest.fixture(autouse=True)
def empresa(monkeypatch):
    """El membrete sin tocar la config de disco. Se parchea en cada módulo
    porque todos importaron `_empresa` por nombre."""
    for modulo in (pg, incidencia_pdf, ingreso_pdf, informe_pdf):
        if hasattr(modulo, "_empresa"):
            monkeypatch.setattr(modulo, "_empresa", lambda: dict(EMPRESA))


# ── La medición ────────────────────────────────────────────────────

def _es_warning(rgb: tuple) -> bool:
    """El color del aviso, y de nada más en estos documentos."""
    return all(abs(v - c / 255) < 0.01 for v, c in zip(rgb, pg._WARNING))


def _recuadro(page) -> list[float]:
    """Las `y` —en mm desde el borde de arriba— de los trazos del recuadro.

    Se leen del content stream y no de `extract_text`, que no informa nada de
    las líneas: el recuadro es justamente la mitad del aviso que no es texto, y
    el defecto consiste en que las dos mitades se separen.
    """
    contenido = page.get_contents()
    if contenido is None:
        return []
    alto = float(page.mediabox.height)
    ys: list[float] = []
    trazo: tuple | None = None
    y_m = 0.0
    for ops, op in ContentStream(contenido, page.pdf).operations:
        o = op.decode() if isinstance(op, bytes) else op
        if o == "RG":
            trazo = tuple(float(v) for v in ops)
        elif o == "m":
            y_m = float(ops[1])
        elif o == "l":
            y_l = float(ops[1])
            if trazo is not None and _es_warning(trazo):
                ys += [(alto - y_m) / MM, (alto - y_l) / MM]
            y_m = y_l
    return ys


def _aviso(pdf_bytes: bytes) -> tuple[int | None, int | None, float | None]:
    """(carilla del recuadro, carilla del texto, borde inferior del recuadro)."""
    marco = texto = None
    borde = None
    for n, page in enumerate(PdfReader(BytesIO(pdf_bytes)).pages, 1):
        ys = _recuadro(page)
        if ys and marco is None:
            marco, borde = n, max(ys)
        if texto is None and "FACTURA" in (page.extract_text() or "").upper():
            texto = n
    return marco, texto, borde


def _revisar(pdf_bytes: bytes, caso: str) -> None:
    """Las dos mitades juntas, y el recuadro adentro de la hoja útil."""
    marco, texto, borde = _aviso(pdf_bytes)
    assert marco is not None, f"no se dibujó el recuadro del aviso ({caso})"
    assert texto is not None, f"no se escribió el texto del aviso ({caso})"
    assert marco == texto, (
        f"el aviso quedó partido: recuadro en la carilla {marco} y su texto en "
        f"la {texto} ({caso})")
    assert borde <= CORTE + 0.1, (
        f"el recuadro termina en {borde:.1f} mm, debajo del corte de "
        f"{CORTE} mm: la reserva no cubre lo que el aviso dibuja ({caso})")


# ── Los documentos ─────────────────────────────────────────────────

_PALABRAS = "palabra " * 40


def _orden_de_trabajo(n_notas: int, n_actividad: int) -> bytes:
    return incidencia_pdf.generar_pdf_incidencia({
        "id": 13, "fecha_creacion": "13-08-2026 04:22", "estado_label": "Abierta",
        "nro_cds": "0001-00041989",
        "cliente": {"nombre": "Arrebeef S.A.", "cuit": "30-71234567-9",
                    "domicilio": "Ruta 5 km 101", "email": "sistemas@arrebeef.com.ar"},
        "titulo": "Cambio de switch de borde", "prioridad_label": "Alta",
        "modalidad_label": "On site", "fecha_cierre": None, "horas": "3.50",
        "categoria": "Redes", "equipo": "Switch de borde", "sector": "Depósito",
        "recepcionista": "Ana", "tecnico": "Juan", "vendedor": "Luis",
        "reclamante": "Pedro", "descripcion": "Se cae el enlace troncal",
        "resolucion": "Se reemplazó el equipo", "notas": _PALABRAS[:8 * n_notas],
        "materiales": [{"cantidad": 1, "descripcion": "Switch 24 puertos"}],
        "actividad": [{"fecha": "13-08-2026 09:15", "descripcion": "Revisión"}
                      for _ in range(n_actividad)],
        "firma": None,
    })


def _comprobante(n_desc: int, n_obs: int, tipo: str) -> bytes:
    return ingreso_pdf.generar_pdf_ingreso({
        "numero": "REC-00000123", "numero_entrega": "ENT-00000123",
        "fecha_recepcion": "2026-08-05T14:30:00",
        "fecha_entrega": "2026-08-12T10:05:00", "incidencia_id": 13,
        "cliente": {"nombre": "Arrebeef S.A.", "cuit": "30-71234567-9",
                    "domicilio": "Ruta 5 km 101", "telefono": "02346-49-1200"},
        "contacto": "Sistemas", "equipo_descripcion": _PALABRAS[:8 * n_desc] or "Notebook",
        "equipo_tipo": "Notebook", "equipo_marca": "Dell",
        "equipo_modelo": "Latitude 5420", "equipo_serial": "8XKQ2H3",
        "accesorios": "Cargador y funda", "estado_fisico": "Rayones en la tapa",
        "falla_declarada": "No enciende", "observaciones": _PALABRAS[:8 * n_obs],
        "tecnico_nombre": "J. Pérez", "trabajo_realizado": _PALABRAS[:8 * n_obs],
        "observaciones_entrega": "Sin novedad", "dias_en_taller": 7,
        "tecnico_entrega_nombre": "J. Pérez",
        "entregado_por": "Marcelo Díaz", "retirado_por": "Marcelo Díaz",
    }, tipo=tipo)


# ── Con datos ──────────────────────────────────────────────────────

def test_la_orden_de_trabajo_no_parte_el_aviso():
    """🔴 Regresión, y con datos de todos los días.

    Una orden con una nota de un renglón y **dos** entradas de actividad deja
    la `y` del cierre en 261,8 mm y el aviso salía partido: el recuadro al pie
    de la carilla 1, su texto arriba de la 2.

    Se barre la cantidad de entradas de actividad —que es lo que mueve la `y`,
    de a 4,5 mm— para no depender de haber acertado el caso: de las
    combinaciones de este barrido, 31 caían del lado malo con la reserva en 14.
    """
    for n_notas in range(0, 3):
        for n_actividad in range(0, 26):
            _revisar(_orden_de_trabajo(n_notas, n_actividad),
                     f"{n_notas} renglones de notas, {n_actividad} de actividad")


@pytest.mark.parametrize("tipo", ["recepcion", "entrega"])
def test_el_comprobante_no_parte_el_aviso(tipo):
    """El mismo barrido sobre los dos comprobantes del taller.

    ⚠️ **Este barrido no alcanza para agarrar el defecto y no se pretende que
    lo haga**: la `y` del comprobante se mueve en pasos de 4,5 y 5 mm y la
    franja mala queda en un agujero de esa grilla —se le pasa por 0,2 mm—. Lo
    que fija el valor de la reserva acá es el test de abajo, que barre la `y`
    de a 0,1 mm. Éste queda igual porque es el que rompe si alguien agrega una
    sección al comprobante y corre la grilla.
    """
    for n_desc in range(0, 6):
        for n_obs in range(0, 20):
            _revisar(_comprobante(n_desc, n_obs, tipo),
                     f"{tipo}: {n_desc} renglones de equipo, {n_obs} de texto")


# ── La franja, barrida de a 0,1 mm ─────────────────────────────────

@pytest.mark.parametrize("nombre,clase,args,reserva", [
    ("comprobante de recepción", ingreso_pdf._IngresoPDF,
     (EMPRESA, {"numero": "REC-1", "fecha_recepcion": "2026-08-05T14:30:00"},
      "recepcion"), ingreso_pdf._ALTO_AVISO),
    ("orden de trabajo", incidencia_pdf._IncidenciaPDF,
     (EMPRESA, {"id": 1, "fecha_creacion": "13-08-2026 04:22",
                "estado_label": "Abierta"}), incidencia_pdf._ALTO_AVISO),
])
def test_ninguna_altura_de_arranque_parte_el_aviso(nombre, clase, args, reserva):
    """La reserva de cada documento, contra **todas** las alturas de arranque.

    Reproduce el cierre de `generar_pdf_*` —el chequeo, el `ln(4)` de la rama
    `else` y la llamada al aviso— arrancando en cada décima de milímetro del
    tramo donde la decisión se juega. Es lo que fija el valor de la constante:
    con 14 se parte en `y` de 261,6 a 263,0 y el recuadro se pasa del corte en
    los 4 mm de 259 a 263; con 18 no pasa ninguna de las dos cosas.

    Que replique esas cuatro líneas es a propósito: el barrido con datos no
    llega a la franja, así que sin esto la constante del comprobante no la
    verifica nadie.
    """
    y = 235.0
    while y <= 275.0:
        pdf = clase(*[dict(a) if isinstance(a, dict) else a for a in args])
        pdf.alias_nb_pages()
        pdf.add_page()
        pdf.set_y(round(y, 1))

        if pdf.get_y() + reserva > pdf.h - 20:
            pdf.add_page()
        else:
            pdf.ln(4)
        pg._draw_no_fiscal_notice(pdf)

        _revisar(bytes(pdf.output()), f"{nombre} arrancando en y={y:.1f} mm")
        y += 0.1


def test_el_informe_reserva_menos_y_esta_bien():
    """El informe reserva 14 y **no** hay que emparejarlo con los 18 del taller.

    Su cierre no hace el `ln(4)` y `_asegurar_espacio` corta en `h - 24` en vez
    de `h - 20`, así que los 14 le dejan 6,5 mm de sobra sobre lo que el aviso
    llega a escribir. Este test está para que el número no se "arregle" de
    prepo: subirlo mueve `_RESERVA_CIERRE` y repagina todos los informes.
    """
    assert informe_pdf._ALTO_AVISO == 14
    assert informe_pdf._RESERVA_CIERRE == 20
    assert ingreso_pdf._ALTO_AVISO == incidencia_pdf._ALTO_AVISO == 18
