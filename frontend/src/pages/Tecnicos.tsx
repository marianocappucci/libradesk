import { useEffect, useMemo, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { api, ApiError, type Tecnico } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Pencil, Trash2 } from 'lucide-react'

const tecnicoSchema = z.object({
  nombre: z.string().trim().min(1, 'El nombre es obligatorio'),
})

type TecnicoFormValues = z.infer<typeof tecnicoSchema>

export function Tecnicos() {
  const [tecnicos, setTecnicos] = useState<Tecnico[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [saving, setSaving] = useState(false)

  const form = useForm<TecnicoFormValues>({
    resolver: zodResolver(tecnicoSchema),
    defaultValues: { nombre: '' },
  })

  useEffect(() => {
    loadTecnicos()
  }, [])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function loadTecnicos() {
    setLoading(true)
    setError(null)
    try {
      const items = await api.get<Tecnico[]>('/api/tecnicos')
      setTecnicos(items.sort((a, b) => a.nombre.localeCompare(b.nombre)))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  function startCreate() {
    setEditingId('new')
    form.reset({ nombre: '' })
  }

  function startEdit(tecnico: Tecnico) {
    setEditingId(tecnico.id)
    form.reset({ nombre: tecnico.nombre })
  }

  function cancelEdit() {
    setEditingId(null)
    form.reset({ nombre: '' })
  }

  async function handleSubmit(values: TecnicoFormValues) {
    setSaving(true)
    setError(null)
    try {
      if (editingId === 'new') {
        await api.post('/api/tecnicos', { nombre: values.nombre, activo: true })
      } else if (editingId) {
        const current = tecnicos.find((t) => t.id === editingId)
        await api.put(`/api/tecnicos/${editingId}`, { nombre: values.nombre, activo: current?.activo ?? true })
      }
      cancelEdit()
      await loadTecnicos()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function toggleActivo(tecnico: Tecnico) {
    setError(null)
    try {
      await api.put(`/api/tecnicos/${tecnico.id}`, { nombre: tecnico.nombre, activo: !tecnico.activo })
      await loadTecnicos()
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function handleDelete(tecnico: Tecnico) {
    setError(null)
    try {
      await api.del(`/api/tecnicos/${tecnico.id}`)
      await loadTecnicos()
    } catch (err) {
      setError(describeError(err))
    }
  }

  const columns = useMemo<ColumnDef<Tecnico>[]>(() => [
    { accessorKey: 'nombre', header: sortableHeader('Nombre'), size: 220, minSize: 140, meta: { stretch: true }, cell: ({ row }) => <span className="font-medium">{row.original.nombre}</span> },
    {
      accessorKey: 'activo',
      header: 'Estado',
      size: 110,
      minSize: 90,
      cell: ({ row }) => (
        <Badge
          variant={row.original.activo ? 'default' : 'outline'}
          className="cursor-pointer"
          onClick={() => toggleActivo(row.original)}
        >
          {row.original.activo ? 'Activo' : 'Inactivo'}
        </Badge>
      ),
    },
    {
      id: 'actions',
      header: () => <div className="text-right">Acciones</div>,
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          <Button size="icon" variant="outline" title="Editar técnico" aria-label="Editar técnico" onClick={() => startEdit(row.original)}><Pencil /></Button>
          <Button size="icon" variant="outline" className="text-destructive hover:text-destructive" title="Eliminar técnico" aria-label="Eliminar técnico" onClick={() => handleDelete(row.original)}><Trash2 /></Button>
        </div>
      ),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [])

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Técnicos</h2>
        {editingId === null && <Button onClick={startCreate}>+ Nuevo técnico</Button>}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {editingId !== null && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{editingId === 'new' ? 'Nuevo técnico' : 'Editar técnico'}</CardTitle>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form className="flex flex-wrap items-start gap-3" onSubmit={form.handleSubmit(handleSubmit)}>
                <FormField control={form.control} name="nombre" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Nombre</FormLabel>
                    <FormControl><Input {...field} className="w-52" /></FormControl>
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
              data={tecnicos}
              emptyMessage="Sin técnicos todavía."
              search={{ campos: (t) => [t.nombre], placeholder: 'Buscar por nombre' }}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
