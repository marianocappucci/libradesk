"""Configuracion del puente de facturacion, editable desde la pantalla.

Tabla nueva y una columna. No migra datos y **no cambia el comportamiento de
ninguna instancia existente**: mientras no haya fila para un destino, el
servicio sigue leyendo las variables de entorno como hasta ahora.

Los secretos van en `secretos_cifrados`, cifrados con una clave derivada de
`SECRET_KEY` (que vive en el entorno y no viaja en el respaldo). La columna es
texto porque guarda el token de Fernet, no el valor.

`envios_facturacion.destino` se agrega para poder mostrar a donde fue cada
envio ahora que hay mas de un destino posible. **No entra en la clave unica**:
la regla sigue siendo un comprobante = un envio, decidido con el humano el
2026-08-12. Las filas viejas quedan en 'contalibra', que es a donde fueron.
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_config_facturacion"
down_revision = "0015_entidad_id_texto"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "config_facturacion",
        # 'contalibra' | 'sos'. Una fila por destino, la PK es el nombre: no
        # hace falta un id sintetico para dos filas que no se borran.
        sa.Column("destino", sa.String(30), primary_key=True),
        # `sa.false()` y no "0": en SQLite los dos emiten DEFAULT 0 y se
        # comportan igual, pero PostgreSQL aborta con "column is of type boolean
        # but default expression is of type integer" y la instancia no arranca.
        sa.Column("habilitado", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        # JSON con lo NO secreto (url, usuario, punto de venta, letra...).
        sa.Column("parametros", sa.Text(), nullable=False, server_default="{}"),
        # JSON con lo secreto, cifrado entero. Vacio = sin credencial cargada.
        sa.Column("secretos_cifrados", sa.Text(), nullable=False, server_default=""),
        sa.Column("actualizado_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
    )

    # El largo va explicito y tiene que coincidir con el del modelo: en SQLite
    # un VARCHAR sin limite y uno con limite se comportan igual, asi que la
    # divergencia solo aparece en Postgres. Ya paso en esta misma tabla de
    # envios (ver el comentario de `origen_tipo` en facturacion_externa.py).
    op.add_column(
        "envios_facturacion",
        sa.Column("destino", sa.String(30), nullable=False,
                  server_default="contalibra"),
    )


def downgrade():
    op.drop_column("envios_facturacion", "destino")
    op.drop_table("config_facturacion")
