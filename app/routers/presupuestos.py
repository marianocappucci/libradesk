"""Presupuestos. Mismo criterio que `remitos.py`: el dominio vive en
`libracore.db.remitos_presupuestos` y aca solo esta el contrato HTTP.

Dos cosas propias de presupuestos:

- **El vencimiento es automatico.** Los listados, la busqueda y el conteo por
  estado de LibraCore corren `auto_vencimiento_presupuestos()` antes de leer,
  asi que un `enviado` con `valid_until` pasado ya sale `vencido` sin tarea
  programada. No hay nada que agendar.
- **Convertir a remito es idempotente**: si ya se convirtio, devuelve el
  remito existente en vez de emitir un segundo remito por el mismo trabajo.
"""
from datetime import date as date_type
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from libracore import pdf_generator
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..dependencies import (
    get_cliente_repository,
    get_data_dir,
    get_presupuesto_service,
    get_remito_service,
)
from ..services.clientes import ClienteRepository
from ..services.remitos_presupuestos import (
    ESTADOS_PRESUPUESTO,
    PresupuestoService,
    RemitoService,
    datos_cliente_para_comprobante,
)

router = APIRouter(prefix="/api/presupuestos", tags=["presupuestos"])

_VALIDEZ_DEFAULT_DIAS = 30


class ItemIn(BaseModel):
    description: str = Field(min_length=1)
    qty: float = Field(gt=0)
    unit_price: float = Field(ge=0)
    # La alicuota de ESTA linea. `None` = se usa la del documento, que es como
    # se comportaba todo antes de 2026-08-05 y lo que mandan los comprobantes
    # ya guardados al editarse.
    tax_rate: float | None = Field(default=None, ge=0, le=1)


def _valid_until_default() -> date_type:
    return date_type.today() + timedelta(days=_VALIDEZ_DEFAULT_DIAS)


class PresupuestoIn(BaseModel):
    client_id: int
    date: date_type = Field(default_factory=date_type.today)
    valid_until: date_type = Field(default_factory=_valid_until_default)
    status: str = "borrador"
    client_cuit: str = ""
    client_address: str | None = None
    items: list[ItemIn] = Field(min_length=1)
    tax_rate: float = Field(default=0.21, ge=0, le=1)
    observations: str = ""


class EstadoIn(BaseModel):
    status: str


def _datos_cliente(client_id: int, clientes: ClienteRepository, override_address: str | None) -> dict:
    """El 404 es lo unico propio del router; el mapeo vive en el servicio."""
    cliente = clientes.get(client_id)
    if cliente is None:
        raise HTTPException(404, "cliente not found")
    return datos_cliente_para_comprobante(cliente, override_address)


def _validar_estado(status: str) -> None:
    if status not in ESTADOS_PRESUPUESTO:
        raise HTTPException(422, f"estado invalido: {status}")


@router.post("", status_code=201)
def create_presupuesto(
    data: PresupuestoIn,
    presupuestos: PresupuestoService = Depends(get_presupuesto_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
    user: dict = Depends(get_current_user),
):
    _validar_estado(data.status)
    return presupuestos.create(
        date=data.date.isoformat(),
        valid_until=data.valid_until.isoformat(),
        status=data.status,
        client_id=data.client_id,
        client_cuit=data.client_cuit,
        items=[i.model_dump() for i in data.items],
        tax_rate=data.tax_rate,
        observations=data.observations,
        usuario_id=int(user["id"]),
        **_datos_cliente(data.client_id, clientes, data.client_address),
    )


@router.get("")
def list_presupuestos(
    q: str | None = None,
    estado: str | None = None,
    client_id: int | None = None,
    limit: int = 100,
    presupuestos: PresupuestoService = Depends(get_presupuesto_service),
):
    if estado:
        _validar_estado(estado)
    if q:
        return presupuestos.search(q, estado)
    if client_id is not None:
        return presupuestos.by_client(client_id)
    return presupuestos.list(limit, estado)


# Ambas antes de /{presupuesto_id}, que parsea int (ver remitos.py).
@router.get("/next-number")
def next_number(presupuestos: PresupuestoService = Depends(get_presupuesto_service)):
    return {"number": presupuestos.next_number()}


@router.get("/resumen")
def resumen(presupuestos: PresupuestoService = Depends(get_presupuesto_service)):
    """Conteo por estado. Dispara el vencimiento automatico, asi que los
    numeros ya reflejan los que acaban de vencer."""
    conteos = presupuestos.counts_by_estado()
    return {estado: conteos.get(estado, 0) for estado in ESTADOS_PRESUPUESTO}


@router.get("/{presupuesto_id}")
def get_presupuesto(
    presupuesto_id: int,
    presupuestos: PresupuestoService = Depends(get_presupuesto_service),
):
    presupuesto = presupuestos.get(presupuesto_id)
    if presupuesto is None:
        raise HTTPException(404, "presupuesto not found")
    return presupuesto


@router.put("/{presupuesto_id}")
def update_presupuesto(
    presupuesto_id: int,
    data: PresupuestoIn,
    presupuestos: PresupuestoService = Depends(get_presupuesto_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
):
    _validar_estado(data.status)
    try:
        return presupuestos.update(
            presupuesto_id,
            date=data.date.isoformat(),
            valid_until=data.valid_until.isoformat(),
            status=data.status,
            client_id=data.client_id,
            client_cuit=data.client_cuit,
            items=[i.model_dump() for i in data.items],
            tax_rate=data.tax_rate,
            observations=data.observations,
            **_datos_cliente(data.client_id, clientes, data.client_address),
        )
    except KeyError:
        raise HTTPException(404, "presupuesto not found")


@router.patch("/{presupuesto_id}/estado")
def cambiar_estado(
    presupuesto_id: int,
    data: EstadoIn,
    presupuestos: PresupuestoService = Depends(get_presupuesto_service),
):
    _validar_estado(data.status)
    try:
        return presupuestos.set_status(presupuesto_id, data.status)
    except KeyError:
        raise HTTPException(404, "presupuesto not found")


@router.post("/{presupuesto_id}/convertir-en-remito", status_code=201)
def convertir_en_remito(
    presupuesto_id: int,
    presupuestos: PresupuestoService = Depends(get_presupuesto_service),
    remitos: RemitoService = Depends(get_remito_service),
    user: dict = Depends(get_current_user),
):
    try:
        return presupuestos.convertir_a_remito(presupuesto_id, remitos, int(user["id"]))
    except KeyError:
        raise HTTPException(404, "presupuesto not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/{presupuesto_id}", status_code=204)
def delete_presupuesto(
    presupuesto_id: int,
    presupuestos: PresupuestoService = Depends(get_presupuesto_service),
):
    try:
        presupuestos.delete(presupuesto_id)
    except KeyError:
        raise HTTPException(404, "presupuesto not found")
    except ValueError as e:
        # LibraCore solo deja borrar un presupuesto en borrador.
        raise HTTPException(409, str(e))
    return Response(status_code=204)


@router.get("/{presupuesto_id}/pdf")
def presupuesto_pdf(
    presupuesto_id: int,
    presupuestos: PresupuestoService = Depends(get_presupuesto_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
    data_dir: str = Depends(get_data_dir),
):
    presupuesto = presupuestos.get(presupuesto_id)
    if presupuesto is None:
        raise HTTPException(404, "presupuesto not found")
    # La condicion del receptor decide si el PDF discrimina el IVA o muestra el
    # precio final (LibraCore v1.13.0).
    #
    # Se lee del cliente **al generar el PDF**, no se copia al comprobante: es
    # un dato del cliente, y si una condicion mal cargada se corrige, el PDF
    # tiene que salir bien la proxima vez sin tocar los presupuestos emitidos.
    #
    # Un presupuesto sin cliente —o de un cliente borrado— cae a precio final,
    # el mismo default que una condicion vacia.
    cliente = (
        clientes.get(presupuesto["client_id"]) if presupuesto.get("client_id") else None
    )
    path = pdf_generator.generate_pdf_presupuesto(
        presupuesto, output_dir=f"{data_dir}/presupuestos_pdf",
        discriminar=bool(cliente and cliente["iva_discriminado"]),
    )
    presupuestos.set_pdf_path(presupuesto_id, path)
    return FileResponse(
        path, media_type="application/pdf",
        filename=f"presupuesto_{presupuesto['number']}.pdf",
    )
