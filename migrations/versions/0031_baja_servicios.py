"""Se dropea `servicios`: la fase 3 del expand/contract, y la última.

## Dónde estamos

Esta es la tercera y última release de la mudanza del catálogo de servicios al
catálogo de LibraCommerce:

| | Qué hizo | Release |
|---|---|---|
| **Fase 1** | `ServicioCatalogoRepository`, el mismo contrato de 8 métodos sobre `catalog_items` | #195 |
| **Fase 2** | La app pasó a **leer** del catálogo; la copia de arranque llenó el destino; `servicios` quedó intacta como red | #195 |
| **Fase 3** | Se dropea el origen — **esto** | esta |

Entre la 2 y la 3 hay una promoción a producción y una verificación, que es
justamente el punto de partir el trabajo en tres: la red existió mientras hubo
algo que pudiera salir mal.

## Por qué se puede dropear ahora, medido

La copia se verificó **por nombre y no por conteo** el 2026-08-17, en las cuatro
instancias. Dos conteos iguales pueden ser dos conjuntos distintos, y acá lo que
está en juego es si el origen se puede borrar:

| Instancia | `servicios` | En el catálogo | ¿Todos, por nombre? |
|---|---|---|---|
| `libradesk-dev` | 11 | 11 | sí |
| `libradesk-demo` | 6 | 6 | sí |
| `libradesk-lagrace` | 7 | 7 | sí |
| `libradesk-compulibra` | 0 | 0 | ⚠️ no prueba nada: no tenía qué copiar |

La fila de compulibra se deja escrita como lo que es. Un `0 = 0` no es evidencia
de que la copia funcione; la evidencia son las otras tres.

## `DROP TABLE` y no baja lógica

Mismo criterio que la revisión `0023` cuando sacó `incidencias_firmas`: una tabla
que nadie escribe ni lee es peso que el backup arrastra, y **el próximo
autogenerate va a proponer dropearla igual** — un mes más tarde y sin este
comentario al lado.

## ⚠️ El `downgrade()` devuelve la tabla, no los datos

Recrea la forma exacta que dejaron `0012` + `0013` + `0022`, y **vacía**. Volver
atrás la migración no revierte la mudanza: los servicios viven en
`catalog_items`, que esta revisión no toca. El camino de vuelta real es volver a
apuntar `app.state.servicios` al repositorio viejo, y ése dejó de existir en esta
misma release **a propósito** — con la tabla dropeada, un repositorio que la
consulte es una promesa que no se puede cumplir.

Por eso el orden importa y por eso esto es la fase 3 y no parte de la 2: la
vuelta atrás barata se ofreció mientras tuvo sentido ofrecerla.
"""
import sqlalchemy as sa
from alembic import op

revision = "0031_baja_servicios"
down_revision = "0030_primera_visita"
branch_labels = None
depends_on = None


def upgrade():
    # Los índices se van con la tabla; nombrarlos acá sería redundante y en
    # PostgreSQL un `drop_index` posterior al `drop_table` falla.
    op.drop_table("servicios")


def downgrade():
    # La forma exacta que dejaron las tres revisiones que la construyeron:
    # `0012` la creó, `0013` le sumó `iva_rate` y `0022` `es_valor_hora`.
    op.create_table(
        "servicios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.String(500), nullable=False, server_default=""),
        # Numeric y no Float: es plata.
        sa.Column("precio", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("iva_rate", sa.Numeric(5, 4), nullable=False, server_default="0.21"),
        sa.Column("es_valor_hora", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(),
                  server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
    )
    op.create_index("ix_servicios_nombre", "servicios", ["nombre"])
    op.create_index("ix_servicios_activo", "servicios", ["activo"])
    op.create_index("ix_servicios_es_valor_hora", "servicios", ["es_valor_hora"])
