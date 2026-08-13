/** Qué reportes hay, en qué grupo va cada uno y qué filtros acepta.
 *
 *  Compartido por el índice (`Reportes.tsx`) y la pantalla de un reporte
 *  (`ReporteDetalle.tsx`): el índice necesita el título, la descripción y el
 *  grupo; la pantalla, además, los campos del formulario. Tenerlo dos veces
 *  haría que agregar un filtro en una y no en la otra pase inadvertido.
 *
 *  **Lo que NO está acá son las columnas.** Esas las manda el backend junto
 *  con los datos (ver `app/services/reporte_vista.py`), que es lo que
 *  garantiza que la tabla en pantalla y el .xlsx sean el mismo reporte.
 */
import { ESTADO_LABELS, PRIORIDAD_LABELS } from '../api'
import Monitor from '~icons/fluent-color/laptop-16'
import Wallet from '~icons/fluent-color/savings-16'
import { Ticket } from '@/components/iconos-accion'

export const TODOS = '__todos__'

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export function firstOfMonthIso(): string {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10)
}

const ESTADO_EQUIPO_LABELS: Record<string, string> = {
  activo: 'Activo',
  en_reparacion: 'En reparación',
  almacenado: 'En depósito',
  baja: 'Baja',
}

const COBRO_LABELS: Record<string, string> = {
  sin_facturar: 'Sin facturar',
  pendiente_cobro: 'Pendiente de cobro',
  facturada: 'Facturada',
}

// Un campo de filtro, declarado por reporte. El formulario se arma solo a
// partir de esto para no repetir el mismo bloque seis veces.
export type Campo =
  | { tipo: 'fecha'; name: string; label: string }
  | { tipo: 'numero'; name: string; label: string }
  | { tipo: 'texto'; name: string; label: string; placeholder?: string }
  | { tipo: 'opciones'; name: string; label: string; opciones: Record<string, string>; todosLabel?: string }
  | { tipo: 'cliente'; name: string; label: string }
  | { tipo: 'sector'; name: string; label: string }
  | { tipo: 'categoria'; name: string; label: string; todosLabel?: string }

export type Grupo = 'equipos' | 'incidencias' | 'administracion'

export type Reporte = {
  slug: string
  titulo: string
  descripcion: string
  grupo: Grupo
  campos: Campo[]
  // Valores iniciales; los que no estén acá arrancan vacíos (= sin filtrar).
  inicial?: Record<string, string>
}

// El índice se arma a partir de esto, no de una lista aparte: agregar un
// reporte es agregarle su `grupo` y ya aparece en la sección que le toca.
export const GRUPOS: { id: Grupo; titulo: string; descripcion: string; icono: React.ReactNode }[] = [
  {
    id: 'equipos',
    titulo: 'Equipos',
    descripcion: 'El parque instalado: qué hay, dónde está y qué se le vence.',
    icono: <Monitor className="size-4" />,
  },
  {
    id: 'incidencias',
    titulo: 'Incidencias',
    descripcion: 'Los tickets del período y cómo se reparte el trabajo.',
    icono: <Ticket className="size-4" />,
  },
  {
    id: 'administracion',
    titulo: 'Administración',
    descripcion: 'Lo que hay para facturar.',
    icono: <Wallet className="size-4" />,
  },
]

const PERIODO: Campo[] = [
  { tipo: 'fecha', name: 'desde', label: 'Desde' },
  { tipo: 'fecha', name: 'hasta', label: 'Hasta' },
]

export const REPORTES: Reporte[] = [
  {
    slug: 'equipamiento',
    titulo: 'Equipamiento',
    descripcion: 'Parque instalado por cliente, con cantidad de incidencias y garantías vencidas resaltadas.',
    grupo: 'equipos',
    campos: [
      { tipo: 'cliente', name: 'cliente_id', label: 'Cliente' },
      { tipo: 'opciones', name: 'estado', label: 'Estado', opciones: ESTADO_EQUIPO_LABELS },
      { tipo: 'texto', name: 'tipo', label: 'Tipo', placeholder: 'Notebook, impresora…' },
    ],
  },
  {
    slug: 'incidencias-periodo',
    titulo: 'Incidencias por período',
    descripcion: 'Detalle de incidencias del período con totales de actividades y promedio de horas de resolución.',
    grupo: 'incidencias',
    campos: [
      ...PERIODO,
      { tipo: 'cliente', name: 'cliente_id', label: 'Cliente' },
      { tipo: 'opciones', name: 'estado', label: 'Estado', opciones: ESTADO_LABELS },
      { tipo: 'opciones', name: 'prioridad', label: 'Prioridad', opciones: PRIORIDAD_LABELS, todosLabel: 'Todas' },
      { tipo: 'sector', name: 'sector_id', label: 'Sector' },
      // Elegir una categoría raíz trae también sus subcategorías — lo resuelve
      // el backend, ver ReportesService.incidencias().
      { tipo: 'categoria', name: 'categoria_id', label: 'Categoría', todosLabel: 'Todas' },
      { tipo: 'texto', name: 'keyword', label: 'Búsqueda', placeholder: 'Título o descripción' },
    ],
  },
  {
    slug: 'facturacion',
    titulo: 'Facturación',
    descripcion: 'Incidencias cerradas de clientes por servicio, agrupadas por cliente. Los clientes con abono mensual no aparecen.',
    grupo: 'administracion',
    campos: [
      ...PERIODO,
      { tipo: 'cliente', name: 'cliente_id', label: 'Cliente' },
      { tipo: 'opciones', name: 'estado_facturacion', label: 'Cobro', opciones: COBRO_LABELS },
    ],
  },
  {
    slug: 'garantias',
    titulo: 'Garantías por vencer',
    descripcion: 'Equipos cuya garantía vence dentro del plazo indicado. Marca las ya vencidas y las que vencen en 14 días o menos.',
    grupo: 'equipos',
    campos: [
      { tipo: 'numero', name: 'dias', label: 'Próximos (días)' },
      { tipo: 'cliente', name: 'cliente_id', label: 'Cliente' },
    ],
    inicial: { dias: '60' },
  },
  {
    slug: 'tecnico',
    titulo: 'Por técnico',
    descripcion: 'Carga de trabajo por técnico: totales por estado, porcentaje de resolución y promedio de horas.',
    grupo: 'incidencias',
    campos: PERIODO,
  },
  {
    slug: 'movimientos',
    titulo: 'Movimientos de equipos',
    descripcion: 'Historial de altas, bajas y traslados, con origen y destino — sector del cliente o depósito.',
    grupo: 'equipos',
    campos: [
      ...PERIODO,
      { tipo: 'cliente', name: 'cliente_id', label: 'Cliente' },
    ],
  },
]

// Los tres volcados planos. Sin filtros: son la tabla entera. Se ven en
// pantalla y se bajan por las mismas dos rutas que los analíticos.
export const VOLCADOS: Reporte[] = [
  { slug: 'clientes', titulo: 'Clientes', descripcion: 'La tabla de clientes completa.', grupo: 'administracion', campos: [] },
  { slug: 'equipos', titulo: 'Equipos', descripcion: 'La tabla de equipos completa.', grupo: 'equipos', campos: [] },
  { slug: 'incidencias', titulo: 'Incidencias', descripcion: 'La tabla de incidencias completa.', grupo: 'incidencias', campos: [] },
]

export function buscarReporte(slug: string | undefined): Reporte | undefined {
  return [...REPORTES, ...VOLCADOS].find((r) => r.slug === slug)
}

export function valoresIniciales(r: Reporte): Record<string, string> {
  const base: Record<string, string> = {}
  for (const campo of r.campos) {
    if (campo.tipo === 'fecha') {
      base[campo.name] = campo.name === 'desde' ? firstOfMonthIso() : todayIso()
    } else if (
      campo.tipo === 'cliente' || campo.tipo === 'sector'
      || campo.tipo === 'categoria' || campo.tipo === 'opciones'
    ) {
      base[campo.name] = TODOS
    } else {
      base[campo.name] = ''
    }
  }
  return { ...base, ...r.inicial }
}

/** Los valores como query string, salteando lo que quedó "sin filtrar".
 *  Lo usan la consulta en pantalla y la descarga del Excel, así que las dos
 *  van con exactamente los mismos filtros. */
export function queryDeValores(valores: Record<string, string>): string {
  const params = new URLSearchParams()
  for (const [name, value] of Object.entries(valores)) {
    if (value && value !== TODOS) params.set(name, value)
  }
  return params.toString()
}
