"""Datos de la empresa que encabezan los PDF de remitos y presupuestos.

Reusa `libracore.config_manager` (el mismo `config.json` en DATA_DIR que
usan Contalibra/Restolibra) en vez de una tabla nueva. Se expone solo el
subconjunto `empresa_*` que leen los PDF: `config.json` tambien guarda
tokens de MercadoPago y credenciales SMTP, y esos **no** salen ni entran por
esta API.

Sin esto los PDF salen con el encabezado vacio, porque `config_manager.load()`
devuelve los defaults (strings vacios) cuando no existe el archivo.
"""
from fastapi import APIRouter, Depends
from libracore import config_manager
from pydantic import BaseModel

from ..auth import require_admin

router = APIRouter(prefix="/api/config-empresa", tags=["config-empresa"])

# Unicas claves que esta API lee y escribe. Cualquier otra cosa en
# config.json (mp_*, email_*, ticket_*) queda intacta y fuera de la
# respuesta — `config_manager.save()` mergea sobre lo existente.
_CAMPOS = (
    "empresa_nombre",
    "empresa_direccion",
    "empresa_cuit",
    "empresa_telefono",
    "empresa_email",
    "empresa_iibb",
    "empresa_iva_condition",
    "empresa_inicio_actividades",
)


class ConfigEmpresa(BaseModel):
    empresa_nombre: str = ""
    empresa_direccion: str = ""
    empresa_cuit: str = ""
    empresa_telefono: str = ""
    empresa_email: str = ""
    empresa_iibb: str = ""
    empresa_iva_condition: str = "Monotributista"
    empresa_inicio_actividades: str = ""


@router.get("", response_model=ConfigEmpresa)
def get_config_empresa():
    cfg = config_manager.load()
    return {campo: cfg.get(campo, "") for campo in _CAMPOS}


@router.put("", response_model=ConfigEmpresa, dependencies=[Depends(require_admin)])
def update_config_empresa(data: ConfigEmpresa):
    """Solo admin. `save()` mergea sobre el config.json existente, asi que no
    pisa las claves de MercadoPago/SMTP que esta API no toca."""
    actual = config_manager.load()
    actual.update(data.model_dump())
    config_manager.save(actual)
    cfg = config_manager.load()
    return {campo: cfg.get(campo, "") for campo in _CAMPOS}
