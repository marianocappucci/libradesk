"""
Cliente para la API REST de Nginx Proxy Manager (NPM).
Documentación NPM API: http://<npm-host>:81/api/

Config leída desde scripts/.npm_config.json (generado por npm_setup.py, y
excluido del repo: tiene credenciales).

Wrapper de configuración sobre libracore.npm_api (lógica compartida con los
otros cinco productos — ver wiki/entities/libracore.md).

Agregado el 2026-08-02 al portar LibraDesk al provisioning de la familia.
`libracore.provisioning.client_from_config()` hace `import npm_api` a secas, así
que sin este archivo devuelve `None` en silencio y el alta de un cliente
terminaría sin crear su dominio.
"""
from pathlib import Path

from libracore.npm_api import (
    NPMClient,
    NPMError,
    client_from_config,
    configure,
    forward_host_from_config,
    le_email_from_config,
    load_config,
    save_config,
)

CONFIG_FILE = Path(__file__).parent / ".npm_config.json"
configure(config_file=CONFIG_FILE)
