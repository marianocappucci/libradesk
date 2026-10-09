"""La empresa ficticia de la demo pública (ADR-038 de libracore).

En una demo (`DEMO_MODE=1`) el motor nunca muestra los datos de la empresa que
haya en `config.json`: los pisa con la empresa que el producto registre acá.
Es ficticia de punta a punta —CUIT con dígito verificador válido y prefijo
`30-999` que ARCA no asigna, correo en `.example`— y su logo viaja con la
imagen, no con `DATA_DIR`, que es justo lo que se ensucia. Motivo: el
2026-10-09 una demo de la suite mostraba los datos fiscales de un cliente real.

Fuera de una demo, registrar no cambia nada.
"""
from pathlib import Path

from libracore import config_manager

#: El logo de fantasía de un servicio técnico inventado, en `app/assets/`.
LOGO = Path(__file__).parent / "assets" / "logo-empresa-demo.png"

EMPRESA = {
    "empresa_nombre":             "Nexo Soporte IT SRL",
    "empresa_cuit":               "30-99999902-2",
    "empresa_direccion":          "Calle Ejemplo 567, Rosario, Santa Fe",
    "empresa_telefono":           "0341 400-0000",
    "empresa_email":              "soporte@nexosoporte.example",
    "empresa_iibb":               "901-000000-2",
    "empresa_iva_condition":      "Responsable Inscripto",
    "empresa_inicio_actividades": "2018-07-01",
}


def registrar() -> None:
    """Idempotente: se puede llamar en cada arranque."""
    config_manager.usar_empresa_demo(EMPRESA, logo_path=str(LOGO))
