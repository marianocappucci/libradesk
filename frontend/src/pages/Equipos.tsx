import { useEffect, useMemo, useRef, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { useNavigate } from 'react-router-dom'
import {
  api, ApiError, ESTADO_EQUIPO_LABELS, describirEquipo, lugarDe, opcionesCliente,
  opcionesDeposito, ubicacionTexto,
  type Cliente, type Deposito, type Equipo,
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
  Dialog, DialogClose, DialogContent, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
import Monitor from '~icons/fluent-color/laptop-16'
import { Eye, Pencil, Plus, Trash2 } from '@/components/iconos-accion'

// Sin depósito: el equipo está instalado en el sector del cliente. Radix no
// admite un <SelectItem value="">, así que el "ninguno" necesita valor propio.
const SIN_DEPOSITO = '__ninguno__'

const equipoSchema = z.object({
  cliente_id: z.string().min(1, 'Elegí un cliente'),
  tipo: z.string().trim().min(1, 'El tipo es obligatorio'),
  marca: z.string().trim().optional(),
  modelo: z.string().trim().optional(),
  serial: z.string().trim().optional(),
  ubicacion_oficina: z.string().trim().optional(),
  sector: z.string().trim().optional(),
  deposito_id: z.string().optional(),
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
  ubicacion_oficina: '', sector: '', deposito_id: SIN_DEPOSITO, estado: 'activo',
  garantia_vence: '', observaciones: '', motivo: '',
}

const ESTADOS_EQUIPO = ['activo', 'en_reparacion', 'almacenado', 'baja']

// Radix no admite un <SelectItem value="">, así que el "sin filtro" necesita
// un valor propio (misma convención que Incidencias.tsx).
const TODOS = 'todos'

export function Equipos() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const navigate = useNavigate()

  const [equipos, setEquipos] = useState<Equipo[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [depositos, setDepositos] = useState<Deposito[]>([])
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

  // Depósitos ofrecibles: los propios de la empresa (reciben equipos de
  // cualquier cliente) más los del cliente que se está eligiendo en el
  // formulario. Es la misma regla que valida el backend; ofrecer los de otro
  // cliente sería ofrecer algo que va a volver con un 422.
  const depositosElegibles = depositos.filter(
    (d) => d.cliente_id === null || String(d.cliente_id) === form.watch('cliente_id'),
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
      // Sólo los activos: el selector del formulario es para elegir a dónde va
      // el equipo, y un depósito dado de baja no es un destino válido.
      const [eq, cl, dep] = await Promise.all([
        api.get<Equipo[]>(rutaEquipos()),
        api.get<Cliente[]>('/api/clientes'),
        api.get<Deposito[]>('/api/depositos?solo_activos=true'),
      ])
      setEquipos(eq)
      setClientes(cl)
      setDepositos(dep)
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
      deposito_id: equipo.deposito_id === null ? SIN_DEPOSITO : String(equipo.deposito_id),
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
      deposito_id: !values.deposito_id || values.deposito_id === SIN_DEPOSITO
        ? null
        : Number(values.deposito_id),
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
        id: 'lugar',
        header: 'Dónde está',
        size: 160,
        minSize: 110,
        // Depósito o sector, nunca los dos: un equipo guardado en el taller no
        // está en ningún sector del cliente. Ver `lugarDe`.
        cell: ({ row }) => {
          const e = row.original
          return (
            <span className="flex items-center gap-1.5">
              {ubicacionTexto(lugarDe(e.deposito_nombre, e.sector), e.ubicacion_oficina)}
              {e.deposito_nombre && <Badge variant="secondary">Depósito</Badge>}
            </span>
          )
        },
      },
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
    // La ficha es de solo lectura, así que la ve cualquier usuario logueado;
    // editar y borrar siguen siendo admin-only.
    base.push({
      id: 'actions',
      header: () => <div className="text-right">Acciones</div>,
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          <Button size="icon" variant="outline" title="Ver ficha del equipo" aria-label="Ver ficha del equipo" onClick={() => navigate(`/equipos/${row.original.id}`)}><Eye /></Button>
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
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Monitor className="size-5" />Equipos
        </h2>
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
                {/* Guardar el equipo en un depósito reemplaza al sector como
                    ubicación efectiva; el sector queda como de dónde salió.
                    Sólo se ofrecen los propios y los del cliente elegido: el
                    backend rechaza el resto (ver `_validar_deposito`). */}
                <FormField control={form.control} name="deposito_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Depósito</FormLabel>
                    <FormControl>
                      <SelectBuscable
                        value={field.value || SIN_DEPOSITO}
                        onChange={field.onChange}
                        opciones={[
                          { value: SIN_DEPOSITO, label: 'Ninguno (en el puesto)' },
                          ...opcionesDeposito(depositosElegibles),
                        ]}
                        ariaLabel="Depósito"
                        className="w-52"
                      />
                    </FormControl>
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
              onRowClick={(e) => navigate(`/equipos/${e.id}`)}
              search={{
                campos: (e) => [
                  e.tipo, e.marca, e.modelo, e.serial,
                  e.sector, e.deposito_nombre, e.ubicacion_oficina,
                  clienteNombre(e.cliente_id),
                ],
                placeholder: 'Buscar por tipo, marca, modelo, serial, depósito, sector o cliente',
              }}
            />
          )}
        </CardContent>
      </Card>

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
