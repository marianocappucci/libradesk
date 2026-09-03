"""agenda de los equipos de trabajo (pedido 42, fase B).

Tres columnas nuevas en `incidencias`: **cuándo** se va a atender
(`fecha_programada`), cuánto dura (`duracion_minutos`) y **qué equipo** lo hace
(`equipo_trabajo_id`).

Sin `fecha_programada` la disponibilidad de un equipo sólo podía ser "está o no
está en otro equipo" — la incidencia no sabía cuándo se iba a atender, y por eso
la fase A dejó la agenda explícitamente afuera. Con esta columna el motor de
turnos puede decir si dos trabajos se pisan.

**Las tres son nullable y sin default**: agendar es opcional, y las 26
incidencias que ya existen no tienen fecha de visita ni la tuvieron nunca.
Inventarles una sería peor que dejarlas sin agenda.

**El vehículo no se guarda acá**, a propósito: sale de lo que el equipo tenga
asignado (revisión `0008`). Una columna `vehiculo_id` en el ticket admitiría que
dijera una patente y el equipo otra.

> **No hay tablas de LibraGenda en esta revisión, y es deliberado.** El motor de
> turnos se usa como **librería de reglas**: de todo él se importa
> `find_conflicts()`, que es una función pura sobre objetos `Appointment`.
> Instalar su schema habría traído 11 tablas —incluida una `clients` al lado de
> la `clientes` que ya existe— y habría obligado a espejar cada equipo y cada
> vehículo como un `resource`, o sea dos filas para la misma cosa. Ver
> `app/services/agenda.py`.

**Es un `ADD COLUMN` puro**: las tres son nullable, así que ni siquiera hace
falta reconstruir la tabla por el lado de los defaults. `batch_alter_table` la
recrea igual por las FK, que en SQLite no se pueden agregar de otro modo.
"""
import sqlalchemy as sa
from alembic import op

revision = '0009_agenda_de_equipos'
down_revision = '0008_equipos_de_trabajo_y_flota'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('incidencias', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fecha_programada', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('duracion_minutos', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('equipo_trabajo_id', sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_incidencias_fecha_programada'), ['fecha_programada'], unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_incidencias_equipo_trabajo_id'), ['equipo_trabajo_id'], unique=False,
        )
        batch_op.create_foreign_key(
            'fk_incidencias_equipo_trabajo_id', 'equipos_trabajo',
            ['equipo_trabajo_id'], ['id'], ondelete='SET NULL',
        )


def downgrade():
    with op.batch_alter_table('incidencias', schema=None) as batch_op:
        batch_op.drop_constraint('fk_incidencias_equipo_trabajo_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_incidencias_equipo_trabajo_id'))
        batch_op.drop_index(batch_op.f('ix_incidencias_fecha_programada'))
        batch_op.drop_column('equipo_trabajo_id')
        batch_op.drop_column('duracion_minutos')
        batch_op.drop_column('fecha_programada')
