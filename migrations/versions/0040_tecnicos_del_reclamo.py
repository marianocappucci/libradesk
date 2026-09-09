"""`incidencias_tecnicos`: quiénes fueron al reclamo, y de qué hora a qué hora.

Sale del pedido del humano del 2026-09-09, describiendo el circuito real:

> *"El técnico va, hace el reclamo y anota en el CDS desde qué hora hasta qué
> hora estuvo. Esas horas por técnico después se cargan en esa incidencia al
> otro día, cuando ya está cerrado el reclamo."*

🔑 **Es la brecha 5 subida un nivel: de la tarea al reclamo.** Desde la revisión
`0034` las horas por técnico viven en `incidencias_tareas_tecnicos`, colgando de
una tarea. Pero en el circuito de Lagrace **no hay tareas**: hay un reclamo, un
papel con las horas de cada técnico, y una carga posterior. Colgarlas de una
tarea obligaba a inventar una tarea por reclamo para poder cargarlas.

**`incidencias_tareas_tecnicos` NO se toca ni se migra.** Sigue viva para las
instancias que sí usan la grilla de tareas; ésta es la vía del modo simple. Son
dos formas de trabajar y el producto sostiene las dos.

**`desde`/`hasta` nullables, y los totales suman sólo los tramos completos.**
Un técnico tildado al que nadie le cargó las horas **no trabajó cero horas**: no
se sabe cuántas. Tratar el vacío como cero da un total que parece cerrado y no
lo está, que es justo el número que alguien mira antes de facturar. Es la misma
decisión que ya documenta la `0034`, y por el mismo motivo.

**`UNIQUE (incidencia_id, tecnico_id)`**: una fila por técnico y por reclamo,
que es lo que un checkbox puede expresar. Dos tramos del mismo técnico en el
mismo reclamo son, en el circuito relevado, dos renglones del CDS que se suman
al cargarlos — no dos filas.
"""
import sqlalchemy as sa
from alembic import op

revision = "0040_tecnicos_del_reclamo"
down_revision = "0039_cotizaciones"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incidencias_tecnicos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "incidencia_id", sa.Integer(),
            sa.ForeignKey("incidencias.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        # `SET NULL` y nullable, igual que `incidencias.tecnico_id`: las horas
        # son la base de lo que se cobra, asi que borrar a una persona del
        # catalogo no puede borrar el trabajo que hizo.
        sa.Column(
            "tecnico_id", sa.Integer(),
            sa.ForeignKey("tecnicos.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column("desde", sa.DateTime(), nullable=True),
        sa.Column("hasta", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "incidencia_id", "tecnico_id", name="uq_incidencia_tecnico",
        ),
    )


def downgrade() -> None:
    op.drop_table("incidencias_tecnicos")
