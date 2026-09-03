# Arquitectura — LibraDesk

## Propósito y límites

LibraDesk es el producto vertical de **soporte técnico IT** de la familia Libra:
gestión de clientes, equipos e incidencias, más el circuito comercial que creció
alrededor (remitos, presupuestos, insumos y contratos de proveedor, reportes). Es
la herramienta interna de la empresa del usuario (Neuroflow/Compulibra).

Nació como "Soporte Neuroflow" (Node.js/Express + PostgreSQL) y el 2026-07-29 se
**reescribió por completo como producto Libra nativo** (FastAPI + SQLAlchemy +
React) para consumir los motores transversales de la familia. En esa reescritura
se descartó la sincronización con Google Workspace (Contacts/Calendar/Tasks) y el
login por Google OAuth: LibraDesk fue el **primer consumidor de [[libraauth]]**,
con login usuario/contraseña propio.

LibraDesk posee el flujo HTTP y las reglas de su negocio; delega en los motores lo
transversal (auth, PDF, provisioning, catálogo/inventario). No incorpora lógica
clínica, gastronómica ni de agenda de turnos.

## Componentes

- **`app/main.py`** (`create_app(database_url, data_dir)`): factory FastAPI.
  Configura el backend (`configure(database_url)`), compone las dependencias y
  monta los routers **con el gating por rol a nivel de router**
  (`include_router(..., dependencies=[Depends(...)])`, no por endpoint): la
  mayoría exige `staff_or_admin`, los de usuarios/empresa-admin exigen
  `require_admin`. Los routers de auth, SMTP, términos y códigos de demo los
  aportan los `build_*_router()` de `libraauth`/`libracore`.
- **`app/database.py`**: engine y session factory **propios** de LibraDesk — no
  existían en Gestiolibra porque aquella depende de `libragenda`. Un solo engine
  compartido por el dominio propio y por la tabla `usuarios` de `libraauth`
  (misma base, sin segunda BD). Su `configure()` **rechaza cualquier destino que
  no sea PostgreSQL** (ver "Persistencia").
- **`app/routers/`** (34 routers): la superficie HTTP —clientes, equipos
  (+movimientos), incidencias (+actividades/estados/movimientos/reemplazo),
  técnicos, sectores, categorías, servicios, proveedores, contratos y
  contratos_proveedor, insumos, inventario, activos, agenda, reparaciones,
  ingresos/depósitos, remitos, presupuestos, compras, ventas, facturación,
  cuotas, sucursales, informes/reportes, dashboard, users, health.
- **`app/services/`** (52 servicios): la lógica de negocio, con el patrón
  **modelo SQLAlchemy + Repository por recurso** (el mismo de `service_prices.py`
  de Gestiolibra). Incluye los generadores de PDF propios (`acta_pdf`,
  `incidencia_pdf`, `informe_pdf`, `ingreso_pdf`, `hoja_ruta_pdf`) y de XLSX
  (`reporte_xlsx`, `xlsx_helper`).
- **`app/auditoria.py`**, **`app/auth.py`**, **`app/dependencies.py`**,
  **`app/modules_gate.py`**, **`app/schema.py`**, **`app/spa.py`**, **`app/asgi.py`**:
  auditoría, dependencias FastAPI de rol, el gate de módulos por plan, el armado
  del schema, y el servido de la SPA.
- **`plans.py`**: los planes y qué módulos habilita cada uno (premium: insumos,
  contratos de proveedor). El gating de módulos se apoya acá.
- **`migrations/`**: cadena Alembic propia (~38 revisiones), corrida en el deploy.
- **`frontend/`**: la SPA React (ver "Frontend").

## Motores que consume

LibraDesk es el producto de la familia que más motores combina — mide el valor de
la separación motor/producto:

- **[[libracore]]**: `db.*` (acceso a datos, 21 sitios), `db.remitos_presupuestos`
  (dominio completo de remitos/presupuestos), `pdf_generator`
  (`RemitoPDF`/`PresupuestoPDF`), `config_manager` (datos de empresa que encabezan
  los PDF), `provisioning` (operación de instancias), `db.schema`,
  `db.url_de_instancia`.
- **[[libraauth]]**: `session_auth` (sesión por cookie, routers de auth),
  `repository`, `auditoria`, `terminos`, `auth_events`, `bootstrap` — la identidad
  entera. LibraDesk es su primer consumidor.
- **[[libracommerce]]**: `db.repository`, `domain.catalog`, `usecases.inventory` —
  el catálogo y el inventario del circuito comercial.

## Persistencia

**LibraDesk corre sobre PostgreSQL y nada más.** El `configure()` de
`app/database.py` **rechaza** cualquier destino que no sea una URL PostgreSQL con
un `ValueError` explícito, en vez de aceptarlo callado: una URL `sqlite://`
levantaba la app sobre un motor donde las FK no se chequean y los tipos son
dinámicos, así que los defectos que PostgreSQL rechaza de entrada pasaban hasta
producción. El corte fue el 2026-08-09/11 y la decisión de familia el 2026-08-12.
La guarda vive en el **arranque del producto**, no en `libracore` (el motor sigue
siendo neutral — ver la arquitectura de LibraCore).

El sidecar es `postgres:16-alpine` (collation por bytes, por eso los tests usan la
misma imagen), con la zona horaria fijada en el servidor
(`command: postgres -c timezone=America/Argentina/Buenos_Aires`), no sólo con
`TZ`. Una base por instancia (silo por cliente). Las migraciones Alembic corren en
el deploy.

## Frontend

SPA en **React 19 + Vite + Tailwind CSS v4 + shadcn/ui**, consumiendo
**[[libra-ui]]** (`v0.59.0`: `Layout`, `Login`, `AuthContext`, `DataTable`,
`api-client`, `Usuarios`, las primitivas de `ui/`). `frontend/src/pages/`
(~47 pantallas) y `frontend/src/components/` (~42). Única webfont del producto: el
wordmark en **Montserrat 700** self-hosted (`@fontsource/montserrat`); el resto,
tipografía del sistema. El build se hornea en la imagen (stage node) y se sirve
como estático; el backend sirve `/api/*` y `/auth/*`.

## Deploy

Docker + `docker compose` en dos stages (node build del frontend → runtime
Python), **manual en el VPS**, sin CD automatizado (el CI de GitHub Actions sólo
corre tests). El build usa `--mount=type=ssh` para las dependencias privadas
(`libraauth` en el backend, `libra-ui` en el frontend), con deploy keys SSH de
solo lectura dedicadas en el VPS.

Para mover una instancia de **cliente** se usa
`scripts/panel_admin.py actualizar --ref main` (sin slug — con slug toma una y
descarta el resto en silencio), ensayado con `--dry-run`: construye del ref
promovido en un clon limpio, así que el checkout del VPS puede seguir en `develop`
sin afectar el deploy. Dos instancias hoy: `dev.libradesk.com.ar` y
`compulibra.libradesk.com.ar`, ambas con SSL Let's Encrypt real detrás de
nginx-proxy-manager.

## Autenticación y roles

Sesión por cookie firmada (vía `libraauth`, usuario/contraseña con PBKDF2, sin
Google). El gating es por rol a nivel de router: `staff`/`admin` para el grueso,
`admin` para usuarios y la administración de empresa. La tabla `usuarios` es de
LibraDesk (la trae `libraauth` por callback), en la misma base que el dominio.

## Tests

`pytest` + FastAPI TestClient en el backend (~113: smoke de API + un archivo por
feature) contra PostgreSQL; `vitest` + Testing Library en el frontend (~14, con
piso de cobertura del 16 % que el CI hace cumplir). El CI corre sólo tests, no
deploy.

## Referencias

- `README.md`, `ONBOARDING_CLIENTES.md`, `DECISIONS.md`, `CHANGELOG.md`.
- Wiki: entidad `libradesk`, `concepts/estandares-desarrollo`, y la auditoría
  `auditoria-estructural-familia-libra-2026-09`.
