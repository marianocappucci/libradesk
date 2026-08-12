"""`clientes` pasa a ser la tabla `clients` de LibraCore.

LibraDesk era el **unico** producto de la familia fuera de todo modulo
compartido de clientes: Contalibra, Restolibra y VentaLibra usan
`libracore.db.clients`, y Gestiolibra y MedLibra heredan el suyo de LibraGenda.
Esta revision convierte la tabla propia en la del motor, para que el CRUD pase
a `libracore.db.clients` y se dejen de reimplementar la validacion de CUIT
duplicado y la normalizacion de email/CUIT en las busquedas.

Ver `wiki/analyses/clientes-transversal-familia-libra.md` para el plan completo.
Depende de la revision `0002` de LibraCore, que agrego al motor las cuatro
columnas que solo tenia este producto (`empresa`, `ciudad`, `observaciones`,
`tipo_facturacion`) -- sin eso, esta migracion perderia esos datos.

## Solo PostgreSQL

Decidido el 2026-08-12: **LibraDesk trabaja contra PostgreSQL y nada mas**. Las
tres instancias (`dev`, `demo`, `compulibra`) ya corrian Postgres desde el
2026-08-11, asi que esto no migra nada -- saca del medio un motor que ya no se
usaba en ningun lado.

Vale anotar lo que la decision **evito**, porque era la parte dificil de esta
revision: `clientes` es tabla padre de siete FK (`equipos`, `incidencias`,
`sectores`, `depositos`, `ingresos_reparacion` y las **dos** de `contratos`),
y en SQLite un cambio de tipo obliga a `batch_alter_table`, que reconstruye la
tabla y **deja a las hijas apuntando a un nombre `_old` que despues se borra**
-- la advertencia esta escrita en `0015_entidad_id_texto`, que la esquivo
porque su tabla no era padre de ninguna. En PostgreSQL el problema no existe:
renombrar una tabla o cambiarle el tipo a una columna no la reconstruye, y las
FK siguen a la tabla solas.

## Los dos cambios de tipo, y por que

`activo` pasa de BOOLEAN a INTEGER porque **`libracore.db.clients` consulta
`WHERE activo = 1`**, y PostgreSQL no acepta un entero contra un BOOLEAN. Es el
mismo choque que ya aparecio con `usuarios.activo` al alinearlo con libraauth,
en la direccion contraria.

`created_at` pasa de TIMESTAMP a TEXT para igualar al motor, que la declara
`TEXT DEFAULT (datetime('now'))`. **Es un costo real y conviene decirlo**: se
pierde el tipo y la precision de sub-segundo. Se paga igual porque el punto de
esta fase es que la tabla sea la del motor; una divergencia de tipo por producto
es exactamente lo que rompe en silencio la proxima feature de LibraCore que
toque esa columna.

## Lo que NO cambia

El `UNIQUE` de `email` se **conserva**, aunque el motor no lo tenga: es una
restriccion mas estricta, no una incompatible, y sacarla habilitaria duplicados
que hoy la base rechaza. La API sigue siendo `/api/clientes` y el frontend no se
entera: lo que cambia es la tabla, no el contrato HTTP.
"""
import sqlalchemy as sa
from alembic import op

revision = "0017_clientes_a_clients"
down_revision = "0016_config_facturacion"
branch_labels = None
depends_on = None


#: `columna_vieja -> columna_del_motor`. Las que ya coinciden (`id`, `email`,
#: `empresa`, `ciudad`, `observaciones`, `tipo_facturacion`, `activo`) no estan.
_RENOMBRES = (
    ("nombre", "name"),
    ("telefono", "phone"),
    ("cuit", "cuit_dni"),
    ("domicilio", "address"),
    ("condicion_iva", "iva_condition"),
    ("fecha_creacion", "created_at"),
)

#: Las que el motor tiene y este producto nunca tuvo. Entran con el mismo
#: default que `init_core_schema()` les da, para que una fila creada aca y una
#: creada en Contalibra sean indistinguibles.
_COLUMNAS_DEL_MOTOR = (
    ("auto_facturar", sa.Integer(), False, "0"),
    ("cc_resumen_auto", sa.Integer(), False, "0"),
    ("cc_resumen_frecuencia", sa.Text(), False, "mensual"),
    ("cc_resumen_ultimo_envio", sa.Text(), True, ""),
    ("external_ref", sa.Text(), True, None),
)


def upgrade():
    op.rename_table("clientes", "clients")

    for viejo, nuevo in _RENOMBRES:
        op.alter_column("clients", viejo, new_column_name=nuevo)

    for nombre, tipo, nullable, default in _COLUMNAS_DEL_MOTOR:
        op.add_column(
            "clients",
            sa.Column(nombre, tipo, nullable=nullable, server_default=default),
        )

    op.alter_column(
        "clients", "activo",
        existing_type=sa.Boolean(), type_=sa.Integer(),
        existing_nullable=False, server_default="1",
        postgresql_using="activo::integer",
    )
    op.alter_column(
        "clients", "created_at",
        existing_type=sa.DateTime(), type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="to_char(created_at, 'YYYY-MM-DD HH24:MI:SS')",
    )
    # 🔴 El default NO se convierte con el tipo: quedaba `CURRENT_TIMESTAMP`
    # —un timestamp— sobre una columna ya TEXT, o sea que una fila nueva se
    # guardaba como `2026-08-12 13:46:35.089981+00` mientras las migradas
    # quedaban en `2026-08-12 13:46:35`. Dos formatos en la misma columna, y
    # ninguno de los dos el del motor.
    #
    # Se pone el mismo literal que genera el adaptador PostgreSQL de LibraCore
    # para `TEXT DEFAULT (datetime('now'))`, verificado contra la tabla
    # `clients` de `contalibra-dev` ya migrada.
    op.execute(
        "ALTER TABLE clients ALTER COLUMN created_at SET DEFAULT "
        "to_char((CURRENT_TIMESTAMP AT TIME ZONE 'UTC'), 'YYYY-MM-DD HH24:MI:SS')"
    )
    # Cosmetico pero evita que un `pg_dump` de este producto se lea distinto al
    # de Contalibra por el nombre de la secuencia. PostgreSQL reapunta el
    # default solo.
    op.execute("ALTER SEQUENCE IF EXISTS clientes_id_seq RENAME TO clients_id_seq")


def downgrade():
    """Vuelve a `clientes`. **Las cinco columnas del motor se pierden**, que es
    lo correcto: son datos que la tabla vieja no puede representar.

    `created_at` vuelve a TIMESTAMP con un `USING` tolerante: una fila cuyo
    texto no parsee queda en NULL en vez de abortar el downgrade entero. Un
    rollback que muere a la mitad deja la base peor que uno que pierde un valor
    que el tipo viejo no podia guardar igual.
    """
    op.execute("ALTER SEQUENCE IF EXISTS clients_id_seq RENAME TO clientes_id_seq")
    # 🔴 Soltar el default ANTES de cambiar el tipo. El `upgrade` deja un
    # default de texto (`to_char(...)`) y PostgreSQL no lo puede castear solo a
    # TIMESTAMP: aborta con "default for column created_at cannot be cast
    # automatically". El `USING` convierte las FILAS, no el default — son dos
    # cosas distintas y esta migración ya se comió la confusión una vez, en el
    # `upgrade`, donde el default viejo quedó pegado sin convertir.
    op.execute("ALTER TABLE clients ALTER COLUMN created_at DROP DEFAULT")
    op.alter_column(
        "clients", "created_at",
        existing_type=sa.Text(), type_=sa.DateTime(),
        existing_nullable=True,
        postgresql_using=(
            "case when created_at ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} "
            "[0-9]{2}:[0-9]{2}:[0-9]{2}$' then created_at::timestamp end"
        ),
    )
    op.execute("ALTER TABLE clients ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP")
    op.alter_column(
        "clients", "activo",
        existing_type=sa.Integer(), type_=sa.Boolean(),
        existing_nullable=False, server_default=sa.text("true"),
        postgresql_using="activo::boolean",
    )

    for nombre, *_ in reversed(_COLUMNAS_DEL_MOTOR):
        op.drop_column("clients", nombre)

    for viejo, nuevo in reversed(_RENOMBRES):
        op.alter_column("clients", nuevo, new_column_name=viejo)

    op.rename_table("clients", "clientes")
