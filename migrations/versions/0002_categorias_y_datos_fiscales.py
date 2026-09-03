"""categorias de incidencia y datos fiscales del cliente.

**La primera migracion real de la cadena**, y la que muestra para que servia
traer Alembic. Estos tres cambios los habia escrito otra sesion, el 2026-08-02,
como entradas de `app/migrations.py` (`ALTER TABLE ADD COLUMN` a mano); al
retirarse ese modulo se convirtieron en esta revision. Cubren los pendientes 16
(datos fiscales del cliente) y 20 (categorias de incidencia) de la pagina del
wiki, que estaban frenados esperando justamente esto.

**`categorias_incidencia` es tabla nueva, y eso ahora importa.** Con
`create_all()` una tabla nueva aparecia sola —lo que no aparecia era una columna
nueva—, asi que la nota original decia que no necesitaba migracion. Al sacar
`create_all()` del dominio propio eso dejo de ser cierto: si esta tabla no
estuviera aca, no la crearia nadie, y el sintoma seria un `no such table` en la
primera consulta, no un error de arranque.

**Por que la FK de `incidencias.categoria_id` va en un `op.execute()` crudo.**
El autogenerate propuso `batch_op.create_foreign_key`, que en SQLite **no puede
agregar la constraint sin reconstruir la tabla**: crea una `incidencias` nueva,
copia las filas, borra la vieja y renombra. Eso es mover datos reales para
agregar una columna nullable, y ademas hay **tres tablas con FK apuntando a
`incidencias`** (`equipos_movimientos`, `actividades_incidencia`,
`incidencias_estados_log`), que es justo donde el copy-and-move de SQLite tiene
sus filos.

El camino limpio de Alembic seria `op.add_column` con la `ForeignKey` adentro,
pero **eso no funciona**: el dialecto SQLite levanta `NotImplementedError`
("No support for ALTER of constraints in SQLite dialect") porque intenta
agregarla como constraint aparte. Verificado, no supuesto — lo agarraron los
tests al primer intento.

Queda el `ALTER TABLE ... ADD COLUMN ... REFERENCES ...` escrito a mano, que es
**exactamente** lo que hacia `app/migrations.py` y lo que produccion ya vivio en
julio con `equipos_movimientos.incidencia_id`: una sola sentencia, sin tocar
ninguna fila. El resultado por `PRAGMA foreign_key_list` es el mismo que emite
`create_all()`, y hay un test que compara las dos bases.

Las dos columnas de `clientes` no necesitan nada especial: `batch_alter_table`
con solo `add_column` no reconstruye (usa `recreate="auto"`).
"""
import sqlalchemy as sa
from alembic import op

revision = '0002_categorias_y_datos_fiscales'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'categorias_incidencia',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['categorias_incidencia.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('parent_id', 'nombre'),
    )
    with op.batch_alter_table('categorias_incidencia', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_categorias_incidencia_parent_id'), ['parent_id'], unique=False,
        )

    with op.batch_alter_table('clientes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cuit', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('domicilio', sa.String(length=255), nullable=True))

    # SQL crudo, y el docstring explica por que: es la unica forma de que la FK
    # viaje en el propio ADD COLUMN sin reconstruir `incidencias`.
    op.execute(
        'ALTER TABLE incidencias '
        'ADD COLUMN categoria_id INTEGER REFERENCES categorias_incidencia(id)'
    )
    # El indice va aparte: SQLite no lo acepta dentro del ADD COLUMN. El nombre
    # es el que genera SQLAlchemy (`ix_<tabla>_<columna>`), para que una base
    # migrada y una creada desde cero queden identicas.
    op.create_index('ix_incidencias_categoria_id', 'incidencias', ['categoria_id'], unique=False)


def downgrade():
    # `drop_column` se lleva la FK con la columna: no hace falta soltarla aparte,
    # y no se podria — el autogenerate habia propuesto un `drop_constraint(None)`,
    # que falla porque la constraint no tiene nombre.
    op.drop_index('ix_incidencias_categoria_id', table_name='incidencias')
    with op.batch_alter_table('incidencias', schema=None) as batch_op:
        batch_op.drop_column('categoria_id')

    with op.batch_alter_table('clientes', schema=None) as batch_op:
        batch_op.drop_column('domicilio')
        batch_op.drop_column('cuit')

    with op.batch_alter_table('categorias_incidencia', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_categorias_incidencia_parent_id'))
    op.drop_table('categorias_incidencia')
