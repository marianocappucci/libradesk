"""Contratos de equipos — la ficha, sus precios con vigencia y sus equipos.

**El importe no se edita por `PUT /api/contratos/{id}`**: se actualiza con
`POST /api/contratos/{id}/precios`, que cierra el vigente y abre el nuevo. Son
dos endpoints y no uno porque son dos cosas distintas — corregir un dato del
contrato no es lo mismo que cambiar cuánto se cobra a partir de una fecha.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..dependencies import get_contrato_repository
from ..services.contratos import (
    CierreServiceActivo, ContratoRepository, DatosServiceActivo,
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
