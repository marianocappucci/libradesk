"""Catalogo de servicios: ABM y el buscador que alimenta las sugerencias.

El ABM es admin-only; **el buscador no**, porque quien arma un presupuesto es
staff. Cerrarlo dejaria el catalogo cargado y sin nadie que pueda usarlo, que
es el escenario que este pedido viene a evitar. Ver el montaje en `main.py`.
"""
from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel, Field

from ..dependencies import get_servicio_repository
from ..services import precios
from ..services.iva import ALICUOTAS, AlicuotaInvalida
from ..services.servicios_repo_catalogo import ServicioCatalogoRepository

router = APIRouter(prefix="/api/servicios", tags=["servicios"])


@router.get("/alicuotas", response_model=list[float])
def alicuotas():
    """Las alícuotas que la pantalla puede ofrecer.

    Salen del backend y no se hardcodean en el frontend para que haya **una**
    lista: si se agregara una y la pantalla siguiera con las cuatro de antes,
    el catálogo aceptaría por API algo que nadie puede elegir.

    Ruta literal antes de `/{servicio_id}`, por el mismo motivo que `/buscar`.
    """
    return [float(a) for a in ALICUOTAS]


class ServicioIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    descripcion: str = Field(default="", max_length=500)
    precio: float = Field(default=0, ge=0)
    # Se valida contra la lista cerrada en el repositorio, no aca: el mensaje
    # de error nombra las alicuotas validas, que es mas util que un 422 de
    # pydantic diciendo "value is not a valid enumeration member".
    iva_rate: float = Field(default=0.21, ge=0, le=1)
    #: Si este es el servicio con el que se cotiza **la hora de trabajo** al
    #: generarle el remito a un reclamo. Marcarlo desmarca al que lo estuviera:
    #: es uno solo, y la regla la aplica el repositorio.
    es_valor_hora: bool = False


class ServicioUpdate(ServicioIn):
    activo: bool = True


class ServicioOut(BaseModel):
    id: int
    nombre: str
    descripcion: str
    # El texto que va al comprobante, ya resuelto (descripcion, o el nombre si
    # esta vacia). La pantalla no repite la regla.
    texto: str
    precio: float
    iva_rate: float
    activo: bool
    es_valor_hora: bool


@router.get("", response_model=list[ServicioOut])
def listar(
    incluir_inactivos: bool = False,
    servicios: ServicioCatalogoRepository = Depends(get_servicio_repository),
):
    return servicios.listar(incluir_inactivos=incluir_inactivos)


@router.get("/buscar", response_model=list[ServicioOut])
def buscar(q: str = "", cliente_id: int | None = None,
           lista_id: int | None = None,
           servicios: ServicioCatalogoRepository = Depends(get_servicio_repository)):
    """Las sugerencias del formulario de comprobante.

    Ruta literal declarada ANTES de `/{servicio_id}` a proposito: las dos
    tienen la misma forma y FastAPI matchea en orden de registro, asi que al
    reves "buscar" caeria en la otra y fallaria al convertirlo a int.

    🔑 **Con `cliente_id` los precios salen de SU lista.** Sin el, de la lista
    por defecto — que es como cotizaba todo antes del 2026-08-16. `lista_id`
    pisa al del cliente, que es la precedencia decidida por el humano.

    Los precios se resuelven **de a lote y no de a uno por sugerencia**: el
    desplegable muestra hasta ocho, y una consulta por cada una serian ocho por
    cada letra que se tipea.
    """
    filas = servicios.buscar(q)
    if not filas:
        return filas
    tabla = precios.precios_de(
        [f["id"] for f in filas], cliente_id=cliente_id, lista_id=lista_id,
    )
    for f in filas:
        f["precio"] = tabla.get(f["id"], f["precio"])
    return filas


@router.get("/{servicio_id}", response_model=ServicioOut)
def obtener(servicio_id: int, servicios: ServicioCatalogoRepository = Depends(get_servicio_repository)):
    s = servicios.get(servicio_id)
    if s is None:
        raise HTTPException(404, "servicio not found")
    return s


@router.post("", status_code=201, response_model=ServicioOut)
def crear(data: ServicioIn, servicios: ServicioCatalogoRepository = Depends(get_servicio_repository)):
    try:
        return servicios.crear(
            data.nombre, data.descripcion, data.precio, data.iva_rate,
            data.es_valor_hora,
        )
    except AlicuotaInvalida as e:
        raise HTTPException(422, str(e))


@router.put("/{servicio_id}", response_model=ServicioOut)
def actualizar(
    servicio_id: int,
    data: ServicioUpdate,
    servicios: ServicioCatalogoRepository = Depends(get_servicio_repository),
):
    try:
        s = servicios.actualizar(
            servicio_id, data.nombre, data.descripcion, data.precio, data.activo,
            data.iva_rate, data.es_valor_hora,
        )
    except AlicuotaInvalida as e:
        raise HTTPException(422, str(e))
    if s is None:
        raise HTTPException(404, "servicio not found")
    return s


@router.delete("/{servicio_id}", status_code=204)
def borrar(servicio_id: int, servicios: ServicioCatalogoRepository = Depends(get_servicio_repository)):
    """Borra de verdad: ningun comprobante lo referencia. Aun asi la pantalla
    ofrece desactivar primero."""
    if not servicios.borrar(servicio_id):
        raise HTTPException(404, "servicio not found")
