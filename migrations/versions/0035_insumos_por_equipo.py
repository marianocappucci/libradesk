"""Insumos por equipo y referencias ajenas — fase 1 del control de consumibles.

## Qué faltaba

El caso concreto (2026-08-24): un cliente le **alquila fotocopiadoras a un
tercero**, y ese tercero le provee los tóner dentro del contrato. Para pedir uno
hay que darle el **número interno de la máquina en el sistema del tercero**, y
cada cambio de tóner es un hecho que no tenía dónde anotarse.

Verificado contra `origin/develop` antes de escribir esto: cero coincidencias de
`insumo`, `toner` y `consumible por equipo` en `app/`, `migrations/` y
`frontend/src/`. Lo único parecido es `incidencias_materiales`, que hace otra
cosa —descuenta **nuestro** depósito— y por eso no sirve acá: el tóner del
cliente nunca fue nuestro.

## Tres cosas y ningún módulo nuevo de más

1. `equipos.proveedor_id` — de quién es el equipo cuando no es del cliente.
2. `equipos_referencias` — cómo lo llaman los demás.
3. `equipos_insumos` — qué consumió, quién se lo dio y con qué contador se puso.

## `equipos.proveedor_id` reusa `proveedores`

Esa tabla nació nombrando al service (*"a quién se le manda un equipo"*) y ahora
también nombra al dueño tercero. Es la misma empresa del mundo real —Sistemas
Junín alquila las máquinas **y** entrega los tóner—, así que una tabla `terceros`
paralela sería el mismo catálogo cargado dos veces, con "Compu Service" y
"compuservice" otra vez. Que es exactamente el problema que `proveedores` vino a
resolver.

Y no hay columna `propiedad` al lado: con `proveedor_id IS NULL` el equipo es del
cliente, que es el caso normal. Guardar las dos cosas sería la misma verdad
escrita dos veces, y el día que discrepen no hay cómo saber cuál miente — el
mismo argumento con el que `activos` no guarda la modalidad del contrato.

## El `ADD COLUMN` va en SQL crudo

Igual que `incidencias.categoria_id` en la revisión `0002`, y por el mismo
motivo verificado allá: `op.add_column()` con la `ForeignKey` adentro levanta
`NotImplementedError` en el dialecto SQLite, que intenta agregarla como
constraint aparte. El `ALTER TABLE ... ADD COLUMN ... REFERENCES ...` es una
sola sentencia, no toca ninguna fila y **es SQL válido en los dos motores**. El
índice va aparte porque SQLite no lo acepta adentro del `ADD COLUMN`, con el
nombre que genera SQLAlchemy para que una base migrada y una creada desde cero
queden idénticas.

## `equipos_referencias`: `UNIQUE (proveedor_id, valor)`

Es la constraint que impide el error que justifica la tabla: dos máquinas con el
mismo número del mismo proveedor es como llega el tóner equivocado.

Con `proveedor_id` NULL —el número patrimonial del propio cliente— la base **no
garantiza nada**, y es a propósito: dos clientes distintos pueden numerar su
patrimonio desde 1 sin que eso sea un error. Esa unicidad la valida
`EquipoRepository._duplicado()` contra el cliente del equipo, que es el alcance
en el que el número significa algo. Un índice único parcial tampoco podría: la
condición vive en **otra tabla** (`equipos.cliente_id`), que es la misma razón
por la que `contratos_actas` no pudo llevar el suyo en la revisión `0032`.

## `equipos_insumos`: tres fechas, ningún `estado`, sin `cantidad`

- **Ningún `estado`**: se deriva de las fechas, igual que `equipos_reparaciones`
  con `fecha_retorno` y `contratos_equipos` con `fecha_retiro`. Una columna al
  lado puede contradecirlas.
- **Un CHECK exige al menos una de las tres**: una fila sin ninguna fecha no
  describe ningún hecho. Las otras tres CHECK ordenan los momentos y atan el
  contador a la colocación, que es cuando se lee el display.
- **Sin `cantidad`**: un pedido de dos tóner son dos filas. Es lo que permite
  contar cuántos te deben y calcular qué rindió cada uno; con una fila de
  cantidad 2 la colocación tendría que ser de las dos juntas, y no es lo que
  pasa.

## `insumo_item_id` sin ForeignKey, y el nombre copiado al lado

El catálogo de consumibles es `catalog_items`, de **LibraCommerce**: otro
`MetaData`, escrito por la conexión cruda de `libracore.db.core`. Una
`ForeignKey` declarada desde el `Base` de este producto ni siquiera resuelve
—`NoReferencedTableError` en el `create_all`—, así que la columna es un entero y
la existencia la valida el service contra el catálogo antes de escribir. Es la
misma frontera que ya respetan `contratos_cuotas.remito_id` y
`incidencias_materiales.item_id`.

`insumo_nombre` copia el nombre al momento de usarlo por lo mismo que lo copia
`materiales._descripcion()`: renombrar un producto no puede reescribir lo que
dice un cambio de tóner de marzo. Como efecto útil, el historial se lee entero
en una instancia que no tenga `stock` prendido — ese módulo hace falta para
**elegir** el insumo, no para leer lo que ya pasó.

## Lo que esta revisión NO trae

**Ninguna columna de plata, y ningún movimiento de stock.** Lo que el tercero
entrega dentro del contrato no se compra ni se vende, así que valorizarlo acá
inventaría un costo que nadie pagó. Y si el insumo sale de nuestro depósito, el
camino que corresponde sigue siendo el material de la incidencia, que descuenta
y appendea el movimiento en la misma transacción — ver el docstring de
`app/services/materiales.py`, que explica por qué eso no puede hacerse desde el
ORM.

Tampoco trae el **contrato con el proveedor** (fase 2): sin él ya se puede
registrar, reclamar y medir, que es el problema de hoy. El contrato agrega
controlar lo pactado, y se modela mejor con dos meses de entregas cargadas.
"""
import sqlalchemy as sa
from alembic import op

revision = "0035_insumos_por_equipo"
down_revision = "0034_tecnicos_por_tarea"
branch_labels = None
depends_on = None


_INDICES_REFERENCIAS = ("equipo_id", "proveedor_id", "valor")
_INDICES_INSUMOS = (
    "equipo_id", "insumo_item_id", "proveedor_id", "incidencia_id",
    "fecha_pedido", "fecha_entrega", "fecha_colocacion",
)


def upgrade():
    # ── De quién es el equipo, cuando no es del cliente ──────────────────
    op.execute(
        "ALTER TABLE equipos "
        "ADD COLUMN proveedor_id INTEGER REFERENCES proveedores(id)"
    )
    op.create_index("ix_equipos_proveedor_id", "equipos", ["proveedor_id"])

    # ── Cómo lo llaman los demás ─────────────────────────────────────────
    op.create_table(
        "equipos_referencias",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "equipo_id", sa.Integer(),
            sa.ForeignKey("equipos.id", ondelete="CASCADE"), nullable=False,
        ),
        # NULL = el número es del propio cliente (patrimonial, inventario).
        sa.Column(
            "proveedor_id", sa.Integer(),
            sa.ForeignKey("proveedores.id"), nullable=True,
        ),
        sa.Column("etiqueta", sa.String(length=100), nullable=False),
        sa.Column("valor", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.UniqueConstraint(
            "proveedor_id", "valor", name="uq_referencia_proveedor_valor",
        ),
    )
    for columna in _INDICES_REFERENCIAS:
        op.create_index(
            f"ix_equipos_referencias_{columna}", "equipos_referencias", [columna],
        )

    # ── Qué consume el equipo ────────────────────────────────────────────
    op.create_table(
        "equipos_insumos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "equipo_id", sa.Integer(), sa.ForeignKey("equipos.id"), nullable=False,
        ),
        # `catalog_items.id` de LibraCommerce, sin FK — ver el docstring.
        sa.Column("insumo_item_id", sa.Integer(), nullable=False),
        sa.Column("insumo_nombre", sa.String(length=255), nullable=False),
        # NULL = lo puso el propio cliente.
        sa.Column(
            "proveedor_id", sa.Integer(), sa.ForeignKey("proveedores.id"),
            nullable=True,
        ),
        sa.Column("fecha_pedido", sa.Date(), nullable=True),
        sa.Column("fecha_entrega", sa.Date(), nullable=True),
        sa.Column("fecha_colocacion", sa.Date(), nullable=True),
        sa.Column("remito_proveedor", sa.String(length=100), nullable=True),
        sa.Column("contador_copias", sa.Integer(), nullable=True),
        sa.Column(
            "incidencia_id", sa.Integer(), sa.ForeignKey("incidencias.id"),
            nullable=True,
        ),
        # Sin `server_default`, igual que `equipos_movimientos.usuario` y
        # `equipos_reparaciones.usuario`: el "Sistema" es el default de Python
        # del modelo, y declararlo también acá dejaría una base migrada distinta
        # de una creada por `create_all()`.
        sa.Column("usuario", sa.String(length=255), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.CheckConstraint(
            "fecha_pedido IS NOT NULL OR fecha_entrega IS NOT NULL "
            "OR fecha_colocacion IS NOT NULL",
            name="ck_insumo_alguna_fecha",
        ),
        sa.CheckConstraint(
            "fecha_entrega IS NULL OR fecha_pedido IS NULL "
            "OR fecha_entrega >= fecha_pedido",
            name="ck_insumo_entrega_despues_del_pedido",
        ),
        sa.CheckConstraint(
            "fecha_colocacion IS NULL OR fecha_entrega IS NULL "
            "OR fecha_colocacion >= fecha_entrega",
            name="ck_insumo_colocacion_despues_de_la_entrega",
        ),
        sa.CheckConstraint(
            "contador_copias IS NULL OR fecha_colocacion IS NOT NULL",
            name="ck_insumo_contador_solo_al_colocar",
        ),
        sa.CheckConstraint(
            "contador_copias IS NULL OR contador_copias >= 0",
            name="ck_insumo_contador_no_negativo",
        ),
    )
    for columna in _INDICES_INSUMOS:
        op.create_index(
            f"ix_equipos_insumos_{columna}", "equipos_insumos", [columna],
        )


def downgrade():
    for columna in _INDICES_INSUMOS:
        op.drop_index(f"ix_equipos_insumos_{columna}", table_name="equipos_insumos")
    op.drop_table("equipos_insumos")

    for columna in _INDICES_REFERENCIAS:
        op.drop_index(
            f"ix_equipos_referencias_{columna}", table_name="equipos_referencias",
        )
    op.drop_table("equipos_referencias")

    # `drop_column` se lleva la FK con la columna, igual que en la revisión
    # `0002`: soltarla aparte no se podría, no tiene nombre.
    op.drop_index("ix_equipos_proveedor_id", table_name="equipos")
    with op.batch_alter_table("equipos", schema=None) as batch_op:
        batch_op.drop_column("proveedor_id")
