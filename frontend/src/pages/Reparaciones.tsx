import { useEffect, useMemo, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { Link } from 'react-router-dom'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import {
  api, ApiError, opcionesCliente, opcionesProveedor,
  type Cliente, type Proveedor, type Reparacion,
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
import { Wrench } from 'lucide-react'
import { fecha } from '@/lib/format'
import { PackageCheck, ShieldCheck } from '@/components/iconos-accion'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'
import { hoyISO } from 'libra-ui/fechas'

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

  // La ficha completa, que se abre al click en la fila. Es un estado aparte del
  // de cierre porque las dos cosas pueden encadenarse: desde la ficha se puede
  // registrar la vuelta, y ahí se cierra una y se abre la otra.
  const [detalle, setDetalle] = useState<Reparacion | null>(null)

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
    // Si venía de la ficha, se cierra: dos diálogos superpuestos dejan el foco
    // en el de abajo y el `Escape` cierra el equivocado.
    setDetalle(null)
    setACerrar(r)
    setFormError(null)
    form.reset({
      // Por default hoy: lo normal es cerrarla el día que vuelve el equipo.
      fecha_retorno: hoyISO(),
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
          {/* Desde la fase 4 esta lista trae las dos familias juntas: el parque
              del cliente y el stock propio alquilado. Sin la marca, un activo
              se lee como un equipo del cliente. */}
          {row.original.es_activo && (
            <Badge variant="outline" className="ml-2 align-middle">Alquilado</Badge>
          )}
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
      id: 'estado',
      header: 'Estado',
      size: 120, minSize: 100,
      cell: ({ row }) => (
        row.original.abierta
          ? <BadgeEstado tono="curso">En service</BadgeEstado>
          : <BadgeEstado tono="neutro">Vuelta {fecha(row.original.fecha_retorno)}</BadgeEstado>
      ),
    },
    {
      id: 'actions',
      header: () => <div className="text-right">Acciones</div>,
      // Queda una sola acción, y es la que da sentido a la pantalla: el
      // docstring de arriba dice que acá las reparaciones "se miran y se
      // cierran". Mandarla al modal costaría dos clicks en el flujo diario en
      // vez de uno.
      //
      // El link al ticket SÍ se fue al modal: es navegación, no la acción de
      // esta pantalla, y un `#123` suelto en la fila no dice a dónde lleva.
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
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
      <EncabezadoDePantalla
        titulo={
          <TituloPantalla icono={Wrench}>
            Reparaciones
            {estado === 'abiertas' && abiertas > 0 && (
              <Badge variant="secondary">{abiertas} en service</Badge>
            )}
          </TituloPantalla>
        }
      >
        {/* Donde el resto de las pantallas tiene el alta, ésta explica por qué
            no la tiene. El motivo está en el docstring de arriba y no cambia;
            lo que faltaba era decírselo al que mira la pantalla: sin este
            texto parece una pantalla a la que se le olvidaron el botón
            (reporte del usuario, 2026-08-13). */}
        <p className="text-right text-xs text-muted-foreground">
          Se abren desde el ticket, con “Reemplazar equipo”.{' '}
          <Link to="/incidencias" className="underline underline-offset-2">
            Ir a Incidencias
          </Link>
        </p>
      </EncabezadoDePantalla>

      <Card>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <div className="grid gap-2">
            <Label>Estado</Label>
            <Select value={estado} onValueChange={(v) => setEstado(v as typeof estado)}>
              <SelectTrigger aria-label="Filtrar por estado"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="abiertas">En service</SelectItem>
                <SelectItem value="cerradas">Ya volvieron</SelectItem>
                <SelectItem value="todas">Todas</SelectItem>
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
            <Label>Proveedor</Label>
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
              data={reparaciones}
              // El click en la fila abre la ficha. `onRowClick` de libra-ui
              // ignora los clicks sobre `button` y `a`, así que "Registrar
              // vuelta" sigue funcionando sin abrir el modal de paso.
              onRowClick={setDetalle}
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

      {/* La ficha de la reparación, al click en la fila.
       *
       *  Pedido del humano (2026-08-14): *"en reparaciones no es necesario que
       *  haya tanto detalle en cada fila, se debería poder hacer click y que se
       *  abra un modal con todos los datos y el detalle de la reparación"*.
       *
       *  🔴 **La ficha no es sólo el mismo contenido reacomodado.** Tres campos
       *  que el backend ya devolvía no se veían en NINGUNA pantalla del
       *  producto: `diagnostico` —lo que el proveedor dijo que le hizo—,
       *  `observaciones` y `usuario`. El primero se cargaba en el diálogo de
       *  cierre y después no había forma de volver a leerlo. */}
      <Dialog open={detalle !== null} onOpenChange={(open) => !open && setDetalle(null)}>
        <DialogContent className="sm:max-w-2xl">
          {detalle && (
            <>
              <DialogHeader>
                <DialogTitle className="flex flex-wrap items-center gap-2">
                  <Wrench className="size-4" />
                  {detalle.equipo_descripcion ?? 'Equipo sin descripción'}
                  {detalle.es_activo && <Badge variant="outline">Alquilado</Badge>}
                </DialogTitle>
                <DialogDescription>
                  {detalle.equipo_serial
                    ? `Serial ${detalle.equipo_serial}`
                    : 'Sin serial registrado'}
                  {' · '}
                  {detalle.abierta
                    ? `En service hace ${detalle.dias_afuera ?? '?'} días`
                    : `Volvió el ${fecha(detalle.fecha_retorno)}`}
                </DialogDescription>
              </DialogHeader>

              <div className="grid gap-3 text-sm sm:grid-cols-2">
                <Dato label="Cliente">{nombreCliente(detalle.cliente_id)}</Dato>
                <Dato label="Proveedor">{detalle.proveedor_nombre ?? '—'}</Dato>
                <Dato label="Enviado">{fecha(detalle.fecha_envio)}</Dato>
                <Dato label="Retorno">
                  {detalle.fecha_retorno ? fecha(detalle.fecha_retorno) : 'Sigue en service'}
                </Dato>
                <Dato label="Remito de salida">{detalle.remito_salida || '—'}</Dato>
                <Dato label="RMA">{detalle.rma || '—'}</Dato>
                {/* La garantía y el costo NO son excluyentes, aunque lo
                    parezcan: una reparación cubierta puede igual haber costado
                    el flete o un repuesto que la garantía no cubría. Una
                    versión vieja de la tabla mostraba la insignia EN LUGAR del
                    importe y **escondía plata realmente gastada** — una
                    reparación en garantía de $45.000 se leía como si no hubiera
                    costado nada, mientras la ficha del equipo sí la sumaba. Acá
                    se muestran los dos, siempre y en el mismo lugar. */}
                <Dato label="Costo">
                  <span className="flex flex-wrap items-center gap-2">
                    {detalle.en_garantia && (
                      <Badge variant="outline" className="gap-1">
                        <ShieldCheck className="size-3" />Garantía
                      </Badge>
                    )}
                    <span>{pesos(detalle.costo)}</span>
                  </span>
                </Dato>
                <Dato label="Cargada por">{detalle.usuario}</Dato>
              </div>

              <div className="grid gap-3 border-t pt-3 text-sm">
                <Dato label="Diagnóstico del proveedor">
                  {/* `whitespace-pre-line`: el diagnóstico se escribe a mano y
                      suele venir en renglones. Sin esto se lee como un párrafo
                      corrido. */}
                  <span className="whitespace-pre-line">
                    {detalle.diagnostico || 'Todavía sin diagnóstico.'}
                  </span>
                </Dato>
                {detalle.observaciones && (
                  <Dato label="Observaciones">
                    <span className="whitespace-pre-line">{detalle.observaciones}</span>
                  </Dato>
                )}
              </div>

              <DialogFooter className="sm:justify-between">
                {/* El ticket que la originó: se fue de la fila para acá, con el
                    texto que dice a dónde lleva. Si la reparación se abrió sin
                    ticket, no hay nada que mostrar y el hueco lo ocupa un
                    `<span>` para que los botones no se corran. */}
                {detalle.incidencia_id !== null ? (
                  <Button asChild variant="ghost" size="sm">
                    <Link to={`/incidencias/${detalle.incidencia_id}`}>
                      Ver el ticket #{detalle.incidencia_id}
                    </Link>
                  </Button>
                ) : <span />}
                <div className="flex gap-2">
                  <DialogClose asChild><Button variant="outline">Cerrar</Button></DialogClose>
                  {detalle.abierta && (
                    <Button onClick={() => abrirCierre(detalle)}>
                      <PackageCheck />Registrar vuelta
                    </Button>
                  )}
                </div>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

/** Un par etiqueta/valor de la ficha.
 *
 *  Local a esta pantalla, como los `Dato` de `EquipoDetalle` y `ContratoDetalle`
 *  — que ya tienen firmas distintas entre sí. Unificar los tres es su propia
 *  tarea, no algo para arrastrar acá de pasada. */
function Dato({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span>{children}</span>
    </div>
  )
}
