"""Actas de entrega y devolución: `contratos_actas` — fase 3 del alquiler.

## Qué faltaba

El circuito de alquiler estaba usable **para cobrar** —contrato, precio con
vigencia, devengado y remito— y no para **documentar la entrega**: se instalaba
un equipo en el cliente y no quedaba ningún papel que lo probara. Verificado
contra `origin/develop` antes de escribir esto: cero coincidencias de
`contratos_actas` en `app/`, `migrations/` y `frontend/src/`.

Lo que el sistema sabía era el **acuerdo** (el contrato) y la **ventana** (desde
cuándo está puesto el activo). Lo que no sabía era el **acto**: quién lo llevó,
quién lo recibió, con qué accesorios y en qué estado. Cuando el equipo vuelve
sin el cargador, esa es exactamente la fila que falta.

## Encabezado y líneas, y los campos del equipo van en la línea

El diseño del 2026-08-04 listaba `estado_fisico`, `accesorios`, `faltantes`,
`danios` y `cargo_reposicion` en el encabezado *y* declaraba líneas por activo.
Un acta cubre varios equipos —se entregan tres el mismo día en un solo papel—,
así que un `estado_fisico` de encabezado no puede contestar por los tres. Son
propiedades del equipo y viven en `contratos_actas_lineas`.

## La línea apunta a la COLOCACIÓN, no al activo

`contrato_equipo_id` y no `activo_id`: un mismo activo puede haber estado
puesto, retirado y vuelto a poner en el mismo contrato, o sea dos filas de
`contratos_equipos`. Apuntando a la colocación el acta dice de cuál de las dos
habla; apuntando al activo sería ambiguo justo en el caso en que alguien va a
discutir. El `activo_id` se lee por el join, que es la única fuente.

## No hay tabla de firmas, y es una decisión con precedente

El PR #121 (revisión `0020`) agregó un pad de firma en pantalla y la revisión
`0023` lo **retiró**, dropeando `incidencias_firmas`: *"la conformidad del
cliente vuelve al papel"*. Acá se respeta. `entrega_nombre` y `recibe_nombre`
son aclaraciones **tipeadas**; el acta se imprime, se firma a mano y el vínculo
entre el papel y el registro es `numero`.

## Tampoco hay `pdf_path`

El diseño lo listaba. El PDF es una función de los datos —igual que el de los
ingresos, remitos y presupuestos— y se genera al pedirlo: una columna con la
ruta de un archivo que nadie escribe es una promesa que la primera lectura
desmiente. `contratos.archivo_pdf` sí es un archivo de verdad (el contrato
firmado escaneado) y sigue esperando que el producto tenga dónde subir
archivos.

## Sin índice único sobre `(contrato_equipo_id, tipo)`

La invariante —una colocación no se entrega ni se devuelve dos veces— la
sostiene `ActaRepository._ya_documentada()`, en Python y dentro de la
transacción. No va como índice único parcial porque el estado que hay que
excluir (`anulada`) está en el **encabezado** y la unicidad sería sobre la
**línea**: un índice parcial no puede leer la otra tabla. Es la diferencia con
`ix_cuota_periodo_recurrente` de la revisión `0025`, donde el estado y la clave
viven en la misma fila.

## `cuota_id` con FK, a diferencia de `contratos_cuotas.remito_id`

Una devolución con faltantes emite una cuota `reposicion` y el acta la
referencia. Acá la FK **sí** va: `contratos_cuotas` es una tabla de este mismo
producto y de esta misma cadena de migraciones. La que no lleva FK es
`remito_id`, porque los remitos son de LibraCore.
"""
from alembic import op
import sqlalchemy as sa

revision = "0032_contratos_actas"
down_revision = "0031_baja_servicios"
branch_labels = None
depends_on = None


_INDICES_ACTAS = ("contrato_id", "tipo", "fecha", "estado", "cuota_id")
_INDICES_LINEAS = ("acta_id", "contrato_equipo_id")


def upgrade():
    op.create_table(
        "contratos_actas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("numero", sa.String(50), nullable=False),
        sa.Column(
            "contrato_id", sa.Integer(),
            sa.ForeignKey("contratos.id"), nullable=False,
        ),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("entrega_nombre", sa.String(255), nullable=True),
        sa.Column("recibe_nombre", sa.String(255), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        # NOT NULL y sin `server_default`, que es la convención de las otras
        # doce tablas del producto: el default vive en el modelo, del lado de
        # Python, y `test_alembic_construye_lo_mismo_que_create_all` compara
        # que la tabla de la migración y la de `create_all()` sean la misma.
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column(
            "cuota_id", sa.Integer(),
            sa.ForeignKey("contratos_cuotas.id"), nullable=True,
        ),
        sa.Column("usuario", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.UniqueConstraint("numero"),
    )
    for columna in _INDICES_ACTAS:
        op.create_index(f"ix_contratos_actas_{columna}", "contratos_actas", [columna])

    op.create_table(
        "contratos_actas_lineas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "acta_id", sa.Integer(),
            sa.ForeignKey("contratos_actas.id"), nullable=False,
        ),
        sa.Column(
            "contrato_equipo_id", sa.Integer(),
            sa.ForeignKey("contratos_equipos.id"), nullable=False,
        ),
        sa.Column("estado_fisico", sa.Text(), nullable=True),
        sa.Column("accesorios", sa.Text(), nullable=True),
        sa.Column("faltantes", sa.Text(), nullable=True),
        sa.Column("danios", sa.Text(), nullable=True),
        sa.Column("cargo_reposicion", sa.Numeric(12, 2), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
    )
    for columna in _INDICES_LINEAS:
        op.create_index(
            f"ix_contratos_actas_lineas_{columna}", "contratos_actas_lineas", [columna],
        )


def downgrade():
    for columna in _INDICES_LINEAS:
        op.drop_index(
            f"ix_contratos_actas_lineas_{columna}", table_name="contratos_actas_lineas",
        )
    op.drop_table("contratos_actas_lineas")
    for columna in _INDICES_ACTAS:
        op.drop_index(f"ix_contratos_actas_{columna}", table_name="contratos_actas")
    op.drop_table("contratos_actas")
