/** El conmutador de pestañas del producto.
 *
 *  Salió de la pantalla de depósitos (pedido 35), donde separa "de la empresa"
 *  de "de clientes". Se generalizó acá el 2026-08-04 al necesitarlo también
 *  Configuración (pedido 36): dos copias del mismo control se desincronizan, y
 *  además el usuario pidió explícitamente que las pestañas nuevas se vieran
 *  como las de depósitos.
 *
 *  **Cada pestaña es una ruta**, no un `useState`. Eso es lo que hace que se
 *  pueda linkear una sección, que el botón "atrás" del navegador funcione, y
 *  que recargar la página deje al usuario donde estaba.
 *
 *  ## 2026-08-22 — se ve igual que el de Contalibra
 *
 *  Hasta hoy dibujaba una caja con borde (`rounded-md border p-1`) y `<Button>`
 *  en `default`/`ghost`. Contalibra dibuja la píldora de shadcn: fondo `muted`,
 *  y la activa en blanco con sombra. Eran dos idiomas distintos para la misma
 *  cosa en la misma familia de productos, y el humano pidió que se vieran
 *  iguales.
 *
 *  🔑 **Las clases son, literalmente, las de `components/ui/tabs.tsx`** — las
 *  mismas cadenas, copiadas de ahí. Por eso las pestañas llevan
 *  `data-state="active" | "inactive"`: es el atributo del que cuelgan las
 *  variantes `data-[state=active]:…` del primitivo, así que la cadena entra sin
 *  tocarle una clase. `test/pestanias-mismo-aspecto.test.ts` compara los dos
 *  archivos y se pone rojo si alguien toca una sola de las dos.
 *
 *  ## Y por qué esto NO es `<Tabs>` de Radix
 *
 *  Porque estas pestañas **son enlaces**: cambian la URL. Envolverlas en
 *  `TabsTrigger asChild` les pisaría el rol —Radix pone `role="tab"` sobre el
 *  `<a>`— y un lector de pantalla dejaría de anunciar que navegan. Radix Tabs
 *  es para paneles dentro de una misma página; acá cada pestaña es una ruta con
 *  su propio `href`, que se puede abrir en otra solapa con el botón del medio.
 *  Lo que se comparte con el primitivo es el aspecto, que es lo que se pidió,
 *  no el mecanismo.
 */
import { Link } from 'react-router-dom'
import type { ComponentType } from 'react'

export type Pestania = {
  /** Identificador de la pestaña, para marcar cuál está activa. */
  clave: string
  to: string
  label: string
  // No `LucideIcon`: ese tipo es un `forwardRef` sobre `svg`, y desde que los
  // iconos de acción vienen envueltos en un recuadro (`<span>`, ver
  // `iconos-accion.tsx`) ya no encajan. La forma que de verdad se necesita acá
  // es la misma que piden `Pagina` y `libra-ui/Layout`.
  icono: ComponentType<{ className?: string }>
}

/** La clase de `TabsList` en `components/ui/tabs.tsx`, sin una coma de
 *  diferencia. Si ahí cambia, acá tiene que cambiar — y el guard lo exige. */
export const CLASES_LISTA = 'inline-flex h-9 w-fit items-center justify-center rounded-lg bg-muted p-[3px] text-muted-foreground'

/** Ídem, la de `TabsTrigger`. */
export const CLASES_PESTANIA = "inline-flex flex-1 items-center justify-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-sm font-medium whitespace-nowrap text-foreground outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-background data-[state=active]:shadow-sm dark:text-muted-foreground dark:data-[state=active]:border-input dark:data-[state=active]:bg-input/30 dark:data-[state=active]:text-foreground [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4"

export function Conmutador({ pestanias, actual }: {
  pestanias: readonly Pestania[]
  actual: string
}) {
  return (
    <div className={CLASES_LISTA}>
      {pestanias.map(({ clave, to, label, icono: Icono }) => {
        const activa = actual === clave
        return (
          /* `aria-current` y no sólo el color: sin él la pestaña activa es
             indistinguible para un lector de pantalla, y los tests tendrían
             que afirmar sobre clases de Tailwind. `data-state` es lo que
             enciende las variantes del primitivo. */
          <Link
            key={clave}
            to={to}
            aria-current={activa ? 'page' : undefined}
            data-state={activa ? 'active' : 'inactive'}
            className={CLASES_PESTANIA}
          >
            <Icono />{label}
          </Link>
        )
      })}
    </div>
  )
}
