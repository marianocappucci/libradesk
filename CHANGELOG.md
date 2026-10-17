# Changelog — LibraDesk

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

> LibraDesk todavía **no publica versiones semver** (el `pyproject.toml` está en
> `0.1.0` y no hay tags de release): se despliega por promoción `develop`→`main`,
> no por tag. Este changelog registra los hitos por **fecha**, más reciente
> primero, reconstruidos de la historia registrada en el wiki (entidad
> `libradesk`) y verificados contra el código. Cuando se adopte versionado semver,
> los hitos de aquí en más se agruparán bajo su versión.

## [Sin versionar] — hitos por fecha

### 2026-10-17
- **Cambiado:** el alta de cliente en el lugar de las pantallas que emiten algo fiscal (Presupuestos, Remitos, venta nueva, remito de venta, contratos y contratos de proveedor) pide además **CUIT y condición frente al IVA** (`ALTA_FISCAL`). Lo habilita libra-ui `v0.158.2` (ADR-072 del kit), que deja de ofrecer «IVA No Responsable», una condición que este backend no conoce; `src/test/alta-de-cliente.test.ts` vigila que las condiciones del kit sean las de `app/services/iva.py`.

### 2026-10-16
- **Agregado:** **todo campo donde se elige un cliente ofrece darlo de alta ahí mismo** (ADR-017; libra-ui `v0.158.1`, ADR-071 del kit). En la recepción de equipos, si quien llega con el equipo no está cargado, ya no hay que cancelar la recepción e ir a Clientes: el botón «Agregar nuevo cliente» al lado del buscador abre el alta (nombre, teléfono y email), crea el cliente por `POST /api/clientes`, lo deja elegido y precarga el teléfono de contacto. Lo mismo en Presupuestos y Remitos, la venta nueva y el remito de una venta de mostrador, el contrato nuevo, los contratos de proveedor, los depósitos de cliente, Equipos, y el alta y la ficha de una incidencia. Un solo `crearClienteEn` (`src/lib/alta-de-cliente.ts`) arma el payload. Los filtros de los listados y de los reportes no crean nada y quedan marcados con `cliente-sin-alta: <motivo>`. `src/test/campos-de-cliente.test.ts` (la guarda, que lee los fuentes) y el caso de alta en `src/test/recepciones.test.tsx`.
- **Cambiado:** pin de libracommerce `v0.16.4` -> `v0.63.0` (47 versiones). **Migraciones del motor `0002` a `0007`** (`libracommerce-migrar upgrade --prefijo libradesk`, ya en la cadena del deploy): todas aditivas, sin tocar una fila (columnas `catalog_items.tracks_expiry/lead_time_days/max_stock/supplier_party_id`, `purchase_receipts.clave_operacion`, un índice en `stock_movements` y las tablas vacías `item_branch_min_stock` y `sale_service_returns`); el arranque suma la tabla vacía `branches`. **Conducta que cambia (ADR-051 del motor):** el depósito por defecto no se puede desactivar (422) y una venta, una recepción de compra o una transferencia que usan un depósito inexistente o dado de baja se rechazan antes de escribir (422); antes entraban. Las pantallas de Ventas y Compras ya ofrecían sólo depósitos activos. `tests/test_deposito_activo_del_motor.py` (en rojo con `v0.16.4`); `tests/test_sucursales.py` pasa a dejar como depósito por defecto el de Mercedes, porque sus tests desactivan el de Chivilcoy. Lo demás que trae el motor (vencimientos y lotes, reposición, devoluciones, `exigir_cliente_para_fiar`, `validar_precios`) vive en su capa `erp`/`web`, que este producto no monta.
- **Agregado:** **filtro por estado en Equipos** (Mesa de ayuda → Equipos), combinable con el de cliente y resuelto por el backend (`GET /api/equipos?estado=`). Es la sección del parque de los clientes que se clickea y abre la ficha con el historial; antes «qué tengo en reparación» sólo se veía en el reporte de Equipamiento, que no se clickea. `tests/test_equipos_filtro_estado.py`.
- **Cambiado:** **el estado va en la pastilla de la suite (`BadgeEstado`) en los reportes**, con el mismo tono que en las pantallas, y la celda ya no lleva el fondo pintado (equipamiento, garantías, reclamos, facturación e insumos). La vista manda `tono` por celda de estado; el Excel no cambia (sigue usando `marca`). Y un solo mapa de tonos del equipo, `ESTADO_EQUIPO_TONO`: activo ok, en reparación atención, en depósito en curso, baja neutro (antes todo lo que no era «activo» salía gris, en la lista, la ficha y el depósito).
- **Cambiado:** pines a libracore `v1.173.0` (antes `v1.170.0`) y libra-ui `v0.156.0` (antes `v0.153.0`); libracommerce **no se sube** (sigue en `v0.16.4`) y libraauth sigue en `v0.51.0`. **Sin migración.** libracore `v1.171.0` (ADR-058): no se puede cobrar de más una factura (409). `v1.172.0` (ADR-059 y ADR-060): las notas de crédito restan de lo pendiente (el resumen y el tablero cuentan también las facturas cobradas a medias por lo que falta) y cobro por turno. `v1.173.0` (ADR-061): una demo no habla con ARCA ni muestra datos fiscales reales (`libracore.demo`). libra-ui `v0.154.0` a `v0.156.0`: sin desbordes a 390 px y contraste AA (ADR-067), «pendiente» y «Acreditada» en las facturas con nota de crédito (ADR-068) y el enlace al tutorial de Padrón A13 (ADR-069). Verificado: `tests/test_base_nueva_del_deploy.py` y los tests de clientes siguen verdes con la `v1.173.0`.
- **Agregado:** tests de la semilla de la demo con `libracore.demo` (`tests/test_seed_corre.py`): ni un CUIT de forma real en el texto de la semilla ni datos fiscales reales en la base sembrada.

### 2026-10-15
- **Cambiado:** pines a libracore `v1.170.0` (`soltar_fk`, y `delete_client` bloquea la baja de un cliente con cuenta corriente, ADR-057), libraauth `v0.51.0` (aceptar los Términos 1.1 por adelantado) y libra-ui `v0.153.0` (aviso no bloqueante «Aceptar / Más tarde»).
- **Corregido:** **una base nueva ya no queda con seis FK y un `DEFAULT` que una migrada no tiene** (ADR-016; exige libracore `v1.169.0`). La baseline del motor crea `cc_debitos`, `cc_pagos`, `recibos`, `remitos`, `presupuestos` y `egresos` con FK hacia `clients`/`proveedores` (las dos de cuenta corriente con `ON DELETE CASCADE`: borrar un cliente se llevaba sus movimientos) y `presupuestos.status` en `'pendiente'`. El arranque las suelta con `soltar_fk()` del motor y alinea el `DEFAULT` a `'borrador'`; idempotente, sin tocar filas, sin migración. Las bases vivas (dev, Compulibra, LaGrace) no cambian. `tests/test_base_nueva_del_deploy.py` compara ahora el schema completo.
- **Corregido:** **una base nueva dejaba `ventas_pagos` apuntando a la tabla `ventas` legada del motor** (ADR-015). Desde el ADR-012 la cadena `libracore-migrar` corre antes del arranque y su baseline crea `ventas_pagos` con la FK a `ventas`; el `CREATE TABLE IF NOT EXISTS` de `comercial.py` ya no la creaba y nadie la repuntaba a `sales`. Efecto: el reset nocturno de la demo, el alta de un cliente y el restore de un backup dejaban una base donde `POST /api/ventas` con un pago devolvía 500 (`ForeignKeyViolation`). `comercial.ensure_schema()` llama ahora a `repuntar_fk_ventas_pagos()` de LibraCommerce (idempotente: las instancias vivas ya la tienen en `sales` y no se tocan). Sin migración ni cambio de pin.

### 2026-10-13
- **Cambiado:** **varios procesos listos (todo sigue en 1) y registro de errores** (2026-10-13, ADR-014; libracore `v1.159.0`, libraauth `v0.50.0`, libra-ui `v0.142.1`). Las siembras de arranque corren serializadas (`una_vez_al_arrancar`), el captcha anota los desafíos usados en la base (`UsadosEnBase`), el compose de `-dev` acepta `WEB_CONCURRENCY` (por defecto 1) y un 500 deja una línea en `errores/errores.jsonl` con un `ref` que ve el usuario (la pantalla «Algo falló» de libra-ui lo muestra). **Con migración de libraauth** (`0003_captcha_usados`), que corre antes de uvicorn. Sin migración propia.

### 2026-10-12
- **Cambiado:** **el CRUD de clientes pasa por `libracore.db.clients` y la auditoría de escrituras vive en el motor** (ADR-013; libracore `v1.157.0`, libraauth `v0.49.0`). `ClienteRepository` escribe con `crear_cliente`/`actualizar_cliente`/`activar_cliente`/`desactivar_cliente`/`delete_client` y `Cliente` queda como mapeo de **sólo lectura** (una guarda `before_flush` levanta si se lo escribe por la sesión). El log de actividad lo escribe el `registrador_dbapi` de libraauth que el motor llama dentro de la misma transacción: **la pantalla de Logs es la misma** (mismas filas y mismo diff; un test corre el guion alta → edición → vaciar un campo → desactivar → activar → borrar contra el código anterior y el nuevo). Vaciar un campo desde la pantalla sigue guardando `NULL`. **Nuevo 409** al borrar un cliente con remitos o presupuestos (el bloqueo es del motor). El alta y la edición ahora mantienen solos el `parties` espejo y el libro de clientes. Sin migración.
- **Retirado:** **los restos del resumen de cuenta corriente por mail** (ADR-042 de libracore). Revisión `0042_retirar_cc_resumen`: borra la tabla `cc_resumenes_enviados` (la creaba `comercial.ensure_schema()`) y las columnas `clients.cc_resumen_auto`, `cc_resumen_frecuencia` y `cc_resumen_ultimo_envio` (las trajo la `0017`); el modelo `Cliente` y el DDL copiado de `comercial.py` dejan de declararlas. **Borra datos** (el historial de envíos; se espera vacío) y se baja devolviendo las columnas vacías. Idempotente (`IF EXISTS`) y convive con la `0024` del motor en cualquier orden. No depende del pin de libracore: este producto escribe sus clientes por SQLAlchemy y no llama al `update_client` del motor.

### 2026-10-07
- **Cambiado:** **los íconos del menú y de los títulos son los del catálogo de la familia: `libra-ui` v0.125.0** (antes v0.123.0; ADR-035 del kit). Un concepto lleva un solo ícono en todos los productos. En LibraDesk cambian: Cuenta corriente (de `Wallet` a `BookOpen`), Recibos (de `Coins` a `ReceiptText`), Presupuestos (de `FileText` a `Calculator`), Remitos (de `Receipt` a `FileText`), Órdenes de compra (de `ShoppingCart` a `ShoppingBasket`), Egresos (de `Wallet` a `ShoppingBag`), Stock (de `PackageSearch` a `Boxes`), Depósitos de stock (de `Boxes` a `Warehouse`, porque `Boxes` es de Stock), Ventas (de `ClipboardList` a `ShoppingCart`) y Reportes (de `FileSpreadsheet` a `ChartColumn`). Cuotas deja `ReceiptText`, que ahora es de Recibos, por `CalendarRange`. Usuarios, Logs y Configuración dejan de pasar su ícono y toman el del kit. Un test nuevo (`iconos-del-catalogo.test.ts`) falla si una entrada del menú usa otro ícono que el de su concepto. El salto trae también v0.124.0 (ADR-034): la marca de cada producto es un dibujo propio y el favicon se reduce a una pieza, sin tocar código (el Login pasa de 40 a 48 px y el test de identidad lo mide así). Sin migración.

### 2026-10-05
- **Cambiado:** **libracore `v1.141.0`** (2026-10-06; antes `v1.140.0`). El emisor de los PDF se resuelve por documento (ADR-031 del motor): config de la instancia, después el `emisor_id` del comprobante, después lo que aporte el producto; acepta el logo como contenido (`logo_bytes`). El archivo de la factura lleva el id, así una nota de crédito no pisa a su factura. Sin migración; para quien no aporta nada, los PDF salen iguales.
- **Cambiado:** **libracore `v1.140.0`** (2026-10-06; antes `v1.139.0`). Suma la pre factura del motor (ADR-030): documento no fiscal con número interno, PDF y envío por correo, sobre la bandeja de comprobantes. **Con migración del motor**: `0021_pre_factura`, que agrega columnas vacías a `comprobantes_pendientes`. La bandeja de siempre no cambia.
- **Cambiado:** **libracore `v1.139.0`** (2026-10-06; antes `v1.138.0`). La cuenta corriente de clientes se lee **sólo** del libro (ADR-029 del motor): se retiran el saldo calculado y el interruptor `LIBRACORE_CC_DESDE_EL_LIBRO`. Sin migración. Lo cargado por fuera de los escritores del motor se ve después de `libro_de_clientes.reconstruir()`.
- **Cambiado:** **libracore `v1.138.0`** (2026-10-06; antes `v1.137.1`). Las lecturas de la cuenta corriente de clientes pueden salir del libro (ADR-028 del motor), detrás del interruptor por instancia `LIBRACORE_CC_DESDE_EL_LIBRO`, **apagado por defecto**: sin encenderlo no cambia nada. Sin migración.
- **Cambiado:** **libracore `v1.137.1`** (2026-10-06; antes `v1.136.1`). La cuenta corriente de clientes también como libro, **en sombra** (`libracore.db.libro_de_clientes`, ADR-027 del motor): los escritores del motor asientan cada pago, débito, cobro a cuenta y venta fiada en `cc_asientos`, y el saldo se sigue leyendo calculado. **Con migración del motor**: `0020_origen_del_asiento`, que agrega una columna vacía. La `v1.137.1` no rompe una base sin `cc_asientos`. LibraDesk suma `cc_asientos` a su copia del DDL del motor (`services/comercial.py`), registra su origen de ventas (`sales`) para el libro y le avisa de cada pago fiado que inserta (`services/ventas.py`).
- **Cambiado:** **libracore `v1.136.1`** (2026-10-06; antes `v1.135.0`). Suma el libro de cuenta corriente de terceros, opcional (`cc_asientos` y `libracore.db.libro_de_terceros`, ADR-026 del motor). **Con migración del motor**: `0019_libro_de_terceros`, que crea una tabla vacía y deja `cc_asientos.created_at` y `cierres_diarios.created_at` en hora de Argentina. Este producto no lo usa: su comportamiento no cambia.

- **Cambiado:** **libracore `v1.135.0`** (2026-10-05; antes `v1.134.0`). Las funciones del comprobante aceptan `conn=` para emitir dentro de la transacción del producto (ADR-025 del motor; sin `conn`, nada cambia) y el dinero del motor se guarda exacto en PostgreSQL (ADR-024): **migración `0018` del motor**, que pasa 33 columnas de dinero de `DOUBLE PRECISION` a `NUMERIC` sin redondear. La lectura sigue siendo `float`: el comportamiento de este producto no cambia. LibraDesk no corre el core del motor (`init_core_schema`), así que la 0018 no le llega.

- **Cambiado:** **libracore `v1.134.0`** (2026-10-05; antes `v1.132.0`). Trae el emisor opcional de cada comprobante (`facturas.emisor_id`, ADR-021 del motor), la anulación con rastro de un comprobante sin CAE (`POST /api/facturas/{id}/anular`, ADR-022) y el registro con número tipeado (ADR-023); incluye v1.133.0 (`libracore.spa`, la SPA del motor, que este producto no adopta todavía). **Con migración del motor**: `0016` y `0017` (columnas nuevas en `facturas` y el índice de numeración por emisor y ambiente); las aplica el arranque (`init_core_schema`) y `alembic upgrade head`. Para este producto no cambia el comportamiento: no pasa emisor.

- **Cambiado:** **libracore `v1.132.0`** (2026-10-05; antes `v1.131.0`). Suma `libracore.arca_wsfecred` (consultas al registro de FCE de ARCA) y `GET /api/facturas/fce/corresponde` (¿a esta factura le corresponde ser FCE?, para avisar antes de emitir; ADR-019 del motor). Nada cambia en la emisión. Sin migración.
- **Corregido (tests):** la suite **ya no deja bases en el servidor** ni corre contra el PostgreSQL de una instancia. `test_alembic`, `test_healthcheck_contenedor` y el test del restore borran al terminar las bases que crean (`_borrar_base`, con `WITH (FORCE)` y verificando que no quede). El `conftest` **se niega a arrancar** si `LIBRADESK_SUITE_POSTGRES_URL` apunta a un host `libradesk-*` (los sidecars de dev, demo y clientes). Motivo: el 2026-08-12 la suite corrió contra `libradesk-demo-db` y dejó 18 bases, una con datos reales de un cliente de La Grace; se encontraron y borraron el 2026-10-05.
- **Cambiado:** **libracore `v1.131.0`** (2026-10-05; antes `v1.127.0`). Trae la **nota de crédito parcial** con tope acumulado (v1.130.0: `{"importe": ...}` en `POST /api/facturas/{id}/nota-credito`; sin él, la total de siempre), la marca de cada nota en la cuenta corriente (v1.128.0), `build_nota_de_credito_router` (v1.129.0) y la nota total de una FCE frenada antes de ir a ARCA (v1.131.0). Cambia sólo `notas_de_credito` y `facturas_router`. Sin migración.

### 2026-09-10
- **Agregado:** cuando SOS **confirma** que un comprobante mandado ya no está, la
  deuda que había cargado en cuenta corriente **se anula sola**, con un débito
  negativo que dice de qué comprobante es (no un pago: de un pago se emite
  recibo). Si se vuelve a mandar, se carga de nuevo. Nada se borra: el libro del
  comprobante muestra cargo, anulación y cargo nuevo, y la idempotencia pasó de
  "ya hay una fila con esta referencia" al **neto** de todas. Las marcas
  anteriores se ajustan en la próxima consulta de estado. Hasta hoy eso se
  revertía a mano (decisión del 2026-08-13, cambiada con el humano).
- **Corregido:** un remito cuya venta se borró en SOS Contador **no se podía
  volver a mandar**, aunque el checkbox dejara. SOS quema el `uniqueid` aunque
  la venta se borre, así que el reenvío volvía `-1` y quedaba "Resuelto allá",
  en verde, sin haber llegado. Ahora el envío lleva un `intento`
  (`envios_facturacion.intento`, revisión `0041`) que entra en el `uniqueid`
  desde el 1; el 0 es el de siempre. Antes de estrenar uno nuevo **se le
  pregunta a SOS**: si la venta sigue allá no se manda (sería duplicarla), y si
  no se puede preguntar tampoco.
- **Cambiado:** "Falló" y "Ya no está allá" dejan de quedar para siempre en la
  columna Envío. Se muestran cuando pasan —en los resultados al enviar, en "En
  el contador" al consultar— y después la fila vuelve a "—", como un remito
  para mandar. La consulta ya no vuelve a preguntar por lo que SOS confirmó
  borrado.
- **Corregido:** "Consultar estado en el contador" dejaba filas en "No se pudo
  preguntar" que se resolvían apretando de nuevo. `GET /venta/detalle` de SOS es
  intermitente —el mismo id cortó a los 15,5 s y contestó bien a los 3,7 s—, así
  que ahora se pregunta **dos veces** antes de rendirse. Sólo se reintenta lo que
  no dice nada (un error o un corte); una respuesta, incluida "ya no está", no.
  Y la consulta entera tiene un **tope de 40 s**: el proxy corta a los 90 y, con
  SOS lento, tres filas reintentadas eran 120 s. Las filas que no llegan a
  consultarse lo dicen ("No se llegó a consultar") y no se tocan.
- **Corregido:** lo de abajo no llegaba a dispararse en producción. SOS no dice
  "no existe" en ningún idioma — contesta *"Error: Imposible cargar detalles de
  la venta"*—, así que los remitos con la venta borrada seguían mostrando "No se
  pudo preguntar". Se agregó el texto real, medido con un par de controles (una
  venta viva devuelve `cabecera`; un id inventado devuelve ese mismo error).

### 2026-09-09
- **Corregido:** en "Enviar a facturar", un remito cuya venta se borró o anuló
  en SOS Contador quedaba en **"En la bandeja" para siempre**, y al consultar
  decía sólo *"No se pudo leer"* — el mismo cartel que un SOS caído. Ahora la
  consulta distingue *SOS contestó que no está* de *no pude preguntarle a SOS*,
  y en el primer caso **escribe de vuelta** el estado del envío
  (`ausente_remoto`, "Ya no está allá"). `/api/facturacion/estados-sos` pasa de
  `GET` a `POST` porque, además de leer, reconcilia.
- **Corregido:** el add-on `modo_simple` no se podía administrar desde el
  backoffice. `app/database.py` no exportaba `get_modulos` ni `set_addon` —el
  contrato que el backoffice invoca por `docker exec`— así que la lectura moría
  con `ImportError` y la pantalla mostraba el add-on **destildado en una
  instancia que lo tenía prendido** (`lagrace`, con `modo_simple = true` en su
  base). Adentro de la app el add-on siempre funcionó bien; lo que estaba roto
  era administrarlo. Los dos shims delegan en `libracore.db.modulos`.

### 2026-08-31
- **Añadido:** mover un equipo del depósito a un sector del cliente, e instalar un
  equipo en un sector lo deja activo (PR #294, #296, #297).

### 2026-08-29
- **Corregido:** los `created_at` dejaban de estampar UTC y pasan a hora local
  Argentina.

### 2026-08-25
- **Corregido:** un `entrypoint:` mal definido dejaba `libradesk-dev` en
  crash loop.

### 2026-08-24
- **Añadido:** módulo de **insumos** (premium) — pedir, recibir y colocar lo que
  consume el parque del cliente, con contador de copias y el resumen derivado
  (cadencia, rinde, desde cuándo pedir).
- **Añadido:** **contratos de proveedor** (mismo módulo premium) — qué máquinas
  cubre el contrato del cliente con su tercero.
- **Añadido:** reporte XLSX de insumos (el papel del reclamo al proveedor:
  agrupado por equipo, con demora de entrega y rinde) — sube a **7** analíticos +
  3 volcados planos.
- **Añadido:** el listado de equipos acepta `?referencia=` para resolver por el
  identificador que usa el proveedor.
- **Cambiado:** el "día de hoy" sale de `libra-ui/fechas` (PR #265).
- **Corregido:** el deploy no corría las 36 migraciones; el CLI de Alembic no
  encontraba `plans`.

### 2026-08-23
- **Corregido:** el contenedor corría en UTC; se fija la zona horaria Argentina
  (UTC-3) en el sidecar PostgreSQL (`postgres -c timezone=...`), no sólo con `TZ`.

### 2026-08-22
- **Cambiado:** el título de pantalla acompaña el icono del sidebar.

### 2026-08-21
- **Cambiado:** los badges de estado adoptan el criterio compartido de la familia.

### 2026-08-16
- **Cambiado:** única webfont del producto — el wordmark en **Montserrat 700**
  self-hosted (`@fontsource/montserrat`, subset latino); el resto, tipografía del
  sistema.

### 2026-08-09 – 2026-08-11
- **Cambiado:** corte a **PostgreSQL** como único motor (las tres instancias ya lo
  hacían desde el 2026-08-11; decisión de familia el 2026-08-12). El arranque
  rechaza cualquier destino que no sea PostgreSQL. Ver `DECISIONS.md` ADR-004.

### 2026-07-30
- **Añadido:** remitos y presupuestos sobre el dominio de LibraCore
  (`db.remitos_presupuestos` + `pdf_generator` + `config_manager`): numeración,
  estados, conversión presupuesto→remito y PDF. Ver `DECISIONS.md` ADR-005.
- **Añadido:** `incidencia_id` en `equipos_movimientos` (el movimiento que causó
  un ticket) y `?equipo_id=` en el listado de incidencias
  ("¿cuántas veces falló este equipo?").

### 2026-07-29
- **Añadido:** reescritura completa como **producto Libra nativo** (FastAPI +
  SQLAlchemy + React), rebrand de "Soporte Neuroflow" a LibraDesk. Ver
  `DECISIONS.md` ADR-001.
- **Añadido:** login propio con **LibraAuth** (usuario/contraseña, PBKDF2) —
  primer consumidor del motor. Ver `DECISIONS.md` ADR-002.
- **Eliminado:** login por Google OAuth y sincronización con Google Workspace
  (Contacts/Calendar/Tasks); los módulos Agenda y Tareas (espejos sin valor propio
  sin esa integración).
- **Cambiado:** dominio conservado de la versión anterior — Clientes, Equipos
  (+historial de movimientos) e Incidencias (+auditoría de estado).
