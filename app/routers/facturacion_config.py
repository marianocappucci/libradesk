"""Configurar a dónde manda lo facturable esta instancia.

**Ninguna ruta de este módulo devuelve una credencial**, ni en claro ni
enmascarada: de los campos secretos sale un booleano `<campo>_cargado`. La
máscara con asteriscos se descartó a propósito — filtra el largo, y el largo de
una contraseña ya es información.

Requiere admin, igual que el resto de la configuración.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..dependencies import get_config_facturacion
from ..services.facturacion_config import (
    PARAMETROS,
    ConfiguracionFacturacion,
    SecretoIlegible,
)

router = APIRouter(prefix="/api/facturacion/config", tags=["facturacion"])

DESTINOS = tuple(PARAMETROS)


class ConfigPayload(BaseModel):
    habilitado: bool = False
    # Los campos van sueltos y no tipados uno por uno: el conjunto depende del
    # destino, y el servicio ya filtra lo que no corresponde. Lo que no está en
    # `PARAMETROS`/`SECRETOS` de ese destino se ignora.
    valores: dict[str, str] = Field(default_factory=dict)


@router.get("")
def ver_todo(config: ConfiguracionFacturacion = Depends(get_config_facturacion)):
    """Los dos destinos con su estado. Sin credenciales."""
    return {
        "destinos": [config.ver(d) for d in DESTINOS],
        "habilitados": config.habilitados(),
    }


@router.put("/{destino}")
def guardar(destino: str, data: ConfigPayload,
            config: ConfiguracionFacturacion = Depends(get_config_facturacion)):
    """Guarda un destino y devuelve cómo quedó.

    Un secreto que llega vacío **no se pisa**: la pantalla nunca recibió el
    valor actual, así que mandarlo vacío significa "no lo toqué", no "borralo".
    Para borrarlo de verdad está `DELETE /{destino}/secreto/{campo}`.
    """
    if destino not in DESTINOS:
        raise HTTPException(422, f"destino desconocido: {destino}")
    try:
        return config.guardar(destino, data.habilitado, data.valores)
    except SecretoIlegible as e:
        raise HTTPException(409, str(e)) from e


@router.delete("/{destino}/secreto/{campo}")
def borrar_secreto(destino: str, campo: str,
                   config: ConfiguracionFacturacion = Depends(get_config_facturacion)):
    if destino not in DESTINOS:
        raise HTTPException(422, f"destino desconocido: {destino}")
    return config.borrar_secreto(destino, campo)
