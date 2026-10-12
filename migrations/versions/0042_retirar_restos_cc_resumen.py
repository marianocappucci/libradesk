"""Se retiran los restos de datos del resumen de cuenta corriente por mail.

El envío periódico del resumen (`libracore/cc_resumen.py`) se borró del motor en la v1.154.0
por ser código muerto, y los datos que dejaba se retiran con la `0024` de LibraCore (ADR-042 del
motor). Este producto los tenía por dos caminos propios, y la cadena del motor no alcanza a
ninguno de los dos:

- las **tres columnas de `clients`** (`cc_resumen_auto`, `cc_resumen_frecuencia`,
  `cc_resumen_ultimo_envio`) las trajo la `0017` y el modelo `Cliente` las declaraba;
- la **tabla `cc_resumenes_enviados`** la creaba `app/services/comercial.py` en cada arranque
  (`CREATE TABLE IF NOT EXISTS`, fuera de esta cadena).

Ninguna de las dos la lee ni la escribe el producto. Sale todo junto: el modelo, el DDL copiado y
esta revisión, que las saca de las bases que las tienen. Decisión del dueño del 2026-10-12: «los
borramos con una migración». **Se pierde el historial de envíos**; como nada lo
escribía, lo esperable es que la tabla esté vacía en toda instancia (no se verificó fila por fila).

## Por qué conviven con la `0024` del motor sin pisarse

LibraDesk corre las dos cadenas (ADR-012): `alembic` (esta), `libracommerce-migrar`,
`libraauth-migrar` y, al final, `libracore-migrar`. Cada una lleva su propia tabla de versión, y
las dos sentencias son `IF EXISTS`: quien llega segundo no encuentra nada y no hace nada. Esta
revisión no depende de que el motor ya esté en su `0024`, ni al revés.

⚠️ Con el pin de `libracore` **anterior** a la v1.155.0, la `0001` del motor (que corre sólo
sobre una base nueva) sigue llamando a su `init_core_schema()` viejo y vuelve a crear las
columnas y la tabla. No rompe nada —el modelo ya no las mira y tienen default—, y desaparecen con
la `0024` al subir el pin.

**No depende del pin de `libracore`.** Lo único del motor que escribe esas columnas es
`libracore.db.clients.update_client` (y los `toggle_`/`registrar_` del resumen), y este producto
no lo llama: las escrituras de clientes van por SQLAlchemy (ver `app/services/clientes.py`) y del
módulo sólo importa `validar_cuit_no_duplicado`. La suite pasa con la v1.154.0 y con el árbol de la v1.155.0.

## Downgrade

Devuelve las **tres columnas, vacías** y con el mismo tipo y default que les puso la `0017`:
hace falta para que el `downgrade` de la `0017` las encuentre y pueda sacarlas. Los datos no
vuelven (para eso, el backup). La tabla no se recrea: nunca fue de esta cadena y la vuelve a
crear el `ensure_schema()` de un código anterior a esta revisión.
"""
from alembic import op

revision = "0042_retirar_cc_resumen"
down_revision = "0041_intento_de_envio"
branch_labels = None
depends_on = None

_COLUMNAS = ("cc_resumen_auto", "cc_resumen_frecuencia", "cc_resumen_ultimo_envio")


def upgrade() -> None:
    # La tabla primero: nada la referencia (la FK a `clients` nunca se declaró acá, ver
    # `comercial.py`), y así el orden no importa aunque alguien la haya recreado a mano.
    op.execute("DROP TABLE IF EXISTS cc_resumenes_enviados")
    # El CHECK sólo existe si la base pasó antes por el `init_core_schema()` del motor; se
    # nombra aparte por si `DROP COLUMN` no se lo lleva en una instancia armada a mano.
    op.execute("ALTER TABLE clients DROP CONSTRAINT IF EXISTS clients_cc_resumen_frecuencia_check")
    for columna in _COLUMNAS:
        op.execute(f"ALTER TABLE clients DROP COLUMN IF EXISTS {columna}")


def downgrade() -> None:
    # Lo que dejó la `0017`: sin CHECK, y la última nullable con default vacío.
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS cc_resumen_auto INTEGER NOT NULL DEFAULT 0")
    op.execute(
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS cc_resumen_frecuencia TEXT NOT NULL DEFAULT 'mensual'"
    )
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS cc_resumen_ultimo_envio TEXT DEFAULT ''")
