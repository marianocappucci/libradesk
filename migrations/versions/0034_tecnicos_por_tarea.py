"""Técnicos por tarea, con su ventana de trabajo — brechas 3 y 5 de Lagrace.

## Qué faltaba

LibraDesk tenía **un** `tecnico_id` en la incidencia. La pantalla de asignación
de Integridad, en cambio, lista **14 técnicos con checkbox**, y al tildar uno se
le cargan las horas: `Fecha Inicio · Hora Inicio · Fecha Fin · Hora Fin · Total`.
O sea: varios ejecutantes por tarea (brecha 3), cada uno con su propio tramo de
tiempo (brecha 5).

`equipo_trabajo_id` **no lo cubría** y está dicho en el relevamiento: una
cuadrilla es una entidad estable con integrantes y vehículo; acá se tildan
técnicos ad hoc por tarea. Son dos cosas y las dos hacen falta.

## El asignado es un técnico, sin polimorfismo

La lista de 14 de Integridad mezcla personas (Sergio López), apellidos sueltos
(Oteiza) y lo que parecían **empresas** (TPI, Líder Telecomunicaciones), y el
relevamiento lo dejó anotado como *"sugiere que tercerizan parte del trabajo — a
confirmar con Cristina, **cambia el modelo de datos**"*.

**Confirmado el 2026-08-19: no tercerizan, son todos personal.** Por eso
`tecnico_id` es una FK a `tecnicos` y nada más. Si algún día entra un tercero, lo
que cambia es esta columna, no el resto del circuito.

## `SET NULL` y no `CASCADE` al borrar el técnico

Mismo criterio que `incidencias.tecnico_id`: las horas trabajadas son la base de
lo que se cobra, así que borrar a una persona del catálogo **no puede borrar el
trabajo que hizo**. La fila queda sin nombre y con sus horas, que es la pérdida
menor. (El producto además da de baja lógica: `tecnicos.activo`.)

## `UNIQUE (tarea_id, tecnico_id)`

Una fila por técnico y por tarea, que es lo que la pantalla de checkbox puede
expresar: se tilda o no se tilda. Dos tramos del mismo técnico en la misma tarea
—se fue y volvió— hoy no tienen cómo cargarse, y **eso es a propósito**: en el
circuito relevado esa segunda visita es otra tarea, que es justamente para lo
que existe la grilla. Si aparece el caso, se saca la constraint.

## Lo que NO trae: ninguna columna de plata

La brecha 5 dice "con importe" y se vio `0.08 h → $1.688,00`. **El importe se
deriva**, no se guarda: horas × el valor hora del catálogo, resuelto por la lista
de precios del cliente del reclamo.

Guardarlo sería una **segunda fuente de verdad para la plata**, al lado de
`incidencias_cargos` —que ya modela la mano de obra como ítems del catálogo—.
Este producto ya pagó ese error una vez: la tabla `servicios` paralela al
catálogo, con 43 precios cargados que ningún circuito aplicaba, dropeada en la
revisión `0031`.

## Tampoco mueve el `N° CDS` ni trae el «continúa en»

En Integridad los dos cuelgan del técnico asignado; en LibraDesk `nro_cds` vive
en la incidencia desde la revisión `0019`. Bajarlo un nivel es una decisión de
producto que todavía no se tomó, y no hace falta para las horas.
"""
import sqlalchemy as sa
from alembic import op

revision = "0034_tecnicos_por_tarea"
down_revision = "0033_tareas_del_reclamo"
branch_labels = None
depends_on = None


_INDICES = ("tarea_id", "tecnico_id")


def upgrade():
    op.create_table(
        "incidencias_tareas_tecnicos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tarea_id", sa.Integer(),
            sa.ForeignKey("incidencias_tareas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Nullable + SET NULL: borrar a una persona del catálogo no puede
        # borrar las horas que trabajó, que son la base de lo que se cobra.
        sa.Column(
            "tecnico_id", sa.Integer(),
            sa.ForeignKey("tecnicos.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("desde", sa.DateTime(), nullable=True),
        sa.Column("hasta", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.UniqueConstraint(
            "tarea_id", "tecnico_id", name="uq_tarea_tecnico",
        ),
    )
    for columna in _INDICES:
        op.create_index(
            f"ix_incidencias_tareas_tecnicos_{columna}",
            "incidencias_tareas_tecnicos", [columna],
        )


def downgrade():
    for columna in _INDICES:
        op.drop_index(
            f"ix_incidencias_tareas_tecnicos_{columna}",
            table_name="incidencias_tareas_tecnicos",
        )
    op.drop_table("incidencias_tareas_tecnicos")
