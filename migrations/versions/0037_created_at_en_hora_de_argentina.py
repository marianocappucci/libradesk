"""Los `created_at` del DDL de LibraDesk dejan de estampar UTC.

La mitad de LibraDesk del arreglo que [[libracore]] hizo en su revisión `0003`
(ver el docstring de aquélla para el diagnóstico completo). El DEFAULT de estas
14 columnas era `datetime('now')`, que en SQLite es UTC y que el adaptador de
PostgreSQL traduce a UTC **a propósito**, para que las dos bases guarden el
mismo texto — o sea que las dos guardaban la hora equivocada, y de la misma
manera.

🔑 **Acá van las 14 y no sólo `sucursales`, aunque trece sean tablas del core.**
Las revisiones de LibraCore **no corren sobre estas bases**: las seis instancias
del VPS tienen `alembic_version_libradesk` y ninguna tiene `alembic_version`
(medido el 2026-08-29). LibraDesk lleva su propio DDL de esas doce tablas en
`app/services/comercial.py` y su propia cadena de migraciones, así que el
arreglo tiene que llegar por esta cadena o no llega.

🔴 **Las 27 columnas `timestamp` de los modelos de SQLAlchemy no entran, y no es
un olvido.** `activos`, `contratos`, `proveedores`, `usuarios` y compañía tienen
`created_at` como `timestamp` con `CURRENT_TIMESTAMP`, que sale de la zona de la
**sesión** del servidor — y los 21 PostgreSQL del VPS están en hora de Argentina
desde el 2026-08-24, verificado con `show timezone` en los 21. O sea que ya
estampan bien. Y el DEFAULT nuevo es texto: ponérselo a una de ellas cortaría
con *"default expression is of type text"* y abortaría el `upgrade` entero. Por
eso el helper del motor las saltea por tipo, no por lista.

⚠️ **No toca las filas ya escritas.** Quedan 3 h adelantadas y hay una
discontinuidad a partir de acá, igual que la que dejó el barrido de huso del
2026-08-23. Decisión del humano el 2026-08-29.
"""
from alembic import op

revision = "0037_created_at_hora_ar"
down_revision = "0036_contratos_de_proveedor"
branch_labels = None
depends_on = None


#: Las 14 columnas de TEXTO con reloj de estas bases, como estaban al
#: escribir esta revisión. Una tabla que nazca después ya viene con el DEFAULT
#: nuevo, y la suite lo vigila (`test_defaults_en_hora_de_argentina.py`).
_COLUMNAS = (
    # 🔴 `clients` la trajo la revision `0017` al adoptar la tabla del motor, y
    # es de TEXTO. No estaba en esta lista --que salio de barrer el DDL de
    # `app/services/`-- y como las revisiones de LibraCore no corren sobre estas
    # bases, se habria quedado en UTC sin que nada lo dijera. Lo encontro el
    # ensayo del 2026-08-29 sobre una copia de la forma de `libradesk-compulibra`:
    # despues de migrar quedaban dos columnas de texto en UTC, y esta era una.
    ("clients", "created_at"),
    ("facturas", "created_at"),
    ("cajas", "created_at"),
    ("caja_movimientos", "created_at"),
    ("egresos", "created_at"),
    ("egresos_pagos", "created_at"),
    ("ventas_pagos", "created_at"),
    ("cc_pagos", "created_at"),
    ("cc_debitos", "created_at"),
    ("cc_resumenes_enviados", "created_at"),
    ("recibos", "created_at"),
    ("sucursales", "created_at"),
    ("remitos", "created_at"),
    ("presupuestos", "created_at"),
)

#: El DEFAULT que tenían antes, para el `downgrade()`.
_UTC = "datetime('now')"


def _aplicar(expresion: str) -> None:
    """El trabajo fino —la traducción exacta a PostgreSQL y saltear las columnas
    que no son TEXT— lo hace `libracore.db.schema.alters_para_hora_ar()`, la
    misma función que usan la revisión del motor y las de los otros productos.
    """
    from libracore.db.schema import alters_para_hora_ar

    for sentencia in alters_para_hora_ar(op.get_bind(), _COLUMNAS, expresion):
        op.execute(sentencia)


def upgrade() -> None:
    from libracore.db.schema import AHORA_AR

    _aplicar(AHORA_AR)


def downgrade() -> None:
    _aplicar(_UTC)
