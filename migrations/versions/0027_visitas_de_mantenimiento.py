"""Las visitas de mantenimiento: el abono deja de cobrar sin operar.

Sale de la revisión del circuito del 2026-08-16, que encontró el hueco más
grande de los cuatro: **el abono cobra la cuota y no programa la visita**.
Verificado entonces y otra vez al escribir esto — cero coincidencias de
`preventiv`, `proxima_visita`, `visita_program`, `recurrenc` o
`frecuencia_visita` en todo `app/`. El sistema le cobraba el mantenimiento al
cliente todos los meses y **no sabía que había que ir**.

## `frecuencia_visita` es un campo propio, y no `periodicidad`

El contrato ya tiene `periodicidad`, y es **cada cuánto se COBRA**. Cobrar y
visitar no son lo mismo: se puede cobrar mensual y visitar trimestral. Decisión
del humano del 2026-08-16.

Reusar `periodicidad` para las dos cosas parecía gratis y ataba dos conceptos
distintos: cambiar cómo se factura un contrato le habría cambiado la cadencia de
visitas **en silencio**.

> 🔑 **NULL significa "no genera visitas", y es el default.** Los contratos que
> ya existen —incluidos los `abono` de Lagrace— siguen comportándose exactamente
> como hoy hasta que alguien les ponga una frecuencia. La adopción es explícita,
> no un efecto de la migración.

## Por qué la visita es una incidencia y no una entidad nueva

Decisión del humano. Una `incidencia` ya trae todo lo que una visita necesita y
que habría que rehacer: agenda con detección de choques, hoja de ruta, cuadrilla,
técnico asignado, horas, materiales, el cierre con control y hasta el camino a
facturación. Y el preventivo aparece en la misma bandeja que el correctivo, que
es donde el técnico ya mira.

Lo que hace falta agregarle son dos columnas:

- **`contrato_id`** — de qué contrato salió. Sin FK con `ondelete`: el desenlace
  lo hace `ContratoRepository.delete()` explícitamente, igual que el resto de las
  referencias de esta tabla, porque el pragma de FKs está apagado en las
  conexiones de SQLAlchemy.
- **`periodo_visita`** — qué período cubre. Es la mitad de la clave que hace
  idempotente al generador.

## El único es parcial, igual que el de las cuotas

`(contrato_id, periodo_visita)` único **excluyendo las incidencias sin período**
—o sea todos los reclamos normales, que tienen las dos columnas en NULL— y
**excluyendo las canceladas** no aplica acá porque una incidencia no se cancela:
se cierra. Lo que sí se excluye es el NULL, que en PostgreSQL ya no choca por sí
solo, pero el índice parcial además lo deja fuera del índice entero: con 33
reclamos hoy y miles después, no tiene sentido indexar filas que nunca se
consultan por esta clave.

Es el mismo criterio que `ix_cuota_periodo_recurrente` de la revisión `0025`:
generar dos veces septiembre tiene que ser imposible en la base, no sólo
improbable en el código.
"""
import sqlalchemy as sa
from alembic import op

revision = "0027_visitas_de_mantenimiento"
down_revision = "0026_ventas_remitos"
branch_labels = None
depends_on = None


def upgrade():
    # NULL = no genera visitas. Ver el docstring: la adopción es explícita.
    op.add_column(
        "contratos",
        sa.Column("frecuencia_visita", sa.String(20), nullable=True),
    )
    # Cuánto dura la visita, para que la agenda pueda detectar choques. Nullable
    # porque no siempre se sabe, y `agenda.validar_agenda()` ya tolera que no
    # esté — un turno sin duración no se pisa con nadie.
    op.add_column(
        "contratos",
        sa.Column("duracion_visita_minutos", sa.Integer(), nullable=True),
    )

    op.add_column(
        "incidencias",
        sa.Column("contrato_id", sa.Integer(), sa.ForeignKey("contratos.id"),
                  nullable=True),
    )
    op.add_column(
        "incidencias",
        sa.Column("periodo_visita", sa.Date(), nullable=True),
    )
    op.create_index("ix_incidencias_contrato_id", "incidencias", ["contrato_id"])

    # Generar dos veces el mismo período de un contrato tiene que ser imposible
    # en la base. Parcial: deja afuera los reclamos normales, que son todos.
    op.create_index(
        "ix_incidencia_visita_periodo",
        "incidencias",
        ["contrato_id", "periodo_visita"],
        unique=True,
        postgresql_where=sa.text("periodo_visita IS NOT NULL"),
    )


def downgrade():
    op.drop_index("ix_incidencia_visita_periodo", table_name="incidencias")
    op.drop_index("ix_incidencias_contrato_id", table_name="incidencias")
    op.drop_column("incidencias", "periodo_visita")
    op.drop_column("incidencias", "contrato_id")
    op.drop_column("contratos", "duracion_visita_minutos")
    op.drop_column("contratos", "frecuencia_visita")
