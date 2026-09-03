"""baseline: el schema propio de LibraDesk tal como estaba antes de Alembic.

**No es una migracion: es una foto.** Las dos instancias que ya existian
(`libradesk-dev` y `libradesk-compulibra`) tienen estas 9 tablas creadas desde
antes, asi que esta revision no llega a ejecutarse en ellas — `ensure_schema()`
las stampea aca y sigue. Corre de verdad solo en bases nuevas.

**Generada con `--autogenerate` contra una base vacia**, no escrita a mano: asi
el DDL sale de los modelos y no de una transcripcion. Verificado despues, el
2026-08-03, contra las bases reales del VPS: la radiografia (columnas, tipos,
nullability, PK, FKs e indices, via PRAGMA) de una base construida por
`alembic upgrade head` resulto **identica** a la de `compulibra` y a la de
`dev`.

Esa comparacion es por PRAGMA y no por texto de DDL a proposito. En produccion,
`equipos_movimientos.incidencia_id` la agrego un `ALTER TABLE` a mano, que deja
`incidencia_id INTEGER REFERENCES incidencias(id)` inline, mientras
`create_all()` emite la misma FK como `FOREIGN KEY(...)` al final del
`CREATE TABLE`. Es la misma constraint escrita distinto: comparar el texto daria
un rojo que no corresponde.
"""
import sqlalchemy as sa
from alembic import op

revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('clientes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('nombre', sa.String(length=255), nullable=False),
    sa.Column('empresa', sa.String(length=255), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('telefono', sa.String(length=20), nullable=True),
    sa.Column('ciudad', sa.String(length=100), nullable=True),
    sa.Column('observaciones', sa.Text(), nullable=True),
    sa.Column('tipo_facturacion', sa.String(length=20), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('modulos',
    sa.Column('modulo', sa.String(), nullable=False),
    sa.Column('habilitado', sa.Boolean(), nullable=False),
    sa.Column('plan', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('modulo')
    )
    op.create_table('tecnicos',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nombre')
    )
    op.create_table('equipos',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('cliente_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=100), nullable=False),
    sa.Column('modelo', sa.String(length=255), nullable=True),
    sa.Column('marca', sa.String(length=255), nullable=True),
    sa.Column('serial', sa.String(length=255), nullable=True),
    sa.Column('ubicacion_oficina', sa.String(length=255), nullable=True),
    sa.Column('sector', sa.String(length=255), nullable=True),
    sa.Column('estado', sa.String(length=50), nullable=False),
    sa.Column('fecha_adicion', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('garantia_vence', sa.Date(), nullable=True),
    sa.Column('observaciones', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('equipos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_equipos_cliente_id'), ['cliente_id'], unique=False)

    op.create_table('sectores',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('cliente_id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cliente_id', 'nombre')
    )
    with op.batch_alter_table('sectores', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sectores_cliente_id'), ['cliente_id'], unique=False)

    op.create_table('incidencias',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('cliente_id', sa.Integer(), nullable=False),
    sa.Column('equipo_id', sa.Integer(), nullable=True),
    sa.Column('tecnico_id', sa.Integer(), nullable=True),
    sa.Column('sector_id', sa.Integer(), nullable=True),
    sa.Column('titulo', sa.String(length=255), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=True),
    sa.Column('estado', sa.String(length=50), nullable=False),
    sa.Column('prioridad', sa.String(length=20), nullable=False),
    sa.Column('horas_invertidas', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('notas', sa.Text(), nullable=True),
    sa.Column('resolucion', sa.Text(), nullable=True),
    sa.Column('estado_facturacion', sa.String(length=20), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('fecha_cierre', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['equipo_id'], ['equipos.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sector_id'], ['sectores.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tecnico_id'], ['tecnicos.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('incidencias', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_incidencias_cliente_id'), ['cliente_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_incidencias_equipo_id'), ['equipo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_incidencias_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_incidencias_fecha_creacion'), ['fecha_creacion'], unique=False)

    op.create_table('actividades_incidencia',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('incidencia_id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=True),
    sa.Column('usuario', sa.String(length=100), nullable=True),
    sa.ForeignKeyConstraint(['incidencia_id'], ['incidencias.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('actividades_incidencia', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_actividades_incidencia_incidencia_id'), ['incidencia_id'], unique=False)

    op.create_table('equipos_movimientos',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('equipo_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=50), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=True),
    sa.Column('sector_origen', sa.String(length=255), nullable=True),
    sa.Column('sector_destino', sa.String(length=255), nullable=True),
    sa.Column('ubicacion_origen', sa.String(length=255), nullable=True),
    sa.Column('ubicacion_destino', sa.String(length=255), nullable=True),
    sa.Column('motivo', sa.String(length=500), nullable=True),
    sa.Column('usuario', sa.String(length=255), nullable=False),
    sa.Column('fecha', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('incidencia_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['equipo_id'], ['equipos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['incidencia_id'], ['incidencias.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('equipos_movimientos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_equipos_movimientos_equipo_id'), ['equipo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_equipos_movimientos_incidencia_id'), ['incidencia_id'], unique=False)

    op.create_table('incidencias_estados_log',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('incidencia_id', sa.Integer(), nullable=False),
    sa.Column('estado_anterior', sa.String(length=50), nullable=True),
    sa.Column('estado_nuevo', sa.String(length=50), nullable=False),
    sa.Column('fecha', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('tecnico', sa.String(length=100), nullable=True),
    sa.ForeignKeyConstraint(['incidencia_id'], ['incidencias.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('incidencias_estados_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_incidencias_estados_log_incidencia_id'), ['incidencia_id'], unique=False)


def downgrade():
    # Se conserva por completitud de la cadena, pero bajar de aca deja la base
    # sin el dominio propio: no es una vuelta atras util en produccion.
    with op.batch_alter_table('incidencias_estados_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_incidencias_estados_log_incidencia_id'))

    op.drop_table('incidencias_estados_log')
    with op.batch_alter_table('equipos_movimientos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_equipos_movimientos_incidencia_id'))
        batch_op.drop_index(batch_op.f('ix_equipos_movimientos_equipo_id'))

    op.drop_table('equipos_movimientos')
    with op.batch_alter_table('actividades_incidencia', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_actividades_incidencia_incidencia_id'))

    op.drop_table('actividades_incidencia')
    with op.batch_alter_table('incidencias', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_incidencias_fecha_creacion'))
        batch_op.drop_index(batch_op.f('ix_incidencias_estado'))
        batch_op.drop_index(batch_op.f('ix_incidencias_equipo_id'))
        batch_op.drop_index(batch_op.f('ix_incidencias_cliente_id'))

    op.drop_table('incidencias')
    with op.batch_alter_table('sectores', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sectores_cliente_id'))

    op.drop_table('sectores')
    with op.batch_alter_table('equipos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_equipos_cliente_id'))

    op.drop_table('equipos')
    op.drop_table('tecnicos')
    op.drop_table('modulos')
    op.drop_table('clientes')
