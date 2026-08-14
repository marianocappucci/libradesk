/** Las pestañas de Equipos y flota (pedido 42, separación en pestañas).
 *
 *  En un archivo aparte por el mismo motivo que `configuracion-piezas.tsx`:
 *  exportar una constante desde un archivo que también exporta componentes
 *  dispara `react-refresh/only-export-components`.
 *
 *  El orden es el del día de trabajo: primero quién sale (equipos), después a
 *  qué (agenda), y la flota última porque es el catálogo que las otras dos
 *  consumen — se toca cuando entra o sale un vehículo, no todas las mañanas.
 */
import type { Pestania } from '@/components/conmutador'
import { CalendarDays, Users } from 'lucide-react'
import { Car } from '@/components/iconos-accion'

export const PESTANIAS_EQUIPOS: readonly Pestania[] = [
  { clave: 'equipos', to: '/equipos-trabajo', label: 'Equipos de trabajo', icono: Users },
  { clave: 'agenda', to: '/equipos-trabajo/agenda', label: 'Agenda del día', icono: CalendarDays },
  { clave: 'flota', to: '/equipos-trabajo/flota', label: 'Flota', icono: Car },
]
