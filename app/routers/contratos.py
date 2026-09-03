"""Contratos de equipos — la ficha, sus precios con vigencia, sus equipos y sus
actas de entrega y devolución.

**El importe no se edita por `PUT /api/contratos/{id}`**: se actualiza con
`POST /api/contratos/{id}/precios`, que cierra el vigente y abre el nuevo. Son
dos endpoints y no uno porque son dos cosas distintas — corregir un dato del
contrato no es lo mismo que cambiar cuánto se cobra a partir de una fecha.

**Las actas viven acá y no en un router propio** (fase 3): son un documento
*del contrato*, salen de su ficha y comparten su gate de módulo. Un router
aparte con el mismo prefijo habría dejado el orden de registro decidiendo cuál
ruta atiende `/api/contratos/actas/5`, que es la clase de detalle que se
descubre en producción.
"""
import os
from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..dependencies import (
    get_acta_repository,
    get_contrato_repository,
    get_data_dir,
)
from ..services import acta_pdf, archivos
from ..services.actas import ActaRepository
from ..services.contratos import (
    CierreServiceActivo,
    ContratoRepository,
    DatosServiceActivo,
)

router = APIRouter(prefix="/api/contratos", tags=["contratos"])


class ContratoIn(BaseModel):
    tipo_contrato: str
    cliente_id: int
    fecha_inicio: date
    propietario_cliente_id: int | None = None
    sector_id: int | None = None
    domicilio_instalacion: str | None = None
    fecha_fin: date | None = None
    renovacion_automatica: bool = False
    periodicidad: str = "mensual"
    #: Cada cuanto se VISITA, que **no** es cada cuanto se cobra. `None` = no
    #: genera visitas de mantenimiento, y es el default: los contratos que ya
    #: existen se comportan como hoy. Ver la revision `0027`.
    frecuencia_visita: str | None = None
    #: Desde cuando corre la cadencia **y** que dia se visita: una sola fecha
    #: resuelve las dos cosas -su mes ancla, su dia es el dia de la visita-.
    #: `None` cae a `fecha_inicio`. Ver la revision `0030`.
    primera_visita: date | None = None
    duracion_visita_minutos: int | None = None
    dia_vencimiento: int | None = None
    moneda: str = "ARS"
    metodo_actualizacion: str = "manual"
    estado: str = "borrador"
    responsable: str | None = None
    observaciones: str | None = None
    # El primer precio, en el mismo request que el alta. Ver
    # `ContratoRepository.create`: separarlos admite un alquiler activo sin
    # ningún precio, del que no se puede derivar cuánto cobrar.
    importe: float | None = None


class ContratoUpdate(BaseModel):
    tipo_contrato: str | None = None
    cliente_id: int | None = None
    propietario_cliente_id: int | None = None
    sector_id: int | None = None
    domicilio_instalacion: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    renovacion_automatica: bool | None = None
    periodicidad: str | None = None
    frecuencia_visita: str | None = None
    primera_visita: date | None = None
    duracion_visita_minutos: int | None = None
    dia_vencimiento: int | None = None
    moneda: str | None = None
    metodo_actualizacion: str | None = None
    estado: str | None = None
    responsable: str | None = None
    observaciones: str | None = None


class PrecioIn(BaseModel):
    importe: float
    vigencia_desde: date
    motivo: str | None = None


class ServiceIn(BaseModel):
    """A dónde se manda el activo que sale. Viaja **dentro** del retiro o del
    reemplazo, misma forma que `DatosService` en "Reemplazar equipo": sacar el
    equipo y registrar a dónde se lo mandó son el mismo hecho."""

    proveedor_id: int
    fecha_envio: date
    remito_salida: str | None = None
    rma: str | None = None
    en_garantia: bool = False
    observaciones: str | None = None


class CierreServiceIn(BaseModel):
    """La vuelta del activo que entra: cierra su reparación abierta."""

    fecha_retorno: date
    diagnostico: str | None = None
    costo: float | None = None


class ColocarIn(BaseModel):
    activo_id: int
    fecha_instalacion: date
    tecnico_instalador_id: int | None = None
    ubicacion: str | None = None
    incidencia_id: int | None = None
    observaciones: str | None = None
    # Colocar un activo que volvió de reparar: cierra su reparación abierta en
    # el mismo gesto. Sin esto un activo `en_reparacion` no se puede colocar y
    # la vuelta del service no tendría camino.
    cierre_service: CierreServiceIn | None = None


class RetirarIn(BaseModel):
    fecha_retiro: date
    motivo_retiro: str
    # **El default vive acá y en ningún otro lado.** `ContratoRepository.retirar`
    # lo exige explícito: teniéndolo en los dos, el del servicio no se ejecuta
    # nunca (el router siempre manda un valor) y romperlo no ponía ningún test
    # en rojo.
    estado_activo: str = "retirado_a_revisar"
    observaciones: str | None = None
    # Sólo con `estado_activo="en_reparacion"` — el servicio rechaza el resto,
    # porque una reparación sobre un equipo que va a depósito describiría algo
    # que no pasó.
    service: ServiceIn | None = None
    incidencia_id: int | None = None


class ActaLineaIn(BaseModel):
    """Un equipo dentro del acta. `contrato_equipo_id` es la **colocación**, no
    el activo: ver el docstring de `ContratoActaLinea`."""

    contrato_equipo_id: int
    estado_fisico: str | None = None
    accesorios: str | None = None
    # Los tres de devolución. En una entrega el servicio los rechaza: el equipo
    # sale de acá, no hay nada que falte ni que cobrar.
    faltantes: str | None = None
    danios: str | None = None
    cargo_reposicion: float | None = None
    observaciones: str | None = None


class ActaIn(BaseModel):
    tipo: str
    fecha: date
    lineas: list[ActaLineaIn]
    # Aclaraciones **tipeadas**, no firmas. El acta se imprime y se firma a
    # mano; ver el docstring de `app/services/actas.py`.
    entrega_nombre: str | None = None
    recibe_nombre: str | None = None
    observaciones: str | None = None


class AnularActaIn(BaseModel):
    motivo: str | None = None


class ReemplazarIn(BaseModel):
    activo_nuevo_id: int
    fecha: date
    estado_activo_retirado: str = "retirado_a_revisar"
    tecnico_instalador_id: int | None = None
    incidencia_id: int | None = None
    observaciones: str | None = None
    service: ServiceIn | None = None
    cierre_service: CierreServiceIn | None = None


def _usuario(request) -> str:
    """Quién hizo el cambio, para el histórico de precios. `getattr` porque el
    router también se ejercita en tests sin sesión montada."""
    user = getattr(request.state, "user", None)
    return getattr(user, "username", None) or "Sistema"


@router.post("", status_code=201)
def create_contrato(
    data: ContratoIn,
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    try:
        return contratos.create(**data.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("")
def list_contratos(
    cliente_id: int | None = None,
    estado: str | None = None,
    tipo_contrato: str | None = None,
    activo_id: int | None = None,
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    return contratos.list(
        cliente_id=cliente_id, estado=estado, tipo_contrato=tipo_contrato,
        activo_id=activo_id,
    )


@router.get("/{contrato_id}")
def get_contrato(
    contrato_id: int,
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    """La ficha completa: incluye `lineas` (todas, no sólo las vigentes) y
    `precios` (el histórico entero)."""
    c = contratos.get(contrato_id)
    if c is None:
        raise HTTPException(404, "contrato not found")
    return c


@router.put("/{contrato_id}")
def update_contrato(
    contrato_id: int, data: ContratoUpdate,
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    try:
        return contratos.update(contrato_id, **data.model_dump(exclude_unset=True))
    except KeyError:
        raise HTTPException(404, "contrato not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/{contrato_id}", status_code=204)
def delete_contrato(
    contrato_id: int,
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    try:
        contratos.delete(contrato_id)
    except KeyError:
        raise HTTPException(404, "contrato not found")
    except ValueError as e:
        raise HTTPException(409, str(e))
    return Response(status_code=204)


# --- precios -----------------------------------------------------------------

def _ruta_archivo(data_dir: str, contrato_id: int) -> str:
    """El nombre sale del id, **no del que subio el archivo**.

    Un `filename` de cliente es texto arbitrario que el que manda el request
    elige: `../../../app/main.py` es un nombre valido. Derivarlo del id saca el
    problema de raiz en vez de sanearlo, y de paso deja **un solo archivo por
    contrato** — volver a subir reemplaza, que es lo que quiere el que escaneo
    torcido la primera vez.
    """
    return os.path.join(data_dir, "contratos", f"contrato_{contrato_id}.pdf")


@router.post("/{contrato_id}/archivo")
async def subir_archivo(
    contrato_id: int,
    archivo: UploadFile = File(...),
    contratos: ContratoRepository = Depends(get_contrato_repository),
    data_dir: str = Depends(get_data_dir),
):
    """El contrato firmado escaneado.

    Es lo que `contratos.archivo_pdf` venia esperando desde la fase 1. El acta
    de entrega la emite el sistema y se firma en papel; **el papel firmado no
    tenia como volver**, asi que el vinculo entre lo que se acordo y lo que
    dice el sistema era el numero de contrato y nada mas.

    Gate: el del router (`staff_or_admin` + modulo `alquileres`). No se le pone
    `require_admin` propio — quien carga el contrato es quien lo trae firmado
    de la visita, y esconderselo al staff no protege nada que la API no le deje
    hacer igual por `PUT`.
    """
    if contratos.get(contrato_id) is None:
        raise HTTPException(404, "contrato not found")
    destino = _ruta_archivo(data_dir, contrato_id)
    bytes_escritos = await archivos.guardar_pdf(archivo, destino)
    contratos.set_archivo(contrato_id, destino)
    return {"archivo_pdf": destino, "bytes": bytes_escritos}


@router.get("/{contrato_id}/archivo")
def bajar_archivo(
    contrato_id: int,
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    """`inline`, igual que el acta: lo normal es mirarlo, no bajarlo.

    Se chequea **el disco y no solo la columna**. Un restore de backup viejo,
    un volumen que no se monto o un borrado a mano dejan la fila apuntando a un
    archivo que no esta, y entonces `FileResponse` revienta con un 500 que no
    dice nada. Con el chequeo, la pantalla dice "no hay firmado cargado", que
    es lo que el usuario necesita saber.
    """
    c = contratos.get(contrato_id)
    if c is None:
        raise HTTPException(404, "contrato not found")
    path = c["archivo_pdf"]
    if not path or not os.path.exists(path):
        raise HTTPException(404, "El contrato no tiene el firmado cargado.")
    return FileResponse(
        path, media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="contrato-{c["numero"]}.pdf"',
        },
    )


@router.delete("/{contrato_id}/archivo", status_code=204)
def borrar_archivo(
    contrato_id: int,
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    """Saca el archivo del disco y la referencia de la fila, en ese orden.

    Al reves —limpiar la fila y despues el disco— un error en el medio deja el
    PDF del cliente en el volumen sin nadie que sepa que esta ahi.
    """
    c = contratos.get(contrato_id)
    if c is None:
        raise HTTPException(404, "contrato not found")
    path = c["archivo_pdf"]
    if path and os.path.exists(path):
        os.remove(path)
    contratos.set_archivo(contrato_id, None)
    return Response(status_code=204)


@router.get("/{contrato_id}/precios")
def list_precios(
    contrato_id: int,
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    if contratos.get(contrato_id) is None:
        raise HTTPException(404, "contrato not found")
    return contratos.list_precios(contrato_id)


@router.post("/{contrato_id}/precios", status_code=201)
def actualizar_precio(
    contrato_id: int, data: PrecioIn, request: Request,
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    """Cierra el precio vigente y abre el nuevo. El anterior **no se modifica en
    su importe** — se le pone fecha de fin."""
    try:
        return contratos.actualizar_precio(
            contrato_id, usuario=_usuario(request), **data.model_dump()
        )
    except KeyError:
        raise HTTPException(404, "contrato not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/{contrato_id}/precio-en/{fecha}")
def precio_en(
    contrato_id: int, fecha: date,
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    """Qué precio regía en esa fecha. Es la consulta que justifica el histórico:
    sin ella, rehacer una liquidación vieja daría el precio de hoy."""
    if contratos.get(contrato_id) is None:
        raise HTTPException(404, "contrato not found")
    p = contratos.precio_en(contrato_id, fecha)
    if p is None:
        raise HTTPException(404, "sin precio vigente en esa fecha")
    return p


# --- equipos del contrato ----------------------------------------------------

@router.get("/{contrato_id}/equipos")
def list_equipos(
    contrato_id: int,
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    if contratos.get(contrato_id) is None:
        raise HTTPException(404, "contrato not found")
    return contratos.list_lineas(contrato_id)


@router.post("/{contrato_id}/equipos", status_code=201)
def colocar_equipo(
    contrato_id: int, data: ColocarIn, request: Request,
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    campos = data.model_dump(exclude={"cierre_service"})
    try:
        return contratos.colocar(
            contrato_id, usuario=_usuario(request),
            cierre_service=_cierre(data.cierre_service), **campos,
        )
    except KeyError as e:
        que, _id = e.args[0]
        raise HTTPException(404, f"{que} not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


def _service(data) -> DatosServiceActivo | None:
    return DatosServiceActivo(**data.model_dump()) if data is not None else None


def _cierre(data) -> CierreServiceActivo | None:
    return CierreServiceActivo(**data.model_dump()) if data is not None else None


@router.post("/equipos/{linea_id}/retirar")
def retirar_equipo(
    linea_id: int, data: RetirarIn, request: Request,
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    """Cierra la línea y devuelve el activo al stock. **No lo pone
    `disponible`** por defecto: un equipo que vuelve de un cliente queda
    `retirado_a_revisar` hasta que alguien lo mire.

    Con `service` cargado, además abre la reparación **en la misma
    transacción** — el activo no puede quedar `en_reparacion` sin una
    reparación que diga dónde está."""
    campos = data.model_dump(exclude={"service"})
    try:
        return contratos.retirar(
            linea_id, service=_service(data.service),
            usuario=_usuario(request), **campos,
        )
    except KeyError as e:
        que = e.args[0][0] if isinstance(e.args[0], tuple) else "línea"
        raise HTTPException(404, f"{que} not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/equipos/{linea_id}/reemplazar")
def reemplazar_equipo(
    linea_id: int, data: ReemplazarIn, request: Request,
    contratos: ContratoRepository = Depends(get_contrato_repository),
):
    """Sustituye el equipo **sin borrar el anterior**: devuelve las dos líneas,
    la que se cerró y la que se abrió, más la reparación que abrió (`service`) y
    la que cerró (`cierre_service`)."""
    campos = data.model_dump(exclude={"service", "cierre_service"})
    try:
        return contratos.reemplazar(
            linea_id, service=_service(data.service),
            cierre_service=_cierre(data.cierre_service),
            usuario=_usuario(request), **campos,
        )
    except KeyError as e:
        que, _id = e.args[0]
        raise HTTPException(404, f"{que} not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


# --- actas de entrega y devolución (fase 3) ----------------------------------
#
# ⚠️ **Van después de las rutas del contrato y el orden importa.** FastAPI
# resuelve por orden de registro, así que `/actas/{acta_id}` tiene que quedar
# donde ninguna ruta anterior con la misma cantidad de segmentos la capture. Las
# de arriba tienen un literal en la segunda posición (`precios`, `equipos`,
# `precio-en`), así que no chocan — pero una ruta nueva de dos segmentos con un
# parámetro ahí sí lo haría, y se rompería en silencio.

@router.get("/{contrato_id}/actas")
def list_actas(
    contrato_id: int,
    contratos: ContratoRepository = Depends(get_contrato_repository),
    actas: ActaRepository = Depends(get_acta_repository),
):
    if contratos.get(contrato_id) is None:
        raise HTTPException(404, "contrato not found")
    return actas.list(contrato_id)


@router.post("/{contrato_id}/actas", status_code=201)
def emitir_acta(
    contrato_id: int, data: ActaIn, request: Request,
    actas: ActaRepository = Depends(get_acta_repository),
):
    """Emite el acta con sus equipos y, si la devolución cobra faltantes, su
    cuota de reposición — todo en la misma transacción."""
    campos = data.model_dump(exclude={"lineas"})
    try:
        return actas.create(
            contrato_id, usuario=_usuario(request),
            lineas=[le.model_dump() for le in data.lineas], **campos,
        )
    except KeyError as e:
        que, _id = e.args[0]
        raise HTTPException(404, f"{que} not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/actas/{acta_id}")
def get_acta(acta_id: int, actas: ActaRepository = Depends(get_acta_repository)):
    a = actas.get(acta_id)
    if a is None:
        raise HTTPException(404, "acta not found")
    return a


@router.get("/actas/{acta_id}/pdf")
def acta_en_pdf(acta_id: int, actas: ActaRepository = Depends(get_acta_repository)):
    """El acta en PDF, para imprimirla y firmarla.

    `inline` y no `attachment`, igual que el comprobante del taller: lo normal
    es mirarla y mandarla a la impresora antes de salir a la instalación.
    """
    datos = actas.datos_para_pdf(acta_id)
    if datos is None:
        raise HTTPException(404, "acta not found")
    return Response(
        content=acta_pdf.generar_pdf_acta(datos),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{datos["numero"]}.pdf"'},
    )


@router.post("/actas/{acta_id}/anular")
def anular_acta(
    acta_id: int, data: AnularActaIn,
    actas: ActaRepository = Depends(get_acta_repository),
):
    """Anula en vez de borrar, y **libera la colocación** para poder emitir la
    correcta. Si el acta cobró y esa cuota ya salió en un remito, no se anula
    ninguna de las dos."""
    try:
        return actas.anular(acta_id, motivo=data.motivo)
    except KeyError:
        raise HTTPException(404, "acta not found")
    except ValueError as e:
        raise HTTPException(409, str(e))
