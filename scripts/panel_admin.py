#!/usr/bin/env python3
"""
Panel de administración LibraDesk.
Gestiona todos los contenedores de clientes desde un menú interactivo.
Uso: python3 scripts/panel_admin.py [comando] [slug]
     python3 scripts/panel_admin.py           → menú interactivo
     python3 scripts/panel_admin.py listar
     python3 scripts/panel_admin.py backup micliente

Wrapper de configuración sobre `libracore.provisioning.panel_admin` (lógica
compartida con los otros cinco productos — ver wiki/entities/libracore.md).
Solo fija las constantes propias de LibraDesk; la lógica real vive en LibraCore.

Es además lo que consume el backoffice compartido (`libra-backoffice`) a través
de `libracore.admin.services`: sin este archivo, LibraDesk se podía listar pero
no operar.
"""
from pathlib import Path

from libracore.provisioning import (
    client_from_config, configure, forward_host_from_config, le_email_from_config, npm_available,
)
from libracore.provisioning.panel_admin import (
    cli, cmd_activar, cmd_actualizar, cmd_backup, cmd_backup_all, cmd_eliminar,
    cmd_estado_servicio, cmd_info, cmd_list_backups, cmd_listar, cmd_logs, cmd_npm_crear,
    cmd_npm_eliminar, cmd_npm_listar, cmd_pausar, cmd_restart, cmd_restore_db, cmd_start,
    cmd_stop, cmd_suspender, compose, container_status, find_client, interactive,
    load_clients, pick_client, _set_servicio_estado,
)

REPO_ROOT = Path(__file__).parent.parent.resolve()

configure(
    # El backup del cron arma el MISMO ZIP que la pantalla de Backups, en
    # `data/backups/`, en vez de un `tar.gz` aparte que la pantalla no lista
    # y el cliente no puede restaurar. Requiere libracore >= v1.29.0.
    #
    # Este producto puede prenderlo porque su pantalla sale de
    # `libracore.respaldo` (`build_backup_router` en app/main.py). Contalibra
    # y Restolibra tienen implementacion propia y todavia no.
    backup_zip=True,
    # `health_path` tampoco se pasa acá — ver el comentario largo en
    # `nuevo_cliente.py`. Este producto ya sirve su salud en `/health`, el
    # default. Lo que importa es que los dos scripts sigan diciendo lo MISMO:
    # `configure()` pisa un `_cfg` global y `libracore.admin.services` importa
    # los dos en el mismo proceso, así que si uno se desviara del otro, el alta
    # siguiente a un listado saldría con la ruta del que ganó el import.
    postgres=True,
    product_name="LIBRADESK",
    image_name="libradesk:latest",
    container_prefix="libradesk",
    db_filename="libradesk.db",
    repo_root=REPO_ROOT,
    base_port=8089,
)

# Re-exportados por compatibilidad con cualquier uso directo de este módulo.
CLIENTES_DIR = REPO_ROOT / "clientes"
_NPM_AVAILABLE = npm_available()

if __name__ == "__main__":
    cli()
