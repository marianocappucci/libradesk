"""IVA: alicuota por servicio y condicion frente al IVA del cliente.

Item 2 de los pendientes transversales. Dos columnas, las dos aditivas y
nullable-o-con-default: ninguna fila existente cambia de comportamiento.

- `servicios.iva_rate` — la alicuota con la que se cotiza ese servicio. El
  default 21% es lo que el sistema asumia para todo hasta ahora, asi que los
  servicios ya cargados siguen exactamente igual.

- `clientes.condicion_iva` — decide si el comprobante muestra el IVA
  discriminado o el precio final. **Nullable a proposito**: los clientes que ya
  existen no la tienen, y `iva.discrimina(None)` cae a precio final. Un default
  de "Responsable Inscripto" le habria cambiado el comprobante a todos de
  golpe, incluido el cliente real que ya usa el sistema.

Lo que NO toca: el schema de `remitos`/`presupuestos`. Es de LibraCore y lo
comparten Contalibra y Restolibra; la alicuota por linea viaja **dentro del
JSON de `items`**, que ya es texto libre y no tiene forma fija.
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_iva_por_item"
down_revision = "0012_servicios"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "servicios",
        sa.Column("iva_rate", sa.Numeric(5, 4), nullable=False, server_default="0.21"),
    )
    op.add_column("clientes", sa.Column("condicion_iva", sa.String(50)))


def downgrade():
    op.drop_column("clientes", "condicion_iva")
    op.drop_column("servicios", "iva_rate")
