"""Listas de precios, sobre `price_lists`/`item_prices` de LibraCommerce.

Cero dominio propio. Es el mismo motor y casi el mismo adaptador que
`app/db_listas_precio.py` de Contalibra (migracion P7b), y se escribio mirando
ese archivo a proposito: dos productos con listas de precios distintas seria
duplicar el mismo calculo por tercera vez en la familia.

## El modelo del motor es mas rico que esta pantalla, y esta bien

`item_prices` soporta **vigencia** (`valid_from`/`valid_until`), **quiebre por
cantidad** (`min_quantity`) y **sucursal** (`branch_id`). LibraDesk usa hoy el
modelo "flat" --un precio por producto por lista-- igual que Contalibra, asi
que toda fila que este modulo escribe lleva `min_quantity IS NULL` y
`branch_id IS NULL`, y `valid_from` va a un sentinel documentado.

**No se inventa una fecha de vigencia real** porque no hay ese dato: poner
`datetime.now()` haria que dos precios cargados el mismo dia se ordenaran por
el reloj, y `resolve_price()` devolveria uno u otro segun el segundo en que se
guardaron. El sentinel los hace comparables.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from libracommerce.db.repository import SqliteCommerceRepository
from libracommerce.domain.catalog import ItemPrice, PriceList
from libracore.db import core as libracore_core

#: Mismo sentinel que Contalibra. Cualquier fecha fija sirve mientras sea LA
#: MISMA para todas las filas; el epoch es la que no se confunde con un dato.
_SIN_VIGENCIA = datetime(1970, 1, 1)


def _repo(conn) -> SqliteCommerceRepository:
    return SqliteCommerceRepository(conn)


def listar() -> list[dict]:
    with libracore_core.get_connection() as conn:
        filas = conn.execute(
            """
            SELECT pl.id, pl.name, pl.description, pl.active, pl.is_default,
                   (SELECT COUNT(*) FROM item_prices ip
                     WHERE ip.price_list_id = pl.id) AS items
            FROM price_lists pl
            ORDER BY pl.is_default DESC, pl.name
            """
        ).fetchall()
    return [
        {"id": r["id"], "nombre": r["name"], "descripcion": r["description"] or "",
         "activa": bool(r["active"]), "es_default": bool(r["is_default"]),
         "items": r["items"]}
        for r in filas
    ]


def crear(nombre: str, descripcion: str = "", es_default: bool = False) -> dict:
    if not (nombre or "").strip():
        raise ValueError("La lista necesita un nombre.")
    with libracore_core.get_connection() as conn:
        lista = _repo(conn).save_price_list(
            PriceList(None, nombre.strip(), description=descripcion,
                      is_default=es_default)
        )
        return {"id": lista.id, "nombre": lista.name}


def editar(lista_id: int, nombre: str, descripcion: str = "",
           activa: bool = True) -> None:
    with libracore_core.get_connection() as conn:
        repo = _repo(conn)
        actual = repo.get_price_list(lista_id)
        if actual is None:
            raise ValueError("La lista no existe.")
        repo.save_price_list(
            PriceList(lista_id, nombre.strip(), description=descripcion,
                      active=activa, is_default=actual.is_default)
        )


def eliminar(lista_id: int) -> None:
    """Borra la lista y sus precios.

    ⚠️ Los precios se borran **antes** que la lista y en la misma conexion: al
    reves quedarian `item_prices` apuntando a una lista inexistente, que es
    justo lo que `resolve_price()` recorre.
    """
    with libracore_core.get_connection() as conn:
        conn.execute("DELETE FROM item_prices WHERE price_list_id=?", (lista_id,))
        conn.execute("DELETE FROM price_lists WHERE id=?", (lista_id,))


def precios_de(lista_id: int) -> list[dict]:
    """Los precios de una lista, con el nombre del producto ya resuelto."""
    with libracore_core.get_connection() as conn:
        filas = conn.execute(
            """
            SELECT ip.id, ip.item_id, ip.amount, ci.name AS producto,
                   ci.default_cost
            FROM item_prices ip
            JOIN catalog_items ci ON ci.id = ip.item_id
            WHERE ip.price_list_id = ?
            ORDER BY ci.name
            """,
            (lista_id,),
        ).fetchall()
    return [
        {"id": r["id"], "item_id": r["item_id"], "producto": r["producto"],
         "precio": float(r["amount"]), "costo": float(r["default_cost"] or 0),
         # El margen se calcula aca y no en la pantalla: si lo hiciera el
         # front, cada vista tendria su propia idea de que es el margen.
         "margen_pct": (
             round((float(r["amount"]) / float(r["default_cost"]) - 1) * 100, 1)
             if r["default_cost"] else None
         )}
        for r in filas
    ]


def fijar_precio(lista_id: int, item_id: int, precio: float) -> None:
    """Alta o actualizacion del precio de un producto en una lista.

    Un solo precio por (lista, producto): se borra el anterior antes de
    escribir. Sin eso, `item_prices` acumularia filas y `resolve_price()`
    empezaria a depender del orden de insercion.
    """
    with libracore_core.get_connection() as conn:
        conn.execute(
            "DELETE FROM item_prices WHERE price_list_id=? AND item_id=?",
            (lista_id, item_id),
        )
        _repo(conn).save_item_price(
            ItemPrice(None, item_id, lista_id, Decimal(str(precio)),
                      valid_from=_SIN_VIGENCIA)
        )


def ajustar_por_porcentaje(lista_id: int, porcentaje: float) -> int:
    """Actualizacion masiva. Devuelve cuantos precios movio.

    Es la operacion que mas se usa en la practica --"subime todo un 12%"-- y la
    razon por la que las listas de precio existen como entidad y no como una
    columna en el producto.
    """
    factor = 1 + (porcentaje / 100)
    if factor <= 0:
        raise ValueError("El ajuste dejaria precios en cero o negativos.")
    with libracore_core.get_connection() as conn:
        cur = conn.execute(
            "UPDATE item_prices SET amount = ROUND(amount * ?, 2) WHERE price_list_id=?",
            (factor, lista_id),
        )
        return max(cur.rowcount or 0, 0)
