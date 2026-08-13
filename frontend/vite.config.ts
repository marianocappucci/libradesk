import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import Icons from 'unplugin-icons/vite'

// Proxy de API en dev: mismo origen que el front (localhost:5173) hacia
// el backend FastAPI (localhost:8000) para que la cookie de sesion
// (ld_session) funcione sin lidiar con CORS/SameSite cross-origin --
// mismo truco que usa el resto de la familia (en produccion el build de
// este frontend se sirve desde el mismo proceso FastAPI, ver app/asgi.py).
const API_PATHS = [
  '/auth', '/api',
]

const escapeRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// Iconos multicolor `fluent-color` (Microsoft, MIT), 2026-08-13.
// `unplugin-icons` resuelve `~icons/fluent-color/<nombre>` en tiempo de
// compilacion contra `@iconify-json/fluent-color`: al bundle entra unicamente
// el SVG de los iconos importados y en runtime no hay ninguna libreria de
// iconos ni pedido a api.iconify.design. Por eso las cuatro dependencias son
// de desarrollo.
//
// 🔴 Estos iconos traen el color HORNEADO (gradientes con hex fijos, sin
// `currentColor`). NO heredan el color del boton ni del estado: un icono
// dentro del boton destructivo se queda con su propio color, y uno de estado
// no puede ponerse en rojo. Se adoptaron igual, por decision explicita del
// humano el 2026-08-13, sabiendo eso.
//
// 🔴 El set NO cubre el vocabulario CRUD: no hay tacho de basura, ni flecha de
// volver, ni impresora, ni caja/paquete, ni ticket. Esos 23 iconos siguen
// viniendo de lucide, que por eso sigue siendo dependencia del producto.
export default defineConfig({
  plugins: [react(), tailwindcss(), Icons({ compiler: 'jsx', jsx: 'react' })],
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
