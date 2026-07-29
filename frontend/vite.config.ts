import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Proxy de API en dev: mismo origen que el front (localhost:5173) hacia
// el backend FastAPI (localhost:8000) para que la cookie de sesion
// (ld_session) funcione sin lidiar con CORS/SameSite cross-origin --
// mismo truco que usa el resto de la familia (en produccion el build de
// este frontend se sirve desde el mismo proceso FastAPI, ver app/asgi.py).
const API_PATHS = [
  '/auth', '/api',
]

const escapeRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: Object.fromEntries(
      API_PATHS.map((apiPath) => [
        `^${escapeRegex(apiPath)}(?:/|$)`,
        { target: 'http://localhost:8199', changeOrigin: true },
      ]),
    ),
  },
})
