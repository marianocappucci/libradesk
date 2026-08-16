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
// Lo que lo devolvería no es subir el pin de `libra-ui`, sino importar
// `libra-ui/iconos-accion`. Ese módulo compartido sigue importando
// `~icons/fluent/…` —también en el pin de hoy, v0.23.0— y viaja como TSX crudo,
// o sea que se compila con el pipeline de ESTE producto. Pero es una hoja: nada
// dentro de `libra-ui` lo importa, y al ser un subpath de `exports` no entra al
// build mientras nadie lo pida por nombre. LibraDesk no lo pide — usa su propio
// `@/components/iconos-accion`, sobre lucide.
//
// Hasta el 2026-08-16 esta nota avisaba en función de la versión ("de v0.18.0 en
// adelante"), y era el disparador equivocado: el pin pasó de v0.17.0 a v0.23.0 y
// el build no se inmutó (v0.18.0 ni llegó a existir — el módulo compartido
// apareció en v0.19.0). El disparador es el import, y cuando llegue el build
// corta solo, con `Cannot find module '~icons/fluent/…'`. La receta para
// reponer el plugin está en el encabezado de `libra-ui/src/iconos-accion.tsx`.
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
