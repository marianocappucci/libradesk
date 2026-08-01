import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import {
  api, ApiError, ESTADO_LABELS, PRIORIDAD_LABELS, opcionesCliente, opcionesEquipo,
  type Cliente, type Equipo, type Incidencia,
} from '../api'
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
import { CircleAlert, Plus } from 'lucide-react'

const NONE = '__none__'
const TODOS = '__todos__'

const incidenciaSchema = z.object({
  cliente_id: z.string().min(1, 'Elegí un cliente'),
  equipo_id: z.string().optional(),
  titulo: z.string().trim().min(1, 'El título es obligatorio'),
  descripcion: z.string().trim().optional(),
})

type IncidenciaFormValues = z.infer<typeof incidenciaSchema>

const EMPTY_VALUES: IncidenciaFormValues = {
  cliente_id: '', equipo_id: NONE, titulo: '', descripcion: '',
}

export function Incidencias() {
  const navigate = useNavigate()
  const [incidencias, setIncidencias] = useState<Incidencia[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [equipos, setEquipos] = useState<Equipo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // El alta vive en un Dialog (antes era una card sobre la tabla), mismo
  // patrón que Contalibra y que el resto de las pantallas del producto.
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  // El error del formulario va DENTRO del modal; el de la página quedaría tapado.
  const [formError, setFormError] = useState<string | null>(null)

  const [filtroEstado, setFiltroEstado] = useState(TODOS)
  const [filtroPrioridad, setFiltroPrioridad] = useState(TODOS)
  const [filtroCliente, setFiltroCliente] = useState(TODOS)

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

  // Un cliente desactivado no se ofrece para tickets nuevos. Se contempla el
  // preseleccionado por el filtro para que el formulario nunca arranque
  // apuntando a una opción que no existe en su propia lista.
  const clientesElegibles = clientes.filter(
    (c) => c.activo || String(c.id) === form.watch('cliente_id'),
  )

  async function loadAll() {
    setLoading(true)
    setError(null)
    try {
      const [inc, cl, eq] = await Promise.all([
        api.get<Incidencia[]>('/api/incidencias'),
        api.get<Cliente[]>('/api/clientes'),
        api.get<Equipo[]>('/api/equipos'),
      ])
      setIncidencias(inc)
      setClientes(cl)
      setEquipos(eq)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  function startCreate() {
    setCreating(true)
    setFormError(null)
    // Si hay un cliente filtrado, el alta arranca con ése elegido.
    form.reset({ ...EMPTY_VALUES, cliente_id: filtroCliente === TODOS ? '' : filtroCliente })
  }

  async function handleSubmit(values: IncidenciaFormValues) {
    setSaving(true)
    setFormError(null)
    const payload = {
      cliente_id: Number(values.cliente_id),
      equipo_id: values.equipo_id && values.equipo_id !== NONE ? Number(values.equipo_id) : null,
      tecnico_id: null,
      sector_id: null,
      titulo: values.titulo,
      descripcion: values.descripcion || null,
      estado: 'abierto' as const,
      prioridad: 'media' as const,
      horas_invertidas: null,
      notas: null,
      resolucion: null,
      estado_facturacion: null,
      activo: true,
    }
    try {
      const nueva = await api.post<Incidencia>('/api/incidencias', payload)
      setCreating(false)
      navigate(`/incidencias/${nueva.id}`)
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  const incidenciasFiltradas = useMemo(() => incidencias.filter((i) =>
    (filtroEstado === TODOS || i.estado === filtroEstado)
    && (filtroPrioridad === TODOS || i.prioridad === filtroPrioridad)
    && (filtroCliente === TODOS || i.cliente_id === Number(filtroCliente)),
  ), [incidencias, filtroEstado, filtroPrioridad, filtroCliente])

  const columns = useMemo<ColumnDef<Incidencia>[]>(() => [
    { accessorKey: 'titulo', header: sortableHeader('Título'), size: 240, minSize: 140, meta: { stretch: true }, cell: ({ row }) => <span className="block truncate font-medium" title={row.original.titulo}>{row.original.titulo}</span> },
    { accessorKey: 'cliente_id', header: 'Cliente', size: 150, minSize: 110, cell: ({ row }) => clienteNombre(row.original.cliente_id) },
    { accessorKey: 'equipo_id', header: 'Equipo', size: 130, minSize: 100, cell: ({ row }) => equipoNombre(row.original.equipo_id) },
    {
      accessorKey: 'prioridad',
      header: sortableHeader('Prioridad'),
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
      header: sortableHeader('Estado'),
      size: 120,
      minSize: 95,
      cell: ({ row }) => (
        <Badge variant={row.original.estado === 'cerrado' || row.original.estado === 'resuelta' ? 'default' : 'outline'}>
          {ESTADO_LABELS[row.original.estado]}
        </Badge>
      ),
    },
    {
      accessorKey: 'fecha_creacion',
      header: sortableHeader('Creada'),
      size: 110,
      minSize: 95,
      cell: ({ row }) => row.original.fecha_creacion ? new Date(row.original.fecha_creacion).toLocaleDateString('es-AR') : '—',
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [clientes, equipos])

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Incidencias</h2>
        <Dialog open={creating} onOpenChange={setCreating}>
          <DialogTrigger asChild>
            <Button onClick={startCreate}><Plus />Nueva incidencia</Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-2xl">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CircleAlert className="size-4" />Nueva incidencia
              </DialogTitle>
              <DialogDescription>
                El resto de los campos —prioridad, técnico, sector, horas— se
                asignan después desde el ticket.
              </DialogDescription>
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
                        className="w-44"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="equipo_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Equipo</FormLabel>
                    <FormControl>
                      <SelectBuscable
                        value={field.value ?? NONE}
                        onChange={field.onChange}
                        // Sólo los equipos del cliente elegido: ofrecer el
                        // parque entero de todos los clientes es lo que hacía
                        // esta lista inmanejable, y además deja elegir un
                        // equipo que no es de ese cliente.
                        opciones={[
                          { value: NONE, label: 'Sin equipo' },
                          ...opcionesEquipo(
                            equipos.filter((e) => String(e.cliente_id) === form.watch('cliente_id')),
                          ),
                        ]}
                        ariaLabel="Equipo"
                        className="w-44"
                        emptyMessage="Ese cliente no tiene equipos."
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="titulo" render={({ field }) => (
                  <FormItem className="w-full">
                    <FormLabel>Título</FormLabel>
                    <FormControl><Input {...field} placeholder="Resumen breve del problema" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="descripcion" render={({ field }) => (
                  <FormItem className="w-full">
                    <FormLabel>Descripción</FormLabel>
                    <FormControl>
                      <textarea {...field} rows={3} className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <DialogFooter className="w-full">
                  <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
                  <Button type="submit" disabled={saving}>{saving ? 'Creando…' : 'Crear incidencia'}</Button>
                </DialogFooter>
              </form>
            </Form>
          </DialogContent>
        </Dialog>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex flex-wrap items-end gap-3">
        <div className="grid gap-1.5">
          <span className="text-xs text-muted-foreground">Estado</span>
          <Select value={filtroEstado} onValueChange={setFiltroEstado}>
            <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={TODOS}>Todos</SelectItem>
              {(Object.keys(ESTADO_LABELS) as (keyof typeof ESTADO_LABELS)[]).map((e) => (
                <SelectItem key={e} value={e}>{ESTADO_LABELS[e]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <span className="text-xs text-muted-foreground">Prioridad</span>
          <Select value={filtroPrioridad} onValueChange={setFiltroPrioridad}>
            <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={TODOS}>Todas</SelectItem>
              {(Object.keys(PRIORIDAD_LABELS) as (keyof typeof PRIORIDAD_LABELS)[]).map((p) => (
                <SelectItem key={p} value={p}>{PRIORIDAD_LABELS[p]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <span className="text-xs text-muted-foreground">Cliente</span>
          <SelectBuscable
            value={filtroCliente}
            onChange={setFiltroCliente}
            opciones={[{ value: TODOS, label: 'Todos' }, ...opcionesCliente(clientes)]}
            ariaLabel="Filtrar por cliente"
            className="w-48"
          />
        </div>
        {(filtroEstado !== TODOS || filtroPrioridad !== TODOS || filtroCliente !== TODOS) && (
          <Button variant="ghost" size="sm" onClick={() => { setFiltroEstado(TODOS); setFiltroPrioridad(TODOS); setFiltroCliente(TODOS) }}>
            Limpiar filtros
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
              data={incidenciasFiltradas}
              emptyMessage="Sin incidencias todavía."
              onRowClick={(i) => navigate(`/incidencias/${i.id}`)}
              search={{
                // El número de ticket entra a propósito: es como se lo nombra
                // por teléfono ("fijate el 14"), y sin él habría que acordarse
                // del título para encontrarlo.
                campos: (i) => [
                  i.id, i.titulo, i.descripcion,
                  clienteNombre(i.cliente_id), equipoNombre(i.equipo_id),
                ],
                placeholder: 'Buscar por número, título, descripción, cliente o equipo',
              }}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
