/** Insumos del parque: qué consume cada equipo, quién se lo entrega y cuándo
 *  se le puso.
 *
 *  El caso que la motiva: el cliente le alquila fotocopiadoras a un tercero que
 *  le provee los tóner, y hasta hoy eso vivía en un cuaderno.
 *
 *  **Arranca en "Pedidos"**, igual que Reparaciones arranca en "En service" y
 *  por el mismo motivo: la pregunta que trae a alguien a esta pantalla es *"¿qué
 *  me deben?"*, y una lista que mezcla los 300 cambios históricos con los 3 que
 *  faltan no la contesta.
 *
 *  Las tres acciones son los tres momentos reales —se pide, llega, se pone—, y
 *  pasan con días de diferencia. Por eso son botones y no un formulario con las
 *  tres fechas: nadie las conoce todas al mismo tiempo. El alta sí las acepta
 *  todas, que es como se vuelca un cuaderno viejo sin inventar un pedido que
 *  nunca existió.
 */
import { useEffect, useMemo, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { Link } from 'react-router-dom'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import {
  api, ApiError, INSUMO_LABELS, INSUMO_TONO, opcionesCliente, opcionesProveedor,
  type Cliente, type Equipo, type EstadoInsumo, type Insumo, type Proveedor,
} from '../api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { BadgeEstado } from 'libra-ui/badge-estado'
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
import { Droplets } from 'lucide-react'
import { fecha } from '@/lib/format'
import { hoyISO } from 'libra-ui/fechas'
// `FilePlus` y no `Plus`: es el alta de un registro, que es lo que ese dibujo
// significa en el vocabulario (`components/iconos-accion.tsx`).
import { FilePlus, PackageCheck } from '@/components/iconos-accion'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

const TODOS = '__todos__'

type Consumible = { id: number; nombre: string; activo: boolean }

const pedidoSchema = z.object({
  equipo_id: z.string().min(1, 'Elegí el equipo'),
  insumo_item_id: z.string().min(1, 'Elegí el insumo'),
  cantidad: z.string().min(1),
  fecha_pedido: z.string().min(1, 'La fecha del pedido es obligatoria'),
  observaciones: z.string().trim().optional(),
})

const entregaSchema = z.object({
  fecha_entrega: z.string().min(1, 'La fecha de entrega es obligatoria'),
  remito_proveedor: z.string().trim().optional(),
})

const colocacionSchema = z.object({
  fecha_colocacion: z.string().min(1, 'La fecha de colocación es obligatoria'),
  contador_copias: z.string().trim().optional(),
})

type PedidoValues = z.infer<typeof pedidoSchema>
type EntregaValues = z.infer<typeof entregaSchema>
type ColocacionValues = z.infer<typeof colocacionSchema>

function copias(v: number | null): string {
  return v === null ? '—' : v.toLocaleString('es-AR')
}

export function Insumos() {
  const [insumos, setInsumos] = useState<Insumo[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [proveedores, setProveedores] = useState<Proveedor[]>([])
  const [equipos, setEquipos] = useState<Equipo[]>([])
  const [consumibles, setConsumibles] = useState<Consumible[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [estado, setEstado] = useState<EstadoInsumo | 'todos'>('pendiente')
  const [clienteId, setClienteId] = useState(TODOS)
  const [proveedorId, setProveedorId] = useState(TODOS)

  const [pidiendo, setPidiendo] = useState(false)
  const [aEntregar, setAEntregar] = useState<Insumo | null>(null)
  const [aColocar, setAColocar] = useState<Insumo | null>(null)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const pedido = useForm<PedidoValues>({
    resolver: zodResolver(pedidoSchema),
    defaultValues: {
      equipo_id: '', insumo_item_id: '', cantidad: '1',
      fecha_pedido: hoyISO(), observaciones: '',
    },
  })
  const entrega = useForm<EntregaValues>({
    resolver: zodResolver(entregaSchema),
    defaultValues: { fecha_entrega: '', remito_proveedor: '' },
  })
  const colocacion = useForm<ColocacionValues>({
    resolver: zodResolver(colocacionSchema),
    defaultValues: { fecha_colocacion: '', contador_copias: '' },
  })

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  useEffect(() => {
    Promise.all([
      api.get<Cliente[]>('/api/clientes'),
      api.get<Proveedor[]>('/api/proveedores'),
      api.get<Equipo[]>('/api/equipos'),
    ])
      .then(([cs, ps, es]) => { setClientes(cs); setProveedores(ps); setEquipos(es) })
      .catch((err) => setError(describeError(err)))
    // El catálogo va aparte y su error no tumba la pantalla: vive detrás del
    // módulo `stock`, así que una instancia mal configurada tiene que poder
    // seguir LEYENDO el historial —que trae el nombre copiado— aunque no pueda
    // elegir un insumo nuevo.
    api.get<Consumible[]>('/api/consumibles')
      .then(setConsumibles)
      .catch(() => setConsumibles([]))
  }, [])

  useEffect(() => {
    loadInsumos()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estado, clienteId, proveedorId])

  async function loadInsumos() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (estado !== 'todos') params.set('estado', estado)
      if (clienteId !== TODOS) params.set('cliente_id', clienteId)
      if (proveedorId !== TODOS) params.set('proveedor_id', proveedorId)
      const qs = params.toString()
      setInsumos(await api.get<Insumo[]>(`/api/insumos${qs ? `?${qs}` : ''}`))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  const nombreCliente = useMemo(() => {
    const porId = new Map(clientes.map((c) => [c.id, c.nombre]))
    return (id: number | null) => (id === null ? '—' : porId.get(id) ?? `#${id}`)
  }, [clientes])

  /** El equipo, con **su número interno** en el subtítulo.
   *
   *  Es el dato con el que se pide el insumo, así que verlo mientras se elige la
   *  máquina es la mitad del trabajo: sin esto hay que abrir la ficha en otra
   *  pestaña para confirmar que la 4471 es ésta. */
  const opcionesDeEquipo = useMemo(() => equipos.map((e) => ({
    value: String(e.id),
    label: [e.tipo, e.marca, e.modelo].filter(Boolean).join(' '),
    hint: [
      nombreCliente(e.cliente_id),
      ...e.referencias.map((r) => `${r.etiqueta} ${r.valor}`),
      e.sector,
    ].filter(Boolean).join(' · ') || undefined,
  })), [equipos, nombreCliente])

  const opcionesDeInsumo = useMemo(() => consumibles
    .filter((c) => c.activo)
    .map((c) => ({ value: String(c.id), label: c.nombre })), [consumibles])

  function abrirPedido() {
    setFormError(null)
    pedido.reset({
      equipo_id: '', insumo_item_id: '', cantidad: '1',
      fecha_pedido: hoyISO(), observaciones: '',
    })
    setPidiendo(true)
  }

  async function handlePedido(values: PedidoValues) {
    setSaving(true)
    setFormError(null)
    try {
      await api.post('/api/insumos', {
        equipo_id: Number(values.equipo_id),
        insumo_item_id: Number(values.insumo_item_id),
        cantidad: Number(values.cantidad),
        fecha_pedido: values.fecha_pedido,
        observaciones: values.observaciones || null,
      })
      setPidiendo(false)
      await loadInsumos()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  function abrirEntrega(i: Insumo) {
    setFormError(null)
    entrega.reset({ fecha_entrega: hoyISO(), remito_proveedor: '' })
    setAEntregar(i)
  }

  async function handleEntrega(values: EntregaValues) {
    if (!aEntregar) return
    setSaving(true)
    setFormError(null)
    try {
      await api.post(`/api/insumos/${aEntregar.id}/entrega`, {
        fecha_entrega: values.fecha_entrega,
        remito_proveedor: values.remito_proveedor || null,
      })
      setAEntregar(null)
      await loadInsumos()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  function abrirColocacion(i: Insumo) {
    setFormError(null)
    colocacion.reset({ fecha_colocacion: hoyISO(), contador_copias: '' })
    setAColocar(i)
  }

  async function handleColocacion(values: ColocacionValues) {
    if (!aColocar) return
    setSaving(true)
    setFormError(null)
    try {
      await api.post(`/api/insumos/${aColocar.id}/colocacion`, {
        fecha_colocacion: values.fecha_colocacion,
        contador_copias: values.contador_copias
          ? Number(values.contador_copias) : null,
      })
      setAColocar(null)
      await loadInsumos()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  const columns = useMemo<ColumnDef<Insumo>[]>(() => [
    {
      id: 'equipo',
      header: 'Equipo',
      size: 220, minSize: 160,
      cell: ({ row }) => (
        <div>
          <Link
            to={`/equipos/${row.original.equipo_id}`}
            className="underline underline-offset-2"
          >
            {row.original.equipo_descripcion ?? `#${row.original.equipo_id}`}
          </Link>
          <span className="block text-xs text-muted-foreground">
            {nombreCliente(row.original.cliente_id)}
          </span>
        </div>
      ),
    },
    { accessorKey: 'insumo_nombre', header: sortableHeader('Insumo'), size: 200, minSize: 140 },
    {
      accessorKey: 'proveedor_nombre',
      header: sortableHeader('Lo entrega'),
      size: 150, minSize: 110,
      // Sin proveedor lo puso el propio cliente, y eso no es un dato faltante.
      cell: ({ row }) => row.original.proveedor_nombre ?? 'El cliente',
    },
    {
      id: 'estado',
      header: 'Estado',
      size: 150, minSize: 120,
      cell: ({ row }) => {
        const i = row.original
        return (
          <div className="flex flex-col gap-0.5">
            <BadgeEstado tono={INSUMO_TONO[i.estado]}>
              {INSUMO_LABELS[i.estado]}
            </BadgeEstado>
            <span className="text-xs text-muted-foreground">
              {i.estado === 'colocado'
                ? fecha(i.fecha_colocacion)
                : i.estado === 'en_poder'
                  ? fecha(i.fecha_entrega)
                  : fecha(i.fecha_pedido)}
            </span>
          </div>
        )
      },
    },
    {
      accessorKey: 'dias_esperando',
      header: sortableHeader('Espera'),
      size: 100, minSize: 80,
      cell: ({ row }) => {
        const d = row.original.dias_esperando
        if (d === null) return '—'
        // Se resalta lo que lleva más de una semana sin llegar, que es cuando
        // el reclamo deja de ser "esperá" y pasa a ser un llamado.
        return (
          <span className={d > 7 ? 'font-medium text-destructive' : undefined}>
            {d} {d === 1 ? 'día' : 'días'}
          </span>
        )
      },
    },
    {
      id: 'contrato',
      header: 'Contrato',
      size: 140, minSize: 110,
      // Tres estados y no dos: sin contrato cargado («—») no es lo mismo que
      // con un contrato que **no cubre los insumos** —uno de service—, que es
      // el caso en el que hay que discutir la factura del proveedor.
      cell: ({ row }) => {
        const i = row.original
        if (i.contrato_numero === null) {
          return <span className="text-muted-foreground">—</span>
        }
        return (
          <span className="flex flex-col gap-0.5">
            <span className="text-sm">{i.contrato_numero}</span>
            {!i.cubierto_por_contrato && (
              <span className="text-xs font-medium text-destructive">no cubre</span>
            )}
          </span>
        )
      },
    },
    {
      id: 'rendimiento',
      header: sortableHeader('Rindió el anterior'),
      accessorKey: 'copias_desde_el_anterior',
      size: 150, minSize: 120,
      cell: ({ row }) => {
        const v = row.original.copias_desde_el_anterior
        if (v === null) return <span className="text-muted-foreground">—</span>
        return `${copias(v)} copias`
      },
    },
    {
      id: 'actions',
      header: () => <div className="text-right">Acciones</div>,
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          {row.original.estado === 'pendiente' && (
            <Button
              size="sm" variant="outline"
              title="Registrar que el insumo llegó"
              onClick={() => abrirEntrega(row.original)}
            >
              <PackageCheck />Llegó
            </Button>
          )}
          {row.original.estado !== 'colocado' && (
            <Button
              size="sm" variant="outline"
              title="Registrar que se puso en la máquina"
              onClick={() => abrirColocacion(row.original)}
            >
              <Droplets />Colocar
            </Button>
          )}
        </div>
      ),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [nombreCliente])

  const pendientes = insumos.filter((i) => i.estado === 'pendiente').length

  return (
    <div className="grid gap-4">
      <EncabezadoDePantalla
        titulo={
          <TituloPantalla icono={Droplets}>
            Insumos
            {estado === 'pendiente' && pendientes > 0 && (
              <Badge variant="secondary">{pendientes} sin llegar</Badge>
            )}
          </TituloPantalla>
        }
      >
        {/* La otra mitad del circuito: acá se registra lo que ya pasó, y allá
            está lo que va a pasar. Ruta propia y no una pestaña, mismo criterio
            que Recepción de equipos: se puede linkear y el atrás funciona. */}
        <Button variant="outline" asChild>
          <Link to="/insumos/a-pedir"><Droplets />Qué hay que pedir</Link>
        </Button>
        <Button onClick={abrirPedido}><FilePlus />Pedir insumo</Button>
      </EncabezadoDePantalla>

      <Card>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <div className="grid gap-2">
            <Label>Estado</Label>
            <Select value={estado} onValueChange={(v) => setEstado(v as typeof estado)}>
              <SelectTrigger aria-label="Filtrar por estado"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="pendiente">Pedidos sin llegar</SelectItem>
                <SelectItem value="en_poder">En el cliente</SelectItem>
                <SelectItem value="colocado">Colocados</SelectItem>
                <SelectItem value="todos">Todos</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>Cliente</Label>
            <SelectBuscable
              value={clienteId}
              onChange={setClienteId}
              opciones={[{ value: TODOS, label: 'Todos los clientes' }, ...opcionesCliente(clientes)]}
              placeholder="Todos los clientes"
              ariaLabel="Filtrar por cliente"
            />
          </div>
          <div className="grid gap-2">
            <Label>Lo entrega</Label>
            <SelectBuscable
              value={proveedorId}
              onChange={setProveedorId}
              opciones={[{ value: TODOS, label: 'Todos los proveedores' }, ...opcionesProveedor(proveedores)]}
              placeholder="Todos los proveedores"
              ariaLabel="Filtrar por proveedor"
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
              data={insumos}
              emptyMessage={
                estado === 'pendiente'
                  ? 'No hay ningún insumo pendiente de entrega.'
                  : 'Sin insumos registrados.'
              }
              search={{
                campos: (i) => [
                  i.equipo_descripcion, i.equipo_serial, i.insumo_nombre,
                  i.proveedor_nombre, i.remito_proveedor,
                ],
                placeholder: 'Buscar por equipo, insumo, proveedor o remito',
              }}
            />
          )}
        </CardContent>
      </Card>

      {/* ── Pedir ─────────────────────────────────────────────────────── */}
      <Dialog open={pidiendo} onOpenChange={(v) => !v && setPidiendo(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Pedir insumo</DialogTitle>
            <DialogDescription>
              Queda pendiente hasta que se registre la entrega.
            </DialogDescription>
          </DialogHeader>
          <Form {...pedido}>
            <form onSubmit={pedido.handleSubmit(handlePedido)} className="grid gap-3">
              <FormField
                control={pedido.control}
                name="equipo_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Equipo</FormLabel>
                    <FormControl>
                      <SelectBuscable
                        value={field.value}
                        onChange={field.onChange}
                        opciones={opcionesDeEquipo}
                        placeholder="Elegí el equipo"
                        ariaLabel="Equipo"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={pedido.control}
                name="insumo_item_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Insumo</FormLabel>
                    <FormControl>
                      <SelectBuscable
                        value={field.value}
                        onChange={field.onChange}
                        opciones={opcionesDeInsumo}
                        placeholder={
                          opcionesDeInsumo.length
                            ? 'Elegí el insumo'
                            : 'Cargá el tóner en Productos'
                        }
                        ariaLabel="Insumo"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="grid gap-3 sm:grid-cols-2">
                <FormField
                  control={pedido.control}
                  name="cantidad"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Cantidad</FormLabel>
                      <FormControl><Input type="number" min={1} {...field} /></FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={pedido.control}
                  name="fecha_pedido"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Fecha del pedido</FormLabel>
                      <FormControl><Input type="date" {...field} /></FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              <FormField
                control={pedido.control}
                name="observaciones"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Observaciones</FormLabel>
                    <FormControl><Input {...field} /></FormControl>
                  </FormItem>
                )}
              />
              {formError && <p className="text-sm text-destructive">{formError}</p>}
              <DialogFooter>
                <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
                <Button type="submit" disabled={saving}>Pedir</Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* ── Llegó ─────────────────────────────────────────────────────── */}
      <Dialog open={aEntregar !== null} onOpenChange={(v) => !v && setAEntregar(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar entrega</DialogTitle>
            <DialogDescription>
              {aEntregar?.insumo_nombre} para {aEntregar?.equipo_descripcion}.
            </DialogDescription>
          </DialogHeader>
          <Form {...entrega}>
            <form onSubmit={entrega.handleSubmit(handleEntrega)} className="grid gap-3">
              <FormField
                control={entrega.control}
                name="fecha_entrega"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Fecha de entrega</FormLabel>
                    <FormControl><Input type="date" {...field} /></FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={entrega.control}
                name="remito_proveedor"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Remito del proveedor</FormLabel>
                    <FormControl><Input placeholder="R-0001" {...field} /></FormControl>
                  </FormItem>
                )}
              />
              {formError && <p className="text-sm text-destructive">{formError}</p>}
              <DialogFooter>
                <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
                <Button type="submit" disabled={saving}>Registrar</Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* ── Colocar ───────────────────────────────────────────────────── */}
      <Dialog open={aColocar !== null} onOpenChange={(v) => !v && setAColocar(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar colocación</DialogTitle>
            <DialogDescription>
              {aColocar?.insumo_nombre} en {aColocar?.equipo_descripcion}.
            </DialogDescription>
          </DialogHeader>
          <Form {...colocacion}>
            <form onSubmit={colocacion.handleSubmit(handleColocacion)} className="grid gap-3">
              <FormField
                control={colocacion.control}
                name="fecha_colocacion"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Fecha de colocación</FormLabel>
                    <FormControl><Input type="date" {...field} /></FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={colocacion.control}
                name="contador_copias"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Contador de copias</FormLabel>
                    <FormControl>
                      <Input type="number" min={0} placeholder="Lectura del display" {...field} />
                    </FormControl>
                    {/* Sin el contador el cambio se registra igual; lo único
                        que no se puede calcular después es el rendimiento. */}
                    <p className="text-xs text-muted-foreground">
                      Opcional. Es lo que permite saber cuánto rindió el anterior.
                    </p>
                  </FormItem>
                )}
              />
              {formError && <p className="text-sm text-destructive">{formError}</p>}
              <DialogFooter>
                <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
                <Button type="submit" disabled={saving}>Registrar</Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
