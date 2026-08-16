"""El vínculo entre una venta y el remito que la lleva a facturación.

Sale del pedido del humano del 2026-08-16: *"la venta de equipo por qué no genera
remito? debería generarlo porque lo vamos a tener cargado como stock y es una
venta que después va a ir a SOS Contador"*.

## Qué faltaba

`ORIGENES_ENVIABLES` de la bandeja es `(ORIGEN_REMITO,)` y **una venta no
generaba ningún remito** — verificado el 2026-08-16, cero coincidencias de
`remito` en `services/ventas.py` y `routers/ventas.py`. O sea que una venta
registraba, descontaba stock y debitaba la cuenta corriente, y no tenía **ningún**
camino a facturarse. Mientras tanto la pantalla de Ventas ya prometía lo
contrario: *"La factura la emite SOS Contador desde Enviar a facturar"*.

No fue una decisión: quedó anotado como pregunta abierta el 2026-08-14 —con las
tres opciones escritas, "genera remito / entra como origen propio / se corrige el
texto"— y nunca se resolvió. Lo que la frenaba era el doble conteo en cuenta
corriente, que esta migración habilita a resolver dándole al puente cómo
reconocer un remito nacido de una venta.

## Por qué una tabla de vínculo y no una columna

Las otras tres fuentes guardan el `remito_id` en su propia tabla:
`incidencias.remito_id` (revisión `0021`), `contratos_cuotas.remito_id` (revisión
`0025`) y `presupuestos.remito_id`. Acá no se puede, y no es por gusto:

**`sales` es de LibraCommerce.** La crea `init_schema()` del motor y la cadena de
Alembic de este producto **no la toca nunca** — se verificó archivo por archivo.
Agregarle una columna desde acá significaría que el schema de una tabla del motor
dependa de la cadena de un consumidor: el `downgrade` intentaría sacar una
columna de una tabla que este producto no creó, y una instancia nueva la crearía
sin la columna porque el motor no la conoce.

Así que el vínculo vive en una tabla propia, que es exactamente lo que ya hace
`envios_facturacion` con los remitos (revisión `0014`): tabla de LibraDesk,
referencias sueltas, integridad sostenida por el router.

## Las dos referencias van sin FK, por dos motivos distintos

| Columna | Apunta a | Por qué sin FK |
|---|---|---|
| `venta_id` | `sales`, de **LibraCommerce** | La tabla padre la maneja el motor, no esta cadena |
| `remito_id` | `remitos`, de **LibraCore** | Mismo motivo que `contratos_cuotas.remito_id`: ataría dos cadenas de migración |

Es el mismo pozo que documenta `comercial.py`: con el pragma de FKs activo,
SQLite resuelve la tabla padre **al preparar el chequeo**, así que una FK contra
una tabla que este producto no creó rompe *todo* INSERT, incluso con la columna
en NULL.

## El único es sobre `venta_id`, y es la regla del módulo

**Una venta = un remito.** Es lo que hace idempotente a `convertir_a_remito()`:
el segundo click encuentra la fila y devuelve el remito que ya existe en vez de
emitir un segundo comprobante por la misma venta.

No es único sobre `remito_id` a propósito: nada impide hoy que alguien arme a
mano un remito y después lo asocie, y sobre todo **un remito puede legítimamente
cubrir varias ventas** el día que se agrupe como ya se agrupan los reclamos. La
regla que hay que sostener hoy es que una venta no salga dos veces; la otra
dirección se deja abierta.
"""
from alembic import op
import sqlalchemy as sa

revision = "0026_ventas_remitos"
down_revision = "0025_contratos_cuotas"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ventas_remitos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # Sin FK: `sales` es de LibraCommerce. Ver el docstring.
        sa.Column("venta_id", sa.Integer(), nullable=False),
        # Sin FK: los remitos son de LibraCore. Ver el docstring.
        sa.Column("remito_id", sa.Integer(), nullable=False),
        # `nullable=False` y `CURRENT_TIMESTAMP`, igual que las otras tablas del
        # producto: el modelo lo declara `Mapped[datetime]` sin `| None`, y
        # `test_alembic_construye_lo_mismo_que_create_all` compara las dos cosas.
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        # Una venta = un remito. Es lo que hace idempotente a la conversión.
        #
        # Va como constraint con nombre y **no** como índice único: el modelo lo
        # declara en `__table_args__`, y las dos formas producen DDL distinto.
        # `test_una_base_vacia_se_construye_entera` compara la tabla que arma
        # esta migración contra la que arma `create_all()`, y las separa.
        sa.UniqueConstraint("venta_id", name="uq_ventas_remitos_venta"),
    )

    # No único: lo consulta el puente para saber si un remito nació de una
    # venta, y esa es la lectura caliente de todo esto.
    #
    # El nombre es el que genera SQLAlchemy para un `index=True` sobre la
    # columna (`ix_<tabla>_<columna>`), por el mismo motivo que el único de
    # arriba: si acá se lo llama distinto, las dos tablas no son la misma.
    op.create_index(
        "ix_ventas_remitos_remito_id", "ventas_remitos", ["remito_id"],
    )


def downgrade():
    op.drop_index("ix_ventas_remitos_remito_id", table_name="ventas_remitos")
    op.drop_table("ventas_remitos")
