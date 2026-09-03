"""Catalogo de servicios reutilizables en remitos y presupuestos.

Tabla nueva y nada mas: no toca ninguna existente y no migra datos. Los
comprobantes que ya existen no la referencian y no van a hacerlo — guardan su
propia descripcion y su propio precio, para que cambiar el catalogo no le
cambie el total a un presupuesto ya enviado. Ver `app/services/servicios.py`.

Arranca vacia. No hay de donde sacar un catalogo inicial: hasta ahora cada item
se retipeaba a mano en cada comprobante, asi que lo unico que existe son textos
sueltos dentro de presupuestos viejos, sin precio canonico ni forma de saber
cuales eran "el mismo" servicio.
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_servicios"
down_revision = "0011_ingresos_reparacion"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "servicios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.String(500), nullable=False, server_default=""),
        # Numeric y no Float: es plata. Ver el comentario en el modelo.
        sa.Column("precio", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        # `nullable=False` y `sa.text('(CURRENT_TIMESTAMP)')`, igual que el
        # resto de las migraciones de este producto: el modelo declara
        # `Mapped[datetime]` (no opcional), y si la migracion lo dejara
        # nullable los dos caminos divergirian —lo caza
        # `test_alembic_construye_lo_mismo_que_create_all`.
        sa.Column("created_at", sa.DateTime(),
                  server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
    )
    # El buscador filtra por nombre y por descripcion; el indice cubre el
    # ordenamiento y el caso mas comun.
    op.create_index("ix_servicios_nombre", "servicios", ["nombre"])
    op.create_index("ix_servicios_activo", "servicios", ["activo"])


def downgrade():
    op.drop_index("ix_servicios_activo", table_name="servicios")
    op.drop_index("ix_servicios_nombre", table_name="servicios")
    op.drop_table("servicios")
