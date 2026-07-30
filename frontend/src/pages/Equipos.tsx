import { useEffect, useMemo, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { api, ApiError, type Cliente, type Equipo, type EquipoMovimiento } from '../api'
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
import { History, Pencil, Trash2 } from 'lucide-react'

const MOV_LABELS: Record<string, string> = {
  alta: 'Alta', baja: 'Baja', traslado: 'Traslado',
  en_reparacion: 'Reparación', almacenado: 'Almacenado', activo: 'Reactivado',
}

function formatFecha(fecha: string | null): string {
  if (!fecha) return '—'
  return new Date(fecha).toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' })
}

function ubicacionTexto(sector: string | null, ubicacion: string | null): string | null {
  return [sector, ubicacion].filter(Boolean).join(' · ') || null
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
const ESTADO_LABELS: Record<string, string> = {
  activo: 'Activo', en_reparacion: 'En reparación', almacenado: 'En depósito', baja: 'Baja',
}

export function Equipos() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [equipos, setEquipos] = useState<Equipo[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [saving, setSaving] = useState(false)
  const [historialDe, setHistorialDe] = useState<Equipo | null>(null)
  const [movimientos, setMovimientos] = useState<EquipoMovimiento[] | null>(null)

  const form = useForm<EquipoFormValues>({
    resolver: zodResolver(equipoSchema),
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

  async function loadAll() {
    setLoading(true)
    setError(null)
    try {
      const [eq, cl] = await Promise.all([
        api.get<Equipo[]>('/api/equipos'),
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

  function startCreate() {
    setEditingId('new')
    form.reset(EMPTY_VALUES)
  }

  function startEdit(equipo: Equipo) {
    setEditingId(equipo.id)
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
  }

  function cancelEdit() {
    setEditingId(null)
    form.reset(EMPTY_VALUES)
  }

  async function handleSubmit(values: EquipoFormValues) {
    setSaving(true)
    setError(null)
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
      if (editingId === 'new') {
        await api.post('/api/equipos', payload)
      } else if (editingId) {
        await api.put(`/api/equipos/${editingId}`, { ...payload, motivo: values.motivo || null })
      }
      cancelEdit()
      await loadAll()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function verHistorial(equipo: Equipo) {
    setHistorialDe(equipo)
    setMovimientos(null)
    try {
      setMovimientos(await api.get<EquipoMovimiento[]>(`/api/equipos/${equipo.id}/movimientos`))
    } catch (err) {
      setError(describeError(err))
      setHistorialDe(null)
    }
  }

  async function handleDelete(equipo: Equipo) {
    setError(null)
    try {
      await api.del(`/api/equipos/${equipo.id}`)
      await loadAll()
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
            {ESTADO_LABELS[row.original.estado] ?? row.original.estado}
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
              <Button size="icon" variant="outline" title="Editar equipo" aria-label="Editar equipo" onClick={() => startEdit(row.original)}><Pencil /></Button>
              <Button size="icon" variant="outline" className="text-destructive hover:text-destructive" title="Eliminar equipo" aria-label="Eliminar equipo" onClick={() => handleDelete(row.original)}><Trash2 /></Button>
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
        {isAdmin && editingId === null && (
          <Button onClick={startCreate}>+ Nuevo equipo</Button>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {isAdmin && editingId !== null && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{editingId === 'new' ? 'Nuevo equipo' : 'Editar equipo'}</CardTitle>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form className="flex flex-wrap items-start gap-3" onSubmit={form.handleSubmit(handleSubmit)}>
                <FormField control={form.control} name="cliente_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Cliente</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="w-48">
                          <SelectValue placeholder="Cliente…" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {clientes.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.nombre}</SelectItem>)}
                      </SelectContent>
                    </Select>
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
                        {ESTADOS_EQUIPO.map((e) => <SelectItem key={e} value={e}>{ESTADO_LABELS[e]}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )} />
                {editingId !== 'new' && (
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
            <DataTable columns={columns} data={equipos} emptyMessage="Sin equipos todavía." />
          )}
        </CardContent>
      </Card>

      <Dialog open={historialDe !== null} onOpenChange={(open) => !open && setHistorialDe(null)}>
        <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Historial de movimientos</DialogTitle>
            <DialogDescription>
              {historialDe && [historialDe.tipo, historialDe.marca, historialDe.modelo].filter(Boolean).join(' ')}
              {historialDe?.serial ? ` — ${historialDe.serial}` : ''}
            </DialogDescription>
          </DialogHeader>

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
                const destino = ubicacionTexto(m.sector_destino, m.ubicacion_destino)
                return (
                  <div key={m.id} className="grid gap-0.5 rounded-md border px-3 py-2 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={m.tipo === 'baja' ? 'destructive' : 'outline'}>
                        {MOV_LABELS[m.tipo] ?? m.tipo}
                      </Badge>
                      <span className="font-medium">{m.descripcion ?? '—'}</span>
                    </div>
                    {(origen || destino) && (
                      <span className="text-xs text-muted-foreground">
                        {origen ?? 'sin ubicación'} → {destino ?? 'sin ubicación'}
                      </span>
                    )}
                    {m.motivo && <span className="text-xs text-muted-foreground">Motivo: {m.motivo}</span>}
                    <span className="text-xs text-muted-foreground">
                      {m.usuario} · {formatFecha(m.fecha)}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
