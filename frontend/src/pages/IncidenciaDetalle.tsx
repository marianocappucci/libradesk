import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  api, ApiError, DESTINO_REEMPLAZO_LABELS, ESTADO_LABELS, MOVIMIENTO_LABELS,
  PRIORIDAD_LABELS, describirEquipo, ubicacionTexto,
  type Actividad, type Cliente, type DestinoReemplazo, type Equipo,
  type EquipoMovimiento, type Incidencia, type IncidenciaEstadoLog,
  type Sector, type Tecnico,
} from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { ConfirmDialog } from '@/components/confirm-dialog'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { ArrowLeft, ArrowLeftRight, History, MessageSquare, Trash2 } from 'lucide-react'

const NONE = '__none__'

type TimelineEntry =
  | { tipo: 'actividad'; fecha: string; data: Actividad }
  | { tipo: 'estado'; fecha: string; data: IncidenciaEstadoLog }
  // Tercera fuente: lo que este ticket le hizo al inventario. Antes el
  // timeline solo tenía notas y cambios de estado, así que "se retiró la
  // impresora" aparecía únicamente si alguien lo escribía a mano.
  | { tipo: 'movimiento'; fecha: string; data: EquipoMovimiento }

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
  const [actividades, setActividades] = useState<Actividad[]>([])
  const [estados, setEstados] = useState<IncidenciaEstadoLog[]>([])
  const [movimientos, setMovimientos] = useState<EquipoMovimiento[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notaTexto, setNotaTexto] = useState('')
  const [guardandoNota, setGuardandoNota] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [reemplazoAbierto, setReemplazoAbierto] = useState(false)
  const [reemplazando, setReemplazando] = useState(false)
  const [reemplazo, setReemplazo] = useState({
    retirado: NONE, sustituto: NONE, destino: 'service' as DestinoReemplazo, motivo: '',
  })

  useEffect(() => {
    cargar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incidenciaId])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function cargar() {
    setLoading(true)
    setError(null)
    try {
      const [inc, cl, eq, te, se, act, est, mov] = await Promise.all([
        api.get<Incidencia>(`/api/incidencias/${incidenciaId}`),
        api.get<Cliente[]>('/api/clientes'),
        api.get<Equipo[]>('/api/equipos'),
        api.get<Tecnico[]>('/api/tecnicos'),
        api.get<Sector[]>('/api/sectores'),
        api.get<Actividad[]>(`/api/incidencias/${incidenciaId}/actividades`),
        api.get<IncidenciaEstadoLog[]>(`/api/incidencias/${incidenciaId}/estados`),
        api.get<EquipoMovimiento[]>(`/api/incidencias/${incidenciaId}/movimientos`),
      ])
      setIncidencia(inc)
      setClientes(cl)
      setEquipos(eq)
      setTecnicos(te)
      setSectores(se)
      setActividades(act)
      setEstados(est)
      setMovimientos(mov)
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

  // Guarda un campo apenas cambia (sin botón "Guardar" aparte) -- mismo
  // patrón que el panel de propiedades de Zendesk/Freshdesk. Reconstruye
  // el payload completo a partir del estado actual porque el backend
  // (`IncidenciaIn`) espera el objeto entero en el PUT.
  async function actualizarCampo(patch: Partial<Incidencia>) {
    if (!incidencia) return
    setError(null)
    const previo = incidencia
    const actualizado = { ...incidencia, ...patch }
    setIncidencia(actualizado)
    try {
      const guardado = await api.put<Incidencia>(`/api/incidencias/${incidenciaId}`, {
        cliente_id: actualizado.cliente_id,
        equipo_id: actualizado.equipo_id,
        tecnico_id: actualizado.tecnico_id,
        sector_id: actualizado.sector_id,
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
      if (patch.estado) await recargarActividadYEstado()
    } catch (err) {
      setIncidencia(previo)
      setError(describeError(err))
    }
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
  const rangoPorTipo = { actividad: 0, movimiento: 1, estado: 2 }
  const timeline: TimelineEntry[] = [
    ...actividades.map((a): TimelineEntry => ({ tipo: 'actividad', fecha: a.fecha ?? '', data: a })),
    ...estados.map((e): TimelineEntry => ({ tipo: 'estado', fecha: e.fecha ?? '', data: e })),
    ...movimientos.map((m): TimelineEntry => ({ tipo: 'movimiento', fecha: m.fecha ?? '', data: m })),
  ].sort((a, b) =>
    new Date(a.fecha).getTime() - new Date(b.fecha).getTime()
    || rangoPorTipo[a.tipo] - rangoPorTipo[b.tipo]
    || a.data.id - b.data.id,
  )

  const equiposDelCliente = incidencia ? equipos.filter((e) => e.cliente_id === incidencia.cliente_id) : []
  const equipoPorId = (id: number) => equipos.find((e) => e.id === id)

  function abrirReemplazo() {
    setReemplazo({
      // Por defecto se retira el equipo del ticket, que es el caso normal.
      retirado: incidencia?.equipo_id ? String(incidencia.equipo_id) : NONE,
      sustituto: NONE,
      destino: 'service',
      motivo: '',
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
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={abrirReemplazo}>
              <ArrowLeftRight />Reemplazar equipo
            </Button>
            <Button size="sm" variant="outline" className="text-destructive hover:text-destructive" onClick={() => setConfirmDelete(true)}>
              <Trash2 />Eliminar
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
                          : <MessageSquare className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />}
                        <div className="grid gap-0.5">
                          {entry.tipo === 'movimiento' ? (
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
              <div className="grid gap-1.5">
                <Label>Cliente</Label>
                <Select value={String(incidencia.cliente_id)} onValueChange={(v) => actualizarCampo({ cliente_id: Number(v), equipo_id: null })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {clientes.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.nombre}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label>Equipo</Label>
                <Select value={incidencia.equipo_id ? String(incidencia.equipo_id) : NONE} onValueChange={(v) => actualizarCampo({ equipo_id: v === NONE ? null : Number(v) })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>Sin equipo</SelectItem>
                    {equiposDelCliente.map((e) => <SelectItem key={e.id} value={String(e.id)}>{e.tipo}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label>Técnico</Label>
                <Select value={incidencia.tecnico_id ? String(incidencia.tecnico_id) : NONE} onValueChange={(v) => actualizarCampo({ tecnico_id: v === NONE ? null : Number(v) })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>Sin asignar</SelectItem>
                    {tecnicos.map((t) => <SelectItem key={t.id} value={String(t.id)}>{t.nombre}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label>Sector</Label>
                <Select value={incidencia.sector_id ? String(incidencia.sector_id) : NONE} onValueChange={(v) => actualizarCampo({ sector_id: v === NONE ? null : Number(v) })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>Sin sector</SelectItem>
                    {sectores.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.nombre}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label>Horas invertidas</Label>
                <Input
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
