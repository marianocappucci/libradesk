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
