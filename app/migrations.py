"""Migraciones de schema para la parte SQLAlchemy de LibraDesk.

**Por que existe esto y no Alembic.** LibraDesk crea su schema con
`Base.metadata.create_all()`, que **no altera tablas existentes**: un
`mapped_column` nuevo aparece solo en las bases que se crean desde cero.
Sin algo asi, una columna nueva nunca llegaria a la base de produccion
(`compulibra`), que existe desde la migracion del Node.js viejo.

Alembic es el destino natural (Gestiolibra ya lo tiene configurado), pero
traerlo implica versionar el schema actual como baseline en las dos
instancias — cambio propio, con su propio deploy. Mientras tanto esto
cubre el caso real y unico que hay: agregar columnas nullable.

**Idempotente y sin destino fijo**: se corre en cada arranque, mira el
schema real (`PRAGMA table_info`) y solo agrega lo que falta. En una base
nueva `create_all()` ya dejo todo, asi que no hace nada.

Dos limites de `ALTER TABLE ADD COLUMN` en SQLite que condicionan lo que
se puede migrar por aca: la columna tiene que admitir NULL (o traer un
default no nulo), y **no se puede crear el indice en la misma sentencia**
— por eso los indices van aparte, con el mismo nombre que genera
SQLAlchemy (`ix_<tabla>_<columna>`), para que una base migrada y una
creada desde cero queden identicas.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

# (tabla, columna, DDL del tipo, ¿indexar?)
_COLUMNAS = [
    (
        "equipos_movimientos",
        "incidencia_id",
        # Sin ON DELETE: el pragma `foreign_keys` esta APAGADO en las
        # conexiones de SQLAlchemy (medido, no supuesto), asi que un
        # `ON DELETE SET NULL` seria decorativo. El desenlace lo maneja
        # `IncidenciaRepository.delete()`, explicitamente.
        "INTEGER REFERENCES incidencias(id)",
        True,
    ),
    # Categoria del ticket ("Hardware -> Impresoras"), 2026-08-02. Apunta a la
    # hoja del catalogo; ver services/categorias.py. La tabla
    # `categorias_incidencia` es **nueva**, asi que la crea `create_all()` —
    # lo que hay que migrar es solo esta columna, sobre una tabla que ya
    # existe en las dos instancias.
    (
        "incidencias",
        "categoria_id",
        "INTEGER REFERENCES categorias_incidencia(id)",
        True,
    ),
    # CUIT y domicilio del cliente, 2026-08-02. Sin estos dos, los datos
    # fiscales se tipeaban a mano en cada remito y cada presupuesto.
    ("clientes", "cuit", "VARCHAR(20)", False),
    ("clientes", "domicilio", "VARCHAR(255)", False),
]


def _columnas_de(conn, tabla: str) -> set[str]:
    filas = conn.execute(text(f"PRAGMA table_info({tabla})")).all()
    return {fila[1] for fila in filas}


def run_migrations(engine: Engine) -> list[str]:
    """Aplica lo que falte y devuelve que hizo (para el log de arranque)."""
    aplicadas: list[str] = []
    with engine.begin() as conn:
        for tabla, columna, tipo_ddl, indexar in _COLUMNAS:
            if not _columnas_de(conn, tabla):
                continue  # la tabla todavia no existe: create_all() la creara completa
            if columna in _columnas_de(conn, tabla):
                continue
            conn.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo_ddl}"))
            if indexar:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS ix_{tabla}_{columna} ON {tabla} ({columna})"
                ))
            aplicadas.append(f"{tabla}.{columna}")
    return aplicadas
