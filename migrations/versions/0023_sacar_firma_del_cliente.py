"""Se saca la conformidad firmada dentro del sistema: vuelve al papel.

La revisión `0020` puso la conformidad adentro del ticket —firma en la pantalla
del técnico, quién firmó y las "Observaciones del Cliente"— para reemplazar el
talonario. **Decisión del 2026-08-14: la conformidad se firma en papel, fuera
del sistema.** El circuito de papel no se digitaliza; lo único que LibraDesk
guarda de él es el `nro_cds` de la revisión `0019`, que es la llave entre el
comprobante firmado y el ticket, y ése se queda.

## Esto borra datos, y no tiene vuelta atrás por migración

`incidencias_firmas` es la única copia de las firmas tomadas entre el
2026-08-13 y hoy. El `downgrade()` puede recrear la tabla, pero **vacía**: una
imagen no se reconstruye desde el schema. Antes de correr esto en una instancia
con firmas cargadas hay que decidir si se archivan; en `demo` la respuesta es
que no, porque son de prueba.

`DROP TABLE` y no un borrado lógico: dejar la tabla sin nada que la escriba ni
la lea la convierte en un blob de 40 KB por ticket que el backup arrastra y que
el próximo autogenerate propone dropear igual, un mes más tarde y sin este
comentario al lado.
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_sacar_firma_del_cliente"
down_revision = "0022_servicio_valor_hora"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("incidencias_firmas")


def downgrade():
    # La forma exacta de `0020`. Vuelve la tabla, no las firmas.
    op.create_table(
        "incidencias_firmas",
        sa.Column(
            "incidencia_id", sa.Integer(),
            sa.ForeignKey("incidencias.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("firmante", sa.String(160), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("imagen", sa.Text(), nullable=False),
        sa.Column("firmado_at", sa.DateTime(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
    )
