from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..dependencies import (
    get_cliente_repository,
    get_equipo_repository, get_incidencia_repository, get_reemplazo_service,
    get_remito_service, get_servicio_repository,
)
from ..services import incidencia_pdf
from ..services.clientes import ClienteRepository
from ..services.equipos import EquipoRepository
from ..services.incidencias import IncidenciaRepository
from ..services.reemplazo import (
    DESTINOS, CierreService, DatosService, ReemplazoService,
)
from ..services.remitos_presupuestos import RemitoService
from ..services.servicios import ServicioRepository

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
    #: Qué parte de este reclamo cubre el abono del cliente: `total`, `parcial`
    #: o `fuera`. Sólo tiene sentido con un cliente `tipo_facturacion='mensual'`.
    #:
    #: 🔴 `None` **no** es "se factura entero": es "nadie lo decidió". Con
    #: abono, `convertir_a_remito` se niega a emitir hasta que se elija — que es
    #: la diferencia entre no cobrar de más por olvido y cobrar de más en
    #: silencio.
    cobertura_abono: str | None = None
    #: Cuántas de las `horas_invertidas` cubre el abono. Sólo con `parcial`.
    abono_horas_cubiertas: float | None = None
    #: Si los materiales del reclamo entran al abono. Sólo con `parcial`.
    abono_materiales_incluidos: bool | None = None
    activo: bool = True


class IncidenciaOut(IncidenciaIn):
    id: int
    fecha_creacion: str | None = None
    fecha_cierre: str | None = None
    #: El remito que se generó de este reclamo, si se generó.
    #:
    #: 🔴 Va en `IncidenciaOut` y **no** en `IncidenciaIn`, y eso es lo que lo
    #: protege: el PUT manda el objeto entero, así que un campo editable que la
    #: pantalla no reenvíe vuelve a `null` —es como este producto perdió el
    #: `nro_cds` una vez—. Al no estar en el payload de entrada, `update()` ni
    #: siquiera lo recibe. Lo escribe sólo `convertir_a_remito`.
    remito_id: int | None = None
    #: De qué contrato salió esta visita de mantenimiento, qué período cubre, y
    #: el derivado con el que la pantalla la distingue de un reclamo.
    #:
    #: 🔴 **Van acá y no en `IncidenciaIn`, por el mismo motivo que
    #: `remito_id`**: el PUT manda el objeto entero, así que un campo editable
    #: que la pantalla no reenvíe vuelve a `null`. Las escribe sólo el generador
    #: de visitas; editar el ticket no puede desatarlo de su contrato.
    #:
    #: 🔴 **Y su ausencia acá FUE el defecto.** La revisión `0027` las guardaba
    #: y `_to_dict()` las devolvía, pero este `response_model` las descartaba
    #: **en silencio** — FastAPI filtra la respuesta por el modelo de salida. La
    #: suite entera pasaba mientras la pantalla no tenía cómo saber que un
    #: ticket era una visita. Lo destapó ejercitar el circuito contra dev.
    contrato_id: int | None = None
    periodo_visita: str | None = None
    es_visita_mantenimiento: bool = False


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


# ── El camino a facturación ──────────────────────────────────────────────
#
# Un reclamo no se manda a facturar: se convierte en remito, y el remito es lo
# único que la bandeja acepta (ver `app/routers/facturacion.py`). El endpoint
# es el gemelo de `POST /api/presupuestos/{id}/convertir-en-remito`, con el
# mismo nombre a propósito.
#
# Son dos rutas y **una sola implementación**: la de a uno llama a la de a
# varios con una lista de un elemento. Dos caminos que arman un remito habrían
# podido divergir en qué lleva la línea o en qué se valida, que es exactamente
# como este producto terminó con el mismo defecto en tres pantallas.


class ConvertirLote(BaseModel):
    #: Los reclamos que entran al mismo remito. Todos del mismo cliente y todos
    #: cerrados; el servicio explica por qué.
    incidencia_ids: list[int] = Field(min_length=1)


class SalidaIn(BaseModel):
    """Una salida de cuadrilla: varios reclamos encadenados desde una hora."""

    #: 🔑 **El orden es el orden del recorrido.** Quien arma la salida sabe por
    #: dónde conviene arrancar; reordenar acá le cambiaría la ruta sin decírselo.
    incidencia_ids: list[int] = Field(min_length=1)
    #: La cuadrilla. Elegirla ya elige el vehículo y los técnicos: eso vive en
    #: `vehiculos.equipo_id` y en `equipos_trabajo_integrantes`, no acá.
    equipo_trabajo_id: int
    #: Fecha y hora de la primera parada.
    inicio: datetime
    #: Cuánto dura cada parada. Sin esto, la hora que trae `agenda.py`.
    duracion_minutos: int | None = None
    #: Entre que termina una parada y arranca la siguiente. En cero por defecto:
    #: una cuadrilla que atiende dos pisos del mismo edificio no viaja.
    traslado_minutos: int = 0


def _convertir(incidencias, ids, remitos, clientes, servicios, user):
    """El manejo de errores, que es igual para las dos rutas."""
    try:
        return incidencias.convertir_a_remito(
            ids, remitos, clientes, servicios, int(user["id"]),
        )
    except KeyError as e:
        faltan = e.args[0]
        if isinstance(faltan, tuple):
            cuales = ", ".join(f"#{x}" for x in faltan)
            raise HTTPException(404, f"No existen los reclamos {cuales}.")
        raise HTTPException(404, "incidencia not found")
    except ValueError as e:
        # 409 y no 422: el pedido está bien formado, es el estado de los
        # reclamos el que no lo permite todavía. Es el mismo código que usa la
        # conversión de un presupuesto rechazado.
        raise HTTPException(409, str(e))


@router.post("/agendar-salida", status_code=200)
def agendar_salida(
    data: SalidaIn,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
):
    """Varios reclamos a una cuadrilla, en un solo gesto.

    Antes había que abrir cada ticket y agendarlo de a uno, calculando los
    horarios a mano. Acá se elige la cuadrilla, el día, la hora de arranque y
    cuánto dura cada parada, y el sistema las encadena.

    **Todo o nada**: si alguna parada se pisa con lo que la cuadrilla ya tiene
    —o con otra del mismo bloque—, no se agenda ninguna. Con N llamadas sueltas,
    un choque en la cuarta dejaría tres agendadas y dos no.
    """
    try:
        return incidencias.agendar_varias(
            data.incidencia_ids,
            equipo_trabajo_id=data.equipo_trabajo_id,
            inicio=data.inicio,
            duracion_minutos=data.duracion_minutos,
            traslado_minutos=data.traslado_minutos,
        )
    except KeyError as e:
        raise HTTPException(404, f"No existe el id {e.args[0]}")
    except ValueError as e:
        # 409 y no 422: el pedido está bien formado — lo que no da es el estado
        # de la agenda o de los reclamos. Mismo criterio que el resto del router.
        raise HTTPException(409, str(e))


# Antes de `/{incidencia_id}/…`: FastAPI matchea en orden de declaración y esta
# ruta literal tiene un segmento menos, así que en realidad no compiten — pero
# declararla arriba deja la de a varios a la vista de quien lee el archivo
# buscando la de a uno.
@router.post("/convertir-en-remito", status_code=201)
def convertir_lote_en_remito(
    data: ConvertirLote,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
    remitos: RemitoService = Depends(get_remito_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
    servicios: ServicioRepository = Depends(get_servicio_repository),
    user: dict = Depends(get_current_user),
):
    """**Un** remito por los reclamos elegidos, para facturarlos juntos.

    El caso real: a un cliente se le hicieron tres visitas en el mes y se le
    emite una sola factura. Cada reclamo es su propia línea, encabezada por el
    N° CDS del comprobante que firmó, para poder conciliar renglón por renglón
    contra los papeles.
    """
    return _convertir(
        incidencias, data.incidencia_ids, remitos, clientes, servicios, user,
    )


@router.post("/{incidencia_id}/convertir-en-remito", status_code=201)
def convertir_en_remito(
    incidencia_id: int,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
    remitos: RemitoService = Depends(get_remito_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
    servicios: ServicioRepository = Depends(get_servicio_repository),
    user: dict = Depends(get_current_user),
):
    """El remito del trabajo hecho. Idempotente: devuelve el que ya existe.

    `201` también cuando devuelve uno anterior, igual que el de presupuestos:
    lo que el llamador pidió —"que exista el remito de esto"— se cumplió, y
    distinguir los dos casos por el status invitaría a tratar un doble click
    como un error.
    """
    return _convertir(
        incidencias, [incidencia_id], remitos, clientes, servicios, user,
    )


# ── Los cargos de mano de obra ────────────────────────────────────────────


class CargoIn(BaseModel):
    #: El item del catalogo que se cobra. **No es un enum**: hora normal, hora
    #: fuera de horario, viatico y traslado son items del catalogo, asi que
    #: sumar un tipo nuevo no toca este archivo ni ninguna migracion.
    item_id: int
    cantidad: float = Field(gt=0)


@router.get("/{incidencia_id}/cargos")
def listar_cargos(
    incidencia_id: int,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
):
    """Los cargos del reclamo, con el precio **ya resuelto** por la lista de su
    cliente: es el mismo con el que van a salir en el remito.

    Resolverlo aca y no en la pantalla es lo que evita que la ficha muestre un
    numero y el comprobante otro.
    """
    return incidencias.list_cargos(incidencia_id)


@router.post("/{incidencia_id}/cargos", status_code=201)
def agregar_cargo(
    incidencia_id: int, payload: CargoIn,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
):
    try:
        return incidencias.add_cargo(
            incidencia_id, payload.item_id, payload.cantidad,
        )
    except KeyError:
        raise HTTPException(404, "La incidencia no existe.")
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/{incidencia_id}/cargos/{cargo_id}", status_code=204)
def quitar_cargo(
    incidencia_id: int, cargo_id: int,
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
):
    try:
        incidencias.delete_cargo(cargo_id)
    except KeyError:
        raise HTTPException(404, "El cargo no existe.")
    return Response(status_code=204)
