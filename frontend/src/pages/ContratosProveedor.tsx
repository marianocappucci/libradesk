/** Los contratos con el PROVEEDOR: el papel que hay detrás del insumo que llega
 *  sin cobrar.
 *
 *  Es entre el **cliente y un tercero** —nosotros lo administramos, no lo
 *  cobramos—, así que no tiene nada de plata: no es la pantalla de "Equipos en
 *  alquiler", que es lo que nosotros le entregamos al cliente.
 *
 *  **Arranca en Vigentes.** La pregunta que trae a alguien acá es *"¿esto sigue
 *  en pie y hasta cuándo?"*; una lista que mezcla los vencidos de tres años no
 *  la contesta. El orden lo decide el backend: primero lo vigente y, dentro,
 *  lo que vence antes.
 *
 *  La cobertura de máquinas se maneja en el diálogo de la ficha y no en el
 *  formulario de alta, por lo mismo que las referencias de un equipo: una
 *  cobertura cuelga de un contrato que ya existe.
 */
import { useEffect, useMemo, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { Link } from 'react-router-dom'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import {
  api, ApiError, TIPO_CONTRATO_PROVEEDOR_LABELS, opcionesCliente, opcionesProveedor,
  type Cliente, type ContratoProveedor, type ContratoProveedorFicha,
  type Equipo, type Proveedor,
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
import { Handshake } from 'lucide-react'
import { fecha } from '@/lib/format'
import { hoyISO } from 'libra-ui/fechas'
import { FilePlus, PlusCircle, Undo2 } from '@/components/iconos-accion'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

const TODOS = '__todos__'

const contratoSchema = z.object({
  proveedor_id: z.string().min(1, 'Elegí el proveedor'),
  cliente_id: z.string().min(1, 'Elegí el cliente'),
  tipo: z.string().min(1),
  numero_externo: z.string().trim().optional(),
  fecha_inicio: z.string().min(1, 'La fecha de inicio es obligatoria'),
  fecha_fin: z.string().trim().optional(),
  incluye_insumos: z.boolean(),
  incluye_service: z.boolean(),
  contacto_nombre: z.string().trim().optional(),
  contacto_telefono: z.string().trim().optional(),
  observaciones: z.string().trim().optional(),
})

type ContratoFormValues = z.infer<typeof contratoSchema>

const VACIO: ContratoFormValues = {
  proveedor_id: '', cliente_id: '', tipo: 'alquiler', numero_externo: '',
  fecha_inicio: hoyISO(), fecha_fin: '', incluye_insumos: true,
  incluye_service: false, contacto_nombre: '', contacto_telefono: '',
  observaciones: '',
}

export function ContratosProveedor() {
  const [contratos, setContratos] = useState<ContratoProveedor[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [proveedores, setProveedores] = useState<Proveedor[]>([])
  const [equipos, setEquipos] = useState<Equipo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [vigencia, setVigencia] = useState<'vigentes' | 'vencidos' | 'todos'>('vigentes')
  const [clienteId, setClienteId] = useState(TODOS)
  const [proveedorId, setProveedorId] = useState(TODOS)

  const [editando, setEditando] = useState(false)
  const [ficha, setFicha] = useState<ContratoProveedorFicha | null>(null)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  // El alta de cobertura, dentro de la ficha.
  const [aCubrir, setACubrir] = useState('')

  const form = useForm<ContratoFormValues>({
    resolver: zodResolver(contratoSchema),
    defaultValues: VACIO,
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
  }, [])

  useEffect(() => {
    loadContratos()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vigencia, clienteId, proveedorId])

  async function loadContratos() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (vigencia !== 'todos') params.set('vigentes', String(vigencia === 'vigentes'))
      if (clienteId !== TODOS) params.set('cliente_id', clienteId)
      if (proveedorId !== TODOS) params.set('proveedor_id', proveedorId)
      const qs = params.toString()
      setContratos(await api.get<ContratoProveedor[]>(
        `/api/contratos-proveedor${qs ? `?${qs}` : ''}`,
      ))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function abrirFicha(c: ContratoProveedor) {
    setFormError(null)
    setACubrir('')
    try {
      setFicha(await api.get<ContratoProveedorFicha>(`/api/contratos-proveedor/${c.id}`))
    } catch (err) {
      setError(describeError(err))
    }
  }

  function abrirNuevo() {
    setFormError(null)
    form.reset({
      ...VACIO,
      cliente_id: clienteId === TODOS ? '' : clienteId,
      proveedor_id: proveedorId === TODOS ? '' : proveedorId,
    })
    setEditando(true)
  }

  async function handleAlta(values: ContratoFormValues) {
    setSaving(true)
    setFormError(null)
    try {
      await api.post('/api/contratos-proveedor', {
        proveedor_id: Number(values.proveedor_id),
        cliente_id: Number(values.cliente_id),
        tipo: values.tipo,
        numero_externo: values.numero_externo || null,
        fecha_inicio: values.fecha_inicio,
        fecha_fin: values.fecha_fin || null,
        incluye_insumos: values.incluye_insumos,
        incluye_service: values.incluye_service,
        contacto_nombre: values.contacto_nombre || null,
        contacto_telefono: values.contacto_telefono || null,
        observaciones: values.observaciones || null,
      })
      setEditando(false)
      await loadContratos()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function cubrir() {
    if (!ficha || !aCubrir) return
    setSaving(true)
    setFormError(null)
    try {
      await api.post(`/api/contratos-proveedor/${ficha.id}/equipos`, {
        equipo_id: Number(aCubrir),
      })
      setACubrir('')
      // Se recarga la ficha entera: la línea nueva viene con el número del
      // proveedor ya resuelto, que es la columna que se lee de esta lista.
      setFicha(await api.get<ContratoProveedorFicha>(`/api/contratos-proveedor/${ficha.id}`))
      await loadContratos()
    } catch (err) {
      // El 409 dice con qué contrato chocó: se muestra tal cual.
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function retirar(lineaId: number) {
    if (!ficha) return
    setFormError(null)
    try {
      await api.post(`/api/contratos-proveedor/equipos/${lineaId}/retirar`, {})
      setFicha(await api.get<ContratoProveedorFicha>(`/api/contratos-proveedor/${ficha.id}`))
      await loadContratos()
    } catch (err) {
      setFormError(describeError(err))
    }
  }

  const nombreCliente = useMemo(() => {
    const porId = new Map(clientes.map((c) => [c.id, c.empresa || c.nombre]))
    return (id: number) => porId.get(id) ?? `#${id}`
  }, [clientes])

  /** Sólo las máquinas del cliente del contrato: ofrecer las de otro cliente
   *  sería ofrecer algo que vuelve con un error. Mismo criterio que los
   *  depósitos elegibles en el alta de un equipo. */
  const equiposElegibles = useMemo(() => {
    if (!ficha) return []
    const yaCubiertos = new Set(
      ficha.equipos.filter((e) => e.vigente).map((e) => e.equipo_id),
    )
    return equipos
      .filter((e) => e.cliente_id === ficha.cliente_id && !yaCubiertos.has(e.id))
      .map((e) => ({
        value: String(e.id),
        label: [e.tipo, e.marca, e.modelo].filter(Boolean).join(' '),
        hint: [e.sector, ...e.referencias.map((r) => r.valor)]
          .filter(Boolean).join(' · ') || undefined,
      }))
  }, [equipos, ficha])

  const columns = useMemo<ColumnDef<ContratoProveedor>[]>(() => [
    {
      accessorKey: 'numero',
      header: sortableHeader('Número'),
      size: 150, minSize: 120,
      cell: ({ row }) => (
        <div>
          <span className="font-medium">{row.original.numero}</span>
          {row.original.numero_externo && (
            <span className="block text-xs text-muted-foreground">
              {/* El número del proveedor: el que hay que citarle por teléfono. */}
              N° {row.original.numero_externo}
            </span>
          )}
        </div>
      ),
    },
    { accessorKey: 'proveedor_nombre', header: sortableHeader('Proveedor'), size: 170, minSize: 130 },
    {
      id: 'cliente',
      header: 'Cliente',
      size: 180, minSize: 130,
      cell: ({ row }) => nombreCliente(row.original.cliente_id),
    },
    {
      id: 'tipo',
      header: 'Tipo',
      size: 120, minSize: 100,
      cell: ({ row }) => TIPO_CONTRATO_PROVEEDOR_LABELS[row.original.tipo] ?? row.original.tipo,
    },
    {
      id: 'cubre',
      header: 'Cubre',
      size: 150, minSize: 120,
      // Las dos obligaciones por separado: es lo que permite saber cuál te
      // están incumpliendo, y lo que decide si un tóner se paga.
      cell: ({ row }) => (
        <span className="flex flex-wrap gap-1">
          {row.original.incluye_insumos && <Badge variant="outline">Insumos</Badge>}
          {row.original.incluye_service && <Badge variant="outline">Service</Badge>}
          {!row.original.incluye_insumos && !row.original.incluye_service && '—'}
        </span>
      ),
    },
    {
      accessorKey: 'equipos_vigentes',
      header: sortableHeader('Máquinas'),
      size: 100, minSize: 90,
    },
    {
      id: 'vence',
      header: 'Vence',
      size: 160, minSize: 130,
      cell: ({ row }) => {
        const c = row.original
        if (!c.fecha_fin) {
          // Sin plazo pactado no es lo mismo que vencido, y por eso no se pinta.
          return <span className="text-muted-foreground">Sin plazo</span>
        }
        const dias = c.dias_para_vencer
        const porVencer = dias !== null && dias >= 0 && dias <= 30
        return (
          <span className={!c.vigente ? 'text-destructive' : undefined}>
            {fecha(c.fecha_fin)}
            {dias !== null && (
              <span className={`block text-xs ${porVencer ? 'font-medium text-destructive' : 'text-muted-foreground'}`}>
                {dias < 0 ? `vencido hace ${Math.abs(dias)} d` : `faltan ${dias} d`}
              </span>
            )}
          </span>
        )
      },
    },
    {
      id: 'estado',
      header: 'Estado',
      size: 110, minSize: 90,
      cell: ({ row }) => (
        <BadgeEstado tono={row.original.vigente ? 'ok' : 'neutro'}>
          {row.original.vigente ? 'Vigente' : 'Terminado'}
        </BadgeEstado>
      ),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [nombreCliente])

  const vigentes = contratos.filter((c) => c.vigente).length

  return (
    <div className="grid gap-4">
      <EncabezadoDePantalla
        titulo={
          <TituloPantalla icono={Handshake}>
            Contratos de proveedor
            {vigencia === 'vigentes' && vigentes > 0 && (
              <Badge variant="secondary">{vigentes} vigentes</Badge>
            )}
          </TituloPantalla>
        }
      >
        <Button onClick={abrirNuevo}><FilePlus />Nuevo contrato</Button>
      </EncabezadoDePantalla>

      <Card>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <div className="grid gap-2">
            <Label>Vigencia</Label>
            <Select value={vigencia} onValueChange={(v) => setVigencia(v as typeof vigencia)}>
              <SelectTrigger aria-label="Filtrar por vigencia"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="vigentes">Vigentes</SelectItem>
                <SelectItem value="vencidos">Terminados</SelectItem>
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
              data={contratos}
              onRowClick={abrirFicha}
              emptyMessage={
                vigencia === 'vigentes'
                  ? 'No hay contratos de proveedor vigentes.'
                  : 'Sin contratos de proveedor.'
              }
              search={{
                campos: (c) => [
                  c.numero, c.numero_externo, c.proveedor_nombre,
                  nombreCliente(c.cliente_id), c.contacto_nombre,
                ],
                placeholder: 'Buscar por número, proveedor, cliente o contacto',
              }}
            />
          )}
        </CardContent>
      </Card>

      {/* ── Alta ──────────────────────────────────────────────────────── */}
      <Dialog open={editando} onOpenChange={(v) => !v && setEditando(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nuevo contrato de proveedor</DialogTitle>
            <DialogDescription>
              El acuerdo entre el cliente y el tercero que le provee. Las máquinas
              que cubre se agregan después, desde la ficha.
            </DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleAlta)} className="grid gap-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <FormField control={form.control} name="cliente_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Cliente</FormLabel>
                    <FormControl>
                      <SelectBuscable
                        value={field.value} onChange={field.onChange}
                        opciones={opcionesCliente(clientes)}
                        placeholder="Elegí el cliente" ariaLabel="Cliente"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="proveedor_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Proveedor</FormLabel>
                    <FormControl>
                      <SelectBuscable
                        value={field.value} onChange={field.onChange}
                        opciones={opcionesProveedor(proveedores)}
                        placeholder="Elegí el proveedor" ariaLabel="Proveedor"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="tipo" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Tipo</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger aria-label="Tipo"><SelectValue /></SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {Object.entries(TIPO_CONTRATO_PROVEEDOR_LABELS).map(([v, label]) => (
                          <SelectItem key={v} value={v}>{label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="numero_externo" render={({ field }) => (
                  <FormItem>
                    <FormLabel>N° del proveedor</FormLabel>
                    <FormControl><Input placeholder="SJ-2211" {...field} /></FormControl>
                  </FormItem>
                )} />
                <FormField control={form.control} name="fecha_inicio" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Desde</FormLabel>
                    <FormControl><Input type="date" {...field} /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="fecha_fin" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Hasta</FormLabel>
                    <FormControl><Input type="date" {...field} /></FormControl>
                    {/* Vacío es un contrato sin plazo pactado, que es el caso
                        más común y NO es lo mismo que vencido. */}
                    <p className="text-xs text-muted-foreground">Vacío = sin plazo.</p>
                  </FormItem>
                )} />
              </div>

              {/* `<input type="checkbox">` pelado y no un componente de shadcn:
                  este producto no tiene `ui/checkbox`, y los cuatro checkboxes
                  que ya existen (depósitos, facturación, la ficha del reclamo)
                  son nativos. Traer el componente por dos casillas sería sumar
                  una dependencia de UI para no usarla en ningún otro lado. */}
              <div className="grid gap-2">
                <Label>Qué cubre</Label>
                <div className="flex flex-wrap gap-4">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={form.watch('incluye_insumos')}
                      onChange={(e) => form.setValue('incluye_insumos', e.target.checked)}
                    />
                    Insumos
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={form.watch('incluye_service')}
                      onChange={(e) => form.setValue('incluye_service', e.target.checked)}
                    />
                    Service
                  </label>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <FormField control={form.control} name="contacto_nombre" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Contacto de pedidos</FormLabel>
                    <FormControl><Input {...field} /></FormControl>
                  </FormItem>
                )} />
                <FormField control={form.control} name="contacto_telefono" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Teléfono</FormLabel>
                    <FormControl><Input {...field} /></FormControl>
                  </FormItem>
                )} />
              </div>

              <FormField control={form.control} name="observaciones" render={({ field }) => (
                <FormItem>
                  <FormLabel>Observaciones</FormLabel>
                  <FormControl><Input {...field} /></FormControl>
                </FormItem>
              )} />

              {formError && <p className="text-sm text-destructive">{formError}</p>}
              <DialogFooter>
                <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
                <Button type="submit" disabled={saving}>Crear</Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* ── Ficha: qué máquinas cubre ─────────────────────────────────── */}
      <Dialog open={ficha !== null} onOpenChange={(v) => !v && setFicha(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {ficha?.numero} — {ficha?.proveedor_nombre}
            </DialogTitle>
            <DialogDescription>
              {ficha && [
                TIPO_CONTRATO_PROVEEDOR_LABELS[ficha.tipo] ?? ficha.tipo,
                ficha.cliente_nombre,
                ficha.numero_externo ? `N° ${ficha.numero_externo}` : null,
                ficha.fecha_fin ? `hasta ${fecha(ficha.fecha_fin)}` : 'sin plazo',
              ].filter(Boolean).join(' · ')}
            </DialogDescription>
          </DialogHeader>

          {ficha && (ficha.contacto_nombre || ficha.contacto_telefono) && (
            <p className="text-sm">
              <span className="text-muted-foreground">Pedidos a: </span>
              {[ficha.contacto_nombre, ficha.contacto_telefono].filter(Boolean).join(' · ')}
            </p>
          )}

          {ficha?.equipos.length === 0 ? (
            <p className="py-2 text-sm text-muted-foreground">
              Todavía no cubre ninguna máquina.
            </p>
          ) : (
            <ul className="divide-y rounded-md border">
              {ficha?.equipos.map((e) => (
                <li key={e.id} className="flex items-center justify-between gap-2 px-3 py-2">
                  <div className="grid gap-0.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        to={`/equipos/${e.equipo_id}`}
                        className="text-sm font-medium underline underline-offset-2"
                      >
                        {e.equipo_descripcion}
                      </Link>
                      {e.referencias.map((r) => (
                        <Badge key={r.id} variant="outline">{r.valor}</Badge>
                      ))}
                      {!e.vigente && <BadgeEstado tono="neutro">Retirada</BadgeEstado>}
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {[
                        e.equipo_sector,
                        `desde ${fecha(e.fecha_alta)}`,
                        e.fecha_baja ? `hasta ${fecha(e.fecha_baja)}` : null,
                      ].filter(Boolean).join(' · ')}
                    </span>
                  </div>
                  {e.vigente && (
                    <Button
                      size="sm" variant="outline"
                      title="Sacar la máquina del contrato"
                      onClick={() => retirar(e.id)}
                    >
                      <Undo2 />Retirar
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}

          <div className="grid gap-2">
            <Label>Agregar una máquina</Label>
            <div className="flex gap-2">
              <SelectBuscable
                value={aCubrir}
                onChange={setACubrir}
                opciones={equiposElegibles}
                placeholder={
                  equiposElegibles.length
                    ? 'Elegí el equipo'
                    : 'No quedan máquinas de este cliente sin cubrir'
                }
                ariaLabel="Equipo a cubrir"
                className="flex-1"
              />
              <Button onClick={cubrir} disabled={saving || !aCubrir}>
                <PlusCircle />Agregar
              </Button>
            </div>
          </div>

          {formError && <p className="text-sm text-destructive">{formError}</p>}

          <DialogFooter>
            <DialogClose asChild><Button type="button" variant="outline">Cerrar</Button></DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
