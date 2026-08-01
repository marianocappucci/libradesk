import { useEffect, useMemo, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { api, ApiError, type Cliente, type Sector } from '../api'
import { useAuth } from '../context/AuthContext'
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
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Check, MapPin, Pencil, Trash2, X } from 'lucide-react'

const clienteSchema = z.object({
  nombre: z.string().trim().min(1, 'El nombre es obligatorio'),
  empresa: z.string().trim().optional(),
  email: z.string().trim().email('Email inválido').optional().or(z.literal('')),
  telefono: z.string().trim().optional(),
  ciudad: z.string().trim().optional(),
  observaciones: z.string().trim().optional(),
  tipo_facturacion: z.enum(['mensual', 'por_servicio']),
})

type ClienteFormValues = z.infer<typeof clienteSchema>

const EMPTY_VALUES: ClienteFormValues = {
  nombre: '', empresa: '', email: '', telefono: '', ciudad: '', observaciones: '',
  tipo_facturacion: 'por_servicio',
}

export function Clientes() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [clientes, setClientes] = useState<Cliente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [saving, setSaving] = useState(false)

  // --- sectores del cliente -------------------------------------------
  // El backend los tenía completos desde la migración (tabla propia con FK
  // al cliente, router con alta/baja/renombrado y 15 filas reales), pero no
  // había ninguna pantalla: el único lugar del sistema donde se veían era el
  // selector de filtro del reporte de incidencias.
  const [sectoresDe, setSectoresDe] = useState<Cliente | null>(null)
  const [sectores, setSectores] = useState<Sector[] | null>(null)
  const [errorSector, setErrorSector] = useState<string | null>(null)
  const [nuevoSector, setNuevoSector] = useState('')
  const [guardandoSector, setGuardandoSector] = useState(false)
  const [renombrando, setRenombrando] = useState<{ id: number; nombre: string } | null>(null)
  const [aBorrar, setABorrar] = useState<Sector | null>(null)

  const form = useForm<ClienteFormValues>({
    resolver: zodResolver(clienteSchema),
    defaultValues: EMPTY_VALUES,
  })

  useEffect(() => {
    loadClientes()
  }, [])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function loadClientes() {
    setLoading(true)
    setError(null)
    try {
      const items = await api.get<Cliente[]>('/api/clientes')
      setClientes(items.sort((a, b) => a.nombre.localeCompare(b.nombre)))
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

  function startEdit(cliente: Cliente) {
    setEditingId(cliente.id)
    form.reset({
      nombre: cliente.nombre,
      empresa: cliente.empresa ?? '',
      email: cliente.email ?? '',
      telefono: cliente.telefono ?? '',
      ciudad: cliente.ciudad ?? '',
      observaciones: cliente.observaciones ?? '',
      tipo_facturacion: cliente.tipo_facturacion,
    })
  }

  function cancelEdit() {
    setEditingId(null)
    form.reset(EMPTY_VALUES)
  }

  async function handleSubmit(values: ClienteFormValues) {
    setSaving(true)
    setError(null)
    const payload = {
      nombre: values.nombre,
      empresa: values.empresa || null,
      email: values.email || null,
      telefono: values.telefono || null,
      ciudad: values.ciudad || null,
      observaciones: values.observaciones || null,
      tipo_facturacion: values.tipo_facturacion,
      activo: true,
    }
    try {
      if (editingId === 'new') {
        await api.post('/api/clientes', payload)
      } else if (editingId) {
        await api.put(`/api/clientes/${editingId}`, payload)
      }
      cancelEdit()
      await loadClientes()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(cliente: Cliente) {
    setError(null)
    try {
      await api.del(`/api/clientes/${cliente.id}`)
      await loadClientes()
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function abrirSectores(cliente: Cliente) {
    setSectoresDe(cliente)
    setSectores(null)
    setErrorSector(null)
    setNuevoSector('')
    setRenombrando(null)
    await recargarSectores(cliente.id)
  }

  async function recargarSectores(clienteId: number) {
    try {
      setSectores(await api.get<Sector[]>(`/api/sectores?cliente_id=${clienteId}`))
    } catch (err) {
      setErrorSector(describeError(err))
    }
  }

  async function crearSector() {
    if (!sectoresDe || !nuevoSector.trim()) return
    setGuardandoSector(true)
    setErrorSector(null)
    try {
      await api.post('/api/sectores', { cliente_id: sectoresDe.id, nombre: nuevoSector.trim() })
      setNuevoSector('')
      await recargarSectores(sectoresDe.id)
    } catch (err) {
      // El 409 del backend (unique cliente_id + nombre) llega con su propio
      // detalle: "sector ya existe para este cliente".
      setErrorSector(describeError(err))
    } finally {
      setGuardandoSector(false)
    }
  }

  async function renombrarSector() {
    if (!sectoresDe || !renombrando || !renombrando.nombre.trim()) return
    setGuardandoSector(true)
    setErrorSector(null)
    try {
      await api.put(`/api/sectores/${renombrando.id}`, { nombre: renombrando.nombre.trim() })
      setRenombrando(null)
      await recargarSectores(sectoresDe.id)
    } catch (err) {
      setErrorSector(describeError(err))
    } finally {
      setGuardandoSector(false)
    }
  }

  async function borrarSector(sector: Sector) {
    if (!sectoresDe) return
    setErrorSector(null)
    try {
      await api.del(`/api/sectores/${sector.id}`)
      await recargarSectores(sectoresDe.id)
    } catch (err) {
      setErrorSector(describeError(err))
    }
  }

  const columns = useMemo<ColumnDef<Cliente>[]>(() => {
    const base: ColumnDef<Cliente>[] = [
      { accessorKey: 'nombre', header: sortableHeader('Nombre'), size: 180, minSize: 120, meta: { stretch: true }, cell: ({ row }) => <span className="block truncate font-medium" title={row.original.nombre}>{row.original.nombre}</span> },
      { accessorKey: 'empresa', header: 'Empresa', size: 160, minSize: 100, cell: ({ row }) => row.original.empresa ?? '—' },
      { accessorKey: 'telefono', header: 'Teléfono', size: 130, minSize: 100, cell: ({ row }) => row.original.telefono ?? '—' },
      { accessorKey: 'email', header: 'Email', size: 190, minSize: 140, cell: ({ row }) => <span className="block truncate" title={row.original.email ?? undefined}>{row.original.email ?? '—'}</span> },
      { accessorKey: 'ciudad', header: 'Ciudad', size: 120, minSize: 90, cell: ({ row }) => row.original.ciudad ?? '—' },
      {
        accessorKey: 'activo',
        header: 'Estado',
        size: 100,
        minSize: 85,
        cell: ({ row }) => (
          <Badge variant={row.original.activo ? 'default' : 'outline'}>
            {row.original.activo ? 'Activo' : 'Inactivo'}
          </Badge>
        ),
      },
    ]
    if (isAdmin) {
      base.push({
        id: 'actions',
        header: () => <div className="text-right">Acciones</div>,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button size="icon" variant="outline" title="Sectores del cliente" aria-label="Sectores del cliente" onClick={() => abrirSectores(row.original)}><MapPin /></Button>
            <Button size="icon" variant="outline" title="Editar cliente" aria-label="Editar cliente" onClick={() => startEdit(row.original)}><Pencil /></Button>
            <Button size="icon" variant="outline" className="text-destructive hover:text-destructive" title="Eliminar cliente" aria-label="Eliminar cliente" onClick={() => handleDelete(row.original)}><Trash2 /></Button>
          </div>
        ),
      })
    }
    return base
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin])

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Clientes</h2>
        {isAdmin && editingId === null && (
          <Button onClick={startCreate}>+ Nuevo cliente</Button>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {isAdmin && editingId !== null && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{editingId === 'new' ? 'Nuevo cliente' : 'Editar cliente'}</CardTitle>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form className="flex flex-wrap items-start gap-3" onSubmit={form.handleSubmit(handleSubmit)}>
                <FormField control={form.control} name="nombre" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Nombre</FormLabel>
                    <FormControl><Input {...field} className="w-48" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="empresa" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Empresa</FormLabel>
                    <FormControl><Input {...field} className="w-44" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="telefono" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Teléfono</FormLabel>
                    <FormControl><Input {...field} className="w-36" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="email" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Email</FormLabel>
                    <FormControl><Input type="email" {...field} className="w-52" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="ciudad" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Ciudad</FormLabel>
                    <FormControl><Input {...field} className="w-36" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="tipo_facturacion" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Facturación</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="w-40">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="por_servicio">Por servicio</SelectItem>
                        <SelectItem value="mensual">Mensual</SelectItem>
                      </SelectContent>
                    </Select>
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
            <DataTable
              columns={columns}
              data={clientes}
              emptyMessage="Sin clientes todavía."
              search={{
                campos: (c) => [c.nombre, c.empresa, c.email, c.telefono, c.ciudad],
                placeholder: 'Buscar por nombre, empresa, email, teléfono o ciudad',
              }}
            />
          )}
        </CardContent>
      </Card>

      <Dialog open={sectoresDe !== null} onOpenChange={(open) => !open && setSectoresDe(null)}>
        <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Sectores</DialogTitle>
            <DialogDescription>
              {sectoresDe?.nombre} — las áreas del cliente, para clasificar
              las incidencias por sector de origen.
            </DialogDescription>
          </DialogHeader>

          {errorSector && <p className="text-sm text-destructive">{errorSector}</p>}

          <form
            className="flex items-end gap-2"
            onSubmit={(e) => { e.preventDefault(); crearSector() }}
          >
            <div className="grid flex-1 gap-1.5">
              <span className="text-xs text-muted-foreground">Nuevo sector</span>
              <Input
                value={nuevoSector}
                onChange={(e) => setNuevoSector(e.target.value)}
                placeholder="Administración, Depósito, Consultorios…"
                aria-label="Nombre del sector nuevo"
              />
            </div>
            <Button type="submit" disabled={guardandoSector || !nuevoSector.trim()}>Agregar</Button>
          </form>

          {sectores === null ? (
            <p className="py-4 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : sectores.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              Este cliente todavía no tiene sectores.
            </p>
          ) : (
            <ul className="divide-y rounded-md border">
              {sectores.map((s) => (
                <li key={s.id} className="flex items-center gap-2 px-3 py-2">
                  {renombrando?.id === s.id ? (
                    <>
                      <Input
                        value={renombrando.nombre}
                        onChange={(e) => setRenombrando({ id: s.id, nombre: e.target.value })}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') { e.preventDefault(); renombrarSector() }
                          if (e.key === 'Escape') setRenombrando(null)
                        }}
                        aria-label={`Nuevo nombre para ${s.nombre}`}
                        autoFocus
                        className="h-8 flex-1"
                      />
                      <Button size="icon" variant="outline" className="size-8" title="Guardar" aria-label="Guardar nombre" disabled={guardandoSector || !renombrando.nombre.trim()} onClick={renombrarSector}><Check /></Button>
                      <Button size="icon" variant="ghost" className="size-8" title="Cancelar" aria-label="Cancelar renombrado" onClick={() => setRenombrando(null)}><X /></Button>
                    </>
                  ) : (
                    <>
                      <span className="flex-1 text-sm">{s.nombre}</span>
                      <Button size="icon" variant="outline" className="size-8" title="Renombrar sector" aria-label={`Renombrar ${s.nombre}`} onClick={() => setRenombrando({ id: s.id, nombre: s.nombre })}><Pencil /></Button>
                      <Button size="icon" variant="outline" className="size-8 text-destructive hover:text-destructive" title="Eliminar sector" aria-label={`Eliminar ${s.nombre}`} onClick={() => setABorrar(s)}><Trash2 /></Button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={aBorrar !== null}
        onOpenChange={(open) => !open && setABorrar(null)}
        title={`¿Eliminar el sector "${aBorrar?.nombre}"?`}
        // Es lo que hace el backend de verdad: el ondelete="SET NULL" del
        // modelo no corre (el pragma está apagado), así que la desasignación
        // se hace explícita en el repositorio.
        description="Las incidencias que lo tengan asignado quedan sin sector. No se borra ninguna incidencia."
        onConfirm={() => { const s = aBorrar; setABorrar(null); if (s) borrarSector(s) }}
      />
    </div>
  )
}
