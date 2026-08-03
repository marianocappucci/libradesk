"""El PDF del informe de servicio, con el mismo membrete que los remitos y
presupuestos que este cliente ya recibe.

**Por que importa de `libracore.pdf_generator` y no reimplementa el
maquetado.** El cliente de LibraDesk recibe hoy remitos y presupuestos
generados por LibraCore. Un informe con otro logo, otra tipografia y otra
paleta se leeria como salido de otra empresa. Reusar el membrete no es ahorro
de codigo: es que los tres documentos sean reconociblemente el mismo emisor.

**Sobre importar nombres privados de otro paquete.** `_draw_header_block`,
`_empresa` y la paleta llevan guion bajo, pero **es el patron ya establecido en
la familia**: `contalibra/app/pdf_generator.py` es un shim que importa
`_TIPO_LABELS`, `_CONCEPTO_LABELS` e `_IVA_LABELS` de la misma manera. Dos
cosas lo hacen seguro acá:

1. El pin de LibraCore es **exacto** (`libracore @ ...@v1.6.0` en
   `pyproject.toml`), no un rango. La API privada no puede cambiar debajo sin
   que alguien edite esa linea a proposito.
2. `tests/test_informe_cliente.py` afirma que cada nombre importado existe. Un
   bump de version que se lleve puesto uno de estos helpers pone el CI en rojo
   en el momento del bump — no meses despues, la primera vez que alguien pida
   un informe.

Si algun otro producto de la familia necesita lo mismo, el paso siguiente es
promover este andamiaje a API publica de LibraCore. Con un solo consumidor eso
seria una release cruzada para nada.

**No persiste el archivo**, a diferencia de `generate_pdf` (remitos) y
`generate_pdf_presupuesto`: aquellos son comprobantes numerados, que tienen que
poder reimprimirse identicos, y por eso guardan su `pdf_path`. Un informe es
una consulta materializada — se regenera de los mismos datos cuando haga falta,
asi que se devuelve en memoria y no deja archivos sueltos en `DATA_DIR`.
"""
from __future__ import annotations

from datetime import date, datetime

from fpdf import FPDF
from libracore.pdf_generator import (
    _ACCENT_DARK, _ACCENT_SOFT, _CW, _INK, _LINE, _LX, _MUTED, _RX,
    _draw_emisor_cliente, _draw_header_block, _draw_no_fiscal_notice, _empresa,
    _rrect, _wrap_text,
)

# La caja de la letra del membrete ("R" en un remito, "CC" en un resumen de
# cuenta corriente). `_draw_header_block` le aplica `.title()` al titulo, asi
# que va sin preposiciones: "Informe de servicio" saldria "Informe De
# Servicio".
_LETRA = "IS"
_TITULO = "Servicio técnico"

# 🔴 Todo el texto del PDF tiene que caber en **latin-1**. Las fuentes core de
# fpdf2 (Helvetica, la que usa todo el maquetado de LibraCore) codifican asi, y
# un caracter fuera del juego no degrada: levanta `UnicodeEncodeError` y tumba
# la request entera. Los dos que se cuelan solos son la elipsis tipografica
# (`…`, U+2026) y la raya (`—`, U+2014) — ninguno esta en latin-1, y los dos
# son los que uno escribe sin pensar al truncar texto o al marcar un dato
# vacio. Las tildes y el punto medio si estan, asi que el resto del texto en
# castellano no da problema.
_ELIPSIS = "..."
_VACIO = "-"

# Y el texto no lo escribimos solo nosotros: titulos de ticket, nombres de
# cliente, marcas, seriales y nombres de proveedor son **datos cargados por el
# usuario**. Alcanza con que alguien pegue un titulo desde Word —que convierte
# las comillas en tipograficas y los guiones en rayas— para que el endpoint
# devuelva 500. Por eso todo lo que viene de la base pasa por `_latin1()`.
_REEMPLAZOS = {
    "—": "-", "–": "-",            # raya y semirraya
    "…": _ELIPSIS,
    "“": '"', "”": '"',            # comillas tipograficas
    "‘": "'", "’": "'",
    " ": " ",                            # espacio duro
    "€": "EUR",
}


def _latin1(texto: str) -> str:
    """Texto que las fuentes core pueden dibujar. Lo que no tiene equivalente
    cae en `?`: un caracter degradado es mejor que un informe que no sale."""
    for original, reemplazo in _REEMPLAZOS.items():
        texto = texto.replace(original, reemplazo)
    return texto.encode("latin-1", "replace").decode("latin-1")

_ESTADO_EQUIPO_LABEL = {
    "activo": "En uso",
    "almacenado": "En depósito",
    "en_reparacion": "En service",
    "baja": "De baja",
}


def _fecha(valor: date | datetime | None) -> str:
    if valor is None:
        return ""
    return valor.strftime("%d/%m/%Y")


def _iso_a_dmy(valor: str) -> str:
    return f"{valor[8:10]}/{valor[5:7]}/{valor[0:4]}" if valor else ""


class InformePDF(FPDF):
    """Membrete completo en la primera pagina y una banda compacta en las
    siguientes.

    `ResumenCCPDF` repite el membrete entero en cada pagina, y para un resumen
    de cuenta de una o dos carillas esta bien. Un informe de servicio de un
    cliente con movimiento se va facil a cuatro o cinco: el bloque de 45 mm
    repetido cinco veces come mas de una carilla completa en membretes.
    """

    def __init__(self, cliente: dict, periodo: dict):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.cliente = cliente
        self.periodo = periodo
        self._emp = None
        self.set_margins(_LX, _LX, _LX)
        self.set_auto_page_break(auto=True, margin=20)
        self.set_title(_latin1(f"Informe de servicio - {cliente['nombre']}"))

    def normalize_text(self, text: str) -> str:
        """El unico punto por el que pasa **todo** el texto antes de dibujarse,
        incluido el que dibujan los helpers de LibraCore con nuestros datos.

        Sanear en cada `cell()` era jugar a no olvidarse: la primera version de
        este archivo se olvido de una semirraya en su propio encabezado y el
        endpoint devolvia 500. Acá no hay nada que recordar.

        Las llamadas a `_latin1()` que quedan repartidas **no son redundantes**:
        el ancho se mide con `get_string_width()` antes de llegar hasta acá, y
        `...` no mide lo mismo que `…`. Esas sanean para medir bien; esta, para
        no romper.
        """
        return super().normalize_text(_latin1(text))

    def header(self):
        if self.page_no() == 1:
            emp = self._emp or _empresa()
            info_fields = [
                ("Período desde:", _iso_a_dmy(self.periodo["desde"])),
                ("Período hasta:", _iso_a_dmy(self.periodo["hasta"])),
                ("Emitido:", _iso_a_dmy(self.periodo["emitido"])),
            ]
            self.set_y(_draw_header_block(
                self, _LETRA, _TITULO, "", info_fields, emp))
            return

        self.set_y(_LX)
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*_INK)
        self.cell(_CW / 2, 5, _latin1(self.cliente["nombre"])[:48], ln=False)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_MUTED)
        self.cell(
            _CW / 2, 5,
            f"Informe de servicio · {_iso_a_dmy(self.periodo['desde'])}"
            f" - {_iso_a_dmy(self.periodo['hasta'])}",
            align="R", ln=False,
        )
        y = _LX + 6
        self.set_draw_color(*_INK)
        self.set_line_width(0.5)
        self.line(_LX, y, _RX, y)
        self.set_text_color(*_INK)
        self.set_y(y + 5)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_MUTED)
        self.cell(_CW, 5, f"Página {self.page_no()} de {{nb}}", align="C", ln=False)
        self.set_text_color(*_INK)


# ── Piezas de maquetado ────────────────────────────────────────────

def _titulo_seccion(pdf: FPDF, texto: str, aclaracion: str | None = None) -> None:
    """Salta de pagina si el titulo quedaria al pie sin nada debajo: un
    encabezado solo al final de una carilla es peor que el corte."""
    if pdf.get_y() + 24 > pdf.h - 20:
        pdf.add_page()
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*_INK)
    pdf.set_x(_LX)
    pdf.cell(_CW, 6, texto, ln=True)
    if aclaracion:
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*_MUTED)
        pdf.set_x(_LX)
        pdf.cell(_CW, 4, aclaracion, ln=True)
        pdf.set_text_color(*_INK)
    pdf.ln(1)


def _tarjetas_resumen(pdf: FPDF, resumen: dict) -> None:
    """Los cuatro numeros que contestan "¿que pasó este mes?" sin leer nada
    mas. Mismo lenguaje visual que el recuadro de saldo del resumen de cuenta
    corriente de LibraCore."""
    datos = [
        ("Recibidas", str(resumen["recibidas"])),
        ("Resueltas", str(resumen["resueltas"])),
        ("Pendientes", str(resumen["pendientes"])),
        ("Horas", f"{resumen['horas']:.1f}".replace(".", ",")),
    ]
    gap = 4
    w = (_CW - gap * (len(datos) - 1)) / len(datos)
    h = 18
    y = pdf.get_y()

    for i, (label, valor) in enumerate(datos):
        x = _LX + i * (w + gap)
        pdf.set_fill_color(*_ACCENT_SOFT)
        _rrect(pdf, x, y, w, h, style="F")
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*_ACCENT_DARK)
        pdf.set_xy(x + 3, y + 2.5)
        pdf.cell(w - 6, 4, label.upper(), ln=False)
        pdf.set_font("Helvetica", "B", 15)
        pdf.set_text_color(*_INK)
        pdf.set_xy(x + 3, y + 8)
        pdf.cell(w - 6, 7, valor, ln=False)

    pdf.set_y(y + h + 2)

    if resumen["promedio_resolucion_horas"] is not None:
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*_MUTED)
        pdf.set_x(_LX)
        pdf.cell(
            _CW, 5,
            f"Tiempo promedio de resolución en el período: "
            f"{resumen['promedio_resolucion_horas']} horas"
            f"  ·  {resumen['actividades']} intervenciones registradas",
            ln=True,
        )
        pdf.set_text_color(*_INK)

    if resumen["por_categoria"]:
        pdf.ln(1)
        categorias = resumen["por_categoria"][:6]
        _asegurar_espacio(pdf, _alto_lista(categorias))
        pdf.set_y(_lista_conteos(
            pdf, "Por tipo de problema", categorias, _LX, _CW, pdf.get_y()))
    pdf.ln(1)


_LINEA = 4.6      # alto de una linea de texto dentro de una fila
_PAD_FILA = 2.9   # aire arriba + abajo de la fila


def _lineas_celda(pdf: FPDF, texto: str, ancho: float, maximo: int) -> list[str]:
    """El texto repartido en hasta `maximo` lineas, con elipsis si sobra."""
    lineas = _wrap_text(pdf, texto, ancho)
    if len(lineas) <= maximo:
        return lineas
    ultima = lineas[maximo - 1]
    return lineas[: maximo - 1] + [ultima[: max(0, len(ultima) - 1)] + _ELIPSIS]


def _tabla(pdf: FPDF, headers: list[str], widths: list[float], aligns: list[str],
           filas: list[list[str]], vacia: str, envuelve: tuple[int, ...] = ()) -> None:
    """Tabla con el mismo lenguaje visual que `_draw_items_table` de LibraCore,
    con repeticion de encabezado al cortar de pagina.

    `envuelve` son los indices de las columnas que pueden ocupar **dos
    lineas**; el resto se trunca con elipsis. Nace de mirar el PDF con datos
    reales: los asuntos de los tickets son frases ("El backup nocturno no corre
    hace tres dias") y los equipos vienen con marca y modelo ("Servidor Dell
    PowerEdge T140"), asi que en una sola linea salian cortados justo los dos
    datos que el cliente lee. Dos lineas alcanzan para el caso normal; el alto
    de la fila se calcula **antes** de dibujarla, asi que el corte de pagina
    sigue siendo exacto.
    """
    th_h = 7
    row_h = _LINEA + _PAD_FILA

    def encabezado():
        y = pdf.get_y()
        x = _LX
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*_MUTED)
        for h, w, a in zip(headers, widths, aligns):
            pdf.set_xy(x, y)
            pdf.cell(w, th_h, ("  " if a == "L" else "") + h, align=a, ln=False)
            x += w
        pdf.set_draw_color(*_INK)
        pdf.set_line_width(0.7)
        pdf.line(_LX, y + th_h, _RX, y + th_h)
        pdf.set_line_width(0.3)
        pdf.set_y(y + th_h + 1)
        pdf.set_text_color(*_INK)

    encabezado()

    if not filas:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*_MUTED)
        pdf.set_xy(_LX + 2, pdf.get_y() + 1.5)
        pdf.cell(_CW - 4, 5, vacia, ln=False)
        pdf.set_text_color(*_INK)
        pdf.set_y(pdf.get_y() + row_h)
        pdf.ln(2)
        return

    for fila in filas:
        pdf.set_font("Helvetica", "", 8)
        # El alto se resuelve ANTES de dibujar: si se decidiera sobre la
        # marcha, el chequeo de corte de pagina usaria un alto que todavia no
        # es el real y la ultima fila terminaria pisando el pie.
        celdas = [_latin1(str(val or "")) for val in fila]
        maximos = [2 if i in envuelve else 1 for i in range(len(celdas))]
        partidas = [
            _lineas_celda(pdf, texto, w - (2 if a == "L" else 0) - 2, maximo)
            for texto, w, a, maximo in zip(celdas, widths, aligns, maximos)
        ]
        alto = max(len(p) for p in partidas) * _LINEA + _PAD_FILA

        if pdf.get_y() + alto > pdf.h - 22:
            pdf.add_page()
            encabezado()

        y = pdf.get_y()
        x = _LX
        pdf.set_text_color(*_INK)
        for lineas, w, a in zip(partidas, widths, aligns):
            pad = 2 if a == "L" else 0
            for n, linea in enumerate(lineas):
                pdf.set_xy(x + pad, y + 1.2 + n * _LINEA)
                pdf.cell(w - pad, _LINEA, linea, align=a, ln=False)
            x += w
        pdf.set_draw_color(*_LINE)
        pdf.set_line_width(0.25)
        pdf.line(_LX, y + alto, _RX, y + alto)
        pdf.set_y(y + alto)

    pdf.ln(3)


# Alto de un renglon de `_lista_conteos`, y del encabezado de la columna. Estan
# como constantes porque `_seccion_parque` necesita **medir** el bloque antes de
# dibujarlo (ver ahi).
_FILA_CONTEO = 5.2
_CABEZAL_CONTEO = 6


def _alto_lista(pares: list) -> float:
    return _CABEZAL_CONTEO + len(pares) * _FILA_CONTEO


def _asegurar_espacio(pdf: FPDF, alto: float) -> None:
    """Salta de pagina si el bloque no entra entero en lo que queda.

    Los bloques que se dibujan con cursor propio —`_lista_conteos`— **tienen
    que** entrar completos: si el salto automatico de fpdf se dispara en el
    medio, la pagina nueva empieza arriba pero el cursor sigue abajo, y cada
    renglon siguiente vuelve a dispararlo. El resultado es una pagina por fila:
    un informe de 7 incidencias salio de **27 paginas** antes de esto.
    """
    if pdf.get_y() + alto > pdf.h - 24:
        pdf.add_page()


def _lista_conteos(pdf: FPDF, titulo: str, pares: list[tuple[str, int]],
                   x: float, w: float, y: float) -> float:
    """Columna "etiqueta ....... n". Devuelve el y final.

    **No pagina**: el que llama garantiza el espacio con `_asegurar_espacio`.
    Ver el porque ahi.
    """
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*_MUTED)
    pdf.set_xy(x, y)
    pdf.cell(w, 5, titulo.upper(), ln=False)
    y += _CABEZAL_CONTEO
    for etiqueta, n in pares:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*_INK)
        pdf.set_xy(x, y)
        texto = _latin1(str(etiqueta))
        if pdf.get_string_width(texto) > w - 12:
            texto = "".join(_wrap_text(pdf, texto, w - 14)[:1]) + _ELIPSIS
        pdf.cell(w - 10, 5, texto, ln=False)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_xy(x + w - 10, y)
        pdf.cell(10, 5, str(n), align="R", ln=False)
        y += _FILA_CONTEO
    return y


# ── Secciones ──────────────────────────────────────────────────────

def _seccion_incidencias(pdf: FPDF, informe: dict) -> None:
    incidencias = informe["incidencias"]
    _titulo_seccion(
        pdf, "Detalle de incidencias",
        "Incluye las abiertas durante el período y las resueltas en él, "
        "aunque se hubieran abierto antes.",
    )

    filas = []
    for i in incidencias:
        if i["fecha_cierre"] is not None:
            estado = f"Resuelta {_fecha(i['fecha_cierre'])}"
        elif i["cerrada"]:
            # Cerrada sin fecha: dato de la migración del sistema viejo. Se
            # informa como resuelta, sin inventarle una fecha.
            estado = "Resuelta"
        else:
            estado = "Pendiente"
        filas.append([
            f"#{i['id']}",
            _fecha(i["fecha_creacion"]),
            i["titulo"],
            i["equipo"] or _VACIO,
            estado,
            f"{i['horas']:.1f}".replace(".", ",") if i["horas"] else _VACIO,
        ])

    # Los anchos salen de medir el contenido real, no de repartir el ancho en
    # partes iguales: "Resuelta 08/01/2026" ocupa ~30 mm a 8 pt y una fecha
    # completa ~17 mm. Una columna corta no se nota al escribirla — se nota
    # como un truncado con elipsis en cada fila.
    #
    # **La categoria no tiene columna propia**, aunque el dato exista: con
    # datos reales se comia 24 mm para decir "Hardware · Impresoras" y dejaba
    # el asunto ilegible. Va como desglose arriba, donde ademas contesta algo
    # que fila por fila no se ve — de que se trataron los tickets del periodo.
    _tabla(
        pdf,
        headers=["#", "FECHA", "ASUNTO", "EQUIPO", "ESTADO", "HS."],
        widths=[11, 20, 62, 38, 32, 11],
        aligns=["L", "L", "L", "L", "L", "R"],
        filas=filas,
        vacia="Sin incidencias registradas en el período.",
        envuelve=(2, 3),
    )


def _seccion_parque(pdf: FPDF, informe: dict) -> None:
    parque = informe["parque"]
    total, bajas = parque["total"], parque["bajas"]
    aclaracion = f"{total} equipo{'s' if total != 1 else ''} bajo servicio."
    if bajas:
        aclaracion += (
            f" No se incluye{'n' if bajas != 1 else ''} {bajas} "
            f"equipo{'s' if bajas != 1 else ''} dado{'s' if bajas != 1 else ''} de baja."
        )
    por_estado = [
        (_ESTADO_EQUIPO_LABEL.get(estado, estado), n)
        for estado, n in sorted(parque["por_estado"].items(), key=lambda kv: -kv[1])
    ]
    # Las listas van recortadas: el informe muestra el reparto del parque, no
    # el inventario completo —para eso está el reporte de Equipamiento—. El
    # tope también es lo que acota el alto del bloque, y por lo tanto lo que
    # garantiza que entre en una página.
    por_tipo = parque["por_tipo"][:8]
    por_sector = parque["por_sector"][:10]

    alto = (
        10                                                  # título + aclaración
        + max(_alto_lista(por_estado), _alto_lista(por_tipo))
        + (2 + _alto_lista(por_sector) if por_sector else 0)
    )
    _asegurar_espacio(pdf, alto)
    _titulo_seccion(pdf, "Parque de equipos", aclaracion)

    y0 = pdf.get_y()
    col_w = (_CW - 10) / 2
    y1 = _lista_conteos(pdf, "Por estado", por_estado, _LX, col_w, y0)
    y2 = _lista_conteos(pdf, "Por tipo", por_tipo, _LX + col_w + 10, col_w, y0)
    pdf.set_y(max(y1, y2) + 2)

    if por_sector:
        pdf.set_y(_lista_conteos(pdf, "Por sector", por_sector, _LX, _CW, pdf.get_y()) + 2)


def _seccion_garantias(pdf: FPDF, informe: dict) -> None:
    garantias = informe["garantias"]
    _titulo_seccion(
        pdf, "Garantías",
        f"Vencidas y a vencer dentro de {informe['dias_garantia']} días "
        f"del cierre del período.",
    )
    filas = [
        [
            g["equipo"],
            g["serial"] or _VACIO,
            g["sector"] or _VACIO,
            _fecha(g["garantia_vence"]),
            (f"Vencida hace {abs(g['dias_restantes'])} d"
             if g["dias_restantes"] < 0 else f"{g['dias_restantes']} d"),
        ]
        for g in garantias
    ]
    _tabla(
        pdf,
        headers=["EQUIPO", "SERIE", "SECTOR", "VENCE", "RESTAN"],
        widths=[54, 28, 30, 22, 40],
        aligns=["L", "L", "L", "L", "R"],
        filas=filas,
        vacia="Sin garantías próximas a vencer.",
        envuelve=(0,),
    )


def _seccion_service(pdf: FPDF, informe: dict) -> None:
    service = informe["service"]
    _titulo_seccion(
        pdf, "Equipos en service",
        "Enviados a reparación externa con actividad en el período.",
    )
    filas = [
        [
            s["equipo"],
            s["serial"] or _VACIO,
            s["proveedor"],
            _fecha(s["fecha_envio"]),
            (f"En service ({s['dias_afuera']} d)" if s["abierta"]
             else f"Devuelto {_fecha(s['fecha_retorno'])}"),
        ]
        for s in service
    ]
    _tabla(
        pdf,
        headers=["EQUIPO", "SERIE", "PROVEEDOR", "ENVIADO", "ESTADO"],
        widths=[46, 26, 38, 22, 42],
        aligns=["L", "L", "L", "L", "L"],
        filas=filas,
        vacia="Ningún equipo pasó por service en el período.",
        envuelve=(0, 2),
    )


# ── Entrada publica ────────────────────────────────────────────────

def generar(informe: dict) -> bytes:
    """El PDF del informe, en memoria.

    `informe` es lo que devuelve `InformeService.cliente()`.
    """
    emp = _empresa()
    cliente = informe["cliente"]

    pdf = InformePDF(cliente, informe["periodo"])
    pdf._emp = emp
    pdf.alias_nb_pages()
    pdf.add_page()

    # La tarjeta la dibuja LibraCore, asi que el saneo va **antes** de
    # entregarle el dato: adentro de su `_draw_card` ya no lo alcanzamos.
    _draw_emisor_cliente(pdf, emp, [
        (etiqueta, _latin1(valor) if valor else valor)
        for etiqueta, valor in (
            ("Cliente", cliente["nombre"]),
            ("Contacto", cliente["contacto"]),
            ("CUIT", cliente["cuit"]),
            ("Domicilio", cliente["domicilio"]),
            ("Localidad", cliente["ciudad"]),
            ("Email", cliente["email"]),
            ("Teléfono", cliente["telefono"]),
        )
    ])

    _titulo_seccion(pdf, "Resumen del período")
    _tarjetas_resumen(pdf, informe["resumen"])

    _seccion_incidencias(pdf, informe)
    _seccion_parque(pdf, informe)
    _seccion_garantias(pdf, informe)
    _seccion_service(pdf, informe)

    _draw_no_fiscal_notice(
        pdf, "Informe de servicio · documento no válido como factura")

    return bytes(pdf.output())
