# Decisiones arquitectónicas — LibraDesk

Registro ADR. Las decisiones no se borran; si dejan de aplicar, se marcan como
reemplazadas. Fechas y motivos salen del código y de la historia registrada en el
wiki (entidad `libradesk`).

## ADR-001 — Reescribir como producto Libra nativo

- Estado: aceptada
- Fecha: 2026-07-29
- Reemplaza: "Soporte Neuroflow" (Node.js/Express + PostgreSQL, stack propio).
- Contexto: el sistema de soporte estaba fuera de la familia y no podía reusar sus
  motores transversales.
- Decisión: reescribirlo por completo sobre el stack de la familia (FastAPI +
  SQLAlchemy + React) y rebrandearlo a LibraDesk, para consumir LibraCore,
  LibraAuth y LibraCommerce.
- Consecuencias: LibraDesk comparte stack, motores y estándares con el resto de la
  familia; el historial Node.js queda como referencia en git (`docs/schema.sql`,
  no ejecutado).

## ADR-002 — Auth propio con LibraAuth, sin Google

- Estado: aceptada
- Fecha: 2026-07-29
- Reemplaza: login 100% Google OAuth y sincronización con Google Workspace
  (Contacts/Calendar/Tasks).
- Contexto: la versión anterior dependía de Google para el login y para espejar
  agenda/tareas/contactos, lo que ataba el producto a esa integración.
- Decisión: adoptar `libraauth` (usuario/contraseña con PBKDF2, sesión por cookie
  firmada) — LibraDesk es su primer consumidor — y eliminar el sync con Google.
- Consecuencias: login propio y sin dependencia de Google; Agenda y Tareas
  (espejos sin valor propio) se eliminaron; un reemplazo propietario del sync
  queda pendiente (hoy no existe).

## ADR-003 — Engine y session factory propios, una sola base compartida con LibraAuth

- Estado: aceptada
- Fecha: 2026-07-29
- Contexto: a diferencia de Gestiolibra, LibraDesk no depende de LibraGenda, así
  que no hereda su engine; y la tabla de usuarios de `libraauth` no debe vivir en
  una segunda base.
- Decisión: `app/database.py` define el engine/session factory propios; un solo
  engine sirve al dominio de LibraDesk (clientes/equipos/incidencias/…) y a la
  tabla `usuarios` de `libraauth`, en la misma base.
- Consecuencias: una sola base por instancia, sin segunda BD sólo para usuarios.

## ADR-004 — PostgreSQL y nada más, con guarda en el arranque

- Estado: aceptada
- Fecha: 2026-08-12 (corte del 2026-08-09/11)
- Contexto: una URL `sqlite://` levantaba la app sobre un motor donde las FK no se
  chequean y los tipos son dinámicos, así que los defectos que PostgreSQL rechaza
  de entrada pasaban desapercibidos hasta producción.
- Decisión: `app/database.py.configure()` **rechaza** cualquier destino que no sea
  PostgreSQL con un `ValueError` explícito, en vez de aceptarlo callado. La guarda
  vive en el arranque del producto, no en LibraCore (que sigue siendo neutral).
- Consecuencias: dev, tests y producción corren sobre el mismo motor; no hay
  rollback silencioso a SQLite.

## ADR-005 — Reusar el dominio de remitos/presupuestos de LibraCore, no reimplementarlo

- Estado: aceptada
- Fecha: 2026-07-30
- Contexto: LibraDesk necesita remitos y presupuestos con numeración y PDF, que ya
  existen como dominio en LibraCore.
- Decisión: consumir `libracore.db.remitos_presupuestos` (dominio completo),
  `libracore.pdf_generator` (`RemitoPDF`/`PresupuestoPDF`) y
  `libracore.config_manager` (datos del emisor), en vez de escribir lo propio.
- Consecuencias: numeración y PDF consistentes con la familia; los cambios del
  dominio se corrigen upstream.

## ADR-006 — Catálogo e inventario sobre LibraCommerce

- Estado: aceptada
- Fecha: 2026-08
- Contexto: el circuito comercial que creció en LibraDesk (insumos, contratos de
  proveedor, ventas) necesita catálogo e inventario, que son dominio de
  LibraCommerce.
- Decisión: consumir `libracommerce` (`db.repository`, `domain.catalog`,
  `usecases.inventory`) para esas piezas.
- Consecuencias: LibraDesk combina tres motores; es el producto que más mide el
  valor de la separación motor/producto.

## ADR-007 — Reportes XLSX con openpyxl, reconstruidos desde cero

- Estado: aceptada
- Fecha: 2026-08-24
- Contexto: LibraDesk necesita reportes analíticos exportables, sin precedente en
  la familia (Gestiolibra no exporta).
- Decisión: implementar la exportación XLSX con openpyxl (`reporte_xlsx`,
  `xlsx_helper`): 7 analíticos + 3 volcados planos.
- Consecuencias: capacidad propia de LibraDesk; si otro producto la necesita,
  habrá que evaluar subirla a un motor.

## ADR-008 — Gating por rol a nivel de router, no por endpoint

- Estado: aceptada
- Fecha: 2026-07-29
- Contexto: casi todos los endpoints de un recurso comparten el mismo requisito de
  rol; repetir la dependencia por endpoint es ruido y una fuente de olvidos.
- Decisión: aplicar el gating en `include_router(..., dependencies=[Depends(...)])`
  — `staff_or_admin` para el grueso, `require_admin` para usuarios y empresa —,
  mismo patrón que Gestiolibra.
- Consecuencias: el requisito de rol se lee en un lugar por recurso; un endpoint
  con requisito distinto es la excepción explícita.

## ADR-009 — Módulos premium habilitados por plan

- Estado: aceptada
- Fecha: 2026-08-24
- Contexto: no todos los clientes contratan todo (el circuito de insumos y
  contratos de proveedor es premium).
- Decisión: `plans.py` + `app/modules_gate.py` definen qué módulos habilita cada
  plan; los routers premium se gatean por módulo activo.
- Consecuencias: una instancia sirve sólo los módulos de su plan; el circuito de
  insumos y el de contratos de proveedor comparten módulo (sin consumibles el
  segundo no tiene para qué existir).

## ADR-010 — Deploy manual, sin CD automatizado

- Estado: aceptada
- Fecha: 2026-07-29
- Contexto: igual que Gestiolibra/MedLibra/VentaLibra, el deploy de LibraDesk es
  al VPS y no se justifica todavía un pipeline de CD.
- Decisión: deploy manual con `docker compose` (build de dos stages) para dev, y
  `scripts/panel_admin.py actualizar --ref main` para las instancias de cliente;
  el CI de GitHub Actions corre sólo tests.
- Consecuencias: el deploy es un paso humano verificable; el CI protege el merge,
  no el despliegue.

## ADR-011 — Los identificadores ajenos de un equipo no se gatean

- Estado: aceptada
- Fecha: 2026-08-24
- Contexto: el número que un proveedor le pone a una máquina es parte de la
  identidad del aparato; esconderlo detrás de un permiso rompe el flujo
  "me dicen que es la 4471, ¿cuál es?".
- Decisión: los identificadores ajenos de `equipos` no se gatean, y el listado
  acepta `?referencia=` para resolver por ese número.
- Consecuencias: la referencia del proveedor es consultable por quien atiende; no
  es dato sensible que ocultar.

## ADR-012 — LibraDesk corre también la cadena de migraciones del motor (`libracore-migrar`)

- Estado: aceptada. **Exige `libracore >= v1.142.1`** para una base sin depósitos (ver
  Consecuencias): hasta v1.142.0 el motor sembraba sobre la `depositos` de este producto.
- Fecha: 2026-10-07
- Contexto: el deploy declaraba `alembic`, `libracommerce-migrar` y `libraauth-migrar`,
  pero no `libracore-migrar`. Las bases de dev, demo, compulibra y lagrace no tenían la
  tabla de versión del motor (`alembic_version`) ni las tablas de las revisiones del motor
  posteriores a lo que LibraDesk copiaba a mano: `arca_credenciales_servicio` (0022),
  la pre factura (0021), el libro de terceros (0019), los cierres diarios (0009)... Medido
  el 2026-10-07: las cuatro bases tienen 82 tablas, ninguna con versión del motor.
  El ADR-005 y la página de migraciones del wiki habían dejado a LibraDesk «fuera del
  alcance del motor» cuando su `clients` tenía 19 columnas propias; desde la `0017` de este
  repo `clients` es la del motor y esa razón dejó de valer.
- Decisión: `("libracore-migrar", "upgrade", "--prefijo", "libradesk")` se declara en
  `scripts/panel_admin.py` y `scripts/nuevo_cliente.py` (lo que usan `actualizar`, el alta de
  un cliente y `reset_demo.sh`, que lee la lista de la imagen) y en el `command:` de `dev` del
  `docker-compose.yml`, **al final**: `alembic`, `libracommerce-migrar`, `libraauth-migrar`,
  `libracore-migrar`. Los composes de las instancias de cliente no listan migraciones (las
  corre el deploy con `compose run --rm`), así que no cambian. `libradesk` figura en
  `_UNA_SOLA_BASE` del motor, por eso `--prefijo libradesk` migra la base de `DATABASE_URL`.
- Por qué al final (medido, no supuesto): el motor antes de `alembic` crea `modulos`,
  `clients`, `depositos`, `proveedores`... y la `0001` de este repo muere con
  `DuplicateTable`; antes de `libraauth-migrar` crea una `usuarios` que es de libraauth.
  Respecto de `libracommerce-migrar` el orden es indiferente (se probaron los dos) y se dejó
  el que ya tienen las instancias.
- Consecuencias:
  - **Sobre una instancia viva** la cadena termina sin error y es idempotente. Copia de la
    demo (82 tablas, 372 filas): +19 tablas (18 del motor, todas vacías, y su
    `alembic_version`), 21 columnas de dinero de tablas ya existentes pasan de `double
    precision` a `numeric` (la lectura sigue devolviendo `float`), `facturas` +19 columnas,
    `cajas` +3, `ventas_pagos` +2, `caja_movimientos` +1, y las 368 filas comparadas
    (todas las que no son de las dos tablas sembradas) conservan sus valores. Lo único que cambia de conteo es lo que el motor siembra:
    `cajas` 0 -> 1 («Caja Principal») y `categorias_egreso` 4 -> 13 (visible en la pantalla de
    egresos).
  - 🔴 **Sobre una base SIN depósitos fallaba (libracore <= v1.142.0), resuelto en v1.142.1 (ADR-033 del motor)**: la baseline del motor siembra `Depósito
    Principal` con `INSERT INTO depositos (nombre, descripcion, es_default) VALUES (?,?,1)` y
    la `depositos` de este producto (propia, con `es_default` y `activo` BOOLEAN) lo rechaza
    (`column "es_default" is of type boolean but expression is of type integer`). Hoy las
    cuatro bases tienen depósitos (1 a 4), así que el deploy sobre ellas anda, pero quedan
    rotos los tres caminos que parten de una base sin depósitos y corren las cadenas
    declaradas: **el alta de un cliente nuevo**, **el reset nocturno de la demo** (`DROP
    SCHEMA` + las cadenas) y **restaurar un backup** desde la pantalla de Backups
    (`libracore.respaldo_postgres.correr_migraciones`; `tests/test_config_backup.py::
    test_crear_listar_y_restaurar` queda en rojo, y el smoke de navegador también). La falla es transaccional: no deja nada a medias. El arreglo
    de fondo es del motor (que no siembre sobre una `depositos` que no es la suya), no de este
    producto: v1.142.1 sólo siembra si `depositos.es_default` es entera, así que una base nueva
    de LibraDesk nace **sin depósitos** (como antes de este ADR) y su pantalla los crea.
    `test_sobre_una_base_vacia_la_cadena_entera_termina_sin_error` lo fija y ya no es `xfail`:
    queda rojo con un pin menor a v1.142.1.
  - En una base nueva `remitos` y `presupuestos` los crea el motor (con la FK `client_id ->
    clients` y `status` por defecto `pendiente`) en vez de la copia de `rp_service`: la FK es
    inocua (`ON DELETE SET NULL`) y el default no se usa (el alta pasa el estado).

## ADR-013 — El CRUD de clientes pasa por `libracore.db.clients` y `Cliente` es de solo lectura

- Estado: aceptada. **Exige `libracore >= v1.157.0` y `libraauth >= v0.49.0`** (la v1.156.0 es un tag erróneo: no usarla).
- Fecha: 2026-10-12
- Contexto: desde la revisión `0017` (2026-08-12) `clients` es la tabla del motor, pero este producto la escribía por su ORM a propósito: el log de actividad de `libraauth` colgaba del `flush` de la sesión, y `libracore.db.clients` escribe por una conexión DB-API cruda, así que adoptarlo dejaba las altas, ediciones y bajas **sin auditar y sin que nadie se enterara** (la nota de `ClienteRepository`, y `test_el_alta_de_un_cliente_sigue_quedando_en_el_log_de_actividad` que lo vigila). El costo: LibraDesk era el único producto que no usaba el CRUD del motor (ni su espejo en `parties`, ni el asiento al libro, ni el bloqueo de borrado con remitos). El dueño decidió el 2026-10-12 que la auditoría de escrituras viva en el motor (ADR-043 de libracore, ADR-022 de libraauth) y que LibraDesk lo adopte sin perder el log ni cambiar la pantalla.
- Qué ya existía (se miró antes): `libracore.auditoria` y `crear_cliente`/`actualizar_cliente` (ADR-043 del motor), `registrador_dbapi` (ADR-022 de libraauth) y `validar_cuit_no_duplicado`, que este repo ya usaba.
- Decisión:
  - **Las escrituras van por el motor**: `ClienteRepository.create` → `crear_cliente`, `update` → `actualizar_cliente`, `set_activo` → `activar_cliente`/`desactivar_cliente`, `delete` → `delete_client`. Se usan `crear_cliente`/`actualizar_cliente` y **no** `create_client`/`update_client` porque escriben exactamente las claves recibidas: `None` es `NULL` (vaciar un campo desde la pantalla lo vacía; `update_client` lo toma por «no tocar» y convierte `NULL` en `""`) y aceptan la columna propia `price_list_id`. El mapa atributo de la API → columna se **deriva** de `inspect(Cliente).column_attrs` (`columnas_por_atributo`), no se escribe a mano.
  - **`Cliente` queda como mapeo de solo lectura** (siete FK y unos veinticinco joins lo necesitan). Una guarda `before_flush` a nivel de `Session` levanta `RuntimeError` si un `Cliente` aparece en `new`, `dirty` (con cambios reales de columna) o `deleted`: escribirlo por la sesión seguiría andando pero sin dejar fila en el log, y eso no puede pasar callado.
  - **La auditoría de clientes pasa al camino del motor**: `Cliente` sale de `AUDITABLES` (con las dos cosas, cada cambio dejaría dos filas) y `create_app` enchufa `libracore.auditoria.configurar_auditoria(registrador_del_motor())` después de crear `actividad_log` y de configurar la conexión del motor (misma base: LibraDesk lleva todo en una). El registrador es el `registrador_dbapi({"clients": "cliente"}, atributos=<columna → atributo, derivado del modelo>)`: la columna `name` se muestra `nombre`. Sin `columnas_ocultas` propias: el ORM tampoco las tenía. Un wrapper pone las claves del diff en **el orden del modelo**, que es el que tenía el log del `flush` (el motor entrega la fila en el orden de la tabla de cada instancia). El filtro de entidades de `/api/logs` sigue ofreciendo `cliente` (`ENTIDADES_DEL_LOG`).
  - **Es transaccional**: el INSERT del log va en la misma transacción que la escritura (ADR-043 del motor). Un log roto (tabla ausente) bloquea las altas y ediciones de clientes en vez de perderse en silencio.
  - **Borrar un cliente con remitos o presupuestos es un 409 nuevo** con el mensaje del motor («El cliente tiene 2 remito(s) y 1 presupuesto(s) asociado(s) y no puede eliminarse. Desactivalo en vez de borrarlo.»). Antes el `DELETE` por la sesión no miraba los remitos ni los presupuestos: la FK es `ON DELETE SET NULL`, así que los dejaba sin cliente en silencio. `ClienteRepository.dependencias` sigue contando lo propio de LibraDesk (equipos, reclamos, sectores, contratos, depósitos, comprobantes de ingreso). El frontend no llama al `DELETE` (los clientes se desactivan), así que no cambia.
  - **El 409 del email duplicado** atrapa `sqlite3.IntegrityError`: la capa dual del motor traduce la violación del `UNIQUE` de psycopg a la clase de `sqlite3`, ya no llega la de SQLAlchemy.
- Diferencias observables (fijadas por `tests/test_auditoria_de_clientes_pantalla_identica.py`, que corre el guion alta → edición → edición sin cambios → vaciar un campo → desactivar → activar → borrar contra el código anterior y contra este): **ninguna en la pantalla de Logs** (mismas filas, mismas descripciones, mismo diff y mismo orden de claves; `activo` sigue siendo `[1, 0]` porque la columna es entera y el ORM también lo registraba así). Fuera de la pantalla:
  - el alta y la edición **mantienen el `parties` espejo y el libro de clientes** en la misma transacción (antes el cliente nuevo no se podía vender hasta el próximo arranque, que lo adoptaba con `sincronizar_parties`);
  - el espejo del motor deja `legal_name` en `NULL` y `tax_id` en `NULL` cuando el CUIT está vacío (el de `sincronizar_parties` los llena con el nombre y `''`).
- Consecuencias:
  - Sin migración. El pin sube a libracore v1.157.0 (desde v1.155.0) y libraauth v0.49.0.
  - Una columna nueva de `clients` en el motor entra sola a `crear_cliente`/`actualizar_cliente`, pero hay que declararla en `Cliente` (si no, `test_cliente_describe_la_tabla_del_motor` se pone rojo, que es su trabajo).
  - Los tests que construyen la app limpian el registrador (`configurar_auditoria(None)`, fixture autouse del `conftest`), que es un global del proceso.


## ADR-014 — Varios procesos listos (`WEB_CONCURRENCY`, hoy 1) y el registro de errores de la familia

- Estado: aceptada. **Exige `libracore >= v1.159.0`, `libraauth >= v0.50.0` (con migración `0003_captcha_usados`) y `libra-ui >= v0.142.1`.**
- Fecha: 2026-10-13
- Contexto: el dueño decidió (2026-10-13) dejar el código listo para correr con `uvicorn --workers N` **sin prender más workers todavía**: todo sigue en 1 (ADR-044 de libracore, `docs/varios-procesos.md`). Y (2026-10-12) que la familia tenga un registro de errores propio (ADR-045 de libracore, ADR-053 de libra-ui): hasta ahora un 500 iba al stdout de uvicorn y se perdía en cada recreate del contenedor.
- Qué ya existía (se miró antes): `docs/varios-procesos.md` y `docs/errores.md` del motor, ADR-023 de libraauth (captcha en la base), el `pool_pre_ping` de este producto. `pool_pre_ping=True` ya estaba (`app/database.py`).
- Decisión:
  - **Siembras de arranque serializadas.** `ensure_default_admin`, `ensure_demo_user` y `ModuleRepository.ensure_seeded` (`app/main.py`) corren adentro de `una_vez_al_arrancar("libradesk-sembrar")`; cada uno sigue preguntando adentro.
  - **Captcha en la base.** `app/routers/auth.py`: `captcha_usados=UsadosEnBase(lambda: get_session_factory()())` (la fábrica se resuelve en cada uso: el módulo se importa antes de que `create_app()` arme el engine).
  - **Nota de crédito.** No emite notas de crédito: no aplica.
  - **Registro de errores.** Backend: `instalar_registro_de_errores(app, "libradesk")` al lado de `SecurityHeadersMiddleware`, que monta `POST /api/errores-cliente`. Frontend: `instalarReporteDeErrores()` antes de montar y `<ErrorBoundary>` alrededor de todo en `main.tsx`. Compose de `-dev`: `LIBRA_ENTORNO=dev`, `LIBRA_INSTANCIA=libradesk-dev`, `LIBRA_VERSION=${LIBRA_VERSION:-dev}`; las instancias de cliente y demo las escribe el panel.
  - **Compose de `-dev`**: `exec uvicorn ... --workers ${WEB_CONCURRENCY:-1}`. `uvicorn>=0.30` ya era el piso.
- Consecuencias:
  - **La migración `0003` de libraauth corre antes de uvicorn** en todo camino de arranque (la cadena de `scripts/panel_admin.py` y el `command:` del compose ya incluyen `libraauth-migrar upgrade`): `exigir_schema_al_dia` hace que el producto no arranque sin ella, aunque no use `UsadosEnBase`.
  - Sin migración propia. Con más de un worker, después de un restore en caliente hay que **reiniciar el contenedor** (`docs/varios-procesos.md` del motor).
  - Las serializaciones del arranque cubren las siembras («si no existe, crear»); la creación idempotente del esquema (`CREATE TABLE IF NOT EXISTS` de `ensure_schema`) no se serializa: antes de subir `WEB_CONCURRENCY` a más de 1 hay que medirlo con dos workers.
  - Tests: `tests/test_registro_de_errores.py`, `tests/test_arranque_varios_procesos.py` y el caso de `captcha_usados` en `tests/test_captcha_login.py`; los dobles del captcha de los `conftest` aceptan el segundo argumento que libraauth v0.50.0 pasa a `_captcha_de(request, usados)`.

## ADR-015 — Una base nueva repunta `ventas_pagos` a `sales` en el arranque (`repuntar_fk_ventas_pagos`)

- Estado: aceptada. Sin cambio de pin (`libracommerce` v0.16.4 ya trae `repuntar_fk_ventas_pagos`).
- Fecha: 2026-10-15
- Contexto: el reset nocturno de la demo (`DROP SCHEMA` + `alembic`, `libracommerce-migrar`, `libraauth-migrar`, `libracore-migrar` + el contenedor + `seed_demo.py`) moría en `POST /api/ventas` con 500: `ForeignKeyViolation: ... ventas_pagos_venta_id_fkey ... Key (venta_id)=(N) is not present in table "ventas"`. Medido en el VPS: las bases de lagrace, compulibra y dev tenían la FK contra `sales`; la demo, recreada de cero, contra `ventas` (la tabla legada del motor, vacía).
- Causa (medida reproduciendo la secuencia en una base vacía): LibraDesk vende por `sales` (LibraCommerce) y sus pagos cuelgan de `sales`. Antes del ADR-012 la primera en crear `ventas_pagos` era `comercial.ensure_schema()` (`CREATE TABLE IF NOT EXISTS`, FK a `sales`). Desde el ADR-012 (2026-10-07) la cadena `libracore-migrar` corre **antes** de que arranque la app y su baseline (`init_core_schema()`) crea `ventas_pagos` con la FK a `ventas`; el `IF NOT EXISTS` del producto ya no hace nada y nadie repuntaba. Las bases que existían antes del ADR-012 conservaron la FK buena. Afecta a toda base que nace de cero: la demo cada noche, el alta de un cliente (`nuevo_cliente`) y el restore de un backup. La suite no lo veía porque la plantilla de `tests/conftest.py` arma la base con el arranque solo, sin `libracore-migrar`.
- Qué ya existía: la costura del motor. `libracommerce.erp.ventas.repuntar_fk_ventas_pagos(conn)` (idempotente, PostgreSQL y SQLite) la llaman Contalibra, Restolibra y VentaLibra en su `init_db`. El arreglo de fondo ya vive en el motor; al producto le faltaba usarlo.
- Decisión: `comercial.ensure_schema()` llama a `repuntar_fk_ventas_pagos(conn)` después de crear las tablas. No hace nada si la FK ya apunta a `sales` (instancias vivas, arranque sin cadena del motor), así que las bases existentes no se tocan. No se agrega migración de Alembic: la cadena del motor es dueña de la creación de la tabla y el repunte es del arranque, igual que en los otros tres productos.
- Consecuencias:
  - **Al desplegar no hace falta nada más que el deploy normal**: la demo se recrea sola a las 04:45 y el arranque del contenedor ya repunta. Una demo recreada **antes** de este deploy y que siga viva conserva la FK mala hasta que arranque el contenedor nuevo (el repunte corre en cada arranque; con la tabla vacía no hay filas huérfanas).
  - `tests/test_base_nueva_del_deploy.py` corre la secuencia real del deploy sobre una base vacía: la FK apunta a `sales`, `POST /api/ventas` con un pago entra (201) y las FK de una base nueva coinciden con las de una migrada. Los tres quedan en rojo sin el cambio.
  - 🔴 **Pendiente, no resuelto acá**: ese mismo orden deja en una base nueva seis FK que una migrada no tiene (`cc_debitos.cliente_id` y `cc_pagos.cliente_id` a `clients` con `ON DELETE CASCADE`, `recibos.cliente_id`, `remitos.client_id` y `presupuestos.client_id` a `clients` con `SET NULL`, `egresos.proveedor_id` a `proveedores`), y el `DEFAULT` de `presupuestos.status` (`'pendiente'` contra `'borrador'`). Contradicen la regla de `app/services/comercial.py` («el DDL crudo no referencia tablas de Alembic»). El test las lista como conocidas (`_DIFERENCIAS_CONOCIDAS`) para que una diferencia nueva lo ponga en rojo. Hay que decidir si se sacan (arreglo de fondo en el motor: que la baseline no cree FK hacia tablas que el producto declara propias) o se aceptan por escrito.
