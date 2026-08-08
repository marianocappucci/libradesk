"""Registro local de lo que se mando a facturar afuera.

Tabla nueva y nada mas: no toca ninguna existente y no migra datos.

Los remitos y presupuestos **no viven en el schema de este producto** —son de
`libracore.db.remitos_presupuestos`, compartidos con el resto de la familia—,
asi que marcar el envio con una columna en esas tablas significaria tocar el
schema del motor por una necesidad de un solo consumidor. Esta tabla es de
LibraDesk y apunta al comprobante por `(origen_tipo, origen_id)`, el mismo par
con el que la bandeja de Contalibra lo identifica del otro lado.

Arranca vacia: hasta ahora no habia forma de mandar nada.
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_envios_facturacion"
down_revision = "0013_iva_por_item"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "envios_facturacion",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # 'remito' | 'presupuesto'. Se deja como texto libre —validado en el
        # servicio— porque las fases 2 y 4 del modulo de alquileres suman
        # 'cuota_contrato' e 'incidencia' sin tocar la tabla.
        sa.Column("origen_tipo", sa.String(30), nullable=False),
        sa.Column("origen_id", sa.Integer(), nullable=False),
        # 'enviado' | 'resuelto_remoto' | 'error'.
        sa.Column("estado", sa.String(20), nullable=False, server_default="enviado"),
        # El id que la bandeja de Contalibra le dio. Es con lo que la fase E va
        # a poder preguntar en que quedo.
        sa.Column("comprobante_remoto_id", sa.Integer(), nullable=True),
        # El texto del error o del rechazo, para que la pantalla pueda decir
        # que paso sin que nadie mire los logs del contenedor.
        sa.Column("detalle", sa.String(500), nullable=False, server_default=""),
        sa.Column("enviado_at", sa.DateTime(),
                  server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("actualizado_at", sa.DateTime(),
                  server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        # Un comprobante tiene UN envio. Reenviarlo actualiza la fila, no agrega
        # otra: del otro lado la bandeja tambien es idempotente por este mismo
        # par, asi que dos filas aca describirian una sola alla.
        #
        # Va DENTRO del create_table y no como `op.create_unique_constraint()`
        # aparte: eso ultimo es un ALTER, y SQLite no soporta ALTER de
        # constraints — alembic levanta NotImplementedError y **no falla solo
        # esta migracion, falla el arranque de la app entera**, que es como se
        # descubrio (409 errores en la suite, ninguno relacionado con esta
        # tabla).
        sa.UniqueConstraint("origen_tipo", "origen_id",
                            name="uq_envios_facturacion_origen"),
    )
    # La consulta caliente: la pantalla abre listando lo que fallo y lo que
    # todavia no se resolvio.
    op.create_index("ix_envios_facturacion_estado", "envios_facturacion", ["estado"])


def downgrade():
    op.drop_index("ix_envios_facturacion_estado", table_name="envios_facturacion")
    op.drop_table("envios_facturacion")
