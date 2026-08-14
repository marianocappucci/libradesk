"""Listas de precios, sobre `price_lists`/`item_prices` de LibraCommerce.

Cero dominio propio. Es el mismo motor y casi el mismo adaptador que
`app/db_listas_precio.py` de Contalibra (migracion P7b), y se escribio mirando
ese archivo a proposito: dos productos con listas de precios distintas seria
duplicar el mismo calculo por tercera vez en la familia.

## El modelo del motor es mas rico que esta pantalla, y esta bien

`item_prices` soporta **vigencia** (`valid_from`/`valid_until`), **quiebre por
cantidad** (`min_quantity`) y **sucursal** (`branch_id`). LibraDesk usa el
modelo "flat" en las dos primeras --toda fila lleva `min_quantity IS NULL` y
`valid_from` en un sentinel documentado-- igual que Contalibra.

**`branch_id` si se usa, desde el 2026-08-14**: un producto puede tener precio
propio en una sucursal y cotizar por el general en las demas. Es la unica de
las tres dimensiones del motor que este producto activa, y LibraDesk es el
primero de la familia en hacerlo --Contalibra la deja en NULL siempre--.

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

from . import comercial

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


def precios_de(lista_id: int, sucursal_id: int | None = None) -> list[dict]:
    """Los precios de una lista, con el nombre del producto ya resuelto.

    ## Que devuelve con sucursal y que sin ella

    Sin `sucursal_id` devuelve **todas** las filas, incluidas las de sucursal,
    cada una marcada con la suya: es la vista de administracion de la lista.

    Con `sucursal_id` devuelve **una fila por producto: la que efectivamente se
    aplica ahi** --la de la sucursal si existe, la general si no--, con
    `propio_de_sucursal` diciendo cual de las dos es. Esa preferencia no se
    inventa aca: es la misma que `resolve_price()` del motor usa al cotizar
    (`branch_id IS NULL OR branch_id = ?`, ordenando la de sucursal primero).
    Mostrar las dos filas del mismo producto contestaria "que precios hay
    cargados", que no es la pregunta que se le hace a esta pantalla estando
    parado en una sucursal.
    """
    # El filtro se arma en Python y no con un `? IS NULL` en el SQL: PostgreSQL
    # no puede inferir el tipo de un parametro suelto a la izquierda de `IS
    # NULL` y falla con "could not determine data type of parameter". Es el
    # mismo motivo por el que `_precio_where()` existe mas abajo.
    where = "" if sucursal_id is None else "AND (ip.branch_id IS NULL OR ip.branch_id = ?)"
    params: tuple = (lista_id,) if sucursal_id is None else (lista_id, sucursal_id)
    with libracore_core.get_connection() as conn:
        filas = conn.execute(
            f"""
            SELECT ip.id, ip.item_id, ip.amount, ip.branch_id, ci.name AS producto,
                   ci.default_cost, s.nombre AS sucursal
            FROM item_prices ip
            JOIN catalog_items ci ON ci.id = ip.item_id
            LEFT JOIN sucursales s ON s.id = ip.branch_id
            WHERE ip.price_list_id = ?
              {where}
            ORDER BY ci.name
            """,
            params,
        ).fetchall()

    precios = [
        {"id": r["id"], "item_id": r["item_id"], "producto": r["producto"],
         "precio": float(r["amount"]), "costo": float(r["default_cost"] or 0),
         "sucursal_id": r["branch_id"], "sucursal": r["sucursal"] or "",
         "propio_de_sucursal": r["branch_id"] is not None,
         # El margen se calcula aca y no en la pantalla: si lo hiciera el
         # front, cada vista tendria su propia idea de que es el margen.
         "margen_pct": (
             round((float(r["amount"]) / float(r["default_cost"]) - 1) * 100, 1)
             if r["default_cost"] else None
         )}
        for r in filas
    ]
    if sucursal_id is None:
        return precios
    # Una fila por producto, ganando la de sucursal. El dict conserva el orden
    # de insercion --que viene ordenado por nombre-- asi que la salida sigue
    # alfabetica sin volver a ordenar.
    efectivos: dict[int, dict] = {}
    for p in precios:
        anterior = efectivos.get(p["item_id"])
        if anterior is None or p["propio_de_sucursal"]:
            efectivos[p["item_id"]] = p
    return list(efectivos.values())


def _precio_where(sucursal_id: int | None) -> tuple[str, tuple]:
    """El `WHERE` que apunta a UNA fila de precio, distinguiendo NULL de un id.

    🔴 **No se puede escribir `branch_id IS ?`.** En SQLite `IS` compara
    null-safe y seria exactamente lo que hace falta, pero en PostgreSQL --que
    es el motor real de LibraDesk-- `IS` solo acepta NULL/TRUE/FALSE y la
    consulta ni siquiera parsea. Y con `= ?` el precio general nunca matchearia
    su propia fila (`NULL = NULL` es NULL), asi que cada guardado dejaria una
    fila mas y `resolve_price()` empezaria a depender del orden de insercion:
    el bug que el DELETE previo existe para evitar.
    """
    if sucursal_id is None:
        return "branch_id IS NULL", ()
    return "branch_id = ?", (sucursal_id,)


def _borrar_fila(conn, lista_id: int, item_id: int,
                 sucursal_id: int | None) -> None:
    cond, extra = _precio_where(sucursal_id)
    conn.execute(
        f"DELETE FROM item_prices WHERE price_list_id=? AND item_id=? AND {cond}",
        (lista_id, item_id) + extra,
    )


def fijar_precio(lista_id: int, item_id: int, precio: float,
                 sucursal_id: int | None = None) -> None:
    """Alta o actualizacion del precio de un producto en una lista.

    Un solo precio por **(lista, producto, sucursal)**: se borra el anterior de
    esa misma combinacion antes de escribir. Sin eso, `item_prices` acumularia
    filas y `resolve_price()` empezaria a depender del orden de insercion.

    ⚠️ **Fijar el precio general NO pisa los de sucursal**, y al reves tampoco.
    Son filas distintas a proposito: la sucursal que tiene precio propio lo
    tiene porque alguien lo cargo, y un ajuste general que lo borrara en
    silencio seria la peor forma de enterarse. Para sacarlo, se borra el precio
    de esa sucursal con `borrar_precio()`.
    """
    with libracore_core.get_connection() as conn:
        comercial.verificar_sucursal(conn, sucursal_id)
        _borrar_fila(conn, lista_id, item_id, sucursal_id)
        _repo(conn).save_item_price(
            ItemPrice(None, item_id, lista_id, Decimal(str(precio)),
                      valid_from=_SIN_VIGENCIA, branch_id=sucursal_id)
        )


def borrar_precio(lista_id: int, item_id: int,
                  sucursal_id: int | None = None) -> None:
    """Saca un precio. Con `sucursal_id`, saca **solo el de esa sucursal**, y
    el producto vuelve a cotizar por el precio general de la lista."""
    with libracore_core.get_connection() as conn:
        _borrar_fila(conn, lista_id, item_id, sucursal_id)


def ajustar_por_porcentaje(lista_id: int, porcentaje: float,
                           sucursal_id: int | None = None) -> int:
    """Actualizacion masiva. Devuelve cuantos precios movio.

    Es la operacion que mas se usa en la practica --"subime todo un 12%"-- y la
    razon por la que las listas de precio existen como entidad y no como una
    columna en el producto.

    ⚠️ **Sin `sucursal_id` mueve TODO, incluidos los precios propios de cada
    sucursal.** Es lo correcto para el aumento general --si sube el proveedor,
    sube en las dos sucursales--, pero hay que saberlo: no es "solo los
    generales". Con `sucursal_id` mueve unicamente los de esa sucursal, y los
    productos que ahi cotizan por el precio general **no se tocan**, porque
    moverlos seria mover el precio de la otra sucursal tambien.
    """
    factor = 1 + (porcentaje / 100)
    if factor <= 0:
        raise ValueError("El ajuste dejaria precios en cero o negativos.")
    sql = "UPDATE item_prices SET amount = ROUND(amount * ?, 2) WHERE price_list_id=?"
    params: tuple = (factor, lista_id)
    if sucursal_id is not None:
        sql += " AND branch_id = ?"
        params += (sucursal_id,)
    with libracore_core.get_connection() as conn:
        return max(conn.execute(sql, params).rowcount or 0, 0)
