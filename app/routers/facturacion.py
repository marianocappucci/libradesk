"""Mandar lo facturable a la instancia de Contalibra del mismo cliente.

Fase B del puente (ver `app/services/facturacion_externa.py` y
`wiki/analyses/libradesk-contalibra-puente-facturacion.md`).

## Sólo se manda el remito

Desde el 2026-08-13 la única fuente es el **remito**: lo que habilita a facturar
es la entrega hecha, y el remito es el documento que la prueba. Un presupuesto
aceptado es una oferta aceptada — todavía no pasó nada que facturar. Los otros
dos orígenes del producto llegan a facturación **convirtiéndose en remito**
primero, no por un camino propio:

- presupuesto aceptado → `POST /api/presupuestos/{id}/convertir-en-remito`
- incidencia cerrada   → `POST /api/incidencias/{id}/convertir-en-remito`

Las dos conversiones son idempotentes y dejan el origen linkeado, así que el
mismo trabajo no puede terminar dos veces en la bandeja. Antes de este cambio sí
podía: el detalle está en el comentario de `ORIGENES_ENVIABLES` en el servicio.

Las cuotas de contrato siguen siendo la fase C y no tienen remito; cuando se
implementen hay que decidir si entran como origen propio o si también generan
uno.

**Ninguna ruta de este módulo emite nada.** Lo peor que puede hacer es dejar una
fila en una bandeja del otro lado, que se descarta con un click.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..dependencies import get_puente_facturacion, get_remito_service
from ..services.facturacion_externa import (
    ORIGEN_REMITO,
    ORIGENES_ENVIABLES,
    EnvioNoConfigurado,
    OrigenNoFacturable,
    PuenteFacturacion,
    destino,
    esta_configurado,
    nombre_destino,
)
from ..services.remitos_presupuestos import RemitoService

router = APIRouter(prefix="/api/facturacion", tags=["facturacion"])

# Cuántos comprobantes se ofrecen para mandar. Es el mismo tope que usa el
# listado de remitos.
_TOPE = 100


class EnviarPayload(BaseModel):
    origen_tipo: str = ORIGEN_REMITO
    ids: list[int] = Field(min_length=1)


def _traer(origen_id: int, remitos: RemitoService) -> dict:
    """El remito, o 404. Valida además que se pueda facturar."""
    comprobante = remitos.get(origen_id)
    if comprobante is None:
        raise HTTPException(404, f"No existe el remito {origen_id}")
    if float(comprobante.get("total") or 0) <= 0:
        # Un remito sin importe no se factura: del otro lado el paso siguiente
        # es emitir con CAE y una factura en cero no existe. El caso real que
        # esto ataja es un remito recién generado desde una incidencia, cuyos
        # materiales todavía no tienen precio cargado — hay que ponérselo y
        # recién ahí mandarlo. Y hace coincidir el envío con el débito en
        # cuenta corriente, que ya saltea los totales en cero.
        raise OrigenNoFacturable(
            f"El remito {comprobante.get('number') or origen_id} tiene total 0: "
            f"cargale los importes antes de mandarlo a facturar."
        )
    return comprobante


@router.get("/estado")
def estado(puente: PuenteFacturacion = Depends(get_puente_facturacion)):
    """Si el puente está configurado, y todo lo que se mandó alguna vez.

    `configurado` es un booleano y **nada más**: la URL y el token no salen por
    la API ni enmascarados. Ver el docstring del servicio.

    Los envíos históricos de tipo `presupuesto` **siguen saliendo por acá**
    aunque ya no se pueda mandar uno nuevo: son lo que se mandó, y esconderlos
    dejaría a la pantalla mintiendo sobre lo que hay del otro lado.
    """
    return {
        "configurado": esta_configurado(),
        "destino": destino(),
        "destino_nombre": nombre_destino(),
        "envios": puente.listar(),
    }


@router.get("/pendientes")
def pendientes(
    puente: PuenteFacturacion = Depends(get_puente_facturacion),
    remitos: RemitoService = Depends(get_remito_service),
):
    """Los remitos que se pueden mandar, con el estado del envío anotado.

    Trae también lo ya enviado, marcado: sin eso la pantalla no puede mostrar
    "esto ya fue" y el usuario lo manda de nuevo para averiguarlo.
    """
    envios_remitos = puente.estados_por_origen(ORIGEN_REMITO)

    filas = [
        {
            "origen_tipo": ORIGEN_REMITO,
            "id": r["id"],
            "numero": r.get("number") or "",
            "fecha": r.get("date") or "",
            "cliente": r.get("client_name") or "",
            "cliente_cuit": r.get("client_cuit") or "",
            "total": float(r.get("total") or 0),
            "envio": envios_remitos.get(r["id"]),
        }
        for r in remitos.list(limit=_TOPE)
    ]
    return {
        "configurado": esta_configurado(),
        "destino": destino(),
        "destino_nombre": nombre_destino(),
        "items": filas,
    }


@router.post("/enviar")
def enviar(
    data: EnviarPayload,
    puente: PuenteFacturacion = Depends(get_puente_facturacion),
    remitos: RemitoService = Depends(get_remito_service),
):
    """Manda los remitos elegidos y devuelve qué pasó con cada uno.

    Devuelve `200` aunque alguno haya fallado: cada ítem trae su propio estado.
    Fallar la request entera por uno dejaría al usuario sin saber cuáles de los
    otros sí llegaron — y como el destino es idempotente, reintentar los que
    fallaron es gratis.
    """
    if data.origen_tipo not in ORIGENES_ENVIABLES:
        # 422 y con el motivo escrito: el que llegue acá con
        # `origen_tipo=presupuesto` es un cliente viejo, y "invalido" a secas lo
        # manda a buscar un typo que no existe.
        raise HTTPException(
            422,
            f"Sólo se manda a facturar un remito, y llegó "
            f"«{data.origen_tipo}». Un presupuesto aceptado se convierte primero "
            f"en remito (POST /api/presupuestos/{{id}}/convertir-en-remito).",
        )
    if not esta_configurado():
        raise HTTPException(
            409,
            f"Esta instancia no tiene configurado el enlace con "
            f"{nombre_destino()}. Se define en el entorno del contenedor al "
            f"contratar los dos sistemas.",
        )

    resultados = []
    for origen_id in data.ids:
        try:
            comprobante = _traer(origen_id, remitos)
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
