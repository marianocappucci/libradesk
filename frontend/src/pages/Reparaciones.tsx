import { useEffect, useMemo, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { Link } from 'react-router-dom'
import {
  api, ApiError, opcionesCliente, opcionesProveedor,
  type Cliente, type Proveedor, type Reparacion,
} from '../api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form'
import { DataTable, sortableHeader } from '@/components/data-table'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { PackageCheck, ShieldCheck, Wrench } from 'lucide-react'

const TODOS = '__todos__'

const cierreSchema = z.object({
  fecha_retorno: z.string().min(1, 'La fecha de retorno es obligatoria'),
  diagnostico: z.string().trim().optional(),
  costo: z.string().trim().optional(),
})

type CierreFormValues = z.infer<typeof cierreSchema>

function pesos(v: number | null): string {
  if (v === null) return '—'
  return v.toLocaleString('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 })
}

function fecha(iso: string | null): string {
  return iso ? new Date(`${iso}T00:00:00`).toLocaleDateString('es-AR') : '—'
}

/**
 * "¿Qué tengo hoy en service?" — la pregunta que motiva la pantalla, y por eso
 * el filtro arranca en **Abiertas**. Una lista que por default mezcla las 40
 * reparaciones históricas con las 3 que están afuera no contesta nada.
 *
 * La reparación se ABRE desde el diálogo "Reemplazar equipo" del ticket, en el
 * mismo gesto con el que se retira el equipo — no hay alta acá, a propósito:
 * un alta suelta permitiría registrar un envío a service sin mover el equipo,
 * y quedarían diciendo cosas distintas. Acá se las mira y se las **cierra**,
 * que es lo que pasa días después y desde otro lugar.
 */
export function Reparaciones() {
  const [reparaciones, setReparaciones] = useState<Reparacion[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [proveedores, setProveedores] = useState<Proveedor[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [estado, setEstado] = useState<'abiertas' | 'cerradas' | 'todas'>('abiertas')
  const [clienteId, setClienteId] = useState(TODOS)
  const [proveedorId, setProveedorId] = useState(TODOS)

  const [aCerrar, setACerrar] = useState<Reparacion | null>(null)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const form = useForm<CierreFormValues>({
    resolver: zodResolver(cierreSchema),
    defaultValues: { fecha_retorno: '', diagnostico: '', costo: '' },
  })

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  useEffect(() => {
    Promise.all([
      api.get<Cliente[]>('/api/clientes'),
      api.get<Proveedor[]>('/api/proveedores'),
    ])
      .then(([cs, ps]) => { setClientes(cs); setProveedores(ps) })
      .catch((err) => setError(describeError(err)))
  }, [])

  useEffect(() => {
    loadReparaciones()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estado, clienteId, proveedorId])

  async function loadReparaciones() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (estado !== 'todas') params.set('abiertas', String(estado === 'abiertas'))
      if (clienteId !== TODOS) params.set('cliente_id', clienteId)
      if (proveedorId !== TODOS) params.set('proveedor_id', proveedorId)
      const qs = params.toString()
      setReparaciones(await api.get<Reparacion[]>(`/api/reparaciones${qs ? `?${qs}` : ''}`))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  function abrirCierre(r: Reparacion) {
    setACerrar(r)
    setFormError(null)
    form.reset({
      // Por default hoy: lo normal es cerrarla el día que vuelve el equipo.
      fecha_retorno: new Date().toISOString().slice(0, 10),
      diagnostico: '',
      costo: '',
    })
  }

  async function handleCierre(values: CierreFormValues) {
    if (!aCerrar) return
    setSaving(true)
    setFormError(null)
    try {
      await api.post(`/api/reparaciones/${aCerrar.id}/cerrar`, {
        fecha_retorno: values.fecha_retorno,
        diagnostico: values.diagnostico || null,
        costo: values.costo ? Number(values.costo) : null,
      })
      setACerrar(null)
      await loadReparaciones()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  const nombreCliente = useMemo(() => {
    const porId = new Map(clientes.map((c) => [c.id, c.nombre]))
    return (id: number | null) => (id === null ? '—' : porId.get(id) ?? `#${id}`)
  }, [clientes])

  const columns = useMemo<ColumnDef<Reparacion>[]>(() => [
    {
      accessorKey: 'equipo_descripcion',
      header: sortableHeader('Equipo'),
      size: 220, minSize: 160, meta: { stretch: true },
      cell: ({ row }) => (
        <div className="leading-tight">
          <span className="font-medium">{row.original.equipo_descripcion}</span>
          {row.original.equipo_serial && (
            <span className="block text-xs text-muted-foreground">{row.original.equipo_serial}</span>
          )}
        </div>
      ),
    },
    {
      id: 'cliente',
      header: 'Cliente',
      size: 150, minSize: 110,
      cell: ({ row }) => nombreCliente(row.original.cliente_id),
    },
    { accessorKey: 'proveedor_nombre', header: sortableHeader('Proveedor'), size: 160, minSize: 120 },
    {
      accessorKey: 'fecha_envio',
      header: sortableHeader('Envío'),
      size: 110, minSize: 90,
      cell: ({ row }) => fecha(row.original.fecha_envio),
    },
    {
      accessorKey: 'dias_afuera',
      header: sortableHeader('Días'),
      size: 90, minSize: 70,
      cell: ({ row }) => {
        const d = row.original.dias_afuera
        if (d === null) return '—'
        // Sólo se resalta lo que sigue afuera: una reparación cerrada que tardó
        // 20 días es un dato histórico, no algo para ir a mirar hoy.
        const demorada = row.original.abierta && d > 15
        return (
          <span className={demorada ? 'font-medium text-destructive' : undefined}>
            {d} {d === 1 ? 'día' : 'días'}
          </span>
        )
      },
    },
    {
      id: 'referencias',
      header: 'Remito / RMA',
      size: 150, minSize: 110,
      cell: ({ row }) => (
        <div className="text-xs leading-tight">
          {row.original.remito_salida && <span className="block">Remito {row.original.remito_salida}</span>}
          {row.original.rma && <span className="block">RMA {row.original.rma}</span>}
          {!row.original.remito_salida && !row.original.rma && '—'}
        </div>
      ),
    },
    {
      id: 'costo',
      header: 'Costo',
      size: 130, minSize: 100,
      // La garantía y el costo NO son excluyentes, aunque lo parezcan: una
      // reparación cubierta puede igual haber costado el flete o un repuesto
      // que la garantía no cubría. La primera versión mostraba la insignia EN
      // LUGAR del importe, y con eso **escondía plata realmente gastada** — se
      // vio en el navegador, con una reparación en garantía de $45.000 que la
      // tabla mostraba como si no hubiera costado nada. La ficha del equipo,
      // que suma los costos, sí la contaba: las dos pantallas decían cosas
      // distintas sobre la misma fila.
      cell: ({ row }) => (
        <div className="flex flex-wrap items-center gap-1">
          {row.original.en_garantia && (
            <Badge variant="outline" className="gap-1">
              <ShieldCheck className="size-3" />Garantía
            </Badge>
          )}
          {(row.original.costo !== null || !row.original.en_garantia) && (
            <span>{pesos(row.original.costo)}</span>
          )}
        </div>
      ),
    },
    {
      id: 'estado',
      header: 'Estado',
      size: 120, minSize: 100,
      cell: ({ row }) => (
        row.original.abierta
          ? <Badge>En service</Badge>
          : <Badge variant="outline">Vuelta {fecha(row.original.fecha_retorno)}</Badge>
      ),
    },
    {
      id: 'actions',
      header: () => <div className="text-right">Acciones</div>,
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          {row.original.incidencia_id !== null && (
            <Button asChild size="sm" variant="ghost" title="Ver el ticket que la originó">
              <Link to={`/incidencias/${row.original.incidencia_id}`}>#{row.original.incidencia_id}</Link>
            </Button>
          )}
          {row.original.abierta && (
            <Button
              size="sm" variant="outline"
              title="Registrar la vuelta del equipo"
              onClick={() => abrirCierre(row.original)}
            >
              <PackageCheck />Registrar vuelta
            </Button>
          )}
        </div>
      ),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [nombreCliente])

  const abiertas = reparaciones.filter((r) => r.abierta).length

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Wrench className="size-5" />
          Reparaciones
          {estado === 'abiertas' && abiertas > 0 && (
            <Badge variant="secondary">{abiertas} en service</Badge>
          )}
        </h2>
      </div>

      <Card>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <div className="grid gap-1.5">
            <Label>Estado</Label>
            <Select value={estado} onValueChange={(v) => setEstado(v as typeof estado)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="abiertas">En service</SelectItem>
                <SelectItem value="cerradas">Ya volvieron</SelectItem>
                <SelectItem value="todas">Todas</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label>Cliente</Label>
            <SelectBuscable
              value={clienteId}
              onChange={setClienteId}
              opciones={[{ value: TODOS, label: 'Todos los clientes' }, ...opcionesCliente(clientes)]}
              placeholder="Todos los clientes"
            />
          </div>
          <div className="grid gap-1.5">
            <Label>Proveedor</Label>
            <SelectBuscable
              value={proveedorId}
              onChange={setProveedorId}
              opciones={[{ value: TODOS, label: 'Todos los proveedores' }, ...opcionesProveedor(proveedores)]}
              placeholder="Todos los proveedores"
            />
          </div>
        </CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable
              columns={columns}
              data={reparaciones}
              emptyMessage={
                estado === 'abiertas'
                  ? 'No hay ningún equipo en service.'
                  : 'Sin reparaciones registradas.'
              }
              search={{
                campos: (r) => [
                  r.equipo_descripcion, r.equipo_serial, r.proveedor_nombre,
                  r.rma, r.remito_salida,
                ],
                placeholder: 'Buscar por equipo, serial, proveedor o RMA',
              }}
            />
          )}
        </CardContent>
      </Card>

      {/* El cierre no reinstala el equipo: moverlo de vuelta a su lugar es un
          movimiento de inventario y lo hace "Reemplazar equipo" desde el
          ticket, que ya sabe generar el historial correcto. Mezclar las dos
          cosas produciría movimientos que la edición manual no produce. */}
      <Dialog open={aCerrar !== null} onOpenChange={(open) => !open && setACerrar(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Registrar la vuelta del equipo</DialogTitle>
            <DialogDescription>
              {aCerrar?.equipo_descripcion} — {aCerrar?.proveedor_nombre}.
              Cierra la reparación; para reinstalarlo en su lugar usá
              “Reemplazar equipo” desde el ticket.
            </DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form className="grid gap-3" onSubmit={form.handleSubmit(handleCierre)}>
              {formError && <p className="text-sm text-destructive">{formError}</p>}
              <FormField control={form.control} name="fecha_retorno" render={({ field }) => (
                <FormItem>
                  <FormLabel>Fecha de retorno</FormLabel>
                  <FormControl><Input type="date" {...field} /></FormControl>
                  <FormMessage />
                </FormItem>
              )} />
              <FormField control={form.control} name="diagnostico" render={({ field }) => (
                <FormItem>
                  <FormLabel>Diagnóstico del proveedor</FormLabel>
                  <FormControl>
                    <Input placeholder="Se cambió el fusor…" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )} />
              <FormField control={form.control} name="costo" render={({ field }) => (
                <FormItem>
                  <FormLabel>Costo</FormLabel>
                  <FormControl>
                    <Input
                      type="number" min="0" step="0.01"
                      placeholder={aCerrar?.en_garantia ? 'Entró por garantía' : '0'}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )} />
              <DialogFooter>
                <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
                <Button type="submit" disabled={saving}>
                  {saving ? 'Guardando…' : 'Registrar vuelta'}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
