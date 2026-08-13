import { useEffect, useMemo, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { api, ApiError, ROL_LABELS, type Tecnico } from '../api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form'
import { DataTable, sortableHeader } from '@/components/data-table'
import {
  Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
import Wrench from '~icons/fluent-color/wrench-16'
import UserCog from '~icons/fluent-color/person-key-20'
import { FilePlus, Pencil, Trash2 } from '@/components/iconos-accion'

const tecnicoSchema = z.object({
  nombre: z.string().trim().min(1, 'El nombre es obligatorio'),
  // Los tres roles son independientes: la misma persona puede ser técnica y
  // vendedora, que es el caso normal en una empresa chica (pedido 41).
  es_tecnico: z.boolean(),
  es_recepcionista: z.boolean(),
  es_vendedor: z.boolean(),
  es_responsable: z.boolean(),
}).refine(
  (v) => v.es_tecnico || v.es_recepcionista || v.es_vendedor || v.es_responsable,
  // Sin ningún rol la persona quedaría cargada y **fuera de los tres
  // selectores** del ticket: invisible, que se lee como un bug del sistema.
  { message: 'Elegí al menos un rol', path: ['es_tecnico'] },
)

type TecnicoFormValues = z.infer<typeof tecnicoSchema>

const CAMPOS_ROL = [
  { campo: 'es_tecnico', label: 'Técnico', ayuda: 'Ejecuta el trabajo' },
  { campo: 'es_recepcionista', label: 'Recepcionista', ayuda: 'Toma el ticket' },
  { campo: 'es_vendedor', label: 'Vendedor', ayuda: 'Habla con el cliente' },
  { campo: 'es_responsable', label: 'Responsable de equipo', ayuda: 'Manda una cuadrilla' },
] as const

// Alta y edición en un solo Dialog reusado (`editando === null` es alta),
// mismo patrón que Contalibra. Antes el formulario era una card que se abría
// ARRIBA de la tabla y la empujaba hacia abajo, dejando la lista a la vista
// mientras se cargaba: el foco quedaba en dos lugares a la vez.
export function Tecnicos() {
  const [tecnicos, setTecnicos] = useState<Tecnico[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editando, setEditando] = useState<Tecnico | null>(null)
  const [saving, setSaving] = useState(false)
  // El error del formulario va DENTRO del modal: el de la página queda tapado.
  const [formError, setFormError] = useState<string | null>(null)
  const [aBorrar, setABorrar] = useState<Tecnico | null>(null)

  const form = useForm<TecnicoFormValues>({
    resolver: zodResolver(tecnicoSchema),
    defaultValues: {
      nombre: '', es_tecnico: true, es_recepcionista: false, es_vendedor: false,
      es_responsable: false,
    },
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

  function abrirNuevo() {
    setEditando(null)
    setFormError(null)
    form.reset({
      nombre: '', es_tecnico: true, es_recepcionista: false, es_vendedor: false,
      es_responsable: false,
    })
    setDialogOpen(true)
  }

  function abrirEditar(tecnico: Tecnico) {
    setEditando(tecnico)
    setFormError(null)
    form.reset({
      nombre: tecnico.nombre,
      es_tecnico: tecnico.es_tecnico,
      es_recepcionista: tecnico.es_recepcionista,
      es_vendedor: tecnico.es_vendedor,
      es_responsable: tecnico.es_responsable,
    })
    setDialogOpen(true)
  }

  async function handleSubmit(values: TecnicoFormValues) {
    setSaving(true)
    setFormError(null)
    const roles = {
      es_tecnico: values.es_tecnico,
      es_recepcionista: values.es_recepcionista,
      es_vendedor: values.es_vendedor,
      es_responsable: values.es_responsable,
    }
    try {
      if (editando === null) {
        await api.post('/api/tecnicos', { nombre: values.nombre, activo: true, ...roles })
      } else {
        await api.put(`/api/tecnicos/${editando.id}`, {
          nombre: values.nombre, activo: editando.activo, ...roles,
        })
      }
      setDialogOpen(false)
      await loadTecnicos()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function toggleActivo(tecnico: Tecnico) {
    setError(null)
    try {
      // Los roles viajan sin cambio: el PUT reemplaza el objeto entero, así que
      // omitirlos dejaría a la persona con los defaults del modelo (sólo
      // técnica) por el solo hecho de activarla o desactivarla.
      await api.put(`/api/tecnicos/${tecnico.id}`, {
        nombre: tecnico.nombre,
        activo: !tecnico.activo,
        es_tecnico: tecnico.es_tecnico,
        es_recepcionista: tecnico.es_recepcionista,
        es_vendedor: tecnico.es_vendedor,
        es_responsable: tecnico.es_responsable,
      })
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
      id: 'roles',
      header: 'Roles',
      size: 220, minSize: 150,
      cell: ({ row }) => (
        <div className="flex flex-wrap gap-1">
          {row.original.roles.map((r) => (
            <Badge key={r} variant="outline">{ROL_LABELS[r] ?? r}</Badge>
          ))}
        </div>
      ),
    },
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
          <Button size="icon" variant="outline" title="Editar técnico" aria-label="Editar técnico" onClick={() => abrirEditar(row.original)}><Pencil /></Button>
          <Button size="icon" variant="outline" className="text-destructive hover:text-destructive" title="Eliminar técnico" aria-label="Eliminar técnico" onClick={() => setABorrar(row.original)}><Trash2 /></Button>
        </div>
      ),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [])

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <UserCog className="size-5" />Técnicos
        </h2>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button onClick={abrirNuevo}><FilePlus />Nuevo técnico</Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-lg">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Wrench className="size-4" />
                {editando === null ? 'Nuevo técnico' : `Editar técnico — ${editando.nombre}`}
              </DialogTitle>
            </DialogHeader>
            <Form {...form}>
              <form className="flex flex-wrap items-start gap-3" onSubmit={form.handleSubmit(handleSubmit)}>
                {formError && <p className="w-full text-sm text-destructive">{formError}</p>}
                <FormField control={form.control} name="nombre" render={({ field }) => (
                  <FormItem className="w-full">
                    <FormLabel>Nombre</FormLabel>
                    <FormControl><Input {...field} autoFocus /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormItem className="w-full">
                  <FormLabel>Roles</FormLabel>
                  <div className="grid gap-2">
                    {CAMPOS_ROL.map(({ campo, label, ayuda }) => (
                      <FormField key={campo} control={form.control} name={campo} render={({ field }) => (
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={field.value}
                            onChange={(e) => field.onChange(e.target.checked)}
                            aria-label={label}
                          />
                          <span>{label}</span>
                          <span className="text-xs text-muted-foreground">— {ayuda}</span>
                        </label>
                      )} />
                    ))}
                  </div>
                  {/* El mensaje del `refine` cuelga de `es_tecnico`. */}
                  <FormMessage>{form.formState.errors.es_tecnico?.message}</FormMessage>
                </FormItem>
                <DialogFooter className="w-full">
                  <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
                  <Button type="submit" disabled={saving}>
                    {saving ? 'Guardando…' : editando === null ? 'Crear técnico' : 'Guardar'}
                  </Button>
                </DialogFooter>
              </form>
            </Form>
          </DialogContent>
        </Dialog>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

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

      <ConfirmDialog
        open={aBorrar !== null}
        onOpenChange={(open) => !open && setABorrar(null)}
        title={`¿Eliminar a ${aBorrar?.nombre}?`}
        description="Las incidencias que lo tengan asignado quedan sin técnico. Esta acción no se puede deshacer."
        onConfirm={() => { const t = aBorrar; setABorrar(null); if (t) handleDelete(t) }}
      />
    </div>
  )
}
