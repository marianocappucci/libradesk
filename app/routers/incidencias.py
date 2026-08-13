from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..auth import get_current_user
from ..dependencies import (
    get_firma_repository,
    get_equipo_repository, get_incidencia_repository, get_reemplazo_service,
)
from ..services import incidencia_pdf
from ..services.equipos import EquipoRepository
from ..services.firma import FirmaRepository
from ..services.incidencias import IncidenciaRepository
from ..services.reemplazo import (
    DESTINOS, CierreService, DatosService, ReemplazoService,
)

router = APIRouter(prefix="/api/incidencias", tags=["incidencias"])


class IncidenciaIn(BaseModel):
    cliente_id: int
    equipo_id: int | None = None
    # El activo alquilado afectado, si el problema es de un equipo NUESTRO
    # puesto en el cliente. No excluye a `equipo_id`: un ticket puede tocar
    # legítimamente las dos cosas.
    activo_id: int | None = None
    # Los tres papeles alrededor del ticket: quien lo **ejecuta**, quien lo
    # **recepciona** y quien **vende**. Los tres apuntan al mismo catálogo de
    # personal (`/api/tecnicos`), filtrable por rol.
    tecnico_id: int | None = None
    recepcionista_id: int | None = None
    vendedor_id: int | None = None
    # `on_site` | `remoto`. Nullable a propósito: los tickets anteriores al
    # 2026-08-04 no saben cómo se atendieron.
    modalidad: str | None = None
    # La agenda (pedido 42, fase B). Los tres nullable: agendar es
    # opcional. El vehículo no viaja acá — sale del equipo asignado.
    fecha_programada: datetime | None = None
    duracion_minutos: int | None = None
    equipo_trabajo_id: int | None = None
    sector_id: int | None = None
    # Hoja del catalogo de categorias ("Hardware -> Impresoras"), 2026-08-02.
    # Opcional a proposito: las 23 incidencias reales son previas al catalogo.
    categoria_id: int | None = None
    titulo: str
    descripcion: str | None = None
    #: El numero del talonario de Comprobante de Servicios (`0001-00041996`).
    #: Opcional: un reclamo resuelto en remoto no tiene papel que numerar.
    nro_cds: str | None = None
    #: Quien llamo, cuando no es el contacto habitual del cliente.
    reclamante: str | None = None
    estado: str = "abierto"
    prioridad: str = "media"
    horas_invertidas: float | None = None
    notas: str | None = None
    resolucion: str | None = None
    estado_facturacion: str | None = None
    activo: bool = True


class IncidenciaOut(IncidenciaIn):
    id: int
    fecha_creacion: str | None = None
    fecha_cierre: str | None = None


class ActividadIn(BaseModel):
    descripcion: str


class ActividadOut(BaseModel):
    id: int
    incidencia_id: int
    fecha: str | None
    descripcion: str | None
    usuario: str | None


class EstadoLogOut(BaseModel):
    id: int
    incidencia_id: int
    estado_anterior: str | None
    estado_nuevo: str
    fecha: str | None
    tecnico: str | None


@router.post("", status_code=201, response_model=IncidenciaOut)
def create_incidencia(
    data: IncidenciaIn,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
    user: dict = Depends(get_current_user),
):
    try:
        return incidencias.create(usuario_actor=user["username"], **data.model_dump())
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("", response_model=list[IncidenciaOut])
def list_incidencias(
    cliente_id: int | None = None, estado: str | None = None,
    equipo_id: int | None = None, categoria_id: int | None = None,
    activo_id: int | None = None,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
):
    return incidencias.list(
        cliente_id=cliente_id, estado=estado, equipo_id=equipo_id,
        categoria_id=categoria_id, activo_id=activo_id,
    )


@router.get("/{incidencia_id}", response_model=IncidenciaOut)
def get_incidencia(incidencia_id: int, incidencias: IncidenciaRepository = Depends(get_incidencia_repository)):
    incidencia = incidencias.get(incidencia_id)
    if incidencia is None:
        raise HTTPException(404, "incidencia not found")
    return incidencia


@router.get("/{incidencia_id}/pdf")
def incidencia_pdf_endpoint(
    incidencia_id: int,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
):
    """La orden de trabajo del ticket, para imprimir (pedido 39).

    `inline` y no `attachment`: lo normal es mirarla y mandarla a la impresora,
    no bajarla. El nombre del archivo igual va, para cuando sí se la guarda.
    """
    datos = incidencias.datos_para_pdf(incidencia_id)
    if datos is None:
        raise HTTPException(404, "incidencia not found")
    return Response(
        content=incidencia_pdf.generar_pdf_incidencia(datos),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="incidencia-{incidencia_id}.pdf"',
        },
    )


@router.put("/{incidencia_id}", response_model=IncidenciaOut)
def update_incidencia(
    incidencia_id: int, data: IncidenciaIn,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
    user: dict = Depends(get_current_user),
):
    try:
        return incidencias.update(incidencia_id, usuario_actor=user["username"], **data.model_dump())
    except KeyError:
        raise HTTPException(404, "incidencia not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/{incidencia_id}", status_code=204)
def delete_incidencia(incidencia_id: int, incidencias: IncidenciaRepository = Depends(get_incidencia_repository)):
    try:
        incidencias.delete(incidencia_id)
    except KeyError:
        raise HTTPException(404, "incidencia not found")
    from fastapi import Response
    return Response(status_code=204)


@router.get("/{incidencia_id}/actividades", response_model=list[ActividadOut])
def list_actividades(incidencia_id: int, incidencias: IncidenciaRepository = Depends(get_incidencia_repository)):
    return incidencias.list_actividades(incidencia_id)


@router.post("/{incidencia_id}/actividades", status_code=201, response_model=ActividadOut)
def add_actividad(
    incidencia_id: int, data: ActividadIn,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
    user: dict = Depends(get_current_user),
):
    return incidencias.add_actividad(incidencia_id, data.descripcion, user["username"])


@router.get("/{incidencia_id}/estados", response_model=list[EstadoLogOut])
def list_estados(incidencia_id: int, incidencias: IncidenciaRepository = Depends(get_incidencia_repository)):
    return incidencias.list_estado_log(incidencia_id)


@router.get("/{incidencia_id}/movimientos")
def list_movimientos_de_la_incidencia(
    incidencia_id: int,
    equipos: EquipoRepository = Depends(get_equipo_repository),
):
    """Los movimientos de equipo que causo este ticket — de todos los
    equipos que toco. Es la tercera fuente del timeline, junto con las
    actividades y la auditoria de estado."""
    return equipos.list_movimientos_por_incidencia(incidencia_id)


class ServiceIn(BaseModel):
    """Datos del envio a reparar. Solo con `destino="service"`."""
    proveedor_id: int
    fecha_envio: date
    remito_salida: str | None = None
    rma: str | None = None
    en_garantia: bool = False
    observaciones: str | None = None


class CierreServiceIn(BaseModel):
    """La vuelta: cierra la reparacion abierta del equipo **sustituto**, que es
    el que entra. Ver `CierreService` en services/reemplazo.py."""
    fecha_retorno: date
    diagnostico: str | None = None
    costo: float | None = None


class ReemplazoIn(BaseModel):
    equipo_retirado_id: int
    equipo_sustituto_id: int | None = None
    destino: str = "service"
    motivo: str | None = None
    # Si no vienen, el destino define el sector (Service/Depósito/Baja) y
    # la ubicacion queda vacia — ver `DESTINOS` en services/reemplazo.py.
    sector_destino: str | None = None
    ubicacion_destino: str | None = None
    # Los dos opcionales: un reemplazo puede no tener nada que ver con service
    # (se cambia un equipo por otro y listo), que es como funcionaba hasta el
    # 2026-08-03. Sin ellos el comportamiento es exactamente el de antes.
    service: ServiceIn | None = None
    cierre_service: CierreServiceIn | None = None


@router.post("/{incidencia_id}/reemplazar-equipo", status_code=201)
def reemplazar_equipo(
    incidencia_id: int,
    data: ReemplazoIn,
    reemplazos: ReemplazoService = Depends(get_reemplazo_service),
    user: dict = Depends(get_current_user),
):
    """Una sola operacion actualiza los dos activos, deja los movimientos
    ligados al ticket y narra las intervenciones. Ver el docstring de
    `ReemplazoService` para el por que."""
    if data.destino not in DESTINOS:
        raise HTTPException(422, f"destino invalido: {data.destino}")
    try:
        return reemplazos.reemplazar(
            incidencia_id,
            equipo_retirado_id=data.equipo_retirado_id,
            equipo_sustituto_id=data.equipo_sustituto_id,
            destino=data.destino,
            motivo=data.motivo,
            sector_destino=data.sector_destino,
            ubicacion_destino=data.ubicacion_destino,
            usuario_actor=user["username"],
            service=DatosService(**data.service.model_dump()) if data.service else None,
            cierre_service=(
                CierreService(**data.cierre_service.model_dump())
                if data.cierre_service else None
            ),
        )
    except KeyError as err:
        que, cual = err.args[0]
        raise HTTPException(404, f"{que} {cual} not found")
    except ValueError as err:
        raise HTTPException(422, str(err))


# ── La conformidad del cliente ───────────────────────────────────────────
#
# Cierra la brecha 7: en el comprobante en papel de Lagrace, la firma certifica
# la conformidad del trabajo y es lo que habilita el cobro a 15 días. Vive en
# el router de incidencias y no en uno propio porque **no es una entidad**: es
# un atributo del ticket que resulta caro de traer siempre (ver
# ).


class FirmaIn(BaseModel):
    #: Data URL de un PNG, tal cual lo produce .
    imagen: str
    firmante: str = ""
    #: "Observaciones del Cliente" del papel. Del cliente, no del técnico.
    observaciones: str = ""


@router.get("/{incidencia_id}/firma")
def obtener_firma(
    incidencia_id: int,
    firmas: FirmaRepository = Depends(get_firma_repository),
):
    """404 si el ticket no está firmado.

    404 y no  con 200: la pantalla necesita distinguir "sin firmar" de
    "no pude leerla", y un cuerpo nulo con 200 no lo hace.
    """
    firma = firmas.obtener(incidencia_id)
    if firma is None:
        raise HTTPException(404, "Este ticket todavía no tiene conformidad.")
    return firma


@router.put("/{incidencia_id}/firma")
def guardar_firma(
    incidencia_id: int,
    payload: FirmaIn,
    firmas: FirmaRepository = Depends(get_firma_repository),
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
    user: dict = Depends(get_current_user),
):
    """PUT y no POST: una incidencia tiene UNA conformidad. Volver a firmar
    reemplaza — es cómo se corrige una firma mal tomada delante del cliente."""
    # Se comprueba que el ticket exista antes de escribir: la FK lo atajaría
    # igual, pero con un 500 de integridad en vez de un 404 que se entiende.
    if incidencias.get(incidencia_id) is None:
        raise HTTPException(404, "La incidencia no existe.")
    try:
        return firmas.guardar(
            incidencia_id, payload.imagen, firmante=payload.firmante,
            observaciones=payload.observaciones, usuario_id=int(user["id"]),
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/{incidencia_id}/firma", status_code=204)
def borrar_firma(
    incidencia_id: int,
    firmas: FirmaRepository = Depends(get_firma_repository),
):
    if not firmas.borrar(incidencia_id):
        raise HTTPException(404, "Este ticket no tiene conformidad.")
