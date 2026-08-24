"""Contratos con el proveedor — fase 2 del control de consumibles.

## Qué faltaba

La revisión `0035` dejó registrado que un tóner se pidió, llegó y se puso. Lo
que no sabía es **por qué llegaba sin cobrar**: eso está en un contrato entre el
cliente y un tercero, que hasta hoy vivía afuera del sistema. Sin él no se puede
contestar si un insumo lo cubre el contrato o hay que pagarlo, a quién se le
pide, hasta cuándo, ni qué máquinas del parque quedaron afuera.

## Por qué no entra en `contratos`

`contratos` es la dirección inversa **y el dominio de la plata**: activos
nuestros colocados en un cliente, con precios, cuotas, actas y el puente a
facturación. Acá el contrato es entre el cliente y un tercero, y nosotros lo
administramos sin cobrarlo.

Compartir la tabla obligaría a filtrar en cada consulta de cuotas, liquidación y
facturación para no contar contratos ajenos. Es el mismo argumento con el que
`activos` se separó de `equipos` en el módulo de alquileres, y el mismo
beneficio: **ninguna consulta de plata necesita enterarse de que esta tabla
existe**.

## La cobertura, con fechas y en tabla aparte

`contratos_proveedor_equipos`, igual que `contratos_equipos`: el proveedor
cambia una máquina por otra y el contrato sigue siendo el mismo. Con las fechas,
*"¿qué contrato cubría esta máquina cuando se puso ese tóner de junio?"* tiene
respuesta — con una columna en `equipos` habría una sola verdad, la de hoy.

Línea vigente = `fecha_baja IS NULL`, el mismo estado derivado que
`equipos_reparaciones` saca de `fecha_retorno`.

## Ninguna columna en `equipos_insumos`

La cobertura de un insumo **se resuelve**, no se guarda: `contrato_de(equipo,
fecha)` la contesta para cualquier momento, incluido el pasado. Guardar un
`contrato_proveedor_id` en la fila del insumo sería una segunda fuente de verdad
sobre lo mismo, y el día que se corrija una fecha de cobertura quedarían
diciendo cosas distintas.

## Lo que NO trae

**Ninguna columna de plata**: ni abono, ni precio por copia. El costo de un
contrato de proveedor es un egreso —dominio de `compras`— y no una columna acá;
este producto ya pagó una vez el precio de duplicar la plata, con la tabla
`servicios` que la revisión `0031` terminó dropeando.

**Ningún tope de copias incluidas**, que es lo primero que uno querría poner. El
contrato real dice "10.000 copias por mes", pero compararlo pide una **lectura
periódica del contador**, y hoy el contador se lee sólo al cambiar el tóner. Una
columna con el tope, sin la lectura que la mida, es una promesa que la primera
pantalla desmiente.
"""
import sqlalchemy as sa
from alembic import op

revision = "0036_contratos_de_proveedor"
down_revision = "0035_insumos_por_equipo"
branch_labels = None
depends_on = None


_INDICES_CONTRATOS = ("proveedor_id", "cliente_id", "fecha_inicio", "fecha_fin")
_INDICES_EQUIPOS = ("contrato_proveedor_id", "equipo_id", "fecha_baja")


def upgrade():
    op.create_table(
        "contratos_proveedor",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # `CPR-00000001`, correlativo propio. Misma forma que `CTR-` y `PRES-`.
        sa.Column("numero", sa.String(length=50), nullable=False),
        sa.Column(
            "proveedor_id", sa.Integer(), sa.ForeignKey("proveedores.id"),
            nullable=False,
        ),
        sa.Column(
            "cliente_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False,
        ),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        # El número que le da EL PROVEEDOR al contrato, que es el que hay que
        # citarle. Mismo problema que resuelve `equipos_referencias` con las
        # máquinas, un nivel más arriba.
        sa.Column("numero_externo", sa.String(length=100), nullable=True),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        # NULL = sin vencimiento pactado, que no es lo mismo que vencido.
        sa.Column("fecha_fin", sa.Date(), nullable=True),
        sa.Column("renovacion_automatica", sa.Boolean(), nullable=False),
        sa.Column("incluye_insumos", sa.Boolean(), nullable=False),
        sa.Column("incluye_service", sa.Boolean(), nullable=False),
        # El contacto es del CONTRATO y no del proveedor: el mismo proveedor
        # puede tener un contrato con el hospital y otro con la clínica, cada
        # uno con su interlocutor.
        sa.Column("contacto_nombre", sa.String(length=255), nullable=True),
        sa.Column("contacto_telefono", sa.String(length=100), nullable=True),
        sa.Column("contacto_email", sa.String(length=255), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.UniqueConstraint("numero"),
    )
    for columna in _INDICES_CONTRATOS:
        op.create_index(
            f"ix_contratos_proveedor_{columna}", "contratos_proveedor", [columna],
        )

    op.create_table(
        "contratos_proveedor_equipos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "contrato_proveedor_id", sa.Integer(),
            sa.ForeignKey("contratos_proveedor.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "equipo_id", sa.Integer(), sa.ForeignKey("equipos.id"), nullable=False,
        ),
        sa.Column("fecha_alta", sa.Date(), nullable=False),
        # NULL = el contrato la sigue cubriendo.
        sa.Column("fecha_baja", sa.Date(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
    )
    for columna in _INDICES_EQUIPOS:
        op.create_index(
            f"ix_contratos_proveedor_equipos_{columna}",
            "contratos_proveedor_equipos", [columna],
        )


def downgrade():
    for columna in _INDICES_EQUIPOS:
        op.drop_index(
            f"ix_contratos_proveedor_equipos_{columna}",
            table_name="contratos_proveedor_equipos",
        )
    op.drop_table("contratos_proveedor_equipos")

    for columna in _INDICES_CONTRATOS:
        op.drop_index(
            f"ix_contratos_proveedor_{columna}", table_name="contratos_proveedor",
        )
    op.drop_table("contratos_proveedor")
