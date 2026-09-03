# LibraDesk

Sistema interno de soporte IT. Gestión de clientes, equipos e incidencias.

Reescrito el 2026-07-29 como producto Libra nativo (antes: Node.js/
Express + PostgreSQL, ver historial de git) — comparte stack y motores
con el resto de la familia Libra (Contalibra/Restolibra/Gestiolibra/
MedLibra/VentaLibra).

---

## Qué hace el sistema

| Módulo | Descripción |
|---|---|
| **Clientes** | CRUD de clientes (empresa, contacto, tipo de facturación) |
| **Equipos** | Inventario de equipos por cliente, con historial de movimientos |
| **Incidencias** | Tickets de soporte con estados, prioridades, técnico asignado, horas y auditoría de cambios de estado |
| **Técnicos / Sectores** | Catálogos de apoyo para incidencias |
| **Dashboard / Reportes** | Resumen agregado + exports a Excel |

Login propio (usuario/contraseña) via [libraauth](https://github.com/marianocappucci/libraauth)
— reemplaza la integración anterior con Google OAuth/Contacts/Calendar/
Tasks (eliminada en la reescritura; reemplazarla por una funcionalidad
propietaria queda pendiente para otra sesión).

---

## Stack

**Backend**
- FastAPI + SQLAlchemy (Python 3.12)
- PostgreSQL — único motor (sidecar `postgres:16-alpine`); el arranque rechaza cualquier otro destino
- [libraauth](https://github.com/marianocappucci/libraauth) — sesión por cookie + usuarios (motor nuevo, primer consumidor)
- openpyxl para exports xlsx

**Frontend**
- React 19 + Vite + Tailwind CSS v4 + shadcn/ui
- [libra-ui](https://github.com/marianocappucci/libra-ui) (Layout, Login, AuthContext, DataTable, api-client)
- React Hook Form + Zod + TanStack Table

**Infraestructura (VPS)**
- Docker (`docker compose`), mismo patrón que el resto de la familia
- Nginx Proxy Manager (Docker) como reverse proxy
- Dominio: `libradesk.com.ar`

---

## Estructura del proyecto

```
libradesk/
├── app/
│   ├── main.py            # create_app(): engine PostgreSQL, libraauth, routers
│   ├── asgi.py             # entrypoint uvicorn, sirve frontend/dist
│   ├── database.py         # engine/session factory propios
│   ├── auth.py              # shim sobre libraauth.session_auth
│   ├── dependencies.py      # Depends(get_x_repository)
│   ├── routers/              # endpoints FastAPI (Pydantic inline)
│   └── services/             # modelo SQLAlchemy + Repository por recurso
├── frontend/
│   └── src/
│       ├── pages/            # Clientes, Equipos, Incidencias, Tecnicos, Dashboard, Usuarios
│       ├── components/       # Layout/data-table (shims libra-ui), ui/ (shadcn)
│       └── api.ts            # cliente HTTP + tipos propios
├── tests/                    # pytest (auth + CRUD + dashboard + xlsx)
├── Dockerfile
├── docker-compose.yml
└── docs/schema.sql           # [HISTÓRICO] schema Postgres de la version Node.js anterior
```

---

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `SECRET_KEY` | Secreto de la cookie de sesión (libraauth) — obligatorio fuera de `ENV=development` |
| `LIBRADESK_ADMIN_USERNAME` | Usuario admin inicial (default `admin`) |
| `LIBRADESK_ADMIN_PASSWORD` | Contraseña del admin inicial — obligatoria fuera de `ENV=development` |
| `DATA_DIR` | Carpeta donde vive `libradesk.db` (default `/app/data` en el container) |
| `ENV` | `development` relaja los fail-fast anteriores |

### Puente de facturación

LibraDesk **no factura**: arma el comprobante y lo deja en la bandeja del
sistema que sí emite, donde una persona lo revisa y saca el CAE. Hay dos
destinos posibles y la instancia elige uno.

| Variable | Descripción |
|----------|-------------|
| `FACTURACION_DESTINO` | `contalibra` (default) o `sos`. Sin la variable, o con un valor desconocido, se usa `contalibra` |
| `INSTANCIA_SLUG` | Identifica a esta instancia del lado del destino |

**Destino `contalibra`:**

| Variable | Descripción |
|----------|-------------|
| `CONTALIBRA_URL` | URL de la instancia de Contalibra del mismo cliente |
| `CONTALIBRA_SERVICE_TOKEN` | Token de servicio. Nunca sale por la API, ni enmascarado |

**Destino `sos`** — SOS Contador, el sistema del estudio contable del cliente:

| Variable | Descripción |
|----------|-------------|
| `SOS_USUARIO` | Usuario de la API. **Que sea uno dedicado**: un usuario del estudio alcanza todas las CUITs de su cartera |
| `SOS_PASSWORD` | Contraseña. La API no tiene tokens de servicio |
| `SOS_IDCUIT` | Id de la CUIT sobre la que se opera (`GET /cuit/listado`) |
| `SOS_PUNTOVENTA` | Punto de venta. **Tiene que ser exclusivo de LibraDesk**: la numeración la lleva el emisor y se pisa con lo que el estudio facture a mano |
| `SOS_LETRA` | Letra del comprobante (default `C`), según la condición del emisor ante ARCA |
| `SOS_IDTIPO_OPERACION` | Default `2`. Los tipos 1, 3 y 5 exigen campos no documentados y fallan |
| `SOS_IDPRODUCTO` | Opcional. Fija un producto genérico del catálogo para todos los ítems, en vez de crear uno por descripción |

Sin las variables del destino elegido **no hay puente**: falla cerrado y la
pantalla lo informa. Los comprobantes se mandan siempre con `obtienecae: false`,
es decir sin emitir ante ARCA.

---

## Desarrollo local

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ENV=development DATA_DIR=./dev-data uvicorn app.asgi:app --reload

# Frontend (proxea /auth y /api al backend en :8000, ver vite.config.ts)
cd frontend
npm install
npm run dev
```

Tests: `pytest -v`

---

## Deploy en el VPS

Mismo patrón que Gestiolibra/MedLibra/VentaLibra — build y deploy manual
via `docker compose`, sin CI/CD automatizado (el CI de GitHub Actions
solo corre tests, no despliega):

```bash
cd /root/libradesk
git pull
docker compose build
docker compose up -d
```

El `Dockerfile` usa `--mount=type=ssh` para instalar las dos
dependencias privadas (`libraauth` en el backend, `libra-ui` en el
frontend) con sus deploy keys de solo lectura dedicadas
(`~/.ssh/id_ed25519_libraauth`, `~/.ssh/id_ed25519_libra_ui` en el VPS).

### Comandos útiles

```bash
docker compose logs -f libradesk      # Logs en tiempo real
docker compose restart libradesk
docker exec -it libradesk-postgres psql -U libradesk libradesk
```

---

## Notas de arquitectura

- El backend FastAPI sirve tanto la API (`/api/*`, `/auth/*`) como el
  frontend estático (build horneado en `/opt/frontend-dist`, fuera del
  bind mount de dev — mismo patrón que el resto de la familia).
- `libraauth` y el dominio propio de LibraDesk viven en la **misma**
  base PostgreSQL (un solo engine para las dos
  metadatas) — decisión explícita para no
  arrastrar las 28 tablas de facturación/ARCA de `libracore.db` que no
  aplican a este producto.
- `docs/schema.sql` queda como referencia histórica del schema Postgres
  de la versión Node.js anterior — no se usa en el sistema actual
  (el schema lo maneja Alembic: migraciones en `migrations/`, corridas en el deploy).
