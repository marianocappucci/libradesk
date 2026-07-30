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
    get_cliente_repository, get_data_dir, get_remito_service,
)
from ..services.clientes import ClienteRepository
from ..services.remitos_presupuestos import RemitoService

router = APIRouter(prefix="/api/remitos", tags=["remitos"])


class ItemIn(BaseModel):
    description: str = Field(min_length=1)
    qty: float = Field(gt=0)
    unit_price: float = Field(ge=0)


class RemitoIn(BaseModel):
    client_id: int
    date: date_type = Field(default_factory=date_type.today)
    client_cuit: str = ""
    client_address: str | None = None
    items: list[ItemIn] = Field(min_length=1)
    tax_rate: float = Field(default=0.21, ge=0, le=1)
    observations: str = ""


def _datos_cliente(client_id: int, clientes: ClienteRepository, override_address: str | None) -> dict:
    cliente = clientes.get(client_id)
    if cliente is None:
        raise HTTPException(404, "cliente not found")
    return {
        "client_name": cliente["empresa"] or cliente["nombre"],
        "client_address": override_address if override_address is not None else (cliente["ciudad"] or ""),
        "client_email": cliente["email"] or "",
        "client_phone": cliente["telefono"] or "",
    }


@router.post("", status_code=201)
def create_remito(
    data: RemitoIn,
    remitos: RemitoService = Depends(get_remito_service),
    clientes: ClienteRepository = Depends(get_cliente_repository),
    user: dict = Depends(get_current_user),
):
    return remitos.create(
        date=data.date.isoformat(),
        client_id=data.client_id,
        client_cuit=data.client_cuit,
        items=[i.model_dump() for i in data.items],
        tax_rate=data.tax_rate,
        observations=data.observations,
        # libraauth devuelve el id como str; la columna es INTEGER y SQLite
        # lo convertiria por afinidad, pero se explicita en vez de confiar.
        usuario_id=int(user["id"]),
        **_datos_cliente(data.client_id, clientes, data.client_address),
    )


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
            observations=data.observations,
            **_datos_cliente(data.client_id, clientes, data.client_address),
        )
    except KeyError:
        raise HTTPException(404, "remito not found")


@router.delete("/{remito_id}", status_code=204)
def delete_remito(remito_id: int, remitos: RemitoService = Depends(get_remito_service)):
    try:
        remitos.delete(remito_id)
    except KeyError:
        raise HTTPException(404, "remito not found")
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
    path = pdf_generator.generate_pdf(remito, output_dir=f"{data_dir}/remitos_pdf")
    remitos.set_pdf_path(remito_id, path)
    return FileResponse(
        path, media_type="application/pdf",
        filename=f"remito_{remito['number']}.pdf",
    )
