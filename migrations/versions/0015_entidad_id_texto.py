"""actividad_log.entidad_id pasa de INTEGER a texto.

🔴 **En ESTE producto la urgencia es al reves que en los otros, y es mayor.**

La columna se llena con el id de la entidad auditada. En MedLibra, Gestiolibra
y LibraGenda esos ids son cadenas, y ahi el tipo `Integer` rompia el alta contra
PostgreSQL. **Aca no**: los ids de LibraDesk son enteros, y por eso el piloto de
PostgreSQL paso limpio -- nunca ejercito la combinacion que falla. Medido el
2026-08-09, las filas de este producto son `integer` en el 100% de los casos.

Lo que hace urgente esta migracion es que **LibraDesk ya corre PostgreSQL en
produccion, en las tres instancias**. El modelo de `libraauth.auditoria` pasa a
declarar la columna como texto; en cuanto este producto bumpee ese motor,
SQLAlchemy va a mandar cadenas a una columna que en la base **sigue siendo
INTEGER de verdad** -- y PostgreSQL las rechaza. Como el log se escribe en la
MISMA transaccion que la operacion auditada, no se pierde una fila de auditoria:
**el alta entera devuelve 500**.

> **Orden obligatorio: primero esta migracion, despues el bump de `libraauth`.**
> Al reves, el producto deja de poder escribir. Los otros consumidores estan en
> SQLite y ahi el tipado dinamico los protege del desorden; este no.

**El orden esta MEDIDO contra PostgreSQL real, no razonado** (2026-08-09), que
es lo unico que separa esto de una corazonada:

| Estado | Escritura |
|---|---|
| columna VARCHAR + modelo `String` (despues del bump) | OK |
| columna INTEGER + modelo `String` (bumpear SIN migrar) | 🔴 `DatatypeMismatch: column is of type integer but expression is of type character varying` |
| columna VARCHAR + modelo `Integer` (migrar SIN bumpear) | OK -- PostgreSQL castea el entero solo |

O sea que el estado intermedio de esta migracion **es seguro**, y el que hay que
evitar es el otro. En SQLite ese intermedio si cambia algo, aunque inocuo: la
columna pasa a afinidad TEXT, con lo que un id entero vuelve como `'1'` en vez
de `1`. Dos tests de este repo lo asertaban como entero y pasan a pedir texto.


El modelo esta en `libraauth.auditoria` (compartido por los seis productos);
aca va solo la migracion de la tabla de este.

**Los datos no se pierden ni cambian de significado.** Los valores que ya eran
texto quedan igual; los enteros pasan a su representacion decimal (`36` ->
`"36"`), que es como se muestran en la pantalla de logs de todos modos: la
columna se usa en un solo lugar, serializada, sin filtros ni joins ni orden.

**Los dos motores no se tocan igual**, y por eso va con `batch_alter_table`:
PostgreSQL necesita un `USING` para castear, y SQLite **no soporta**
`ALTER COLUMN ... TYPE` -- ahi Alembic reconstruye la tabla y copia las filas.

> La reconstruccion de SQLite es segura en este caso concreto porque
> `actividad_log` **no es tabla padre de ninguna otra**: ninguna declara una FK
> hacia ella. Vale la aclaracion porque en esta familia ya hubo un incidente por
> lo contrario -- reconstruir una tabla referenciada deja a las hijas apuntando
> a un nombre `_old` que despues se borra.
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_entidad_id_texto"
down_revision = "0014_envios_facturacion"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("actividad_log") as batch:
        batch.alter_column(
            "entidad_id",
            existing_type=sa.Integer(),
            type_=sa.String(100),
            existing_nullable=True,
            postgresql_using="entidad_id::varchar",
        )


def downgrade():
    """Vuelve a INTEGER, y **puede perder datos**: cualquier `entidad_id` que no
    sea un numero no entra. Es inherente al tipo viejo, no un descuido de esta
    migracion -- es exactamente el motivo por el que se cambio.

    El `USING` deja en NULL lo que no sea numerico, en vez de hacer fallar el
    downgrade entero: un rollback que aborta a la mitad es peor que uno que
    pierde un dato que el tipo viejo no podia representar igual.

    > La primera version de esto usaba `nullif(entidad_id, '')::integer`, que
    > solo cubre la cadena vacia, y el downgrade moria con
    > `invalid input syntax for type integer: "patient-1"` -- o sea que el
    > comentario prometia algo que el codigo no hacia. Lo encontro probar el
    > downgrade de verdad contra PostgreSQL con datos mezclados, no leerlo.
    """
    with op.batch_alter_table("actividad_log") as batch:
        batch.alter_column(
            "entidad_id",
            existing_type=sa.String(100),
            type_=sa.Integer(),
            existing_nullable=True,
            postgresql_using=(
                "case when entidad_id ~ '^-?[0-9]+$' "
                "then entidad_id::integer end"
            ),
        )
