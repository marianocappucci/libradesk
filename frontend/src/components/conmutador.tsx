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
 */
import { Link } from 'react-router-dom'
import type { ComponentType } from 'react'
import { Button } from '@/components/ui/button'

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

export function Conmutador({ pestanias, actual }: {
  pestanias: readonly Pestania[]
  actual: string
}) {
  return (
    <div className="flex w-fit flex-wrap gap-1 rounded-md border p-1">
      {pestanias.map(({ clave, to, label, icono: Icono }) => (
        <Button
          key={clave}
          asChild
          size="sm"
          variant={actual === clave ? 'default' : 'ghost'}
        >
          {/* `aria-current` y no sólo el color: sin él la pestaña activa es
              indistinguible para un lector de pantalla, y los tests tendrían
              que afirmar sobre clases de Tailwind. */}
          <Link to={to} aria-current={actual === clave ? 'page' : undefined}>
            <Icono />{label}
          </Link>
        </Button>
      ))}
    </div>
  )
}
