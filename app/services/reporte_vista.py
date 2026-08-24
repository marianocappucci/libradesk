"""Los seis reportes analiticos **como datos**: titulo, filtros aplicados,
columnas, filas y totales, sin decidir en que se van a dibujar.

**Por que existe.** Hasta el 2026-08-04 cada reporte se definia adentro de su
ruta `.xlsx`: ahi vivian los encabezados, el orden de las columnas, el formato
de cada celda, los resaltados, la agrupacion y la fila de totales. Cuando se
pidio verlos tambien en pantalla habia dos caminos: escribir esas mismas
definiciones otra vez en TypeScript, o extraerlas una sola vez. Duplicarlas
significa que agregar una columna al Excel y olvidarse de la pantalla —o al
reves— produce dos reportes con el mismo nombre y distinto contenido, y nadie
se entera hasta que alguien compara. Asi que se extrajeron: aca se define el
reporte, y `routers/reportes.py` lo baja a xlsx mientras el frontend lo baja a
una tabla HTML.

**Los resaltados son semanticos, no colores.** Una celda no dice "pintame de
FFFEE2E2" sino `marca="peligro"`; cada renderizador la traduce a lo suyo (un
`PatternFill` en el Excel, una clase de Tailwind en pantalla). Las ocho marcas
son exactamente los ocho colores que ya usaba el helper de Excel —portados a su
vez del backend Node.js viejo—, asi que los archivos que se bajan siguen
saliendo identicos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# ── Vocabulario compartido ─────────────────────────────────────────
#
# Vive aca y no en `xlsx_helper` (donde estaba) porque ya no es del Excel: lo
# usan las dos salidas. `xlsx_helper` quedo con lo que si es suyo, que son los
# helpers de openpyxl.

ESTADO_LABEL = {
    "activo": "Activo", "baja": "Baja", "en_reparacion": "En reparación",
    "almacenado": "En depósito",
    "abierto": "Abierto", "en_progreso": "En progreso",
    "resuelta": "Resuelta", "cerrado": "Cerrado",
}
PRIO_LABEL = {"alta": "Alta", "media": "Media", "baja": "Baja"}
FACT_LABEL = {"pendiente_cobro": "Pend. cobro", "facturada": "Facturada"}

# Cómo se cobra un reclamo de un cliente **con abono**, según qué parte cubre
# (revisión `0024`). Antes la columna decía "Mensual" para todos, y desde que el
# abono es un espectro eso es informar lo contrario de lo que pasa en la mitad
# de los casos. `None` —sin decidir— conserva la etiqueta vieja: no se sabe
# todavía, y es el estado que el remito frena.
COBERTURA_COBRO = {
    None: ("Mensual", "info"),
    "total": ("Cubierto", "info"),
    "parcial": ("Parcial", "urgente"),
    "fuera": ("Se factura", "urgente"),
}
MOV_LABEL = {
    "alta": "Alta", "baja": "Baja", "traslado": "Traslado",
    "en_reparacion": "Reparación", "almacenado": "Almacenado",
    "activo": "Reactivado",
}

# marca -> ARGB del Excel. Los ocho colores que ya se usaban, sin cambiar
# ninguno: el archivo que se baja tiene que seguir viendose igual.
MARCA_ARGB = {
    "ok": "FFD1FAE5",        # verde: activo, resuelta, facturada
    "peligro": "FFFEE2E2",   # rojo: vencida, prioridad alta, baja
    "atencion": "FFFED7AA",  # naranja: en reparación, en progreso
    "carga": "FFFFEDD5",     # naranja suave: tiene incidencias acumuladas
    "urgente": "FFFEF9C3",   # amarillo: por vencer, pendiente de cobro
    "info": "FFEDE9FE",      # violeta: abono mensual, guardado
    "nuevo": "FFDBEAFE",     # celeste: abierto
    "neutro": "FFF3F4F6",    # gris: cerrado, sin facturar
}

ESTADO_MARCA = {
    "activo": "ok", "baja": "peligro", "en_reparacion": "atencion",
    "almacenado": "info",
    "abierto": "nuevo", "en_progreso": "atencion",
    "resuelta": "ok", "cerrado": "neutro",
}
PRIO_MARCA = {"alta": "peligro", "media": "urgente", "baja": "ok"}
FACT_MARCA = {"pendiente_cobro": "urgente", "facturada": "ok", "sin_facturar": "neutro"}


def fmt_fecha(value) -> str:
    """dd-mm-aa, o '—' si no hay valor. Acepta datetime, date o el ISO string
    que devuelven los repositories. Es el mismo formato en las dos salidas: si
    la pantalla formateara por su cuenta, imprimir y bajar el Excel darian dos
    fechas distintas para la misma fila."""
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if hasattr(value, "strftime"):
        return value.strftime("%d-%m-%y")
    return str(value)


# ── La vista ───────────────────────────────────────────────────────

@dataclass
class Columna:
    label: str
    # Ancho en el Excel. En pantalla la tabla se acomoda sola, pero el orden
    # relativo de los anchos igual sirve de pista de cuanto ocupa cada una.
    ancho: int = 14
    # Alinea a la derecha y evita que la busqueda de la tabla la trate como
    # texto: conteos, dias, horas.
    numerica: bool = False


@dataclass
class Celda:
    texto: str | None = None
    marca: str | None = None
    # El valor crudo cuando es un numero. **No es redundante con `texto`**: si
    # el Excel recibiera el string, la columna "#" y los conteos dejarian de
    # ser numeros para la planilla —no se suman, no se ordenan— y eso es
    # exactamente para lo que se baja el archivo. La pantalla usa `texto`.
    numero: int | float | None = None


@dataclass
class Grupo:
    """Un bloque de filas con su encabezado. `etiqueta=None` es la tabla plana
    —que es el caso de cinco de los seis reportes—, y asi el renderizador
    recorre siempre la misma estructura en vez de tener dos caminos."""
    etiqueta: str | None
    filas: list[list[Celda]] = field(default_factory=list)


@dataclass
class Vista:
    slug: str
    titulo: str
    filtros: list[str]
    columnas: list[Columna]
    grupos: list[Grupo]
    totales: list[Celda] | None = None
    generado: str = ""

    def __post_init__(self):
        if not self.generado:
            self.generado = datetime.now().isoformat(timespec="seconds")

    @property
    def cantidad_filas(self) -> int:
        return sum(len(g.filas) for g in self.grupos)

    def to_dict(self) -> dict:
        """Lo que viaja al frontend. Plano a proposito: la pantalla dibuja lo
        que le llega y no vuelve a decidir nada."""
        return {
            "slug": self.slug,
            "titulo": self.titulo,
            "filtros": self.filtros,
            "generado": self.generado,
            "cantidad_filas": self.cantidad_filas,
            "columnas": [
                {"label": c.label, "numerica": c.numerica} for c in self.columnas
            ],
            "grupos": [
                {
                    "etiqueta": g.etiqueta,
                    "filas": [
                        [{"texto": c.texto, "marca": c.marca} for c in fila]
                        for fila in g.filas
                    ],
                }
                for g in self.grupos
            ],
            "totales": (
                [{"texto": c.texto, "marca": c.marca} for c in self.totales]
                if self.totales else None
            ),
        }


def _fila(valores: list, marcas: list[str | None] | None = None) -> list[Celda]:
    """Arma la fila desde dos listas paralelas, que es como se leen los seis
    reportes: los valores en un bloque y los resaltados enfrente."""
    return [
        Celda(
            texto=None if v is None or v == "" else str(v),
            marca=marcas[i] if marcas and i < len(marcas) else None,
            numero=v if isinstance(v, (int, float)) and not isinstance(v, bool) else None,
        )
        for i, v in enumerate(valores)
    ]


def _plano(filas: list[list[Celda]]) -> list[Grupo]:
    return [Grupo(etiqueta=None, filas=filas)]


# ── Los seis reportes ──────────────────────────────────────────────

def equipamiento(data: list[dict], filtros: list[str]) -> Vista:
    columnas = [
        Columna("Cliente", 28), Columna("Tipo", 14), Columna("Marca", 14),
        Columna("Modelo", 18), Columna("Serial", 15),
        # Antes decia solo "Sector". Desde que los depositos son una entidad, un
        # equipo guardado no esta en ningun sector del cliente y la columna
        # mostraba el sector del que habia salido hace meses.
        Columna("Sector / Depósito", 20),
        Columna("Ubicación", 16), Columna("Estado", 14),
        Columna("Garantía vence", 14), Columna("Inc.", 6, numerica=True),
        Columna("Alta", 12),
    ]

    ahora = datetime.now()
    filas = []
    for r in data:
        vence = r["garantia_vence"]
        vencida = bool(vence) and (
            (vence if isinstance(vence, datetime) else datetime.combine(vence, datetime.min.time()))
            < ahora
        )
        filas.append(_fila([
            r["cliente"], r["tipo"], r["marca"], r["modelo"], r["serial"],
            r["lugar"], r["ubicacion_oficina"],
            ESTADO_LABEL.get(r["estado"], r["estado"]),
            fmt_fecha(vence),
            r["incidencias_count"] or None,
            fmt_fecha(r["fecha_adicion"]),
        ], [
            None, None, None, None, None, None, None,
            ESTADO_MARCA.get(r["estado"]),
            "peligro" if vencida else None,
            "carga" if r["incidencias_count"] else None,
            None,
        ]))

    return Vista("equipamiento", "Equipamiento", filtros, columnas, _plano(filas))


def incidencias_periodo(data: list[dict], filtros: list[str]) -> Vista:
    # Sin columna "Tar.": la tabla incidencia_tareas ya no existe.
    columnas = [
        Columna("#", 6, numerica=True), Columna("Cliente", 24), Columna("Sector", 18),
        Columna("Categoría", 24), Columna("Título", 30), Columna("Descripción", 38),
        Columna("Estado", 14), Columna("Prioridad", 11), Columna("Técnico", 20),
        Columna("Creación", 12), Columna("Cierre", 12),
        Columna("Act.", 6, numerica=True), Columna("Hs.", 6, numerica=True),
        Columna("Cobro", 16),
    ]

    filas = []
    for r in data:
        if r["tipo_facturacion"] == "mensual":
            cobro_text, cobro_marca = COBERTURA_COBRO.get(
                r.get("cobertura_abono"), ("Mensual", "info"),
            )
        elif r["estado_facturacion"]:
            cobro_text = FACT_LABEL.get(r["estado_facturacion"], r["estado_facturacion"])
            cobro_marca = FACT_MARCA.get(r["estado_facturacion"])
        elif r["estado"] in ("cerrado", "resuelta"):
            cobro_text, cobro_marca = "Sin facturar", "neutro"
        else:
            cobro_text, cobro_marca = None, None

        filas.append(_fila([
            r["id"], r["cliente"], r["sector"], r["categoria"],
            r["titulo"], r["descripcion"],
            ESTADO_LABEL.get(r["estado"], r["estado"]),
            PRIO_LABEL.get(r["prioridad"], r["prioridad"]),
            r["tecnico"],
            fmt_fecha(r["fecha_creacion"]), fmt_fecha(r["fecha_cierre"]),
            r["actividades_count"] or None,
            f"{r['horas_resolucion']}h" if r["horas_resolucion"] is not None else None,
            cobro_text,
        ], [
            None, None, None, None, None, None,
            ESTADO_MARCA.get(r["estado"]),
            PRIO_MARCA.get(r["prioridad"]),
            None, None, None, None, None,
            cobro_marca,
        ]))

    total_act = sum(r["actividades_count"] for r in data)
    con_horas = [r["horas_resolucion"] for r in data if r["horas_resolucion"] is not None]
    prom = f"{round(sum(con_horas) / len(con_horas))}h prom" if con_horas else None
    totales = _fila([
        None, None, None, None, None, None, None, None, None,
        f"{len(data)} incidencias", None, total_act, prom, None,
    ])

    return Vista(
        "incidencias-periodo", "Incidencias", filtros, columnas, _plano(filas),
        totales=totales,
    )


def facturacion(data: list[dict], filtros: list[str]) -> Vista:
    columnas = [
        Columna("#", 6, numerica=True), Columna("Cliente", 28), Columna("Título", 42),
        Columna("Técnico", 20), Columna("Cierre", 12), Columna("Estado cobro", 18),
    ]

    por_cliente: dict[int, list[dict]] = {}
    for r in data:
        por_cliente.setdefault(r["cliente_id"], []).append(r)

    grupos = []
    for filas_cliente in por_cliente.values():
        cantidad = len(filas_cliente)
        etiqueta = (
            f"{filas_cliente[0]['cliente']} — {cantidad} "
            f"incidencia{'s' if cantidad != 1 else ''}"
        )
        filas = []
        for r in filas_cliente:
            if r["estado_facturacion"]:
                texto = FACT_LABEL.get(r["estado_facturacion"], r["estado_facturacion"])
                marca = FACT_MARCA.get(r["estado_facturacion"], "neutro")
            else:
                texto, marca = "Sin facturar", "neutro"
            filas.append(_fila([
                r["id"], r["cliente"], r["titulo"], r["tecnico"],
                fmt_fecha(r["fecha_cierre"]), texto,
            ], [None, None, None, None, None, marca]))
        grupos.append(Grupo(etiqueta=etiqueta, filas=filas))

    sin_fact = sum(1 for r in data if not r["estado_facturacion"])
    pend = sum(1 for r in data if r["estado_facturacion"] == "pendiente_cobro")
    facturadas = sum(1 for r in data if r["estado_facturacion"] == "facturada")
    totales = _fila([
        None, None,
        f"Total: {len(data)}  |  Sin facturar: {sin_fact}  |  "
        f"Pend. cobro: {pend}  |  Facturadas: {facturadas}",
        None, None, None,
    ])

    return Vista("facturacion", "Facturación", filtros, columnas, grupos, totales=totales)


def garantias(data: list[dict], filtros: list[str]) -> Vista:
    columnas = [
        Columna("Cliente", 28), Columna("Tipo", 14), Columna("Marca", 14),
        Columna("Modelo", 18), Columna("Serial", 15),
        Columna("Sector / Depósito", 20), Columna("Estado", 14),
        Columna("Garantía vence", 14), Columna("Días restantes", 13, numerica=True),
    ]

    filas = []
    for r in data:
        restantes = r["dias_restantes"]
        vencida = restantes < 0
        urgente = 0 <= restantes <= 14
        texto = f"Vencida hace {abs(restantes)}d" if vencida else f"{restantes}d"
        marca = "peligro" if vencida else ("urgente" if urgente else None)
        filas.append(_fila([
            r["cliente"], r["tipo"], r["marca"], r["modelo"], r["serial"],
            r["lugar"], ESTADO_LABEL.get(r["estado"], r["estado"]),
            fmt_fecha(r["garantia_vence"]), texto,
        ], [
            None, None, None, None, None, None,
            ESTADO_MARCA.get(r["estado"]), marca, marca,
        ]))

    return Vista("garantias", "Garantías", filtros, columnas, _plano(filas))


def por_tecnico(data: list[dict], filtros: list[str]) -> Vista:
    columnas = [
        Columna("Técnico", 28), Columna("Total", 9, numerica=True),
        Columna("Abiertas", 10, numerica=True), Columna("En progreso", 13, numerica=True),
        Columna("Cerradas", 10, numerica=True), Columna("% Resolución", 14, numerica=True),
        Columna("Actividades", 13, numerica=True), Columna("Prom. horas", 13, numerica=True),
    ]

    filas = []
    for r in data:
        pct = f"{round(r['cerradas'] / r['total'] * 100)}%" if r["total"] else "0%"
        filas.append(_fila([
            r["tecnico"], r["total"], r["abiertas"] or None,
            r["en_progreso"] or None, r["cerradas"] or None, pct,
            r["total_actividades"] or None,
            f"{r['promedio_horas_resolucion']}h"
            if r["promedio_horas_resolucion"] is not None else None,
        ]))

    total = sum(r["total"] for r in data)
    cerradas = sum(r["cerradas"] for r in data)
    totales = _fila([
        "TOTAL", total,
        sum(r["abiertas"] for r in data), sum(r["en_progreso"] for r in data),
        cerradas,
        f"{round(cerradas / total * 100)}%" if total else "0%",
        sum(r["total_actividades"] for r in data), None,
    ])

    return Vista("tecnico", "Por técnico", filtros, columnas, _plano(filas), totales=totales)


def movimientos(data: list[dict], filtros: list[str]) -> Vista:
    columnas = [
        Columna("Fecha", 12), Columna("Cliente", 26), Columna("Equipo", 28),
        Columna("Tipo", 12),
        # Origen y destino ya vienen resueltos: un traslado a un deposito guarda
        # el nombre del deposito en el mismo campo de texto que un traslado a un
        # sector. Ver `services/depositos.py`.
        Columna("Origen", 24), Columna("Destino", 24), Columna("Motivo", 28),
    ]

    filas = []
    for r in data:
        origen = " · ".join(x for x in (r["sector_origen"], r["ubicacion_origen"]) if x) or None
        destino = " · ".join(x for x in (r["sector_destino"], r["ubicacion_destino"]) if x) or None
        filas.append(_fila([
            fmt_fecha(r["fecha"]), r["cliente"], r["equipo"],
            MOV_LABEL.get(r["tipo"], r["tipo"]),
            origen, destino, r["motivo"],
        ]))

    return Vista(
        "movimientos", "Movimientos de equipos", filtros, columnas, _plano(filas),
    )


def volcado(slug: str, titulo: str, headers: list[tuple[str, int]],
            filas: list[list], filtros: list[str]) -> Vista:
    """Los tres listados planos (clientes, equipos, incidencias): la tabla
    cruda, sin resaltados ni totales."""
    columnas = [Columna(label, ancho) for label, ancho in headers]
    return Vista(slug, titulo, filtros, columnas, _plano([_fila(f) for f in filas]))


# ── Insumos (fase 2) ───────────────────────────────────────────────

#: Los tres estados de un insumo, con su resaltado. Lo pendiente es lo unico
#: que pide una accion de nuestro lado, y por eso es lo unico que se pinta
#: fuerte: si los tres estados llevaran color, el reclamo se pierde entre el
#: historial. Mismo criterio que el resto de los reportes.
INSUMO_LABEL = {
    "pendiente": "Pedido", "en_poder": "En el cliente", "colocado": "Colocado",
}
INSUMO_MARCA = {"pendiente": "urgente", "en_poder": "nuevo", "colocado": "ok"}

#: A partir de cuantos dias esperando un pedido deja de ser "esperá" y pasa a
#: ser un llamado. Es el mismo umbral que resalta la pantalla de Insumos.
DIAS_RECLAMO = 7


def insumos(data: list[dict], filtros: list[str]) -> Vista:
    """Lo que consumio cada maquina, agrupado POR EQUIPO.

    Agrupado por equipo y no plano porque las dos preguntas que trae a alguien a
    este reporte son de una maquina: *"cuanto me dura un toner en esta"* y
    *"cuantos le pedi para esta"*. Con las filas mezcladas, la cadena de
    contadores de una impresora queda partida entre las de las otras y el numero
    de rendimiento, que es el que justifica pedir el contador, no se puede leer.
    """
    columnas = [
        Columna("Insumo", 26), Columna("Estado", 14), Columna("Pedido", 11),
        Columna("Entregado", 11), Columna("Demora", 9, numerica=True),
        Columna("Colocado", 11), Columna("Contador", 12, numerica=True),
        Columna("Rindió el anterior", 16, numerica=True),
        Columna("Remito", 14), Columna("Contrato", 16),
    ]

    por_equipo: dict[int, list[dict]] = {}
    for r in data:
        por_equipo.setdefault(r["equipo_id"], []).append(r)

    grupos = []
    for filas_equipo in por_equipo.values():
        primera = filas_equipo[0]
        # El numero del proveedor en el encabezado: es con lo que se pide, asi
        # que tenerlo arriba del bloque evita ir a buscarlo a otra pantalla
        # mientras se hace el reclamo.
        partes = [primera["equipo_descripcion"] or f"Equipo #{primera['equipo_id']}"]
        if primera.get("referencia"):
            partes.append(f"N° {primera['referencia']}")
        if primera.get("sector"):
            partes.append(primera["sector"])
        partes.append(primera.get("cliente") or "—")
        etiqueta = " · ".join(partes)

        filas = []
        for r in filas_equipo:
            # La columna mide dos cosas segun el estado, y las dos son demora:
            # lo entregado muestra **cuanto tardo** (entrega − pedido) y lo
            # pendiente **cuanto lleva esperando** (hoy − pedido). Con una sola
            # de las dos, un proveedor que entrega todo en veinte dias saldria
            # con la columna vacia por el solo hecho de haber entregado.
            demora = r["dias_esperando"]
            if demora is None:
                demora = r.get("dias_de_entrega")
            demorado = demora is not None and demora > DIAS_RECLAMO
            # Sin contrato y sin cobertura son cosas distintas: "—" es que no
            # hay contrato cargado; "no cubre" es que lo hay y el insumo se paga
            # igual, que es el caso que hace falta ver antes de discutir una
            # factura.
            if r["contrato_numero"] is None:
                contrato, marca_contrato = "—", None
            elif r["cubierto_por_contrato"]:
                contrato, marca_contrato = r["contrato_numero"], "ok"
            else:
                contrato = f"{r['contrato_numero']} (no cubre)"
                marca_contrato = "atencion"

            filas.append(_fila([
                r["insumo_nombre"],
                INSUMO_LABEL.get(r["estado"], r["estado"]),
                fmt_fecha(r["fecha_pedido"]), fmt_fecha(r["fecha_entrega"]),
                f"{demora} d" if demora is not None else None,
                fmt_fecha(r["fecha_colocacion"]),
                r["contador_copias"], r["copias_desde_el_anterior"],
                r["remito_proveedor"], contrato,
            ], [
                None, INSUMO_MARCA.get(r["estado"]), None, None,
                "peligro" if demorado else None,
                None, None, None, None, marca_contrato,
            ]))
        grupos.append(Grupo(etiqueta=etiqueta, filas=filas))

    pendientes = [r for r in data if r["estado"] == "pendiente"]
    entregas = [
        r["dias_de_entrega"] for r in data if r.get("dias_de_entrega") is not None
    ]
    rendimientos = [
        r["copias_desde_el_anterior"] for r in data
        if r["copias_desde_el_anterior"] is not None
    ]
    # 🔑 El promedio de la columna es el de **lo entregado**, no el de lo que
    # falta: es el numero con el que se discute el cumplimiento del contrato.
    # Lo pendiente ya esta contado al lado, que es la otra mitad del reclamo.
    #
    # Los dos promedios salen vacios cuando no hay de que promediar, en vez de
    # cero: un cero se lee como una medicion.
    totales = _fila([
        f"Total: {len(data)}",
        f"Pendientes: {len(pendientes)}",
        None, None,
        f"{round(sum(entregas) / len(entregas))} d prom." if entregas else None,
        None, None,
        round(sum(rendimientos) / len(rendimientos)) if rendimientos else None,
        None, None,
    ])

    return Vista("insumos", "Insumos por equipo", filtros, columnas, grupos,
                 totales=totales)
