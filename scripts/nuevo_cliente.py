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

Ese día quedó escrito acá que `deploy_cliente.sh` **no se borraba**, porque
"seguía siendo la vía para repinear la imagen de una instancia existente".
**Eso dejó de ser cierto el 2026-08-17**: `panel_admin.py actualizar` hace
exactamente eso —y de más: rollback, revertir el pin si el arranque falla,
saltear instancias detenidas sin repinearlas— y desde `libracore v1.39.0`
también construye del ref promovido en un worktree limpio, que era el único
guard que el bash tenía y el módulo compartido no. Así que el bash se retiró y
los seis productos despliegan igual.
"""
from pathlib import Path

from libracore.provisioning import configure
from libracore.provisioning.nuevo_cliente import (
    ClienteError,
    ask,
    build_image,
    crear_cliente,
    image_exists,
    main,
    network_exists,
    next_port,
    slugify,
    used_ports,
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
    # ⚠️ **Tiene que decir lo mismo que `scripts/panel_admin.py`.** Hasta el
    # 2026-08-24 este archivo no pasaba `backup_zip` y el otro sí, que es el
    # único campo en el que los dos `configure()` diferían. Como pisan un `_cfg`
    # GLOBAL y `libracore.admin.services` importa los dos módulos en el mismo
    # proceso, una diferencia acá hace que el resultado dependa del orden de los
    # imports. `tests/test_provisioning.py` lo compara entero con `asdict`.
    #
    # **No estaba mordiendo**: todo camino que hoy lee `cfg.backup_zip` —el
    # `backup-all` del cron de las 03:45, el `backup <slug>` de la CLI y el menú
    # interactivo— entra por `panel_admin.py`, que ya lo tenía en `True`. Se ve
    # en el servidor: las tres instancias vienen armando su
    # `backup_automatico_*.zip` diario en `data/backups/`. Era una mina, no un
    # incendio: el primer `cmd_backup` que se llamara desde el backoffice se
    # habría llevado el camino viejo, en silencio.
    #
    # `True` es el valor correcto, no un empate arbitrario: este producto sirve
    # su pantalla de Backups con el `build_backup_router` de
    # `libracore.respaldo` (ver `app/main.py`), así que el ZIP que arma el cron
    # es exactamente el que el cliente puede listar, bajar y restaurar solo. Sin
    # el flag, el `tar.gz` empaqueta `data/` mientras el dump de PostgreSQL
    # queda **afuera**, en `clientes/<slug>/backups/` — el archivo que parece el
    # backup de la instancia no lo es.
    backup_zip=True,
    # 🔴 **Sin esta línea el deploy no aplica ninguna revisión.** El paso lo
    # trae el motor desde LibraCore `v1.48.0` —`cmd_actualizar` corre estos
    # comandos con `compose run --rm` ANTES del `up -d`, así la migración usa
    # el código nuevo mientras la instancia todavía sirve el viejo— pero el
    # default es vacío, así que un producto que no declara nada no ve ningún
    # paso y su deploy pasa de largo en silencio.
    #
    # Este repo tiene 36 revisiones y no la declaraba. Las bases de producción
    # están al día igual porque alguien las corrió a mano en cada deploy; el
    # defecto es que dependía de que ese alguien se acordara. A LibraCargo se
    # le olvidó el 2026-08-24 y quedó con el código nuevo sobre el esquema
    # viejo: `healthy`, `/salud` en 200, y todo `SELECT` sobre la tabla nueva
    # muriendo.
    #
    # Una sola cadena. Este producto importa de LibraGenda sólo `domain` y
    # `scheduling` —dataclasses congelados y algoritmos, sin persistencia— así
    # que no tiene la `alembic_version` del motor al lado de la propia.
    # Gestiolibra y MedLibra usan `libragenda.sqlalchemy_repository` y por eso
    # declaran `libragenda-migrar upgrade` primero.
    migraciones=(("alembic", "upgrade", "head"),),
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
