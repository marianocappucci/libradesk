"""`cotizaciones`: cuántos pesos vale un dólar cada día.

Sale del pedido del humano del 2026-09-09, después de probar el sistema con
Lagrace: facturan en pesos y en dólares, y *"tiene que poder cargarse la
cotización del dólar"*.

🔑 **La tabla guarda el valor por fecha; el comprobante guarda el que USÓ.** Son
dos cosas distintas y las dos hacen falta. Esta tabla es la fuente que la
pantalla ofrece al armar la pre-factura; una vez armada, la cotización queda
**congelada adentro del comprobante** (en el JSON de sus ítems). Si no se
congelara, reimprimir en diciembre una factura de agosto le cambiaría el total
—la convertiría al dólar de diciembre—, que es exactamente el error que este
producto ya evitó una vez con `contratos_precios`, donde un precio nunca se
sobrescribe.

**`fecha` es UNIQUE: una cotización por día.** Cargarla dos veces el mismo día
es corregirla, no agregar una segunda. Y como el comprobante ya congeló la que
usó, corregir la de hoy **no le mueve el total a nada que ya se haya emitido**.

**`valor` con cuatro decimales** y no dos: el tipo de cambio se publica con más
precisión que un precio, y redondear a dos acá arrastra el error a cada
renglón convertido.
"""
import sqlalchemy as sa
from alembic import op

revision = "0039_cotizaciones"
down_revision = "0038_caja_movimientos_anulado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cotizaciones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("valor", sa.Numeric(12, 4), nullable=False),
        sa.Column("usuario", sa.String(255), nullable=False, server_default="Sistema"),
        sa.Column("observaciones", sa.Text(), nullable=True),
        # `nullable=False`: el modelo lo declara `Mapped[datetime]` sin `| None`,
        # asi que `create_all()` lo crea NOT NULL. Un `nullable=True` aca deja
        # la cadena y los modelos describiendo tablas distintas, que es lo que
        # mide `test_alembic_construye_lo_mismo_que_create_all`.
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("fecha", name="uq_cotizacion_fecha"),
    )
    # Se consulta **siempre** por fecha —la del día, o la última anterior— y
    # nunca por id. El índice va descendente porque la pregunta real es "la más
    # reciente hasta esta fecha", que es un `ORDER BY fecha DESC LIMIT 1`.
    op.create_index("ix_cotizaciones_fecha", "cotizaciones", ["fecha"])


def downgrade() -> None:
    op.drop_index("ix_cotizaciones_fecha", table_name="cotizaciones")
    op.drop_table("cotizaciones")
