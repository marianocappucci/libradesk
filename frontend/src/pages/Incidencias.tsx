import { useEffect, useMemo, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import {
  api, ApiError, ESTADO_LABELS, PRIORIDAD_LABELS,
  type Cliente, type Equipo, type Incidencia, type Sector, type Tecnico,
} from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
import { Pencil, Trash2 } from 'lucide-react'

const NONE = '__none__'

const incidenciaSchema = z.object({
  cliente_id: z.string().min(1, 'Elegí un cliente'),
  equipo_id: z.string().optional(),
  tecnico_id: z.string().optional(),
  sector_id: z.string().optional(),
  titulo: z.string().trim().min(1, 'El título es obligatorio'),
  descripcion: z.string().trim().optional(),
  estado: z.enum(['abierto', 'en_progreso', 'resuelta', 'cerrado']),
  prioridad: z.enum(['alta', 'media', 'baja']),
  horas_invertidas: z.string().optional(),
  notas: z.string().trim().optional(),
  resolucion: z.string().trim().optional(),
})

type IncidenciaFormValues = z.infer<typeof incidenciaSchema>

const EMPTY_VALUES: IncidenciaFormValues = {
  cliente_id: '', equipo_id: NONE, tecnico_id: NONE, sector_id: NONE,
  titulo: '', descripcion: '', estado: 'abierto', prioridad: 'media',
  horas_invertidas: '', notas: '', resolucion: '',
}

export function Incidencias() {
  const [incidencias, setIncidencias] = useState<Incidencia[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [equipos, setEquipos] = useState<Equipo[]>([])
  const [tecnicos, setTecnicos] = useState<Tecnico[]>([])
  const [sectores, setSectores] = useState<Sector[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [saving, setSaving] = useState(false)

  const form = useForm<IncidenciaFormValues>({
    resolver: zodResolver(incidenciaSchema),
    defaultValues: EMPTY_VALUES,
  })

  useEffect(() => {
    loadAll()
  }, [])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  const clienteNombre = (id: number) => clientes.find((c) => c.id === id)?.nombre ?? `#${id}`
  const equipoNombre = (id: number | null) => id ? (equipos.find((e) => e.id === id)?.tipo ?? `#${id}`) : '—'
  const tecnicoNombre = (id: number | null) => id ? (tecnicos.find((t) => t.id === id)?.nombre ?? `#${id}`) : '—'

  async function loadAll() {
    setLoading(true)
    setError(null)
    try {
      const [inc, cl, eq, te, se] = await Promise.all([
        api.get<Incidencia[]>('/api/incidencias'),
        api.get<Cliente[]>('/api/clientes'),
        api.get<Equipo[]>('/api/equipos'),
        api.get<Tecnico[]>('/api/tecnicos'),
        api.get<Sector[]>('/api/sectores'),
      ])
      setIncidencias(inc)
      setClientes(cl)
      setEquipos(eq)
      setTecnicos(te)
      setSectores(se)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  function startCreate() {
    setEditingId('new')
    form.reset(EMPTY_VALUES)
  }

  function startEdit(incidencia: Incidencia) {
    setEditingId(incidencia.id)
    form.reset({
      cliente_id: String(incidencia.cliente_id),
      equipo_id: incidencia.equipo_id ? String(incidencia.equipo_id) : NONE,
      tecnico_id: incidencia.tecnico_id ? String(incidencia.tecnico_id) : NONE,
      sector_id: incidencia.sector_id ? String(incidencia.sector_id) : NONE,
      titulo: incidencia.titulo,
      descripcion: incidencia.descripcion ?? '',
      estado: incidencia.estado,
      prioridad: incidencia.prioridad,
      horas_invertidas: incidencia.horas_invertidas?.toString() ?? '',
      notas: incidencia.notas ?? '',
      resolucion: incidencia.resolucion ?? '',
    })
  }

  function cancelEdit() {
    setEditingId(null)
    form.reset(EMPTY_VALUES)
  }

  async function handleSubmit(values: IncidenciaFormValues) {
    setSaving(true)
    setError(null)
    const payload = {
      cliente_id: Number(values.cliente_id),
      equipo_id: values.equipo_id && values.equipo_id !== NONE ? Number(values.equipo_id) : null,
      tecnico_id: values.tecnico_id && values.tecnico_id !== NONE ? Number(values.tecnico_id) : null,
      sector_id: values.sector_id && values.sector_id !== NONE ? Number(values.sector_id) : null,
      titulo: values.titulo,
      descripcion: values.descripcion || null,
      estado: values.estado,
      prioridad: values.prioridad,
      horas_invertidas: values.horas_invertidas ? Number(values.horas_invertidas) : null,
      notas: values.notas || null,
      resolucion: values.resolucion || null,
      estado_facturacion: null,
      activo: true,
    }
    try {
      if (editingId === 'new') {
        await api.post('/api/incidencias', payload)
      } else if (editingId) {
        await api.put(`/api/incidencias/${editingId}`, payload)
      }
      cancelEdit()
      await loadAll()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(incidencia: Incidencia) {
    setError(null)
    try {
      await api.del(`/api/incidencias/${incidencia.id}`)
      await loadAll()
    } catch (err) {
      setError(describeError(err))
    }
  }

  const columns = useMemo<ColumnDef<Incidencia>[]>(() => [
    { accessorKey: 'titulo', header: sortableHeader('Título'), size: 220, minSize: 140, meta: { stretch: true }, cell: ({ row }) => <span className="block truncate font-medium" title={row.original.titulo}>{row.original.titulo}</span> },
    { accessorKey: 'cliente_id', header: 'Cliente', size: 150, minSize: 110, cell: ({ row }) => clienteNombre(row.original.cliente_id) },
    { accessorKey: 'equipo_id', header: 'Equipo', size: 130, minSize: 100, cell: ({ row }) => equipoNombre(row.original.equipo_id) },
    { accessorKey: 'tecnico_id', header: 'Técnico', size: 130, minSize: 100, cell: ({ row }) => tecnicoNombre(row.original.tecnico_id) },
    {
      accessorKey: 'prioridad',
      header: 'Prioridad',
      size: 100,
      minSize: 85,
      cell: ({ row }) => (
        <Badge variant={row.original.prioridad === 'alta' ? 'destructive' : 'outline'}>
          {PRIORIDAD_LABELS[row.original.prioridad]}
        </Badge>
      ),
    },
    {
      accessorKey: 'estado',
      header: 'Estado',
      size: 120,
      minSize: 95,
      cell: ({ row }) => (
        <Badge variant={row.original.estado === 'cerrado' || row.original.estado === 'resuelta' ? 'default' : 'outline'}>
          {ESTADO_LABELS[row.original.estado]}
        </Badge>
      ),
    },
    {
      id: 'actions',
      header: () => <div className="text-right">Acciones</div>,
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          <Button size="icon" variant="outline" title="Editar incidencia" aria-label="Editar incidencia" onClick={() => startEdit(row.original)}><Pencil /></Button>
          <Button size="icon" variant="outline" className="text-destructive hover:text-destructive" title="Eliminar incidencia" aria-label="Eliminar incidencia" onClick={() => handleDelete(row.original)}><Trash2 /></Button>
        </div>
      ),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [clientes, equipos, tecnicos])

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Incidencias</h2>
        {editingId === null && <Button onClick={startCreate}>+ Nueva incidencia</Button>}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {editingId !== null && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{editingId === 'new' ? 'Nueva incidencia' : 'Editar incidencia'}</CardTitle>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form className="flex flex-wrap items-start gap-3" onSubmit={form.handleSubmit(handleSubmit)}>
                <FormField control={form.control} name="cliente_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Cliente</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl><SelectTrigger className="w-44"><SelectValue placeholder="Cliente…" /></SelectTrigger></FormControl>
                      <SelectContent>
                        {clientes.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.nombre}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="equipo_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Equipo</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl><SelectTrigger className="w-40"><SelectValue /></SelectTrigger></FormControl>
                      <SelectContent>
                        <SelectItem value={NONE}>Sin equipo</SelectItem>
                        {equipos.map((e) => <SelectItem key={e.id} value={String(e.id)}>{e.tipo} — {clienteNombre(e.cliente_id)}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="tecnico_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Técnico</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl><SelectTrigger className="w-40"><SelectValue /></SelectTrigger></FormControl>
                      <SelectContent>
                        <SelectItem value={NONE}>Sin asignar</SelectItem>
                        {tecnicos.map((t) => <SelectItem key={t.id} value={String(t.id)}>{t.nombre}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="sector_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Sector</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl><SelectTrigger className="w-40"><SelectValue /></SelectTrigger></FormControl>
                      <SelectContent>
                        <SelectItem value={NONE}>Sin sector</SelectItem>
                        {sectores.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.nombre}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="titulo" render={({ field }) => (
                  <FormItem className="w-full">
                    <FormLabel>Título</FormLabel>
                    <FormControl><Input {...field} /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="descripcion" render={({ field }) => (
                  <FormItem className="w-full">
                    <FormLabel>Descripción</FormLabel>
                    <FormControl>
                      <textarea {...field} rows={2} className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="estado" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Estado</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl><SelectTrigger className="w-40"><SelectValue /></SelectTrigger></FormControl>
                      <SelectContent>
                        {(Object.keys(ESTADO_LABELS) as (keyof typeof ESTADO_LABELS)[]).map((e) => (
                          <SelectItem key={e} value={e}>{ESTADO_LABELS[e]}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="prioridad" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Prioridad</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl><SelectTrigger className="w-32"><SelectValue /></SelectTrigger></FormControl>
                      <SelectContent>
                        {(Object.keys(PRIORIDAD_LABELS) as (keyof typeof PRIORIDAD_LABELS)[]).map((p) => (
                          <SelectItem key={p} value={p}>{PRIORIDAD_LABELS[p]}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="horas_invertidas" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Horas</FormLabel>
                    <FormControl><Input type="number" step="0.5" {...field} className="w-24" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="resolucion" render={({ field }) => (
                  <FormItem className="w-full">
                    <FormLabel>Resolución</FormLabel>
                    <FormControl>
                      <textarea {...field} rows={2} className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <div className="flex gap-2 pt-6">
                  <Button type="submit" disabled={saving}>
                    {saving ? 'Guardando…' : editingId === 'new' ? 'Crear' : 'Guardar'}
                  </Button>
                  <Button type="button" variant="outline" onClick={cancelEdit}>Cancelar</Button>
                </div>
              </form>
            </Form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable columns={columns} data={incidencias} emptyMessage="Sin incidencias todavía." />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
