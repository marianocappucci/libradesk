import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { api, ApiError, type Cliente, type Sector } from '../api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form'
import { DataTable, sortableHeader } from '@/components/data-table'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
// El reparto de dos sets: `fluent-color` para IDENTIDAD (el icono del titulo,
// que etiqueta de que se habla y no cambia nunca) y `fluent` monocromo para
// ACCION, desde `components/iconos-accion`.
//
// Este bloque describia el spike y quedo viejo: nombraba a `streamline-plump`
// (descartado por la atribucion que exige CC BY 4.0) y decia que `Plus` y `X`
// seguian en lucide, que ya no es cierto. Los dos sets vigentes son MIT.
import Users from '~icons/fluent-color/people-16'
import { Check, FilePlus, MapPin, Pencil, Trash2, Undo2, X } from '@/components/iconos-accion'

const clienteSchema = z.object({
  nombre: z.string().trim().min(1, 'El nombre es obligatorio'),
  empresa: z.string().trim().optional(),
  email: z.string().trim().email('Email inválido').optional().or(z.literal('')),
  telefono: z.string().trim().optional(),
  ciudad: z.string().trim().optional(),
  cuit: z.string().trim().optional(),
  // '' = sin cargar, y es un valor legítimo: poner "Responsable Inscripto" por
  // defecto le cambiaría el comprobante de golpe a todos los que ya existen.
  condicion_iva: z.string().optional(),
  domicilio: z.string().trim().optional(),
  observaciones: z.string().trim().optional(),
  tipo_facturacion: z.enum(['mensual', 'por_servicio']),
})

type ClienteFormValues = z.infer<typeof clienteSchema>

/** El `<Select>` de shadcn no admite `value=""` (lo usa para "sin elegir" y el
 *  placeholder queda pegado), así que "sin cargar" viaja con un centinela y se
 *  traduce a `null` al guardar. */
const SIN_CONDICION = '__sin_cargar__'

/** Una condición frente al IVA y su efecto sobre el comprobante, tal como las
 *  devuelve `GET /api/clientes/condiciones-iva`. */
type CondicionIVA = { nombre: string; discrimina: boolean }

/** Las conocidas al escribir esta pantalla. Sólo se usan si la consulta al
 *  backend falla: el que manda es el backend. */
const CONDICIONES_INICIALES: CondicionIVA[] = [
  { nombre: 'Responsable Inscripto', discrimina: true },
  { nombre: 'Monotributista', discrimina: false },
  { nombre: 'IVA Exento', discrimina: false },
  { nombre: 'Consumidor Final', discrimina: false },
  { nombre: 'No Alcanzado', discrimina: false },
]

const EMPTY_VALUES: ClienteFormValues = {
  nombre: '', empresa: '', email: '', telefono: '', ciudad: '', cuit: '',
  condicion_iva: SIN_CONDICION,
  domicilio: '', observaciones: '', tipo_facturacion: 'por_servicio',
}

export function Clientes() {
  const navigate = useNavigate()

  const [clientes, setClientes] = useState<Cliente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Alta y edición en un solo Dialog reusado (`editando === null` es alta),
  // mismo patrón que Contalibra. Antes el formulario era una card que se abría
  // ARRIBA de la tabla y la empujaba hacia abajo, dejando la lista entera a la
  // vista mientras se cargaba un cliente.
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editando, setEditando] = useState<Cliente | null>(null)
  const [saving, setSaving] = useState(false)
  // El error del formulario va DENTRO del modal; el de la página quedaría tapado.
  const [formError, setFormError] = useState<string | null>(null)
  const [clienteADesactivar, setClienteADesactivar] = useState<Cliente | null>(null)
  // Las condiciones y su efecto salen del backend, que es donde está la regla.
  // El fallback deja el formulario usable si la consulta falla; guardar valida
  // igual del otro lado.
  const [condiciones, setCondiciones] = useState<CondicionIVA[]>(CONDICIONES_INICIALES)

  useEffect(() => {
    let vigente = true
    api.get<CondicionIVA[]>('/api/clientes/condiciones-iva')
      .then((res) => { if (vigente && res.length) setCondiciones(res) })
      .catch(() => { /* se quedan las conocidas */ })
    return () => { vigente = false }
  }, [])

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

  function abrirNuevo() {
    setEditando(null)
    setFormError(null)
    form.reset(EMPTY_VALUES)
    setDialogOpen(true)
  }

  function abrirEditar(cliente: Cliente) {
    setEditando(cliente)
    setFormError(null)
    form.reset({
      nombre: cliente.nombre,
      empresa: cliente.empresa ?? '',
      email: cliente.email ?? '',
      telefono: cliente.telefono ?? '',
      ciudad: cliente.ciudad ?? '',
      cuit: cliente.cuit ?? '',
      condicion_iva: cliente.condicion_iva ?? SIN_CONDICION,
      domicilio: cliente.domicilio ?? '',
      observaciones: cliente.observaciones ?? '',
      tipo_facturacion: cliente.tipo_facturacion,
    })
    setDialogOpen(true)
  }

  async function handleSubmit(values: ClienteFormValues) {
    setSaving(true)
    setFormError(null)
    const payload = {
      nombre: values.nombre,
      empresa: values.empresa || null,
      email: values.email || null,
      telefono: values.telefono || null,
      ciudad: values.ciudad || null,
      cuit: values.cuit || null,
      condicion_iva:
        values.condicion_iva && values.condicion_iva !== SIN_CONDICION
          ? values.condicion_iva
          : null,
      domicilio: values.domicilio || null,
      observaciones: values.observaciones || null,
      tipo_facturacion: values.tipo_facturacion,
      // Al editar se conserva el estado real del cliente: antes iba `true`
      // fijo, así que guardar un cliente inactivo lo reactivaba de callado.
      activo: editando?.activo ?? true,
    }
    try {
      if (editando === null) {
        await api.post('/api/clientes', payload)
      } else {
        await api.put(`/api/clientes/${editando.id}`, payload)
      }
      setDialogOpen(false)
      await loadClientes()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  // Un cliente NO se borra: se desactiva. Es la baja lógica de Contalibra,
  // decidida el 2026-08-01 — así el problema de dejar equipos e incidencias
  // huérfanos deja de existir en vez de resolverse, y además es reversible.
  // El endpoint `DELETE` sigue existiendo para un cliente vacío (uno cargado
  // por error), pero ya no lo llama ninguna pantalla.
  async function toggleActivo(cliente: Cliente) {
    setError(null)
    try {
      const ruta = cliente.activo ? 'desactivar' : 'activar'
      await api.post(`/api/clientes/${cliente.id}/${ruta}`)
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
    // Sin gate de rol: `clientes.router` se monta con `staff_or_admin` (ver
    // `app/main.py`), así que el alta, la edición y la baja las puede hacer
    // cualquier usuario logueado. Estaban detrás de `role === 'admin'`, y eso
    // dejaba a la recepcionista —que es quien da de alta al cliente cuando
    // entra con el equipo— sin ningún botón: la pantalla se veía como una
    // lista de sólo lectura aunque la API le aceptara el POST. El resto de las
    // pantallas del producto (incidencias, contratos, presupuestos) nunca
    // gatearon por rol; quien decide es el backend.
    base.push({
      id: 'actions',
      header: () => <div className="text-right">Acciones</div>,
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          <Button size="icon" variant="outline" title="Sectores del cliente" aria-label="Sectores del cliente" onClick={() => abrirSectores(row.original)}><MapPin /></Button>
          <Button size="icon" variant="outline" title="Editar cliente" aria-label="Editar cliente" onClick={() => abrirEditar(row.original)}><Pencil /></Button>
          {/* El tacho desactiva, no borra; y un cliente inactivo ofrece
              reactivarse. Mismo par de botones que Contalibra. */}
          {row.original.activo ? (
            <Button size="icon" variant="outline" className="text-destructive hover:text-destructive" title="Desactivar cliente" aria-label="Desactivar cliente" onClick={() => setClienteADesactivar(row.original)}><Trash2 /></Button>
          ) : (
            <Button size="icon" variant="outline" title="Reactivar cliente" aria-label="Reactivar cliente" onClick={() => toggleActivo(row.original)}><Undo2 /></Button>
          )}
        </div>
      ),
    })
    return base
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Users className="size-5" />Clientes
        </h2>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button onClick={abrirNuevo}><FilePlus />Nuevo cliente</Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-2xl">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <Users className="size-4" />
                  {editando === null ? 'Nuevo cliente' : `Editar cliente — ${editando.nombre}`}
                </DialogTitle>
              </DialogHeader>
            <Form {...form}>
              <form className="flex flex-wrap items-start gap-3" onSubmit={form.handleSubmit(handleSubmit)}>
                {formError && <p className="w-full text-sm text-destructive">{formError}</p>}
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
                {/* CUIT y domicilio: los usan los remitos y presupuestos.
                    Antes había que tipearlos en cada comprobante porque el
                    cliente no los guardaba. */}
                <FormField control={form.control} name="cuit" render={({ field }) => (
                  <FormItem>
                    <FormLabel>CUIT / DNI</FormLabel>
                    <FormControl><Input {...field} className="w-40" placeholder="20-12345678-9" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                {/* Decide si los comprobantes de este cliente muestran el IVA
                    discriminado o el precio final. **No** decide la alícuota:
                    esa es del servicio, y se carga en el catálogo. */}
                <FormField control={form.control} name="condicion_iva" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Condición frente al IVA</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="w-52">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={SIN_CONDICION}>Sin cargar</SelectItem>
                        {condiciones.map((c) => (
                          <SelectItem key={c.nombre} value={c.nombre}>{c.nombre}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      {condiciones.find((c) => c.nombre === field.value)?.discrimina
                        ? 'Los comprobantes salen con el IVA discriminado.'
                        : 'Los comprobantes salen con el precio final, sin desglose.'}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="domicilio" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Domicilio</FormLabel>
                    <FormControl><Input {...field} className="w-52" placeholder="Av. Siempreviva 742" /></FormControl>
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
                <DialogFooter className="w-full">
                  <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
                  <Button type="submit" disabled={saving}>
                    {saving ? 'Guardando…' : editando === null ? 'Crear cliente' : 'Guardar'}
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
              data={clientes}
              emptyMessage="Sin clientes todavía."
              // Click en la fila → ficha del cliente, misma convención que
              // Incidencias. A diferencia de esa pantalla, acá las acciones se
              // quedan en la tabla: `onRowClick` ignora los clicks sobre
              // botones y links de la celda de acciones (ver libra-ui).
              onRowClick={(c) => navigate(`/clientes/${c.id}`)}
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

      <ConfirmDialog
        open={clienteADesactivar !== null}
        onOpenChange={(open) => !open && setClienteADesactivar(null)}
        title={`¿Desactivar a "${clienteADesactivar?.nombre}"?`}
        // Dice lo que pasa de verdad, y lo que pasa ahora es reversible.
        // Contalibra titula "¿Eliminar a X?" aunque desactive; acá se prefiere
        // nombrar la operación real, porque el botón de al lado ofrece
        // reactivar y "eliminar" haría dudar de si eso es posible.
        description="Deja de aparecer en los selectores de equipos e incidencias nuevas. Su historial queda intacto y podés reactivarlo cuando quieras."
        confirmLabel="Desactivar"
        onConfirm={() => { const c = clienteADesactivar; setClienteADesactivar(null); if (c) toggleActivo(c) }}
      />
    </div>
  )
}
