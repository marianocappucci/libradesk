import { useEffect, useMemo, useRef, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { Link } from 'react-router-dom'
import {
  api, ApiError, ESTADO_EQUIPO_LABELS, ESTADO_LABELS as ESTADO_INCIDENCIA_LABELS,
  MOVIMIENTO_LABELS, describirEquipo, ubicacionTexto, opcionesCliente,
  type Cliente, type Equipo, type EquipoMovimiento, type Incidencia,
  type Reparacion,
} from '../api'
import { useAuth } from '../context/AuthContext'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form'
import { DataTable, sortableHeader } from '@/components/data-table'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { History, Monitor, Pencil, Plus, ShieldCheck, Trash2, Wrench } from 'lucide-react'

function formatFecha(fecha: string | null): string {
  if (!fecha) return '—'
  return new Date(fecha).toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' })
}

const equipoSchema = z.object({
  cliente_id: z.string().min(1, 'Elegí un cliente'),
  tipo: z.string().trim().min(1, 'El tipo es obligatorio'),
  marca: z.string().trim().optional(),
  modelo: z.string().trim().optional(),
  serial: z.string().trim().optional(),
  ubicacion_oficina: z.string().trim().optional(),
  sector: z.string().trim().optional(),
  estado: z.string().min(1),
  garantia_vence: z.string().trim().optional(),
  observaciones: z.string().trim().optional(),
  // Solo para el historial: si el guardado implica traslado o cambio de
  // estado, este texto queda como motivo del movimiento.
  motivo: z.string().trim().optional(),
})

type EquipoFormValues = z.infer<typeof equipoSchema>

const EMPTY_VALUES: EquipoFormValues = {
  cliente_id: '', tipo: '', marca: '', modelo: '', serial: '',
  ubicacion_oficina: '', sector: '', estado: 'activo',
  garantia_vence: '', observaciones: '', motivo: '',
}

const ESTADOS_EQUIPO = ['activo', 'en_reparacion', 'almacenado', 'baja']

// Radix no admite un <SelectItem value="">, así que el "sin filtro" necesita
// un valor propio (misma convención que Incidencias.tsx).
const TODOS = 'todos'

export function Equipos() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [equipos, setEquipos] = useState<Equipo[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Alta y edición en un solo Dialog reusado (`editando === null` es alta),
  // mismo patrón que Contalibra. Antes era una card sobre la tabla: al cargar
  // un equipo quedaban a la vista el formulario, la lista entera y el filtro,
  // los tres compitiendo por la atención.
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editando, setEditando] = useState<Equipo | null>(null)
  const [saving, setSaving] = useState(false)
  // El error del formulario va DENTRO del modal; el de la página quedaría tapado.
  const [formError, setFormError] = useState<string | null>(null)
  const [aBorrar, setABorrar] = useState<Equipo | null>(null)
  const [historialDe, setHistorialDe] = useState<Equipo | null>(null)
  const [movimientos, setMovimientos] = useState<EquipoMovimiento[] | null>(null)
  const [incidenciasDelEquipo, setIncidenciasDelEquipo] = useState<Incidencia[] | null>(null)
  const [reparacionesDelEquipo, setReparacionesDelEquipo] = useState<Reparacion[] | null>(null)
  const [filtroCliente, setFiltroCliente] = useState(TODOS)

  const form = useForm<EquipoFormValues>({
    resolver: zodResolver(equipoSchema),
    defaultValues: EMPTY_VALUES,
  })

  const montado = useRef(false)

  useEffect(() => {
    loadAll()
  }, [])

  // El filtro por cliente recarga SOLO los equipos y sin pasar por `loading`:
  // si la tabla se desmontara para mostrar "Cargando…", el buscador (que vive
  // dentro de DataTable) perdería lo escrito en cada cambio de cliente.
  useEffect(() => {
    if (!montado.current) {
      montado.current = true
      return
    }
    loadEquipos()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtroCliente])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  const clienteNombre = (id: number) => clientes.find((c) => c.id === id)?.nombre ?? `#${id}`

  // Clientes ofrecibles en el formulario: sólo los activos, **más el que ya
  // tiene el equipo que se está editando** aunque esté desactivado. Sin esa
  // excepción, abrir un equipo de un cliente dado de baja mostraría el
  // selector vacío y guardarlo lo movería de cliente sin querer.
  const clientesElegibles = clientes.filter(
    (c) => c.activo || String(c.id) === form.watch('cliente_id'),
  )

  // El filtro lo resuelve el backend (`?cliente_id=`, ya existía y no lo usaba
  // nadie), no un filter local: es lo que escala cuando el parque crezca.
  const rutaEquipos = () =>
    filtroCliente === TODOS ? '/api/equipos' : `/api/equipos?cliente_id=${filtroCliente}`

  async function loadEquipos() {
    setError(null)
    try {
      setEquipos(await api.get<Equipo[]>(rutaEquipos()))
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function loadAll() {
    setLoading(true)
    setError(null)
    try {
      const [eq, cl] = await Promise.all([
        api.get<Equipo[]>(rutaEquipos()),
        api.get<Cliente[]>('/api/clientes'),
      ])
      setEquipos(eq)
      setClientes(cl)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  function abrirNuevo() {
    setEditando(null)
    setFormError(null)
    // Si hay un cliente filtrado, el alta ya viene con ése elegido: es el
    // caso normal (se filtra por cliente y se le carga un equipo).
    form.reset({ ...EMPTY_VALUES, cliente_id: filtroCliente === TODOS ? '' : filtroCliente })
    setDialogOpen(true)
  }

  function abrirEditar(equipo: Equipo) {
    setEditando(equipo)
    setFormError(null)
    form.reset({
      cliente_id: String(equipo.cliente_id),
      tipo: equipo.tipo,
      marca: equipo.marca ?? '',
      modelo: equipo.modelo ?? '',
      serial: equipo.serial ?? '',
      ubicacion_oficina: equipo.ubicacion_oficina ?? '',
      sector: equipo.sector ?? '',
      estado: equipo.estado,
      garantia_vence: equipo.garantia_vence ?? '',
      observaciones: equipo.observaciones ?? '',
      motivo: '',
    })
    setDialogOpen(true)
  }

  async function handleSubmit(values: EquipoFormValues) {
    setSaving(true)
    setFormError(null)
    const payload = {
      cliente_id: Number(values.cliente_id),
      tipo: values.tipo,
      marca: values.marca || null,
      modelo: values.modelo || null,
      serial: values.serial || null,
      ubicacion_oficina: values.ubicacion_oficina || null,
      sector: values.sector || null,
      estado: values.estado,
      observaciones: values.observaciones || null,
      // Antes iba `null` fijo porque el formulario no tenía el campo: cada
      // edición borraba la garantía del equipo y lo sacaba del reporte de
      // Garantías sin que nadie lo notara.
      garantia_vence: values.garantia_vence || null,
    }
    try {
      if (editando === null) {
        await api.post('/api/equipos', payload)
      } else {
        await api.put(`/api/equipos/${editando.id}`, { ...payload, motivo: values.motivo || null })
      }
      setDialogOpen(false)
      // Solo los equipos: la lista de clientes no cambió, y recargarla
      // apagaría la tabla un instante y con ella la búsqueda escrita.
      await loadEquipos()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function verHistorial(equipo: Equipo) {
    setHistorialDe(equipo)
    setMovimientos(null)
    setIncidenciasDelEquipo(null)
    setReparacionesDelEquipo(null)
    try {
      // Las tres mitades de la ficha: qué le pasó al equipo (incidencias),
      // dónde estuvo (movimientos) y cuántas veces salió a reparar
      // (reparaciones). Antes sólo se veía la segunda, así que ni "¿cuántas
      // veces falló?" ni "¿cuánto llevamos gastado en este aparato?" tenían
      // respuesta.
      const [movs, incs, reps] = await Promise.all([
        api.get<EquipoMovimiento[]>(`/api/equipos/${equipo.id}/movimientos`),
        api.get<Incidencia[]>(`/api/incidencias?equipo_id=${equipo.id}`),
        api.get<Reparacion[]>(`/api/reparaciones?equipo_id=${equipo.id}`),
      ])
      setMovimientos(movs)
      setIncidenciasDelEquipo(incs)
      setReparacionesDelEquipo(reps)
    } catch (err) {
      setError(describeError(err))
      setHistorialDe(null)
    }
  }

  async function handleDelete(equipo: Equipo) {
    setError(null)
    try {
      await api.del(`/api/equipos/${equipo.id}`)
      await loadEquipos()
    } catch (err) {
      setError(describeError(err))
    }
  }

  const columns = useMemo<ColumnDef<Equipo>[]>(() => {
    const base: ColumnDef<Equipo>[] = [
      { accessorKey: 'tipo', header: sortableHeader('Tipo'), size: 140, minSize: 100, meta: { stretch: true }, cell: ({ row }) => <span className="font-medium">{row.original.tipo}</span> },
      { accessorKey: 'cliente_id', header: 'Cliente', size: 160, minSize: 120, cell: ({ row }) => clienteNombre(row.original.cliente_id) },
      { accessorKey: 'marca', header: 'Marca', size: 120, minSize: 90, cell: ({ row }) => row.original.marca ?? '—' },
      { accessorKey: 'modelo', header: 'Modelo', size: 150, minSize: 100, cell: ({ row }) => row.original.modelo ?? '—' },
      { accessorKey: 'serial', header: 'Serial', size: 130, minSize: 100, cell: ({ row }) => row.original.serial ?? '—' },
      {
        accessorKey: 'estado',
        header: 'Estado',
        size: 120,
        minSize: 90,
        cell: ({ row }) => (
          <Badge variant={row.original.estado === 'activo' ? 'default' : 'outline'}>
            {ESTADO_EQUIPO_LABELS[row.original.estado] ?? row.original.estado}
          </Badge>
        ),
      },
    ]
    // El historial es de solo lectura, así que lo ve cualquier usuario
    // logueado; editar y borrar siguen siendo admin-only.
    base.push({
      id: 'actions',
      header: () => <div className="text-right">Acciones</div>,
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          <Button size="icon" variant="outline" title="Ver historial de movimientos" aria-label="Ver historial de movimientos" onClick={() => verHistorial(row.original)}><History /></Button>
          {isAdmin && (
            <>
              <Button size="icon" variant="outline" title="Editar equipo" aria-label="Editar equipo" onClick={() => abrirEditar(row.original)}><Pencil /></Button>
              <Button size="icon" variant="outline" className="text-destructive hover:text-destructive" title="Eliminar equipo" aria-label="Eliminar equipo" onClick={() => setABorrar(row.original)}><Trash2 /></Button>
            </>
          )}
        </div>
      ),
    })
    return base
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin, clientes])

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Equipos</h2>
        {isAdmin && (
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button onClick={abrirNuevo}><Plus />Nuevo equipo</Button>
            </DialogTrigger>
            <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <Monitor className="size-4" />
                  {editando === null ? 'Nuevo equipo' : `Editar equipo — ${describirEquipo(editando)}`}
                </DialogTitle>
              </DialogHeader>
            <Form {...form}>
              <form className="flex flex-wrap items-start gap-3" onSubmit={form.handleSubmit(handleSubmit)}>
                {formError && <p className="w-full text-sm text-destructive">{formError}</p>}
                <FormField control={form.control} name="cliente_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Cliente</FormLabel>
                    <FormControl>
                      <SelectBuscable
                        value={field.value}
                        onChange={field.onChange}
                        opciones={opcionesCliente(clientesElegibles)}
                        placeholder="Cliente…"
                        ariaLabel="Cliente"
                        className="w-48"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="tipo" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Tipo</FormLabel>
                    <FormControl><Input {...field} className="w-36" placeholder="Notebook, impresora…" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="marca" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Marca</FormLabel>
                    <FormControl><Input {...field} className="w-32" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="modelo" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Modelo</FormLabel>
                    <FormControl><Input {...field} className="w-36" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="serial" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Serial</FormLabel>
                    <FormControl><Input {...field} className="w-32" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="sector" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Sector</FormLabel>
                    <FormControl><Input {...field} className="w-36" placeholder="Depósito, Admisión…" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="ubicacion_oficina" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Ubicación</FormLabel>
                    <FormControl><Input {...field} className="w-36" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="garantia_vence" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Garantía vence</FormLabel>
                    <FormControl><Input type="date" {...field} className="w-40" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="estado" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Estado</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="w-40">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {ESTADOS_EQUIPO.map((e) => <SelectItem key={e} value={e}>{ESTADO_EQUIPO_LABELS[e]}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )} />
                {editando !== null && (
                  <FormField control={form.control} name="motivo" render={({ field }) => (
                    <FormItem>
                      <FormLabel>Motivo del movimiento</FormLabel>
                      <FormControl>
                        <Input {...field} className="w-56" placeholder="Si cambia sector o estado" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )} />
                )}
                <DialogFooter className="w-full">
                  <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
                  <Button type="submit" disabled={saving}>
                    {saving ? 'Guardando…' : editando === null ? 'Crear equipo' : 'Guardar'}
                  </Button>
                </DialogFooter>
              </form>
            </Form>
            </DialogContent>
          </Dialog>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex flex-wrap items-end gap-3">
        <div className="grid gap-1.5">
          <span className="text-xs text-muted-foreground">Cliente</span>
          <SelectBuscable
            value={filtroCliente}
            onChange={setFiltroCliente}
            opciones={[{ value: TODOS, label: 'Todos' }, ...opcionesCliente(clientes)]}
            ariaLabel="Filtrar por cliente"
            className="w-56"
          />
        </div>
        {filtroCliente !== TODOS && (
          <Button variant="ghost" size="sm" onClick={() => setFiltroCliente(TODOS)}>
            Limpiar filtro
          </Button>
        )}
      </div>

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable
              columns={columns}
              data={equipos}
              emptyMessage={filtroCliente === TODOS
                ? 'Sin equipos todavía.'
                : 'Este cliente no tiene equipos cargados.'}
              search={{
                campos: (e) => [
                  e.tipo, e.marca, e.modelo, e.serial,
                  e.sector, e.ubicacion_oficina, clienteNombre(e.cliente_id),
                ],
                placeholder: 'Buscar por tipo, marca, modelo, serial, sector o cliente',
              }}
            />
          )}
        </CardContent>
      </Card>

      <Dialog open={historialDe !== null} onOpenChange={(open) => !open && setHistorialDe(null)}>
        <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Historial del equipo</DialogTitle>
            <DialogDescription>
              {historialDe && describirEquipo(historialDe)}
              {historialDe?.serial ? ` — ${historialDe.serial}` : ''}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-2">
            <h4 className="text-sm font-semibold">
              Incidencias{incidenciasDelEquipo ? ` (${incidenciasDelEquipo.length})` : ''}
            </h4>
            {incidenciasDelEquipo === null ? (
              <p className="text-sm text-muted-foreground">Cargando…</p>
            ) : incidenciasDelEquipo.length === 0 ? (
              <p className="text-sm text-muted-foreground">Este equipo nunca falló.</p>
            ) : (
              incidenciasDelEquipo.map((i) => (
                <Link
                  key={i.id}
                  to={`/incidencias/${i.id}`}
                  className="grid gap-0.5 rounded-md border px-3 py-2 text-sm hover:bg-muted/50"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={i.estado === 'cerrado' || i.estado === 'resuelta' ? 'default' : 'outline'}>
                      {ESTADO_INCIDENCIA_LABELS[i.estado] ?? i.estado}
                    </Badge>
                    <span className="font-medium">{i.titulo}</span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    #{i.id} · {formatFecha(i.fecha_creacion)}
                  </span>
                </Link>
              ))
            )}
          </div>

          <div className="grid gap-2">
            <h4 className="text-sm font-semibold">
              Reparaciones{reparacionesDelEquipo ? ` (${reparacionesDelEquipo.length})` : ''}
            </h4>
            {reparacionesDelEquipo === null ? (
              <p className="text-sm text-muted-foreground">Cargando…</p>
            ) : reparacionesDelEquipo.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nunca salió a service.</p>
            ) : (
              <>
                {reparacionesDelEquipo.map((r) => (
                  <div key={r.id} className="grid gap-0.5 rounded-md border px-3 py-2 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={r.abierta ? 'default' : 'outline'}>
                        {r.abierta ? 'En service' : 'Volvió'}
                      </Badge>
                      <span className="font-medium">{r.proveedor_nombre}</span>
                      {r.en_garantia && (
                        <Badge variant="outline" className="gap-1">
                          <ShieldCheck className="size-3" />Garantía
                        </Badge>
                      )}
                      {r.incidencia_id !== null && (
                        <Link
                          to={`/incidencias/${r.incidencia_id}`}
                          className="text-xs underline underline-offset-2"
                        >
                          Incidencia #{r.incidencia_id}
                        </Link>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {[
                        r.abierta
                          ? `Salió el ${r.fecha_envio} · ${r.dias_afuera} días afuera`
                          : `${r.fecha_envio} → ${r.fecha_retorno} · ${r.dias_afuera} días`,
                        r.remito_salida ? `remito ${r.remito_salida}` : null,
                        r.rma ? `RMA ${r.rma}` : null,
                        r.costo !== null ? `$ ${r.costo.toLocaleString('es-AR')}` : null,
                      ].filter(Boolean).join(' · ')}
                    </span>
                    {r.diagnostico && (
                      <span className="text-xs text-muted-foreground">{r.diagnostico}</span>
                    )}
                  </div>
                ))}
                {/* Lo que ninguna fila suelta contesta: cuánto lleva gastado
                    este aparato. Con eso al lado del precio de uno nuevo, la
                    decisión de reemplazarlo deja de ser una corazonada. */}
                {(() => {
                  const gastado = reparacionesDelEquipo
                    .reduce((suma, r) => suma + (r.costo ?? 0), 0)
                  return gastado > 0 ? (
                    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Wrench className="size-3" />
                      Gastado en reparaciones: <strong>$ {gastado.toLocaleString('es-AR')}</strong>
                    </p>
                  ) : null
                })()}
              </>
            )}
          </div>

          <h4 className="text-sm font-semibold">Movimientos</h4>
          {movimientos === null ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : movimientos.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Sin movimientos registrados.
            </p>
          ) : (
            <div className="grid gap-2">
              {movimientos.map((m) => {
                const origen = ubicacionTexto(m.sector_origen, m.ubicacion_origen)
                // Un cambio de estado no tiene destino: la ubicación viaja
                // como origen (de dónde sale el equipo). Dibujar la flecha
                // igual mostraría "Service → sin ubicación", como si se
                // hubiera movido a ninguna parte.
                const tieneDestino = Boolean(m.sector_destino || m.ubicacion_destino)
                const destino = ubicacionTexto(m.sector_destino, m.ubicacion_destino)
                return (
                  <div key={m.id} className="grid gap-0.5 rounded-md border px-3 py-2 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={m.tipo === 'baja' ? 'destructive' : 'outline'}>
                        {MOVIMIENTO_LABELS[m.tipo] ?? m.tipo}
                      </Badge>
                      <span className="font-medium">{m.descripcion ?? '—'}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {tieneDestino ? `${origen} → ${destino}` : `en ${origen}`}
                    </span>
                    {m.motivo && <span className="text-xs text-muted-foreground">Motivo: {m.motivo}</span>}
                    <span className="text-xs text-muted-foreground">
                      {m.usuario} · {formatFecha(m.fecha)}
                      {/* El "por qué" del movimiento: sin esto el historial dice
                          que salió de Admisión pero no de qué ticket vino. */}
                      {m.incidencia_id && (
                        <>
                          {' · '}
                          <Link to={`/incidencias/${m.incidencia_id}`} className="underline">
                            Incidencia #{m.incidencia_id}
                          </Link>
                        </>
                      )}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={aBorrar !== null}
        onOpenChange={(open) => !open && setABorrar(null)}
        title={`¿Eliminar ${describirEquipo(aBorrar ?? undefined)}?`}
        // Describe lo que el repositorio hace de verdad: los `ondelete` de los
        // modelos no corren (el pragma está apagado), así que el borrado del
        // historial y la desasignación se hacen explícitos en el backend.
        description="Se borra también su historial de movimientos. Las incidencias que lo tengan asignado quedan sin equipo, no se borran. Esta acción no se puede deshacer."
        onConfirm={() => { const e = aBorrar; setABorrar(null); if (e) handleDelete(e) }}
      />
    </div>
  )
}
