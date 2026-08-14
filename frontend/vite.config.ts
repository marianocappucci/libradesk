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

// Sin `unplugin-icons` desde el 2026-08-13: los 96 iconos del producto volvieron
// a **lucide**, que se importa como cualquier otra dependencia. Con eso se
// fueron también `@iconify-json/fluent`, `@iconify-json/fluent-color` y los dos
// `@svgr/*`, que existían sólo para resolver los `~icons/…` virtuales.
//
// ⚠️ Si alguna vez se sube el pin de `libra-ui` a v0.18.0 o mayor, el plugin
// vuelve a hacer falta: esa versión trae el módulo compartido de iconos de
// acción, que importa `~icons/fluent/…` y viaja como TSX crudo, o sea que se
// compila con el pipeline de ESTE producto. Hoy el pin es v0.17.0 y no lo
// necesita.
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
