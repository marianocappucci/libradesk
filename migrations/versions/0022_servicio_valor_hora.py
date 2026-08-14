"""Cuál de los servicios del catálogo es la hora de trabajo.

Hasta acá el remito que se generaba de un reclamo salía con **la mano de obra en
cero**: el producto no tenía el valor hora en ningún lado, así que el operador
tenía que escribirlo a mano en cada remito. Con reclamos agrupados —tres visitas
del mes en un solo remito— eso es tres veces el mismo número tipeado a mano, y
cualquiera de las tres puede salir distinta.

## Por qué en `servicios` y no en una tabla de configuración

El catálogo de servicios ya es un nombre, un precio y una alícuota, con ABM
propio y pestaña en Configuración. Una tabla nueva de un solo número habría
necesitado migración, endpoint y pantalla para guardar menos de lo que esta fila
ya guarda — y el valor hora habría quedado en un lugar distinto del resto de los
precios del producto.

## Por qué no hay un índice único parcial

La regla "uno solo marcado" la aplica `ServicioRepository`, desmarcando al resto
en la misma transacción. Un índice único parcial se declara distinto en SQLite y
en PostgreSQL, y este producto corre contra los dos (`LibraEdge` aparte): sería
una constraint que existe en un motor con una forma y en el otro con otra, para
proteger un invariante que de todos modos hay que sostener en el código, porque
la pantalla necesita poder mover la marca de un servicio a otro sin un estado
intermedio con dos.

## `NOT NULL` con `server_default`

Como `activo`: el `server_default` es lo que ve la base al agregar la columna
sobre las filas que ya existen, y el `default` de Python lo que pone una fila
nueva. Declarar sólo uno hace que una base creada por `create_all()` no coincida
con una creada por esta migración, y eso lo caza
`test_alembic_construye_lo_mismo_que_create_all`.
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_servicio_valor_hora"
down_revision = "0021_incidencia_remito_id"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "servicios",
        sa.Column(
            "es_valor_hora", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index("ix_servicios_es_valor_hora", "servicios", ["es_valor_hora"])


def downgrade():
    op.drop_index("ix_servicios_es_valor_hora", table_name="servicios")
    op.drop_column("servicios", "es_valor_hora")
