import { useEffect, useMemo, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { Link } from 'react-router-dom'
import {
  api, ApiError, ESTADO_ACTIVO_LABELS, ESTADOS_ACTIVO_MANUALES,
  type Activo, type HitoActivo, type ResumenActivos,
} from '../api'
import { fecha } from '@/lib/format'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form'
import { DataTable, sortableHeader } from '@/components/data-table'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
import History from '~icons/fluent-color/history-16'
import IconoActivos from '~icons/fluent-color/briefcase-20'
import { Boxes, Pencil, Plus, Trash2 } from '@/components/iconos-accion'

const TODOS = '__todos__'

const HITO_LABELS: Record<HitoActivo['clase'], string> = {
  contrato: 'Contrato',
  movimiento: 'Movimiento',
  service: 'Service',
}

const activoSchema = z.object({
  tipo: z.string().trim().min(1, 'El tipo es obligatorio'),
  marca: z.string().trim().optional(),
  modelo: z.string().trim().optional(),
  serial: z.string().trim().optional(),
  codigo_interno: z.string().trim().optional(),
  mac: z.string().trim().optional(),
  imei: z.string().trim().optional(),
  ip: z.string().trim().optional(),
  accesorios: z.string().trim().optional(),
  estado: z.string(),
  costo_compra: z.string().trim().optional(),
  valor_reposicion: z.string().trim().optional(),
  garantia_vence: z.string().trim().optional(),
  observaciones: z.string().trim().optional(),
})

type ActivoFormValues = z.infer<typeof activoSchema>

const VACIO: ActivoFormValues = {
  tipo: '', marca: '', modelo: '', serial: '', codigo_interno: '',
  mac: '', imei: '', ip: '', accesorios: '', estado: 'disponible',
  costo_compra: '', valor_reposicion: '', garantia_vence: '', observaciones: '',
}

function pesos(v: number | null): string {
  if (v === null) return '—'
  return v.toLocaleString('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 })
}

function numero(v: string | undefined): number | undefined {
  const limpio = (v ?? '').trim()
  return limpio === '' ? undefined : Number(limpio)
}

/**
 * El stock propio: los equipos que la empresa entrega a sus clientes.
 *
 * **No se coloca ni se retira desde acá**, a propósito. Eso ocurre contra un
 * contrato, que es donde vive la fecha y el motivo; un activo colocado desde
 * esta pantalla sería un activo que dice estar en un cliente sin ninguna línea
 * que diga en cuál. Por eso `colocado` tampoco está en el selector de estado.
 */
export function Activos() {
  const [activos, setActivos] = useState<Activo[]>([])
  const [resumen, setResumen] = useState<ResumenActivos | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [estado, setEstado] = useState(TODOS)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editando, setEditando] = useState<Activo | null>(null)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [aBorrar, setABorrar] = useState<Activo | null>(null)
  const [verHistorial, setVerHistorial] = useState<Activo | null>(null)
  const [hitos, setHitos] = useState<HitoActivo[] | null>(null)

  const form = useForm<ActivoFormValues>({
    resolver: zodResolver(activoSchema),
    defaultValues: VACIO,
  })

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estado])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const qs = estado === TODOS ? '' : `?estado=${estado}`
      const [items, r] = await Promise.all([
        api.get<Activo[]>(`/api/activos${qs}`),
        api.get<ResumenActivos>('/api/activos/resumen'),
      ])
      setActivos(items)
      setResumen(r)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  function abrirNuevo() {
    setEditando(null)
    setFormError(null)
    form.reset(VACIO)
    setDialogOpen(true)
  }

  function abrirEditar(a: Activo) {
    setEditando(a)
    setFormError(null)
    form.reset({
      tipo: a.tipo, marca: a.marca ?? '', modelo: a.modelo ?? '',
      serial: a.serial ?? '', codigo_interno: a.codigo_interno ?? '',
      mac: a.mac ?? '', imei: a.imei ?? '', ip: a.ip ?? '',
      accesorios: a.accesorios ?? '',
      // Un activo colocado no puede cambiar de estado (el backend lo rechaza),
      // así que el formulario arranca en lo que se puede elegir.
      estado: a.estado === 'colocado' ? 'colocado' : a.estado,
      costo_compra: a.costo_compra === null ? '' : String(a.costo_compra),
      valor_reposicion: a.valor_reposicion === null ? '' : String(a.valor_reposicion),
      garantia_vence: a.garantia_vence ?? '',
      observaciones: a.observaciones ?? '',
    })
    setDialogOpen(true)
  }

  async function handleSubmit(values: ActivoFormValues) {
    setSaving(true)
    setFormError(null)
    const body: Record<string, unknown> = {
      tipo: values.tipo,
      marca: values.marca || null,
      modelo: values.modelo || null,
      serial: values.serial || null,
      codigo_interno: values.codigo_interno || null,
      mac: values.mac || null,
      imei: values.imei || null,
      ip: values.ip || null,
      accesorios: values.accesorios || null,
      costo_compra: numero(values.costo_compra) ?? null,
      valor_reposicion: numero(values.valor_reposicion) ?? null,
      garantia_vence: values.garantia_vence || null,
      observaciones: values.observaciones || null,
    }
    // El estado sólo viaja si se puede tocar: mandarlo en un activo colocado
    // daría un 409 aunque el usuario no lo haya cambiado.
    if (editando === null || editando.estado !== 'colocado') body.estado = values.estado

    try {
      if (editando === null) {
        await api.post('/api/activos', body)
      } else {
        await api.put(`/api/activos/${editando.id}`, body)
      }
      setDialogOpen(false)
      await load()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function abrirHistorial(a: Activo) {
    setVerHistorial(a)
    setHitos(null)
    try {
      setHitos(await api.get<HitoActivo[]>(`/api/activos/${a.id}/linea-de-tiempo`))
    } catch (err) {
      setError(describeError(err))
      setVerHistorial(null)
    }
  }

  async function handleDelete(a: Activo) {
    setError(null)
    try {
      await api.del(`/api/activos/${a.id}`)
      await load()
    } catch (err) {
      setError(describeError(err))
    }
  }

  const columns = useMemo<ColumnDef<Activo>[]>(() => [
    {
      accessorKey: 'descripcion',
      header: sortableHeader('Equipo'),
      size: 240, minSize: 160, meta: { stretch: true },
      cell: ({ row }) => (
        <div>
          <div className="font-medium">{row.original.descripcion}</div>
          {(row.original.serial || row.original.codigo_interno) && (
            <div className="text-xs text-muted-foreground">
              {[row.original.serial, row.original.codigo_interno].filter(Boolean).join(' · ')}
            </div>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'estado',
      header: sortableHeader('Estado'),
      size: 150, minSize: 110,
      cell: ({ row }) => (
        <Badge variant={row.original.estado === 'colocado' ? 'default' : 'outline'}>
          {ESTADO_ACTIVO_LABELS[row.original.estado] ?? row.original.estado}
        </Badge>
      ),
    },
    {
      id: 'donde',
      header: 'Dónde está',
      size: 220, minSize: 140,
      cell: ({ row }) => {
        const a = row.original
        if (a.contrato_id === null) {
          return <span className="text-muted-foreground">En depósito</span>
        }
        return (
          <div>
            <div>{a.cliente_nombre}</div>
            <Link className="text-xs underline" to={`/contratos/${a.contrato_id}`}>
              {a.contrato_numero}
            </Link>
          </div>
        )
      },
    },
    {
      accessorKey: 'costo_compra',
      header: sortableHeader('Costo'),
      size: 120, minSize: 90,
      cell: ({ row }) => pesos(row.original.costo_compra),
    },
    {
      id: 'actions',
      header: () => <div className="text-right">Acciones</div>,
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          <Button size="icon" variant="outline" title="Ver historial" aria-label="Ver historial" onClick={() => abrirHistorial(row.original)}><History /></Button>
          <Button size="icon" variant="outline" title="Editar activo" aria-label="Editar activo" onClick={() => abrirEditar(row.original)}><Pencil /></Button>
          <Button size="icon" variant="outline" className="text-destructive hover:text-destructive" title="Eliminar activo" aria-label="Eliminar activo" onClick={() => setABorrar(row.original)}><Trash2 /></Button>
        </div>
      ),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [])

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <IconoActivos className="size-5" />Activos en alquiler
        </h2>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button onClick={abrirNuevo}><Plus />Nuevo activo</Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-2xl">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Boxes className="size-4" />
                {editando === null ? 'Nuevo activo' : `Editar — ${editando.descripcion}`}
              </DialogTitle>
              <DialogDescription>
                Equipos propios que se entregan a clientes bajo contrato. Para
                colocarlos en un cliente, entrá al contrato.
              </DialogDescription>
            </DialogHeader>
            <Form {...form}>
              <form className="grid gap-3 sm:grid-cols-2" onSubmit={form.handleSubmit(handleSubmit)}>
                {formError && <p className="sm:col-span-2 text-sm text-destructive">{formError}</p>}
                <FormField control={form.control} name="tipo" render={({ field }) => (
                  <FormItem><FormLabel>Tipo</FormLabel><FormControl><Input {...field} autoFocus placeholder="Central telefónica" /></FormControl><FormMessage /></FormItem>
                )} />
                <FormField control={form.control} name="estado" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Estado</FormLabel>
                    {editando?.estado === 'colocado' ? (
                      <p className="text-sm text-muted-foreground">
                        Colocado en {editando.contrato_numero}. Retiralo del
                        contrato para cambiarle el estado.
                      </p>
                    ) : (
                      <Select value={field.value} onValueChange={field.onChange}>
                        <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                        <SelectContent>
                          {ESTADOS_ACTIVO_MANUALES.map((e) => (
                            <SelectItem key={e} value={e}>{ESTADO_ACTIVO_LABELS[e]}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="marca" render={({ field }) => (
                  <FormItem><FormLabel>Marca</FormLabel><FormControl><Input {...field} /></FormControl></FormItem>
                )} />
                <FormField control={form.control} name="modelo" render={({ field }) => (
                  <FormItem><FormLabel>Modelo</FormLabel><FormControl><Input {...field} /></FormControl></FormItem>
                )} />
                <FormField control={form.control} name="serial" render={({ field }) => (
                  <FormItem><FormLabel>Número de serie</FormLabel><FormControl><Input {...field} /></FormControl></FormItem>
                )} />
                <FormField control={form.control} name="codigo_interno" render={({ field }) => (
                  <FormItem><FormLabel>Código patrimonial</FormLabel><FormControl><Input {...field} /></FormControl></FormItem>
                )} />
                <FormField control={form.control} name="mac" render={({ field }) => (
                  <FormItem><FormLabel>MAC</FormLabel><FormControl><Input {...field} /></FormControl></FormItem>
                )} />
                <FormField control={form.control} name="ip" render={({ field }) => (
                  <FormItem><FormLabel>Dirección IP</FormLabel><FormControl><Input {...field} /></FormControl></FormItem>
                )} />
                <FormField control={form.control} name="imei" render={({ field }) => (
                  <FormItem><FormLabel>IMEI</FormLabel><FormControl><Input {...field} /></FormControl></FormItem>
                )} />
                <FormField control={form.control} name="garantia_vence" render={({ field }) => (
                  <FormItem><FormLabel>Vence la garantía</FormLabel><FormControl><Input type="date" {...field} /></FormControl></FormItem>
                )} />
                <FormField control={form.control} name="costo_compra" render={({ field }) => (
                  <FormItem><FormLabel>Costo de compra</FormLabel><FormControl><Input type="number" step="0.01" {...field} /></FormControl></FormItem>
                )} />
                <FormField control={form.control} name="valor_reposicion" render={({ field }) => (
                  <FormItem><FormLabel>Valor de reposición</FormLabel><FormControl><Input type="number" step="0.01" {...field} /></FormControl></FormItem>
                )} />
                <FormField control={form.control} name="accesorios" render={({ field }) => (
                  <FormItem className="sm:col-span-2"><FormLabel>Accesorios entregados</FormLabel><FormControl><Input {...field} placeholder="Fuente, cables, soporte de pared" /></FormControl></FormItem>
                )} />
                <FormField control={form.control} name="observaciones" render={({ field }) => (
                  <FormItem className="sm:col-span-2"><FormLabel>Observaciones</FormLabel><FormControl><Input {...field} /></FormControl></FormItem>
                )} />
                <DialogFooter className="sm:col-span-2">
                  <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
                  <Button type="submit" disabled={saving}>
                    {saving ? 'Guardando…' : editando === null ? 'Crear activo' : 'Guardar'}
                  </Button>
                </DialogFooter>
              </form>
            </Form>
          </DialogContent>
        </Dialog>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {resumen && (
        <Card>
          <CardContent className="flex flex-wrap gap-4 text-sm">
            <span><strong>{resumen.total}</strong> activos</span>
            {Object.entries(resumen.por_estado)
              .filter(([, n]) => n > 0)
              .map(([e, n]) => (
                <span key={e} className="text-muted-foreground">
                  {ESTADO_ACTIVO_LABELS[e] ?? e}: <strong>{n}</strong>
                </span>
              ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="grid gap-1.5 sm:max-w-xs">
          <Label>Estado</Label>
          <Select value={estado} onValueChange={setEstado}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={TODOS}>Todos</SelectItem>
              {Object.entries(ESTADO_ACTIVO_LABELS).map(([e, label]) => (
                <SelectItem key={e} value={e}>{label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable
              columns={columns}
              data={activos}
              emptyMessage="Sin activos todavía."
              search={{
                campos: (a) => [a.descripcion, a.serial ?? '', a.codigo_interno ?? '', a.cliente_nombre ?? ''],
                placeholder: 'Buscar por equipo, serie, código o cliente',
              }}
            />
          )}
        </CardContent>
      </Card>

      {/* La línea de tiempo: contratos, movimientos y pasos por service en una
          sola secuencia. Es lo que contesta "por dónde anduvo este equipo", que
          con las tres listas separadas hay que armar a ojo. */}
      <Dialog open={verHistorial !== null} onOpenChange={(open) => !open && setVerHistorial(null)}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <History className="size-4" />
              Historial — {verHistorial?.descripcion}
            </DialogTitle>
            <DialogDescription>
              {verHistorial?.serial ?? 'Sin número de serie'}
            </DialogDescription>
          </DialogHeader>
          {hitos === null ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : hitos.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Todavía no pasó nada con este activo.
            </p>
          ) : (
            <ol className="grid gap-3">
              {hitos.map((h, i) => (
                <li key={`${h.clase}-${h.linea_id ?? h.movimiento_id ?? h.reparacion_id ?? i}`} className="flex gap-3">
                  <Badge variant={h.clase === 'service' ? 'default' : 'outline'} className="h-fit shrink-0">
                    {HITO_LABELS[h.clase]}
                  </Badge>
                  <div className="leading-tight">
                    <div className="text-sm">{h.titulo}</div>
                    <div className="text-xs text-muted-foreground">
                      {fecha(h.fecha)}{h.detalle ? ` · ${h.detalle}` : ''}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
          <DialogFooter>
            <DialogClose asChild><Button type="button" variant="outline">Cerrar</Button></DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={aBorrar !== null}
        onOpenChange={(open) => !open && setABorrar(null)}
        title={`¿Eliminar ${aBorrar?.descripcion}?`}
        description="Sólo se puede borrar un activo que nunca estuvo en un contrato. Si tiene historial, dalo de baja."
        onConfirm={() => { const a = aBorrar; setABorrar(null); if (a) handleDelete(a) }}
      />
    </div>
  )
}
