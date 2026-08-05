"""Ingresos a reparación y sus dos comprobantes (pedido 43).

Ver `app/services/ingresos.py` para por qué es **una fila por episodio de
custodia** y no dos comprobantes enlazados.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..auth import get_current_user
from ..dependencies import get_ingreso_repository
from ..services import ingreso_pdf
from ..services.ingresos import IngresoRepository

router = APIRouter(prefix="/api/ingresos-reparacion", tags=["ingresos"])


class IngresoIn(BaseModel):
    cliente_id: int
    # Opcional a propósito: la notebook que trae un cliente de mostrador no está
    # en su inventario. Si viene, los cuatro campos del equipo se completan de
    # ahí **una sola vez**, al recibir — ver el docstring del service.
    equipo_id: int | None = None
    equipo_tipo: str | None = None
    equipo_marca: str | None = None
    equipo_modelo: str | None = None
    equipo_serial: str | None = None
    fecha_recepcion: datetime | None = None
    contacto: str | None = None
    contacto_telefono: str | None = None
    accesorios: str | None = None
    estado_fisico: str | None = None
    falla_declarada: str | None = None
    observaciones: str | None = None
    tecnico_id: int | None = None
    entregado_por: str | None = None
    incidencia_id: int | None = None


class EntregaIn(BaseModel):
    fecha_entrega: datetime | None = None
    retirado_por: str | None = None
    trabajo_realizado: str | None = None
    observaciones_entrega: str | None = None
    tecnico_entrega_id: int | None = None


@router.post("", status_code=201)
def recibir(
    data: IngresoIn,
    ingresos: IngresoRepository = Depends(get_ingreso_repository),
    user: dict = Depends(get_current_user),
):
    """Recibe el equipo y emite el comprobante de recepción."""
    try:
        return ingresos.create(usuario_actor=user["username"], **data.model_dump())
    except KeyError:
        raise HTTPException(404, "equipo not found")
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("")
def listar(
    cliente_id: int | None = None,
    incidencia_id: int | None = None,
    en_taller: bool | None = None,
    ingresos: IngresoRepository = Depends(get_ingreso_repository),
):
    return ingresos.list(
        cliente_id=cliente_id, incidencia_id=incidencia_id, en_taller=en_taller,
    )


@router.get("/{ingreso_id}")
def obtener(
    ingreso_id: int,
    ingresos: IngresoRepository = Depends(get_ingreso_repository),
):
    ingreso = ingresos.get(ingreso_id)
    if ingreso is None:
        raise HTTPException(404, "ingreso not found")
    return ingreso


@router.get("/{ingreso_id}/pdf/{tipo}")
def comprobante_pdf(
    ingreso_id: int, tipo: str,
    ingresos: IngresoRepository = Depends(get_ingreso_repository),
):
    """El comprobante en PDF. `tipo` es `recepcion` o `entrega`.

    `inline` y no `attachment`, igual que la orden de trabajo: lo normal es
    mirarlo y mandarlo a la impresora para dárselo al cliente en el mostrador.
    """
    if tipo not in ("recepcion", "entrega"):
        raise HTTPException(404, "tipo de comprobante desconocido")
    try:
        datos = ingresos.datos_para_pdf(ingreso_id, tipo=tipo)
    except ValueError as e:
        raise HTTPException(409, str(e))
    if datos is None:
        raise HTTPException(404, "ingreso not found")
    numero = datos["numero_entrega"] if tipo == "entrega" else datos["numero"]
    return Response(
        content=ingreso_pdf.generar_pdf_ingreso(datos, tipo=tipo),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{numero}.pdf"'},
    )


@router.put("/{ingreso_id}")
def corregir(
    ingreso_id: int, data: IngresoIn,
    ingresos: IngresoRepository = Depends(get_ingreso_repository),
    user: dict = Depends(get_current_user),
):
    """Corrige la recepción. **No** puede tocar la entrega: para eso está
    `/entregar`, que es el único que emite el segundo número."""
    try:
        return ingresos.update(
            ingreso_id, usuario_actor=user["username"],
            **{k: v for k, v in data.model_dump().items() if k != "equipo_id"},
        )
    except KeyError:
        raise HTTPException(404, "ingreso not found")
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/{ingreso_id}/entregar")
def entregar(
    ingreso_id: int, data: EntregaIn,
    ingresos: IngresoRepository = Depends(get_ingreso_repository),
    user: dict = Depends(get_current_user),
):
    """Devuelve el equipo al cliente y emite el comprobante de entrega."""
    try:
        return ingresos.entregar(
            ingreso_id, usuario_actor=user["username"], **data.model_dump(),
        )
    except KeyError:
        raise HTTPException(404, "ingreso not found")
    except ValueError as e:
        # 409 y no 422: el cuerpo está bien, lo que no se puede es entregar dos
        # veces lo mismo.
        raise HTTPException(409, str(e))


@router.delete("/{ingreso_id}", status_code=204)
def borrar(
    ingreso_id: int,
    ingresos: IngresoRepository = Depends(get_ingreso_repository),
):
    try:
        ingresos.delete(ingreso_id)
    except KeyError:
        raise HTTPException(404, "ingreso not found")
    except ValueError as e:
        raise HTTPException(409, str(e))
    return Response(status_code=204)
