"""activos en la cadena de service (fase 4 del modulo de alquileres).

Hasta acá un **activo** —el equipo propio que se entrega bajo contrato— no podía
pasar por service ni tener historial de movimientos: las dos tablas de esa
cadena tenían `equipo_id` como FK `NOT NULL` a `equipos.id`, que es el parque
del cliente. Un activo colocado que fallaba se pasaba a `en_reparacion` a mano y
sin ningún registro de a dónde se lo mandó, que es exactamente el hueco que el
bloque de service/RMA vino a cerrar para los equipos del cliente.

**Las dos tablas pasan a polimórficas**: o `equipo_id` o `activo_id`, nunca las
dos ni ninguna. Se eligió esto sobre duplicar la cadena en tablas
`activos_movimientos` / `activos_reparaciones` porque un paso por service es el
mismo hecho sea de quién sea el aparato, y duplicarlo partiría en dos la
pregunta que justifica registrarlo — *"qué tengo hoy afuera"*, *"este proveedor
cuánto tarda"* — en cada pantalla, cada reporte y cada informe.

> 🔴 **Es la única revisión del módulo que toca datos existentes.** En SQLite
> volver nullable una columna `NOT NULL` obliga a **recrear la tabla y copiar**,
> que es lo que hace `batch_alter_table`. Medido antes de escribirla:
> `equipos_movimientos` tiene 77 filas en producción y 53 en dev;
> `equipos_reparaciones`, 0 y 5. Todas las filas existentes cumplen el CHECK
> nuevo sin tocarlas, porque tienen `equipo_id` con valor y `activo_id` en NULL.

**El CHECK va a mano y no por autogenerate**: Alembic no detecta constraints de
tipo CHECK, así que la revisión generada no los traía. Se agregan explícitamente
con `create_check_constraint`, y los nombres de las FK también son explícitos —
el autogenerate emitía `drop_constraint(None, ...)` en el downgrade, que falla.

> ⚠️ **Trampa para la próxima revisión que toque estas dos tablas.** SQLAlchemy
> **no refleja los CHECK de SQLite**, y `batch_alter_table` recrea la tabla a
> partir de lo reflejado: un `batch_alter_table('equipos_movimientos')` futuro
> **se llevaría puestos estos CHECK en silencio**. Si hace falta otra operación
> batch sobre estas tablas, hay que volver a declarar los CHECK en esa revisión.

**`incidencias.activo_id` es sólo un `ADD COLUMN`** — no reconstruye nada — y
**no** lleva CHECK contra `equipo_id`: un ticket puede tocar legítimamente las
dos cosas ("el teléfono alquilado no registra en la PC del cliente"), y forzar
uno solo obligaría a elegir cuál de los dos se pierde.

**No hay backfill.** Ningún activo pasó por service todavía: la tabla `activos`
se creó vacía en la 0004 y sigue vacía en dev.
"""
from alembic import op
import sqlalchemy as sa

revision = '0006_activos_en_service'
down_revision = '0005_depositos'
branch_labels = None
depends_on = None

# "Exactamente uno de los dos". `<>` es XOR sobre los booleanos que devuelve
# cada `IS NOT NULL`, asi que rechaza tanto la fila con los dos cargados como la
# que no tiene ninguno.
_XOR = "(equipo_id IS NOT NULL) <> (activo_id IS NOT NULL)"


def upgrade():
    with op.batch_alter_table('equipos_movimientos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('activo_id', sa.Integer(), nullable=True))
        batch_op.alter_column('equipo_id', existing_type=sa.INTEGER(), nullable=True)
        batch_op.create_index(
            batch_op.f('ix_equipos_movimientos_activo_id'), ['activo_id'], unique=False,
        )
        batch_op.create_foreign_key(
            'fk_equipos_movimientos_activo_id', 'activos', ['activo_id'], ['id'],
            ondelete='CASCADE',
        )
        batch_op.create_check_constraint('ck_movimiento_equipo_xor_activo', _XOR)

    with op.batch_alter_table('equipos_reparaciones', schema=None) as batch_op:
        batch_op.add_column(sa.Column('activo_id', sa.Integer(), nullable=True))
        batch_op.alter_column('equipo_id', existing_type=sa.INTEGER(), nullable=True)
        batch_op.create_index(
            batch_op.f('ix_equipos_reparaciones_activo_id'), ['activo_id'], unique=False,
        )
        batch_op.create_foreign_key(
            'fk_equipos_reparaciones_activo_id', 'activos', ['activo_id'], ['id'],
        )
        batch_op.create_check_constraint('ck_reparacion_equipo_xor_activo', _XOR)

    with op.batch_alter_table('incidencias', schema=None) as batch_op:
        batch_op.add_column(sa.Column('activo_id', sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_incidencias_activo_id'), ['activo_id'], unique=False,
        )
        batch_op.create_foreign_key(
            'fk_incidencias_activo_id', 'activos', ['activo_id'], ['id'],
            ondelete='SET NULL',
        )


def downgrade():
    """Vuelve `equipo_id` a `NOT NULL`, así que **descarta las filas de activos**.

    No hay alternativa: una fila de un activo no tiene equipo al que apuntar, y
    dejarla con `equipo_id` en NULL violaría la constraint que se está
    restaurando. Se borran explícitamente en vez de dejar que reviente el
    `alter_column` con un error que no explica nada.
    """
    op.execute("DELETE FROM equipos_movimientos WHERE activo_id IS NOT NULL")
    op.execute("DELETE FROM equipos_reparaciones WHERE activo_id IS NOT NULL")

    with op.batch_alter_table('incidencias', schema=None) as batch_op:
        batch_op.drop_constraint('fk_incidencias_activo_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_incidencias_activo_id'))
        batch_op.drop_column('activo_id')

    with op.batch_alter_table('equipos_reparaciones', schema=None) as batch_op:
        batch_op.drop_constraint('ck_reparacion_equipo_xor_activo', type_='check')
        batch_op.drop_constraint('fk_equipos_reparaciones_activo_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_equipos_reparaciones_activo_id'))
        batch_op.alter_column('equipo_id', existing_type=sa.INTEGER(), nullable=False)
        batch_op.drop_column('activo_id')

    with op.batch_alter_table('equipos_movimientos', schema=None) as batch_op:
        batch_op.drop_constraint('ck_movimiento_equipo_xor_activo', type_='check')
        batch_op.drop_constraint('fk_equipos_movimientos_activo_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_equipos_movimientos_activo_id'))
        batch_op.alter_column('equipo_id', existing_type=sa.INTEGER(), nullable=False)
        batch_op.drop_column('activo_id')
