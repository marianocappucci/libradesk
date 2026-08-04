"""roles del personal y modalidad de la incidencia (pedidos 41 y 37).

**Pedido 41** — que se vea quién recepciona el ticket (puede ser un
recepcionista), quién lo ejecuta (un técnico) y poder manejar vendedores. Los
tres papeles salen del **mismo catálogo** (`tecnicos`, que pasa a ser el personal
de la empresa) con tres banderas independientes: en una empresa chica la misma
persona recepciona y ejecuta, y un único campo `rol` obligaría a cargarla dos
veces y a partir su historial. Ver `app/services/tecnicos.py`.

**Pedido 37** — `incidencias.modalidad` (`on_site` | `remoto`). Nullable y sin
default: los 23 tickets que ya existen no saben cómo se atendieron, y ponerles
`on_site` sería inventar el dato.

> 🔴 **Lo que el autogenerate hacía mal, y habría reventado en producción.**
> Emitía `add_column(sa.Column('es_tecnico', sa.Boolean(), nullable=False))`
> **sin `server_default`**. `batch_alter_table` reconstruye la tabla copiando
> las filas, así que las 3 columnas nuevas quedarían en NULL sobre una columna
> `NOT NULL` — falla con datos, y `tecnicos` tiene 1 fila en el cliente y 5 en
> dev. Se agregan con `server_default` y por eso la copia entra sin backfill
> aparte.
>
> El default de `es_tecnico` es **1**, no 0: las filas que ya existen eran
> técnicos por definición —la tabla no servía para otra cosa— así que quedan
> descritas igual que antes. Los otros dos arrancan en 0.
>
> El downgrade también venía mal: `drop_constraint(None, ...)` no puede
> ejecutarse. Las FK van con nombre explícito.
"""
from alembic import op
import sqlalchemy as sa

revision = '0007_roles_y_modalidad'
down_revision = '0006_activos_en_service'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tecnicos', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'es_tecnico', sa.Boolean(), nullable=False, server_default=sa.text('1'),
        ))
        batch_op.add_column(sa.Column(
            'es_recepcionista', sa.Boolean(), nullable=False, server_default=sa.text('0'),
        ))
        batch_op.add_column(sa.Column(
            'es_vendedor', sa.Boolean(), nullable=False, server_default=sa.text('0'),
        ))

    with op.batch_alter_table('incidencias', schema=None) as batch_op:
        batch_op.add_column(sa.Column('recepcionista_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('vendedor_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('modalidad', sa.String(length=20), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_incidencias_modalidad'), ['modalidad'], unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_incidencias_recepcionista_id'), ['recepcionista_id'], unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_incidencias_vendedor_id'), ['vendedor_id'], unique=False,
        )
        batch_op.create_foreign_key(
            'fk_incidencias_recepcionista_id', 'tecnicos', ['recepcionista_id'], ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_incidencias_vendedor_id', 'tecnicos', ['vendedor_id'], ['id'],
            ondelete='SET NULL',
        )


def downgrade():
    with op.batch_alter_table('incidencias', schema=None) as batch_op:
        batch_op.drop_constraint('fk_incidencias_vendedor_id', type_='foreignkey')
        batch_op.drop_constraint('fk_incidencias_recepcionista_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_incidencias_vendedor_id'))
        batch_op.drop_index(batch_op.f('ix_incidencias_recepcionista_id'))
        batch_op.drop_index(batch_op.f('ix_incidencias_modalidad'))
        batch_op.drop_column('modalidad')
        batch_op.drop_column('vendedor_id')
        batch_op.drop_column('recepcionista_id')

    with op.batch_alter_table('tecnicos', schema=None) as batch_op:
        batch_op.drop_column('es_vendedor')
        batch_op.drop_column('es_recepcionista')
        batch_op.drop_column('es_tecnico')
