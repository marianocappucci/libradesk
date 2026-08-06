/** Las pestañas de Configuración (pedido 36, 2026-08-04).
 *
 *  Antes las tres secciones —datos de la empresa, tipos de incidencia y
 *  proveedores— eran tres tarjetas apiladas en una sola pantalla larga. Se
 *  separaron en pestañas **con el mismo conmutador que depósitos**, a pedido
 *  del usuario.
 *
 *  Cada pestaña es una ruta, así que se puede linkear "andá a proveedores" y el
 *  botón "atrás" del navegador hace lo que se espera.
 */
import type { Pestania } from '@/components/conmutador'
import { Building2, Database, ListChecks, Tags, Wrench } from 'lucide-react'

export const PESTANIAS_CONFIG: readonly Pestania[] = [
  { clave: 'empresa', to: '/configuracion', label: 'Empresa', icono: Building2 },
  { clave: 'servicios', to: '/configuracion/servicios', label: 'Servicios', icono: ListChecks },
  { clave: 'categorias', to: '/configuracion/categorias', label: 'Tipos de incidencia', icono: Tags },
  { clave: 'proveedores', to: '/configuracion/proveedores', label: 'Proveedores', icono: Wrench },
  // Última a propósito: es la que más rompe si se toca sin querer, y la que
  // menos se usa en el día a día. Mismo lugar que en Contalibra.
  { clave: 'datos', to: '/configuracion/datos', label: 'Datos / Backup', icono: Database },
]
