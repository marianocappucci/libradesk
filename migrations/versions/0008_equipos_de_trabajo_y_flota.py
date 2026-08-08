"""equipos de trabajo y flota de vehiculos (pedido 42, fase A).

Tres tablas nuevas —`equipos_trabajo`, `equipos_trabajo_integrantes` y
`vehiculos`— mas una bandera de rol en el personal (`tecnicos.es_responsable`).

**Las tres tablas nuevas no tienen filo**: no hay `ALTER TABLE` crudo, no hay FK
agregada sobre datos y no se reconstruye nada; las FK viajan dentro del
`CREATE TABLE`, que es donde SQLite si las acepta.

> 🔴 **La bandera SI reconstruye `tecnicos`**, que tiene 9 filas en dev y 1 en el
> cliente. Va con `server_default=0` por el mismo motivo que las tres banderas
> de la 0007: `batch_alter_table` recrea la tabla copiando las filas, y sin
> default la columna `NOT NULL` quedaria en NULL y el upgrade fallaria **con
> datos**. El autogenerate no lo pone: hay que escribirlo.
>
> El default es **0** y no 1, a diferencia de `es_tecnico` en la 0007: nadie es
> responsable de un equipo hasta que alguien lo marque, y marcar a todos seria
> inventar una estructura que no existe.
>
> 🔴 Se escribe `sa.false()` y no `sa.text('0')` por el mismo motivo que las tres
> banderas de la 0007 — ver el docstring de esa revision. En SQLite las dos
> formas emiten `DEFAULT 0`; en PostgreSQL `BOOLEAN DEFAULT 0` no compila.

**No hay backfill.** Los equipos de trabajo no existen como dato: hasta hoy la
organizacion de las cuadrillas vivia fuera del sistema.
"""
from alembic import op
import sqlalchemy as sa

revision = '0008_equipos_de_trabajo_y_flota'
down_revision = '0007_roles_y_modalidad'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tecnicos', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'es_responsable', sa.Boolean(), nullable=False, server_default=sa.false(),
        ))

    op.create_table(
        'equipos_trabajo',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('responsable_id', sa.Integer(), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['responsable_id'], ['tecnicos.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nombre'),
    )
    with op.batch_alter_table('equipos_trabajo', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_equipos_trabajo_responsable_id'), ['responsable_id'], unique=False,
        )

    op.create_table(
        'equipos_trabajo_integrantes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('equipo_id', sa.Integer(), nullable=False),
        sa.Column('tecnico_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['equipo_id'], ['equipos_trabajo.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tecnico_id'], ['tecnicos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # Sobre el PAR: la misma persona puede estar en dos equipos, pero no dos
        # veces en el mismo.
        sa.UniqueConstraint('equipo_id', 'tecnico_id'),
    )
    with op.batch_alter_table('equipos_trabajo_integrantes', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_equipos_trabajo_integrantes_equipo_id'), ['equipo_id'], unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_equipos_trabajo_integrantes_tecnico_id'), ['tecnico_id'], unique=False,
        )

    op.create_table(
        'vehiculos',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('patente', sa.String(length=20), nullable=False),
        sa.Column('marca', sa.String(length=100), nullable=True),
        sa.Column('modelo', sa.String(length=100), nullable=True),
        sa.Column('anio', sa.Integer(), nullable=True),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('equipo_id', sa.Integer(), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['equipo_id'], ['equipos_trabajo.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('patente'),
    )
    with op.batch_alter_table('vehiculos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_vehiculos_equipo_id'), ['equipo_id'], unique=False)


def downgrade():
    with op.batch_alter_table('vehiculos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_vehiculos_equipo_id'))
    op.drop_table('vehiculos')

    with op.batch_alter_table('equipos_trabajo_integrantes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_equipos_trabajo_integrantes_tecnico_id'))
        batch_op.drop_index(batch_op.f('ix_equipos_trabajo_integrantes_equipo_id'))
    op.drop_table('equipos_trabajo_integrantes')

    with op.batch_alter_table('equipos_trabajo', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_equipos_trabajo_responsable_id'))
    op.drop_table('equipos_trabajo')

    with op.batch_alter_table('tecnicos', schema=None) as batch_op:
        batch_op.drop_column('es_responsable')
