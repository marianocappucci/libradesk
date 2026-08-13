#!/usr/bin/env python3
"""
Onboarding de nuevo cliente LibraDesk.
Uso: python3 scripts/nuevo_cliente.py

Wrapper de configuración sobre `libracore.provisioning.nuevo_cliente` (lógica
compartida con los otros cinco productos — ver wiki/entities/libracore.md).
Solo fija las constantes propias de LibraDesk; la lógica real vive en LibraCore.

Agregado el 2026-08-02 al normalizar los seis productos: LibraDesk desplegaba
instancias con `scripts/deploy_cliente.sh` y era el único que su backoffice no
podía administrar igual que al resto.

> `deploy_cliente.sh` **no se borra**: sigue siendo la vía para repinear la
> imagen de una instancia existente, que es lo que hace y que este script no
> reemplaza. Lo que agrega esto es el alta, el plan y el ciclo de vida.
"""
from pathlib import Path

from libracore.provisioning import configure
from libracore.provisioning.nuevo_cliente import (
    ClienteError, ask, build_image, crear_cliente, image_exists, main,
    network_exists, next_port, slugify, used_ports,
)

REPO_ROOT = Path(__file__).parent.parent.resolve()

configure(
    # `health_path` **no se pasa**, y esa ausencia es el cambio: desde el
    # 2026-08-12 este producto sirve su salud en `/health`, que es el default
    # del motor y la ruta de los otros cinco. Hasta esa fecha había acá un
    # `health_path="/api/health"` porque LibraDesk era el único que la servía
    # bajo el prefijo de su API, y sin ese argumento toda instancia nueva nacía
    # con el healthcheck apuntado a una ruta que este producto no tenía. Se
    # normalizó el desvío en vez de seguir parametrizándolo — ver
    # `app/routers/health.py`.
    #
    # Que la ruta efectiva sea una que el router realmente sirve lo verifica
    # `tests/test_healthcheck_contenedor.py`, contra ESTE archivo y contra
    # `panel_admin.py` por separado: son dos llamadas a un `configure()` que
    # pisa un `_cfg` GLOBAL, y `libracore.admin.services` importa los dos en el
    # mismo proceso (`_nc()` y `_pa()`), así que gana el último import. Con las
    # dos en el default no hay nada que desincronizar; el test es lo que impide
    # que vuelvan a separarse.
    postgres=True,
    product_name="LIBRADESK",
    image_name="libradesk:latest",
    container_prefix="libradesk",
    db_filename="libradesk.db",
    repo_root=REPO_ROOT,
    # 8069-8088 ya están ocupados por el resto del ecosistema (verificado
    # contra `docker ps` real al desplegar libradesk-web en el 8088).
    base_port=8089,
)

# Re-exportados por compatibilidad con cualquier uso directo de este módulo.
CLIENTES_DIR = REPO_ROOT / "clientes"

if __name__ == "__main__":
    main()
