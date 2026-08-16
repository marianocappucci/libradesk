import { useEffect, useMemo, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { useNavigate } from 'react-router-dom'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import {
  api, ApiError, ESTADO_CONTRATO_LABELS, METODO_ACTUALIZACION_LABELS,
  PERIODICIDAD_LABELS, TIPO_CONTRATO_LABELS, TIPOS_CON_CUOTA, opcionesCliente,
  type Cliente, type Contrato, type TipoContrato,
} from '../api'
import { fecha, pesos } from '@/lib/format'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import {
  Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form'
import { DataTable, sortableHeader } from '@/components/data-table'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { FilePenLine as FileSignature } from 'lucide-react'
import { FilePlus } from '@/components/iconos-accion'
import { TituloPantalla } from '@/components/titulo-pantalla'

const TODOS = '__todos__'

const contratoSchema = z.object({
  tipo_contrato: z.string().min(1),
  cliente_id: z.string().min(1, 'Elegí un cliente'),
  fecha_inicio: z.string().min(1, 'La fecha de inicio es obligatoria'),
  fecha_fin: z.string().optional(),
  estado: z.string(),
  periodicidad: z.string(),
  /** Cada cuánto se VISITA, que no es cada cuánto se cobra. `'ninguna'` es el
   *  valor de pantalla para "no genera visitas"; en la API viaja como `null`.
   *  Un `<Select>` de Radix no admite `value=""`, que es por qué hace falta el
   *  centinela en vez de la cadena vacía. */
  frecuencia_visita: z.string(),
  metodo_actualizacion: z.string(),
  dia_vencimiento: z.string().optional(),
  domicilio_instalacion: z.string().trim().optional(),
  responsable: z.string().trim().optional(),
  observaciones: z.string().trim().optional(),
  importe: z.string().trim().optional(),
})

type ContratoFormValues = z.infer<typeof contratoSchema>

/**
 * Contratos de equipos — alquiler, comodato, préstamo, leasing y cesión.
 *
 * El menú dice "Equipos en alquiler" porque es lo que se entiende, pero la
 * entidad es el **contrato**: así las otras cinco modalidades entran como una
 * columna en vez de como un módulo nuevo.
 *
 * El importe se carga en el alta y después **no se edita acá**: se actualiza
 * con vigencia desde la ficha, para que el precio viejo no se pierda.
 */
export function Contratos() {
  const navigate = useNavigate()
  const [contratos, setContratos] = useState<Contrato[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [estado, setEstado] = useState(TODOS)
  const [tipo, setTipo] = useState(TODOS)
  const [clienteId, setClienteId] = useState(TODOS)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const form = useForm<ContratoFormValues>({
    resolver: zodResolver(contratoSchema),
    defaultValues: {
      tipo_contrato: 'alquiler', cliente_id: '', fecha_inicio: '', fecha_fin: '',
      estado: 'borrador', periodicidad: 'mensual',
      frecuencia_visita: 'ninguna', metodo_actualizacion: 'manual',
      dia_vencimiento: '', domicilio_instalacion: '', responsable: '',
      observaciones: '', importe: '',
    },
  })

  // El campo de importe aparece o desaparece según el tipo: un comodato con
  // importe es un 409 del backend, así que ni se ofrece.
  const tipoElegido = form.watch('tipo_contrato') as TipoContrato
  const llevaCuota = TIPOS_CON_CUOTA.includes(tipoElegido)

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  useEffect(() => {
    api.get<Cliente[]>('/api/clientes')
      .then(setClientes)
      .catch((err) => setError(describeError(err)))
  }, [])

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estado, tipo, clienteId])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (estado !== TODOS) params.set('estado', estado)
      if (tipo !== TODOS) params.set('tipo_contrato', tipo)
      if (clienteId !== TODOS) params.set('cliente_id', clienteId)
      const qs = params.toString()
      setContratos(await api.get<Contrato[]>(`/api/contratos${qs ? `?${qs}` : ''}`))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  function abrirNuevo() {
    setFormError(null)
    form.reset({
      tipo_contrato: 'alquiler', cliente_id: '',
      fecha_inicio: new Date().toISOString().slice(0, 10), fecha_fin: '',
      estado: 'borrador', periodicidad: 'mensual',
      frecuencia_visita: 'ninguna', metodo_actualizacion: 'manual',
      dia_vencimiento: '', domicilio_instalacion: '', responsable: '',
      observaciones: '', importe: '',
    })
    setDialogOpen(true)
  }

  async function handleSubmit(values: ContratoFormValues) {
    setSaving(true)
    setFormError(null)
    const body: Record<string, unknown> = {
      tipo_contrato: values.tipo_contrato,
      cliente_id: Number(values.cliente_id),
      fecha_inicio: values.fecha_inicio,
      estado: values.estado,
      periodicidad: values.periodicidad,
      metodo_actualizacion: values.metodo_actualizacion,
      // `'ninguna'` es el centinela de pantalla; la API espera `null`.
      frecuencia_visita: (
        values.frecuencia_visita === 'ninguna' ? null : values.frecuencia_visita
      ),
    }
    if (values.fecha_fin) body.fecha_fin = values.fecha_fin
    if (values.dia_vencimiento) body.dia_vencimiento = Number(values.dia_vencimiento)
    if (values.domicilio_instalacion) body.domicilio_instalacion = values.domicilio_instalacion
    if (values.responsable) body.responsable = values.responsable
    if (values.observaciones) body.observaciones = values.observaciones
    if (llevaCuota && values.importe) body.importe = Number(values.importe)

    try {
      const creado = await api.post<Contrato>('/api/contratos', body)
      setDialogOpen(false)
      navigate(`/contratos/${creado.id}`)
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  const columns = useMemo<ColumnDef<Contrato>[]>(() => [
    {
      accessorKey: 'numero',
      header: sortableHeader('Número'),
      size: 130, minSize: 110,
      cell: ({ row }) => <span className="font-medium">{row.original.numero}</span>,
    },
    {
      accessorKey: 'cliente_nombre',
      header: sortableHeader('Cliente'),
      size: 220, minSize: 140, meta: { stretch: true },
    },
    {
      accessorKey: 'tipo_contrato',
      header: sortableHeader('Modalidad'),
      size: 160, minSize: 120,
      cell: ({ row }) => TIPO_CONTRATO_LABELS[row.original.tipo_contrato] ?? row.original.tipo_contrato,
    },
    {
      accessorKey: 'estado',
      header: sortableHeader('Estado'),
      size: 120, minSize: 100,
      cell: ({ row }) => (
        <Badge variant={row.original.estado === 'activo' ? 'default' : 'outline'}>
          {ESTADO_CONTRATO_LABELS[row.original.estado] ?? row.original.estado}
        </Badge>
      ),
    },
    {
      accessorKey: 'equipos_vigentes',
      header: 'Equipos',
      size: 90, minSize: 70,
    },
    {
      accessorKey: 'importe_vigente',
      header: sortableHeader('Importe'),
      size: 130, minSize: 100,
      cell: ({ row }) => (
        row.original.lleva_cuota
          ? pesos(row.original.importe_vigente, row.original.moneda)
          : <span className="text-muted-foreground">sin cuota</span>
      ),
    },
    {
      accessorKey: 'fecha_inicio',
      header: sortableHeader('Inicio'),
      size: 110, minSize: 90,
      cell: ({ row }) => fecha(row.original.fecha_inicio),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [])

  return (
    <div className="grid gap-4">
      <EncabezadoDePantalla titulo={<TituloPantalla icono={FileSignature}>Equipos en alquiler</TituloPantalla>}>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button onClick={abrirNuevo}><FilePlus />Nuevo contrato</Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-2xl">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <FileSignature className="size-4" />
                Nuevo contrato
              </DialogTitle>
              <DialogDescription>
                Los equipos se agregan después, desde la ficha del contrato.
              </DialogDescription>
            </DialogHeader>
            <Form {...form}>
              <form className="grid gap-3 sm:grid-cols-2" onSubmit={form.handleSubmit(handleSubmit)}>
                {formError && <p className="sm:col-span-2 text-sm text-destructive">{formError}</p>}

                <FormField control={form.control} name="tipo_contrato" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Modalidad</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                      <SelectContent>
                        {Object.entries(TIPO_CONTRATO_LABELS).map(([t, label]) => (
                          <SelectItem key={t} value={t}>{label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      {llevaCuota ? 'Se cobra una cuota periódica.' : 'Se entrega sin cobrar por el equipo.'}
                    </FormDescription>
                  </FormItem>
                )} />

                <FormField control={form.control} name="cliente_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Cliente (locatario)</FormLabel>
                    <FormControl>
                      <SelectBuscable
                        value={field.value}
                        onChange={field.onChange}
                        opciones={opcionesCliente(clientes)}
                        placeholder="Elegí un cliente"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />

                <FormField control={form.control} name="fecha_inicio" render={({ field }) => (
                  <FormItem><FormLabel>Inicio</FormLabel><FormControl><Input type="date" {...field} /></FormControl><FormMessage /></FormItem>
                )} />
                <FormField control={form.control} name="fecha_fin" render={({ field }) => (
                  <FormItem><FormLabel>Fin (opcional)</FormLabel><FormControl><Input type="date" {...field} /></FormControl></FormItem>
                )} />

                {llevaCuota && (
                  <>
                    <FormField control={form.control} name="importe" render={({ field }) => (
                      <FormItem>
                        <FormLabel>Importe</FormLabel>
                        <FormControl><Input type="number" step="0.01" {...field} /></FormControl>
                        <FormDescription>
                          Después se actualiza con vigencia; el valor anterior no se pierde.
                        </FormDescription>
                      </FormItem>
                    )} />
                    <FormField control={form.control} name="periodicidad" render={({ field }) => (
                      <FormItem>
                        <FormLabel>Periodicidad</FormLabel>
                        <Select value={field.value} onValueChange={field.onChange}>
                          <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                          <SelectContent>
                            {Object.entries(PERIODICIDAD_LABELS).map(([p, label]) => (
                              <SelectItem key={p} value={p}>{label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </FormItem>
                    )} />
                    {/* Cada cuánto se VISITA. Va justo debajo de la
                        periodicidad de cobro porque es la distinción que hay
                        que ver: son dos cadencias distintas y se confunden. */}
                    <FormField control={form.control} name="frecuencia_visita" render={({ field }) => (
                      <FormItem>
                        <FormLabel>Visita de mantenimiento</FormLabel>
                        <Select value={field.value} onValueChange={field.onChange}>
                          <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                          <SelectContent>
                            <SelectItem value="ninguna">No genera visitas</SelectItem>
                            {Object.entries(PERIODICIDAD_LABELS).map(([p, label]) => (
                              <SelectItem key={p} value={p}>{label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormDescription>
                          Cada cuánto se visita, que no es cada cuánto se cobra.
                          Se puede cobrar mensual y visitar trimestral.
                        </FormDescription>
                      </FormItem>
                    )} />
                    <FormField control={form.control} name="dia_vencimiento" render={({ field }) => (
                      <FormItem><FormLabel>Día de vencimiento</FormLabel><FormControl><Input type="number" min="1" max="31" {...field} /></FormControl></FormItem>
                    )} />
                    <FormField control={form.control} name="metodo_actualizacion" render={({ field }) => (
                      <FormItem>
                        <FormLabel>Actualización del precio</FormLabel>
                        <Select value={field.value} onValueChange={field.onChange}>
                          <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                          <SelectContent>
                            {Object.entries(METODO_ACTUALIZACION_LABELS).map(([m, label]) => (
                              <SelectItem key={m} value={m}>{label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </FormItem>
                    )} />
                  </>
                )}

                <FormField control={form.control} name="estado" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Estado</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                      <SelectContent>
                        {Object.entries(ESTADO_CONTRATO_LABELS).map(([e, label]) => (
                          <SelectItem key={e} value={e}>{label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormItem>
                )} />
                <FormField control={form.control} name="responsable" render={({ field }) => (
                  <FormItem><FormLabel>Responsable comercial</FormLabel><FormControl><Input {...field} /></FormControl></FormItem>
                )} />
                <FormField control={form.control} name="domicilio_instalacion" render={({ field }) => (
                  <FormItem className="sm:col-span-2"><FormLabel>Domicilio de instalación</FormLabel><FormControl><Input {...field} placeholder="Sucursal Mercedes — Av. San Martín 1200" /></FormControl></FormItem>
                )} />
                <FormField control={form.control} name="observaciones" render={({ field }) => (
                  <FormItem className="sm:col-span-2"><FormLabel>Observaciones</FormLabel><FormControl><Input {...field} /></FormControl></FormItem>
                )} />

                <DialogFooter className="sm:col-span-2">
                  <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
                  <Button type="submit" disabled={saving}>
                    {saving ? 'Guardando…' : 'Crear contrato'}
                  </Button>
                </DialogFooter>
              </form>
            </Form>
          </DialogContent>
        </Dialog>
      </EncabezadoDePantalla>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <div className="grid gap-2">
            <Label>Estado</Label>
            <Select value={estado} onValueChange={setEstado}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>Todos</SelectItem>
                {Object.entries(ESTADO_CONTRATO_LABELS).map(([e, label]) => (
                  <SelectItem key={e} value={e}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>Modalidad</Label>
            <Select value={tipo} onValueChange={setTipo}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>Todas</SelectItem>
                {Object.entries(TIPO_CONTRATO_LABELS).map(([t, label]) => (
                  <SelectItem key={t} value={t}>{label}</SelectItem>
                ))}
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
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable
              columns={columns}
              data={contratos}
              emptyMessage="Sin contratos todavía."
              onRowClick={(c) => navigate(`/contratos/${c.id}`)}
              search={{
                campos: (c) => [c.numero, c.cliente_nombre ?? '', c.responsable ?? ''],
                placeholder: 'Buscar por número, cliente o responsable',
              }}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
