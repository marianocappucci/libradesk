"""Qué parte de un reclamo cubre el abono del cliente y qué parte se factura.

Sale del pedido del humano del 2026-08-14: *"los reclamos de los clientes con
abono se guardan en incidencias por una cuestión de trazabilidad, deberíamos ver
qué es lo que está contemplado dentro del contrato del abono de ese cliente y qué
va por fuera, o sea que en esos casos deberíamos poder elegir si la incidencia
corre por dentro del abono o por fuera, tanto total como parcial"*.

## Por qué hacen falta columnas nuevas y no alcanza lo que había

`clientes.tipo_facturacion` ya distingue `mensual` de `por_servicio` desde la
baseline, pero es **del cliente**, no del reclamo: dice que hay abono, no qué
entra en él. Y `estado_facturacion` no sirve para esto por dos motivos: habla del
**cobro** (`pendiente_cobro` / `facturada`), no de la cobertura, y además **no lo
escribe nadie** — existe como filtro de reportes y el frontend siempre manda
`null`. Meter la cobertura ahí sería darle un segundo significado a un campo que
ya tiene uno.

## Las tres columnas

- `cobertura_abono` — `total` (todo el reclamo entra al abono y no se factura
  nada), `parcial` o `fuera` (se factura entero, que es como se comportaba el
  producto hasta hoy). **NULL** es un tercer estado con sentido propio: *nadie lo
  decidió todavía*. Por eso no lleva default — un `'fuera'` server-side haría
  indistinguible "se decidió facturarlo" de "nunca se miró", que es justo la
  diferencia que habilita la guarda de `convertir_a_remito()`.

- `abono_horas_cubiertas` — cuántas de las `horas_invertidas` entran al abono.
  Sólo tiene sentido con `parcial`. Cubre el abono con **tope de horas**: 2 de 5
  adentro, 3 se facturan. Misma precisión que `horas_invertidas` (`Numeric(5,2)`)
  a propósito: son la misma magnitud y una resta entre las dos no tiene que
  redondear.

- `abono_materiales_incluidos` — si los materiales del reclamo entran al abono o
  se facturan aparte. Sólo con `parcial`. Cubre el caso típico de un abono de
  mantenimiento: la mano de obra está incluida y los repuestos se cobran.

Son dos ejes y no uno porque los dos existen en la calle y **no son el mismo**:
un abono puede cubrir 2 horas de 5 *y* además incluir los materiales. Modelarlo
con una sola columna obligaría a una segunda migración el día que aparezca el
otro criterio, y el costo de la de más son dos columnas nullable.

> ⚠️ **Nullable las tres, y sin backfill.** Los reclamos que ya existen se
> facturaron —o se van a facturar— con el criterio de antes, que es "todo se
> factura". Escribirles `'fuera'` en masa diría que alguien tomó esa decisión
> reclamo por reclamo, y no pasó. El código trata `NULL` como "se factura entero"
> para el cliente sin abono, que es el comportamiento histórico.

> 🔑 **No hay CHECK de coherencia en la base.** Que `abono_horas_cubiertas` no
> supere a `horas_invertidas`, y que las dos columnas de detalle sólo tengan
> valor con `parcial`, lo sostiene `IncidenciaRepository`. Un CHECK acá partiría
> la validación en dos lugares y daría un `IntegrityError` sin mensaje útil donde
> hoy sale un texto que dice qué corregir.
"""
import sqlalchemy as sa
from alembic import op

revision = "0024_cobertura_del_abono"
down_revision = "0023_sacar_firma_del_cliente"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "incidencias", sa.Column("cobertura_abono", sa.String(20), nullable=True),
    )
    op.add_column(
        "incidencias",
        sa.Column("abono_horas_cubiertas", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        "incidencias",
        sa.Column("abono_materiales_incluidos", sa.Boolean(), nullable=True),
    )


def downgrade():
    op.drop_column("incidencias", "abono_materiales_incluidos")
    op.drop_column("incidencias", "abono_horas_cubiertas")
    op.drop_column("incidencias", "cobertura_abono")
