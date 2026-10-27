"""El ajuste por índice del contrato: `indice_ajuste` y `periodicidad_ajuste`.

`metodo_actualizacion='indice'` estaba declarado desde la fase 1 y se comportaba como `manual` «hasta que se defina de
dónde sale el índice». Desde libracore v1.196.0 el motor guarda los índices oficiales (ICL, IPC, CER, UVA, dólar A 3500,
Casa Propia; ADR-085 del motor) y calcula el ajuste, así que el contrato sólo tiene que decir **cuál** usa y **cada
cuánto** se ajusta. Pedido del humano del 2026-10-26, junto con el producto nuevo LibraInmo.

- `indice_ajuste`: una clave de `libracore.indices_ajuste.INDICES` (`icl`, `ipc`, ...). La valida el repositorio, no
  un CHECK: el catálogo es del motor y crece con un bump, no con una migración de este producto.
- `periodicidad_ajuste`: `mensual` ... `anual`, contada desde `fecha_inicio` (`libracore.periodos.periodo_anclado`).

Aditiva: dos columnas nullable, sin default. Los contratos existentes no cambian: ninguno tiene `indice` cargado con
efecto, porque hasta hoy se comportaba como `manual`.
"""
import sqlalchemy as sa
from alembic import op

revision = "0043_ajuste_por_indice"
down_revision = "0042_retirar_cc_resumen"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("contratos", sa.Column("indice_ajuste", sa.String(30), nullable=True))
    op.add_column("contratos", sa.Column("periodicidad_ajuste", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("contratos", "periodicidad_ajuste")
    op.drop_column("contratos", "indice_ajuste")
