import express from 'express';
import cors from 'cors';
import session from 'express-session';
import connectPgSimple from 'connect-pg-simple';
import dotenv from 'dotenv';
import path from 'path';
import pool, { testConnection } from './database/connection';
import authRoutes from './routes/auth';
import clientesRoutes from './routes/clientes';
import equiposRoutes from './routes/equipos';
import incidenciasRoutes from './routes/incidencias';
import calendarRoutes from './routes/calendar';
import tasksRoutes from './routes/tasks';
import reportesRoutes from './routes/reportes';
import sectoresRoutes from './routes/sectores';
import tecnicosRoutes from './routes/tecnicos';
import dashboardRoutes from './routes/dashboard';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3001;
const FRONTEND_DIST = path.join(__dirname, '..', '..', 'frontend', 'dist');

// Necesario para que Express confíe en los headers del reverse proxy (NPM)
app.set('trust proxy', 1);

app.use(cors({
  origin: process.env.FRONTEND_URL || 'http://localhost:5173',
  credentials: true,
}));

app.use(express.json());

const PgSession = connectPgSimple(session);

app.use(session({
  store: new PgSession({
    pool,
    tableName: 'session',
    // Limpia sesiones expiradas cada hora
    pruneSessionInterval: 60 * 60,
  }),
  secret: process.env.SESSION_SECRET || 'soporte-it-secret-2024',
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: false,
    httpOnly: true,
    sameSite: 'lax',
    maxAge: 7 * 24 * 60 * 60 * 1000,
  },
}));

app.use('/api/auth', authRoutes);
app.use('/api/clientes', clientesRoutes);
app.use('/api/equipos', equiposRoutes);
app.use('/api/incidencias', incidenciasRoutes);
app.use('/api/calendar', calendarRoutes);
app.use('/api/tasks', tasksRoutes);
app.use('/api/reportes', reportesRoutes);
app.use('/api/sectores', sectoresRoutes);
app.use('/api/tecnicos', tecnicosRoutes);
app.use('/api/dashboard', dashboardRoutes);

app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Servir frontend en producción
app.use(express.static(FRONTEND_DIST));
app.get('*', (_req, res) => {
  res.sendFile(path.join(FRONTEND_DIST, 'index.html'));
});

async function start() {
  await testConnection();
  app.listen(PORT, () => {
    console.log(`✓ Servidor corriendo en http://localhost:${PORT}`);
  });
}

start();
