"""depositos, y la columna que dice en cual esta cada equipo.

Cubre el pedido de manejar depositos "como en Contalibra" y poder mover equipos
entre ellos. Hasta aca "esta en el deposito" era texto libre en `equipos.sector`
—`ReemplazoService` escribia la constante `"Depósito"`—, o sea que no habia
forma de listar el contenido de un deposito ni de mover un equipo de uno a otro.
Ver `app/services/depositos.py` para el modelo y por que una sola tabla sirve
para los depositos propios y los del cliente.

**La FK de `equipos.deposito_id` va en un `op.execute()` crudo, igual que la de
`incidencias.categoria_id` en la 0002 y por el mismo motivo**: en SQLite,
`batch_op.create_foreign_key` no puede agregar la constraint sin reconstruir la
tabla (crea una `equipos` nueva, copia, borra y renombra), y `equipos` es la
tabla con los 53 activos reales de `compulibra` — ademas de tener dos tablas
apuntandole (`equipos_movimientos`, `incidencias`). El `ALTER TABLE ... ADD
COLUMN ... REFERENCES ...` es una sola sentencia que no toca ninguna fila, y
deja el mismo `PRAGMA foreign_key_list` que emite `create_all()`; lo verifica
`test_alembic_construye_lo_mismo_que_create_all`.

**Sin backfill y sin deposito sembrado.** No hay dato del que derivar los
depositos existentes: los equipos "en deposito" tienen la palabra suelta en
`sector`, sin nombre real, y adivinar cuantos depositos representa seria
inventarlo. Los equipos quedan todos con `deposito_id` en NULL —o sea, en el
sector del cliente, que es donde estan— y los depositos se cargan por pantalla.
Un `ReemplazoService` con destino "deposito" en una instancia que todavia no
creo ninguno sigue funcionando como antes, escribiendo el texto: ver DESTINOS.

**Por que es la 0005 y no la 0004.** Nacio como `0004_depositos`, colgando de la
`0003`, y quedo hermana de `0004_alquileres` — otra sesion la escribio el mismo
dia (PR #27). Dos revisiones con el mismo padre dejan la cadena con **dos
cabezas**, y `app/schema.py` corre `command.upgrade(cfg, "head")` en cada
arranque: con dos cabezas eso falla con "Multiple head revisions are present" y
el contenedor no levanta. Git no avisa nada, porque los dos archivos conviven
sin conflicto de merge. Se renumero esta para que cuelgue de aquella; el orden
lo eligio el usuario. Desde ahora lo cubre
`test_la_cadena_tiene_una_sola_cabeza`.
"""
import sqlalchemy as sa
from alembic import op

revision = '0005_depositos'
down_revision = '0004_alquileres'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'depositos',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('cliente_id', sa.Integer(), nullable=True),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('descripcion', sa.String(length=500), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('es_default', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=False),
        sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('depositos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_depositos_cliente_id'), ['cliente_id'], unique=False)

    # SQL crudo, y el docstring explica por que. Mismo camino que la 0002.
    op.execute('ALTER TABLE equipos ADD COLUMN deposito_id INTEGER REFERENCES depositos(id)')
    # El indice va aparte: SQLite no lo acepta dentro del ADD COLUMN. El nombre
    # es el que genera SQLAlchemy (`ix_<tabla>_<columna>`), para que una base
    # migrada y una creada desde cero queden identicas.
    op.create_index('ix_equipos_deposito_id', 'equipos', ['deposito_id'], unique=False)


def downgrade():
    # `drop_column` se lleva la FK con la columna — ver el downgrade de la 0002.
    op.drop_index('ix_equipos_deposito_id', table_name='equipos')
    with op.batch_alter_table('equipos', schema=None) as batch_op:
        batch_op.drop_column('deposito_id')

    with op.batch_alter_table('depositos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_depositos_cliente_id'))
    op.drop_table('depositos')
