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

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from libracommerce.db.repository import SqliteCommerceRepository
from libracommerce.db.schema import init_schema
from libracommerce.domain.catalog import (
    CatalogItem,
    CatalogItemType,
    ItemCode,
    ItemCodeType,
    Unit,
)
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
    "editar_item",
    "baja_item",
    "listar_categorias",
    "crear_categoria",
    "codigos_de",
    "agregar_codigo",
    "buscar_por_codigo",
    "grilla_stock",
    "bajo_minimo",
]

#: La unidad por defecto de un consumible, cuando el alta no elige otra.
#: El motor exige una siempre.
_UNIDAD = Unit("u", "Unidad")

#: Las unidades que se ofrecen en el alta. Salen del relevamiento de Lagrace:
#: cable y canaleta se compran por metro, el resto por unidad o caja.
UNIDADES = (
    Unit("u", "Unidad"),
    Unit("m", "Metro", allows_fraction=True, decimal_scale=2),
    Unit("caja", "Caja"),
    Unit("rollo", "Rollo"),
)


def _unidad(codigo: str) -> Unit:
    for u in UNIDADES:
        if u.code == codigo:
            return u
    return _UNIDAD


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
        sucursales = {
            s["id"]: s["nombre"]
            for s in conn.execute("SELECT id, nombre FROM sucursales").fetchall()
        }
        return [
            {"id": loc.id, "nombre": loc.name, "activo": loc.active,
             "descripcion": loc.description, "es_default": loc.is_default,
             # `branch_id` es del motor y no tiene FK: la tabla `sucursales` es
             # de este producto. Ver `app/services/comercial.py`.
             "sucursal_id": loc.branch_id,
             "sucursal": sucursales.get(loc.branch_id, "")}
            for loc in _repo(conn).list_locations()
        ]


def crear_deposito(nombre: str, descripcion: str = "", es_default: bool = False,
                   sucursal_id: int | None = None) -> dict:
    if not (nombre or "").strip():
        raise ValueError("El deposito necesita un nombre.")
    with libracore_core.get_connection() as conn:
        loc = _repo(conn).save_location(
            Location(None, nombre.strip(), description=descripcion,
                     is_default=es_default, branch_id=sucursal_id)
        )
        return {"id": loc.id, "nombre": loc.name}


# ── Catalogo de consumibles ──────────────────────────────────────────────


def listar_items(solo_activos: bool = True) -> list[dict]:
    """El catalogo, con el stock total ya sumado.

    El total viene de una sola consulta agregada sobre `stock_movements` y no de
    N llamadas a `current_stock()`. Con 300 consumibles y 6 depositos la
    diferencia entre las dos formas es la que hace que la pantalla abra o no.
    """
    with libracore_core.get_connection() as conn:
        totales = {
            r["item_id"]: float(r["total"] or 0)
            for r in conn.execute(
                "SELECT item_id, SUM(quantity_delta) AS total "
                "FROM stock_movements GROUP BY item_id"
            ).fetchall()
        }
        categorias = {c["id"]: c["nombre"] for c in listar_categorias(conn)}
        items = _repo(conn).list_catalog_items(
            active_only=solo_activos, item_type=CatalogItemType.PRODUCT
        )
        codigos = _codigos_primarios(conn)
        return [
            {"id": it.id, "nombre": it.name, "activo": it.active,
             "stock_minimo": float(it.min_stock), "costo": float(it.default_cost),
             "precio": float(it.default_sale_price),
             "unidad": it.unit.code, "descripcion": it.description,
             "categoria_id": it.category_id,
             "categoria": categorias.get(it.category_id, ""),
             "codigo": codigos.get(it.id, ""),
             "stock": totales.get(it.id, 0.0),
             "bajo_minimo": (
                 float(it.min_stock) > 0
                 and totales.get(it.id, 0.0) < float(it.min_stock)
             )}
            for it in items
        ]


def crear_item(nombre: str, costo: float = 0.0, stock_minimo: float = 0.0, *,
               precio: float = 0.0, unidad: str = "u", descripcion: str = "",
               categoria_id: int | None = None, codigo: str = "") -> dict:
    if not (nombre or "").strip():
        raise ValueError("El consumible necesita un nombre.")
    with libracore_core.get_connection() as conn:
        item = _repo(conn).save_catalog_item(
            CatalogItem(
                None, CatalogItemType.PRODUCT, nombre.strip(), _unidad(unidad),
                category_id=categoria_id, description=descripcion,
                default_cost=Decimal(str(costo)),
                default_sale_price=Decimal(str(precio)),
                min_stock=Decimal(str(stock_minimo)),
            )
        )
        if codigo.strip():
            _guardar_codigo(conn, item.id, codigo.strip())
        return {"id": item.id, "nombre": item.name}


def editar_item(item_id: int, *, nombre: str, costo: float = 0.0,
                stock_minimo: float = 0.0, precio: float = 0.0,
                unidad: str = "u", descripcion: str = "",
                categoria_id: int | None = None, activo: bool = True) -> None:
    with libracore_core.get_connection() as conn:
        repo = _repo(conn)
        if repo.get_catalog_item(item_id) is None:
            raise ValueError("El consumible no existe.")
        repo.save_catalog_item(
            CatalogItem(
                item_id, CatalogItemType.PRODUCT, nombre.strip(), _unidad(unidad),
                category_id=categoria_id, description=descripcion, active=activo,
                default_cost=Decimal(str(costo)),
                default_sale_price=Decimal(str(precio)),
                min_stock=Decimal(str(stock_minimo)),
            )
        )


def baja_item(item_id: int) -> None:
    """Baja **logica**, igual que clientes y proveedores.

    Un consumible con movimientos historicos no se puede borrar sin romper esa
    historia --y `stock_movements` es append-only a proposito--, pero si dejar
    de ofrecerse en los selects.
    """
    with libracore_core.get_connection() as conn:
        repo = _repo(conn)
        item = repo.get_catalog_item(item_id)
        if item is None:
            raise ValueError("El consumible no existe.")
        repo.save_catalog_item(replace(item, active=False))


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


# ── Categorias ───────────────────────────────────────────────────────────
#
# `categories` es una tabla de LibraCommerce que hasta hoy se creaba vacia. Se
# consulta por SQL directo y no por el repositorio porque el motor no expone un
# `list_categories()` -- tiene el DDL y el `category_id` en `catalog_items`,
# pero no el CRUD. Es un hueco del motor, no una preferencia de este producto:
# **si algun dia LibraCommerce lo agrega, esto se reemplaza por la llamada.**


def listar_categorias(conn=None) -> list[dict]:
    """Acepta una conexion abierta para poder reusarla desde `listar_items()`.

    Sin eso, listar el catalogo abriria dos conexiones para una pantalla.
    """
    sql = "SELECT id, name, parent_id, active FROM categories ORDER BY name"
    if conn is not None:
        filas = conn.execute(sql).fetchall()
    else:
        with libracore_core.get_connection() as c:
            filas = c.execute(sql).fetchall()
    return [
        {"id": r["id"], "nombre": r["name"], "parent_id": r["parent_id"],
         "activa": bool(r["active"])}
        for r in filas
    ]


def crear_categoria(nombre: str, parent_id: int | None = None) -> dict:
    if not (nombre or "").strip():
        raise ValueError("La categoria necesita un nombre.")
    with libracore_core.get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO categories (name, parent_id, active) VALUES (?,?,1)",
            (nombre.strip(), parent_id),
        )
        return {"id": cur.lastrowid, "nombre": nombre.strip()}


# ── Codigos / SKU ────────────────────────────────────────────────────────


def _guardar_codigo(conn, item_id: int, codigo: str) -> None:
    _repo(conn).save_item_code(
        ItemCode(None, item_id, ItemCodeType.INTERNAL, codigo, is_primary=True)
    )


def _codigos_primarios(conn) -> dict[int, str]:
    return {
        r["item_id"]: r["code"]
        for r in conn.execute(
            "SELECT item_id, code FROM item_codes WHERE is_primary = 1"
        ).fetchall()
    }


def codigos_de(item_id: int) -> list[dict]:
    with libracore_core.get_connection() as conn:
        return [
            {"id": c.id, "tipo": str(c.code_type), "codigo": c.code,
             "principal": c.is_primary}
            for c in _repo(conn).list_item_codes(item_id)
        ]


def agregar_codigo(item_id: int, codigo: str, principal: bool = False) -> dict:
    if not (codigo or "").strip():
        raise ValueError("El codigo no puede estar vacio.")
    with libracore_core.get_connection() as conn:
        guardado = _repo(conn).save_item_code(
            ItemCode(None, item_id, ItemCodeType.INTERNAL, codigo.strip(),
                     is_primary=principal)
        )
        return {"id": guardado.id, "codigo": guardado.code}


def buscar_por_codigo(codigo: str) -> dict | None:
    """Busqueda exacta por codigo, la que usa el lector o el tipeo rapido.

    Es la razon de ser de `item_codes`: en Integridad el operador tipea
    `10000315` y aparece el `PLUG RJ 45 CAT 6`. Sin codigos, la unica busqueda
    posible es por nombre, y "plug" devuelve diez.
    """
    with libracore_core.get_connection() as conn:
        item = _repo(conn).find_item_by_code(codigo.strip())
        if item is None:
            return None
        return {"id": item.id, "nombre": item.name,
                "costo": float(item.default_cost),
                "precio": float(item.default_sale_price)}


# ── Existencias, la vista de conjunto ────────────────────────────────────


def grilla_stock() -> dict:
    """Todos los consumibles contra todos los depositos, en una sola consulta.

    Es lo que faltaba para que el modulo fuera usable: hasta ahora el stock se
    miraba **consumible por consumible**, asi que la pregunta normal de un
    deposito --"que tengo aca"-- no tenia pantalla que la contestara.

    Devuelve `{depositos, items, celdas}` en vez de una matriz armada: la
    matriz la arma la pantalla, y asi el mismo endpoint sirve para la grilla y
    para el detalle de un deposito.
    """
    with libracore_core.get_connection() as conn:
        depositos = [
            {"id": loc.id, "nombre": loc.name, "es_default": loc.is_default}
            for loc in _repo(conn).list_locations(active_only=True)
        ]
        items = [
            {"id": it.id, "nombre": it.name, "unidad": it.unit.code,
             "stock_minimo": float(it.min_stock)}
            for it in _repo(conn).list_catalog_items(
                active_only=True, item_type=CatalogItemType.PRODUCT
            )
        ]
        celdas = [
            {"item_id": r["item_id"], "deposito_id": r["location_id"],
             "stock": float(r["total"] or 0)}
            for r in conn.execute(
                """
                SELECT item_id, location_id, SUM(quantity_delta) AS total
                FROM stock_movements
                GROUP BY item_id, location_id
                HAVING SUM(quantity_delta) <> 0
                """
            ).fetchall()
        ]
    return {"depositos": depositos, "items": items, "celdas": celdas}


def bajo_minimo() -> list[dict]:
    """Los consumibles cuyo stock TOTAL quedo por debajo de su minimo.

    ⚠️ **El minimo se compara contra el total de todos los depositos**, no
    contra cada uno. Un minimo por deposito significaria que la camioneta de un
    tecnico dispara reposicion cada vez que sale a trabajar, que es ruido y no
    informacion. Si algun dia hace falta el minimo por deposito, es una columna
    nueva y no una relectura de esta.
    """
    return [i for i in listar_items(solo_activos=True) if i["bajo_minimo"]]


def editar_deposito(deposito_id: int, nombre: str, descripcion: str = "",
                    activo: bool = True, sucursal_id: int | None = None) -> None:
    with libracore_core.get_connection() as conn:
        repo = _repo(conn)
        actual = repo.get_location(deposito_id)
        if actual is None:
            raise ValueError("El deposito no existe.")
        repo.save_location(
            Location(deposito_id, nombre.strip(), description=descripcion,
                     active=activo, is_default=actual.is_default,
                     branch_id=sucursal_id)
        )
