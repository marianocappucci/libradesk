# Changelog — LibraDesk

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

> LibraDesk todavía **no publica versiones semver** (el `pyproject.toml` está en
> `0.1.0` y no hay tags de release): se despliega por promoción `develop`→`main`,
> no por tag. Este changelog registra los hitos por **fecha**, más reciente
> primero, reconstruidos de la historia registrada en el wiki (entidad
> `libradesk`) y verificados contra el código. Cuando se adopte versionado semver,
> los hitos de aquí en más se agruparán bajo su versión.

## [Sin versionar] — hitos por fecha

### 2026-10-05
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
