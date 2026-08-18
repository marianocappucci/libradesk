"""Configurar a dónde manda lo facturable esta instancia.

**Ninguna ruta de este módulo devuelve una credencial**, ni en claro ni
enmascarada: de los campos secretos sale un booleano `<campo>_cargado`. La
máscara con asteriscos se descartó a propósito — filtra el largo, y el largo de
una contraseña ya es información.

Requiere admin, igual que el resto de la configuración.
"""
import httpx
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


class CuitsPayload(BaseModel):
    """Credenciales tipeadas y todavía sin guardar.

    Las dos son opcionales: si vienen vacías se usan las guardadas. Eso es lo
    que hace que el botón funcione tanto antes como después de apretar Guardar
    — que es donde se lo va a apretar, porque el `idcuit` hace falta para poder
    guardar completo.
    """

    usuario: str = ""
    password: str = ""


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


@router.post("/sos/cuits")
def cuits_de_sos(data: CuitsPayload):
    """Las CUITs que ve el usuario de SOS, para elegir el `idcuit` sin salir.

    Existe porque el `idcuit` **no aparece en ninguna pantalla de SOS**: es un
    id interno que sólo devuelve la API. Antes de esto había que sacarlo con un
    script contra la instancia del cliente, que es como se consiguió el de
    Lagrace el 2026-08-18.

    `POST` y no `GET` porque puede llevar una contraseña en el cuerpo, y una
    credencial en la query string queda en el log del proxy y en el historial
    del navegador.

    **No devuelve credenciales** — sólo id, CUIT y razón social. Y sólo lo
    monta este router, que ya exige admin.
    """
    # Import local: el adaptador de SOS no se carga en las instancias que no lo
    # usan, mismo criterio que en `facturacion_externa.esta_configurado`.
    from ..services.facturacion_sos import ErrorSOS, listar_cuits

    try:
        return {"cuits": listar_cuits(data.usuario, data.password)}
    except ErrorSOS as e:
        # 409 y no 502: lo que falla casi siempre es la credencial, y eso lo
        # arregla quien está mirando la pantalla.
        raise HTTPException(409, str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(502, f"No se pudo consultar SOS Contador: {e}") from e


@router.delete("/{destino}/secreto/{campo}")
def borrar_secreto(destino: str, campo: str,
                   config: ConfiguracionFacturacion = Depends(get_config_facturacion)):
    if destino not in DESTINOS:
        raise HTTPException(422, f"destino desconocido: {destino}")
    return config.borrar_secreto(destino, campo)
