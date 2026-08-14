"""El remito que se generó de un reclamo.

Es la mitad persistente del camino a facturación de un trabajo por servicio:
desde el 2026-08-13 LibraDesk manda a facturar **sólo remitos** —lo que habilita
a facturar es la entrega hecha— y un reclamo cerrado llega a la bandeja
convirtiéndose en remito, igual que un presupuesto aceptado. Ver
`app/routers/facturacion.py` y `IncidenciaRepository.convertir_a_remito`.

## Por qué no hay ForeignKey

`incidencias` es un modelo de SQLAlchemy; `remitos` **no**: la crea el DDL crudo
de `app/services/remitos_presupuestos.py` porque el dominio de remitos vive en
LibraCore. O sea que `remitos` no está en `Base.metadata`, y `app/schema.py`
`include_name()` filtra el autogenerate por ahí. Declarar la FK dejaría a
Alembic apuntando a una tabla que no ve.

Es el mismo pozo que ese módulo ya documenta para `remitos.client_id ->
clients`, con los dueños al revés. Quien sostiene la integridad es
`RemitoService.delete()`, que se niega a borrar un remito que una incidencia
referencia — la misma defensa que ya tenía para los presupuestos convertidos.

## Nullable y sin default

La enorme mayoría de los reclamos no se convierte nunca: un ticket resuelto por
teléfono no genera remito. `NULL` significa "no se convirtió", que es distinto
de un `0` que habría que interpretar.

**Indexada** porque la pregunta que la justifica es la inversa —"¿qué reclamo
generó este remito?"— y la contesta `RemitoService.dependencias()` en cada
intento de borrado.
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_incidencia_remito_id"
down_revision = "0020_firma_del_cliente"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("incidencias", sa.Column("remito_id", sa.Integer(), nullable=True))
    op.create_index("ix_incidencias_remito_id", "incidencias", ["remito_id"])


def downgrade():
    op.drop_index("ix_incidencias_remito_id", table_name="incidencias")
    op.drop_column("incidencias", "remito_id")
