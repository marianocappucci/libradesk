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
  // Dónde está guardado. Null = instalado en el sector del cliente. El nombre
  // lo resuelve el backend para que la lista no cruce `/api/depositos`.
  deposito_id: number | null
  deposito_nombre: string | null
  estado: string
  fecha_adicion: string | null
  garantia_vence: string | null
  observaciones: string | null
}

// --- depósitos -------------------------------------------------------------
//
// `cliente_id: null` es un depósito **propio de la empresa**; con cliente es
// del cliente. Una sola entidad para los dos casos — ver
// app/services/depositos.py, que explica por qué.

export type Deposito = {
  id: number
  cliente_id: number | null
  cliente_nombre: string | null
  nombre: string
  descripcion: string | null
  activo: boolean
  // Sólo entre los propios: es a dónde va un equipo que "vuelve a depósito"
  // sin que nadie elija cuál.
  es_default: boolean
  total_equipos: number | null
  created_at: string | null
}

export type EquipoEnDeposito = Equipo & {
  descripcion: string
  cliente_nombre: string
}

export function opcionesDeposito(depositos: Deposito[]): OpcionSelect[] {
  return depositos.map((d) => ({
    value: String(d.id),
    label: d.nombre,
    // El dueño es lo que desambigua: "Depósito" propio y "Depósito" de un
    // cliente son dos lugares distintos con el mismo nombre.
    hint: [d.cliente_nombre ?? 'Empresa', d.activo ? null : 'inactivo']
      .filter(Boolean).join(' · ') || undefined,
  }))
}

/** Dónde está el equipo: el depósito si está guardado, si no su sector.
 *  Espejo de `lugar_de()` del backend — única definición de "dónde está". */
export function lugarDe(depositoNombre: string | null, sector: string | null): string | null {
  return depositoNombre || sector
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
  // Uno de los dos y sólo uno (fase 4): `equipo_id` es el parque del cliente,
  // `activo_id` el stock propio alquilado. `equipo_descripcion` y
  // `equipo_serial` los resuelve el backend para los dos casos, así que la
  // pantalla de service no tiene que distinguirlos para escribir un renglón.
  equipo_id: number | null
  activo_id: number | null
  es_activo: boolean
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

// --- alquiler y cesión de equipos ------------------------------------------
//
// `Activo` es el equipo NUESTRO, el que se entrega bajo contrato; `Equipo` es
// el parque del cliente. Son tablas distintas a propósito (ver
// `app/services/activos.py`): así el informe al cliente y los reportes, que
// cuentan `equipos`, no se llevan puesto el stock propio.

export type Activo = {
  id: number
  tipo: string
  marca: string | null
  modelo: string | null
  serial: string | null
  codigo_interno: string | null
  descripcion: string
  mac: string | null
  imei: string | null
  ip: string | null
  accesorios: string | null
  estado: string
  costo_compra: number | null
  fecha_compra: string | null
  proveedor_compra_id: number | null
  valor_reposicion: number | null
  garantia_vence: string | null
  observaciones: string | null
  created_at: string | null
  // Dónde está colocado, derivado de la línea de contrato abierta. Los cuatro
  // en null cuando el activo está en depósito.
  contrato_id: number | null
  contrato_numero: string | null
  cliente_id: number | null
  cliente_nombre: string | null
}

// `colocado` NO se setea a mano: lo escribe la colocación en un contrato. El
// backend rechaza un PUT que lo intente.
export const ESTADO_ACTIVO_LABELS: Record<string, string> = {
  disponible: 'Disponible',
  reservado: 'Reservado',
  en_instalacion: 'En instalación',
  colocado: 'Colocado',
  en_reparacion: 'En reparación',
  retirado_a_revisar: 'Retirado, a revisar',
  baja: 'Baja',
  perdido: 'Perdido',
}

/** Los que un formulario puede elegir — `colocado` queda afuera. */
export const ESTADOS_ACTIVO_MANUALES = Object.keys(ESTADO_ACTIVO_LABELS)
  .filter((e) => e !== 'colocado')

export type TipoContrato =
  | 'alquiler' | 'comodato' | 'prestamo' | 'incluido_en_servicio'
  | 'leasing' | 'venta_financiada'

export const TIPO_CONTRATO_LABELS: Record<TipoContrato, string> = {
  alquiler: 'Alquiler',
  comodato: 'Comodato',
  prestamo: 'Préstamo temporal',
  incluido_en_servicio: 'Incluido en el servicio',
  leasing: 'Leasing',
  venta_financiada: 'Venta financiada',
}

/** Los que llevan cuota. Los otros tres se entregan sin cobrar por el equipo,
 *  así que el backend rechaza un importe. */
export const TIPOS_CON_CUOTA: TipoContrato[] = ['alquiler', 'leasing', 'venta_financiada']

export const ESTADO_CONTRATO_LABELS: Record<string, string> = {
  borrador: 'Borrador',
  activo: 'Activo',
  suspendido: 'Suspendido',
  vencido: 'Vencido',
  rescindido: 'Rescindido',
  finalizado: 'Finalizado',
}

export const PERIODICIDAD_LABELS: Record<string, string> = {
  mensual: 'Mensual', bimestral: 'Bimestral', trimestral: 'Trimestral',
  semestral: 'Semestral', anual: 'Anual',
}

export const METODO_ACTUALIZACION_LABELS: Record<string, string> = {
  fijo: 'Precio fijo',
  manual: 'Actualización manual',
  porcentaje: 'Porcentaje cada N meses',
  // Declarado pero se comporta como manual hasta que se defina de dónde sale
  // el índice — decisión abierta del diseño.
  indice: 'Índice configurable',
  dolar: 'En dólares, convertido al facturar',
  lista: 'Lista de precios',
}

export type ContratoLinea = {
  id: number
  contrato_id: number
  activo_id: number
  activo_descripcion: string | null
  activo_serial: string | null
  activo_codigo_interno: string | null
  fecha_instalacion: string | null
  // Null = el activo sigue puesto. El estado se deriva de esta fecha.
  fecha_retiro: string | null
  vigente: boolean
  motivo_retiro: string | null
  // La línea a la que ésta sustituye. Es lo que hace que un reemplazo conserve
  // el equipo anterior en vez de pisarlo.
  reemplaza_a_id: number | null
  tecnico_instalador_id: number | null
  incidencia_id: number | null
  ubicacion: string | null
  observaciones: string | null
  // Sólo en el historial de un activo.
  contrato_numero?: string | null
  tipo_contrato?: string | null
  cliente_id?: number | null
  cliente_nombre?: string | null
}

export type ContratoPrecio = {
  id: number
  contrato_id: number
  vigencia_desde: string | null
  vigencia_hasta: string | null
  vigente: boolean
  importe: number | null
  moneda: string
  motivo: string | null
  usuario: string
  created_at: string | null
}

export type Contrato = {
  id: number
  numero: string
  tipo_contrato: TipoContrato
  cliente_id: number
  cliente_nombre: string | null
  propietario_cliente_id: number | null
  propietario_nombre: string | null
  sector_id: number | null
  domicilio_instalacion: string | null
  fecha_inicio: string | null
  fecha_fin: string | null
  renovacion_automatica: boolean
  periodicidad: string
  dia_vencimiento: number | null
  moneda: string
  metodo_actualizacion: string
  estado: string
  responsable: string | null
  observaciones: string | null
  archivo_pdf: string | null
  created_at: string | null
  // Derivados: el importe NO es una columna del contrato, sale del precio
  // vigente en `contratos_precios`.
  importe_vigente: number | null
  precio_vigente_desde: string | null
  lleva_cuota: boolean
  equipos_vigentes: number
  // Sólo en la ficha (`GET /api/contratos/{id}`), no en el listado.
  lineas?: ContratoLinea[]
  precios?: ContratoPrecio[]
}

export type ResumenActivos = {
  total: number
  por_estado: Record<string, number>
}

/** A dónde se manda el activo que sale. Viaja DENTRO del retiro o del
 *  reemplazo: sacarlo y registrar a dónde se lo mandó son el mismo hecho. */
export type ServicePayload = {
  proveedor_id: number
  fecha_envio: string
  remito_salida?: string | null
  rma?: string | null
  en_garantia?: boolean
  observaciones?: string | null
}

/** La vuelta del que entra: cierra su reparación abierta. */
export type CierreServicePayload = {
  fecha_retorno: string
  diagnostico?: string | null
  costo?: number | null
}

/** Un hito de la línea de tiempo de un activo: contrato, movimiento o service.
 *  Las tres fuentes vienen unidas porque por separado ninguna cuenta el
 *  recorrido completo. */
export type HitoActivo = {
  clase: 'contrato' | 'movimiento' | 'service'
  fecha: string | null
  titulo: string | null
  detalle: string | null
  contrato_id?: number
  linea_id?: number
  movimiento_id?: number
  reparacion_id?: number
  incidencia_id?: number | null
  vigente?: boolean
  abierta?: boolean
}

export function describirActivo(a: Activo | undefined): string {
  if (!a) return 'Activo'
  return a.descripcion || [a.tipo, a.marca, a.modelo].filter(Boolean).join(' ')
}

export function opcionesActivo(activos: Activo[]): OpcionSelect[] {
  return activos.map((a) => ({
    value: String(a.id),
    label: describirActivo(a),
    // El serial y el código patrimonial son lo que se lee de la etiqueta
    // cuando hay seis teléfonos del mismo modelo en el depósito.
    hint: [a.serial, a.codigo_interno].filter(Boolean).join(' · ') || undefined,
  }))
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

export type ModalidadIncidencia = 'on_site' | 'remoto'

export const MODALIDAD_LABELS: Record<ModalidadIncidencia, string> = {
  on_site: 'On-site',
  remoto: 'Remoto',
}

export type Incidencia = {
  id: number
  cliente_id: number
  equipo_id: number | null
  // El activo alquilado afectado, si el problema es de un equipo nuestro.
  activo_id: number | null
  // Los tres papeles alrededor del ticket: quien lo **ejecuta**, quien lo
  // **recepciona** y quien **vende**. Los tres apuntan al mismo catálogo de
  // personal (`/api/tecnicos`), filtrable por rol.
  tecnico_id: number | null
  recepcionista_id: number | null
  vendedor_id: number | null
  // Null en los tickets anteriores al pedido 37: no saben cómo se atendieron.
  modalidad: ModalidadIncidencia | null
  sector_id: number | null
  // Hoja del catálogo de categorías ("Hardware → Impresoras"). Null en las
  // incidencias previas al catálogo.
  categoria_id: number | null
  // La agenda (pedido 42, fase B). Los tres null si el ticket no se agenda —
  // agendar es opcional. `fecha_programada` es **cuándo se va a atender**, y no
  // tiene nada que ver con `fecha_creacion`.
  fecha_programada: string | null
  duracion_minutos: number | null
  /** El equipo de trabajo que sale. El vehículo no se elige acá: sale de lo que
   *  ese equipo tenga asignado (fase A). */
  equipo_trabajo_id: number | null
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

/** El **personal** de la empresa. El tipo conserva el nombre `Tecnico` porque
 *  la tabla y la ruta (`/api/tecnicos`) también lo conservan — ver el docstring
 *  de `app/services/tecnicos.py`. En la UI el módulo se llama "Personal".
 *
 *  Los roles son banderas independientes: la misma persona puede ser técnica y
 *  vendedora, que es el caso normal en una empresa chica. */
export type Tecnico = {
  id: number
  nombre: string
  activo: boolean
  es_tecnico: boolean
  es_recepcionista: boolean
  es_vendedor: boolean
  /** Quien manda un equipo de trabajo (pedido 42). */
  es_responsable: boolean
  /** Derivado por el backend, para no armar el texto en cada fila. */
  roles: string[]
}

export const ROL_LABELS: Record<string, string> = {
  tecnico: 'Técnico',
  recepcionista: 'Recepcionista',
  vendedor: 'Vendedor',
  responsable: 'Responsable de equipo',
}

// --- equipos de trabajo y flota (pedido 42, fase A) -----------------------

export type EquipoTrabajo = {
  id: number
  nombre: string
  responsable_id: number | null
  responsable_nombre: string | null
  observaciones: string | null
  activo: boolean
  created_at: string | null
  integrantes: { id: number; nombre: string }[]
  /** Plural aunque hoy lo normal sea uno: nada impide que una cuadrilla salga
   *  con dos vehículos, y el modelo ya lo admite. */
  vehiculos: Vehiculo[]
}

export type Vehiculo = {
  id: number
  patente: string
  marca: string | null
  modelo: string | null
  anio: number | null
  /** `asignado` NO se setea a mano: lo escribe la asignación a un equipo. */
  estado: string
  equipo_id: number | null
  equipo_nombre: string | null
  descripcion: string
  observaciones: string | null
  created_at: string | null
}

export const ESTADO_VEHICULO_LABELS: Record<string, string> = {
  disponible: 'Disponible',
  asignado: 'Asignado',
  en_taller: 'En taller',
  baja: 'Baja',
}

/** Los que un formulario puede elegir — `asignado` queda afuera. */
export const ESTADOS_VEHICULO_MANUALES = Object.keys(ESTADO_VEHICULO_LABELS)
  .filter((e) => e !== 'asignado')

export function opcionesVehiculo(vehiculos: Vehiculo[]): OpcionSelect[] {
  return vehiculos.map((v) => ({
    value: String(v.id),
    label: v.patente,
    hint: v.descripcion !== v.patente ? v.descripcion : undefined,
  }))
}

// --- ingresos a reparación (pedido 43) ------------------------------------
//
// El equipo del cliente en nuestro poder, de la recepción a la entrega. **Una
// fila por episodio de custodia**, no dos comprobantes enlazados: `fecha_entrega
// null` es "sigue en el taller" y no puede mentir, y el vínculo entre los dos
// papeles es estructural en vez de una FK que se puede apuntar mal.
//
// Los cuatro campos del equipo están **congelados** en el comprobante, no leídos
// del inventario: si mañana se corrige el modelo en `equipos`, el papel que el
// cliente firmó no puede cambiar. Ver `app/services/ingresos.py`.

export type IngresoReparacion = {
  id: number
  numero: string
  fecha_recepcion: string | null
  cliente_id: number
  cliente_nombre: string | null
  contacto: string | null
  contacto_telefono: string | null
  /** Null si es un equipo de mostrador que no está en el inventario. */
  equipo_id: number | null
  equipo_tipo: string
  equipo_marca: string | null
  equipo_modelo: string | null
  equipo_serial: string | null
  /** Armada por el backend, para no repetir el join de strings en cada fila. */
  equipo_descripcion: string
  accesorios: string | null
  estado_fisico: string | null
  falla_declarada: string | null
  observaciones: string | null
  tecnico_id: number | null
  tecnico_nombre: string | null
  entregado_por: string | null
  incidencia_id: number | null
  // La entrega. Todo null mientras el equipo siga acá.
  numero_entrega: string | null
  fecha_entrega: string | null
  retirado_por: string | null
  trabajo_realizado: string | null
  observaciones_entrega: string | null
  tecnico_entrega_id: number | null
  tecnico_entrega_nombre: string | null
  /** Derivados por el backend, nunca almacenados. */
  en_taller: boolean
  dias_en_taller: number | null
  usuario: string
  created_at: string | null
}

// --- agenda de equipos (pedido 42, fase B) --------------------------------
//
// Una fila por trabajo agendado, ya resuelta por el backend: el nombre del
// cliente, el `hasta` calculado y las patentes del equipo. La pantalla no
// cruza tres endpoints para armar una grilla horaria.

export type TrabajoAgendado = {
  incidencia_id: number
  titulo: string
  cliente_id: number | null
  cliente_nombre: string | null
  estado: EstadoIncidencia
  modalidad: ModalidadIncidencia | null
  desde: string
  hasta: string
  duracion_minutos: number
  /** En qué sale el equipo. Derivado de la asignación de la fase A, no
   *  guardado en el ticket: si mañana el equipo cambia de vehículo, la agenda
   *  dice el nuevo sin tocar nada. */
  vehiculos: string[]
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

/** Un backup guardado en el servidor. Lo devuelve `GET /api/config/backups`
 *  (LibraCore v1.10.0).
 *
 *  **Es un ZIP con las bases y los archivos de la instancia**, no un `.db`
 *  suelto: acá la base es una sola, pero en Gestiolibra, MedLibra y VentaLibra
 *  son dos, y en MedLibra van además los documentos clínicos. El formato es el
 *  mismo en los seis a propósito. */
export type BackupGuardado = {
  filename: string
  size_mb: number
  mtime: string
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

// --- ficha del equipo (`/equipos/:id`) -------------------------------------
//
// Una sola llamada (GET /api/dashboard/equipo/{id}) con las cuatro cosas que
// la pantalla necesita: el equipo, **de quién es**, los totales y las tres
// historias. Antes eran tres endpoints y el cliente no venía en ninguno.

export type IncidenciaDeEquipo = {
  id: number
  titulo: string
  estado: EstadoIncidencia
  prioridad: PrioridadIncidencia
  categoria: string | null
  tecnico: string | null
  horas_invertidas: number
  fecha_creacion: string | null
  fecha_cierre: string | null
  resolucion: string | null
}

export type EquipoFicha = {
  equipo: Equipo & {
    descripcion: string
    // Dónde está, ya resuelto por el backend (depósito o sector).
    lugar: string | null
    dias_garantia_restantes: number | null
  }
  cliente: {
    id: number
    nombre: string
    empresa: string | null
    telefono: string | null
    email: string | null
    ciudad: string | null
    activo: boolean
  } | null
  resumen: {
    total_incidencias: number
    incidencias_abiertas: number
    horas_invertidas: number
    total_reparaciones: number
    reparaciones_abiertas: number
    // Lo que contesta "¿lo reemplazo o lo sigo arreglando?".
    gastado_reparaciones: number
    dias_en_service: number
    total_movimientos: number
  }
  incidencias: IncidenciaDeEquipo[]
  reparaciones: Reparacion[]
  movimientos: EquipoMovimiento[]
}

// --- reportes en pantalla --------------------------------------------------
//
// El backend manda el reporte ya armado (columnas, filas, resaltados y
// totales) y esta pantalla sólo lo dibuja. Es la MISMA definición con la que
// se genera el .xlsx — ver app/services/reporte_vista.py: si las columnas se
// declararan también acá, agregar una al Excel y olvidarse de la pantalla
// daría dos reportes distintos con el mismo nombre.

export type CeldaReporte = {
  texto: string | null
  // Resaltado semántico, no un color: cada salida lo traduce a lo suyo.
  marca: string | null
}

export type VistaReporte = {
  slug: string
  titulo: string
  filtros: string[]
  generado: string
  cantidad_filas: number
  columnas: { label: string; numerica: boolean }[]
  // `etiqueta: null` es la tabla plana; con etiqueta es un bloque agrupado
  // (hoy sólo Facturación, agrupada por cliente).
  grupos: { etiqueta: string | null; filas: CeldaReporte[][] }[]
  totales: CeldaReporte[] | null
}

/** Las ocho marcas del backend a clases de Tailwind. Los mismos ocho colores
 *  que el Excel pinta como relleno de celda, para que lo que se ve en pantalla
 *  y lo que se baja sean reconociblemente el mismo reporte. */
export const MARCA_CLASE: Record<string, string> = {
  ok: 'bg-emerald-100 dark:bg-emerald-950/60',
  peligro: 'bg-red-100 dark:bg-red-950/60',
  atencion: 'bg-orange-200 dark:bg-orange-950/60',
  carga: 'bg-orange-100 dark:bg-orange-950/40',
  urgente: 'bg-yellow-100 dark:bg-yellow-950/60',
  info: 'bg-violet-100 dark:bg-violet-950/60',
  nuevo: 'bg-blue-100 dark:bg-blue-950/60',
  neutro: 'bg-gray-100 dark:bg-gray-800/60',
}

// --- logs (admin) ----------------------------------------------------------
//
// Los tipos viven en libra-ui junto a la pantalla (v0.12.0): la respuesta la
// arma `libraauth.auditoria.build_logs_router()`, que es del motor, no de este
// producto.
export type { ActividadLog, AccesoLog, LogsData } from 'libra-ui/Logs'

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
