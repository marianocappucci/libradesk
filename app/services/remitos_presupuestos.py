"""Remitos y presupuestos: **cero logica de dominio propia**.

Todo el dominio (numeracion, CRUD, busqueda, vencimiento automatico) sale
de `libracore.db.remitos_presupuestos`, y los PDF de
`libracore.pdf_generator` (`RemitoPDF` / `PresupuestoPDF`) — el mismo
codigo que ya usan Contalibra y Restolibra. Este modulo es solo el
adaptador: configura LibraCore contra la base de LibraDesk, crea las dos
tablas que el dominio necesita, y envuelve las funciones para que los
routers reciban/devuelvan dicts con totales ya calculados.

Tres decisiones que cuestan tiempo si no estan escritas:

1. **Una sola base, dos tablas.** `libracore.db.core.configure()` acepta un
   `db_path` por producto, asi que apunta al mismo `libradesk.db` que usa
   SQLAlchemy. No hay segunda base ni las otras 29 tablas de LibraCore
   (facturacion/ARCA/caja), que LibraDesk no usa.

2. **El DDL se copia a mano y SIN la FK a `clients`.** `init_core_schema()`
   de LibraCore no es componible por tabla (es un solo `executescript` con
   las 31), asi que las dos se crean aca. Pero el DDL original declara
   `client_id INTEGER REFERENCES clients(id)` y LibraDesk **no tiene
   `clients`** (tiene `clientes`, SQLAlchemy). Dejar la FK colgando NO es
   inocuo: `libracore.db.core.get_connection()` corre
   `PRAGMA foreign_keys = ON` en **toda** conexion (core.py:69), y con el
   pragma activo SQLite resuelve la tabla padre al preparar el chequeo, asi
   que **todo INSERT falla con `no such table: main.clients` — incluso con
   `client_id = NULL`** (verificado empiricamente antes de escribir esto; no
   es que las FK con NULL se saltean, es que ni llega a mirar el valor).
   Por eso `client_id` se declara `INTEGER` pelado. La integridad contra
   `clientes` la sostiene el router, que valida que el cliente exista.

3. **`usuario_id` va en el `CREATE TABLE`.** En LibraCore esa columna la
   agrega una funcion de migracion aparte, no el DDL — pero
   `create_remito()`/`create_presupuesto()` la insertan. Copiar el DDL tal
   cual daria `no such column: usuario_id` en el primer alta. Su FK a
   `usuarios` SI se conserva: esa tabla existe (la crea `libraauth`), y
   `ensure_schema()` corre despues de `create_all()` para garantizar el
   orden.
"""
from __future__ import annotations

import os

from libracore import config_manager
from libracore.db import core as libracore_core
from libracore.db import remitos_presupuestos as rp

from . import iva

# El DDL de LibraCore (libracore/db/schema.py) menos la FK a `clients`, y
# con `usuario_id` incluido. Cualquier otra diferencia contra el original es
# un bug: las dos tablas las lee y escribe el codigo de LibraCore.
_DDL = """
CREATE TABLE IF NOT EXISTS remitos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    number         TEXT NOT NULL UNIQUE,
    date           TEXT NOT NULL,
    client_id      INTEGER,
    client_name    TEXT NOT NULL,
    client_address TEXT,
    client_cuit    TEXT,
    client_email   TEXT,
    client_phone   TEXT,
    items          TEXT NOT NULL,
    subtotal       REAL NOT NULL,
    tax_rate       REAL NOT NULL DEFAULT 0.21,
    tax_amount     REAL NOT NULL,
    total          REAL NOT NULL,
    observations   TEXT,
    pdf_path       TEXT,
    usuario_id     INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    created_at     TEXT DEFAULT (datetime('now','-3 hours'))
);

CREATE TABLE IF NOT EXISTS presupuestos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    number          TEXT NOT NULL UNIQUE,
    date            TEXT NOT NULL,
    valid_until     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'borrador',
    client_id       INTEGER,
    client_name     TEXT NOT NULL,
    client_address  TEXT,
    client_cuit     TEXT,
    client_email    TEXT,
    client_phone    TEXT,
    items           TEXT NOT NULL,
    subtotal        REAL NOT NULL,
    tax_rate        REAL NOT NULL DEFAULT 0.21,
    tax_amount      REAL NOT NULL,
    total           REAL NOT NULL,
    observations    TEXT,
    pdf_path        TEXT,
    remito_id       INTEGER REFERENCES remitos(id),
    usuario_id      INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    created_at      TEXT DEFAULT (datetime('now','-3 hours'))
);
"""

ESTADOS_PRESUPUESTO = ("borrador", "enviado", "aceptado", "rechazado", "vencido")


def configure(database_url: str, data_dir: str) -> None:
    """Apunta LibraCore a la base y al DATA_DIR de esta instancia.

    `config_manager` y `pdf_generator` congelan sus rutas al importarse
    (leen `DATA_DIR` a nivel de modulo), lo que en produccion da lo correcto
    pero en los tests deja la ruta del primer test para todos los demas
    —`libracore.*` no se reimporta entre tests, solo `app.*`—. Rebindear
    aca es explicito y del mismo tipo que `core.configure()`: LibraCore esta
    disenado para configurarse por producto.
    """
    if not database_url:
        raise ValueError("database_url vacia")
    # 🔴 **Este producto corre sobre PostgreSQL y nada mas.** La guarda va aca,
    # en el arranque del producto, y no dentro de `libracore.db.core`: el motor
    # tiene que poder abrir un SQLite igual, porque de eso vive la herramienta
    # de diagnostico `python -m libracore.db.schema_dump`, que vuelca el schema
    # de un archivo viejo o de la base de LibraEdge --- la excepcion permanente
    # de la familia. La regla "este producto no habla con otro motor" es del
    # producto.
    #
    # Aca habia un `if/else`: URL de PostgreSQL a `configure()` tal cual, y
    # cualquier otra cosa convertida a ruta de archivo con `make_url().database`.
    # Con la guarda esa segunda rama no existe mas. Ademas el criterio sale del
    # motor y no de una lista escrita a mano --- `es_url_postgres` es el mismo
    # chequeo en un solo lugar, y las listas a mano son las que se olvidan de
    # `postgresql+psycopg://` (le paso a Gestiolibra).
    if not libracore_core.es_url_postgres(database_url):
        raise RuntimeError(
            f"LibraDesk corre solo sobre PostgreSQL y recibio {database_url!r}, que no es "
            "una URL de PostgreSQL. El modo SQLite se retiro el 2026-08-12: no "
            "chequea las FK, tipa dinamicamente y acepta cadenas donde la base "
            "pide enteros."
        )
    libracore_core.configure(database_url)

    config_manager.CONFIG_PATH = os.path.join(data_dir, "config.json")
    config_manager.LOGO_DIR = os.path.join(data_dir, "logos")


def ensure_schema() -> None:
    """Crea `remitos` y `presupuestos` si no existen. Llamar DESPUES de
    `create_all()`, para que la FK `usuario_id -> usuarios` tenga destino."""
    with libracore_core.get_connection() as conn:
        conn.executescript(_DDL)


def _totales(items: list[dict], tax_rate: float) -> tuple[float, float, float]:
    """Totales calculados en el servidor: lo que manda el cliente se ignora.

    Desde el 2026-08-05 **cada linea lleva su alicuota** y el IVA se suma linea
    por linea; `tax_rate` queda como default de las que no la traigan. Antes era
    `subtotal * tax_rate` para todo el comprobante, que daba mal apenas una
    linea era exenta. Ver `app/services/iva.py`.
    """
    con_alicuota = [{**i, "tax_rate": _alicuota(i, tax_rate)} for i in items]
    return iva.totales(con_alicuota)


def _alicuota(item: dict, defecto: float) -> float:
    """La alicuota de una linea, o la del documento.

    ⚠️ No alcanza con `item.get("tax_rate", defecto)`: el payload del router
    trae la clave **presente y en `None`** cuando el usuario no la eligio
    (`tax_rate: float | None = None`), y ahi `.get` devuelve `None`, no el
    default. Un `None` multiplicando revienta o —peor— se cuela como 0.
    """
    valor = item.get("tax_rate")
    return float(defecto if valor is None else valor)


#: Las dos monedas que admite un renglon. Cerrada como la lista de alicuotas y
#: por el mismo motivo: lo que salga de aca termina en un comprobante fiscal.
MONEDAS = ("ARS", "USD")

#: La moneda de un renglon que no dice nada. Es la del comprobante emitido.
MONEDA_DEFECTO = "ARS"


def _normalizar_items(items: list[dict], tax_rate: float = 0.21,
                      cotizacion: float | None = None) -> list[dict]:
    """Deja los items en la forma que espera el PDF de LibraCore
    (`description`/`qty`/`unit_price`/`subtotal`, ver `_draw_items_table`),
    con el subtotal por linea recalculado.

    Suma dos campos: `tax_rate` —la alicuota de esa linea, que se guarda en el
    JSON— y `iva_pct`, la misma en porcentaje, que es lo que lee la columna de
    IVA del PDF (`item["iva_pct"]`). Se guardan los dos en vez de derivar uno
    del otro al dibujar, para que un comprobante ya guardado no dependa de que
    alguien recuerde la conversion.

    Y conserva `detalle` si viene: la aclaracion corta de ESE renglon, que el
    PDF imprime debajo del nombre del item. Es opcional item por item, asi que
    la clave solo se escribe cuando tiene texto.

    ## La moneda por renglon (2026-09-09)

    Lagrace arma una **pre-factura** donde conviven renglones en pesos y en
    dolares --y alicuotas del 10,5 y del 21-- y la factura **sale unificada en
    pesos**.

    🔑 **Un renglon en dolares se convierte ACA, y `unit_price` sigue siendo el
    importe EN PESOS.** Ese es el truco entero: los totales, el PDF, la cuenta
    corriente y el adaptador de SOS leen `unit_price`/`subtotal` y **no se
    enteran de que existen los dolares**. Guardar el dolar ahi habria obligado
    a tocar los cuatro, y el de SOS **no tiene donde poner la moneda**: su
    `PUT /venta` manda numeros pelados, sin `moneda` ni `ctz`.

    Del renglon en dolares se guardan ademas tres claves: `moneda`,
    `unit_price_origen` (el precio en dolares, tal como se tipeo) y
    `cotizacion` (la que se uso). Con eso el comprobante se vuelve a mostrar en
    su moneda original sin recalcular nada.

    🔴 **La cotizacion se congela por renglon.** No se deriva al leer: si se
    derivara, reimprimir en diciembre una factura de agosto la convertiria al
    dolar de diciembre. Es la misma regla que gobierna `contratos_precios`, que
    nunca sobrescribe un precio.

    🔴 **Un renglon en dolares SIN cotizacion es un error, no un `x1`.** Caer a
    1 dejaria el comprobante emitido por una fraccion de lo que vale **sin que
    nada falle**, que es el modo de falla mas caro que puede tener esto.

    Los renglones en pesos no escriben ninguna de las tres claves, misma
    convencion que `detalle`: un comprobante sin dolares queda **igual** que
    antes de que la moneda existiera.
    """
    salida = []
    for i in items:
        qty = float(i["qty"])
        precio = float(i["unit_price"])
        alicuota = _alicuota(i, tax_rate)
        moneda = str(i.get("moneda") or MONEDA_DEFECTO).upper()
        if moneda not in MONEDAS:
            raise ValueError(
                f"Moneda invalida: {moneda!r}. Las validas son {', '.join(MONEDAS)}."
            )

        unit_price = precio
        extra: dict = {}
        if moneda != MONEDA_DEFECTO:
            # 🔴 **Esta funcion tiene que ser IDEMPOTENTE, y es lo mas facil de
            # romper de todo el cambio.** Un renglon ya normalizado vuelve a
            # pasar por aca en tres caminos: al editar un comprobante guardado,
            # al convertir un presupuesto en remito (`convertir_a_remito` le
            # pasa `p["items"]` tal cual) y al reconvertir. En esos casos
            # `unit_price` **ya viene en pesos** mientras `moneda` sigue
            # diciendo `USD`: convertirlo otra vez lo multiplica por la
            # cotizacion **dos veces**, y el comprobante sale por mil veces su
            # valor sin que nada falle.
            #
            # Se distingue por `unit_price_origen`, que solo existe en un item
            # que ya paso por aca. Cuando esta, se reconvierte desde el precio
            # en dolares con la cotizacion **congelada de ese renglon** --no con
            # la del argumento--, asi que el resultado es identico al de la
            # primera vez y un presupuesto convertido en remito conserva su
            # tipo de cambio original aunque el dolar se haya movido.
            origen = i.get("unit_price_origen")
            congelada = i.get("cotizacion")
            if origen is not None and congelada:
                precio = float(origen)
                tipo_cambio = float(congelada)
            elif cotizacion and float(cotizacion) > 0:
                tipo_cambio = float(cotizacion)
            else:
                raise ValueError(
                    f"El renglon {str(i.get('description') or '')!r} esta en "
                    f"{moneda} y el comprobante no tiene cotizacion cargada."
                )
            # Se redondea a dos DESPUES de multiplicar, no antes: la cotizacion
            # tiene cuatro decimales y redondearla primero le mueve el importe
            # a cada renglon.
            unit_price = round(precio * tipo_cambio, 2)
            extra = {
                "moneda": moneda,
                "unit_price_origen": precio,
                "cotizacion": tipo_cambio,
            }

        item = {
            "description": str(i["description"]).strip(),
            "qty": qty,
            "unit_price": unit_price,
            "subtotal": round(qty * unit_price, 2),
            "tax_rate": alicuota,
            "iva_pct": round(alicuota * 100, 1),
            **extra,
        }
        # `detalle` solo si tiene texto: la clave ausente y la clave vacia
        # significan lo mismo para el PDF, y no escribirla deja los
        # comprobantes sin detalle igual que antes de que el campo existiera.
        detalle = str(i.get("detalle") or "").strip()
        if detalle:
            item["detalle"] = detalle
        salida.append(item)
    return salida


def _plata(valor: float) -> str:
    """`1450.5` -> `1.450,50`. Formato argentino, que es el de presentacion.

    Solo para el papel: la base y las APIs siguen con el numero. Ver la regla
    de formato de fecha y hora del proyecto, que dice lo mismo.
    """
    return f"{valor:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def comprobante_para_pdf(comprobante: dict) -> dict:
    """El comprobante con la conversion de cada renglon en dolares **a la vista**.

    > *"Cuando la factura se genera ya muestra los valores unificados en pesos
    > con sus respectivos calculos."*

    Los importes del papel siguen siendo los pesos --eso no se toca-- y lo que
    se agrega es de donde salieron: `USD 100,00 x $1.450,50` debajo del nombre
    del item.

    🔑 **Va en `detalle`, que el PDF de [[libracore]] ya imprime, y por eso el
    motor no se toca.** Una columna de moneda propia seria un cambio en el
    generador que comparten los ocho productos, con su release, para algo que
    hoy usa uno solo. Si mañana lo pide un segundo producto, ahi si sube.

    🔴 **No pisa el detalle que escribio la persona: lo appendea.** Y devuelve
    una copia --`items` nuevo, dicts nuevos-- porque lo guardado no se modifica
    para dibujar. Un comprobante que volviera del PDF con el detalle cambiado
    lo iria acumulando en cada reimpresion.
    """
    items = []
    for i in comprobante.get("items") or []:
        item = dict(i)
        if item.get("moneda") and item.get("moneda") != MONEDA_DEFECTO:
            conversion = (
                f"{item['moneda']} {_plata(float(item.get('unit_price_origen') or 0))}"
                f" x ${_plata(float(item.get('cotizacion') or 0))}"
            )
            detalle = str(item.get("detalle") or "").strip()
            item["detalle"] = f"{detalle} - {conversion}" if detalle else conversion
        items.append(item)
    return {**comprobante, "items": items}


def datos_cliente_para_comprobante(cliente: dict, override_address: str | None = None) -> dict:
    """Del cliente de LibraDesk a los campos que copia un comprobante.

    Vive aca y no en los routers porque desde el 2026-08-13 hay **tres**
    lugares que arman un comprobante a partir de un cliente —remitos,
    presupuestos y la conversion de una incidencia— y con una copia por lugar
    alcanzaba con tocar dos para que el tercero empezara a emitir con otros
    datos.

    `empresa or nombre` no es cosmetico: el comprobante va a nombre de la razon
    social cuando existe, y al nombre de la persona cuando el cliente es una
    persona. `override_address` deja pisar el domicilio en el comprobante sin
    tocar la ficha del cliente; `None` significa "usar el del cliente", que no
    es lo mismo que `""`.
    """
    return {
        "client_name": cliente["empresa"] or cliente["nombre"],
        "client_address": (
            override_address if override_address is not None
            else (cliente["ciudad"] or "")
        ),
        "client_email": cliente["email"] or "",
        "client_phone": cliente["telefono"] or "",
    }


class RemitoService:
    """Envoltorio sobre `libracore.db.remitos_presupuestos` (remitos)."""

    def next_number(self) -> str:
        return rp.get_next_remito_number()

    def create(self, *, date, client_id, client_name, client_address="", client_cuit="",
               client_email="", client_phone="", items, tax_rate=0.21, observations="",
               usuario_id=None, cotizacion=None) -> dict:
        items = _normalizar_items(items, tax_rate, cotizacion)
        subtotal, tax_amount, total = _totales(items, tax_rate)
        # Lo que se guarda en la columna del comprobante es la alicuota
        # EFECTIVA, no la que vino del formulario: si las lineas mezclan, no
        # hay una sola que describa al documento. Ver `iva.py`.
        tax_rate = iva.alicuota_del_documento(items)
        remito_id = rp.create_remito(
            rp.get_next_remito_number(), date, client_id, client_name, client_address,
            client_cuit, client_email, client_phone, items, subtotal, tax_rate,
            tax_amount, total, observations, "", usuario_id,
        )
        return rp.get_remito(remito_id)

    def list(self, limit: int = 100) -> list[dict]:
        return rp.get_all_remitos(limit)

    def get(self, remito_id: int) -> dict | None:
        return rp.get_remito(remito_id)

    def by_client(self, client_id: int) -> list[dict]:
        return rp.get_remitos_by_client(client_id)

    def search(self, query: str) -> list[dict]:
        return rp.search_remitos(query)

    def update(self, remito_id: int, *, date, client_id, client_name, client_address="",
               client_cuit="", client_email="", client_phone="", items, tax_rate=0.21,
               observations="", cotizacion=None) -> dict:
        if rp.get_remito(remito_id) is None:
            raise KeyError(remito_id)
        items = _normalizar_items(items, tax_rate, cotizacion)
        subtotal, tax_amount, total = _totales(items, tax_rate)
        # Lo que se guarda en la columna del comprobante es la alicuota
        # EFECTIVA, no la que vino del formulario: si las lineas mezclan, no
        # hay una sola que describa al documento. Ver `iva.py`.
        tax_rate = iva.alicuota_del_documento(items)
        rp.update_remito(
            remito_id, date, client_id, client_name, client_address, client_cuit,
            client_email, client_phone, items, subtotal, tax_rate, tax_amount,
            total, observations,
        )
        return rp.get_remito(remito_id)

    def delete(self, remito_id: int) -> None:
        """Borra el remito **si nada lo referencia**.

        `presupuestos.remito_id` guarda de que presupuesto salio el remito
        (`convertir_a_remito`). Borrar el remito dejaba esa columna apuntando a
        un id inexistente y el presupuesto seguia diciendo "ya se convirtio",
        sin nada al otro lado. Contra PostgreSQL esa FK rechaza el borrado
        sola; aca se hace explicito para que SQLite haga lo mismo (2026-08-09).

        Desde el 2026-08-13 vale igual para `incidencias.remito_id`, que es el
        mismo vinculo con el otro origen. **Ahi la FK no existe en ningun
        motor** —`incidencias` es SQLAlchemy y `remitos` no, ver el comentario
        de la columna—, asi que este chequeo es la unica defensa que hay.
        """
        if rp.get_remito(remito_id) is None:
            raise KeyError(remito_id)

        colgando = self.dependencias(remito_id)
        if any(colgando.values()):
            raise ValueError(colgando)

        rp.delete_remito(remito_id)

    def dependencias(self, remito_id: int) -> dict[str, int]:
        """Que sigue apuntando a este remito. Todo en cero = se puede borrar."""
        from libracore.db import core as libracore_core

        with libracore_core.get_connection() as conn:
            presupuestos = conn.execute(
                "SELECT COUNT(*) FROM presupuestos WHERE remito_id=?", (remito_id,)
            ).fetchone()[0]
            # `incidencias` la escribe SQLAlchemy, pero vive en la MISMA base
            # (`configure()` apunta LibraCore al mismo destino), asi que se lee
            # por esta conexion como cualquier otra tabla. Leerla por el ORM
            # obligaria a inyectar la session factory en este servicio, que hoy
            # no depende de SQLAlchemy para nada.
            incidencias = conn.execute(
                "SELECT COUNT(*) FROM incidencias WHERE remito_id=?", (remito_id,)
            ).fetchone()[0]
        return {
            "presupuestos_convertidos": presupuestos,
            "incidencias_convertidas": incidencias,
        }

    def set_pdf_path(self, remito_id: int, pdf_path: str) -> None:
        rp.update_remito_pdf_path(remito_id, pdf_path)


class PresupuestoService:
    """Envoltorio sobre `libracore.db.remitos_presupuestos` (presupuestos).

    Ojo: varias funciones de LibraCore corren `auto_vencimiento_presupuestos()`
    antes de leer (los listados, la busqueda y el conteo por estado), asi que
    un presupuesto `enviado` con `valid_until` pasado aparece ya como
    `vencido` sin que nadie corra una tarea programada.
    """

    def next_number(self) -> str:
        return rp.get_next_presupuesto_number()

    def create(self, *, date, valid_until, client_id, client_name, client_address="",
               client_cuit="", client_email="", client_phone="", items, tax_rate=0.21,
               observations="", status="borrador", usuario_id=None,
               cotizacion=None) -> dict:
        items = _normalizar_items(items, tax_rate, cotizacion)
        subtotal, tax_amount, total = _totales(items, tax_rate)
        # Lo que se guarda en la columna del comprobante es la alicuota
        # EFECTIVA, no la que vino del formulario: si las lineas mezclan, no
        # hay una sola que describa al documento. Ver `iva.py`.
        tax_rate = iva.alicuota_del_documento(items)
        presupuesto_id = rp.create_presupuesto(
            rp.get_next_presupuesto_number(), date, valid_until, client_id, client_name,
            client_address, client_cuit, client_email, client_phone, items, subtotal,
            tax_rate, tax_amount, total, observations, "", status, usuario_id,
        )
        return rp.get_presupuesto(presupuesto_id)

    def list(self, limit: int = 100, estado: str | None = None) -> list[dict]:
        return rp.get_all_presupuestos(limit, estado)

    def counts_by_estado(self) -> dict[str, int]:
        return rp.get_presupuestos_count_by_estado()

    def get(self, presupuesto_id: int) -> dict | None:
        return rp.get_presupuesto(presupuesto_id)

    def by_client(self, client_id: int) -> list[dict]:
        return rp.get_presupuestos_by_client(client_id)

    def search(self, query: str, estado: str | None = None) -> list[dict]:
        return rp.search_presupuestos(query, estado)

    def update(self, presupuesto_id: int, *, date, valid_until, status, client_id,
               client_name, client_address="", client_cuit="", client_email="",
               client_phone="", items, tax_rate=0.21, observations="",
               cotizacion=None) -> dict:
        if rp.get_presupuesto(presupuesto_id) is None:
            raise KeyError(presupuesto_id)
        items = _normalizar_items(items, tax_rate, cotizacion)
        subtotal, tax_amount, total = _totales(items, tax_rate)
        # Lo que se guarda en la columna del comprobante es la alicuota
        # EFECTIVA, no la que vino del formulario: si las lineas mezclan, no
        # hay una sola que describa al documento. Ver `iva.py`.
        tax_rate = iva.alicuota_del_documento(items)
        rp.update_presupuesto(
            presupuesto_id, date, valid_until, status, client_id, client_name,
            client_address, client_cuit, client_email, client_phone, items,
            subtotal, tax_rate, tax_amount, total, observations,
        )
        return rp.get_presupuesto(presupuesto_id)

    def set_status(self, presupuesto_id: int, status: str) -> dict:
        if status not in ESTADOS_PRESUPUESTO:
            raise ValueError(status)
        if rp.get_presupuesto(presupuesto_id) is None:
            raise KeyError(presupuesto_id)
        rp.update_presupuesto_status(presupuesto_id, status)
        return rp.get_presupuesto(presupuesto_id)

    def delete(self, presupuesto_id: int) -> None:
        """LibraCore solo permite borrar un presupuesto en `borrador`; en
        cualquier otro estado levanta ValueError, que el router traduce a 409."""
        if rp.get_presupuesto(presupuesto_id) is None:
            raise KeyError(presupuesto_id)
        rp.delete_presupuesto(presupuesto_id)

    def set_pdf_path(self, presupuesto_id: int, pdf_path: str) -> None:
        rp.update_presupuesto_pdf_path(presupuesto_id, pdf_path)

    def convertir_a_remito(self, presupuesto_id: int, remitos: RemitoService,
                           usuario_id=None) -> dict:
        """Genera el remito con los datos del presupuesto, lo deja linkeado y
        marca el presupuesto como `aceptado`.

        Delega el esqueleto (idempotencia, link, marcar aceptado) en
        `libracore.convertir_presupuesto_a_remito`; la arista de LibraDesk entra
        por los hooks: `crear_remito` recomputa los totales (IVA por línea vía
        `RemitoService.create`) y conserva `usuario_id`, y valida el estado ahí
        —dentro del create— para que un retorno idempotente no valide, igual que
        antes. `al_convertir` marca `aceptado` sólo en una conversión nueva."""
        presupuesto = rp.get_presupuesto(presupuesto_id)
        if presupuesto is None:
            raise KeyError(presupuesto_id)

        def crear(p):
            if p["status"] in ("rechazado", "vencido"):
                raise ValueError(f"no se convierte un presupuesto {p['status']}")
            remito = remitos.create(
                date=p["date"],
                client_id=p["client_id"],
                client_name=p["client_name"],
                client_address=p["client_address"] or "",
                client_cuit=p["client_cuit"] or "",
                client_email=p["client_email"] or "",
                client_phone=p["client_phone"] or "",
                items=p["items"],
                tax_rate=p["tax_rate"],
                observations=f"Generado del presupuesto {p['number']}",
                usuario_id=usuario_id,
            )
            return remito["id"]

        return rp.convertir_presupuesto_a_remito(
            presupuesto,
            idempotente=True,
            crear_remito=crear,
            al_convertir=lambda pres_id, _remito: rp.update_presupuesto_status(
                pres_id, "aceptado"),
        )
