"""`envios_facturacion.intento`: cuántas veces hubo que volver a mandar un
comprobante que borraron del otro lado.

Sale del pedido del humano del 2026-09-10, mirando "Enviar a facturar" en
`lagrace`: tres remitos cuyas ventas se borraron en SOS Contador mostraban
"Ya no está allá", y la idea era poder mandarlos de nuevo.

🔴 **No se podía, aunque el checkbox dejara.** SOS desduplica por `uniqueid`, y
ese id **queda quemado aunque la venta se borre**. El `uniqueid` sale de
`(instancia, origen_tipo, origen_id)`, así que el reenvío llevaba el mismo, SOS
contestaba `-1` y el puente lo registraba `resuelto_remoto` — "Resuelto allá",
en verde, sobre un remito que no había llegado a ningún lado.

Esta columna entra en la semilla del `uniqueid` a partir del 1 (ver
`facturacion_sos.uniqueid_de`). **El 0 es la semilla de siempre**, así que las
filas existentes conservan el `uniqueid` con el que se mandaron.

`server_default` además del `default` del modelo, por lo mismo que el resto de
la tabla: una base creada por `create_all()` y una creada por esta migración
tienen que coincidir.
"""
import sqlalchemy as sa
from alembic import op

revision = "0041_intento_de_envio"
down_revision = "0040_tecnicos_del_reclamo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "envios_facturacion",
        sa.Column("intento", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("envios_facturacion", "intento")
