"""`proveedores` toma la forma de la tabla del motor.

LibraDesk tenia su propia `proveedores` --a quien se le manda un equipo a
service-- y LibraCore declara **otra tabla con el mismo nombre** para el
circuito de egresos, con columnas distintas: `cuit_dni`, `address` e
`iva_condition` en vez de `contacto` y `observaciones`.

🔴 **El choque no falla, y por eso hay que resolverlo antes y no despues.** El
DDL del motor es `CREATE TABLE IF NOT EXISTS`, asi que al traer el schema de
egresos la tabla de LibraDesk **se conserva y la del motor no se crea**: no hay
error, no hay aviso, y el primer `create_proveedor()` de
`libracore.db.egresos` explota contra columnas que no existen. Es el mismo
mecanismo que ya esta anotado para `actividad_log` en
`app/services/inventario.py`, y el mismo que resolvio la `0017` para clientes.

**Es aditivo**: se agregan las tres columnas del motor y **no se toca ninguna
de las propias**. `contacto` y `observaciones` siguen ahi porque los usa el
circuito de reparaciones, que no cambia. Un proveedor de service existente
queda con CUIT vacio, que es exactamente lo que se sabe de el.

`activo` se conserva y **no se reemplaza por el `delete_proveedor()` del
motor**: la baja de LibraDesk es logica a proposito --un proveedor con
reparaciones historicas no se puede borrar sin romper esa historia-- y el motor
borra de verdad. La pantalla de compras usa la baja logica.
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_proveedores_forma_del_motor"
down_revision = "0017_clientes_a_clients"
branch_labels = None
depends_on = None


def upgrade():
    # `server_default=""` y no NULL: `libracore.db.egresos` hace
    # `COALESCE`-free en varios selects y compara contra cadena vacia. Con NULL
    # el proveedor sin CUIT desaparecia de esos listados en vez de aparecer sin
    # CUIT.
    op.add_column("proveedores", sa.Column("cuit_dni", sa.Text(),
                                           nullable=False, server_default=""))
    op.add_column("proveedores", sa.Column("address", sa.Text(),
                                           nullable=False, server_default=""))
    op.add_column("proveedores", sa.Column("iva_condition", sa.Text(),
                                           nullable=False, server_default=""))


def downgrade():
    op.drop_column("proveedores", "iva_condition")
    op.drop_column("proveedores", "address")
    op.drop_column("proveedores", "cuit_dni")
