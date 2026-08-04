"""Alembic: que el baseline sea fiel, que el filtro no deje tocar tablas
ajenas, y que las bases que ya existen se adopten sin perder nada.

Las tres cosas que estos tests protegen, en orden de gravedad si fallaran:

1. **Que `--autogenerate` no proponga dropear tablas de otro dueno.** En este
   archivo SQLite tambien viven `usuarios`/`password_reset_tokens`/
   `smtp_settings` (de `libraauth`) y `remitos`/`presupuestos` (de `libracore`).
   Sin el filtro de `app.schema.include_name`, Alembic las ve como sobrantes.
2. **Que el baseline describa la base REAL de produccion**, que no nacio de
   `create_all()` sino de la migracion desde Postgres mas un `ALTER TABLE` a
   mano. Si no la describiera, stamparla registraria una revision falsa.
3. **Que los modelos y la cadena no se separen**: un `mapped_column` nuevo sin
   su revision tiene que poner un test en rojo, no aparecer recien cuando la
   consulta falle en produccion.
"""
import sqlite3

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from app.schema import (
    BASELINE,
    SchemaInesperado,
    VERSION_TABLE,
    ensure_schema,
    include_name,
    metadata,
)
from app.schema import _config as alembic_config

# El schema REAL de las 9 tablas propias en `libradesk-compulibra`, leido del
# VPS el 2026-08-03. No es una transcripcion a mano: se genero volcando
# `sqlite_master` de la base de produccion.
#
# Dos cosas que solo se ven aca y no en los modelos: `equipos_movimientos`
# declara `incidencia_id INTEGER REFERENCES incidencias(id)` **inline** (asi lo
# dejo el `ALTER TABLE` de la migracion a mano, mientras `create_all()` emite la
# misma FK como `FOREIGN KEY(...)` al final), y `modulos` tiene `"plan"`
# entrecomillado. Por eso las comparaciones de este archivo son por PRAGMA y no
# por texto.
_DDL_PRODUCCION = [
    'CREATE TABLE clientes ( id INTEGER NOT NULL, nombre VARCHAR(255) NOT NULL, empresa VARCHAR(255), email VARCHAR(255), telefono VARCHAR(20), ciudad VARCHAR(100), observaciones TEXT, tipo_facturacion VARCHAR(20) NOT NULL, activo BOOLEAN NOT NULL, fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY (id), UNIQUE (email) )',
    'CREATE TABLE modulos ( modulo VARCHAR NOT NULL, habilitado BOOLEAN NOT NULL, "plan" VARCHAR NOT NULL, PRIMARY KEY (modulo) )',
    'CREATE TABLE tecnicos ( id INTEGER NOT NULL, nombre VARCHAR(100) NOT NULL, activo BOOLEAN NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY (id), UNIQUE (nombre) )',
    'CREATE TABLE sectores ( id INTEGER NOT NULL, cliente_id INTEGER NOT NULL, nombre VARCHAR(100) NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY (id), UNIQUE (cliente_id, nombre), FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE )',
    'CREATE TABLE equipos ( id INTEGER NOT NULL, cliente_id INTEGER NOT NULL, tipo VARCHAR(100) NOT NULL, modelo VARCHAR(255), marca VARCHAR(255), serial VARCHAR(255), ubicacion_oficina VARCHAR(255), sector VARCHAR(255), estado VARCHAR(50) NOT NULL, fecha_adicion DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, garantia_vence DATE, observaciones TEXT, PRIMARY KEY (id), FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE )',
    'CREATE TABLE incidencias ( id INTEGER NOT NULL, cliente_id INTEGER NOT NULL, equipo_id INTEGER, tecnico_id INTEGER, sector_id INTEGER, titulo VARCHAR(255) NOT NULL, descripcion TEXT, estado VARCHAR(50) NOT NULL, prioridad VARCHAR(20) NOT NULL, horas_invertidas NUMERIC(5, 2), notas TEXT, resolucion TEXT, estado_facturacion VARCHAR(20), activo BOOLEAN NOT NULL, fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, fecha_cierre DATETIME, PRIMARY KEY (id), FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE, FOREIGN KEY(equipo_id) REFERENCES equipos (id) ON DELETE SET NULL, FOREIGN KEY(tecnico_id) REFERENCES tecnicos (id) ON DELETE SET NULL, FOREIGN KEY(sector_id) REFERENCES sectores (id) ON DELETE SET NULL )',
    'CREATE TABLE actividades_incidencia ( id INTEGER NOT NULL, incidencia_id INTEGER NOT NULL, fecha DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, descripcion TEXT, usuario VARCHAR(100), PRIMARY KEY (id), FOREIGN KEY(incidencia_id) REFERENCES incidencias (id) ON DELETE CASCADE )',
    'CREATE TABLE equipos_movimientos ( id INTEGER NOT NULL, equipo_id INTEGER NOT NULL, tipo VARCHAR(50) NOT NULL, descripcion TEXT, sector_origen VARCHAR(255), sector_destino VARCHAR(255), ubicacion_origen VARCHAR(255), ubicacion_destino VARCHAR(255), motivo VARCHAR(500), usuario VARCHAR(255) NOT NULL, fecha DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, incidencia_id INTEGER REFERENCES incidencias(id), PRIMARY KEY (id), FOREIGN KEY(equipo_id) REFERENCES equipos (id) ON DELETE CASCADE )',
    'CREATE TABLE incidencias_estados_log ( id INTEGER NOT NULL, incidencia_id INTEGER NOT NULL, estado_anterior VARCHAR(50), estado_nuevo VARCHAR(50) NOT NULL, fecha DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, tecnico VARCHAR(100), PRIMARY KEY (id), FOREIGN KEY(incidencia_id) REFERENCES incidencias (id) ON DELETE CASCADE )',
    'CREATE INDEX ix_actividades_incidencia_incidencia_id ON actividades_incidencia (incidencia_id)',
    'CREATE INDEX ix_equipos_cliente_id ON equipos (cliente_id)',
    'CREATE INDEX ix_equipos_movimientos_equipo_id ON equipos_movimientos (equipo_id)',
    'CREATE INDEX ix_equipos_movimientos_incidencia_id ON equipos_movimientos (incidencia_id)',
    'CREATE INDEX ix_incidencias_cliente_id ON incidencias (cliente_id)',
    'CREATE INDEX ix_incidencias_equipo_id ON incidencias (equipo_id)',
    'CREATE INDEX ix_incidencias_estado ON incidencias (estado)',
    'CREATE INDEX ix_incidencias_estados_log_incidencia_id ON incidencias_estados_log (incidencia_id)',
    'CREATE INDEX ix_incidencias_fecha_creacion ON incidencias (fecha_creacion)',
    'CREATE INDEX ix_sectores_cliente_id ON sectores (cliente_id)',
]

# Las 5 tablas que en el mismo archivo pertenecen a otros duenos. El DDL exacto
# no importa para lo que se prueba (que Alembic no las toque), si el nombre.
_TABLAS_AJENAS = {
    "usuarios": "CREATE TABLE usuarios (id INTEGER PRIMARY KEY, username VARCHAR(100) NOT NULL)",
    "password_reset_tokens": "CREATE TABLE password_reset_tokens (id INTEGER PRIMARY KEY, user_id INTEGER)",
    "smtp_settings": "CREATE TABLE smtp_settings (id INTEGER PRIMARY KEY, host VARCHAR(200))",
    "remitos": "CREATE TABLE remitos (id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT NOT NULL UNIQUE)",
    "presupuestos": "CREATE TABLE presupuestos (id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT NOT NULL UNIQUE)",
}


# --- helpers -----------------------------------------------------------------

def _engine(tmp_path, nombre="libradesk.db"):
    return create_engine(f"sqlite:///{tmp_path / nombre}")


def _upgrade(engine, hasta="head") -> None:
    with engine.begin() as conn:
        command.upgrade(alembic_config(conn), hasta)


def _head() -> str:
    """La ultima revision, leida de la cadena y no escrita a mano: asi agregar
    una revision no obliga a tocar los tests."""
    with create_engine("sqlite://").connect() as conn:
        return ScriptDirectory.from_config(alembic_config(conn)).get_current_head()


def _heads() -> list[str]:
    with create_engine("sqlite://").connect() as conn:
        return list(ScriptDirectory.from_config(alembic_config(conn)).get_heads())


def _ejecutar(engine, sentencias) -> None:
    with engine.begin() as conn:
        for sql in sentencias:
            conn.execute(text(sql))


def _radiografia(engine) -> dict:
    """Columnas, tipos, nullability, PK, FKs e indices de las tablas propias.

    Por PRAGMA y no por el texto del `CREATE TABLE`: produccion y `create_all()`
    escriben la misma FK de dos formas distintas (ver `_DDL_PRODUCCION`).
    """
    out = {}
    with engine.connect() as conn:
        raw = conn.connection.driver_connection
        for t in sorted(metadata.tables):
            cols = {}
            for _cid, nombre, tipo, notnull, dflt, pk in raw.execute(f'PRAGMA table_info("{t}")'):
                if dflt and dflt.startswith("(") and dflt.endswith(")"):
                    # `DEFAULT (CURRENT_TIMESTAMP)` y `DEFAULT CURRENT_TIMESTAMP`
                    # son lo mismo; Alembic emite uno y create_all() el otro.
                    dflt = dflt[1:-1]
                cols[nombre] = (tipo, bool(notnull), dflt, pk)
            fks = sorted(
                (r[2], r[3], r[4], r[5], r[6])
                for r in raw.execute(f'PRAGMA foreign_key_list("{t}")')
            )
            idx = {}
            for _seq, nombre, unico, origen, _parcial in raw.execute(f'PRAGMA index_list("{t}")'):
                campos = [r[2] for r in raw.execute(f'PRAGMA index_info("{nombre}")')]
                # Los indices que respaldan un UNIQUE se llaman
                # `sqlite_autoindex_<tabla>_<N>`, y ese N depende del orden de
                # creacion: se los identifica por sus columnas.
                clave = nombre if origen == "c" else f"<{origen}:{','.join(campos)}>"
                idx[clave] = (bool(unico), origen, campos)
            out[t] = {"columnas": cols, "fks": fks, "indices": idx}
    return out


def _diferencias(engine, filtro=include_name):
    """Lo que `--autogenerate` propondria contra esta base."""
    with engine.connect() as conn:
        contexto = MigrationContext.configure(
            conn,
            opts={
                "target_metadata": metadata,
                "include_name": filtro,
                "version_table": VERSION_TABLE,
                "render_as_batch": True,
            },
        )
        return compare_metadata(contexto, metadata)


def _version(engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(
            conn, opts={"version_table": VERSION_TABLE}
        ).get_current_revision()


# --- el baseline es fiel -----------------------------------------------------

def test_alembic_construye_lo_mismo_que_create_all(tmp_path):
    """Una base nueva tiene que quedar igual la haga Alembic o `create_all()`.

    Es lo que garantiza que traer Alembic no cambie nada para una instancia
    nueva: mismo schema, distinto camino.
    """
    por_alembic = _engine(tmp_path, "a.db")
    _upgrade(por_alembic)

    por_create_all = _engine(tmp_path, "b.db")
    metadata.create_all(por_create_all)

    assert _radiografia(por_alembic) == _radiografia(por_create_all)


def test_el_baseline_describe_la_base_real_de_produccion(tmp_path):
    """El permiso para stampear.

    Stampear es afirmar "esta base ya esta en esta revision" sin ejecutar nada.
    Si `compulibra` no fuera igual al baseline, esa afirmacion seria falsa y la
    proxima migracion correria sobre un schema que no es el que cree.

    Se compara contra `BASELINE` y no contra `head` a proposito: lo que se
    stampea es el baseline. Las revisiones que vienen despues describen cambios
    que produccion todavia no tiene — de eso se encargan, justamente.
    """
    real = _engine(tmp_path, "produccion.db")
    _ejecutar(real, _DDL_PRODUCCION)

    del_baseline = _engine(tmp_path, "baseline.db")
    _upgrade(del_baseline, BASELINE)

    assert _radiografia(real) == _radiografia(del_baseline)


def test_los_modelos_no_se_separan_de_la_cadena(tmp_path):
    """Si alguien agrega un `mapped_column` y se olvida de la revision, esto se
    pone en rojo. Es el unico test que cubre el olvido: la app arrancaria igual
    y el error recien aparecerea al consultar la columna que no existe."""
    engine = _engine(tmp_path)
    _upgrade(engine)

    assert _diferencias(engine) == []


def test_la_cadena_tiene_una_sola_cabeza(tmp_path):
    """Dos revisiones hermanas rompen el arranque de la app, y **git no lo
    avisa**: los dos archivos conviven sin conflicto de merge.

    El caso concreto que motiva este test (2026-08-04): dos sesiones en
    paralelo escribieron cada una su `0004`, las dos colgando de
    `0003_proveedores_y_reparaciones` — `0004_alquileres` (PR #27) y
    `0004_depositos`. Con las dos en la rama, `command.upgrade(cfg, "head")`
    —que es lo que corre `app/schema.py` en cada arranque— falla con "Multiple
    head revisions are present" y **el contenedor no levanta**. Ninguna de las
    dos revisiones esta mal; lo que falta es que la segunda cuelgue de la
    primera.

    Que se ponga en rojo acá es mucho mas barato que descubrirlo en el deploy:
    el arreglo es una linea (`down_revision` de la que llegue segunda) y un
    renombre.
    """
    cabezas = _heads()

    assert len(cabezas) == 1, (
        f"la cadena de migraciones tiene {len(cabezas)} cabezas: {cabezas}. "
        "Alguna revision nueva tiene que colgar de la otra en vez de compartir "
        "`down_revision` — ver el docstring de este test."
    )
    # Y la unica coincide con la que devuelve `get_current_head()`, que es la
    # que usan el resto de los tests.
    assert cabezas == [_head()]


# --- el filtro protege a las tablas de los otros duenos ----------------------

def test_autogenerate_no_propone_dropear_las_tablas_ajenas(tmp_path):
    """El footgun principal de meter Alembic en este producto."""
    engine = _engine(tmp_path)
    _upgrade(engine)
    _ejecutar(engine, _TABLAS_AJENAS.values())

    assert _diferencias(engine) == []


def test_sin_el_filtro_si_las_dropearia(tmp_path):
    """La contraprueba: sin `include_name`, Alembic propone borrar las 5.

    Sin este test, el anterior pasaria igual aunque el filtro no hiciera nada
    — por ejemplo si un dia dejara de estar cableado en `migrations/env.py`.
    """
    engine = _engine(tmp_path)
    _upgrade(engine)
    _ejecutar(engine, _TABLAS_AJENAS.values())

    propuestas = _diferencias(engine, filtro=None)
    dropeadas = {d[1].name for d in propuestas if d[0] == "remove_table"}

    assert dropeadas == set(_TABLAS_AJENAS)


# --- adopcion de las bases que ya existen ------------------------------------

def test_una_base_anterior_a_alembic_se_adopta_sin_perder_datos(tmp_path):
    """El caso real del deploy: `compulibra` existe desde la migracion del
    Node.js viejo, tiene datos, y no tiene tabla de version.

    Lo que se exige: que se la stampee en el baseline, que **desde ahi corra el
    resto de la cadena**, y que ni una fila se pierda en el camino. Sin la
    adopcion, el arranque intentaria correr el baseline sobre tablas que ya
    existen y fallaria con `table clientes already exists`.
    """
    engine = _engine(tmp_path)
    _ejecutar(engine, _DDL_PRODUCCION)
    _ejecutar(engine, [
        "INSERT INTO clientes (id, nombre, tipo_facturacion, activo) "
        "VALUES (1, 'Compulibra', 'por_servicio', 1)",
        "INSERT INTO equipos (id, cliente_id, tipo, estado) VALUES (1, 1, 'Impresora', 'activo')",
        "INSERT INTO incidencias (id, cliente_id, titulo, estado, prioridad, activo) "
        "VALUES (1, 1, 'La impresora hace ruido', 'abierto', 'media', 1)",
    ])
    columnas_antes = _radiografia(engine)["clientes"]["columnas"]

    assert _version(engine) is None
    assert ensure_schema(engine) == "stamp+upgrade"

    # Queda en head, no en el baseline: la adopcion stampea y sigue.
    assert _version(engine) == _head() != BASELINE

    despues = _radiografia(engine)
    # Lo que ya estaba sigue igual, con el mismo tipo y la misma nullability...
    for nombre, definicion in columnas_antes.items():
        assert despues["clientes"]["columnas"][nombre] == definicion
    # ...y lo que agrego la 0002 esta.
    assert {"cuit", "domicilio"} <= set(despues["clientes"]["columnas"])
    assert "categoria_id" in despues["incidencias"]["columnas"]
    assert despues["categorias_incidencia"]["columnas"]

    with engine.connect() as conn:
        assert conn.execute(text("SELECT nombre FROM clientes")).scalar() == "Compulibra"
        assert conn.execute(text("SELECT COUNT(*) FROM equipos")).scalar() == 1
        # La fila de incidencias sobrevivio al ADD COLUMN de `categoria_id`, que
        # es el punto donde un `create_foreign_key` en batch habria reconstruido
        # la tabla entera (ver el docstring de la revision 0002).
        assert conn.execute(text("SELECT titulo FROM incidencias")).scalar() == \
            "La impresora hace ruido"
        assert conn.execute(text("SELECT categoria_id FROM incidencias")).scalar() is None


def test_una_base_vacia_se_construye_entera(tmp_path):
    engine = _engine(tmp_path)

    assert ensure_schema(engine) == "creacion"

    assert _version(engine) == _head()
    assert _diferencias(engine) == []


def test_una_base_ya_adoptada_solo_hace_upgrade(tmp_path):
    """El segundo arranque y todos los siguientes: idempotente."""
    engine = _engine(tmp_path)
    ensure_schema(engine)

    assert ensure_schema(engine) == "upgrade"
    assert _version(engine) == _head()


def test_no_se_stampea_una_base_que_no_coincide_con_el_baseline(tmp_path):
    """Si a la base le falta algo que el baseline promete, abortar es preferible
    a registrar una version que no es cierta: el error apareceria mucho despues,
    en la primera migracion que se apoye en esa columna.
    """
    engine = _engine(tmp_path)
    # Produccion, pero sin la columna que agrego la migracion a mano de julio:
    # es exactamente el estado del que se venia.
    sin_columna = [
        sql.replace(" incidencia_id INTEGER REFERENCES incidencias(id),", "")
        if sql.startswith("CREATE TABLE equipos_movimientos") else sql
        for sql in _DDL_PRODUCCION
        if "ix_equipos_movimientos_incidencia_id" not in sql
    ]
    _ejecutar(engine, sin_columna)

    with pytest.raises(SchemaInesperado) as e:
        ensure_schema(engine)

    assert "equipos_movimientos.incidencia_id" in str(e.value)
    # Y no dejo la version escrita a medias.
    assert _version(engine) is None


def test_la_tabla_de_version_no_es_la_default(tmp_path):
    """`alembic_version` a secas se corromperia si `libraauth` o `libracore`
    adoptaran Alembic sobre este mismo archivo. Mismo motivo que en Gestiolibra.
    """
    engine = _engine(tmp_path)
    ensure_schema(engine)

    with engine.connect() as conn:
        tablas = {
            r[0] for r in conn.connection.driver_connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert VERSION_TABLE in tablas
    assert "alembic_version" not in tablas


def test_sqlite_no_soporta_alter_column_sin_batch():
    """Deja anotado por que `render_as_batch=True` no es opcional.

    Sin batch, Alembic emite `ALTER TABLE ... ALTER COLUMN`, que SQLite no
    entiende — y ese era justamente el techo de `app/migrations.py`: solo podia
    agregar columnas nullable.
    """
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE t (a INTEGER, b VARCHAR(10))")

    with pytest.raises(sqlite3.OperationalError):
        con.execute("ALTER TABLE t ALTER COLUMN b TYPE VARCHAR(20)")

    con.close()
