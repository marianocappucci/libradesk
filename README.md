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
- SQLite (estándar de la familia Libra)
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
│   ├── main.py            # create_app(): engine SQLite, libraauth, routers
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
docker exec -it libradesk sqlite3 /app/data/libradesk.db
```

---

## Notas de arquitectura

- El backend FastAPI sirve tanto la API (`/api/*`, `/auth/*`) como el
  frontend estático (build horneado en `/opt/frontend-dist`, fuera del
  bind mount de dev — mismo patrón que el resto de la familia).
- `libraauth` y el dominio propio de LibraDesk viven en el **mismo**
  archivo SQLite (`Base.metadata.create_all()` se llama para las dos
  metadatas contra el mismo engine) — decisión explícita para no
  arrastrar las 28 tablas de facturación/ARCA de `libracore.db` que no
  aplican a este producto.
- `docs/schema.sql` queda como referencia histórica del schema Postgres
  de la versión Node.js anterior — no se usa en el sistema actual
  (SQLAlchemy `create_all()` en su lugar, sin Alembic todavía).
