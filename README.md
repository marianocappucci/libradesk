# Soporte Neuroflow

Sistema interno de soporte IT para Neuroflow. Gestión de clientes, equipos, incidencias, agenda y tareas, con integración a Google Workspace.

---

## Qué hace el sistema

| Módulo | Descripción |
|---|---|
| **Clientes** | CRUD de clientes con sincronización bidireccional a Google Contacts (etiqueta "IT Soporte") |
| **Equipos** | Inventario de equipos por cliente (tipo, modelo, serial, garantía, estado) |
| **Incidencias** | Tickets de soporte con estados, prioridades, técnico asignado, horas y actividades |
| **Agenda** | Eventos en el calendario "IT Soporte" de Google Calendar |
| **Tareas** | Lista "IT Soporte" de Google Tasks |

El acceso está restringido a una única cuenta de Google (`ALLOWED_EMAIL` en el `.env`).

---

## Stack

**Backend**
- Node.js 22 + Express + TypeScript
- PostgreSQL 16 (sesiones y datos)
- Google OAuth 2.0 + googleapis (Contacts, Calendar, Tasks)

**Frontend**
- React 18 + Vite + Tailwind CSS
- Axios con `withCredentials` (sesión por cookie)
- React Router v6

**Infraestructura (VPS)**
- PM2 como process manager
- Nginx Proxy Manager (Docker) como reverse proxy
- Dominio: `soporte.neuroflow.com.ar`

---

## Estructura del proyecto

```
soporte-neuroflow/
├── backend/
│   ├── src/
│   │   ├── controllers/      # Lógica de cada recurso
│   │   ├── routes/           # Definición de endpoints
│   │   ├── middleware/        # Auth (requireAuth)
│   │   ├── database/         # Pool de conexión PostgreSQL
│   │   ├── models/           # Tipos TypeScript
│   │   └── utils/
│   │       ├── contactsSync.ts   # Sync con Google Contacts
│   │       └── googleClient.ts   # OAuth2 client factory
│   ├── dist/                 # Compilado (generado, no commitear)
│   ├── .env                  # Variables de entorno (no commiteado)
│   ├── .env.example          # Plantilla de variables
│   └── tsconfig.json
├── frontend/
│   ├── src/
│   │   ├── pages/            # Clientes, Incidencias, Agenda, Tareas, Dashboard
│   │   ├── components/       # Layout, Sidebar
│   │   ├── hooks/            # useAuth
│   │   └── services/         # api.ts (axios)
│   ├── dist/                 # Build de producción (generado)
│   └── vite.config.ts
└── docs/
    └── schema.sql            # Schema completo de la BD
```

---

## Variables de entorno (backend/.env)

```env
DATABASE_URL=postgresql://usuario:password@localhost:5432/soporte_it
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://soporte.neuroflow.com.ar/api/auth/google/callback
SESSION_SECRET=clave-secreta-larga
ALLOWED_EMAIL=tu@email.com
FRONTEND_URL=http://soporte.neuroflow.com.ar
PORT=3001
NODE_ENV=production
```

---

## Base de datos

```sql
clientes              -- Clientes con google_contact_id para sync
equipos               -- Equipos vinculados a clientes
incidencias           -- Tickets de soporte
actividades_incidencia -- Historial de actividades por ticket
session               -- Sesiones persistentes (connect-pg-simple)
```

Setup inicial:
```bash
sudo -u postgres psql -f docs/schema.sql
sudo -u postgres psql -c "CREATE USER usuario WITH PASSWORD 'password';"
sudo -u postgres psql -c "CREATE DATABASE soporte_it OWNER usuario;"
sudo -u postgres psql -d soporte_it -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO usuario;"
sudo -u postgres psql -d soporte_it -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO usuario;"
```

---

## Google Cloud Console

El proyecto requiere un OAuth 2.0 client con los siguientes scopes habilitados:
- `openid`, `email`, `profile`
- `https://www.googleapis.com/auth/calendar`
- `https://www.googleapis.com/auth/tasks`
- `https://www.googleapis.com/auth/contacts`

Y la siguiente URI de redirección autorizada:
```
http://soporte.neuroflow.com.ar/api/auth/google/callback
```
(Agregar también la versión `https://` cuando se active SSL)

---

## Deploy en el VPS

### Primera vez

```bash
# 1. Clonar
git clone https://github.com/marianocappucci/soporte-neuroflow.git
cd soporte-neuroflow

# 2. Instalar dependencias
cd backend && npm install
cd ../frontend && npm install

# 3. Configurar .env
cp backend/.env.example backend/.env
# editar backend/.env con los valores reales

# 4. Crear BD y schema
sudo -u postgres psql -c "CREATE USER usuario WITH PASSWORD 'soporte2024';"
sudo -u postgres psql -c "CREATE DATABASE soporte_it OWNER usuario;"
sudo -u postgres psql -d soporte_it < docs/schema.sql
sudo -u postgres psql -d soporte_it -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO usuario;"
sudo -u postgres psql -d soporte_it -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO usuario;"

# 5. Compilar backend
cd backend
chmod -R +x node_modules/.bin/
node_modules/.bin/tsc

# 6. Build frontend
cd ../frontend
chmod +x node_modules/@esbuild/linux-x64/bin/esbuild
node node_modules/vite/bin/vite.js build

# 7. Iniciar con PM2
pm2 start backend/dist/index.js --name soporte-neuroflow --cwd backend
pm2 save
```

### Deploy de cambios

```bash
# Compilar backend
cd /root/soporte-neuroflow/backend
node_modules/.bin/tsc

# Build frontend (si hubo cambios en frontend/)
cd /root/soporte-neuroflow/frontend
node node_modules/vite/bin/vite.js build

# Reiniciar
pm2 restart soporte-neuroflow --update-env

# Subir a GitHub
cd /root/soporte-neuroflow
git add <archivos>
git commit -m "descripción"
git push
```

### Comandos útiles

```bash
pm2 status                          # Estado del proceso
pm2 logs soporte-neuroflow          # Logs en tiempo real
pm2 logs soporte-neuroflow --lines 50 --nostream  # Últimas 50 líneas

# Ver sesiones activas en BD
sudo -u postgres psql -d soporte_it -c "SELECT sid, expire FROM session;"

# Conectarse a la BD
psql -U usuario -d soporte_it -h localhost
```

---

## Sincronización con Google Contacts

- Al **crear** un cliente en la app → se crea el contacto en Google y se agrega a la etiqueta "IT Soporte" via `contactGroups.members.modify`
- Al **editar** un cliente → se actualiza el contacto en Google (verifica y re-agrega al grupo si hace falta)
- Al **eliminar** un cliente → se elimina el contacto de Google
- Botón **"Importar de Google"** → lee solo los contactos etiquetados "IT Soporte" e importa los que no existan en la app (merge por `google_contact_id` o email)

---

## Notas de arquitectura

- El backend Express sirve tanto la API (`/api/*`) como el frontend estático (`frontend/dist/`)
- Las sesiones se persisten en PostgreSQL (`tabla session`) con `connect-pg-simple`, sobreviven reinicios de PM2
- El proxy en Nginx Proxy Manager apunta `soporte.neuroflow.com.ar → 172.17.0.1:3001`
- `app.set('trust proxy', 1)` está activo para funcionar correctamente detrás de NPM
