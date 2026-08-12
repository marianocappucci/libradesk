"""Materiales consumidos en una incidencia — el enganche con el stock.

Es la bisagra entre los dos circuitos de una mesa de ayuda que ademas mueve
mercaderia: el ticket dice **que se hizo** y el stock dice **con que**. Sin
esto, el tecnico saca 10 plugs de la camioneta y el sistema sigue creyendo que
estan ahi.

## Por que esta tabla NO es un modelo de SQLAlchemy

El dominio de este producto es SQLAlchemy contra `engine`; el stock lo escribe
LibraCommerce por la conexion cruda de `libracore.db.core`. **Son dos
conexiones distintas contra la misma base**, asi que una fila escrita por
SQLAlchemy y un movimiento escrito por el motor no pueden estar en la misma
transaccion: si la segunda falla, queda un material anotado que nunca salio del
deposito, o al reves.

Como el requisito de esta funcion es justamente que las dos cosas pasen o no
pase ninguna, la tabla se crea con DDL crudo y se escribe **por la misma
conexion que el movimiento**, adentro de `repo.transaction()`. Es el mismo
patron que ya usan `remitos` y `presupuestos` en este producto.

No entra a Alembic a proposito, y no se le puede colar: `app/schema.py`
`include_name()` filtra por `metadata.tables`, asi que una tabla que no es un
modelo queda fuera del autogenerate sola.

## Cuando se mueve el stock

**Al cargar el material, no al cerrar el ticket** (decidido el 2026-08-12).
Dos motivos:

1. Una incidencia de LibraDesk **se puede reabrir** (`incidencias.py`, el
   estado vuelve y se limpia `fecha_cierre`). Si el stock se moviera al cerrar,
   reabrir obligaria a revertir y volver a aplicar: una maquina de estados con
   efectos sobre un ledger que es append-only.
2. Mientras el ticket esta abierto, el deposito diria una mentira. Si el
   material salio de la camioneta, salio.

Sacar un material **no borra la fila ni el movimiento**: appendea la reversion
y marca la fila, igual que `cancel_sale` del motor. El historial de que se
saco y se devolvio es parte de lo que hay que poder auditar.
"""

from datetime import datetime
from decimal import Decimal

from libracommerce.db.repository import SqliteCommerceRepository
from libracommerce.domain.inventory import StockMovement, StockMovementType
from libracommerce.usecases.inventory import verificar_disponibilidad
from libracore.db import core as libracore_core

#: El `source_type` con el que el movimiento apunta a la incidencia. Con esto,
#: `list_stock_movements_by_source("incidencia", id)` devuelve todo lo que
#: consumio un ticket, sin joins contra tablas de otro dueno.
ORIGEN = "incidencia"

DDL = """
CREATE TABLE IF NOT EXISTS incidencias_materiales (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    incidencia_id   INTEGER NOT NULL,
    item_id         INTEGER NOT NULL,
    location_id     INTEGER NOT NULL,
    cantidad        NUMERIC NOT NULL CHECK (cantidad > 0),
    descripcion     TEXT NOT NULL DEFAULT '',
    movimiento_id   INTEGER,
    reversa_id      INTEGER,
    created_at      TEXT NOT NULL,
    created_by      INTEGER
);

CREATE INDEX IF NOT EXISTS idx_incidencias_materiales_incidencia
    ON incidencias_materiales(incidencia_id);
"""


def ensure_schema() -> None:
    """Crea la tabla. Llamar DESPUES de `inventario.ensure_schema()`."""
    with libracore_core.get_connection() as conn:
        conn.executescript(DDL)


def _descripcion(repo: SqliteCommerceRepository, item_id: int) -> str:
    """El nombre del consumible **al momento de usarlo**.

    Se copia y no se referencia por el mismo motivo que
    `description_snapshot` en el motor: renombrar un producto en el catalogo
    no puede reescribir lo que dice un ticket ya cerrado.
    """
    item = repo.get_catalog_item(item_id)
    return item.name if item is not None else ""


def cargar(incidencia_id: int, item_id: int, location_id: int, cantidad: float, *,
           usuario_id: int | None = None, cuando: datetime | None = None) -> dict:
    """Registra material consumido y **lo descuenta del deposito**.

    Las dos escrituras y la lectura que las autoriza van en la misma
    transaccion: si no hay stock, no queda ni la fila ni el movimiento.
    """
    if cantidad <= 0:
        raise ValueError("La cantidad de material tiene que ser positiva.")
    momento = cuando or datetime.now()
    cant = Decimal(str(cantidad))

    with libracore_core.get_connection() as conn:
        repo = SqliteCommerceRepository(conn)
        with repo.transaction():
            verificar_disponibilidad(repo, item_id, location_id, cant)
            # `ADJUSTMENT` y no `SALE`: no hay ninguna fila en `sales` detras
            # de esto, y un `movement_type = sale` mandaria a cualquier lector
            # a buscar una venta que no existe. Este producto no vende. El que
            # dice la verdad es `reason_code`, igual que hace Contalibra con
            # su vocabulario propio de entrada/salida/ajuste.
            movimiento = repo.append_stock_movement(
                StockMovement(
                    None, item_id, location_id, StockMovementType.ADJUSTMENT,
                    -cant, momento,
                    source_type=ORIGEN, source_id=incidencia_id,
                    created_by=usuario_id, reason_code="consumo_incidencia",
                )
            )
            cur = conn.execute(
                """INSERT INTO incidencias_materiales
                   (incidencia_id, item_id, location_id, cantidad, descripcion,
                    movimiento_id, created_at, created_by)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (incidencia_id, item_id, location_id, str(cant),
                 _descripcion(repo, item_id), movimiento.id,
                 momento.isoformat(), usuario_id),
            )
            fila_id = cur.lastrowid
    return {"id": fila_id, "movimiento_id": movimiento.id}


def quitar(material_id: int, *, usuario_id: int | None = None,
           cuando: datetime | None = None) -> None:
    """Devuelve al deposito un material cargado por error.

    **No borra nada**: appendea la reversion y marca la fila con su id. Un
    ledger del que se puede borrar no sirve para auditar, y lo que hay que
    poder contestar es "quien cargo esto y quien lo saco", no solo cuanto hay.
    """
    momento = cuando or datetime.now()
    with libracore_core.get_connection() as conn:
        repo = SqliteCommerceRepository(conn)
        fila = conn.execute(
            """SELECT item_id, location_id, cantidad, reversa_id
               FROM incidencias_materiales WHERE id = ?""",
            (material_id,),
        ).fetchone()
        if fila is None:
            raise ValueError(f"No existe el material {material_id}.")
        if fila[3] is not None:
            # Idempotente: un doble click no puede devolver el stock dos veces
            # e inventar mercaderia. Mismo criterio que `cancel_sale`.
            return

        with repo.transaction():
            reversa = repo.append_stock_movement(
                StockMovement(
                    None, fila[0], fila[1], StockMovementType.RETURN,
                    Decimal(str(fila[2])), momento,
                    source_type=ORIGEN, source_id=material_id,
                    created_by=usuario_id, reason_code="devolucion_incidencia",
                )
            )
            conn.execute(
                "UPDATE incidencias_materiales SET reversa_id = ? WHERE id = ?",
                (reversa.id, material_id),
            )


def listar(incidencia_id: int, incluir_devueltos: bool = False) -> list[dict]:
    """Los materiales de un ticket. Por defecto, solo los que siguen puestos."""
    sql = """SELECT id, item_id, location_id, cantidad, descripcion,
                    movimiento_id, reversa_id, created_at, created_by
             FROM incidencias_materiales WHERE incidencia_id = ?"""
    if not incluir_devueltos:
        sql += " AND reversa_id IS NULL"
    sql += " ORDER BY id"
    with libracore_core.get_connection() as conn:
        filas = conn.execute(sql, (incidencia_id,)).fetchall()
    return [
        {"id": f[0], "item_id": f[1], "deposito_id": f[2],
         "cantidad": float(f[3]), "descripcion": f[4],
         "movimiento_id": f[5], "devuelto": f[6] is not None,
         "fecha": f[7], "usuario_id": f[8]}
        for f in filas
    ]
