"""Mandar lo facturable a la instancia de Contalibra del mismo cliente.

Fase B del puente (ver `app/services/facturacion_externa.py` y
`wiki/analyses/libradesk-contalibra-puente-facturacion.md`). Hoy manda remitos y
presupuestos, que son las dos fuentes que ya tienen importe. Las cuotas de
contrato son la fase C y las incidencias la D — cuando existan, entran por acá
sin tocar la tabla.

**Ninguna ruta de este módulo emite nada.** Lo peor que puede hacer es dejar una
fila en una bandeja del otro lado, que se descarta con un click.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..dependencies import (
    get_presupuesto_service,
    get_puente_facturacion,
    get_remito_service,
)
from ..services.facturacion_externa import (
    ESTADOS_PRESUPUESTO_FACTURABLES,
    ORIGEN_PRESUPUESTO,
    ORIGEN_REMITO,
    ORIGENES,
    EnvioNoConfigurado,
    OrigenNoFacturable,
    PuenteFacturacion,
    esta_configurado,
)
from ..services.remitos_presupuestos import PresupuestoService, RemitoService

router = APIRouter(prefix="/api/facturacion", tags=["facturacion"])

# Cuántos comprobantes se ofrecen para mandar. Es el mismo tope que usan los
# listados de remitos y presupuestos.
_TOPE = 100


class EnviarPayload(BaseModel):
    origen_tipo: str
    ids: list[int] = Field(min_length=1)


def _traer(origen_tipo: str, origen_id: int, remitos: RemitoService,
           presupuestos: PresupuestoService) -> dict:
    """El comprobante, o 404. Valida además que se pueda facturar."""
    if origen_tipo == ORIGEN_REMITO:
        comprobante = remitos.get(origen_id)
        if comprobante is None:
            raise HTTPException(404, f"No existe el remito {origen_id}")
        return comprobante

    comprobante = presupuestos.get(origen_id)
    if comprobante is None:
        raise HTTPException(404, f"No existe el presupuesto {origen_id}")
    if comprobante.get("status") not in ESTADOS_PRESUPUESTO_FACTURABLES:
        # Un presupuesto que el cliente no aceptó no se factura. Del otro lado
        # el paso siguiente es emitir con CAE, así que dejarlo pasar pondría a
        # una persona a un click de facturar algo que nadie aprobó.
        raise OrigenNoFacturable(
            f"El presupuesto {comprobante.get('number') or origen_id} está en "
            f"estado «{comprobante.get('status')}»: sólo se puede facturar uno "
            f"aceptado."
        )
    return comprobante


@router.get("/estado")
def estado(puente: PuenteFacturacion = Depends(get_puente_facturacion)):
    """Si el puente está configurado, y todo lo que se mandó alguna vez.

    `configurado` es un booleano y **nada más**: la URL y el token no salen por
    la API ni enmascarados. Ver el docstring del servicio.
    """
    return {"configurado": esta_configurado(), "envios": puente.listar()}


@router.get("/pendientes")
def pendientes(
    puente: PuenteFacturacion = Depends(get_puente_facturacion),
    remitos: RemitoService = Depends(get_remito_service),
    presupuestos: PresupuestoService = Depends(get_presupuesto_service),
):
    """Lo que se puede mandar, con el estado del envío anotado.

    Trae también lo ya enviado, marcado: sin eso la pantalla no puede mostrar
    "esto ya fue" y el usuario lo manda de nuevo para averiguarlo.
    """
    envios_remitos = puente.estados_por_origen(ORIGEN_REMITO)
    envios_presu = puente.estados_por_origen(ORIGEN_PRESUPUESTO)

    def _fila(origen_tipo, comprobante, envio):
        return {
            "origen_tipo": origen_tipo,
            "id": comprobante["id"],
            "numero": comprobante.get("number") or "",
            "fecha": comprobante.get("date") or "",
            "cliente": comprobante.get("client_name") or "",
            "cliente_cuit": comprobante.get("client_cuit") or "",
            "total": float(comprobante.get("total") or 0),
            "envio": envio,
        }

    filas = [
        _fila(ORIGEN_REMITO, r, envios_remitos.get(r["id"]))
        for r in remitos.list(limit=_TOPE)
    ]
    # Sólo los aceptados: es la misma regla que aplica `_traer`, y ofrecer en
    # la pantalla algo que el envío después rechaza sería una trampa.
    filas += [
        _fila(ORIGEN_PRESUPUESTO, p, envios_presu.get(p["id"]))
        for p in presupuestos.list(limit=_TOPE)
        if p.get("status") in ESTADOS_PRESUPUESTO_FACTURABLES
    ]
    return {"configurado": esta_configurado(), "items": filas}


@router.post("/enviar")
def enviar(
    data: EnviarPayload,
    puente: PuenteFacturacion = Depends(get_puente_facturacion),
    remitos: RemitoService = Depends(get_remito_service),
    presupuestos: PresupuestoService = Depends(get_presupuesto_service),
):
    """Manda los comprobantes elegidos y devuelve qué pasó con cada uno.

    Devuelve `200` aunque alguno haya fallado: cada ítem trae su propio estado.
    Fallar la request entera por uno dejaría al usuario sin saber cuáles de los
    otros sí llegaron — y como el destino es idempotente, reintentar los que
    fallaron es gratis.
    """
    if data.origen_tipo not in ORIGENES:
        raise HTTPException(422, f"origen_tipo invalido: {data.origen_tipo}")
    if not esta_configurado():
        raise HTTPException(
            409,
            "Esta instancia no tiene configurado el enlace con Contalibra. "
            "Se define en el entorno del contenedor al contratar los dos "
            "sistemas.",
        )

    resultados = []
    for origen_id in data.ids:
        try:
            comprobante = _traer(data.origen_tipo, origen_id, remitos, presupuestos)
        except OrigenNoFacturable as e:
            resultados.append({"origen_id": origen_id, "estado": "no_facturable",
                               "detalle": str(e)})
            continue
        try:
            resultados.append(puente.enviar(data.origen_tipo, comprobante))
        except EnvioNoConfigurado as e:
            # No debería llegar acá —arriba se chequea— pero si la variable
            # desaparece entre medio, esto lo dice en vez de dar un 500.
            raise HTTPException(409, str(e))
    return {"resultados": resultados}
