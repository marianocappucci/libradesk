"""Contratos con el proveedor — el papel que hay detrás del insumo.

Cuelga del **mismo módulo que los insumos** (`insumos`) y no de uno propio: un
contrato de proveedor sin el circuito de consumibles no tiene para qué existir
—no se cobra, no se liquida, no emite nada—, así que gatearlo aparte ofrecería
media funcionalidad. Es el mismo criterio con el que activos y contratos cuelgan
juntos de `alquileres`.

Ver `app/services/contratos_proveedor.py` para el modelo y, sobre todo, para lo
que deliberadamente no tiene: plata y topes de copias.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..dependencies import get_contrato_proveedor_repository
from ..services.contratos_proveedor import ContratoProveedorRepository

router = APIRouter(prefix="/api/contratos-proveedor", tags=["contratos-proveedor"])


class ContratoIn(BaseModel):
    proveedor_id: int
    cliente_id: int
    fecha_inicio: date
    # alquiler | comodato | service | mantenimiento — ver `TIPOS`.
    tipo: str = "alquiler"
    # El número que le da el proveedor al contrato, el que hay que citarle.
    numero_externo: str | None = None
    fecha_fin: date | None = None
    renovacion_automatica: bool = False
    incluye_insumos: bool = True
    incluye_service: bool = False
    contacto_nombre: str | None = None
    contacto_telefono: str | None = None
    contacto_email: str | None = None
    observaciones: str | None = None


class ContratoUpdate(BaseModel):
    """No están `proveedor_id` ni `cliente_id`: cambiar cualquiera de los dos no
    corrige un dato, es otro contrato — y arrastraría la cobertura de máquinas
    que no son de ese cliente."""

    tipo: str | None = None
    numero_externo: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    renovacion_automatica: bool | None = None
    incluye_insumos: bool | None = None
    incluye_service: bool | None = None
    contacto_nombre: str | None = None
    contacto_telefono: str | None = None
    contacto_email: str | None = None
    observaciones: str | None = None


class CoberturaIn(BaseModel):
    equipo_id: int
    # Sin fecha, arranca hoy (o el inicio del contrato si es posterior).
    fecha_alta: date | None = None
    observaciones: str | None = None


class RetiroIn(BaseModel):
    fecha_baja: date | None = None
    observaciones: str | None = None


class ReferenciaDeEquipo(BaseModel):
    id: int
    equipo_id: int
    proveedor_id: int | None
    proveedor_nombre: str | None
    etiqueta: str
    valor: str


class CoberturaOut(BaseModel):
    id: int
    contrato_proveedor_id: int
    equipo_id: int
    equipo_descripcion: str | None
    equipo_serial: str | None
    equipo_sector: str | None
    # El número con el que el proveedor llama a esa máquina: es la columna que
    # se lee de esta lista cuando hay que pedirle algo.
    referencias: list[ReferenciaDeEquipo] = []
    fecha_alta: str | None
    fecha_baja: str | None
    vigente: bool
    observaciones: str | None


class ContratoOut(BaseModel):
    id: int
    numero: str
    proveedor_id: int
    proveedor_nombre: str | None
    cliente_id: int
    cliente_nombre: str | None
    tipo: str
    numero_externo: str | None
    fecha_inicio: str | None
    fecha_fin: str | None
    renovacion_automatica: bool
    incluye_insumos: bool
    incluye_service: bool
    contacto_nombre: str | None
    contacto_telefono: str | None
    contacto_email: str | None
    observaciones: str | None
    # Derivados de las fechas, nunca almacenados.
    vigente: bool
    dias_para_vencer: int | None
    equipos_vigentes: int
    created_at: str | None


class ContratoFicha(ContratoOut):
    equipos: list[CoberturaOut] = []


@router.post("", status_code=201, response_model=ContratoOut)
def create_contrato(
    data: ContratoIn,
    contratos: ContratoProveedorRepository = Depends(get_contrato_proveedor_repository),
):
    try:
        return contratos.create(**data.model_dump())
    except KeyError as e:
        que, _id = e.args[0]
        raise HTTPException(404, f"{que} not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("", response_model=list[ContratoOut])
def list_contratos(
    cliente_id: int | None = None,
    proveedor_id: int | None = None,
    vigentes: bool | None = None,
    contratos: ContratoProveedorRepository = Depends(get_contrato_proveedor_repository),
):
    """Los vigentes primero y, dentro de cada grupo, el que vence antes: lo que
    hay que renovar arriba."""
    return contratos.list(
        cliente_id=cliente_id, proveedor_id=proveedor_id, vigentes=vigentes,
    )


@router.get("/{contrato_id}", response_model=ContratoFicha)
def get_contrato(
    contrato_id: int,
    contratos: ContratoProveedorRepository = Depends(get_contrato_proveedor_repository),
):
    c = contratos.get(contrato_id)
    if c is None:
        raise HTTPException(404, "contrato not found")
    return c


@router.put("/{contrato_id}", response_model=ContratoOut)
def update_contrato(
    contrato_id: int, data: ContratoUpdate,
    contratos: ContratoProveedorRepository = Depends(get_contrato_proveedor_repository),
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
    contratos: ContratoProveedorRepository = Depends(get_contrato_proveedor_repository),
):
    """Se lleva sus líneas de cobertura. Los insumos ya cargados **no se
    tocan**: la cobertura se resuelve al preguntarla, así que un insumo viejo
    pasa a figurar sin contrato en vez de desaparecer."""
    try:
        contratos.delete(contrato_id)
    except KeyError:
        raise HTTPException(404, "contrato not found")
    return Response(status_code=204)


@router.get("/equipos/{equipo_id}/cobertura", response_model=ContratoOut | None)
def cobertura_de_equipo(
    equipo_id: int,
    contratos: ContratoProveedorRepository = Depends(get_contrato_proveedor_repository),
):
    """El contrato que cubre HOY a ese equipo, o `null` si ninguno.

    `null` con 200 y no un 404: que una máquina no esté cubierta es una
    respuesta, no un error — de hecho es el estado de todo el parque hasta que
    alguien cargue el primer contrato. Un 404 obligaría a la pantalla a
    distinguirlo de un equipo inexistente.

    Cuelga de este router y no del de equipos porque **está gateado por
    `insumos`**: una instancia que no contrató el módulo no tiene por qué
    enterarse de que existen los contratos de proveedor.
    """
    return contratos.cobertura_de_equipo(equipo_id)


@router.post("/{contrato_id}/equipos", status_code=201, response_model=CoberturaOut)
def cubrir_equipo(
    contrato_id: int, data: CoberturaIn,
    contratos: ContratoProveedorRepository = Depends(get_contrato_proveedor_repository),
):
    """Agrega una máquina al contrato. Devuelve 409 si esa máquina ya está
    cubierta por otro contrato en esa fecha, con el número del que choca."""
    try:
        return contratos.cubrir(contrato_id, **data.model_dump())
    except KeyError as e:
        que, _id = e.args[0]
        raise HTTPException(404, f"{que} not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/equipos/{linea_id}/retirar", response_model=CoberturaOut)
def retirar_equipo(
    linea_id: int, data: RetiroIn,
    contratos: ContratoProveedorRepository = Depends(get_contrato_proveedor_repository),
):
    """Cierra la cobertura de esa máquina. **No borra la línea**: que el
    contrato la haya cubierto entre marzo y agosto es lo que hace contestable si
    el tóner de junio entraba o no.

    La ruta cuelga de la línea y no del contrato —`/equipos/{linea_id}/retirar`
    y no `/{contrato_id}/equipos/{linea_id}`— porque el id de la línea ya la
    identifica sola; pedir además el contrato admitiría una combinación
    inexistente que habría que validar. No choca con `/{contrato_id}`: son tres
    segmentos contra uno.
    """
    try:
        return contratos.retirar(linea_id, **data.model_dump())
    except KeyError:
        raise HTTPException(404, "cobertura not found")
    except ValueError as e:
        raise HTTPException(409, str(e))
