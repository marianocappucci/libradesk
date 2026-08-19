"""Tareas dentro del reclamo: `incidencias_tareas` — brecha 4 de Lagrace.

## Qué faltaba

Un reclamo de LibraDesk se resuelve de una sola vez o no se puede representar.
La ficha de Integridad, en cambio, tiene una **grilla de tareas** con
`Item · Detalle Tarea · F. Inicio · F. Fin · Estado · Observación ·
Tipo Servicio`: N tareas por reclamo, **cada una con su propio estado y sus
propias fechas**. Es el caso normal de ellos — se va, se diagnostica, se pide un
repuesto, se vuelve.

Lo más parecido que había es `actividades_incidencia`, y **no alcanza**: es un
log de `(fecha, descripcion, usuario)`, sin estado, sin fecha de fin y sin nada
que cerrar. Verificado contra `origin/develop` antes de escribir esto: cero
coincidencias de `incidencias_tareas` en `app/`, `migrations/` y `frontend/src/`.

Sin esta tabla no hay dónde colgar las otras tres brechas del bloque: varios
técnicos **por tarea** (3), horas e importe **por técnico y por tarea** (5), y
el «continúa en» (9), que según el relevamiento se resuelve solo si esto está
bien hecho.

## `Tipo Servicio` es el catálogo, no un enum ni una tabla propia

`item_id` apunta a un `catalog_items` de tipo `SERVICE`, igual que
`incidencias_cargos` desde la revisión `0029`. Es la misma decisión y por el
mismo motivo: agregar un tipo de servicio nuevo es cargar un ítem, sin código ni
migración, y de arrastre vienen el precio de la lista del cliente y la alícuota.

**Y hay precedente de hacerlo mal**: este producto tuvo una tabla `servicios`
paralela al catálogo, con 43 precios cargados que ningún circuito aplicaba, y se
dropeó en la revisión `0031`. Una tabla de "tipos de tarea" acá sería el mismo
error otra vez.

Sin FK, igual que `incidencias_cargos`: `catalog_items` es de LibraCommerce y
esta cadena no la toca.

## El estado de la tarea NO usa el vocabulario del reclamo

El reclamo tiene `abierto / en_progreso / resuelta / cerrado`, y esa distinción
entre las dos últimas existe por una razón concreta: `resuelta` es "el técnico
terminó" y `cerrado` es "alguien controló el comprobante de servicios contra la
hoja de ruta y decidió que va a facturación" — está escrito en el docstring de
`convertir_a_remito`, que **sólo convierte reclamos `cerrado`**.

Una tarea no pasa por ese control: el control es del reclamo entero. Así que
lleva su propio vocabulario, más corto — `pendiente / en_progreso / terminada` —
y no se hereda uno que tendría un estado que nunca se usa.

## `orden` y no `item`

La grilla de Integridad numera las tareas en una columna `Item`. Acá esa columna
es `orden`: es la posición en la lista, la decide quien carga, y sirve para
mostrarlas siempre igual. No es un identificador — el id es `id`.

## Las fechas son `Date`, no `DateTime`

Porque es lo que se vio: la grilla de tareas muestra `F. Inicio · F. Fin`, y el
detalle con hora (`Fecha Inicio · Hora Inicio · Fecha Fin · Hora Fin`) aparece
**un nivel más abajo**, al tildar un técnico. Ese nivel es la brecha 5 y va en
su propia tabla; ponerle hora a la tarea sería adelantar un dato que la pantalla
que se relevó no pide acá.

## Lo que esta revisión NO trae

- **Los técnicos por tarea** (brecha 3) y **las horas con importe** (brecha 5).
  Van en la fase siguiente, y tienen una decisión de producto abierta antes:
  la lista de 14 de Integridad **mezcla personas con empresas** (TPI, Líder
  Telecomunicaciones), y el relevamiento lo dejó anotado como *"a confirmar con
  Cristina — cambia el modelo de datos"*.
- **`horas_invertidas` de la incidencia no se toca.** Sigue siendo la fuente del
  remito. Es un expand/contract: primero conviven, y recién cuando las horas
  vivan en las tareas se decide qué pasa con la columna vieja. El producto ya
  hizo esto con `servicios` (revisiones `0029` a `0031`) y salió bien.
"""
import sqlalchemy as sa
from alembic import op

revision = "0033_tareas_del_reclamo"
down_revision = "0032_contratos_actas"
branch_labels = None
depends_on = None


_INDICES = ("incidencia_id", "estado", "item_id")


def upgrade():
    op.create_table(
        "incidencias_tareas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "incidencia_id", sa.Integer(),
            sa.ForeignKey("incidencias.id", ondelete="CASCADE"), nullable=False,
        ),
        # La posición en la grilla. NOT NULL: una tarea sin lugar no se puede
        # mostrar de forma estable, y el orden es lo que el usuario decide.
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("detalle", sa.Text(), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=True),
        sa.Column("fecha_fin", sa.Date(), nullable=True),
        # NOT NULL y sin `server_default`, que es la convención del producto: el
        # default vive en el modelo, del lado de Python, y
        # `test_alembic_construye_lo_mismo_que_create_all` compara que la tabla
        # de la migración y la de `create_all()` sean la misma.
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        # `catalog_items` de tipo SERVICE. Sin FK: es de LibraCommerce.
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
    )
    for columna in _INDICES:
        op.create_index(
            f"ix_incidencias_tareas_{columna}", "incidencias_tareas", [columna],
        )


def downgrade():
    for columna in _INDICES:
        op.drop_index(f"ix_incidencias_tareas_{columna}", table_name="incidencias_tareas")
    op.drop_table("incidencias_tareas")
