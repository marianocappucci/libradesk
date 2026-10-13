"""Se retiran los restos del resumen de cuenta corriente por mail: la revisión `0042`.

La tabla `cc_resumenes_enviados` la creaba `comercial.ensure_schema()` y las tres columnas
`clients.cc_resumen_*` las trajo la `0017`. Ni el modelo ni el DDL copiado las declaran ya; la
`0042` las saca de las bases que las tienen, y tiene que poder repetirse y convivir con la `0024`
de LibraCore (que hace lo mismo con `IF EXISTS`). Que el modelo y la cadena no se separen lo
cubre `test_alembic.py::test_los_modelos_no_se_separan_de_la_cadena`; acá se mide el borrado.
"""
import re
import zlib

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from app.schema import _config as alembic_config

REVISION = "0042_retirar_cc_resumen"
ANTERIOR = "0041_intento_de_envio"
COLUMNAS = {"cc_resumen_auto", "cc_resumen_frecuencia", "cc_resumen_ultimo_envio"}

# La tabla como la dejaba `comercial.ensure_schema()` antes de este cambio.
_TABLA_VIEJA = """
CREATE TABLE cc_resumenes_enviados (
    id            SERIAL PRIMARY KEY,
    cliente_id    INTEGER NOT NULL,
    fecha         TEXT NOT NULL,
    periodo_desde TEXT NOT NULL,
    periodo_hasta TEXT NOT NULL,
    saldo         NUMERIC NOT NULL DEFAULT 0,
    email         TEXT DEFAULT '',
    estado        TEXT NOT NULL DEFAULT 'ok',
    detalle       TEXT DEFAULT '',
    automatico    INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT
)
"""


@pytest.fixture
def engine(tmp_path):
    from conftest import _borrar_base, _sql_admin, _url_de

    crudo = re.sub(r"[^a-z0-9_]", "_", f"{tmp_path.name}_cc_resumen".lower())
    base = f"lda_{zlib.crc32(crudo.encode()):08x}_{crudo[-28:]}"[:60]
    _sql_admin(f'DROP DATABASE IF EXISTS "{base}"', f'CREATE DATABASE "{base}"')
    eng = create_engine(_url_de(base))
    yield eng
    eng.dispose()
    _borrar_base(base)


def _a(engine, revision):
    with engine.begin() as conn:
        command.upgrade(alembic_config(conn), revision)


def _stamp(engine, revision):
    with engine.begin() as conn:
        command.stamp(alembic_config(conn), revision)


def _columnas(engine):
    with engine.connect() as conn:
        return {r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'clients'"))}


def _hay_tabla(engine):
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'cc_resumenes_enviados'")).fetchone() is not None


def _base_con_restos(engine):
    """Una instancia como la de hoy: la cadena en la `0041` (con las tres columnas, por la `0017`),
    la tabla del DDL copiado, un cliente y un resumen enviado."""
    _a(engine, ANTERIOR)
    with engine.begin() as conn:
        conn.execute(text(_TABLA_VIEJA))
        conn.execute(text(
            "INSERT INTO clients (name, tipo_facturacion, cc_resumen_auto, cc_resumen_frecuencia) "
            "VALUES ('Cliente Ficticio', 'por_servicio', 1, 'semanal')"))
        conn.execute(text(
            "INSERT INTO cc_resumenes_enviados (cliente_id, fecha, periodo_desde, periodo_hasta) "
            "VALUES (1, '2026-09-01', '2026-08-01', '2026-08-31')"))
    assert _hay_tabla(engine) and COLUMNAS <= _columnas(engine), "la base de partida tiene que traer los restos"


def test_la_0042_borra_la_tabla_y_las_tres_columnas_y_no_toca_a_los_clientes(engine):
    _base_con_restos(engine)
    _a(engine, REVISION)

    assert not _hay_tabla(engine)
    assert not COLUMNAS & _columnas(engine)
    assert {"name", "cuit_dni", "auto_facturar", "external_ref"} <= _columnas(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM clients")).fetchall() == [("Cliente Ficticio",)]


def test_la_0042_es_idempotente(engine):
    _base_con_restos(engine)
    _a(engine, REVISION)
    # Estampar la anterior y repetir: no hay nada que borrar y no tiene que fallar.
    _stamp(engine, ANTERIOR)
    _a(engine, REVISION)
    assert not _hay_tabla(engine) and not COLUMNAS & _columnas(engine)


def test_la_0042_no_pisa_lo_que_ya_hizo_la_0024_del_motor(engine):
    """Con las dos cadenas en la misma base, quien llega segundo no encuentra nada."""
    _base_con_restos(engine)
    with engine.begin() as conn:
        # Lo que hace la `0024` de LibraCore.
        conn.execute(text("DROP TABLE IF EXISTS cc_resumenes_enviados"))
        for columna in COLUMNAS:
            conn.execute(text(f"ALTER TABLE clients DROP COLUMN IF EXISTS {columna}"))
    _a(engine, REVISION)
    assert not _hay_tabla(engine) and not COLUMNAS & _columnas(engine)


def test_bajar_la_0042_devuelve_las_columnas_vacias_para_que_la_0017_pueda_bajar(engine):
    _base_con_restos(engine)
    _a(engine, REVISION)
    with engine.begin() as conn:
        command.downgrade(alembic_config(conn), ANTERIOR)
    assert COLUMNAS <= _columnas(engine)
    with engine.connect() as conn:
        fila = conn.execute(text(
            "SELECT cc_resumen_auto, cc_resumen_frecuencia, cc_resumen_ultimo_envio FROM clients")).fetchone()
    assert tuple(fila) == (0, "mensual", ""), "las columnas vuelven con su default; los datos, no"
