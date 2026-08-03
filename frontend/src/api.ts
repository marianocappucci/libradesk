// Cliente HTTP delgado sobre la API de LibraDesk. Cookie de sesion
// (ld_session) manejada por el browser via credentials:"include" -- en
// dev el proxy de Vite mantiene todo en el mismo origen, en produccion
// el build de este frontend se sirve desde el mismo proceso FastAPI (ver
// app/asgi.py). El cliente base (ApiError/api) y el tipo User vienen de
// libra-ui/api-client, mismo patron que el resto de la familia.

export { api, ApiError, type User } from 'libra-ui/api-client'

import type { OpcionSelect } from 'libra-ui/SelectBuscable'

export type Cliente = {
  id: number
  nombre: string
  empresa: string | null
  email: string | null
  telefono: string | null
  ciudad: string | null
  // Datos fiscales, para que los comprobantes no obliguen a tipearlos cada
  // vez. Nulos en los 9 clientes migrados del Node.js viejo.
  cuit: string | null
  domicilio: string | null
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
  // El ticket que causó el movimiento, o null si fue una edición suelta
  // del equipo. Lo escribe la acción "Reemplazar equipo".
  incidencia_id: number | null
}

// Vivían duplicadas en Equipos.tsx; ahora las consumen también el timeline
// de la incidencia y el diálogo de reemplazo.
export const MOVIMIENTO_LABELS: Record<string, string> = {
  alta: 'Alta', baja: 'Baja', traslado: 'Traslado',
  en_reparacion: 'Reparación', almacenado: 'Almacenado', activo: 'Reactivado',
}

export const ESTADO_EQUIPO_LABELS: Record<string, string> = {
  activo: 'Activo', en_reparacion: 'En reparación', almacenado: 'En depósito', baja: 'Baja',
}

// Destino del equipo retirado en un reemplazo. El backend deriva de acá el
// estado y el sector por defecto (ver services/reemplazo.py, DESTINOS).
export type DestinoReemplazo = 'service' | 'deposito' | 'baja'

export const DESTINO_REEMPLAZO_LABELS: Record<DestinoReemplazo, string> = {
  service: 'Enviar a service',
  deposito: 'Volver a depósito',
  baja: 'Dar de baja',
}

export type ResultadoReemplazo = {
  retirado: Equipo
  sustituto: Equipo | null
  movimientos: EquipoMovimiento[]
  actividades: Actividad[]
  // La reparación que abrió el envío a service, y la que cerró la vuelta.
  // Las dos null cuando el reemplazo no tuvo nada que ver con service.
  reparacion: Reparacion | null
  reparacion_cerrada: Reparacion | null
}

// --- service / RMA ---------------------------------------------------------

export type Proveedor = {
  id: number
  nombre: string
  contacto: string | null
  telefono: string | null
  email: string | null
  observaciones: string | null
  activo: boolean
}

export type Reparacion = {
  id: number
  equipo_id: number
  incidencia_id: number | null
  proveedor_id: number
  // Resueltos por el backend, para que la lista no pida dos endpoints más
  // sólo para escribir un renglón.
  proveedor_nombre: string | null
  equipo_descripcion: string | null
  equipo_serial: string | null
  cliente_id: number | null
  fecha_envio: string | null
  // Null = el equipo sigue en service. El estado se deriva de esta fecha y no
  // hay columna `estado` que pueda contradecirla.
  fecha_retorno: string | null
  abierta: boolean
  // Con la reparación abierta se cuenta contra hoy: en la lista de abiertas
  // lo que interesa mirar es cuál se está demorando.
  dias_afuera: number | null
  remito_salida: string | null
  rma: string | null
  en_garantia: boolean
  costo: number | null
  diagnostico: string | null
  observaciones: string | null
  usuario: string
  // El sello con milisegundos, para ordenar la reparación dentro del timeline
  // del ticket. `fecha_envio` es un date que carga el usuario y puede ser de
  // hace una semana.
  created_at: string | null
}

export function opcionesProveedor(proveedores: Proveedor[]): OpcionSelect[] {
  return proveedores.map((p) => ({
    value: String(p.id),
    label: p.nombre,
    hint: [p.contacto, p.telefono].filter(Boolean).join(' · ') || undefined,
  }))
}

export function describirEquipo(e: Equipo | undefined): string {
  if (!e) return 'Equipo'
  return [e.tipo, e.marca, e.modelo].filter(Boolean).join(' ')
}

// --- opciones para los selects con búsqueda --------------------------------
//
// Viven acá, junto a los tipos, para que las cinco pantallas que eligen un
// cliente lo muestren y lo busquen igual. El `hint` no es decorativo: además
// de desambiguar dos clientes de nombre parecido, **entra en la búsqueda**,
// así se puede tipear la ciudad o la empresa.

export function opcionesCliente(clientes: Cliente[]): OpcionSelect[] {
  return clientes.map((c) => ({
    value: String(c.id),
    label: c.nombre,
    hint: [c.empresa, c.ciudad, c.activo ? null : 'inactivo']
      .filter(Boolean).join(' · ') || undefined,
  }))
}

export function opcionesEquipo(
  equipos: Equipo[],
  nombreCliente?: (id: number) => string,
): OpcionSelect[] {
  return equipos.map((e) => ({
    value: String(e.id),
    label: describirEquipo(e),
    // El serial es lo que se lee de la etiqueta del aparato cuando hay tres
    // impresoras del mismo modelo; el cliente, para no confundir parques.
    hint: [nombreCliente?.(e.cliente_id), e.serial].filter(Boolean).join(' · ') || undefined,
  }))
}

/** Para las entidades que sólo tienen nombre: técnicos y sectores. */
export function opcionesPorNombre(items: { id: number; nombre: string }[]): OpcionSelect[] {
  return items.map((i) => ({ value: String(i.id), label: i.nombre }))
}

export function ubicacionTexto(sector: string | null, ubicacion: string | null): string {
  return [sector, ubicacion].filter(Boolean).join(' · ') || 'sin ubicación'
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
  // Hoja del catálogo de categorías ("Hardware → Impresoras"). Null en las
  // incidencias previas al catálogo.
  categoria_id: number | null
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

// Catálogo de tipos de incidencia, de dos niveles y global (no por cliente,
// a diferencia de los sectores). `parent_id: null` = categoría raíz; una
// incidencia se clasifica siempre en una **hoja**.
export type CategoriaIncidencia = {
  id: number
  parent_id: number | null
  nombre: string
  parent_nombre: string | null
  // "Hardware · Impresoras" ya armado por el backend, para no rearmar el
  // árbol en cada pantalla que sólo quiere mostrar el nombre completo.
  ruta: string
}

/** Sólo las hojas: es lo único que se puede asignar a un ticket. Si una raíz
 *  no tiene hijas todavía, se ofrece ella misma — si no, crear la categoría y
 *  no poder usarla hasta agregarle una subcategoría desconcierta. */
export function categoriasAsignables(categorias: CategoriaIncidencia[]): CategoriaIncidencia[] {
  const conHijas = new Set(categorias.map((c) => c.parent_id).filter((id): id is number => id !== null))
  return categorias.filter((c) => c.parent_id !== null || !conHijas.has(c.id))
}

export function opcionesCategoria(categorias: CategoriaIncidencia[]): OpcionSelect[] {
  return categorias.map((c) => ({
    value: String(c.id),
    label: c.nombre,
    hint: c.parent_nombre ?? undefined,
  }))
}

// Remitos y presupuestos. Las columnas vienen tal cual de las tablas de
// libracore (en ingles, ver app/services/remitos_presupuestos.py): no se
// renombran para no divergir del dominio compartido con Contalibra/
// Restolibra, que es el que las lee y escribe.
export type ComprobanteItem = {
  description: string
  qty: number
  unit_price: number
  subtotal: number
}

type ComprobanteBase = {
  id: number
  number: string
  date: string
  client_id: number | null
  client_name: string
  client_address: string | null
  client_cuit: string | null
  client_email: string | null
  client_phone: string | null
  items: ComprobanteItem[]
  subtotal: number
  tax_rate: number
  tax_amount: number
  total: number
  observations: string | null
  pdf_path: string | null
  created_at: string | null
}

export type Remito = ComprobanteBase

export type EstadoPresupuesto = 'borrador' | 'enviado' | 'aceptado' | 'rechazado' | 'vencido'

export const ESTADO_PRESUPUESTO_LABELS: Record<EstadoPresupuesto, string> = {
  borrador: 'Borrador',
  enviado: 'Enviado',
  aceptado: 'Aceptado',
  rechazado: 'Rechazado',
  vencido: 'Vencido',
}

export type Presupuesto = ComprobanteBase & {
  valid_until: string
  status: EstadoPresupuesto
  remito_id: number | null
}

export type ConfigEmpresa = {
  empresa_nombre: string
  empresa_direccion: string
  empresa_cuit: string
  empresa_telefono: string
  empresa_email: string
  empresa_iibb: string
  empresa_iva_condition: string
  empresa_inicio_actividades: string
}

export type DashboardSummary = {
  incidencias_por_estado: Record<string, number>
  incidencias_por_prioridad_abiertas: Record<string, number>
  incidencias_en_rango: number
  total_clientes_activos: number
  total_equipos: number
  horas_totales_invertidas: number
}

// --- ficha del cliente (`/clientes/:id`) -----------------------------------
//
// El backend arma esto de una sola vez (GET /api/dashboard/cliente/{id}): son
// agregados y dos listas ya acotadas, no las tablas enteras a filtrar acá.

export type IncidenciaAbierta = {
  id: number
  titulo: string
  estado: EstadoIncidencia
  prioridad: PrioridadIncidencia
  fecha_creacion: string | null
  equipo_id: number | null
  equipo: string | null
  tecnico: string | null
}

export type GarantiaEquipo = {
  id: number
  descripcion: string
  serial: string | null
  sector: string | null
  ubicacion_oficina: string | null
  estado: string
  garantia_vence: string
  // Negativo si ya venció. El backend incluye las vencidas a propósito.
  dias_restantes: number
}

export type ClienteResumen = {
  cliente: Cliente
  equipos_por_estado: Record<string, number>
  total_equipos: number
  incidencias_por_estado: Record<string, number>
  total_incidencias: number
  incidencias_abiertas: IncidenciaAbierta[]
  garantias: GarantiaEquipo[]
  dias_garantia: number
  total_sectores: number
  horas_invertidas: number
}
