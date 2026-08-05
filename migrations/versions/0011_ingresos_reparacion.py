"""Ingresos a reparación con sus dos comprobantes (pedido 43).

**Aditiva pura**: una tabla nueva, ninguna existente se toca. No hay
`batch_alter_table`, así que no reconstruye nada y no puede llevarse puesto
ningún CHECK de los que SQLAlchemy no refleja (la trampa anotada en la `0006`).

Escrita a mano y no autogenerada, por lo mismo de siempre acá: el autogenerate
emite las FK sin nombrar y los `drop_constraint(None)` del downgrade no corren
en SQLite.

**El UNIQUE de `numero_entrega` convive con muchos NULL, y eso es lo buscado**:
mientras el equipo está en el taller la columna es NULL, y en SQLite (como en
el estándar) un UNIQUE no compara NULLs entre sí. Se llegó a escribir como
índice **parcial** para hacer explícita la intención, y se volvió atrás: el
modelo declara `UniqueConstraint`, y un índice parcial en la migración habría
sido deriva contra el metadata —`alembic check` en rojo por una diferencia
puramente cosmética—. La intención vive en el comentario del modelo, que es
donde se lee.

**Nace vacía, sin backfill.** Los ingresos anteriores al pedido 43 no existen
como dato: reconstruirlos de los movimientos de equipo sería inventar números de
comprobante que nunca se le dieron a nadie.
"""
from alembic import op
import sqlalchemy as sa

# Renumerada de `0010` a `0011` al mergear: una sesión paralela metió
# `0010_log_de_actividad` colgando del mismo `0009`. Dos revisiones con el mismo
# `down_revision` dan **dos cabezas**, y ahí Alembic no sabe cuál correr. El
# criterio ya usado con el choque del `0004` es el mismo: **el que mergea
# segundo renumera y encadena**, en vez de que las dos compartan padre. Lo cubre
# `test_la_cadena_tiene_una_sola_cabeza`.
#
# Encadenar es seguro porque las dos son aditivas puras y tocan tablas distintas
# (`log_actividad` y `ingresos_reparacion`): el orden entre ellas no cambia nada.
revision = "0011_ingresos_reparacion"
down_revision = "0010_log_de_actividad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingresos_reparacion",
        sa.Column("id", sa.Integer(), nullable=False),
        # --- comprobante de recepción ---
        sa.Column("numero", sa.String(length=50), nullable=False),
        sa.Column("fecha_recepcion", sa.DateTime(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("contacto", sa.String(length=255), nullable=True),
        sa.Column("contacto_telefono", sa.String(length=50), nullable=True),
        # --- el equipo, congelado: son datos del papel, no del inventario ---
        sa.Column("equipo_id", sa.Integer(), nullable=True),
        sa.Column("equipo_tipo", sa.String(length=255), nullable=False),
        sa.Column("equipo_marca", sa.String(length=255), nullable=True),
        sa.Column("equipo_modelo", sa.String(length=255), nullable=True),
        sa.Column("equipo_serial", sa.String(length=255), nullable=True),
        sa.Column("accesorios", sa.Text(), nullable=True),
        sa.Column("estado_fisico", sa.Text(), nullable=True),
        sa.Column("falla_declarada", sa.Text(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("tecnico_id", sa.Integer(), nullable=True),
        sa.Column("entregado_por", sa.String(length=255), nullable=True),
        sa.Column("incidencia_id", sa.Integer(), nullable=True),
        # --- comprobante de entrega: NULL = sigue en el taller ---
        sa.Column("numero_entrega", sa.String(length=50), nullable=True),
        sa.Column("fecha_entrega", sa.DateTime(), nullable=True),
        sa.Column("retirado_por", sa.String(length=255), nullable=True),
        sa.Column("trabajo_realizado", sa.Text(), nullable=True),
        sa.Column("observaciones_entrega", sa.Text(), nullable=True),
        sa.Column("tecnico_entrega_id", sa.Integer(), nullable=True),
        # Sin `server_default`: el modelo usa un default de Python
        # (`default="Sistema"`), igual que `reparaciones`. Un `server_default`
        # acá haría que la tabla creada por la migración no fuera idéntica a la
        # que crea `create_all()`, y hay un test que compara las dos —es lo que
        # garantiza que traer Alembic no cambie nada para una instancia nueva—.
        # La tabla nace vacía, así que no hace falta para rellenar nada.
        sa.Column("usuario", sa.String(length=255), nullable=False),
        # `nullable=False` para coincidir con el modelo (`Mapped[datetime]`, sin
        # `| None`). Se escribió `True` primero y `alembic check` no dijo nada
        # —la tabla no estaba en `metadata` porque faltaba su import en
        # `app/schema.py`, así que el filtro la ocultaba—. El `server_default`
        # es lo que hace que NOT NULL no moleste en el INSERT.
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # FK con nombre explícito: sin nombrarlas, un `batch_alter_table`
        # posterior sobre esta tabla no las puede referenciar en SQLite.
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"],
                                name="fk_ingreso_cliente"),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"],
                                name="fk_ingreso_equipo"),
        sa.ForeignKeyConstraint(["tecnico_id"], ["tecnicos.id"],
                                name="fk_ingreso_tecnico"),
        sa.ForeignKeyConstraint(["tecnico_entrega_id"], ["tecnicos.id"],
                                name="fk_ingreso_tecnico_entrega"),
        sa.ForeignKeyConstraint(["incidencia_id"], ["incidencias.id"],
                                name="fk_ingreso_incidencia"),
        sa.UniqueConstraint("numero", name="uq_ingreso_numero"),
        sa.UniqueConstraint("numero_entrega", name="uq_ingreso_numero_entrega"),
    )
    op.create_index("ix_ingresos_reparacion_cliente_id",
                    "ingresos_reparacion", ["cliente_id"])
    op.create_index("ix_ingresos_reparacion_equipo_id",
                    "ingresos_reparacion", ["equipo_id"])
    op.create_index("ix_ingresos_reparacion_incidencia_id",
                    "ingresos_reparacion", ["incidencia_id"])
    op.create_index("ix_ingresos_reparacion_tecnico_id",
                    "ingresos_reparacion", ["tecnico_id"])
    op.create_index("ix_ingresos_reparacion_tecnico_entrega_id",
                    "ingresos_reparacion", ["tecnico_entrega_id"])
    op.create_index("ix_ingresos_reparacion_equipo_serial",
                    "ingresos_reparacion", ["equipo_serial"])
    # `fecha_entrega` indexada porque "qué tengo hoy en el taller" es
    # `WHERE fecha_entrega IS NULL` y es la consulta que más se corre.
    op.create_index("ix_ingresos_reparacion_fecha_entrega",
                    "ingresos_reparacion", ["fecha_entrega"])
    op.create_index("ix_ingresos_reparacion_fecha_recepcion",
                    "ingresos_reparacion", ["fecha_recepcion"])


def downgrade() -> None:
    # `drop_table` se lleva los índices con ella; dropearlos antes uno por uno
    # fallaría en SQLite al no existir ya.
    op.drop_table("ingresos_reparacion")
