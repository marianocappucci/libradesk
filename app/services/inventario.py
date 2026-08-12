"""Stock de consumibles, sobre LibraCommerce.

Hasta el 2026-08-12 este producto **no tenia stock de ninguna clase**: ninguna
de sus 23 tablas modelaba productos, materiales ni cantidades, y sus
`depositos` guardan **unidades serializadas** (donde esta un equipo cuando no
esta instalado), no existencias.

La decision del humano (2026-08-11) fue no construir un inventario propio sino
**adoptar el motor** que ya usan Contalibra, Restolibra y VentaLibra. Este
modulo es el enganche, y sigue el mismo patron que
`app/services/remitos_presupuestos.py` para LibraCore: **una sola base, varias
familias de tablas**, compartiendo la conexion que arma
`libracore.db.core`.

Por eso `configure()` de este modulo **no** llama a `libracore_core.configure()`
otra vez: lo hizo `remitos_presupuestos.configure()` en el arranque, y llamarlo
de nuevo seria fijar dos veces la misma ruta. Acá solo se crea el schema.

## Dos cosas que hay que saber antes de tocar esto

**1. `init_schema()` del motor es monolitico**: crea sus ~19 tablas de una. Este
producto usa cinco --`catalog_items`, `units`, `categories`, `locations`,
`stock_movements`-- y las otras catorce quedan vacias. Es barato en disco y es
lo que ya viven los otros tres consumidores; modularizarlo seria un cambio del
motor que toca a los cuatro.

**2. 🔴 `actividad_log` YA EXISTE en este producto** (la crea `libraauth` para
la auditoria por flush) **y el motor tambien la declara**. Como el DDL del motor
es `CREATE TABLE IF NOT EXISTS`, la de LibraDesk **se conserva** y la del motor
no se crea: no se pisan datos. Pero las dos difieren en `entidad_id` --`varchar`
aca, `INTEGER` en el motor--, asi que **no hay que activar la auditoria de
LibraCommerce en este producto**: escribiria un entero en una columna de texto.
La auditoria de LibraDesk es la de `libraauth` y no cambia.
"""

from datetime import datetime
from decimal import Decimal

from libracommerce.db.repository import SqliteCommerceRepository
from libracommerce.db.schema import init_schema
from libracommerce.domain.catalog import CatalogItem, CatalogItemType, Unit
from libracommerce.domain.inventory import Location, StockMovement, StockMovementType
from libracommerce.usecases.inventory import (
    StockInsuficienteError,
    transfer_stock,
    verificar_disponibilidad,
)
from libracore.db import core as libracore_core

#: Se re-exporta para que los routers atrapen el error sin importar del motor.
__all__ = [
    "StockInsuficienteError",
    "ensure_schema",
    "listar_depositos",
    "crear_deposito",
    "listar_items",
    "crear_item",
    "stock_actual",
    "movimientos",
    "ajustar",
    "transferir",
]

#: La unidad por defecto de un consumible. El motor exige una y este producto
#: no tiene pantalla de unidades todavia.
_UNIDAD = Unit("u", "Unidad")


def ensure_schema() -> None:
    """Crea las tablas de LibraCommerce si no existen.

    Llamar DESPUES de `remitos_presupuestos.configure()`, que es quien apunta
    `libracore.db.core` a la base de esta instancia. Sin eso, `get_connection()`
    levanta `RuntimeError` por no estar configurado.
    """
    with libracore_core.get_connection() as conn:
        init_schema(conn)


def _repo(conn) -> SqliteCommerceRepository:
    return SqliteCommerceRepository(conn)


# ── Depositos ────────────────────────────────────────────────────────────


def listar_depositos() -> list[dict]:
    """Los depositos de consumibles.

    ⚠️ **No son los `depositos` de LibraDesk.** Aquella tabla guarda donde esta
    un equipo serializado; esta guarda existencias por cantidad. Conviven a
    proposito y se llaman distinto en la base (`depositos` contra `locations`).
    """
    with libracore_core.get_connection() as conn:
        return [
            {"id": loc.id, "nombre": loc.name, "activo": loc.active,
             "descripcion": loc.description, "es_default": loc.is_default}
            for loc in _repo(conn).list_locations()
        ]


def crear_deposito(nombre: str, descripcion: str = "", es_default: bool = False) -> dict:
    if not (nombre or "").strip():
        raise ValueError("El deposito necesita un nombre.")
    with libracore_core.get_connection() as conn:
        loc = _repo(conn).save_location(
            Location(None, nombre.strip(), description=descripcion, is_default=es_default)
        )
        return {"id": loc.id, "nombre": loc.name}


# ── Catalogo de consumibles ──────────────────────────────────────────────


def listar_items(solo_activos: bool = True) -> list[dict]:
    with libracore_core.get_connection() as conn:
        return [
            {"id": it.id, "nombre": it.name, "activo": it.active,
             "stock_minimo": float(it.min_stock), "costo": float(it.default_cost)}
            for it in _repo(conn).list_catalog_items(
                active_only=solo_activos, item_type=CatalogItemType.PRODUCT
            )
        ]


def crear_item(nombre: str, costo: float = 0.0, stock_minimo: float = 0.0) -> dict:
    if not (nombre or "").strip():
        raise ValueError("El consumible necesita un nombre.")
    with libracore_core.get_connection() as conn:
        item = _repo(conn).save_catalog_item(
            CatalogItem(
                None, CatalogItemType.PRODUCT, nombre.strip(), _UNIDAD,
                default_cost=Decimal(str(costo)), min_stock=Decimal(str(stock_minimo)),
            )
        )
        return {"id": item.id, "nombre": item.name}


# ── Existencias ──────────────────────────────────────────────────────────


def stock_actual(item_id: int, deposito_id: int) -> float:
    with libracore_core.get_connection() as conn:
        return float(_repo(conn).current_stock(item_id, deposito_id))


def movimientos(item_id: int, deposito_id: int) -> list[dict]:
    with libracore_core.get_connection() as conn:
        return [
            {"id": m.id, "tipo": m.movement_type, "cantidad": float(m.quantity_delta),
             "fecha": m.occurred_at.isoformat(), "nota": m.note,
             "motivo": m.reason_code}
            for m in _repo(conn).list_stock_movements(item_id, deposito_id)
        ]


def ajustar(item_id: int, deposito_id: int, cantidad: float, *,
            nota: str = "", usuario_id: int | None = None,
            fecha: datetime | None = None) -> None:
    """Entrada o salida manual. `cantidad` positiva entra, negativa sale.

    Una salida manual **si** valida disponibilidad: a diferencia de un
    mostrador --donde el cliente ya tiene el producto en la mano y negarse a
    cobrar es peor que quedar en negativo-- acá el ajuste lo hace alguien
    mirando el deposito, y un negativo es un error de carga, no un hecho.
    """
    if not cantidad:
        raise ValueError("La cantidad del ajuste no puede ser cero.")
    cuando = fecha or datetime.now()
    with libracore_core.get_connection() as conn:
        repo = _repo(conn)
        with repo.transaction():
            if cantidad < 0:
                verificar_disponibilidad(repo, item_id, deposito_id, Decimal(str(-cantidad)))
            repo.append_stock_movement(
                StockMovement(
                    None, item_id, deposito_id, StockMovementType.ADJUSTMENT,
                    Decimal(str(cantidad)), cuando, note=nota, created_by=usuario_id,
                    reason_code="entrada" if cantidad > 0 else "salida",
                )
            )


def transferir(item_id: int, origen_id: int, destino_id: int, cantidad: float, *,
               nota: str = "", usuario_id: int | None = None,
               fecha: datetime | None = None) -> None:
    """Mueve consumibles entre depositos, en una sola transaccion.

    Es el caso de uso central del producto que motivo todo esto: el deposito
    central que abastece la camioneta de un tecnico. Delega en el motor --que
    hace las dos escrituras y la lectura que las autoriza en la misma
    transaccion-- en vez de escribir los dos movimientos a mano, que es como
    Contalibra lo tenia y perdia mercaderia si el segundo fallaba.
    """
    try:
        with libracore_core.get_connection() as conn:
            transfer_stock(
                _repo(conn),
                item_id=item_id,
                from_location_id=origen_id,
                to_location_id=destino_id,
                quantity=Decimal(str(cantidad)),
                occurred_at=fecha or datetime.now(),
                note=nota,
                created_by=usuario_id,
                reason_code_salida="transferencia_salida",
                reason_code_entrada="transferencia_entrada",
            )
    except StockInsuficienteError as e:
        raise ValueError(
            f"Stock insuficiente en el deposito de origen (disponible: {float(e.disponible)})."
        ) from e
