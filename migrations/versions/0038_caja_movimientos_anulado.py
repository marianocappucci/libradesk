"""`caja_movimientos.anulado`, que LibraDesk no tenía y el motor ya consulta.

Un movimiento de caja **se anula, no se borra** desde [[libracore]] `v1.57.x`:
borrar dejaba el arqueo con un agujero que nadie puede auditar. La columna la
agrega `init_core_schema()` de forma idempotente… pero **LibraDesk no lo llama**:
lleva su propia copia del DDL de `caja_movimientos` en `app/services/comercial.py`
y su propia cadena de migraciones.

El resultado es una incompatibilidad latente: catorce consultas del motor
—`saldo()` de cuenta corriente entre ellas— filtran por `cm.anulado`, y contra
una base de LibraDesk mueren con *"column cm.anulado does not exist"*. No se veía
porque este producto estaba pineado a `v1.51.0`; apareció al bumpear a `v1.60.1`,
y en cuatro tests que tocan cuenta corriente y remitos.

**No es una decisión de producto sino ponerse al día con el motor**: la columna
entra con el mismo tipo y el mismo default que la del core, así que las filas que
ya existen quedan como "no anuladas", que es lo que son.
"""
import sqlalchemy as sa
from alembic import op

revision = "0038_caja_movimientos_anulado"
down_revision = "0037_created_at_hora_ar"
branch_labels = None
depends_on = None


def _columnas(bind) -> set[str] | None:
    """Las columnas de `caja_movimientos`, o `None` si la tabla no existe.

    🔴 Sobre una base VACIA la tabla todavia no esta: la crea el DDL de
    `app/services/comercial.py`, que corre al arrancar la app y no en esta
    cadena. `get_columns()` a secas tira `NoSuchTableError` y aborta el upgrade
    entero -- que es lo que pasa en un alta, donde las migraciones corren ANTES
    del primer arranque. Ahi no hay nada que agregar: la tabla va a nacer con la
    columna puesta.
    """
    from alembic import context

    # 🔴 En modo OFFLINE (`alembic upgrade --sql`, que es como se RENDERIZA la
    # cadena sin base) no hay nada que inspeccionar: el bind no ejecuta. Sin esta
    # salida la revision explota y se lleva puesto el render de la cadena
    # ENTERA, no solo el suyo. La corrida en linea --que es como despliega esta
    # familia-- anda igual, asi que el defecto solo aparece por el camino que
    # nadie mira hasta que lo necesita. Lo mismo le paso a la `0003` del motor.
    if context.is_offline_mode():
        return None

    inspector = sa.inspect(bind)
    if not inspector.has_table("caja_movimientos"):
        return None
    return {c["name"] for c in inspector.get_columns("caja_movimientos")}


def upgrade() -> None:
    bind = op.get_bind()
    columnas = _columnas(bind)
    if columnas is None or "anulado" in columnas:
        return
    op.add_column(
        "caja_movimientos",
        sa.Column("anulado", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    columnas = _columnas(bind)
    if columnas is None or "anulado" not in columnas:
        return
    op.drop_column("caja_movimientos", "anulado")
