"""La conformidad del cliente: firma, quién firmó y sus observaciones.

Cierra la brecha 7 del backlog de [[lagrace-comunicaciones]]. En el comprobante
de servicios en papel, el pie dice que **la firma certifica la conformidad del
trabajo** y que el pago va a 15 días de la factura; hoy ese respaldo vive sólo
en el talonario archivado.

## Por qué es una tabla aparte y no tres columnas en `incidencias`

Una firma es un PNG en base64: entre 10 y 40 KB por ticket. En `incidencias`
—que se lista entera en la grilla, se filtra y se ordena— eso significa
arrastrar megabytes en consultas que nunca miran la firma. Con la tabla aparte,
"¿este ticket está firmado?" es un JOIN barato y el blob se lee sólo al abrir la
ficha o al imprimir.

**PK = `incidencia_id`**, sin id sintético: una incidencia tiene una
conformidad o no la tiene. Dos firmas para el mismo trabajo no significan nada,
y sin la PK habría que decidir cuál gana.

`ON DELETE CASCADE`: si el ticket se borra, su conformidad no tiene de qué ser
conformidad.

## La imagen se guarda como texto, no como binario

Es un data URL (`data:image/png;base64,...`), que es lo que produce el canvas
del navegador y lo que consume tanto un `<img>` como fpdf. Guardarlo como
`LargeBinary` obligaría a decodificar y re-codificar en las dos puntas para no
ganar nada: el tamaño lo domina el PNG, no el 33 % del base64.

> ⚠️ **El tamaño se valida en el servicio, no acá.** Una columna `Text` acepta
> cualquier cosa, y un cliente que mande 10 MB de "firma" llenaría el disco sin
> que la base se queje. Ver `app/services/firma.py`.
"""
import sqlalchemy as sa
from alembic import op

revision = "0020_firma_del_cliente"
down_revision = "0019_nro_cds_y_reclamante"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "incidencias_firmas",
        sa.Column(
            "incidencia_id", sa.Integer(),
            sa.ForeignKey("incidencias.id", ondelete="CASCADE"), primary_key=True,
        ),
        # Quién firmó: el nombre que la persona escribe al lado de su firma.
        # Nullable porque el papel de ellos tampoco lo exige — a veces está
        # sólo la firma.
        sa.Column("firmante", sa.String(160), nullable=True),
        # "Observaciones del Cliente" del comprobante en papel. Es un campo del
        # cliente, no del técnico: por eso vive con la firma y no en `notas`.
        sa.Column("observaciones", sa.Text(), nullable=True),
        # El data URL del PNG.
        sa.Column("imagen", sa.Text(), nullable=False),
        sa.Column("firmado_at", sa.DateTime(), nullable=False),
        # Quién de LibraDesk tomó la firma. No es el firmante: es el técnico que
        # le acercó el teléfono.
        sa.Column("usuario_id", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_table("incidencias_firmas")
