// Cliente HTTP delgado sobre la API de LibraDesk. Cookie de sesion
// (ld_session) manejada por el browser via credentials:"include" -- en
// dev el proxy de Vite mantiene todo en el mismo origen, en produccion
// el build de este frontend se sirve desde el mismo proceso FastAPI (ver
// app/asgi.py). El cliente base (ApiError/api) y el tipo User vienen de
// libra-ui/api-client, mismo patron que el resto de la familia.

export { api, ApiError, type User } from 'libra-ui/api-client'

export type Cliente = {
  id: number
  nombre: string
  empresa: string | null
  email: string | null
  telefono: string | null
  ciudad: string | null
  observaciones: string | null
  tipo_facturacion: 'mensual' | 'por_servicio'
  activo: boolean
  fecha_creacion: string | null
}

export type Equipo = {
  id: number
  cliente_id: number
  tipo: string
  modelo: string | null
  marca: string | null
  serial: string | null
  ubicacion_oficina: string | null
  sector: string | null
  estado: string
  fecha_adicion: string | null
  garantia_vence: string | null
  observaciones: string | null
}

export type EquipoMovimiento = {
  id: number
  equipo_id: number
  tipo: string
  descripcion: string | null
  // El backend (MovimientoOut) siempre devolvió estos cuatro; faltaban acá
  // porque nada del frontend consumía el historial todavía.
  sector_origen: string | null
  sector_destino: string | null
  ubicacion_origen: string | null
  ubicacion_destino: string | null
  motivo: string | null
  usuario: string
  fecha: string | null
}

export type EstadoIncidencia = 'abierto' | 'en_progreso' | 'resuelta' | 'cerrado'
export type PrioridadIncidencia = 'alta' | 'media' | 'baja'

export const ESTADO_LABELS: Record<EstadoIncidencia, string> = {
  abierto: 'Abierto',
  en_progreso: 'En progreso',
  resuelta: 'Resuelta',
  cerrado: 'Cerrado',
}

export const PRIORIDAD_LABELS: Record<PrioridadIncidencia, string> = {
  alta: 'Alta',
  media: 'Media',
  baja: 'Baja',
}

export type Incidencia = {
  id: number
  cliente_id: number
  equipo_id: number | null
  tecnico_id: number | null
  sector_id: number | null
  titulo: string
  descripcion: string | null
  estado: EstadoIncidencia
  prioridad: PrioridadIncidencia
  horas_invertidas: number | null
  notas: string | null
  resolucion: string | null
  estado_facturacion: string | null
  activo: boolean
  fecha_creacion: string | null
  fecha_cierre: string | null
}

export type IncidenciaEstadoLog = {
  id: number
  incidencia_id: number
  estado_anterior: EstadoIncidencia | null
  estado_nuevo: EstadoIncidencia
  fecha: string | null
  tecnico: string | null
}

export type Actividad = {
  id: number
  incidencia_id: number
  fecha: string | null
  descripcion: string | null
  usuario: string | null
}

export type Tecnico = {
  id: number
  nombre: string
  activo: boolean
}

export type Sector = {
  id: number
  cliente_id: number
  nombre: string
}

export type DashboardSummary = {
  incidencias_por_estado: Record<string, number>
  incidencias_por_prioridad_abiertas: Record<string, number>
  incidencias_en_rango: number
  total_clientes_activos: number
  total_equipos: number
  horas_totales_invertidas: number
}
