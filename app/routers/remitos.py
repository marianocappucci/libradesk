"""Remitos. El dominio es de `libracore.db.remitos_presupuestos` (ver
`app/services/remitos_presupuestos.py`); aca solo va el contrato HTTP.

Los datos del cliente se derivan del `clientes` real de LibraDesk en vez de
confiar en lo que manda el front — eso valida que el cliente exista, que es
la integridad que se pierde al no poder declarar la FK (ver el docstring del
service). `client_cuit` y `client_address` si vienen del formulario: la tabla
`clientes` de LibraDesk no tiene CUIT y su unico campo de ubicacion es
`ciudad`, que no es un domicilio.
"""
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from libracore import pdf_generator
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..dependencies import (
    get_cliente_repository,
    get_data_dir,
    get_incidencia_repository,
    get_remito_service,
)
from ..services.clientes import ClienteRepository
from ..services.incidencias import IncidenciaRepository
from ..services.remitos_presupuestos import (
    RemitoService,
    comprobante_para_pdf,
    datos_cliente_para_comprobante,
)

router = APIRouter(prefix="/api/remitos", tags=["remitos"])


class ItemIn(BaseModel):
    description: str = Field(min_length=1)
    qty: float = Field(gt=0)
    unit_price: float = Field(ge=0)
    # La alicuota de ESTA linea. `None` = se usa la del documento.
    tax_rate: float | None = Field(default=None, ge=0, le=1)

    # Aclaracion corta de ESTE renglon, opcional. Se imprime debajo del nombre
    # del item, mas chica y mas clara (`pdf_generator._draw_items_table`). No es
    # `observations`, que es una sola y describe el comprobante entero.
    detalle: str = ""
    # La moneda de ESTE renglon (2026-09-09). `ARS` por default: un payload que
    # no la manda se comporta igual que antes de que la moneda existiera. Un
    # renglon en `USD` se convierte a pesos con la `cotizacion` del comprobante
    # y **falla si no hay ninguna** -- ver
    # `remitos_presupuestos._normalizar_items`.
    moneda: str = "ARS"

    # 🔴 **Las dos claves que devuelve el servidor, aceptadas de vuelta.** Sin
    # esto Pydantic las descarta al reenviar el item --que es lo que hace la
    # pantalla al editar-- y el renglon en dolares se vuelve a convertir desde
    # un `unit_price` que YA esta en pesos. Se descubrio con un test que hacia
    # el round-trip por HTTP; el que llamaba a `_normalizar_items` directo daba
    # verde igual, porque no pasaba por el modelo.
    #
    # `unit_price_origen` es el precio en dolares tal como se tipeo y
    # `cotizacion` la que se congelo para ESE renglon. Cuando vienen, mandan
    # sobre la del documento.
    unit_price_origen: float | None = Field(default=None, ge=0)
    cotizacion: float | None = Field(default=None, gt=0)


class RemitoIn(BaseModel):
    client_id: int
    date: date_type = Field(default_factory=date_type.today)
    client_cuit: str = ""
    client_address: str | None = None
    items: list[ItemIn] = Field(min_length=1)
    tax_rate: float = Field(default=0.21, ge=0, le=1)
    observations: str = ""
    # Pesos por dolar, para los renglones en `USD`. Va a nivel documento porque
    # la pre-factura se arma con UNA cotizacion; se congela renglon por renglon
    # al guardar, asi que corregirla despues no le mueve el total a lo emitido.
    cotizacion: float | None = Field(default=None, gt=0)
    #: Los reclamos cerrados que este remito factura (2026-09-09).
    #:
    #: 🔴 **No es informativo: es lo que impide el doble cobro.** Al crear, el
    #: remito los ata con `incidencias.remito_id`, y un reclamo atado deja de
    #: ofrecerse en el selector y no se puede volver a facturar. Sin esta lista
    #: los renglones que trae "Nuevo remito" serian texto suelto, y el mismo
    #: trabajo podria entrar en dos comprobantes.
    #:
    #: Vacia en un remito que no sale de reclamos --uno tipeado a mano-- que es
    #: como se comportaba todo antes de que esto existiera.
    incidencia_ids: list[int] = Field(default_factory=list)


def _datos_cliente(client_id: int, clientes: ClienteRepository, override_address: str | None) -> dict:
    """El 404 es lo unico propio del router; el mapeo vive en el servicio."""
    cliente = clientes.get(client_id)
    if cliente is None:
        raise HTTPException(404, "cliente not found")
    return datos_cliente_para_comprobante(cliente, override_address)


@router.post("", status_code=201)
def create_remito(
    data: RemitoIn,
    remitos: RemitoService = Depends(get_remito_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
    incidencias: IncidenciaRepository = Depends(get_incidencia_repository),
    user: dict = Depends(get_current_user),
):
    # 422 y no 409: un renglon en dolares sin cotizacion es un payload que no se
    # puede procesar, no un conflicto con el estado. (`contratos.py` usa 409
    # para sus `ValueError`, que si son conflictos de estado.)
    try:
        remito = remitos.create(
            date=data.date.isoformat(),
            client_id=data.client_id,
            client_cuit=data.client_cuit,
            items=[i.model_dump() for i in data.items],
            tax_rate=data.tax_rate,
            cotizacion=data.cotizacion,
            observations=data.observations,
            # libraauth devuelve el id como str; la columna es INTEGER y SQLite
            # lo convertiria por afinidad, pero se explicita en vez de confiar.
            usuario_id=int(user["id"]),
            **_datos_cliente(data.client_id, clientes, data.client_address),
        )
    except ValueError as e:
        raise HTTPException(422, str(e))

    # 🔴 **El vinculo va DESPUES de crear, y no antes.** Mismo orden y mismo
    # motivo que `convertir_a_remito()`: si el proceso muere en el medio queda
    # un remito sin vinculo --que se puede rehacer-- y no un reclamo diciendo
    # "ya se remito" contra un remito que no existe, que lo dejaria sin poder
    # facturarse nunca.
    if data.incidencia_ids:
        incidencias.vincular_al_remito(data.incidencia_ids, remito["id"])
    return remito


@router.get("")
def list_remitos(
    q: str | None = None,
    client_id: int | None = None,
    limit: int = 100,
    remitos: RemitoService = Depends(get_remito_service),
):
    if q:
        return remitos.search(q)
    if client_id is not None:
        return remitos.by_client(client_id)
    return remitos.list(limit)


# Antes de /{remito_id}: FastAPI matchea por orden de declaracion y
# "next-number" no parsea como int (daria 422).
@router.get("/next-number")
def next_number(remitos: RemitoService = Depends(get_remito_service)):
    return {"number": remitos.next_number()}


@router.get("/{remito_id}")
def get_remito(remito_id: int, remitos: RemitoService = Depends(get_remito_service)):
    remito = remitos.get(remito_id)
    if remito is None:
        raise HTTPException(404, "remito not found")
    return remito


@router.put("/{remito_id}")
def update_remito(
    remito_id: int,
    data: RemitoIn,
    remitos: RemitoService = Depends(get_remito_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    try:
        return remitos.update(
            remito_id,
            date=data.date.isoformat(),
            client_id=data.client_id,
            client_cuit=data.client_cuit,
            items=[i.model_dump() for i in data.items],
            tax_rate=data.tax_rate,
            cotizacion=data.cotizacion,
            observations=data.observations,
            **_datos_cliente(data.client_id, clientes, data.client_address),
        )
    except KeyError:
        raise HTTPException(404, "remito not found")
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/{remito_id}", status_code=204)
def delete_remito(remito_id: int, remitos: RemitoService = Depends(get_remito_service)):
    try:
        remitos.delete(remito_id)
    except KeyError:
        raise HTTPException(404, "remito not found")
    except ValueError as e:
        # `RemitoService.delete()` se niega si algo lo referencia. Sin este
        # `except` el ValueError salia como **500**: la defensa funcionaba y la
        # pantalla mostraba un error del servidor, que manda a mirar los logs
        # en vez de decir por que no se puede borrar. Se descubrio al sumar el
        # segundo origen (incidencias, 2026-08-13); valia igual para el
        # primero.
        colgando = e.args[0] if e.args and isinstance(e.args[0], dict) else {}
        partes = []
        if colgando.get("presupuestos_convertidos"):
            partes.append(f"{colgando['presupuestos_convertidos']} presupuesto/s")
        if colgando.get("incidencias_convertidas"):
            partes.append(f"{colgando['incidencias_convertidas']} reclamo/s")
        detalle = " y ".join(partes) or "otros comprobantes"
        raise HTTPException(
            409,
            f"No se puede borrar este remito: lo generaron {detalle}. "
            f"Borralo desde ahi o desvincula primero.",
        )
    return Response(status_code=204)


@router.get("/{remito_id}/pdf")
def remito_pdf(
    remito_id: int,
    remitos: RemitoService = Depends(get_remito_service),
    data_dir: str = Depends(get_data_dir),
):
    """PDF via `libracore.pdf_generator.generate_pdf` (RemitoPDF), el mismo
    que emiten Contalibra y Restolibra. `output_dir` se pasa explicito: el
    `PDF_DIR` del modulo se congela al importarse y no seguiria al DATA_DIR
    de esta instancia."""
    remito = remitos.get(remito_id)
    if remito is None:
        raise HTTPException(404, "remito not found")
    # `comprobante_para_pdf` le agrega a cada renglon en dolares su conversion
    # (`USD 100,00 x $1.450,50`) en el `detalle`, que el PDF del motor ya
    # imprime. Devuelve una copia: lo guardado no se toca para dibujar.
    path = pdf_generator.generate_pdf(
        comprobante_para_pdf(remito), output_dir=f"{data_dir}/remitos_pdf",
    )
    remitos.set_pdf_path(remito_id, path)
    return FileResponse(
        path, media_type="application/pdf",
        filename=f"remito_{remito['number']}.pdf",
    )
