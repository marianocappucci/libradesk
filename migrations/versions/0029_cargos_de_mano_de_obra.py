"""Los cargos de mano de obra de un reclamo.

Tercera pieza del trabajo de tarifas. La primera mudó los servicios al catálogo
del motor; la segunda hizo que las listas de precios se resolvieran por cliente
y por operación. Ésta le da al reclamo **qué mano de obra se le cobra**.

## El problema

Hasta hoy el remito de un reclamo llevaba **una sola línea de trabajo**: las
`horas_invertidas` al único valor hora del sistema. Eso no alcanza para lo que
una cuadrilla que sale a la calle realmente factura — una visita son dos horas
de trabajo **más** un viático **más** el traslado, y el viático no reemplaza a
las horas: se suma.

## 🔑 El tipo de cargo NO es un enum: es un ítem del catálogo

La decisión de fondo, y es la que deja base para ampliar.

`item_id` apunta a un `catalog_items` de tipo `SERVICE`. O sea que «hora
normal», «hora fuera de horario», «viático» y «traslado» son **cuatro filas de
datos**, no cuatro constantes en el código. Agregar «hora nocturna», «feriado» o
«especialista senior» mañana es cargar un ítem: cero código, cero migración.

Y de arrastre hereda todo lo que el catálogo ya resuelve:

| Qué | De dónde sale |
|---|---|
| El precio | La lista del cliente o de la operación (revisión `0028`) |
| La alícuota | `tax_profile` del ítem |
| La descripción | El nombre del ítem |

Un enum en el código habría dado lo mismo hoy y habría cerrado las tres cosas.

## Sin FK contra `catalog_items`

Es de **LibraCommerce** y la cadena de Alembic de este producto no la toca —
misma situación que `ventas_remitos.venta_id` (`0026`), `contratos_cuotas.remito_id`
(`0025`) y `clients.price_list_id` (`0028`).

Y pesa el pozo que documenta `comercial.py`: con el pragma de FKs activo, SQLite
resuelve la tabla padre **al preparar el chequeo**, así que una FK contra una
tabla que este producto no creó rompe *todo* INSERT sobre esta tabla.

## Sin cargos, el remito sale exactamente como hoy

Un reclamo sin ninguna fila acá se cobra como se cobraba: las `horas_invertidas`
al valor hora. **Ningún ticket existente cambia de precio**, y la visita normal
sigue siendo un click. Los cargos son para lo que antes no se podía expresar.

> **`horas_invertidas` no se toca, y es deliberado.** La usan el dashboard en
> cinco lugares, los informes y los reportes: significa *las horas que se
> trabajaron*, que es lo que esos tres cuentan, y no *lo que se factura*. Meter
> ahí el viático habría roto las tres pantallas en silencio.
"""
import sqlalchemy as sa
from alembic import op

revision = "0029_cargos_mano_de_obra"
down_revision = "0028_lista_precios_cliente"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "incidencias_cargos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "incidencia_id", sa.Integer(),
            sa.ForeignKey("incidencias.id", ondelete="CASCADE"), nullable=False,
        ),
        # Sin FK: `catalog_items` es de LibraCommerce. Ver el docstring.
        sa.Column("item_id", sa.Integer(), nullable=False),
        # `Numeric` y no `Float`: se multiplica por un precio y se suma. Un
        # `float` acumula error y el total del remito termina a centavos del
        # que se lee fila por fila — mismo criterio que `servicios.precio`.
        sa.Column("cantidad", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
    )
    op.create_index(
        "ix_incidencias_cargos_incidencia_id", "incidencias_cargos",
        ["incidencia_id"],
    )


def downgrade():
    op.drop_index(
        "ix_incidencias_cargos_incidencia_id", table_name="incidencias_cargos",
    )
    op.drop_table("incidencias_cargos")
