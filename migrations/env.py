"""Alembic environment de LibraDesk.

**El dato que condiciona todo este archivo: en el mismo archivo SQLite
conviven tablas de TRES duenos distintos.**

| Dueno | Tablas | Quien las crea |
|---|---|---|
| LibraDesk | las 9 de `Base` (clientes, equipos, incidencias, ...) | esta cadena de Alembic |
| `libraauth` | `usuarios`, `password_reset_tokens`, `smtp_settings` | `AuthBase.metadata.create_all()` |
| `libracore` | `remitos`, `presupuestos` | `rp_service.ensure_schema()`, sqlite3 crudo |

Un `--autogenerate` con `target_metadata = Base.metadata` y sin filtro ve esas
5 tablas ajenas en la base y no las ve en la metadata, asi que **propone
dropearlas**. Por eso `include_name`: solo pasan las tablas que estan en
`Base.metadata`, y la lista se deriva de la metadata misma en vez de estar
escrita a mano — un modelo nuevo entra solo, y una tabla ajena no puede
colarse. Hay un test que lo fija (`test_alembic.py`).

Gestiolibra resolvio lo mismo al reves, con `target_metadata = None` y todas
las revisiones a mano, porque alla los modelos propios cuelgan de la `Base`
compartida de LibraGenda y no habia forma de separarlos. Aca `Base` es propia
de LibraDesk (app/database.py), asi que el filtro alcanza y el autogenerate
queda utilizable — que era el punto de traer Alembic.

`version_table` propio por el mismo motivo que en Gestiolibra: si alguno de los
otros dos duenos adoptara Alembic sobre este mismo archivo, dos cadenas
compartiendo `alembic_version` se corromperian mutuamente.

`render_as_batch` es obligatorio en SQLite: no hay `ALTER TABLE ... ALTER
COLUMN` ni `DROP CONSTRAINT`, asi que Alembic emula el cambio creando la tabla
nueva, copiando y renombrando. Sin esto, cualquier migracion que no sea un
`ADD COLUMN` falla — que es justo el limite por el que existia
`app/migrations.py`.
"""
import os

from alembic import context
from libracore.db.url_de_instancia import url_de_instancia
from sqlalchemy import engine_from_config, pool

# Todo lo compartido sale de `app.schema`: ahi esta la lista de modulos que
# registran modelos en `Base`, el filtro y el nombre de la tabla de version.
# Este archivo no define nada propio, para que no haya dos definiciones que
# puedan divergir — y para que los tests puedan probar el filtro sin importar
# env.py, que ejecuta codigo del contexto de Alembic al importarse.
from app.schema import VERSION_TABLE, include_name
from app.schema import metadata as target_metadata


def _url() -> str:
    # `DATABASE_URL` primero, misma convencion que gestiolibra/migrations/env.py:
    # asi el CLI apunta a la base real (o a una descartable) sin editar el ini.
    return url_de_instancia("libradesk") or context.config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
        include_name=include_name,
        render_as_batch=True,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # `ensure_schema()` inyecta la conexion ya abierta del engine de la app:
    # asi la migracion y el resto del arranque van por la MISMA conexion, en
    # vez de abrir una segunda contra un SQLite que puede estar en WAL. El
    # camino de abajo es solo para el CLI (`alembic upgrade head` a mano).
    connectable = context.config.attributes.get("connection")

    if connectable is None:
        configuration = context.config.get_section(context.config.config_ini_section, {})
        configuration["sqlalchemy.url"] = _url()
        engine = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
        with engine.connect() as connection:
            _run(connection)
    else:
        _run(connectable)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
        include_name=include_name,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
