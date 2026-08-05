import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  api, ApiError, DESTINO_REEMPLAZO_LABELS, ESTADO_LABELS, MODALIDAD_LABELS,
  MOVIMIENTO_LABELS,
  PRIORIDAD_LABELS, categoriasAsignables, describirEquipo, ubicacionTexto,
  opcionesCategoria, opcionesCliente, opcionesEquipo, opcionesPorNombre,
  opcionesProveedor,
  type Actividad, type CategoriaIncidencia, type Cliente, type DestinoReemplazo,
  type Equipo, type EquipoMovimiento, type EquipoTrabajo, type Incidencia,
  type IncidenciaEstadoLog,
  type ModalidadIncidencia, type Proveedor, type Reparacion, type Sector,
  type Tecnico,
} from '../api'
import { deIsoALocal, deLocalAIso } from '@/lib/format'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { SelectBuscable } from '@/components/select-buscable'
import { ConfirmDialog } from '@/components/confirm-dialog'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  ArrowLeft, ArrowLeftRight, Check, History, MessageSquare, PackageCheck,
  Printer, ShieldCheck, Trash2, Wrench,
} from 'lucide-react'

const NONE = '__none__'

type TimelineEntry =
  | { tipo: 'actividad'; fecha: string; data: Actividad }
  | { tipo: 'estado'; fecha: string; data: IncidenciaEstadoLog }
  // Tercera fuente: lo que este ticket le hizo al inventario. Antes el
  // timeline solo tenía notas y cambios de estado, así que "se retiró la
  // impresora" aparecía únicamente si alguien lo escribía a mano.
  | { tipo: 'movimiento'; fecha: string; data: EquipoMovimiento }
  // Cuarta fuente: el paso por service. Se ancla en `created_at` y no en
  // `fecha_envio`, que es un date que carga el usuario y puede ser de hace una
  // semana — ordenar por ahí pondría la salida a service antes del retiro que
  // la causó.
  | { tipo: 'reparacion'; fecha: string; data: Reparacion }

function formatFecha(fecha: string | null): string {
  if (!fecha) return '—'
  return new Date(fecha).toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' })
}

export function IncidenciaDetalle() {
  const { id } = useParams<{ id: string }>()
  const incidenciaId = Number(id)
  const navigate = useNavigate()

  const [incidencia, setIncidencia] = useState<Incidencia | null>(null)
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [equipos, setEquipos] = useState<Equipo[]>([])
  const [tecnicos, setTecnicos] = useState<Tecnico[]>([])
  const [sectores, setSectores] = useState<Sector[]>([])
  const [categorias, setCategorias] = useState<CategoriaIncidencia[]>([])
  const [actividades, setActividades] = useState<Actividad[]>([])
  const [estados, setEstados] = useState<IncidenciaEstadoLog[]>([])
  const [movimientos, setMovimientos] = useState<EquipoMovimiento[]>([])
  const [reparaciones, setReparaciones] = useState<Reparacion[]>([])
  const [equiposTrabajo, setEquiposTrabajo] = useState<EquipoTrabajo[]>([])
  // Las abiertas de TODOS los tickets, no sólo las de éste: el equipo que
  // vuelve de service pudo haber salido por otro ticket, y en ese caso su
  // reparación no está en `reparaciones` — el diálogo no ofrecería cerrarla.
  const [abiertas, setAbiertas] = useState<Reparacion[]>([])
  const [proveedores, setProveedores] = useState<Proveedor[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notaTexto, setNotaTexto] = useState('')
  const [guardandoNota, setGuardandoNota] = useState(false)
  // Estado del guardado automático, para que deje de ser invisible (pedido 40).
  // `enVuelo` es un ref y no estado porque `guardarYVolver` lo lee dentro de un
  // bucle: con `useState` leería siempre el valor del render en que se creó.
  const enVuelo = useRef(0)
  const [guardando, setGuardando] = useState(false)
  const [guardadoAt, setGuardadoAt] = useState<Date | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [reemplazoAbierto, setReemplazoAbierto] = useState(false)
  const [reemplazando, setReemplazando] = useState(false)
  const [reemplazo, setReemplazo] = useState({
    retirado: NONE, sustituto: NONE, destino: 'service' as DestinoReemplazo, motivo: '',
    // Bloque de service: sólo viaja con destino "service". El backend rechaza
    // lo contrario en vez de ignorarlo en silencio — quien cargó proveedor y
    // RMA creía que iban a alguna parte.
    proveedor: NONE, fechaEnvio: '', remito: '', rma: '', enGarantia: false,
    // Y la vuelta, que se ofrece cuando el equipo que ENTRA tiene una
    // reparación abierta: la vuelta del service es este mismo reemplazo al
    // revés, así que el que vuelve es el sustituto.
    cerrarService: true, fechaRetorno: '', diagnostico: '', costo: '',
  })

  useEffect(() => {
    cargar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incidenciaId])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  /** El personal que tiene ese rol, más el que ya está asignado al ticket.
   *
   * Lo segundo importa: si a alguien se le saca el rol de vendedor después de
   * haber quedado en un ticket, el selector mostraría vacío y el dato se vería
   * como perdido. Se lo sigue ofreciendo mientras esté puesto ahí. */
  function conRol(rol: 'tecnico' | 'recepcionista' | 'vendedor'): Tecnico[] {
    const asignado = {
      tecnico: incidencia?.tecnico_id,
      recepcionista: incidencia?.recepcionista_id,
      vendedor: incidencia?.vendedor_id,
    }[rol]
    return tecnicos.filter(
      (t) => t[`es_${rol}` as const] || t.id === asignado,
    )
  }

  async function cargar() {
    setLoading(true)
    setError(null)
    try {
      const [inc, cl, eq, te, se, cat, act, est, mov, rep, abi, prov, et] = await Promise.all([
        api.get<Incidencia>(`/api/incidencias/${incidenciaId}`),
        api.get<Cliente[]>('/api/clientes'),
        api.get<Equipo[]>('/api/equipos'),
        api.get<Tecnico[]>('/api/tecnicos'),
        api.get<Sector[]>('/api/sectores'),
        api.get<CategoriaIncidencia[]>('/api/categorias'),
        api.get<Actividad[]>(`/api/incidencias/${incidenciaId}/actividades`),
        api.get<IncidenciaEstadoLog[]>(`/api/incidencias/${incidenciaId}/estados`),
        api.get<EquipoMovimiento[]>(`/api/incidencias/${incidenciaId}/movimientos`),
        api.get<Reparacion[]>(`/api/reparaciones?incidencia_id=${incidenciaId}`),
        api.get<Reparacion[]>('/api/reparaciones?abiertas=true'),
        api.get<Proveedor[]>('/api/proveedores?solo_activos=true'),
        api.get<EquipoTrabajo[]>('/api/equipos-trabajo'),
      ])
      setIncidencia(inc)
      setClientes(cl)
      setEquipos(eq)
      setTecnicos(te)
      setSectores(se)
      setCategorias(cat)
      setActividades(act)
      setEstados(est)
      setMovimientos(mov)
      setReparaciones(rep)
      setAbiertas(abi)
      setProveedores(prov)
      setEquiposTrabajo(et)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function recargarActividadYEstado() {
    const [act, est] = await Promise.all([
      api.get<Actividad[]>(`/api/incidencias/${incidenciaId}/actividades`),
      api.get<IncidenciaEstadoLog[]>(`/api/incidencias/${incidenciaId}/estados`),
    ])
    setActividades(act)
    setEstados(est)
  }

  // Guarda un campo apenas cambia — mismo patrón que el panel de propiedades de
  // Zendesk/Freshdesk. Reconstruye el payload completo a partir del estado
  // actual porque el backend (`IncidenciaIn`) espera el objeto entero en el PUT.
  //
  // 🔴 **El guardado automático se queda, pero deja de ser invisible.** El
  // usuario reportó (pedido 40) que "no hay botón de guardar; si salgo queda
  // guardada, pero no es la idea". El problema no era que no guardara: era que
  // no había forma de saberlo ni de terminar. Sacar el autoguardado habría
  // perdido lo tipeado al navegar, así que se suma lo que faltaba — un
  // indicador de estado y un botón explícito que cierra y vuelve al listado.
  async function actualizarCampo(patch: Partial<Incidencia>) {
    if (!incidencia) return
    setError(null)
    const previo = incidencia
    const actualizado = { ...incidencia, ...patch }
    setIncidencia(actualizado)
    enVuelo.current += 1
    setGuardando(true)
    try {
      const guardado = await api.put<Incidencia>(`/api/incidencias/${incidenciaId}`, {
        cliente_id: actualizado.cliente_id,
        equipo_id: actualizado.equipo_id,
        activo_id: actualizado.activo_id,
        tecnico_id: actualizado.tecnico_id,
        recepcionista_id: actualizado.recepcionista_id,
        vendedor_id: actualizado.vendedor_id,
        modalidad: actualizado.modalidad,
        // Los tres de la agenda tienen que viajar en **todo** PUT, aunque el
        // cambio no los toque: el backend recibe el objeto entero y lo que no
        // se manda vuelve a null. Sin esta línea, cambiarle la prioridad a un
        // ticket lo desagendaba en silencio.
        fecha_programada: actualizado.fecha_programada,
        duracion_minutos: actualizado.duracion_minutos,
        equipo_trabajo_id: actualizado.equipo_trabajo_id,
        sector_id: actualizado.sector_id,
        categoria_id: actualizado.categoria_id,
        titulo: actualizado.titulo,
        descripcion: actualizado.descripcion,
        estado: actualizado.estado,
        prioridad: actualizado.prioridad,
        horas_invertidas: actualizado.horas_invertidas,
        notas: actualizado.notas,
        resolucion: actualizado.resolucion,
        estado_facturacion: null,
        activo: true,
      })
      setIncidencia(guardado)
      setGuardadoAt(new Date())
      if (patch.estado) await recargarActividadYEstado()
    } catch (err) {
      setIncidencia(previo)
      setError(describeError(err))
    } finally {
      enVuelo.current -= 1
      if (enVuelo.current === 0) setGuardando(false)
    }
  }

  /** Cierra la ficha y vuelve al listado, **después** de que termine de guardar.
   *
   * Los dos pasos importan y los dos costaron el reporte del usuario:
   *
   * 1. El `blur()` fuerza el `onBlur` del campo que tenga el foco. Sin esto, lo
   *    último tipeado se pierde: el botón navega antes de que ese campo dispare
   *    su guardado.
   * 2. La espera a `enVuelo` cubre el PUT ya lanzado. Navegar desmonta el
   *    componente y la respuesta llega a un componente que ya no existe.
   */
  async function guardarYVolver() {
    (document.activeElement as HTMLElement | null)?.blur()
    // Un tick para que el `onBlur` corra y alcance a incrementar `enVuelo`.
    await new Promise((r) => setTimeout(r, 0))
    // Con tope: si un PUT quedara colgado, la pantalla no puede quedar presa.
    for (let i = 0; enVuelo.current > 0 && i < 100; i++) {
      await new Promise((r) => setTimeout(r, 25))
    }
    navigate('/incidencias')
  }

  async function agregarNota() {
    if (!notaTexto.trim()) return
    setGuardandoNota(true)
    setError(null)
    try {
      await api.post(`/api/incidencias/${incidenciaId}/actividades`, { descripcion: notaTexto.trim() })
      setNotaTexto('')
      await recargarActividadYEstado()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setGuardandoNota(false)
    }
  }

  async function eliminar() {
    try {
      await api.del(`/api/incidencias/${incidenciaId}`)
      navigate('/incidencias')
    } catch (err) {
      setError(describeError(err))
    }
  }

  // Empate de fechas: las tres tablas usan CURRENT_TIMESTAMP, que en SQLite
  // tiene resolución de un segundo, así que dos entradas de la misma
  // operación empatan seguido. Sin desempate el orden queda a merced del
  // orden de concatenación (que además viene DESC de la API) y la historia
  // se lee al revés. El id ascendente dentro de cada fuente es el orden real
  // de inserción.
  const rangoPorTipo = { actividad: 0, reparacion: 1, movimiento: 2, estado: 3 }
  const timeline: TimelineEntry[] = [
    ...actividades.map((a): TimelineEntry => ({ tipo: 'actividad', fecha: a.fecha ?? '', data: a })),
    ...estados.map((e): TimelineEntry => ({ tipo: 'estado', fecha: e.fecha ?? '', data: e })),
    ...movimientos.map((m): TimelineEntry => ({ tipo: 'movimiento', fecha: m.fecha ?? '', data: m })),
    ...reparaciones.map((r): TimelineEntry => ({ tipo: 'reparacion', fecha: r.created_at ?? '', data: r })),
  ].sort((a, b) =>
    new Date(a.fecha).getTime() - new Date(b.fecha).getTime()
    || rangoPorTipo[a.tipo] - rangoPorTipo[b.tipo]
    || a.data.id - b.data.id,
  )

  const equiposDelCliente = incidencia ? equipos.filter((e) => e.cliente_id === incidencia.cliente_id) : []
  // Sólo hojas: un ticket se clasifica en "Impresoras", no en "Hardware" a
  // secas. La única excepción son las raíces que todavía no tienen hijas.
  const categoriasElegibles = categoriasAsignables(categorias)
  const equipoPorId = (id: number) => equipos.find((e) => e.id === id)

  // El bloque de service sólo tiene sentido si el equipo efectivamente sale a
  // reparar. Con "volver a depósito" o "dar de baja", cargar proveedor y RMA
  // describiría algo que no pasó — y el backend lo rechaza, no lo ignora.
  const mostrarBloqueService = reemplazo.destino === 'service'
  // La vuelta: si el equipo que ENTRA está hoy en service, es porque está
  // volviendo. No hay que preguntarlo, se deduce del estado del inventario.
  const reparacionDelSustituto = reemplazo.sustituto === NONE
    ? undefined
    : abiertas.find((r) => r.equipo_id === Number(reemplazo.sustituto))

  function abrirReemplazo() {
    const hoy = new Date().toISOString().slice(0, 10)
    setReemplazo({
      // Por defecto se retira el equipo del ticket, que es el caso normal.
      retirado: incidencia?.equipo_id ? String(incidencia.equipo_id) : NONE,
      sustituto: NONE,
      destino: 'service',
      motivo: '',
      proveedor: NONE, fechaEnvio: hoy, remito: '', rma: '', enGarantia: false,
      cerrarService: true, fechaRetorno: hoy, diagnostico: '', costo: '',
    })
    setReemplazoAbierto(true)
  }

  async function confirmarReemplazo() {
    if (reemplazo.retirado === NONE) return
    setReemplazando(true)
    setError(null)
    try {
      await api.post(`/api/incidencias/${incidenciaId}/reemplazar-equipo`, {
        equipo_retirado_id: Number(reemplazo.retirado),
        equipo_sustituto_id: reemplazo.sustituto === NONE ? null : Number(reemplazo.sustituto),
        destino: reemplazo.destino,
        motivo: reemplazo.motivo.trim() || null,
        // El proveedor es lo único obligatorio del bloque: sin él la reparación
        // no identifica a dónde fue el equipo, que es todo el punto de
        // registrarla. Sin proveedor elegido el reemplazo funciona como antes.
        service: mostrarBloqueService && reemplazo.proveedor !== NONE ? {
          proveedor_id: Number(reemplazo.proveedor),
          fecha_envio: reemplazo.fechaEnvio,
          remito_salida: reemplazo.remito.trim() || null,
          rma: reemplazo.rma.trim() || null,
          en_garantia: reemplazo.enGarantia,
        } : null,
        cierre_service: reparacionDelSustituto && reemplazo.cerrarService ? {
          fecha_retorno: reemplazo.fechaRetorno,
          diagnostico: reemplazo.diagnostico.trim() || null,
          costo: reemplazo.costo ? Number(reemplazo.costo) : null,
        } : null,
      })
      setReemplazoAbierto(false)
      // Recarga completa: la operación tocó equipos, movimientos y actividad.
      await cargar()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setReemplazando(false)
    }
  }

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button asChild size="sm" variant="outline"><Link to="/incidencias"><ArrowLeft />Volver</Link></Button>
          {incidencia && (
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              {incidencia.titulo}
              <Badge variant={incidencia.estado === 'cerrado' || incidencia.estado === 'resuelta' ? 'default' : 'outline'}>
                {ESTADO_LABELS[incidencia.estado]}
              </Badge>
              <Badge variant={incidencia.prioridad === 'alta' ? 'destructive' : 'outline'}>
                {PRIORIDAD_LABELS[incidencia.prioridad]}
              </Badge>
            </h2>
          )}
        </div>
        {incidencia && (
          <div className="flex flex-wrap items-center gap-2">
            {/* El estado del guardado automático, a la vista. Sin esto el
                usuario no tenía forma de saber si lo que tipeó quedó. */}
            <span className="text-xs text-muted-foreground" aria-live="polite">
              {guardando
                ? 'Guardando…'
                : guardadoAt
                  ? `Guardado ${guardadoAt.toLocaleTimeString('es-AR', { timeStyle: 'short' })}`
                  : 'Los cambios se guardan solos'}
            </span>
            <Button size="sm" variant="outline" asChild>
              <a href={`/api/incidencias/${incidenciaId}/pdf`} target="_blank" rel="noreferrer">
                <Printer />Imprimir
              </a>
            </Button>
            <Button size="sm" variant="outline" onClick={abrirReemplazo}>
              <ArrowLeftRight />Reemplazar equipo
            </Button>
            <Button size="sm" variant="outline" className="text-destructive hover:text-destructive" onClick={() => setConfirmDelete(true)}>
              <Trash2 />Eliminar
            </Button>
            {/* El botón que faltaba: termina el trabajo y vuelve al listado.
                🔴 **No lleva `disabled={guardando}`**, aunque parezca lo
                natural. El click del usuario primero hace `blur` en el campo
                que estaba editando, ese blur dispara el guardado y `guardando`
                pasa a true — así que para cuando llega el `click` el botón ya
                está deshabilitado y el handler **nunca corre**. Es decir: se
                rompía exactamente en el caso para el que existe (tipear algo y
                tocar guardar). Lo agarró el test de "espera a que termine el
                guardado". La espera la hace `guardarYVolver`, no el disabled. */}
            <Button size="sm" onClick={guardarYVolver}>
              <Check />{guardando ? 'Guardando…' : 'Guardar y volver'}
            </Button>
          </div>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading || !incidencia ? (
        <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="grid gap-4 md:col-span-2">
            <Card>
              <CardHeader><CardTitle className="text-base">Detalle</CardTitle></CardHeader>
              <CardContent className="grid gap-3">
                <div className="grid gap-1.5">
                  <Label>Título</Label>
                  <Input
                    defaultValue={incidencia.titulo}
                    onBlur={(e) => e.target.value.trim() && e.target.value !== incidencia.titulo && actualizarCampo({ titulo: e.target.value.trim() })}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label>Descripción</Label>
                  <textarea
                    defaultValue={incidencia.descripcion ?? ''}
                    rows={3}
                    className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs"
                    onBlur={(e) => e.target.value !== (incidencia.descripcion ?? '') && actualizarCampo({ descripcion: e.target.value || null })}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">Actividad</CardTitle></CardHeader>
              <CardContent className="grid gap-3">
                {timeline.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Sin actividad todavía.</p>
                ) : (
                  <div className="grid gap-2">
                    {timeline.map((entry) => (
                      <div
                        key={`${entry.tipo}-${entry.data.id}`}
                        className={entry.tipo === 'estado'
                          ? 'flex items-start gap-2 rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground'
                          : 'flex items-start gap-2 rounded-md border px-3 py-2 text-sm'}
                      >
                        {entry.tipo === 'estado' ? <History className="mt-0.5 size-3.5 shrink-0" />
                          : entry.tipo === 'movimiento' ? <ArrowLeftRight className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                          : entry.tipo === 'reparacion' ? <Wrench className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                          : <MessageSquare className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />}
                        <div className="grid gap-0.5">
                          {entry.tipo === 'reparacion' ? (
                            <>
                              {/* La tarjeta describe el ENVÍO, porque está
                                  anclada en `created_at`, que es cuando el
                                  equipo salió. Decir "Volvió de service" acá
                                  —como hacía la primera versión— deja el
                                  renglón que anuncia la vuelta ARRIBA del que
                                  anuncia la salida: la historia al revés, el
                                  mismo defecto que ya pagó el timeline de este
                                  repo. La vuelta la narra su propia actividad,
                                  en su lugar; acá sólo se refleja en el badge
                                  de estado y en la fecha de retorno. */}
                              <span className="flex flex-wrap items-center gap-2">
                                <Badge variant={entry.data.abierta ? 'default' : 'outline'}>
                                  {entry.data.abierta ? 'En service' : 'Pasó por service'}
                                </Badge>
                                <strong>{entry.data.equipo_descripcion}</strong>
                                {entry.data.en_garantia && (
                                  <Badge variant="outline" className="gap-1">
                                    <ShieldCheck className="size-3" />Garantía
                                  </Badge>
                                )}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                {[
                                  entry.data.proveedor_nombre,
                                  entry.data.remito_salida ? `remito ${entry.data.remito_salida}` : null,
                                  entry.data.rma ? `RMA ${entry.data.rma}` : null,
                                ].filter(Boolean).join(' · ')}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                {entry.data.abierta
                                  ? `Enviado el ${entry.data.fecha_envio} · ${entry.data.dias_afuera} días afuera`
                                  : `Enviado el ${entry.data.fecha_envio}, volvió el ${entry.data.fecha_retorno} · ${entry.data.dias_afuera} días${entry.data.diagnostico ? ` · ${entry.data.diagnostico}` : ''}`}
                              </span>
                            </>
                          ) : entry.tipo === 'movimiento' ? (
                            <>
                              <span className="flex flex-wrap items-center gap-2">
                                <Badge variant={entry.data.tipo === 'baja' ? 'destructive' : 'outline'}>
                                  {MOVIMIENTO_LABELS[entry.data.tipo] ?? entry.data.tipo}
                                </Badge>
                                <strong>{describirEquipo(equipoPorId(entry.data.equipo_id))}</strong>
                              </span>
                              {/* Solo el traslado tiene destino: en un cambio de
                                  estado la ubicación va como origen (de dónde
                                  sale), así que mostrar "→" sería inventar. */}
                              <span className="text-xs text-muted-foreground">
                                {entry.data.tipo === 'traslado'
                                  ? `${ubicacionTexto(entry.data.sector_origen, entry.data.ubicacion_origen)} → ${ubicacionTexto(entry.data.sector_destino, entry.data.ubicacion_destino)}`
                                  : `${entry.data.descripcion ?? '—'} · en ${ubicacionTexto(entry.data.sector_origen, entry.data.ubicacion_origen)}`}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                {entry.data.usuario} · {formatFecha(entry.data.fecha)}
                              </span>
                            </>
                          ) : entry.tipo === 'estado' ? (
                            <span>
                              Cambió de <strong>{entry.data.estado_anterior ? ESTADO_LABELS[entry.data.estado_anterior as keyof typeof ESTADO_LABELS] ?? entry.data.estado_anterior : 'creación'}</strong>
                              {' '}a <strong>{ESTADO_LABELS[entry.data.estado_nuevo as keyof typeof ESTADO_LABELS] ?? entry.data.estado_nuevo}</strong>
                              {entry.data.tecnico ? ` — ${entry.data.tecnico}` : ''} · {formatFecha(entry.data.fecha)}
                            </span>
                          ) : (
                            <>
                              <span>{entry.data.descripcion}</span>
                              <span className="text-xs text-muted-foreground">{entry.data.usuario ?? '—'} · {formatFecha(entry.data.fecha)}</span>
                            </>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex gap-2 pt-2">
                  <textarea
                    value={notaTexto}
                    onChange={(e) => setNotaTexto(e.target.value)}
                    rows={2}
                    placeholder="Agregar una nota…"
                    className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs"
                  />
                  <Button onClick={agregarNota} disabled={guardandoNota || !notaTexto.trim()}>
                    {guardandoNota ? 'Guardando…' : 'Agregar'}
                  </Button>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">Notas internas y resolución</CardTitle></CardHeader>
              <CardContent className="grid gap-3">
                <div className="grid gap-1.5">
                  <Label>Notas</Label>
                  <textarea
                    defaultValue={incidencia.notas ?? ''}
                    rows={2}
                    className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs"
                    onBlur={(e) => e.target.value !== (incidencia.notas ?? '') && actualizarCampo({ notas: e.target.value || null })}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label>Resolución</Label>
                  <textarea
                    defaultValue={incidencia.resolucion ?? ''}
                    rows={2}
                    className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs"
                    onBlur={(e) => e.target.value !== (incidencia.resolucion ?? '') && actualizarCampo({ resolucion: e.target.value || null })}
                  />
                </div>
              </CardContent>
            </Card>
          </div>

          <Card className="h-fit">
            <CardHeader><CardTitle className="text-base">Propiedades</CardTitle></CardHeader>
            <CardContent className="grid gap-3">
              <div className="grid gap-1.5">
                <Label>Estado</Label>
                <Select value={incidencia.estado} onValueChange={(estado) => actualizarCampo({ estado: estado as Incidencia['estado'] })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(Object.keys(ESTADO_LABELS) as (keyof typeof ESTADO_LABELS)[]).map((e) => (
                      <SelectItem key={e} value={e}>{ESTADO_LABELS[e]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label>Prioridad</Label>
                <Select value={incidencia.prioridad} onValueChange={(prioridad) => actualizarCampo({ prioridad: prioridad as Incidencia['prioridad'] })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(Object.keys(PRIORIDAD_LABELS) as (keyof typeof PRIORIDAD_LABELS)[]).map((p) => (
                      <SelectItem key={p} value={p}>{PRIORIDAD_LABELS[p]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {/* Sólo si hay catálogo: hasta que alguien cargue categorías en
                  Configuración, un select con una única opción "Sin categoría"
                  sería ruido. */}
              {categoriasElegibles.length > 0 && (
                <div className="grid gap-1.5">
                  <Label>Categoría</Label>
                  <SelectBuscable
                    value={incidencia.categoria_id ? String(incidencia.categoria_id) : NONE}
                    onChange={(v) => actualizarCampo({ categoria_id: v === NONE ? null : Number(v) })}
                    opciones={[
                      { value: NONE, label: 'Sin categoría' },
                      ...opcionesCategoria(categoriasElegibles),
                    ]}
                    ariaLabel="Categoría"
                    className="w-full"
                  />
                </div>
              )}
              <div className="grid gap-1.5">
                <Label>Cliente</Label>
                <SelectBuscable
                  value={String(incidencia.cliente_id)}
                  onChange={(v) => actualizarCampo({ cliente_id: Number(v), equipo_id: null })}
                  opciones={opcionesCliente(clientes)}
                  ariaLabel="Cliente"
                  className="w-full"
                />
              </div>
              <div className="grid gap-1.5">
                <Label>Equipo</Label>
                <SelectBuscable
                  value={incidencia.equipo_id ? String(incidencia.equipo_id) : NONE}
                  onChange={(v) => actualizarCampo({ equipo_id: v === NONE ? null : Number(v) })}
                  opciones={[{ value: NONE, label: 'Sin equipo' }, ...opcionesEquipo(equiposDelCliente)]}
                  ariaLabel="Equipo"
                  className="w-full"
                  emptyMessage="Ese cliente no tiene equipos."
                />
              </div>
              {/* Los tres papeles (pedido 41). Cada selector ofrece sólo a
                  quien tiene ese rol: mostrar el personal entero en los tres
                  vuelve a dejar la pregunta "quién lo ejecutó" sin contestar. */}
              <div className="grid gap-1.5">
                <Label>Recepcionó</Label>
                <SelectBuscable
                  value={incidencia.recepcionista_id ? String(incidencia.recepcionista_id) : NONE}
                  onChange={(v) => actualizarCampo({ recepcionista_id: v === NONE ? null : Number(v) })}
                  opciones={[{ value: NONE, label: 'Sin asignar' }, ...opcionesPorNombre(conRol('recepcionista'))]}
                  ariaLabel="Recepcionó"
                  className="w-full"
                  emptyMessage="Nadie tiene el rol de recepcionista."
                />
              </div>
              <div className="grid gap-1.5">
                <Label>Técnico (ejecuta)</Label>
                <SelectBuscable
                  value={incidencia.tecnico_id ? String(incidencia.tecnico_id) : NONE}
                  onChange={(v) => actualizarCampo({ tecnico_id: v === NONE ? null : Number(v) })}
                  opciones={[{ value: NONE, label: 'Sin asignar' }, ...opcionesPorNombre(conRol('tecnico'))]}
                  ariaLabel="Técnico"
                  className="w-full"
                />
              </div>
              <div className="grid gap-1.5">
                <Label>Vendedor</Label>
                <SelectBuscable
                  value={incidencia.vendedor_id ? String(incidencia.vendedor_id) : NONE}
                  onChange={(v) => actualizarCampo({ vendedor_id: v === NONE ? null : Number(v) })}
                  opciones={[{ value: NONE, label: 'Sin asignar' }, ...opcionesPorNombre(conRol('vendedor'))]}
                  ariaLabel="Vendedor"
                  className="w-full"
                  emptyMessage="Nadie tiene el rol de vendedor."
                />
              </div>
              <div className="grid gap-1.5">
                <Label>Modalidad</Label>
                <Select
                  value={incidencia.modalidad ?? NONE}
                  onValueChange={(v) => actualizarCampo({
                    modalidad: v === NONE ? null : (v as ModalidadIncidencia),
                  })}
                >
                  <SelectTrigger aria-label="Modalidad"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {/* "Sin definir" es un valor real y no un placeholder: los
                        tickets anteriores al pedido 37 no saben cómo se
                        atendieron, y ponerles on-site sería inventarlo. */}
                    <SelectItem value={NONE}>Sin definir</SelectItem>
                    {(Object.keys(MODALIDAD_LABELS) as ModalidadIncidencia[]).map((m) => (
                      <SelectItem key={m} value={m}>{MODALIDAD_LABELS[m]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {/* La agenda (pedido 42, fase B). Los tres juntos y en este
                  orden porque se llenan juntos: cuándo, cuánto y quién va.
                  El vehículo NO se elige acá — sale del equipo, y se muestra
                  debajo para que quien agenda lo vea sin ir a otra pantalla. */}
              <div className="grid gap-1.5">
                <Label htmlFor="fecha-programada">Fecha y hora del trabajo</Label>
                <Input
                  id="fecha-programada"
                  type="datetime-local"
                  value={deIsoALocal(incidencia.fecha_programada)}
                  onChange={(e) => actualizarCampo({
                    fecha_programada: deLocalAIso(e.target.value),
                  })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="duracion">Duración (minutos)</Label>
                <Input
                  id="duracion"
                  type="number"
                  min="15"
                  step="15"
                  placeholder="60"
                  value={incidencia.duracion_minutos ?? ''}
                  onChange={(e) => actualizarCampo({
                    duracion_minutos: e.target.value ? Number(e.target.value) : null,
                  })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label>Equipo de trabajo</Label>
                <SelectBuscable
                  value={
                    incidencia.equipo_trabajo_id ? String(incidencia.equipo_trabajo_id) : NONE
                  }
                  onChange={(v) => actualizarCampo({
                    equipo_trabajo_id: v === NONE ? null : Number(v),
                  })}
                  opciones={[
                    { value: NONE, label: 'Sin asignar' },
                    ...opcionesPorNombre(equiposTrabajo.filter(
                      (e) => e.activo || e.id === incidencia.equipo_trabajo_id,
                    )),
                  ]}
                  ariaLabel="Equipo de trabajo"
                  className="w-full"
                  emptyMessage="No hay equipos de trabajo cargados."
                />
                {(() => {
                  const equipo = equiposTrabajo.find(
                    (e) => e.id === incidencia.equipo_trabajo_id,
                  )
                  if (!equipo) return null
                  const patentes = equipo.vehiculos.map((v) => v.patente).join(', ')
                  return (
                    <p className="text-xs text-muted-foreground">
                      {patentes
                        ? `Sale en ${patentes}`
                        : 'Ese equipo no tiene vehículo asignado.'}
                      {equipo.responsable_nombre && ` · A cargo: ${equipo.responsable_nombre}`}
                    </p>
                  )
                })()}
              </div>
              <div className="grid gap-1.5">
                <Label>Sector</Label>
                <SelectBuscable
                  value={incidencia.sector_id ? String(incidencia.sector_id) : NONE}
                  onChange={(v) => actualizarCampo({ sector_id: v === NONE ? null : Number(v) })}
                  opciones={[{ value: NONE, label: 'Sin sector' }, ...opcionesPorNombre(sectores)]}
                  ariaLabel="Sector"
                  className="w-full"
                  emptyMessage="Ese cliente no tiene sectores."
                />
              </div>
              <div className="grid gap-1.5">
                {/* `htmlFor`/`id`: el label estaba suelto y no nombraba a su
                    input para un lector de pantalla. */}
                <Label htmlFor="horas-invertidas">Horas invertidas</Label>
                <Input
                  id="horas-invertidas"
                  type="number"
                  step="0.5"
                  defaultValue={incidencia.horas_invertidas ?? ''}
                  onBlur={(e) => {
                    const valor = e.target.value ? Number(e.target.value) : null
                    if (valor !== incidencia.horas_invertidas) actualizarCampo({ horas_invertidas: valor })
                  }}
                />
              </div>
              <div className="grid gap-0.5 pt-1 text-xs text-muted-foreground">
                <span>Creada: {formatFecha(incidencia.fecha_creacion)}</span>
                {incidencia.fecha_cierre && <span>Cerrada: {formatFecha(incidencia.fecha_cierre)}</span>}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Una sola operación en vez de tres pasos manuales sueltos: mueve
          los dos activos, deja los movimientos ligados a este ticket y
          narra las dos intervenciones en el timeline. */}
      <Dialog open={reemplazoAbierto} onOpenChange={setReemplazoAbierto}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Reemplazar equipo</DialogTitle>
            <DialogDescription>
              Actualiza el estado y la ubicación de los dos equipos, registra los
              movimientos asociados a esta incidencia y deja las intervenciones
              en la actividad del ticket.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3">
            <div className="grid gap-1.5">
              <Label>Equipo que se retira</Label>
              <Select value={reemplazo.retirado} onValueChange={(v) => setReemplazo({ ...reemplazo, retirado: v })}>
                <SelectTrigger><SelectValue placeholder="Elegí el equipo…" /></SelectTrigger>
                <SelectContent>
                  {equiposDelCliente.map((e) => (
                    <SelectItem key={e.id} value={String(e.id)}>
                      {describirEquipo(e)} — {ubicacionTexto(e.sector, e.ubicacion_oficina)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-1.5">
              <Label>Destino del equipo retirado</Label>
              <Select value={reemplazo.destino} onValueChange={(v) => setReemplazo({ ...reemplazo, destino: v as DestinoReemplazo })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(Object.keys(DESTINO_REEMPLAZO_LABELS) as DestinoReemplazo[]).map((d) => (
                    <SelectItem key={d} value={d}>{DESTINO_REEMPLAZO_LABELS[d]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-1.5">
              <Label>Equipo sustituto (opcional)</Label>
              <Select value={reemplazo.sustituto} onValueChange={(v) => setReemplazo({ ...reemplazo, sustituto: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>Sin reemplazo</SelectItem>
                  {equiposDelCliente
                    .filter((e) => String(e.id) !== reemplazo.retirado)
                    .map((e) => (
                      <SelectItem key={e.id} value={String(e.id)}>
                        {describirEquipo(e)} — {ubicacionTexto(e.sector, e.ubicacion_oficina)}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
              <span className="text-xs text-muted-foreground">
                Queda en el lugar exacto que deja el equipo retirado.
              </span>
            </div>

            <div className="grid gap-1.5">
              <Label>Motivo</Label>
              <Input
                value={reemplazo.motivo}
                placeholder="Ruido mecánico, se envía a service…"
                onChange={(e) => setReemplazo({ ...reemplazo, motivo: e.target.value })}
              />
            </div>

            {/* Bloque de service (pendiente 18). Hasta acá, "a quién se lo
                mandamos" y "con qué RMA" sólo podían vivir dentro del texto
                del motivo, de donde no se pueden listar ni sumar. */}
            {mostrarBloqueService && (
              <div className="grid gap-3 rounded-md border border-dashed p-3">
                <span className="flex items-center gap-2 text-sm font-medium">
                  <Wrench className="size-4" />Datos del service
                </span>

                <div className="grid gap-1.5">
                  <Label>Proveedor</Label>
                  <SelectBuscable
                    value={reemplazo.proveedor}
                    onChange={(v) => setReemplazo({ ...reemplazo, proveedor: v })}
                    opciones={[
                      { value: NONE, label: 'No registrar la reparación' },
                      ...opcionesProveedor(proveedores),
                    ]}
                    placeholder="Elegí el proveedor…"
                  />
                  <span className="text-xs text-muted-foreground">
                    {proveedores.length === 0
                      ? 'No hay proveedores cargados. Se cargan en Configuración.'
                      : 'Sin proveedor el equipo se mueve igual, pero no queda registro del service.'}
                  </span>
                </div>

                {reemplazo.proveedor !== NONE && (
                  <>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <div className="grid gap-1.5">
                        <Label>Fecha de envío</Label>
                        <Input
                          type="date" value={reemplazo.fechaEnvio}
                          onChange={(e) => setReemplazo({ ...reemplazo, fechaEnvio: e.target.value })}
                        />
                      </div>
                      <div className="grid gap-1.5">
                        <Label>Remito</Label>
                        <Input
                          value={reemplazo.remito} placeholder="R-0001"
                          onChange={(e) => setReemplazo({ ...reemplazo, remito: e.target.value })}
                        />
                      </div>
                      <div className="grid gap-1.5">
                        <Label>RMA</Label>
                        <Input
                          value={reemplazo.rma} placeholder="RMA-99"
                          onChange={(e) => setReemplazo({ ...reemplazo, rma: e.target.value })}
                        />
                      </div>
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox" checked={reemplazo.enGarantia}
                        onChange={(e) => setReemplazo({ ...reemplazo, enGarantia: e.target.checked })}
                      />
                      <ShieldCheck className="size-4" />
                      Entra por garantía
                    </label>
                  </>
                )}
              </div>
            )}

            {/* La vuelta del service. No se pregunta si el equipo está
                volviendo: se deduce de que el que entra tenga una reparación
                abierta. */}
            {reparacionDelSustituto && (
              <div className="grid gap-3 rounded-md border border-dashed p-3">
                <label className="flex items-center gap-2 text-sm font-medium">
                  <input
                    type="checkbox" checked={reemplazo.cerrarService}
                    onChange={(e) => setReemplazo({ ...reemplazo, cerrarService: e.target.checked })}
                  />
                  <PackageCheck className="size-4" />
                  Cerrar la reparación en {reparacionDelSustituto.proveedor_nombre}
                </label>
                <span className="text-xs text-muted-foreground">
                  Salió el {reparacionDelSustituto.fecha_envio}
                  {reparacionDelSustituto.rma ? ` · RMA ${reparacionDelSustituto.rma}` : ''}
                  {' '}· {reparacionDelSustituto.dias_afuera} días afuera.
                </span>

                {reemplazo.cerrarService && (
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div className="grid gap-1.5">
                      <Label>Fecha de retorno</Label>
                      <Input
                        type="date" value={reemplazo.fechaRetorno}
                        onChange={(e) => setReemplazo({ ...reemplazo, fechaRetorno: e.target.value })}
                      />
                    </div>
                    <div className="grid gap-1.5">
                      <Label>Diagnóstico</Label>
                      <Input
                        value={reemplazo.diagnostico} placeholder="Se cambió el fusor…"
                        onChange={(e) => setReemplazo({ ...reemplazo, diagnostico: e.target.value })}
                      />
                    </div>
                    <div className="grid gap-1.5">
                      <Label>Costo</Label>
                      <Input
                        type="number" min="0" step="0.01" value={reemplazo.costo}
                        placeholder={reparacionDelSustituto.en_garantia ? 'Por garantía' : '0'}
                        onChange={(e) => setReemplazo({ ...reemplazo, costo: e.target.value })}
                      />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setReemplazoAbierto(false)}>Cancelar</Button>
            <Button onClick={confirmarReemplazo} disabled={reemplazando || reemplazo.retirado === NONE}>
              {reemplazando ? 'Aplicando…' : 'Reemplazar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="¿Eliminar esta incidencia?"
        description="Se borra también su historial de actividad y de cambios de estado. Esta acción no se puede deshacer."
        confirmLabel="Eliminar"
        onConfirm={() => { eliminar(); setConfirmDelete(false) }}
      />
    </div>
  )
}
