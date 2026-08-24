"""Insumos por equipo — pedir, recibir y colocar.

Tres endpoints de acción y no un CRUD a secas porque son tres momentos
distintos, con días entre uno y otro y hechos por personas distintas: se pide
por teléfono, llega con un remito, y se pone cuando el técnico pasa. Un solo
`PUT` con las tres fechas dejaría que la bandeja de pendientes dependiera de que
alguien se acuerde de borrar un campo.

El alta acepta las tres fechas igual, y eso es lo que permite registrar un
cambio **ya hecho** —el caso de la primera carga, cuando se vuelca lo que estaba
en un cuaderno— sin inventar un pedido que nunca existió.

Ver `app/services/insumos.py` para el modelo y, sobre todo, para el límite: este
módulo **no mueve stock**.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..dependencies import get_insumo_repository
from ..services.insumos import InsumoRepository

router = APIRouter(prefix="/api/insumos", tags=["insumos"])


class InsumoIn(BaseModel):
    equipo_id: int
    # `catalog_items.id` del catálogo de consumibles (módulo `stock`). Es el
    # que identifica QUÉ tóner: una máquina color lleva cuatro items distintos,
    # y por eso no hay campo "color" al lado.
    insumo_item_id: int
    # Una fila por unidad — ver el docstring del servicio.
    cantidad: int = Field(default=1, ge=1, le=50)
    # None y equipo de un tercero → se hereda el proveedor del equipo.
    proveedor_id: int | None = None
    fecha_pedido: date | None = None
    fecha_entrega: date | None = None
    fecha_colocacion: date | None = None
    remito_proveedor: str | None = None
    contador_copias: int | None = Field(default=None, ge=0)
    incidencia_id: int | None = None
    observaciones: str | None = None


class EntregaIn(BaseModel):
    fecha_entrega: date
    remito_proveedor: str | None = None


class ColocacionIn(BaseModel):
    fecha_colocacion: date
    # La lectura del display al poner el insumo. Opcional: si la máquina no
    # tiene contador o nadie lo miró, el cambio se registra igual y lo único
    # que no se puede calcular es el rendimiento.
    contador_copias: int | None = Field(default=None, ge=0)


class InsumoUpdate(BaseModel):
    """Corrección de una carga. No están `equipo_id` ni `insumo_item_id`: mover
    una fila de equipo o de insumo no corrige un dato, arrastra el rendimiento
    de dos cadenas de contadores."""

    proveedor_id: int | None = None
    fecha_pedido: date | None = None
    fecha_entrega: date | None = None
    fecha_colocacion: date | None = None
    remito_proveedor: str | None = None
    contador_copias: int | None = Field(default=None, ge=0)
    observaciones: str | None = None


class InsumoOut(BaseModel):
    id: int
    equipo_id: int
    equipo_descripcion: str | None
    equipo_serial: str | None
    cliente_id: int | None
    insumo_item_id: int
    insumo_nombre: str
    proveedor_id: int | None
    proveedor_nombre: str | None
    fecha_pedido: str | None
    fecha_entrega: str | None
    fecha_colocacion: str | None
    # Derivados de las fechas, nunca almacenados.
    estado: str
    dias_esperando: int | None
    remito_proveedor: str | None
    contador_copias: int | None
    # Lo que rindió el insumo anterior de la misma clase en este equipo.
    copias_desde_el_anterior: int | None
    # El contrato de proveedor que cubría el equipo en la fecha de esta fila
    # (fase 2). Se resuelve al leer, no se guarda.
    contrato_numero: str | None
    # 🔑 Tener contrato **no** es estar cubierto: uno de service cubre la
    # máquina y no los insumos, así que ese tóner se paga igual.
    cubierto_por_contrato: bool
    incidencia_id: int | None
    usuario: str
    observaciones: str | None
    created_at: str | None


@router.post("", status_code=201, response_model=list[InsumoOut])
def create_insumo(
    data: InsumoIn,
    insumos: InsumoRepository = Depends(get_insumo_repository),
    user: dict = Depends(get_current_user),
):
    """Devuelve una **lista**: `cantidad` unidades son `cantidad` filas."""
    try:
        return insumos.create(usuario=user["username"], **data.model_dump())
    except KeyError as e:
        que, _id = e.args[0]
        raise HTTPException(404, f"{que} not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("", response_model=list[InsumoOut])
def list_insumos(
    equipo_id: int | None = None,
    cliente_id: int | None = None,
    proveedor_id: int | None = None,
    insumo_item_id: int | None = None,
    incidencia_id: int | None = None,
    estado: str | None = None,
    insumos: InsumoRepository = Depends(get_insumo_repository),
):
    """`estado=pendiente` responde "qué me deben"; sin filtro sale todo, con lo
    pendiente arriba."""
    try:
        return insumos.list(
            equipo_id=equipo_id, cliente_id=cliente_id, proveedor_id=proveedor_id,
            insumo_item_id=insumo_item_id, incidencia_id=incidencia_id,
            estado=estado,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


class ResumenOut(BaseModel):
    """El consumo de un insumo en una máquina, ya resumido (fase 3).

    Todo derivado del historial: no hay ninguna tabla nueva detrás de esto.
    """

    equipo_id: int
    equipo_descripcion: str | None
    equipo_sector: str | None
    cliente_id: int | None
    cliente_nombre: str | None
    insumo_item_id: int
    insumo_nombre: str
    # Cuántas colocaciones hay registradas. Con menos de dos no hay intervalo
    # que promediar y el estado es `sin_historial`.
    cambios: int
    ultimo_cambio: str | None
    dias_desde_el_ultimo: int | None
    # Cada cuánto se cambia esta máquina. 🔑 Mide el CAMBIO, no la vida del
    # tóner: adentro del intervalo está el tiempo que la máquina estuvo parada
    # esperando el repuesto. Para "cuánto dura un tóner" el número honesto es
    # `copias_promedio`, que no depende de cuándo se pudo cambiar.
    dias_entre_cambios: int | None
    copias_promedio: int | None
    # Lo que tarda el proveedor en entregar para esta máquina, medido de sus
    # propias entregas. Es lo que se le descuenta al aviso.
    demora_proveedor: int | None
    proximo_cambio_estimado: str | None
    # Desde cuándo conviene pedirlo, que es antes de que se acabe.
    pedir_desde: str | None
    # sin_historial | ya_pedido | pedir_ahora | al_dia
    estado: str
    dias_para_pedir: int | None


@router.get("/resumen", response_model=list[ResumenOut])
def resumen_de_consumo(
    cliente_id: int | None = None,
    equipo_id: int | None = None,
    estado: str | None = None,
    insumos: InsumoRepository = Depends(get_insumo_repository),
):
    """Qué le toca a cada máquina — la fase 3.

    Convierte el historial que se viene cargando en algo que se puede mirar
    **antes** de que la máquina se pare: cada cuánto se cambia, cuándo fue la
    última vez y desde cuándo conviene ir pidiendo el próximo.

    Va antes que `/{insumo_id}` en el archivo **y hace falta**: `resumen` no
    parsea como entero, así que sin este orden la ruta caería en la de la ficha
    y devolvería un 422 en vez de la lista.

    `estado=pedir_ahora` es la bandeja: lo que hay que pedir hoy.
    """
    try:
        return insumos.resumen(
            cliente_id=cliente_id, equipo_id=equipo_id, estado=estado,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/{insumo_id}", response_model=InsumoOut)
def get_insumo(
    insumo_id: int, insumos: InsumoRepository = Depends(get_insumo_repository),
):
    i = insumos.get(insumo_id)
    if i is None:
        raise HTTPException(404, "insumo not found")
    return i


@router.post("/{insumo_id}/entrega", response_model=InsumoOut)
def entregar_insumo(
    insumo_id: int, data: EntregaIn,
    insumos: InsumoRepository = Depends(get_insumo_repository),
):
    """Llegó. Es el paso que saca la fila de la bandeja de pendientes."""
    try:
        return insumos.entregar(insumo_id, **data.model_dump())
    except KeyError:
        raise HTTPException(404, "insumo not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/{insumo_id}/colocacion", response_model=InsumoOut)
def colocar_insumo(
    insumo_id: int, data: ColocacionIn,
    insumos: InsumoRepository = Depends(get_insumo_repository),
):
    """Se puso en la máquina, con la lectura del contador."""
    try:
        return insumos.colocar(insumo_id, **data.model_dump())
    except KeyError:
        raise HTTPException(404, "insumo not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.put("/{insumo_id}", response_model=InsumoOut)
def update_insumo(
    insumo_id: int, data: InsumoUpdate,
    insumos: InsumoRepository = Depends(get_insumo_repository),
):
    try:
        return insumos.update(insumo_id, **data.model_dump(exclude_unset=True))
    except KeyError as e:
        if e.args and isinstance(e.args[0], tuple):
            que, _id = e.args[0]
            raise HTTPException(404, f"{que} not found")
        raise HTTPException(404, "insumo not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/{insumo_id}", status_code=204)
def delete_insumo(
    insumo_id: int, insumos: InsumoRepository = Depends(get_insumo_repository),
):
    try:
        insumos.delete(insumo_id)
    except KeyError:
        raise HTTPException(404, "insumo not found")
    return Response(status_code=204)
