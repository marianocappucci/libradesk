"""Los reportes, en pantalla y en Excel.

Dos familias, deliberadamente distintas:

- **Reportes analiticos** (6): reconstruidos desde el backend Node.js viejo
  (`reportesXlsxController.ts`) — con filtros, resaltados por celda,
  agrupacion y filas de totales. Son los que se ofrecen en `/reportes`.
- **Volcados planos** (3): un listado por dominio, sin filtros ni formato
  analitico. Nacieron con la reescritura como export minimo y se conservan
  porque sirven para bajar la tabla cruda.

**Cada reporte tiene dos rutas y una sola definicion.** `GET /<slug>` devuelve
la vista en JSON (la pantalla) y `GET /<slug>.xlsx` la misma vista bajada a un
libro de Excel. Las dos llaman a la misma funcion `_vista_*`, asi que agregar
una columna la agrega en los dos lados o en ninguno. Hasta el 2026-08-04 solo
existia el `.xlsx` y la definicion vivia adentro de la ruta; ver el docstring
de `services/reporte_vista.py` para por que se extrajo.
"""
from fastapi import APIRouter, Depends, Query

from ..dependencies import (
    get_categoria_repository, get_cliente_repository, get_equipo_repository,
    get_incidencia_repository, get_reportes_service,
)
from ..services import reporte_vista as vistas
from ..services.categorias import CategoriaRepository
from ..services.clientes import ClienteRepository
from ..services.equipos import EquipoRepository
from ..services.incidencias import IncidenciaRepository
from ..services.reporte_vista import (
    ESTADO_LABEL, FACT_LABEL, PRIO_LABEL, Vista, fmt_fecha,
)
from ..services.reporte_xlsx import renderizar
from ..services.reportes import ReportesService
from ..services.xlsx_helper import xlsx_response

router = APIRouter(prefix="/api/reportes", tags=["reportes"])


def _label_cliente(cliente_id: int | None, clientes: ClienteRepository) -> str | None:
    if not cliente_id:
        return None
    c = clientes.get(cliente_id)
    return (c["empresa"] or c["nombre"]) if c else f"#{cliente_id}"


def _excel(vista: Vista):
    return xlsx_response(renderizar(vista), f"{vista.slug}.xlsx")


# ── Equipamiento ───────────────────────────────────────────────────

def _vista_equipamiento(cliente_id, estado, tipo, reportes, clientes) -> Vista:
    data = reportes.equipamiento(cliente_id=cliente_id, estado=estado, tipo=tipo)

    filtros = []
    if (label := _label_cliente(cliente_id, clientes)):
        filtros.append(f"Cliente: {label}")
    if estado:
        filtros.append(f"Estado: {ESTADO_LABEL.get(estado, estado)}")
    if tipo:
        filtros.append(f"Tipo: {tipo}")

    return vistas.equipamiento(data, filtros)


@router.get("/equipamiento")
def equipamiento(
    cliente_id: int | None = None,
    estado: str | None = None,
    tipo: str | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    return _vista_equipamiento(cliente_id, estado, tipo, reportes, clientes).to_dict()


@router.get("/equipamiento.xlsx")
def equipamiento_xlsx(
    cliente_id: int | None = None,
    estado: str | None = None,
    tipo: str | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    return _excel(_vista_equipamiento(cliente_id, estado, tipo, reportes, clientes))


# ── Incidencias por periodo ────────────────────────────────────────

def _vista_incidencias(desde, hasta, cliente_id, estado, prioridad, sector_id,
                       keyword, categoria_id, reportes, clientes, categorias) -> Vista:
    data = reportes.incidencias(
        desde=desde, hasta=hasta, cliente_id=cliente_id, estado=estado,
        prioridad=prioridad, sector_id=sector_id, keyword=keyword,
        categoria_id=categoria_id,
    )

    filtros = [f"Período: {fmt_fecha(desde)} – {fmt_fecha(hasta)}"]
    if (label := _label_cliente(cliente_id, clientes)):
        filtros.append(f"Cliente: {label}")
    if estado:
        filtros.append(f"Estado: {ESTADO_LABEL.get(estado, estado)}")
    if prioridad:
        filtros.append(f"Prioridad: {PRIO_LABEL.get(prioridad, prioridad)}")
    if categoria_id and (cat := categorias.get(categoria_id)):
        filtros.append(f"Categoría: {cat['ruta']}")
    if keyword:
        filtros.append(f'Búsqueda: "{keyword}"')

    return vistas.incidencias_periodo(data, filtros)


@router.get("/incidencias-periodo")
def incidencias_periodo(
    desde: str = Query(...),
    hasta: str = Query(...),
    cliente_id: int | None = None,
    estado: str | None = None,
    prioridad: str | None = None,
    sector_id: int | None = None,
    keyword: str | None = None,
    categoria_id: int | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
    categorias: CategoriaRepository = Depends(get_categoria_repository),
):
    return _vista_incidencias(
        desde, hasta, cliente_id, estado, prioridad, sector_id, keyword,
        categoria_id, reportes, clientes, categorias,
    ).to_dict()


@router.get("/incidencias-periodo.xlsx")
def incidencias_periodo_xlsx(
    desde: str = Query(...),
    hasta: str = Query(...),
    cliente_id: int | None = None,
    estado: str | None = None,
    prioridad: str | None = None,
    sector_id: int | None = None,
    keyword: str | None = None,
    categoria_id: int | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
    categorias: CategoriaRepository = Depends(get_categoria_repository),
):
    return _excel(_vista_incidencias(
        desde, hasta, cliente_id, estado, prioridad, sector_id, keyword,
        categoria_id, reportes, clientes, categorias,
    ))


# ── Facturacion ────────────────────────────────────────────────────

def _vista_facturacion(desde, hasta, cliente_id, estado_facturacion,
                       reportes, clientes) -> Vista:
    data = reportes.facturacion(
        desde=desde, hasta=hasta, cliente_id=cliente_id,
        estado_facturacion=estado_facturacion,
    )

    filtros = [f"Período: {fmt_fecha(desde)} – {fmt_fecha(hasta)}"]
    if (label := _label_cliente(cliente_id, clientes)):
        filtros.append(f"Cliente: {label}")
    if estado_facturacion:
        filtros.append(
            f"Cobro: {FACT_LABEL.get(estado_facturacion, estado_facturacion)}"
        )

    return vistas.facturacion(data, filtros)


@router.get("/facturacion")
def facturacion(
    desde: str = Query(...),
    hasta: str = Query(...),
    cliente_id: int | None = None,
    estado_facturacion: str | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    return _vista_facturacion(
        desde, hasta, cliente_id, estado_facturacion, reportes, clientes
    ).to_dict()


@router.get("/facturacion.xlsx")
def facturacion_xlsx(
    desde: str = Query(...),
    hasta: str = Query(...),
    cliente_id: int | None = None,
    estado_facturacion: str | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    return _excel(_vista_facturacion(
        desde, hasta, cliente_id, estado_facturacion, reportes, clientes
    ))


# ── Garantias ──────────────────────────────────────────────────────

def _vista_garantias(dias, cliente_id, reportes, clientes) -> Vista:
    data = reportes.garantias(dias=dias, cliente_id=cliente_id)

    filtros = [f"Próximos {dias} días"]
    if (label := _label_cliente(cliente_id, clientes)):
        filtros.append(f"Cliente: {label}")

    return vistas.garantias(data, filtros)


@router.get("/garantias")
def garantias(
    dias: int = 60,
    cliente_id: int | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    return _vista_garantias(dias, cliente_id, reportes, clientes).to_dict()


@router.get("/garantias.xlsx")
def garantias_xlsx(
    dias: int = 60,
    cliente_id: int | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    return _excel(_vista_garantias(dias, cliente_id, reportes, clientes))


# ── Por tecnico ────────────────────────────────────────────────────

def _vista_tecnico(desde, hasta, reportes) -> Vista:
    data = reportes.por_tecnico(desde=desde, hasta=hasta)
    filtros = [f"Período: {fmt_fecha(desde)} – {fmt_fecha(hasta)}"]
    return vistas.por_tecnico(data, filtros)


@router.get("/tecnico")
def tecnico(
    desde: str = Query(...),
    hasta: str = Query(...),
    reportes: ReportesService = Depends(get_reportes_service),
):
    return _vista_tecnico(desde, hasta, reportes).to_dict()


@router.get("/tecnico.xlsx")
def tecnico_xlsx(
    desde: str = Query(...),
    hasta: str = Query(...),
    reportes: ReportesService = Depends(get_reportes_service),
):
    return _excel(_vista_tecnico(desde, hasta, reportes))


# ── Movimientos ────────────────────────────────────────────────────

def _vista_movimientos(desde, hasta, cliente_id, reportes, clientes) -> Vista:
    data = reportes.movimientos(desde=desde, hasta=hasta, cliente_id=cliente_id)

    filtros = [f"Período: {fmt_fecha(desde)} – {fmt_fecha(hasta)}"]
    if (label := _label_cliente(cliente_id, clientes)):
        filtros.append(f"Cliente: {label}")

    return vistas.movimientos(data, filtros)


@router.get("/movimientos")
def movimientos(
    desde: str = Query(...),
    hasta: str = Query(...),
    cliente_id: int | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    return _vista_movimientos(desde, hasta, cliente_id, reportes, clientes).to_dict()


@router.get("/movimientos.xlsx")
def movimientos_xlsx(
    desde: str = Query(...),
    hasta: str = Query(...),
    cliente_id: int | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    return _excel(_vista_movimientos(desde, hasta, cliente_id, reportes, clientes))


# ── Volcados planos ────────────────────────────────────────────────

def _vista_clientes(clientes: ClienteRepository) -> Vista:
    data = clientes.list()
    return vistas.volcado(
        "clientes", "Clientes",
        [("ID", 6), ("Nombre", 28), ("Empresa", 24), ("Email", 26),
         ("Teléfono", 16), ("Ciudad", 16), ("Estado", 12)],
        [
            [c["id"], c["nombre"], c["empresa"], c["email"], c["telefono"],
             c["ciudad"], "Activo" if c["activo"] else "Inactivo"]
            for c in data
        ],
        [f"Total: {len(data)}"],
    )


def _vista_equipos(equipos: EquipoRepository) -> Vista:
    data = equipos.list()
    return vistas.volcado(
        "equipos", "Equipos",
        [("ID", 6), ("Cliente", 10), ("Tipo", 18), ("Marca", 18),
         ("Modelo", 20), ("Serial", 20), ("Depósito", 20), ("Estado", 12)],
        [
            [e["id"], e["cliente_id"], e["tipo"], e["marca"], e["modelo"],
             e["serial"], e["deposito_nombre"], e["estado"]]
            for e in data
        ],
        [f"Total: {len(data)}"],
    )


def _vista_incidencias_planas(estado, incidencias: IncidenciaRepository) -> Vista:
    data = incidencias.list(estado=estado)
    filtros = [f"Total: {len(data)}"] + ([f"Estado: {estado}"] if estado else [])
    return vistas.volcado(
        "incidencias", "Incidencias",
        [("ID", 6), ("Cliente", 10), ("Título", 32), ("Estado", 14),
         ("Prioridad", 12), ("Horas", 10), ("Fecha", 18)],
        [
            [i["id"], i["cliente_id"], i["titulo"], i["estado"], i["prioridad"],
             i["horas_invertidas"], i["fecha_creacion"]]
            for i in data
        ],
        filtros,
    )


@router.get("/clientes")
def export_clientes_pantalla(clientes: ClienteRepository = Depends(get_cliente_repository)):
    return _vista_clientes(clientes).to_dict()


@router.get("/clientes.xlsx")
def export_clientes(clientes: ClienteRepository = Depends(get_cliente_repository)):
    return _excel(_vista_clientes(clientes))


@router.get("/equipos")
def export_equipos_pantalla(equipos: EquipoRepository = Depends(get_equipo_repository)):
    return _vista_equipos(equipos).to_dict()


@router.get("/equipos.xlsx")
def export_equipos(equipos: EquipoRepository = Depends(get_equipo_repository)):
    return _excel(_vista_equipos(equipos))


@router.get("/incidencias")
def export_incidencias_pantalla(
    estado: str | None = None,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
):
    return _vista_incidencias_planas(estado, incidencias).to_dict()


@router.get("/incidencias.xlsx")
def export_incidencias(
    estado: str | None = None,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
):
    return _excel(_vista_incidencias_planas(estado, incidencias))


# ── Insumos por equipo (fase 2) ────────────────────────────────────

def _vista_insumos(desde, hasta, cliente_id, proveedor_id, estado,
                   reportes, clientes) -> Vista:
    data = reportes.insumos(
        desde=desde, hasta=hasta, cliente_id=cliente_id,
        proveedor_id=proveedor_id, estado=estado,
    )

    filtros = [f"{fmt_fecha(desde)} a {fmt_fecha(hasta)}"]
    if (label := _label_cliente(cliente_id, clientes)):
        filtros.append(f"Cliente: {label}")
    if proveedor_id:
        # Por el nombre que ya viene resuelto en las filas: pedirlo de nuevo al
        # repositorio de proveedores sería una consulta más para un texto que ya
        # está en la mano. Sin filas no hay nombre, y el filtro dice el id — que
        # es más honesto que omitirlo.
        nombre = next(
            (f["proveedor_nombre"] for f in data if f["proveedor_nombre"]), None
        )
        filtros.append(f"Proveedor: {nombre or f'#{proveedor_id}'}")
    if estado:
        filtros.append(f"Estado: {vistas.INSUMO_LABEL.get(estado, estado)}")

    return vistas.insumos(data, filtros)


@router.get("/insumos")
def insumos(
    desde: str,
    hasta: str,
    cliente_id: int | None = None,
    proveedor_id: int | None = None,
    estado: str | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    return _vista_insumos(
        desde, hasta, cliente_id, proveedor_id, estado, reportes, clientes
    ).to_dict()


@router.get("/insumos.xlsx")
def insumos_xlsx(
    desde: str,
    hasta: str,
    cliente_id: int | None = None,
    proveedor_id: int | None = None,
    estado: str | None = None,
    reportes: ReportesService = Depends(get_reportes_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    return _excel(_vista_insumos(
        desde, hasta, cliente_id, proveedor_id, estado, reportes, clientes
    ))
