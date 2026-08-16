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

from . import comercial, iva

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


def listar_depositos(sucursal_id: int | None = None) -> list[dict]:
    """Los depositos de consumibles. `sucursal_id=None` los trae todos.

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
            if sucursal_id is None or loc.branch_id == sucursal_id
        ]


def crear_deposito(nombre: str, descripcion: str = "", es_default: bool = False,
                   sucursal_id: int | None = None) -> dict:
    if not (nombre or "").strip():
        raise ValueError("El deposito necesita un nombre.")
    with libracore_core.get_connection() as conn:
        comercial.verificar_sucursal(conn, sucursal_id)
        loc = _repo(conn).save_location(
            Location(None, nombre.strip(), description=descripcion,
                     is_default=es_default, branch_id=sucursal_id)
        )
        return {"id": loc.id, "nombre": loc.name}


# ── Catalogo de consumibles ──────────────────────────────────────────────


def listar_items(solo_activos: bool = True,
                 sucursal_id: int | None = None) -> list[dict]:
    """El catalogo, con el stock total ya sumado.

    El total viene de una sola consulta agregada sobre `stock_movements` y no de
    N llamadas a `current_stock()`. Con 300 consumibles y 6 depositos la
    diferencia entre las dos formas es la que hace que la pantalla abra o no.

    Con `sucursal_id` el total es **el de esa sucursal**, y `bajo_minimo` se
    calcula contra ese total: mirando Chivilcoy, lo que importa es si falta
    material en Chivilcoy, no si sobra en la otra punta.
    """
    with libracore_core.get_connection() as conn:
        # El JOIN contra `locations` sale solo cuando hay filtro. Sin sucursal
        # es la misma consulta agregada de siempre, sin costo agregado.
        if sucursal_id is None:
            filas = conn.execute(
                "SELECT item_id, SUM(quantity_delta) AS total "
                "FROM stock_movements GROUP BY item_id"
            ).fetchall()
        else:
            filas = conn.execute(
                "SELECT sm.item_id, SUM(sm.quantity_delta) AS total "
                "FROM stock_movements sm "
                "JOIN locations l ON l.id = sm.location_id "
                "WHERE l.branch_id = ? GROUP BY sm.item_id",
                (sucursal_id,),
            ).fetchall()
        totales = {r["item_id"]: float(r["total"] or 0) for r in filas}
        categorias = {c["id"]: c["nombre"] for c in listar_categorias(conn)}
        items = _repo(conn).list_catalog_items(
            active_only=solo_activos, item_type=CatalogItemType.PRODUCT
        )
        codigos = _codigos_primarios(conn)
        return [
            {"id": it.id, "nombre": it.name, "activo": it.active,
             "stock_minimo": float(it.min_stock), "costo": float(it.default_cost),
             "precio": float(it.default_sale_price),
             "iva_rate": float(alicuota_de(it)),
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


# ── La alícuota de IVA de un producto ───────────────────────────────────────
#
# Vive en `catalog_items.tax_profile`, que es **la columna del motor** para
# esto: existe en el schema de LibraCommerce desde siempre, el repositorio la
# lee y la escribe, y hasta el 2026-08-16 **ningún consumidor la usaba** — se
# verificó en los cinco repos y en el propio motor, cuyo adaptador de Contalibra
# la deja explícitamente en `None` con el comentario *"Contalibra resolves IVA at
# invoicing time"*.
#
# 🔑 **Por qué acá y no en una tabla propia de LibraDesk.** La alternativa era un
# `productos_iva(item_id, iva_rate)` en la cadena de Alembic, y sería una segunda
# fuente de verdad sobre un producto del motor: un item dado de baja allá dejaría
# una fila huérfana acá, y cada lectura del catálogo necesitaría un join. Es
# exactamente el patrón de espejado que este producto viene evitando en depósitos
# y en el precio de los contratos.
#
# ⚠️ **Es TEXT y guarda el número como cadena** (`"0.21"`). El nombre de la
# columna dice "perfil" y acá se usa como alícuota: es una decisión, no un
# descuido. El motor no ofrece otro lugar, y las cuatro alícuotas válidas ya
# están cerradas por `iva.ALICUOTAS`, así que el texto libre no puede entrar —
# `_alicuota_texto()` valida antes de escribir.
def _leer_alicuota(crudo: str | None) -> Decimal:
    """El texto de `tax_profile` a alícuota. `iva.DEFECTO` si no dice nada.

    **El default es 21% y no 0%** a propósito: un producto sin alícuota cargada
    es un producto que nadie tocó todavía, no un producto exento. Devolver 0
    haría que el remito saliera sin IVA y nadie lo notaría hasta la factura;
    devolver 21 es la respuesta correcta para la enorme mayoría, y lo que no lo
    sea se carga a mano.
    """
    texto = (crudo or "").strip()
    if not texto:
        return iva.DEFECTO
    try:
        return iva.validar(texto)
    except (iva.AlicuotaInvalida, ArithmeticError, ValueError):
        # Un valor que no es una de las cuatro llegó por fuera de este módulo
        # —una carga vieja, una migración de datos—. Se cae al default en vez de
        # explotar: el catálogo tiene que poder listarse igual.
        return iva.DEFECTO


def alicuota_de(item: CatalogItem) -> Decimal:
    """La alícuota de un producto ya leído del catálogo."""
    return _leer_alicuota(item.tax_profile)


def _alicuota_texto(iva_rate) -> str:
    """`0.21` → `"0.21"`, validando contra las cuatro que ARCA sabe mapear."""
    return str(iva.validar(iva_rate))


def alicuotas_de_items(item_ids) -> dict[int, Decimal]:
    """`{item_id: alícuota}` para los ids pedidos, en **una sola** consulta.

    Existe para que `ventas.convertir_a_remito()` no pida el catálogo ítem por
    ítem: una venta de doce líneas serían doce `get_catalog_item()`. Mismo
    motivo por el que `listar_items()` suma el stock con una agregada en vez de
    N llamadas a `current_stock()`.

    Lee `tax_profile` directo por SQL en vez de armar el `CatalogItem` entero:
    de las catorce columnas del producto, acá hace falta una.

    Los ids que no existen no aparecen en el resultado; el que llama decide con
    qué reemplazarlos.
    """
    unicos = {int(i) for i in item_ids if i}
    if not unicos:
        return {}
    marcadores = ", ".join("?" for _ in unicos)
    with libracore_core.get_connection() as conn:
        filas = conn.execute(
            f"SELECT id, tax_profile FROM catalog_items WHERE id IN ({marcadores})",
            tuple(unicos),
        ).fetchall()
    return {f["id"]: _leer_alicuota(f["tax_profile"]) for f in filas}


def crear_item(nombre: str, costo: float = 0.0, stock_minimo: float = 0.0, *,
               precio: float = 0.0, unidad: str = "u", descripcion: str = "",
               categoria_id: int | None = None, codigo: str = "",
               iva_rate=None) -> dict:
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
                tax_profile=_alicuota_texto(
                    iva.DEFECTO if iva_rate is None else iva_rate
                ),
            )
        )
        # 🔑 **Siempre queda con codigo.** Si el alta trae uno se respeta —el
        # del proveedor, un EAN—; si no, se genera `PRD-NNNNNNNN`. Hasta el
        # 2026-08-16 un alta sin codigo dejaba el producto sin ninguno y la
        # columna del listado salia vacia, que es lo que reporto el humano.
        codigo_final = codigo.strip() or _siguiente_codigo(conn)
        _guardar_codigo(conn, item.id, codigo_final)
        return {"id": item.id, "nombre": item.name, "codigo": codigo_final}


def editar_item(item_id: int, *, nombre: str, costo: float = 0.0,
                stock_minimo: float = 0.0, precio: float = 0.0,
                unidad: str = "u", descripcion: str = "",
                categoria_id: int | None = None, activo: bool = True,
                iva_rate=None) -> None:
    """Edita un producto del catálogo.

    🔴 **`iva_rate=None` conserva la alícuota que ya tenía, no la borra.**

    No es una cortesía: `save_catalog_item()` recibe un `CatalogItem` **entero**
    y pisa la fila con lo que traiga, así que todo campo que esta función no
    ponga se pierde en silencio. La alícuota es el único campo del producto que
    no está en el formulario de todas las pantallas que llaman acá, y sin este
    rescate editar el precio desde cualquiera de ellas dejaría el producto sin
    IVA — el remito saldría bien la primera vez y mal después de la primera
    corrección, que es la peor forma de fallar que tiene esto.
    """
    with libracore_core.get_connection() as conn:
        repo = _repo(conn)
        actual = repo.get_catalog_item(item_id)
        if actual is None:
            raise ValueError("El consumible no existe.")
        repo.save_catalog_item(
            CatalogItem(
                item_id, CatalogItemType.PRODUCT, nombre.strip(), _unidad(unidad),
                category_id=categoria_id, description=descripcion, active=activo,
                default_cost=Decimal(str(costo)),
                default_sale_price=Decimal(str(precio)),
                min_stock=Decimal(str(stock_minimo)),
                tax_profile=_alicuota_texto(
                    alicuota_de(actual) if iva_rate is None else iva_rate
                ),
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
               fecha: datetime | None = None) -> dict:
    """Mueve consumibles entre depositos, en una sola transaccion.

    Es el caso de uso central del producto que motivo todo esto: el deposito
    central que abastece la camioneta de un tecnico. Delega en el motor --que
    hace las dos escrituras y la lectura que las autoriza en la misma
    transaccion-- en vez de escribir los dos movimientos a mano, que es como
    Contalibra lo tenia y perdia mercaderia si el segundo fallaba.

    ## Entre sucursales es el MISMO movimiento, con otro nombre

    Cuando origen y destino son de sucursales distintas, lo unico que cambia es
    el `reason_code`: `transferencia_sucursal_salida`/`_entrada` en vez de
    `transferencia_salida`/`_entrada`. **No hay estado "en transito" ni
    confirmacion del lado que recibe** --decidido el 2026-08-14--: sale y entra
    en la misma transaccion, igual que entre dos depositos de la misma
    sucursal.

    > ⚠️ **Lo que eso implica, dicho de frente**: entre el momento en que la
    > mercaderia sale fisicamente y el momento en que llega, el sistema ya la
    > cuenta en el destino. Si hace falta que alguien confirme la recepcion,
    > este no es el mecanismo y no alcanza con leer el `reason_code`: hay que
    > agregar el tercer estado.

    El `reason_code` distinto no es cosmetico: es lo que hace que
    `transferencias(solo_entre_sucursales=True)` pueda existir sin releer las
    dos `locations` de cada par de movimientos.
    """
    with libracore_core.get_connection() as conn:
        repo = _repo(conn)
        origen = repo.get_location(origen_id)
        destino = repo.get_location(destino_id)
        if origen is None or destino is None:
            raise ValueError("El deposito de origen o el de destino no existe.")
        # `is not` sobre dos `int | None`: dos depositos sin sucursal NO cruzan
        # nada, y uno con sucursal contra uno sin sucursal SI --es sacar
        # mercaderia del circuito de una sucursal, y merece el nombre--.
        entre_sucursales = origen.branch_id != destino.branch_id
        sufijo = "_sucursal" if entre_sucursales else ""
        try:
            salida, entrada = transfer_stock(
                repo,
                item_id=item_id,
                from_location_id=origen_id,
                to_location_id=destino_id,
                quantity=Decimal(str(cantidad)),
                occurred_at=fecha or datetime.now(),
                note=nota,
                created_by=usuario_id,
                reason_code_salida=f"transferencia{sufijo}_salida",
                reason_code_entrada=f"transferencia{sufijo}_entrada",
            )
        except StockInsuficienteError as e:
            raise ValueError(
                f"Stock insuficiente en el deposito de origen "
                f"(disponible: {float(e.disponible)})."
            ) from e
    return {"salida_id": salida.id, "entrada_id": entrada.id,
            "entre_sucursales": entre_sucursales,
            "origen_sucursal_id": origen.branch_id,
            "destino_sucursal_id": destino.branch_id}


def transferencias(sucursal_id: int | None = None, *,
                   solo_entre_sucursales: bool = False,
                   limit: int = 200) -> list[dict]:
    """El historial de transferencias, reconstruido desde el ledger.

    **No hay tabla de transferencias** y no hace falta una: el motor deja la
    entrada apuntando a la salida con `source_type='transfer'` y `source_id` =
    id de la salida (ver `transfer_stock`), asi que un `JOIN` de
    `stock_movements` contra si misma devuelve el par completo. Inventar una
    tabla aparte seria una segunda version de la verdad que puede desincronizarse
    del ledger, que es lo unico que `current_stock()` mira.

    `sucursal_id` trae las que **tocan** esa sucursal, de los dos lados: lo que
    salio y lo que entro. Filtrar solo por destino contestaria "que me llego" y
    dejaria fuera la mitad de la pregunta.
    """
    sql = """
        SELECT e.id AS entrada_id, s.id AS salida_id,
               e.item_id, ci.name AS item, ci.unit_code AS unidad,
               e.quantity_delta AS cantidad, e.occurred_at, e.note,
               e.reason_code,
               s.location_id AS origen_id, lo.name AS origen,
               lo.branch_id AS origen_sucursal_id, so.nombre AS origen_sucursal,
               e.location_id AS destino_id, ld.name AS destino,
               ld.branch_id AS destino_sucursal_id, sd.nombre AS destino_sucursal,
               e.created_by, u.nombre AS usuario
        FROM stock_movements e
        JOIN stock_movements s ON s.id = e.source_id
        JOIN catalog_items ci ON ci.id = e.item_id
        JOIN locations lo ON lo.id = s.location_id
        JOIN locations ld ON ld.id = e.location_id
        LEFT JOIN sucursales so ON so.id = lo.branch_id
        LEFT JOIN sucursales sd ON sd.id = ld.branch_id
        LEFT JOIN usuarios u ON u.id = e.created_by
        WHERE e.source_type = 'transfer'
    """
    params: list = []
    if solo_entre_sucursales:
        # 🔴 Comparacion **null-safe escrita a mano**, y no `IS NOT` ni
        # `IS DISTINCT FROM`. `a IS NOT b` es sintaxis de SQLite y PostgreSQL la
        # rechaza (ahi `IS NOT` solo acepta NULL/TRUE/FALSE), y LibraDesk corre
        # sobre PostgreSQL en las tres instancias. `IS DISTINCT FROM` si es
        # estandar, pero en SQLite depende de la version del binario.
        #
        # Un `<>` pelado tampoco sirve: con un deposito sin sucursal daria NULL
        # --ni verdadero ni falso-- y esa transferencia quedaria afuera, que es
        # justo el caso de sacar mercaderia del circuito de una sucursal.
        sql += (" AND ((lo.branch_id IS NULL) <> (ld.branch_id IS NULL)"
                "      OR lo.branch_id <> ld.branch_id)")
    if sucursal_id is not None:
        sql += " AND (lo.branch_id = ? OR ld.branch_id = ?)"
        params += [sucursal_id, sucursal_id]
    sql += " ORDER BY e.occurred_at DESC, e.id DESC LIMIT ?"
    params.append(limit)

    with libracore_core.get_connection() as conn:
        filas = conn.execute(sql, tuple(params)).fetchall()
    return [
        {"salida_id": r["salida_id"], "entrada_id": r["entrada_id"],
         "item_id": r["item_id"], "item": r["item"], "unidad": r["unidad"],
         "cantidad": float(r["cantidad"]), "fecha": r["occurred_at"],
         "nota": r["note"] or "",
         "origen_id": r["origen_id"], "origen": r["origen"],
         "origen_sucursal_id": r["origen_sucursal_id"],
         "origen_sucursal": r["origen_sucursal"] or "",
         "destino_id": r["destino_id"], "destino": r["destino"],
         "destino_sucursal_id": r["destino_sucursal_id"],
         "destino_sucursal": r["destino_sucursal"] or "",
         "entre_sucursales": r["origen_sucursal_id"] != r["destino_sucursal_id"],
         "usuario_id": r["created_by"], "usuario": r["usuario"] or ""}
        for r in filas
    ]


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


#: El prefijo del codigo interno de un producto. Misma forma que el resto de los
#: correlativos del producto —`CTR-`, `REC-`, `ENT-`— porque son la misma clase
#: de identificador: uno que se lee en voz alta y se busca a mano.
_PREFIJO_CODIGO = "PRD-"


def _siguiente_codigo(conn) -> str:
    """`PRD-00000001`, correlativo — el codigo que se genera solo.

    Pedido del humano el 2026-08-16: *"los productos deberian tener un codigo
    que se genere automaticamente"*. Hasta hoy `codigo` existia pero habia que
    tipearlo, asi que la mayoria de los productos no tenia ninguno y la columna
    del listado salia vacia.

    **Se calcula del maximo dentro de la misma transaccion que inserta**, igual
    que `ContratoRepository._siguiente_numero`. Es lo que evita el duplicado
    entre dos altas simultaneas.

    🔑 **Solo mira los codigos con este prefijo.** Un codigo tipeado a mano —el
    que trae el proveedor, un EAN— no entra en la cuenta y no la corre: los dos
    conviven, y el automatico se usa solo cuando el alta no trae ninguno.
    """
    fila = conn.execute(
        "SELECT MAX(code) AS ultimo FROM item_codes WHERE code LIKE ?",
        (f"{_PREFIJO_CODIGO}%",),
    ).fetchone()
    ultimo = fila["ultimo"] if fila else None
    if not ultimo:
        return f"{_PREFIJO_CODIGO}00000001"
    try:
        siguiente = int(ultimo[len(_PREFIJO_CODIGO):]) + 1
    except ValueError:
        # Alguien escribio "PRD-A1" a mano. No se rompe el alta por eso: se
        # cuenta cuantos hay y se sigue, que a lo sumo deja un salto.
        siguiente = conn.execute(
            "SELECT COUNT(*) AS n FROM item_codes WHERE code LIKE ?",
            (f"{_PREFIJO_CODIGO}%",),
        ).fetchone()["n"] + 1
    return f"{_PREFIJO_CODIGO}{siguiente:08d}"


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


def grilla_stock(sucursal_id: int | None = None) -> dict:
    """Todos los consumibles contra todos los depositos, en una sola consulta.

    Es lo que faltaba para que el modulo fuera usable: hasta ahora el stock se
    miraba **consumible por consumible**, asi que la pregunta normal de un
    deposito --"que tengo aca"-- no tenia pantalla que la contestara.

    Devuelve `{depositos, items, celdas}` en vez de una matriz armada: la
    matriz la arma la pantalla, y asi el mismo endpoint sirve para la grilla y
    para el detalle de un deposito.

    Con `sucursal_id` se recortan **los depositos y las celdas**, no los items:
    el catalogo es de la empresa y una fila en cero es informacion ("aca no hay
    de eso"), mientras que una columna de otra sucursal es ruido.
    """
    with libracore_core.get_connection() as conn:
        depositos = [
            {"id": loc.id, "nombre": loc.name, "es_default": loc.is_default,
             "sucursal_id": loc.branch_id}
            for loc in _repo(conn).list_locations(active_only=True)
            if sucursal_id is None or loc.branch_id == sucursal_id
        ]
        items = [
            {"id": it.id, "nombre": it.name, "unidad": it.unit.code,
             "stock_minimo": float(it.min_stock)}
            for it in _repo(conn).list_catalog_items(
                active_only=True, item_type=CatalogItemType.PRODUCT
            )
        ]
        filas = conn.execute(
            """
            SELECT item_id, location_id, SUM(quantity_delta) AS total
            FROM stock_movements
            GROUP BY item_id, location_id
            HAVING SUM(quantity_delta) <> 0
            """
        ).fetchall()
        # Las celdas se filtran contra los depositos que ya quedaron, y no con
        # un segundo WHERE sobre `branch_id`: asi no hay forma de que la grilla
        # traiga una celda de una columna que no esta.
        visibles = {d["id"] for d in depositos}
        celdas = [
            {"item_id": r["item_id"], "deposito_id": r["location_id"],
             "stock": float(r["total"] or 0)}
            for r in filas if r["location_id"] in visibles
        ]
    return {"depositos": depositos, "items": items, "celdas": celdas}


def bajo_minimo(sucursal_id: int | None = None) -> list[dict]:
    """Los consumibles cuyo stock TOTAL quedo por debajo de su minimo.

    ⚠️ **El minimo se compara contra el total de todos los depositos**, no
    contra cada uno. Un minimo por deposito significaria que la camioneta de un
    tecnico dispara reposicion cada vez que sale a trabajar, que es ruido y no
    informacion. Si algun dia hace falta el minimo por deposito, es una columna
    nueva y no una relectura de esta.

    ⚠️ **Con `sucursal_id` el minimo se compara contra el stock de esa
    sucursal**, y eso es una decision, no una consecuencia: el minimo es uno
    solo por consumible (`catalog_items.min_stock`, de la empresa). Mirando una
    sucursal, un consumible puede figurar bajo minimo aunque la empresa entera
    tenga de sobra. Es lo que hace util la vista --dice donde reponer-- pero no
    hay que leer la suma de las dos sucursales como el faltante de la empresa.
    """
    return [
        i for i in listar_items(solo_activos=True, sucursal_id=sucursal_id)
        if i["bajo_minimo"]
    ]


def editar_deposito(deposito_id: int, nombre: str, descripcion: str = "",
                    activo: bool = True, sucursal_id: int | None = None) -> None:
    with libracore_core.get_connection() as conn:
        repo = _repo(conn)
        actual = repo.get_location(deposito_id)
        if actual is None:
            raise ValueError("El deposito no existe.")
        # Mover un deposito de sucursal mueve con el todo su stock, porque las
        # existencias cuelgan del deposito y no de la sucursal. Se permite --es
        # como se corrige un deposito mal asignado-- pero la sucursal destino
        # tiene que existir y estar activa.
        comercial.verificar_sucursal(conn, sucursal_id)
        repo.save_location(
            Location(deposito_id, nombre.strip(), description=descripcion,
                     active=activo, is_default=actual.is_default,
                     branch_id=sucursal_id)
        )
