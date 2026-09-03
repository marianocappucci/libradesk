"""El devengado de un contrato: `contratos_cuotas` — fase 2 del módulo de alquiler.

Sale del pedido del humano del 2026-08-14: *"son parte del circuito y también hay
que poder facturarlos, así que tenemos que poder generar el remito de eso, que
entiendo que son remitos que se deberían generar automáticamente en el sistema"*.

## Qué faltaba

El sistema sabía **cuánto** vale el alquiler de agosto —lo resuelve
`contratos_precios`— pero **nunca decía que agosto se devengó**. Verificado el
2026-08-14 contra `origin/develop`: `contratos_cuotas` no existía en ningún
archivo del repo, ni tabla, ni modelo, ni migración, ni pantalla. El precio de un
contrato se sabía y no se cobraba nunca.

La cuota es el insumo del remito, no al revés: un generador automático necesita
de dónde sacar el período que cobra, la idempotencia de no emitir agosto dos
veces, el prorrateo del primer mes y la mora.

## El único es PARCIAL, y esa es la decisión de esta migración

`ix_cuota_periodo_recurrente` es único sobre `(contrato_id, periodo_desde)` pero
**sólo** sobre los tres cargos que representan el período —`alquiler`,
`proporcional`, `mantenimiento`— y **excluyendo las anuladas**.

El diseño del 2026-08-04 lo proponía sobre `(contrato_id, tipo_cargo,
periodo_desde)`, y esa forma tiene dos defectos que aparecen recién al escribir
la generación:

1. **Dejaba cobrar el mes dos veces.** Un `alquiler` y un `proporcional` del
   mismo período son dos filas con distinto `tipo_cargo`, así que el único no las
   veía chocar — y son exactamente el mismo mes, una entera y otra a medias.
2. **Prohibía dos reparaciones en el mismo mes**, que es legítimo y pasa seguido.

Excluir las anuladas es lo que hace que anular una cuota permita volver a
generar el período. Sin eso, un error de carga dejaría el mes bloqueado para
siempre.

> 🔑 **El índice parcial no es un lujo de PostgreSQL que haya que evitar.** Este
> producto tiene una guarda en `app/database.py` que rechaza cualquier motor que
> no sea PostgreSQL (desde el 2026-08-12), así que no hay un segundo motor con el
> que esto tenga que ser compatible.

## Los importes se congelan, no se recalculan

`importe_base` e `importe_total` se escriben al generar y no se vuelven a tocar;
`precio_id` deja la trazabilidad de con qué precio salió. Si mañana el precio se
actualiza con retroactivo, la cuota emitida no se mueve. Recalcular al leer haría
que reimprimir una liquidación vieja diera otro número, que es justamente lo que
`contratos_precios` existe para evitar.

## `remito_id` nace en esta migración aunque lo escriba la pieza B

Mismo criterio que `contratos.archivo_pdf`, que se creó en la fase 1 para la
fase 3: la columna cuesta nada ahora y una migración entera después. Va **sin
FK**: los remitos son de LibraCore y viven en su propio esquema, así que una FK
de acá para allá ataría las dos cadenas de migración.

> ⚠️ **`abono` no aparece en esta migración, a propósito.** Es un valor nuevo de
> `contratos.tipo_contrato`, que es un `String(50)` sin CHECK ni enum: la lista
> válida la sostiene `TIPOS_CONTRATO` en el servicio. Agregarlo no toca el
> schema. La decisión de no poner el CHECK en la base es de la fase 1 y se
> respeta acá.
"""
import sqlalchemy as sa
from alembic import op

revision = "0025_contratos_cuotas"
down_revision = "0024_cobertura_del_abono"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contratos_cuotas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "contrato_id", sa.Integer(),
            sa.ForeignKey("contratos.id"), nullable=False,
        ),
        sa.Column("periodo_desde", sa.Date(), nullable=False),
        sa.Column("periodo_hasta", sa.Date(), nullable=False),
        sa.Column("concepto", sa.String(255), nullable=False),
        sa.Column("tipo_cargo", sa.String(30), nullable=False),
        sa.Column("fecha_emision", sa.Date(), nullable=False),
        sa.Column("fecha_vencimiento", sa.Date(), nullable=True),
        # 🔑 **NOT NULL y sin `server_default`**, que es la convención de las
        # otras once tablas del producto: el default vive en el modelo, del lado
        # de Python. Se escribieron con `server_default` en el primer intento y
        # `test_alembic_construye_lo_mismo_que_create_all` lo agarró — la tabla
        # que arma la migración y la que arma `create_all()` tienen que ser la
        # misma, y un default del lado del servidor las separa.
        sa.Column("importe_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("bonificacion", sa.Numeric(12, 2), nullable=False),
        sa.Column("impuestos", sa.Numeric(12, 2), nullable=False),
        sa.Column("interes_mora", sa.Numeric(12, 2), nullable=False),
        sa.Column("importe_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("moneda", sa.String(3), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column(
            "precio_id", sa.Integer(),
            sa.ForeignKey("contratos_precios.id"), nullable=True,
        ),
        # Sin FK: los remitos son de LibraCore. Ver el docstring.
        sa.Column("remito_id", sa.Integer(), nullable=True),
        sa.Column("factura_numero", sa.String(50), nullable=True),
        sa.Column("comprobante_pago", sa.String(255), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        # `nullable=False` y `CURRENT_TIMESTAMP`, igual que las otras once
        # tablas del producto: el modelo lo declara `Mapped[datetime]` sin
        # `| None`, o sea NOT NULL, y el guard de Alembic compara las dos cosas.
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
    )

    for columna in (
        "contrato_id", "periodo_desde", "fecha_emision", "fecha_vencimiento",
        "tipo_cargo", "estado", "precio_id", "remito_id",
    ):
        op.create_index(
            f"ix_contratos_cuotas_{columna}", "contratos_cuotas", [columna],
        )

    # El único parcial. Ver el docstring: es la decisión de esta migración.
    op.create_index(
        "ix_cuota_periodo_recurrente",
        "contratos_cuotas",
        ["contrato_id", "periodo_desde"],
        unique=True,
        postgresql_where=sa.text(
            "tipo_cargo IN ('alquiler', 'proporcional', 'mantenimiento') "
            "AND estado <> 'anulada'"
        ),
    )


def downgrade():
    op.drop_index("ix_cuota_periodo_recurrente", table_name="contratos_cuotas")
    for columna in (
        "contrato_id", "periodo_desde", "fecha_emision", "fecha_vencimiento",
        "tipo_cargo", "estado", "precio_id", "remito_id",
    ):
        op.drop_index(f"ix_contratos_cuotas_{columna}", table_name="contratos_cuotas")
    op.drop_table("contratos_cuotas")
