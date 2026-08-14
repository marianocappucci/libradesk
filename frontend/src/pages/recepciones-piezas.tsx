/** Las pestañas de Recepción de equipos (pedido 43).
 *
 *  En un archivo aparte por el mismo motivo que `configuracion-piezas.tsx`:
 *  exportar una constante desde un archivo que también exporta componentes
 *  dispara `react-refresh/only-export-components`.
 *
 *  Cada pestaña es una ruta, así que se puede linkear "mirá lo que hay en el
 *  taller" y el botón "atrás" del navegador hace lo que se espera.
 */
import type { Pestania } from '@/components/conmutador'
import { Warehouse } from 'lucide-react'
import { PackageCheck } from '@/components/iconos-accion'

export const PESTANIAS_RECEPCION: readonly Pestania[] = [
  { clave: 'taller', to: '/recepciones', label: 'En el taller', icono: Warehouse },
  {
    clave: 'entregados', to: '/recepciones/entregados', label: 'Entregados',
    icono: PackageCheck,
  },
]
