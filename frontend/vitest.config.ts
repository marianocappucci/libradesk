// Config de tests aparte del vite.config.ts, y no un bloque `test` dentro
// de el: asi el build de produccion no arrastra tipos ni opciones de
// Vitest. Se reusa la config de Vite (con su alias `@`) via mergeConfig,
// para que los tests resuelvan los imports igual que la app.
import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    // `@vitejs/plugin-react` no toca node_modules, asi que los .tsx de
    // libra-ui los transpila esbuild -- y por defecto usa el runtime
    // CLASICO, que emite `React.createElement` sin que React este
    // importado: "React is not defined" al primer render. Con `automatic`
    // usa el mismo runtime que el resto de la app.
    esbuild: { jsx: 'automatic' },
    test: {
      environment: 'jsdom',
      globals: true,
      // Zona fija. Sin esto, todo test que compare una fecha depende de la
      // zona de la máquina: la agenda (pedido 42, fase B) tiene que abrir en
      // "hoy" **local**, y con TZ=UTC —que es lo que traen el CI y WSL— a las
      // 22:00 de Argentina eso ya es mañana. Se pone la zona real de los
      // usuarios, así el test mide lo que le pasa a la empresa.
      env: { TZ: 'America/Argentina/Buenos_Aires' },
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      // 15 s en vez de los 5 s por defecto. **El motivo cambió el 2026-08-14 y
      // el número quedó igual**, así que vale escribir cuál es cuál.
      //
      // El motivo VIEJO se fue: `unplugin-icons` compilaba cada SVG con svgr en
      // frío y eso llevaba la compilación de la suite de 6,4 s a 53 s. Con los
      // iconos de vuelta en lucide ese paso no existe (transform: ~6 s).
      //
      // El motivo NUEVO es que la suite tiene tests legítimamente lentos.
      // Medido con la máquina en reposo: `recepciones.test.tsx` → "manda los
      // campos del pedido y NO manda cadenas vacías" tarda **4,55 s**, y el
      // archivo entero 12,6 s. Contra un techo de 5 s eso deja 450 ms de
      // margen, o sea ninguno: se cayó apenas la máquina se puso a hacer otra
      // cosa al mismo tiempo, y el CI corre en runners compartidos.
      //
      // Se intentó bajarlo a 5 s primero, con una medición mal leída —se tomó
      // como "el test más lento" una línea de una salida truncada, que decía
      // 1,83 s—. Lo destapó la suite completa poniéndose roja. Si alguien
      // quiere volver a bajarlo, el número a mirar es el del test de
      // recepciones, no el total de la corrida.
      testTimeout: 15_000,
      coverage: {
        provider: 'v8',
        // Trinquete, no meta. Los tests de los SPAs son de HUMO a proposito
        // (la logica compartida se prueba a fondo en libra-ui, que tiene su
        // propia suite y su propio CI), asi que este numero es bajo y esta
        // bien que lo sea: sirve para que nadie borre tests, no para medir
        // calidad. Medido el 2026-07-31: 18.18% de lineas; el piso queda 3
        // puntos abajo.
        thresholds: { lines: 16 },
        reporter: ['text-summary', 'json-summary'],
        // Solo el codigo propio del producto: `libra-ui` tiene su propia
        // suite y su propio CI, medirlo aca contaria dos veces lo mismo.
        include: ['src/**/*.{ts,tsx}'],
        exclude: [
          'src/test/**',          // helpers de test, no codigo de la app
          'src/**/*.d.ts',
          'src/main.tsx',         // solo monta el arbol de React
          'src/components/ui/**', // shadcn/ui: copiado tal cual del upstream
        ],
      },
      server: {
        deps: {
          // `libra-ui` se consume como CODIGO FUENTE (.tsx) desde
          // node_modules -- sus `exports` apuntan a src/. Vitest por
          // defecto no transforma node_modules, asi que ese JSX llegaria
          // sin compilar y todo revienta con "React is not defined".
          // Inlinearlo lo hace pasar por el pipeline de Vite, igual que en
          // el build real del producto.
          inline: ['libra-ui'],
        },
      },
    },
  }),
)
