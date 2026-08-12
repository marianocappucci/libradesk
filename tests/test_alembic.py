"""Alembic: que el baseline sea fiel, que el filtro no deje tocar tablas
ajenas, y que las bases que ya existen se adopten sin perder nada.

Las tres cosas que estos tests protegen, en orden de gravedad si fallaran:

1. **Que `--autogenerate` no proponga dropear tablas de otro dueno.** En la
   misma base viven tambien `usuarios`/`password_reset_tokens`/
   `smtp_settings` (de `libraauth`) y `remitos`/`presupuestos` (de `libracore`).
   Sin el filtro de `app.schema.include_name`, Alembic las ve como sobrantes.

> Todo este archivo corria contra SQLite hasta el 2026-08-12, y su
> introspeccion era por `PRAGMA`. Con SQLite retirado del producto, cada test
> arma su propia base PostgreSQL y `_radiografia()` va por
> `sqlalchemy.inspect()`, que no depende del dialecto.
2. **Que el baseline describa la base REAL de produccion**, que no nacio de
   `create_all()` sino de la migracion desde Postgres mas un `ALTER TABLE` a
   mano. Si no la describiera, stamparla registraria una revision falsa.
3. **Que los modelos y la cadena no se separen**: un `mapped_column` nuevo sin
   su revision tiene que poner un test en rojo, no aparecer recien cuando la
   consulta falle en produccion.
"""
import contextlib
import io
import re
import zlib

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.schema import (
    BASELINE,
    SchemaInesperado,
    VERSION_TABLE,
    ensure_schema,
    include_name,
    metadata,
)
from app.schema import _config as alembic_config

# El schema de las 9 tablas propias tal como existia en `libradesk-compulibra`
# ANTES de Alembic: no nacio de `create_all()` sino de la migracion del Node.js
# viejo mas un `ALTER TABLE` a mano. Leido del VPS el 2026-08-03 volcando
# `sqlite_master`, cuando esa instancia todavia era SQLite.
#
# **Traducido a PostgreSQL el 2026-08-12**, al retirarse SQLite. Lo que se
# conserva es lo que el test necesita —la FORMA de la base de la que se venia,
# distinta de la que emite `create_all()`— y no el dialecto en el que estaba
# escrita. Los cambios son mecanicos: `INTEGER NOT NULL` + PK -> `SERIAL`,
# `DATETIME` -> `TIMESTAMP`, `NUMERIC(5, 2)` queda igual.
#
# Dos cosas que solo se ven aca y no en los modelos: `equipos_movimientos`
# declara `incidencia_id INTEGER REFERENCES incidencias(id)` **inline** (asi lo
# dejo el `ALTER TABLE` de la migracion a mano, mientras `create_all()` emite la
# misma FK como `FOREIGN KEY(...)` al final), y `modulos` tiene `"plan"`
# entrecomillado. Por eso las comparaciones de este archivo son por
# introspeccion y no por texto.
_DDL_PRODUCCION = [
    'CREATE TABLE clientes ( id SERIAL, nombre VARCHAR(255) NOT NULL, empresa VARCHAR(255), email VARCHAR(255), telefono VARCHAR(20), ciudad VARCHAR(100), observaciones TEXT, tipo_facturacion VARCHAR(20) NOT NULL, activo BOOLEAN NOT NULL, fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY (id), UNIQUE (email) )',
    'CREATE TABLE modulos ( modulo VARCHAR NOT NULL, habilitado BOOLEAN NOT NULL, "plan" VARCHAR NOT NULL, PRIMARY KEY (modulo) )',
    'CREATE TABLE tecnicos ( id SERIAL, nombre VARCHAR(100) NOT NULL, activo BOOLEAN NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY (id), UNIQUE (nombre) )',
    'CREATE TABLE sectores ( id SERIAL, cliente_id INTEGER NOT NULL, nombre VARCHAR(100) NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, PRIMARY KEY (id), UNIQUE (cliente_id, nombre), FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE )',
    'CREATE TABLE equipos ( id SERIAL, cliente_id INTEGER NOT NULL, tipo VARCHAR(100) NOT NULL, modelo VARCHAR(255), marca VARCHAR(255), serial VARCHAR(255), ubicacion_oficina VARCHAR(255), sector VARCHAR(255), estado VARCHAR(50) NOT NULL, fecha_adicion TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, garantia_vence DATE, observaciones TEXT, PRIMARY KEY (id), FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE )',
    'CREATE TABLE incidencias ( id SERIAL, cliente_id INTEGER NOT NULL, equipo_id INTEGER, tecnico_id INTEGER, sector_id INTEGER, titulo VARCHAR(255) NOT NULL, descripcion TEXT, estado VARCHAR(50) NOT NULL, prioridad VARCHAR(20) NOT NULL, horas_invertidas NUMERIC(5, 2), notas TEXT, resolucion TEXT, estado_facturacion VARCHAR(20), activo BOOLEAN NOT NULL, fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, fecha_cierre TIMESTAMP, PRIMARY KEY (id), FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE, FOREIGN KEY(equipo_id) REFERENCES equipos (id) ON DELETE SET NULL, FOREIGN KEY(tecnico_id) REFERENCES tecnicos (id) ON DELETE SET NULL, FOREIGN KEY(sector_id) REFERENCES sectores (id) ON DELETE SET NULL )',
    'CREATE TABLE actividades_incidencia ( id SERIAL, incidencia_id INTEGER NOT NULL, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, descripcion TEXT, usuario VARCHAR(100), PRIMARY KEY (id), FOREIGN KEY(incidencia_id) REFERENCES incidencias (id) ON DELETE CASCADE )',
    'CREATE TABLE equipos_movimientos ( id SERIAL, equipo_id INTEGER NOT NULL, tipo VARCHAR(50) NOT NULL, descripcion TEXT, sector_origen VARCHAR(255), sector_destino VARCHAR(255), ubicacion_origen VARCHAR(255), ubicacion_destino VARCHAR(255), motivo VARCHAR(500), usuario VARCHAR(255) NOT NULL, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, incidencia_id INTEGER REFERENCES incidencias(id), PRIMARY KEY (id), FOREIGN KEY(equipo_id) REFERENCES equipos (id) ON DELETE CASCADE )',
    'CREATE TABLE incidencias_estados_log ( id SERIAL, incidencia_id INTEGER NOT NULL, estado_anterior VARCHAR(50), estado_nuevo VARCHAR(50) NOT NULL, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, tecnico VARCHAR(100), PRIMARY KEY (id), FOREIGN KEY(incidencia_id) REFERENCES incidencias (id) ON DELETE CASCADE )',
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

# Las tablas que en el mismo archivo pertenecen a otros duenos. El DDL exacto
# no importa para lo que se prueba (que Alembic no las toque), si el nombre.
_TABLAS_AJENAS = {
    "usuarios": "CREATE TABLE usuarios (id INTEGER PRIMARY KEY, username VARCHAR(100) NOT NULL)",
    "password_reset_tokens": "CREATE TABLE password_reset_tokens (id INTEGER PRIMARY KEY, user_id INTEGER)",
    "smtp_settings": "CREATE TABLE smtp_settings (id INTEGER PRIMARY KEY, host VARCHAR(200))",
    "remitos": "CREATE TABLE remitos (id SERIAL PRIMARY KEY, number TEXT NOT NULL UNIQUE)",
    "presupuestos": "CREATE TABLE presupuestos (id SERIAL PRIMARY KEY, number TEXT NOT NULL UNIQUE)",
}

# `actividad_log` es ajena igual que las de arriba —su schema lo versiona
# `libraauth.auditoria` desde v0.9.0— pero NO se crea aca: ya la creo la
# revision `0010`, de cuando el log de actividad era codigo de este producto.
# Esa revision se queda (una migracion aplicada no se borra), asi que despues
# de `_upgrade()` la tabla existe y un `CREATE TABLE` mas fallaria.
_TABLAS_AJENAS_YA_CREADAS = {"actividad_log"}
_NOMBRES_AJENOS = set(_TABLAS_AJENAS) | _TABLAS_AJENAS_YA_CREADAS


# --- helpers -----------------------------------------------------------------

def _engine(tmp_path, nombre="libradesk"):
    """Una PostgreSQL vacia por llamada.

    Antes devolvia un SQLite dentro de `tmp_path`. Al retirarse SQLite
    (2026-08-12) el nombre del archivo pasa a ser el nombre de la base: el
    identificador sale de `tmp_path` —unico por test— mas `nombre` —unico
    dentro del test—, asi los catorce call sites se siguen escribiendo igual.

    Vacia y no copiada de la plantilla: estos tests construyen el schema
    corriendo la cadena o `create_all()`, que es justamente lo que miden.
    """
    from conftest import _sql_admin, _url_de

    crudo = re.sub(r"[^a-z0-9_]", "_", f"{tmp_path.name}_{nombre}".lower())
    base = f"lda_{zlib.crc32(crudo.encode()):08x}_{crudo[-28:]}"[:60]
    _sql_admin(f'DROP DATABASE IF EXISTS "{base}"', f'CREATE DATABASE "{base}"')
    return create_engine(_url_de(base))


def _upgrade(engine, hasta="head") -> None:
    with engine.begin() as conn:
        command.upgrade(alembic_config(conn), hasta)


def _head() -> str:
    """La ultima revision, leida de la cadena y no escrita a mano: asi agregar
    una revision no obliga a tocar los tests.

    `alembic_config(None)`: leer la cadena es mirar los archivos de
    `migrations/versions`, no la base. Estas dos funciones abrian un SQLite en
    memoria solo para tener una conexion que pasarle — y `_config()` lo unico
    que hace con ella es guardarla en `cfg.attributes`.
    """
    return ScriptDirectory.from_config(alembic_config(None)).get_current_head()


def _heads() -> list[str]:
    return list(ScriptDirectory.from_config(alembic_config(None)).get_heads())


def _ejecutar(engine, sentencias) -> None:
    with engine.begin() as conn:
        for sql in sentencias:
            conn.execute(text(sql))


def _normalizar_default(valor):
    """El texto de un DEFAULT, comparable entre quienes lo escribieron distinto.

    Tres formas de lo mismo conviven acá: el DDL a mano de produccion escribe
    `CURRENT_TIMESTAMP`, PostgreSQL lo devuelve como `now()`, y SQLAlchemy le
    agrega un cast (`'por_servicio'::character varying`). El default de una PK
    serial (`nextval(...)`) se descarta entero: el nombre de la secuencia
    depende de como se llamo la tabla al crearse, y eso no es schema.
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if texto.startswith("nextval("):
        return "<serial>"
    texto = re.sub(r"::[a-z ]+(\([0-9, ]*\))?", "", texto)   # casts de PostgreSQL
    # Solo un par que ENVUELVA todo: `(CURRENT_TIMESTAMP)` y `CURRENT_TIMESTAMP`
    # son lo mismo. Un `.strip("()")` a secas convertiria `now()` en `now` y
    # el mapeo de abajo dejaria de aplicar — que es justo lo que pasaba.
    if texto.startswith("(") and texto.endswith(")"):
        texto = texto[1:-1].strip()
    return {"now()": "CURRENT_TIMESTAMP"}.get(texto.lower(), texto)


def _radiografia(engine) -> dict:
    """Columnas, tipos, nullability, PK, FKs e indices de las tablas propias.

    Por introspeccion y no por el texto del `CREATE TABLE`: produccion y
    `create_all()` escriben la misma FK de dos formas distintas (ver
    `_DDL_PRODUCCION`).

    Va por `sqlalchemy.inspect()` y no por `PRAGMA` desde que se retiro SQLite
    (2026-08-12). El inspector es agnostico del motor, asi que esto deja de
    depender de un dialecto — que era el motivo por el que este archivo entero
    seguia atado a SQLite.

    Las tablas del `metadata` que **no existen** en esa base se saltean: hay
    tests que comparan contra el baseline, donde todavia no existen las que
    crearon las revisiones posteriores.
    """
    out = {}
    inspector = inspect(engine)
    existentes = set(inspector.get_table_names())
    for t in sorted(metadata.tables):
        if t not in existentes:
            continue
        cols = {}
        for c in inspector.get_columns(t):
            cols[c["name"]] = (
                # El tipo como lo entiende SQLAlchemy, no como lo escribio el
                # dialecto: `VARCHAR(255)` y `character varying(255)` son lo
                # mismo y tienen que comparar igual.
                str(c["type"]),
                not c["nullable"],
                _normalizar_default(c.get("default")),
            )
        pk = tuple(inspector.get_pk_constraint(t).get("constrained_columns") or ())
        fks = sorted(
            (
                tuple(fk["constrained_columns"]),
                fk["referred_table"],
                tuple(fk["referred_columns"]),
                (fk.get("options") or {}).get("ondelete"),
            )
            for fk in inspector.get_foreign_keys(t)
        )
        # Los indices por sus COLUMNAS y no por su nombre: el que respalda un
        # UNIQUE lo nombra cada motor a su manera, y ese nombre no es schema.
        idx = {
            (tuple(i["column_names"]), bool(i["unique"]))
            for i in inspector.get_indexes(t)
        }
        uniques = {
            tuple(u["column_names"]) for u in inspector.get_unique_constraints(t)
        }
        out[t] = {
            "columnas": cols, "pk": pk, "fks": fks,
            "indices": sorted(idx), "uniques": sorted(uniques),
        }
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
    """La contraprueba: sin `include_name`, Alembic propone borrar todas las
    ajenas.

    Sin este test, el anterior pasaria igual aunque el filtro no hiciera nada
    — por ejemplo si un dia dejara de estar cableado en `migrations/env.py`.
    """
    engine = _engine(tmp_path)
    _upgrade(engine)
    _ejecutar(engine, _TABLAS_AJENAS.values())

    propuestas = _diferencias(engine, filtro=None)
    dropeadas = {d[1].name for d in propuestas if d[0] == "remove_table"}

    assert dropeadas == _NOMBRES_AJENOS


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
        # `true` y no `1`: `activo` es BOOLEAN en la base de la que se venia, y
        # PostgreSQL no acepta un entero ahi. SQLite entendia las dos.
        "INSERT INTO clientes (id, nombre, tipo_facturacion, activo) "
        "VALUES (1, 'Compulibra', 'por_servicio', true)",
        "INSERT INTO equipos (id, cliente_id, tipo, estado) VALUES (1, 1, 'Impresora', 'activo')",
        "INSERT INTO incidencias (id, cliente_id, titulo, estado, prioridad, activo) "
        "VALUES (1, 1, 'La impresora hace ruido', 'abierto', 'media', true)",
    ])
    # Se lee directo y no por `_radiografia()`: esa recorre `metadata`, donde
    # la tabla ya se llama `clients` desde la revision `0017`. Aca todavia es
    # `clientes`, que es el punto — se esta mirando la base de la que se venia.
    columnas_antes = {c["name"] for c in inspect(engine).get_columns("clientes")}

    assert _version(engine) is None
    assert ensure_schema(engine) == "stamp+upgrade"

    # Queda en head, no en el baseline: la adopcion stampea y sigue.
    assert _version(engine) == _head() != BASELINE

    despues = _radiografia(engine)
    # 🔴 La cadena la renombro a `clients` en la `0017`, al adoptar el modulo de
    # clientes de LibraCore. El renombre tiene que traerse las columnas que ya
    # estaban, con su nombre nuevo: si reconstruyera la tabla en vez de
    # renombrarla, esto quedaria vacio y las siete FK apuntarian a la nada.
    assert "clientes" not in despues
    renombradas = {
        "nombre": "name", "telefono": "phone", "cuit": "cuit_dni",
        "domicilio": "address", "condicion_iva": "iva_condition",
        "fecha_creacion": "created_at",
    }
    esperadas = {renombradas.get(c, c) for c in columnas_antes}
    assert esperadas <= set(despues["clients"]["columnas"])

    # Lo que agrego la 0002 esta, con el nombre que le dejo la 0017.
    assert {"cuit_dni", "address"} <= set(despues["clients"]["columnas"])
    assert "categoria_id" in despues["incidencias"]["columnas"]
    assert despues["categorias_incidencia"]["columnas"]

    with engine.connect() as conn:
        # Ni una fila se perdio en el renombre.
        assert conn.execute(text("SELECT name FROM clients")).scalar() == "Compulibra"
        assert conn.execute(text("SELECT COUNT(*) FROM equipos")).scalar() == 1
        # Y las FK siguieron a la tabla: el equipo sigue colgando del cliente.
        assert conn.execute(
            text("SELECT COUNT(*) FROM equipos e JOIN clients c ON c.id = e.cliente_id")
        ).scalar() == 1
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

    tablas = set(inspect(engine).get_table_names())
    assert VERSION_TABLE in tablas
    assert "alembic_version" not in tablas


# Acá vivía `test_sqlite_no_soporta_alter_column_sin_batch`, que dejaba anotado
# por qué `render_as_batch=True` no era opcional: sin batch, Alembic emite
# `ALTER TABLE ... ALTER COLUMN`, que SQLite no entiende. Se retiró junto con
# SQLite el 2026-08-12 — probaba una limitación de un motor que este producto
# ya no usa.
#
# ⚠️ **`render_as_batch=True` sigue puesto** en `migrations/env.py` y acá en
# `_diferencias()`. Contra PostgreSQL no hace falta y sólo afecta cómo se
# RENDERIZA una revisión autogenerada; las revisiones ya escritas que usan
# `batch_alter_table` siguen andando igual (contra PostgreSQL el batch emite el
# `ALTER` directo). Sacarlo es parte del barrido de SQLite y no de esta
# reescritura: cambia el código que Alembic va a generar de acá en adelante,
# que es una decisión y no una traducción.


# --- la cadena tambien tiene que compilar en PostgreSQL ----------------------

def _sql_de_la_cadena(monkeypatch, url: str) -> str:
    """La cadena entera renderizada para un dialecto, SIN servidor ni base.

    Alembic tiene modo offline (`sql=True`): en vez de ejecutar, imprime el SQL
    que ejecutaria. `migrations/env.py` ya lo soporta y toma la URL de
    `DATABASE_URL`, asi que apuntandolo a una URL PostgreSQL se obtiene el DDL
    tal como lo veria PostgreSQL — en milisegundos y sin levantar nada.
    """
    monkeypatch.setenv("DATABASE_URL", url)
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        command.upgrade(alembic_config(None), "head", sql=True)
    return salida.getvalue()


# `BOOLEAN DEFAULT 1`, en cualquiera de las dos formas en que puede aparecer:
# dentro de un `CREATE TABLE` y en un `ADD COLUMN`.
_BOOLEANO_CON_DEFAULT_ENTERO = re.compile(r"(\w+)\s+BOOLEAN\s+DEFAULT\s+(\d+)", re.IGNORECASE)


def test_ningun_booleano_lleva_un_default_entero_en_postgres(monkeypatch):
    """🔴 `BOOLEAN DEFAULT 1` pasa en SQLite y rompe el upgrade en PostgreSQL.

    SQLite no tiene booleano nativo: `sa.text("1")` y `sa.true()` emiten los dos
    `DEFAULT 1` y se comportan igual. PostgreSQL es estricto y aborta con
    *"column is of type boolean but default expression is of type integer"* —
    o sea que la migracion no corre y **la instancia no arranca**.

    Es real, no hipotetico: el 2026-08-08 la revision 0007 freno el gate
    PostgreSQL del piloto con `es_tecnico BOOLEAN DEFAULT 1 NOT NULL`, con las
    otras 480 pruebas de la suite en verde. La forma correcta es `sa.true()` /
    `sa.false()`, que se compilan segun el dialecto.

    **Esto no reemplaza al gate contra PostgreSQL real** — ese es
    `test_database_backend.py::test_application_starts_against_postgres`, que
    corre la cadena de verdad en CI. Renderizar no ejecuta, asi que ve errores
    de compilacion del DDL y no de semantica. Este test existe para que esta
    clase concreta —la que ya costo una corrida de CI— se vea en segundos y
    localmente, sin PostgreSQL instalado.
    """
    sql = _sql_de_la_cadena(monkeypatch, "postgresql+psycopg://u:p@localhost:5432/x")

    ofensores = _BOOLEANO_CON_DEFAULT_ENTERO.findall(sql)

    assert ofensores == [], (
        "estas columnas booleanas llevan un default entero, que PostgreSQL "
        f"rechaza: {ofensores}. Usar `sa.true()`/`sa.false()`, que se compilan "
        "segun el dialecto (1/0 en SQLite, true/false en PostgreSQL)."
    )


def test_el_render_postgres_realmente_mira_la_cadena(monkeypatch):
    """La contraprueba del test de arriba.

    Sin esto, aquel assert pasaria igual si el render devolviera vacio, si la
    URL cayera de vuelta a SQLite, o si el regex no matcheara nunca — tres
    formas distintas de dar verde sin haber mirado nada. Se exige que el SQL sea
    efectivamente de PostgreSQL (`SERIAL`, que el dialecto SQLite no emite), que
    las cuatro banderas aparezcan en el render, y que el regex sepa encontrar el
    defecto cuando esta presente.
    """
    sql = _sql_de_la_cadena(monkeypatch, "postgresql+psycopg://u:p@localhost:5432/x")

    assert "SERIAL" in sql.upper()
    for bandera in ("es_tecnico", "es_recepcionista", "es_vendedor", "es_responsable"):
        assert f"{bandera} BOOLEAN DEFAULT" in sql, f"falta {bandera} en el render"

    assert _BOOLEANO_CON_DEFAULT_ENTERO.findall(
        "ALTER TABLE tecnicos ADD COLUMN es_tecnico BOOLEAN DEFAULT 1 NOT NULL;"
    ) == [("es_tecnico", "1")]
