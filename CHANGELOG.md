# Changelog — LibraDesk

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

> LibraDesk todavía **no publica versiones semver** (el `pyproject.toml` está en
> `0.1.0` y no hay tags de release): se despliega por promoción `develop`→`main`,
> no por tag. Este changelog registra los hitos por **fecha**, más reciente
> primero, reconstruidos de la historia registrada en el wiki (entidad
> `libradesk`) y verificados contra el código. Cuando se adopte versionado semver,
> los hitos de aquí en más se agruparán bajo su versión.

## [Sin versionar] — hitos por fecha

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
