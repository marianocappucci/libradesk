"""La lista de precios del cliente: lo que hace que las listas sirvan.

## Qué problema resuelve

Hoy Lagrace tiene **tres listas de precios** —«Lista general», «Resellers» y
«Mostrador»— con **43 precios cargados**, y **ningún circuito las aplica**.
Verificado el 2026-08-16: ni ventas, ni remitos, ni presupuestos, ni los
materiales de un reclamo. Todo cotiza por `catalog_items.default_sale_price`.

O sea que alguien cargó 43 precios diferenciados por segmento creyendo que
servían para algo, y no cambian nada en ninguna pantalla. Es un cabo suelto, no
un hueco de diseño: el mecanismo está construido y desenchufado.

Lo que faltaba era **de dónde saber qué lista le toca a cada uno**, y eso es esta
columna.

## Sin FK, y ya van varias

`price_lists` es de **LibraCommerce** y la cadena de Alembic de este producto no
la toca. Misma situación que `ventas_remitos.venta_id` (revisión `0026`) y que
`contratos_cuotas.remito_id` (`0025`): la referencia va suelta y la integridad la
sostiene el servicio.

Y acá pesa además el pozo que documenta `comercial.py`: con el pragma de FKs
activo, SQLite resuelve la tabla padre **al preparar el chequeo**, así que una FK
contra una tabla que este producto no creó rompe *todo* INSERT sobre `clients`
—incluso con la columna en NULL—.

## NULL es "la lista por defecto", y es el default

Un cliente sin lista asignada cotiza por la que esté marcada `is_default`, que es
exactamente lo que pasa hoy con todos. Así que **la adopción es explícita**: los
14 clientes de Lagrace siguen cotizando igual hasta que alguien les asigne una,
y nadie ve cambiar un precio por haber corrido esta migración.
"""
from alembic import op
import sqlalchemy as sa

revision = "0028_lista_precios_cliente"
down_revision = "0027_visitas_de_mantenimiento"
branch_labels = None
depends_on = None


def upgrade():
    # Sin FK: `price_lists` es de LibraCommerce. Ver el docstring.
    op.add_column(
        "clients",
        sa.Column("price_list_id", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("clients", "price_list_id")
