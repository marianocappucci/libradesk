/** Las pestañas de Equipos y flota (pedido 42, separación en pestañas).
 *
 *  En un archivo aparte por el mismo motivo que tenia `configuracion-piezas.tsx`
 *  --que se fue el 2026-08-30, al pasar Configuracion a la pantalla del kit--:
 *  exportar una constante desde un archivo que también exporta componentes
 *  dispara `react-refresh/only-export-components`.
 *
 *  Primero quién sale (equipos) y después en qué (flota), que es el catálogo que
 *  la otra consume — se toca cuando entra o sale un vehículo, no todas las
 *  mañanas.
 *
 *  **Eran tres.** La del medio era la agenda del día; desde el 2026-08-14 es una
 *  pantalla propia (`/agenda`, ver `pages/Agenda.tsx`) y un ítem del menú. Es lo
 *  que se abre todas las mañanas, y estaba detrás de un ítem que se llama por el
 *  catálogo de vehículos.
 */
import type { Pestania } from '@/components/conmutador'
import { Users } from 'lucide-react'
import { Car } from '@/components/iconos-accion'

export const PESTANIAS_EQUIPOS: readonly Pestania[] = [
  { clave: 'equipos', to: '/equipos-trabajo', label: 'Equipos de trabajo', icono: Users },
  { clave: 'flota', to: '/equipos-trabajo/flota', label: 'Flota', icono: Car },
]
