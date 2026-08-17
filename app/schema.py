"""Creacion y migracion del schema propio de LibraDesk, con Alembic.

**Que reemplaza.** Hasta el 2026-08-03 el arranque hacia
`Base.metadata.create_all()` + `app/migrations.py`. `create_all()` no altera
tablas que ya existen, asi que toda columna nueva necesitaba ademas un
`ALTER TABLE ADD COLUMN` idempotente escrito a mano, y eso solo cubre columnas
nullable: renombrar, cambiar un tipo o tocar una constraint no tenia camino a
produccion. Ahora las dos cosas las hace la cadena de `migrations/`.

**La adopcion es automatica y no hay paso manual en el VPS.** Las dos
instancias que ya existen (`libradesk-dev` y `libradesk-compulibra`) tienen las
tablas creadas desde antes de Alembic y no tienen tabla de version. En su
primer arranque con este codigo, `ensure_schema()` las **stampea** en el
baseline y sigue desde ahi. Una base vacia, en cambio, se construye entera
corriendo la cadena desde el principio. Se distingue un caso del otro mirando
la base, no una variable de entorno.

**Antes de stampear, verifica.** Stampear es afirmar "esta base esta en esta
revision" sin ejecutar nada; si la afirmacion fuera falsa, la proxima migracion
correria sobre un schema que no es el que cree, y el error aparecerea mucho
despues y lejos del cambio que lo causo. Por eso `_verificar_baseline()`
compara la base real contra la metadata **antes** de escribir la version, y si
falta algo aborta el arranque con el detalle. Que sea ruidoso es deliberado: un
contenedor que no levanta se ve enseguida; una version mentida, no.
"""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

from .database import Base

# --- Registro de modelos -----------------------------------------------------
# Importar estos modulos es lo que puebla `Base.metadata`. Es la UNICA lista:
# `migrations/env.py` importa `metadata` de aca, asi que un modelo nuevo entra
# al autogenerate por el solo hecho de estar importado en esta linea. Si en su
# lugar env.py tuviera su propia lista, agregar un modelo y olvidarse de una de
# las dos daria una tabla sin migracion, en silencio.
#
# 🔴 **Olvidarse de agregar una linea aca NO se nota mirando `alembic check`**,
# y se comprobo el 2026-08-05 con `ingresos` (pedido 43): la tabla estaba creada
# por su migracion y el modelo existia, pero al no estar importado quedaba fuera
# de `metadata` — y `include_name` filtra por `metadata`, asi que el autogenerate
# ni siquiera veia la tabla y reportaba "sin cambios". Un verde por ceguera.
# Lo agarro `test_sin_el_filtro_si_las_dropearia`, la contraprueba que corre el
# autogenerate SIN filtro: ahi la tabla aparecia en la lista de las que se
# dropearian, junto a las cinco ajenas. Esa es la unica senal que hay.
from .services import activos as _activos  # noqa: F401
from .services import categorias as _categorias  # noqa: F401
from .services import clientes as _clientes  # noqa: F401
from .services import contratos as _contratos  # noqa: F401
from .services import cuotas as _cuotas  # noqa: F401
from .services import depositos as _depositos  # noqa: F401
from .services import equipos as _equipos  # noqa: F401
from .services import equipos_trabajo as _equipos_trabajo  # noqa: F401
# `config_facturacion`: la creo la revision `0016` (2026-08-11) y esta linea
# faltaba, asi que la tabla quedaba fuera de `metadata` — el mismo olvido que
# el comentario de arriba describe para `ingresos`. No se noto porque la unica
# senal, `test_sin_el_filtro_si_las_dropearia`, llevaba dias en rojo por otro
# motivo (corria contra SQLite y moria antes de llegar a comparar). Un guard
# que ya esta rojo no avisa de nada.
from .services import facturacion_config as _facturacion_config  # noqa: F401
from .services import facturacion_externa as _facturacion_externa  # noqa: F401
from .services import incidencias as _incidencias  # noqa: F401
from .services import ingresos as _ingresos  # noqa: F401
from .services import modules as _modules  # noqa: F401
from .services import proveedores as _proveedores  # noqa: F401
from .services import reparaciones as _reparaciones  # noqa: F401
from .services import sectores as _sectores  # noqa: F401
# `servicios` **ya no se importa, y no es un olvido de los que documenta el
# comentario de arriba**: la revision `0031` dropeo la tabla y borro el modulo.
# El catalogo de servicios vive ahora en `catalog_items`, que es de
# LibraCommerce y por eso NO va en `metadata` — es justo lo que `include_name()`
# filtra para que el autogenerate no proponga dropear las tablas del motor.
from .services import tecnicos as _tecnicos  # noqa: F401
# `ventas` entra por `VentaRemito` (revision `0026`), que es su UNICA tabla
# SQLAlchemy: el resto del modulo es LibraCommerce por conexion cruda. Sin esta
# linea la tabla queda fuera de `metadata` y el autogenerate ni la ve — el mismo
# olvido que arriba se documenta para `ingresos` y `config_facturacion`.
from .services import ventas as _ventas  # noqa: F401

metadata = Base.metadata
# `visitas` **no declara tablas propias** —una visita de mantenimiento ES una
# incidencia, revision `0027`— asi que no hace falta importarlo para el
# autogenerate. Se deja dicho para que la ausencia de la linea se lea como una
# decision y no como el olvido que documentan los comentarios de arriba.

VERSION_TABLE = "alembic_version_libradesk"
BASELINE = "0001_baseline"


def include_name(name, type_, parent_names=None) -> bool:
    """Filtro del autogenerate: solo las tablas de LibraDesk.

    En este mismo archivo SQLite viven tambien `usuarios`,
    `password_reset_tokens`, `smtp_settings`, `auth_log` y `actividad_log` (de
    `libraauth`) y `remitos` y `presupuestos` (de `libracore`, en sqlite3
    crudo). Ninguna esta en `metadata`, asi que sin este filtro
    `--autogenerate` las ve como tablas que sobran y **propone dropearlas**.

    > `actividad_log` estuvo en `metadata` un dia: la creo la revision `0010`,
    > de cuando el log de actividad era codigo de este producto. Al extraerse a
    > `libraauth.auditoria` (v0.9.0) su schema paso a versionarlo el motor, como
    > el de `usuarios`. **La revision `0010` se queda** —ya corrio en dev y una
    > migracion aplicada no se borra—, pero la tabla ya no es de este metadata.

    La lista sale de `metadata` y no esta escrita a mano: un modelo nuevo entra
    solo, y una tabla ajena no puede colarse por olvido. Vive aca y no en
    `migrations/env.py` para que los tests puedan importarlo — env.py ejecuta
    codigo del contexto de Alembic al importarse.
    """
    del parent_names
    if type_ == "table":
        # `name is None` es el schema default: tiene que pasar.
        return name is None or name in metadata.tables
    return True

_RAIZ = Path(__file__).resolve().parent.parent
_ALEMBIC_INI = _RAIZ / "alembic.ini"
_MIGRATIONS = _RAIZ / "migrations"

log = logging.getLogger(__name__)


class SchemaInesperado(RuntimeError):
    """La base existente no coincide con el baseline: no se puede stampear."""


def _config(connection) -> Config:
    # `alembic.ini` y `migrations/` viajan en la imagen por el `COPY . .` del
    # Dockerfile, no dentro del wheel (`[tool.hatch.build.targets.wheel]`
    # empaqueta solo `app`). O sea que dependen de que el `app` que se importe
    # sea el del checkout y no el de site-packages. Si algun dia deja de serlo,
    # que el error lo diga en vez de salir como un fallo raro de Alembic.
    if not _ALEMBIC_INI.is_file() or not (_MIGRATIONS / "versions").is_dir():
        raise RuntimeError(
            f"No se encuentra la configuracion de Alembic junto a la app: se busco "
            f"{_ALEMBIC_INI} y {_MIGRATIONS}/versions. El paquete `app` se importo "
            f"desde {_RAIZ}, que no es la raiz del repo."
        )
    cfg = Config(str(_ALEMBIC_INI))
    # Absolutos: el cwd del proceso no es necesariamente la raiz del repo
    # (uvicorn corre desde /app en el contenedor, pytest desde donde lo llamen).
    cfg.set_main_option("script_location", str(_MIGRATIONS))
    cfg.attributes["connection"] = connection
    return cfg


def _version_actual(connection) -> str | None:
    return MigrationContext.configure(
        connection, opts={"version_table": VERSION_TABLE}
    ).get_current_revision()


def _schema_del_baseline() -> dict[str, set[str]]:
    """Tablas y columnas que crea la revision baseline, corriendola en memoria.

    **Contra el baseline y no contra `metadata`**, que es la diferencia entre
    que esto funcione o tire abajo el arranque de produccion. `metadata` refleja
    los modelos de HOY, o sea el `head` de la cadena; una base anterior a
    Alembic esta —por definicion— en el baseline y le faltan todas las columnas
    que agregaron las revisiones posteriores. Compararla contra `metadata`
    hacia fallar la verificacion en cuanto existio la primera revision real, y
    con ella el arranque de las dos instancias. Lo agarro
    `test_una_base_anterior_a_alembic_se_adopta_sin_perder_datos` al sumarse la
    0002.
    """
    memoria = create_engine("sqlite://")
    with memoria.begin() as conn:
        command.upgrade(_config(conn), BASELINE)
        inspector = inspect(conn)
        return {
            t: {c["name"] for c in inspector.get_columns(t)}
            for t in inspector.get_table_names()
            if not t.startswith("alembic_version")
        }


def _verificar_baseline(connection) -> None:
    """Comprueba que la base preexistente tenga de verdad el schema del baseline.

    Solo mira lo que FALTA. Una columna de mas no aborta: puede ser de otro
    dueno del archivo, o una base que quedo adelantada, y ninguno de esos casos
    rompe la cadena. Una de menos si: significa que el baseline no describe esta
    base y stamparla seria registrar algo falso.
    """
    inspector = inspect(connection)
    presentes = set(inspector.get_table_names())
    faltantes: list[str] = []

    for tabla, columnas in _schema_del_baseline().items():
        if tabla not in presentes:
            faltantes.append(f"tabla {tabla}")
            continue
        reales = {c["name"] for c in inspector.get_columns(tabla)}
        faltantes.extend(f"{tabla}.{c}" for c in columnas - reales)

    if faltantes:
        raise SchemaInesperado(
            "La base existente no coincide con el baseline de Alembic y por eso "
            "no se la stampea: hacerlo dejaria registrada una revision que esta "
            "base no tiene.\n"
            f"Falta en la base: {', '.join(sorted(faltantes))}\n"
            "Revisar el schema real contra migrations/versions/0001_baseline.py "
            "antes de arrancar."
        )


def ensure_schema(engine: Engine) -> str:
    """Deja la base en `head`. Devuelve que camino se tomo (para el log)."""
    with engine.begin() as connection:
        existentes = set(inspect(connection).get_table_names())
        if _version_actual(connection) is not None:
            camino = "upgrade"
        elif existentes & set(metadata.tables):
            # Hay tablas propias pero no hay tabla de version: es una base
            # anterior a Alembic y hay que adoptarla. Se pregunta por la
            # interseccion con la metadata y no por una tabla puntual porque
            # `usuarios` y `remitos` tambien viven en este archivo y son de
            # otros duenos: su presencia no dice nada sobre el schema propio.
            _verificar_baseline(connection)
            command.stamp(_config(connection), BASELINE)
            camino = "stamp+upgrade"
        else:
            camino = "creacion"

        command.upgrade(_config(connection), "head")

    log.info("schema de LibraDesk en head (%s)", camino)
    return camino
