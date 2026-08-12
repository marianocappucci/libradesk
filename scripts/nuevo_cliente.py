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
    # **LibraDesk es el único de los seis que no sirve su salud en `/health`**:
    # `app/routers/health.py` declara `@router.get("/api/health")`. Los otros
    # cinco usan `/health` — Gestiolibra, MedLibra y VentaLibra con este mismo
    # archivo y esta misma forma, sólo que sin el `/api` en el literal.
    #
    # Sin esto, el healthcheck que se le estampa a cada instancia nueva apunta
    # a `/health`, que en este producto lo contesta el catch-all de la SPA con
    # el index.html. Hasta libracore v1.34.0 eso pasaba desapercibido porque el
    # chequeo era un `urlopen()` a secas y cualquier 200 le alcanzaba; desde
    # v1.34.0 hace `json.load` del cuerpo, así que la instancia nueva nacería
    # `unhealthy` para siempre. Medido el 2026-08-12 contra `libradesk-demo`:
    # `/health` da exit 1, `/api/health` da exit 0.
    #
    # Va también en `panel_admin.py`, y no es duplicación decorativa:
    # `configure()` pisa un `_cfg` GLOBAL, y `libracore.admin.services` importa
    # los dos scripts en el mismo proceso (`_pa()` y `_nc()`). Gana el último
    # import. Si sólo lo pusiera acá, un listado posterior a un alta dejaría
    # `_cfg.health_path` de vuelta en `/health` y el próximo alta volvería a
    # generar el compose equivocado.
    health_path="/api/health",
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
