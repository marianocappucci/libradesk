/** Las pestañas de Configuración (pedido 36, 2026-08-04).
 *
 *  Antes las secciones eran tarjetas apiladas en una sola pantalla larga. Se
 *  separaron en pestañas **con el mismo conmutador que depósitos**, a pedido
 *  del usuario.
 *
 *  Cada pestaña es una ruta, así que se puede linkear "andá a facturación" y el
 *  botón "atrás" del navegador hace lo que se espera.
 */
import type { Pestania } from '@/components/conmutador'
import { Building2, Database, ListChecks, Send, Tags } from 'lucide-react'

export const PESTANIAS_CONFIG: readonly Pestania[] = [
  { clave: 'empresa', to: '/configuracion', label: 'Empresa', icono: Building2 },
  { clave: 'servicios', to: '/configuracion/servicios', label: 'Servicios', icono: ListChecks },
  { clave: 'categorias', to: '/configuracion/categorias', label: 'Tipos de incidencia', icono: Tags },
  // Proveedores no está: es una pantalla propia bajo Compras (`/proveedores`).
  // Mientras fue pestaña, el ítem del menú comercial apuntaba a esta ruta, y
  // entrar por Compras se veía igual que entrar por Configuración general.
  { clave: 'facturacion', to: '/configuracion/facturacion', label: 'Facturación', icono: Send },
  // Última a propósito: es la que más rompe si se toca sin querer, y la que
  // menos se usa en el día a día. Mismo lugar que en Contalibra.
  { clave: 'datos', to: '/configuracion/datos', label: 'Datos / Backup', icono: Database },
]
