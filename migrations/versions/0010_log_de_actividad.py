"""log de actividad (`actividad_log`).

Una fila por creación, edición o borrado de cualquier entidad auditable, con
quién lo hizo y qué cambió. La escribe el `flush` de SQLAlchemy, no los
repositorios — ver `app/services/auditoria.py` para por qué.

**Tabla nueva y nada más**: no toca ninguna tabla existente, no migra datos y no
tiene backfill posible. Lo que pasó antes de esta revisión no quedó registrado
en ningún lado, así que el log arranca vacío y desde hoy. Es lo esperable de un
log de auditoría; inventarle filas históricas a partir de los `fecha_creacion`
de cada tabla habría producido un log que *parece* completo y no lo es, que es
peor que uno que declara desde cuándo empieza.

`auth_log` (accesos) **no está acá**: la crea `libraauth` con
`Base.metadata.create_all()`, igual que `usuarios` — su schema lo versiona el
motor, no este producto.

Los tres índices son los de las tres columnas por las que filtra la pantalla
(`ts`, `accion`, `entidad`). En una tabla que sólo crece y se lee ordenada por
fecha, el que importa es el de `ts`.
"""
import sqlalchemy as sa
from alembic import op

revision = '0010_log_de_actividad'
down_revision = '0009_agenda_de_equipos'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'actividad_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ts', sa.DateTime(), nullable=False),
        sa.Column('usuario', sa.String(length=100), nullable=False),
        sa.Column('accion', sa.String(length=20), nullable=False),
        sa.Column('entidad', sa.String(length=50), nullable=False),
        # Nullable: un borrado deja el id de la fila que se fue, pero nada
        # garantiza que toda entidad auditable tenga uno al momento de anotarla.
        sa.Column('entidad_id', sa.Integer(), nullable=True),
        sa.Column('descripcion', sa.String(length=500), nullable=False),
        # JSON en texto: cada entidad tiene sus propias columnas y no se filtra
        # por adentro de este campo, sólo se muestra.
        sa.Column('cambios', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_actividad_log_ts'), 'actividad_log', ['ts'], unique=False)
    op.create_index(op.f('ix_actividad_log_accion'), 'actividad_log', ['accion'], unique=False)
    op.create_index(op.f('ix_actividad_log_entidad'), 'actividad_log', ['entidad'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_actividad_log_entidad'), table_name='actividad_log')
    op.drop_index(op.f('ix_actividad_log_accion'), table_name='actividad_log')
    op.drop_index(op.f('ix_actividad_log_ts'), table_name='actividad_log')
    op.drop_table('actividad_log')
