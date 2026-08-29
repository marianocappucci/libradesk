"""El schema comercial que LibraDesk toma prestado de LibraCore, el espejo de
`parties` que lo habilita, y las sucursales.

Este modulo no tiene dominio propio: es **el paso 6 del arranque**, lo que
tiene que existir en la base antes de que egresos, recibos, cuenta corriente,
compras y ventas puedan funcionar. El dominio de cada uno vive en su propio
`app/services/<modulo>.py` y todos delegan en LibraCore o LibraCommerce.

## Por que el DDL se copia a mano (otra vez)

Mismo motivo que `remitos_presupuestos.py`, y con la misma incomodidad:
`init_core_schema()` de LibraCore es **un solo `executescript` con 31 tablas**
y no se puede pedir por familia. LibraDesk necesita ocho de esas tablas y no
las otras veintitres --no tiene facturacion propia (la emite SOS Contador), ni
caja, ni tesoreria--.

> 🔴 **Esto es deuda, no diseño.** La salida buena es hacer `init_core_schema()`
> componible por familia en LibraCore, que sirve a los seis productos; esta
> copia son ~110 lineas que hay que mantener sincronizadas a mano y **nadie
> avisa cuando el motor cambia**. Se hizo asi porque cambiar el motor obliga a
> publicar una version y mover el pin de seis productos. Ver
> `wiki/analyses/libradesk-modulo-comercial-plan.md`, fase 0.

## Las FK que hubo que tocar, por dos motivos distintos

**Motivo 1 — la tabla padre no existe en este producto.**
`libracore.db.core.get_connection()` corre `PRAGMA foreign_keys = ON` en toda
conexion. Con el pragma activo **SQLite resuelve la tabla padre al preparar el
chequeo**, asi que una FK que apunta a una tabla inexistente hace fallar
**todo INSERT** con `no such table` --incluso con la columna en NULL--. Es el
mismo pozo documentado en `remitos_presupuestos.py` para `clients`.

| Columna | FK original | Que se hizo |
|---|---|---|
| `ventas_pagos.venta_id` | `ventas(id)` | **repuntada a `sales(id)`** |
| `caja_movimientos.turno_id` | `turnos_caja(id)` | INTEGER pelado: no hay turnos de caja |

La primera no es una FK menos: es *la* decision de este modulo. LibraDesk vende
por `sales` de LibraCommerce, no por la tabla `ventas` de LibraCore, asi que
`ventas_pagos` cuelga de `sales`. Es coherente con el origen
`VENTAS_LIBRACOMMERCE` que consume la cuenta corriente --y es la razon por la
que el orden del arranque importa: esto corre DESPUES de
`inventario.ensure_schema()`, que es quien crea `sales`.

**Motivo 2 — la tabla padre la maneja Alembic y esta no.** Este archivo escribe
DDL crudo; `proveedores` y `clients` los versiona la cadena de `migrations/`.
Una FK que cruza los dos sistemas deja la tabla del lado Alembic **imposible de
recrear**: el `downgrade` la borra para rehacerla y PostgreSQL lo rechaza porque
algo la referencia, asi que **se rompe la cadena entera, no solo este modulo**.

| Columna | FK original |
|---|---|
| `egresos.proveedor_id` | `proveedores(id)` |
| `cc_pagos.cliente_id`, `cc_debitos.cliente_id`, `cc_resumenes_enviados.cliente_id`, `recibos.cliente_id` | `clients(id)` |

Las cinco quedan como INTEGER pelado y **la integridad la sostiene el router**,
igual que `client_id` en `remitos_presupuestos.py`. No se descubrio pensando:
lo destapo `test_la_migracion_agrega_cuit_y_domicilio_a_una_base_vieja`, que
hace un downgrade real hasta el baseline.

> La regla que queda, y vale para el proximo modulo que copie DDL: **el DDL
> crudo no referencia tablas de Alembic**. Al reves si --`egresos_pagos` cuelga
> de `egresos` y las dos son de aca--.

## Tres tablas que se crean para quedar VACIAS, y no es desprolijidad

`facturas`, `cajas` y `caja_movimientos` no las usa LibraDesk --no emite
comprobantes fiscales (los emite SOS Contador) ni lleva caja-- y sin embargo se
crean. Las dos razones se descubrieron leyendo el motor, no probando:

1. **`get_cc_saldo()` las consulta siempre.** Su segunda pata suma los debitos
   por factura con `FROM caja_movimientos cm JOIN facturas f ...`, y solo la
   saltea si el cliente no tiene CUIT. Los clientes de LibraDesk **si** tienen
   CUIT, asi que sin estas dos tablas la cuenta corriente no devuelve cero:
   **revienta**.
2. **`create_pago_egreso()` busca la caja por defecto.** Hace
   `caja_id or get_default_caja_id()`, y esa funcion es un `SELECT id FROM
   cajas`. Con la tabla ausente, registrar el pago de un egreso falla; con la
   tabla presente y vacia devuelve `None`, el pago se guarda con `caja_id` en
   NULL y **el camino del motor corre sin modificar**.

Vacias, las dos consultas devuelven 0 y NULL respectivamente, que es la
respuesta correcta para un producto que no factura ni maneja caja. Es el mismo
criterio con el que el motor documenta `cc_debitos`: *"queda vacia en los
productos que no la usan, asi que su saldo no cambia"*.

## Por que este modulo no se podria haber escrito la semana pasada

Aunque las FK contra `clients` no queden declaradas, el modulo **depende** de
que esa tabla sea la del motor: `get_cc_saldo()` hace
`SELECT cuit_dni FROM clients` y los cuatro `cliente_id` de arriba guardan su
id. La revision `0017` (2026-08-12) llevo la tabla de clientes de LibraDesk a la
compartida de LibraCore; antes de eso el motor habria leido una tabla que no
existia.
"""

from __future__ import annotations

from libracore.db import core as libracore_core

#: Los proveedores viven desplazados dentro de `parties` para no chocar con
#: los ids de `clients`. 500.000 y no 100.000 para no pisar el offset que ya
#: usa VentaLibra en el mismo espacio (ver `libracore/db/clients.py`).
_OFFSET_PROVEEDOR = 500_000

#: Copiado de `libracore/db/schema.py` con las tres FK de arriba corregidas.
#: Cualquier OTRA diferencia contra el original es un bug: estas tablas las
#: leen y escriben `libracore.db.egresos`, `.recibos` y `.cuenta_corriente`.
_DDL_LIBRACORE = """
CREATE TABLE IF NOT EXISTS facturas (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo             INTEGER NOT NULL,
    punto_venta      INTEGER NOT NULL,
    numero           INTEGER NOT NULL,
    fecha            TEXT NOT NULL,
    cliente_cuit     TEXT,
    cliente_razon    TEXT,
    cliente_iva_cond INTEGER,
    items            TEXT NOT NULL,
    subtotal         REAL NOT NULL,
    iva_amount       REAL NOT NULL,
    total            REAL NOT NULL,
    concepto         INTEGER NOT NULL DEFAULT 1,
    cae              TEXT,
    cae_vto          TEXT,
    observaciones    TEXT,
    pdf_path         TEXT,
    created_at       TEXT DEFAULT (datetime('now','-3 hours'))
);

CREATE TABLE IF NOT EXISTS cajas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT NOT NULL,
    descripcion TEXT DEFAULT '',
    medios_pago TEXT NOT NULL DEFAULT '[]',
    activo      INTEGER NOT NULL DEFAULT 1,
    es_default  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now','-3 hours'))
);

-- 🔴 Las tres ultimas columnas NO estan en el `CREATE TABLE` de LibraCore: se
-- las agrega su bloque de migraciones con `ALTER TABLE`, que corre dentro de
-- `init_core_schema()` --el que este producto no llama--. Copiar solo el DDL
-- deja la tabla sin ellas, y `get_cc_saldo()` **consulta `cm.medio_pago`**:
-- el saldo de cuenta corriente muere con `column cm.medio_pago does not
-- exist`. Verificado contra PostgreSQL antes de que llegara a la demo.
--
-- Es el mismo pozo que ya documenta `remitos_presupuestos.py` para
-- `usuario_id`, y la razon de fondo por la que copiar DDL a mano es deuda:
-- el `CREATE TABLE` del motor **no describe la tabla que el motor consulta**.
CREATE TABLE IF NOT EXISTS caja_movimientos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha       TEXT NOT NULL,
    tipo        TEXT NOT NULL,
    concepto    TEXT NOT NULL,
    monto       REAL NOT NULL,
    referencia  TEXT DEFAULT '',
    factura_id  INTEGER,
    created_at  TEXT DEFAULT (datetime('now','-3 hours')),
    turno_id    INTEGER,
    caja_id     INTEGER REFERENCES cajas(id) ON DELETE SET NULL,
    medio_pago  TEXT DEFAULT '',
    usuario_id  INTEGER REFERENCES usuarios(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS categorias_egreso (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE
);

-- ⚠️ `proveedor_id` va SIN la FK a `proveedores` que declara LibraCore, y no es
-- una omision: **`proveedores` la maneja Alembic y esta tabla no**. Una FK que
-- cruza los dos sistemas de schema deja la tabla de Alembic imposible de
-- recrear —PostgreSQL rechaza el `DROP TABLE proveedores` del downgrade porque
-- algo la referencia— y eso rompe la cadena entera, no sólo este modulo.
-- Lo destapo `test_la_migracion_agrega_cuit_y_domicilio_a_una_base_vieja`, que
-- hace un downgrade real hasta el baseline.
-- La integridad la sostiene el router, igual que `client_id` en
-- `remitos_presupuestos.py`.
CREATE TABLE IF NOT EXISTS egresos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha            TEXT NOT NULL,
    proveedor_id     INTEGER,
    proveedor_nombre TEXT NOT NULL DEFAULT '',
    tipo_comprobante TEXT NOT NULL DEFAULT 'otro',
    numero           TEXT DEFAULT '',
    categoria        TEXT DEFAULT '',
    concepto         TEXT NOT NULL,
    monto_neto       REAL NOT NULL DEFAULT 0,
    iva_pct          REAL NOT NULL DEFAULT 0,
    iva_monto        REAL NOT NULL DEFAULT 0,
    total            REAL NOT NULL,
    estado           TEXT NOT NULL DEFAULT 'pendiente',
    observaciones    TEXT DEFAULT '',
    usuario_id       INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    created_at       TEXT DEFAULT (datetime('now','-3 hours'))
);

CREATE TABLE IF NOT EXISTS egresos_pagos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    egreso_id   INTEGER NOT NULL REFERENCES egresos(id) ON DELETE CASCADE,
    fecha       TEXT NOT NULL,
    monto       REAL NOT NULL,
    caja_id     INTEGER REFERENCES cajas(id) ON DELETE SET NULL,
    medio_pago  TEXT DEFAULT '',
    referencia  TEXT DEFAULT '',
    usuario_id  INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    created_at  TEXT DEFAULT (datetime('now','-3 hours'))
);

CREATE TABLE IF NOT EXISTS ventas_pagos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id   INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    medio      TEXT NOT NULL,
    monto      REAL NOT NULL,
    referencia TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','-3 hours'))
);

CREATE TABLE IF NOT EXISTS cc_pagos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id  INTEGER NOT NULL,
    monto       REAL NOT NULL,
    fecha       TEXT NOT NULL,
    concepto    TEXT DEFAULT '',
    referencia  TEXT DEFAULT '',
    medio_pago  TEXT DEFAULT 'efectivo',
    caja_id     INTEGER REFERENCES cajas(id) ON DELETE SET NULL,
    usuario_id  INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    created_at  TEXT DEFAULT (datetime('now','-3 hours'))
);

CREATE TABLE IF NOT EXISTS cc_debitos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id  INTEGER NOT NULL,
    monto       REAL NOT NULL,
    fecha       TEXT NOT NULL,
    concepto    TEXT DEFAULT '',
    referencia  TEXT DEFAULT '',
    usuario_id  INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    created_at  TEXT DEFAULT (datetime('now','-3 hours'))
);

CREATE TABLE IF NOT EXISTS cc_resumenes_enviados (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id    INTEGER NOT NULL,
    fecha         TEXT NOT NULL,
    periodo_desde TEXT NOT NULL,
    periodo_hasta TEXT NOT NULL,
    saldo         REAL NOT NULL DEFAULT 0,
    email         TEXT DEFAULT '',
    estado        TEXT NOT NULL DEFAULT 'ok',
    detalle       TEXT DEFAULT '',
    automatico    INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now','-3 hours'))
);

CREATE TABLE IF NOT EXISTS recibos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    punto_venta       INTEGER NOT NULL DEFAULT 1,
    numero            INTEGER NOT NULL,
    fecha             TEXT NOT NULL,
    cliente_id        INTEGER,
    cliente_razon     TEXT NOT NULL,
    cliente_cuit      TEXT DEFAULT '',
    cliente_domicilio TEXT DEFAULT '',
    origen_tipo       TEXT NOT NULL,
    origen_id         INTEGER,
    concepto          TEXT DEFAULT '',
    total             REAL NOT NULL,
    pagos             TEXT NOT NULL DEFAULT '[]',
    observaciones     TEXT DEFAULT '',
    anulado           INTEGER NOT NULL DEFAULT 0,
    anulado_motivo    TEXT DEFAULT '',
    anulado_at        TEXT DEFAULT '',
    usuario_id        INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    created_at        TEXT DEFAULT (datetime('now','-3 hours'))
);
"""

#: Propio de LibraDesk. Ver el docstring de `listar_sucursales()`.
_DDL_PROPIO = """
CREATE TABLE IF NOT EXISTS sucursales (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre     TEXT NOT NULL UNIQUE,
    codigo     TEXT DEFAULT '',
    direccion  TEXT DEFAULT '',
    activa     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now','-3 hours'))
);
"""


def ensure_schema() -> None:
    """Crea las tablas comerciales. Llamar DESPUES de `inventario.ensure_schema()`.

    El orden no es cosmetico: `ventas_pagos` referencia `sales`, que la crea el
    `init_schema()` de LibraCommerce.
    """
    with libracore_core.get_connection() as conn:
        conn.executescript(_DDL_LIBRACORE)
        conn.executescript(_DDL_PROPIO)


def _existe_tabla(conn, nombre: str) -> bool:
    """Si la tabla existe, en los dos motores.

    🔴 **No se puede preguntar por `sqlite_master`**: en PostgreSQL esa relacion
    no existe y el adaptador de LibraCore no la emula --devuelve
    `ProgrammingError: relation "sqlite_master" does not exist`, verificado
    contra la instancia demo el 2026-08-12--. Es una trampa real porque el
    mismo codigo anda perfecto en una instancia SQLite y explota en produccion.
    """
    if libracore_core.is_postgres():
        sql = "SELECT 1 FROM information_schema.tables WHERE table_name=?"
        params = (nombre,)
    else:
        sql = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"
        params = (nombre,)
    return conn.execute(sql, params).fetchone() is not None


# ── El espejo de `parties` ───────────────────────────────────────────────
#
# `sales.customer_party_id`, `purchase_orders.supplier_party_id` y
# `purchase_receipts.supplier_party_id` tienen FK contra `parties`, y las dos
# de compras son **NOT NULL**. O sea: sin espejo no hay ni una venta ni una
# recepcion de compra.
#
# 🔴 **LibraCore sabe espejar clientes y en LibraDesk ese codigo no corre.**
# `libracore.db.clients._crear_party_espejo()` se dispara desde las escrituras
# de ESE modulo, y LibraDesk escribe sus clientes por SQLAlchemy a proposito
# --para que la auditoria por flush de libraauth vea la operacion (ver
# `app/services/clientes.py`)--. El resultado es que `parties` existe y esta
# vacia. Por eso el espejo se sincroniza aca, en el arranque y despues de cada
# alta, en vez de confiar en el motor.
#
# Del lado proveedor no hay espejo para nadie: LibraCore solo crea
# `party_type='person'`. Esa mitad se escribe entera aca.


def sincronizar_parties() -> dict:
    """Crea los `parties` que falten. Idempotente: se puede correr siempre.

    **Los clientes se espejan con el MISMO id.** Es lo que hace que
    `sales.customer_party_id` y `clients.id` sean intercambiables, que es como
    lo resolvio LibraCore y como lo consume la cuenta corriente
    (`VENTAS_LIBRACOMMERCE.columna_cliente` es `customer_party_id` y se compara
    contra un `cliente_id`). Romper esa igualdad rompe el saldo **en silencio**:
    el JOIN no falla, devuelve cero filas.

    Los **proveedores** no pueden usar su id crudo --colisionaria con el de un
    cliente-- asi que van desplazados `_OFFSET_PROVEEDOR`. No es elegante; es lo
    unico que no obliga a tocar el esquema del motor.

    Devuelve cuantos creo de cada lado.
    """
    creados = {"clientes": 0, "proveedores": 0}
    with libracore_core.get_connection() as conn:
        if not _existe_tabla(conn, "parties"):
            return creados

        cur = conn.execute(
            """
            INSERT INTO parties (id, party_type, display_name, legal_name,
                                 tax_id, email, phone, active)
            SELECT c.id, 'person', c.name, c.name, COALESCE(c.cuit_dni, ''),
                   COALESCE(c.email, ''), COALESCE(c.phone, ''),
                   COALESCE(c.activo, 1)
            FROM clients c
            LEFT JOIN parties p ON p.id = c.id
            WHERE p.id IS NULL
            """
        )
        creados["clientes"] = max(cur.rowcount or 0, 0)

        cur = conn.execute(
            """
            INSERT INTO parties (id, party_type, display_name, legal_name,
                                 tax_id, email, phone, active)
            SELECT pr.id + ?, 'company', pr.nombre, pr.nombre,
                   COALESCE(pr.cuit_dni, ''), COALESCE(pr.email, ''),
                   COALESCE(pr.telefono, ''),
                   CASE WHEN pr.activo THEN 1 ELSE 0 END
            FROM proveedores pr
            LEFT JOIN parties p ON p.id = pr.id + ?
            WHERE p.id IS NULL
            """,
            (_OFFSET_PROVEEDOR, _OFFSET_PROVEEDOR),
        )
        creados["proveedores"] = max(cur.rowcount or 0, 0)
    return creados


def asegurar_parties() -> None:
    """Sincroniza el espejo **antes de una operacion que lo necesita**.

    🔴 **Correr el espejo solo en el arranque no alcanza, y es un error que se
    ve recien en produccion.** Un proveedor dado de alta despues del boot no
    tiene `party`, asi que la primera recepcion de compra a su nombre muere con
    `violates foreign key constraint purchase_receipts_supplier_party_id_fkey`.
    Lo destapo `test_comercial_api.py`, no el flujo manual: al probar los
    servicios a mano se llamaba a `sincronizar_parties()` explicitamente entre
    el alta y la compra, que es justo lo que la app no hacia.

    Se llama desde `compras` y `ventas`, que son los tres puntos donde un id de
    `parties` viaja a una FK. Va aca y no en el alta de clientes/proveedores a
    proposito: **cubre tambien los que entran por otro camino** --una
    importacion, un script, el backoffice-- sin que cada camino tenga que
    acordarse.

    Es idempotente y barato: dos `INSERT ... SELECT` con anti-join sobre tablas
    de cientos de filas. Si algun dia son decenas de miles, se cambia por un
    espejo de una sola fila; hoy seria optimizar algo que no duele.
    """
    sincronizar_parties()


def party_de_proveedor(proveedor_id: int) -> int:
    """El id dentro de `parties` que le corresponde a un proveedor."""
    return proveedor_id + _OFFSET_PROVEEDOR


def proveedor_de_party(party_id: int) -> int:
    """La vuelta de `party_de_proveedor()`."""
    return party_id - _OFFSET_PROVEEDOR


# ── Sucursales ───────────────────────────────────────────────────────────


def listar_sucursales(solo_activas: bool = True) -> list[dict]:
    """Las sucursales de la empresa.

    **Sucursal es un eje transversal, no una instancia aparte** (decidido el
    2026-08-14, cerrando la pregunta que la fase 6 de
    `wiki/analyses/libradesk-modulo-comercial-plan.md` dejo abierta). Lo que
    fija el alcance son estas tres respuestas:

    - **La cuenta corriente de un cliente es UNA SOLA entre sucursales.** Es lo
      que descarta el camino de "una instancia por sucursal", y por eso ningun
      modulo de dinero filtra por sucursal: el saldo de un cliente es el mismo
      lo haya generado donde lo haya generado.
    - **Filtran los modulos comerciales y nada mas**: stock, depositos, ventas,
      compras y listas de precio. La mesa de ayuda --incidencias, agenda,
      tecnicos-- **no filtra**, y no es un pendiente: un tecnico atiende donde
      haga falta.
    - **La caja no entra** porque LibraDesk no lleva caja (ver el encabezado de
      este modulo). Si algun dia la lleva, la caja es por sucursal.

    **No hace falta una tabla puente**: `locations.branch_id`, `sales.branch_id`,
    `purchase_orders.branch_id` e `item_prices.branch_id` ya existen en
    LibraCommerce --sueltos, sin FK, porque el motor no trae tabla de
    sucursales--. Esta tabla es a lo que esos cuatro apuntan. Contalibra los
    deja en NULL siempre; LibraDesk es el primero de la familia que los usa.

    ⚠️ **Que no haya FK es exactamente por que no hay borrado.** Ver
    `cambiar_estado_sucursal()`.
    """
    sql = """
        SELECT s.id, s.nombre, s.codigo, s.direccion, s.activa,
               (SELECT COUNT(*) FROM locations l
                 WHERE l.branch_id = s.id AND l.active = 1) AS depositos
        FROM sucursales s
    """
    if solo_activas:
        sql += " WHERE s.activa = 1"
    sql += " ORDER BY s.nombre"
    with libracore_core.get_connection() as conn:
        return [
            {"id": r["id"], "nombre": r["nombre"], "codigo": r["codigo"],
             "direccion": r["direccion"], "activa": bool(r["activa"]),
             "depositos": r["depositos"]}
            for r in conn.execute(sql).fetchall()
        ]


def crear_sucursal(nombre: str, codigo: str = "", direccion: str = "") -> dict:
    if not (nombre or "").strip():
        raise ValueError("La sucursal necesita un nombre.")
    with libracore_core.get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO sucursales (nombre, codigo, direccion) VALUES (?,?,?)",
            (nombre.strip(), codigo, direccion),
        )
        return {"id": cur.lastrowid, "nombre": nombre.strip()}


def editar_sucursal(sucursal_id: int, nombre: str, codigo: str = "",
                    direccion: str = "") -> None:
    if not (nombre or "").strip():
        raise ValueError("La sucursal necesita un nombre.")
    with libracore_core.get_connection() as conn:
        cur = conn.execute(
            "UPDATE sucursales SET nombre=?, codigo=?, direccion=? WHERE id=?",
            (nombre.strip(), codigo, direccion, sucursal_id),
        )
        if not cur.rowcount:
            raise ValueError("La sucursal no existe.")


def cambiar_estado_sucursal(sucursal_id: int, activa: bool) -> None:
    """Baja y alta **logicas**. No existe el borrado, y no por conservadurismo.

    `locations.branch_id`, `sales.branch_id`, `purchase_orders.branch_id` e
    `item_prices.branch_id` son columnas del motor **sin FK contra esta tabla**
    --el motor no la conoce--. Un `DELETE` no rebota ni cascadea: deja cuatro
    tablas apuntando a un id que ya no existe, y el sintoma aparece meses
    despues como una venta cuya sucursal figura en blanco. La baja logica la
    saca de los selects y conserva la historia.

    La guarda de depositos activos es lo mismo mirado desde el otro lado:
    desactivar una sucursal que todavia tiene stock parado ahi lo vuelve
    invisible en la pantalla filtrada sin que nadie lo haya movido.
    """
    with libracore_core.get_connection() as conn:
        fila = conn.execute(
            "SELECT nombre FROM sucursales WHERE id=?", (sucursal_id,)
        ).fetchone()
        if fila is None:
            raise ValueError("La sucursal no existe.")
        if not activa:
            _verificar_baja_de_sucursal(conn, sucursal_id)
        conn.execute(
            "UPDATE sucursales SET activa=? WHERE id=?", (int(activa), sucursal_id)
        )


def _verificar_baja_de_sucursal(conn, sucursal_id: int) -> None:
    """Se planta si la sucursal todavia tiene algo vivo colgando.

    ## Que se mira, y que NO

    🔴 **Las EXISTENCIAS, no el envase.** La guarda original contaba
    `locations WHERE active=1`, o sea depositos abiertos. Eso deja pasar el caso
    que el humano reporto el 2026-08-16: un deposito **desactivado con stock
    adentro** no lo veia, y dar de baja la sucursal volvia esas existencias
    invisibles sin que nadie las hubiera movido — que es exactamente lo que la
    guarda existia para impedir. Miraba el contenedor en vez del contenido.

    Se cuentan los pares (item, deposito) con saldo **distinto de cero**, y no
    la suma total: sumando todos los items juntos, un saldo negativo por un
    error de carga taparia uno positivo de otro producto. Y el `<> 0` en vez de
    `> 0` es a proposito — un stock negativo tampoco es "nada que mover": es un
    dato roto que conviene ver antes de cerrar la sucursal.

    **Los depositos activos se siguen mirando**, aunque esten vacios: un
    deposito abierto es un destino que las pantallas siguen ofreciendo, y
    dejarlo colgando de una sucursal dada de baja es la misma clase de
    inconsistencia.

    ⚠️ **La historia NO bloquea.** `sales`, `purchase_orders` e `item_prices`
    tambien tienen `branch_id`, y una sucursal que alguna vez vendio algo los va
    a tener para siempre: bloquear por eso haria imposible cerrar una sucursal,
    nunca. La baja es logica justamente para conservar esa historia — ver el
    docstring de `cambiar_estado_sucursal`.
    """
    problemas = []

    depositos = conn.execute(
        "SELECT COUNT(*) AS n FROM locations WHERE branch_id=? AND active=1",
        (sucursal_id,),
    ).fetchone()["n"]
    if depositos:
        problemas.append(f"{depositos} deposito(s) de stock activo(s)")

    con_saldo = conn.execute(
        "SELECT COUNT(*) AS n FROM ("
        "  SELECT sm.item_id, sm.location_id"
        "  FROM stock_movements sm"
        "  JOIN locations l ON l.id = sm.location_id"
        "  WHERE l.branch_id = ?"
        "  GROUP BY sm.item_id, sm.location_id"
        "  HAVING SUM(sm.quantity_delta) <> 0"
        ") x",
        (sucursal_id,),
    ).fetchone()["n"]
    if con_saldo:
        problemas.append(f"{con_saldo} producto(s) con existencias en sus depositos")

    if problemas:
        raise ValueError(
            "La sucursal todavia tiene " + " y ".join(problemas) + ". "
            "Transferi el stock a otra sucursal y desactiva los depositos antes "
            "de dar de baja la sucursal."
        )


def verificar_sucursal(conn, sucursal_id: int | None) -> None:
    """Rebota un `sucursal_id` que no existe o que esta dada de baja.

    Sin esto la falta de FK se paga en el alta: `locations.branch_id = 99`
    entra sin chistar y el deposito desaparece de toda pantalla filtrada.
    `None` es valido y significa "sin sucursal" --el caso de la empresa de un
    solo local, que es la mayoria--.
    """
    if sucursal_id is None:
        return
    fila = conn.execute(
        "SELECT activa FROM sucursales WHERE id=?", (sucursal_id,)
    ).fetchone()
    if fila is None:
        raise ValueError("La sucursal indicada no existe.")
    if not fila["activa"]:
        raise ValueError("La sucursal indicada esta dada de baja.")
