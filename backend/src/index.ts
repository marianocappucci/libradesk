import express from 'express';
import cors from 'cors';
import session from 'express-session';
import dotenv from 'dotenv';
import path from 'path';
import { testConnection } from './database/connection';
import authRoutes from './routes/auth';
import clientesRoutes from './routes/clientes';
import equiposRoutes from './routes/equipos';
import incidenciasRoutes from './routes/incidencias';
import calendarRoutes from './routes/calendar';
import tasksRoutes from './routes/tasks';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3001;
const FRONTEND_DIST = path.join(__dirname, '..', '..', 'frontend', 'dist');

app.use(cors({
  origin: process.env.FRONTEND_URL || 'http://localhost:5173',
  credentials: true,
}));

app.use(express.json());

app.use(session({
  secret: process.env.SESSION_SECRET || 'soporte-it-secret-2024',
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: false,
    httpOnly: true,
    maxAge: 7 * 24 * 60 * 60 * 1000,
  },
}));

app.use('/api/auth', authRoutes);
app.use('/api/clientes', clientesRoutes);
app.use('/api/equipos', equiposRoutes);
app.use('/api/incidencias', incidenciasRoutes);
app.use('/api/calendar', calendarRoutes);
app.use('/api/tasks', tasksRoutes);

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
