/** El título de una pantalla: **una sola definición** del tamaño, del espaciado
 *  y de cómo se muestra el icono.
 *
 *  Existe porque no había ninguna. Al 2026-08-14 los títulos estaban repartidos
 *  en tres formas distintas escritas a mano en cada pantalla:
 *
 *  | forma | dónde | icono |
 *  |---|---|---|
 *  | `text-lg` + tile | 20 pantallas | en recuadro gris |
 *  | `text-2xl` + `h-6 w-6` | `comercial-ui` (10 pantallas) y `Stock` | suelto, sin recuadro |
 *  | `text-lg`, sin icono | los 4 detalles de registro | ninguno |
 *
 *  El resultado era que pasar de Incidencias a Ventas cambiaba el tamaño del
 *  título y el tratamiento del icono, sin que eso significara nada.
 *
 *  **Converge a `text-lg` con tile**, que es lo que ya cumplían 20 de 22 — la
 *  regla de siempre: se normaliza hacia la convención que alguien ya cumple, no
 *  hacia una nueva. Los dos `text-2xl` bajan de tamaño.
 *
 *  **El icono es obligatorio, y es el punto.** Pedido del humano (2026-08-14):
 *  que todos tengan fondo gris. Un `icono?` opcional deja que la próxima
 *  pantalla nazca sin él y nadie se entere, que es exactamente cómo se llegó a
 *  las tres formas de arriba. Si alguna vez hace falta un título sin icono, se
 *  escribe un `<h2>` a mano y queda a la vista que es la excepción.
 */
import type { ComponentType, ReactNode } from 'react'
import { Tile } from '@/components/iconos-accion'
import { cn } from '@/lib/utils'

export function TituloPantalla({ icono: Icono, children, className }: {
  icono: ComponentType<{ className?: string }>
  children: ReactNode
  className?: string
}) {
  return (
    <h2 className={cn('flex items-center gap-2 text-lg font-semibold', className)}>
      {/* 32 px con el glifo a 20: el tile del título pesa más que el de la fila
          de una tabla porque encabeza la pantalla. Misma receta, otro tamaño
          — igual que en lucide.dev, que usa 56 px en la grilla y 21,6 en la
          barra de arriba. */}
      <Tile className="size-8 [&>svg]:size-5">
        <Icono />
      </Tile>
      {children}
    </h2>
  )
}
