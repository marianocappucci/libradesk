"""El número del comprobante de servicios y quién reclamó.

Las dos columnas salen del relevamiento de Lagrace
(`wiki/sources/lagrace-relevamiento-whatsapp.md`) y son las brechas 6 y 8 del
backlog de esa venta.

## `nro_cds` — la llave entre el papel y el sistema

El **CDS (Comprobante de Servicios)** es un talonario preimpreso: el que se vio
lleva `N° 0001-00041996`, de la serie 0001-00041701 a 42200 impresa en noviembre
de 2025. El técnico completa el papel en el lugar, el cliente lo firma, y ese
número se tipea después dentro del reclamo. **Es lo único que ata la conformidad
firmada del cliente con el ticket del sistema.**

Va como `String` y no como entero aunque hoy sea `0001-00041996`: el formato es
de un talonario de imprenta, no una secuencia que este sistema genere. Guardarlo
como número obligaría a decidir qué hacer con el punto de venta, y a reconstruir
el formato en cada pantalla que lo muestre.

**Indexado**, porque la pregunta que justifica la columna es "¿qué reclamo es
este papel?" — se busca por él.

**Nullable a propósito y sin default**: los reclamos que se cargan por teléfono
y se resuelven en remoto no tienen comprobante en papel, y los históricos que se
migren van a traer el suyo. Un default vacío haría indistinguible "no
corresponde" de "todavía no se cargó".

> ⚠️ **No hay `UNIQUE`.** Sería lo natural —un talonario no repite número— pero
> las dos razones sociales del grupo tienen talonarios propios, así que el mismo
> número puede existir dos veces. Ponerlo ahora rompería la migración histórica
> el día que entren los dos. Cuando se decida si son una instancia o dos, se
> revisa.

## `reclamante` — quién llamó

Distinto del cliente: en el reclamo de Neumyser figura `FACUNDO`. Es texto libre
y no una FK a una tabla de contactos, porque **eso es lo que hay**: la persona
que atiende el teléfono anota un nombre de pila. Una tabla de contactos por
cliente es otro módulo y nadie la pidió.
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_nro_cds_y_reclamante"
down_revision = "0018_proveedores_forma_del_motor"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("incidencias", sa.Column("nro_cds", sa.String(30), nullable=True))
    op.add_column("incidencias", sa.Column("reclamante", sa.String(120), nullable=True))
    op.create_index("ix_incidencias_nro_cds", "incidencias", ["nro_cds"])


def downgrade():
    op.drop_index("ix_incidencias_nro_cds", table_name="incidencias")
    op.drop_column("incidencias", "reclamante")
    op.drop_column("incidencias", "nro_cds")
