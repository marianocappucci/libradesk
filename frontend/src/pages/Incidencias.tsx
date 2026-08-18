import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import {
  api, ApiError, ESTADO_COLOR, ESTADO_LABELS, ESTADO_PILDORA, PRIORIDAD_LABELS, opcionesCliente, opcionesEquipo,
  opcionesCategoria,
  type CategoriaIncidencia, type Cliente, type Equipo, type EquipoTrabajo,
  type Incidencia,
} from '../api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form'
import { DataTable, sortableHeader } from '@/components/data-table'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { CircleAlert as AlertCircle, CircleAlert, Monitor } from 'lucide-react'
import { fechaDeDate } from '@/lib/format'
import { FilePlus, PackageCheck, PlusCircle } from '@/components/iconos-accion'
import { CalendarPlus } from 'lucide-react'
import { TituloPantalla } from '@/components/titulo-pantalla'

const NONE = '__none__'
const TODOS = '__todos__'

const incidenciaSchema = z.object({
  cliente_id: z.string().min(1, 'Elegí un cliente'),
  equipo_id: z.string().optional(),
  titulo: z.string().trim().min(1, 'El título es obligatorio'),
  descripcion: z.string().trim().optional(),
})

type IncidenciaFormValues = z.infer<typeof incidenciaSchema>

const EMPTY_VALUES: IncidenciaFormValues = {
  cliente_id: '', equipo_id: NONE, titulo: '', descripcion: '',
}

export function Incidencias() {
  const navigate = useNavigate()
  const [incidencias, setIncidencias] = useState<Incidencia[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [equipos, setEquipos] = useState<Equipo[]>([])
  const [categorias, setCategorias] = useState<CategoriaIncidencia[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // El alta vive en un Dialog (antes era una card sobre la tabla), mismo
  // patrón que Contalibra y que el resto de las pantallas del producto.
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  // El error del formulario va DENTRO del modal; el de la página quedaría tapado.
  const [formError, setFormError] = useState<string | null>(null)

  // Alta de equipo sin salir del alta de la incidencia (pedido 38).
  const [altaEquipo, setAltaEquipo] = useState(false)
  const [creandoEquipo, setCreandoEquipo] = useState(false)
  const [equipoError, setEquipoError] = useState<string | null>(null)
  const [equipoNuevo, setEquipoNuevo] = useState({ tipo: '', marca: '', modelo: '', serial: '' })

  const [filtroEstado, setFiltroEstado] = useState(TODOS)
  const [filtroPrioridad, setFiltroPrioridad] = useState(TODOS)
  const [filtroCliente, setFiltroCliente] = useState(TODOS)
  const [filtroCategoria, setFiltroCategoria] = useState(TODOS)

  // Los reclamos elegidos para entrar juntos al mismo remito (ver la barra de
  // abajo de la grilla).
  const [elegidos, setElegidos] = useState<number[]>([])
  const [generando, setGenerando] = useState(false)
  // La salida de cuadrilla (pedido del humano, 2026-08-15).
  const [salidaAbierta, setSalidaAbierta] = useState(false)

  const form = useForm<IncidenciaFormValues>({
    resolver: zodResolver(incidenciaSchema),
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
  const equipoNombre = (id: number | null) => id ? (equipos.find((e) => e.id === id)?.tipo ?? `#${id}`) : '—'
  const categoriaRuta = (id: number | null) => id ? (categorias.find((c) => c.id === id)?.ruta ?? `#${id}`) : '—'

  // Un cliente desactivado no se ofrece para tickets nuevos. Se contempla el
  // preseleccionado por el filtro para que el formulario nunca arranque
  // apuntando a una opción que no existe en su propia lista.
  const clientesElegibles = clientes.filter(
    (c) => c.activo || String(c.id) === form.watch('cliente_id'),
  )

  const equiposDelCliente = equipos.filter(
    (e) => String(e.cliente_id) === form.watch('cliente_id'),
  )

  // --- Alta de equipo desde el propio formulario del ticket (pedido 38) -----

  function abrirAltaEquipo() {
    setEquipoError(null)
    setEquipoNuevo({ tipo: '', marca: '', modelo: '', serial: '' })
    setAltaEquipo(true)
  }

  async function crearEquipo() {
    const clienteId = form.watch('cliente_id')
    if (!clienteId || !equipoNuevo.tipo.trim()) {
      setEquipoError('El tipo es obligatorio.')
      return
    }
    setCreandoEquipo(true)
    setEquipoError(null)
    try {
      const creado = await api.post<Equipo>('/api/equipos', {
        cliente_id: Number(clienteId),
        tipo: equipoNuevo.tipo.trim(),
        marca: equipoNuevo.marca.trim() || null,
        modelo: equipoNuevo.modelo.trim() || null,
        serial: equipoNuevo.serial.trim() || null,
      })
      // Se suma a la lista y queda **elegido**: si sólo se recargara, el
      // usuario tendría que volver a buscarlo, que es la mitad del problema
      // que este atajo viene a sacar.
      setEquipos((previos) => [...previos, creado])
      form.setValue('equipo_id', String(creado.id))
      setAltaEquipo(false)
    } catch (err) {
      setEquipoError(describeError(err))
    } finally {
      setCreandoEquipo(false)
    }
  }

  async function loadAll() {
    setLoading(true)
    setError(null)
    try {
      const [inc, cl, eq, cat] = await Promise.all([
        api.get<Incidencia[]>('/api/incidencias'),
        api.get<Cliente[]>('/api/clientes'),
        api.get<Equipo[]>('/api/equipos'),
        api.get<CategoriaIncidencia[]>('/api/categorias'),
      ])
      setIncidencias(inc)
      setClientes(cl)
      setEquipos(eq)
      setCategorias(cat)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  function startCreate() {
    setCreating(true)
    setFormError(null)
    // Si hay un cliente filtrado, el alta arranca con ése elegido.
    form.reset({ ...EMPTY_VALUES, cliente_id: filtroCliente === TODOS ? '' : filtroCliente })
  }

  async function handleSubmit(values: IncidenciaFormValues) {
    setSaving(true)
    setFormError(null)
    const payload = {
      cliente_id: Number(values.cliente_id),
      equipo_id: values.equipo_id && values.equipo_id !== NONE ? Number(values.equipo_id) : null,
      tecnico_id: null,
      sector_id: null,
      // Se clasifica desde el ticket, igual que técnico y sector: el alta se
      // dejó en 4 campos a propósito (decisión del usuario, 2026-07-29).
      categoria_id: null,
      titulo: values.titulo,
      descripcion: values.descripcion || null,
      estado: 'abierto' as const,
      prioridad: 'media' as const,
      horas_invertidas: null,
      notas: null,
      resolucion: null,
      estado_facturacion: null,
      activo: true,
    }
    try {
      const nueva = await api.post<Incidencia>('/api/incidencias', payload)
      setCreating(false)
      navigate(`/incidencias/${nueva.id}`)
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  // Filtrar por una categoría RAÍZ trae también las de sus subcategorías:
  // "Hardware" tiene que contestar por impresoras y notebooks juntas, que es
  // la pregunta que se hace de verdad. Mismo criterio que el reporte.
  function coincideCategoria(i: Incidencia): boolean {
    if (filtroCategoria === TODOS) return true
    const buscada = Number(filtroCategoria)
    if (i.categoria_id === buscada) return true
    const suya = categorias.find((c) => c.id === i.categoria_id)
    return suya?.parent_id === buscada
  }

  const incidenciasFiltradas = useMemo(() => incidencias.filter((i) =>
    (filtroEstado === TODOS || i.estado === filtroEstado)
    && (filtroPrioridad === TODOS || i.prioridad === filtroPrioridad)
    && (filtroCliente === TODOS || i.cliente_id === Number(filtroCliente))
    && coincideCategoria(i),
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ), [incidencias, categorias, filtroEstado, filtroPrioridad, filtroCliente, filtroCategoria])

  // --- Varios reclamos, un solo remito -------------------------------------
  //
  // El caso real: a un cliente se le hicieron tres visitas en el mes y se le
  // emite UNA factura. El remito es lo único que llega a la bandeja de
  // facturación, así que agrupar es agrupar acá.

  /** Un reclamo se puede remitar si está cerrado y no está ya en otro remito.
   *
   *  Es la misma regla que valida el backend, escrita también acá para poder
   *  no ofrecer el tilde: un checkbox que siempre termina en un 409 es peor
   *  que no tenerlo. La que manda es la del backend — ésta sólo evita el viaje.
   */
  const remitable = (i: Incidencia) => i.estado === 'cerrado' && !i.remito_id

  /** Un reclamo se puede agendar si todavía no se resolvió.
   *
   *  Es la otra mitad del tilde, y es **la regla opuesta** a `remitable`: uno
   *  agrupa lo que ya se hizo para cobrarlo, el otro arma lo que falta hacer.
   *  Misma regla que valida el backend, escrita también acá para no ofrecer un
   *  tilde que siempre termina en 409.
   */
  const agendable = (i: Incidencia) => i.estado !== 'cerrado' && i.estado !== 'resuelta'

  // Si un reclamo elegido deja de estar a la vista —porque cambió un filtro—
  // sale de la selección. Sin esto la barra contaría reclamos que no están en
  // pantalla, y el remito saldría con un trabajo que el operador no ve.
  useEffect(() => {
    const visibles = new Set(incidenciasFiltradas.map((i) => i.id))
    // Devolver `prev` sin tocar cuando no sobra nada: un array nuevo en cada
    // render volvería a disparar este efecto para siempre.
    setElegidos((prev) => prev.some((id) => !visibles.has(id))
      ? prev.filter((id) => visibles.has(id))
      : prev)
  }, [incidenciasFiltradas])

  const seleccionadas = useMemo(
    () => incidenciasFiltradas.filter((i) => elegidos.includes(i.id)),
    [incidenciasFiltradas, elegidos],
  )
  const clientesElegidos = new Set(seleccionadas.map((i) => i.cliente_id))
  const mezclaClientes = clientesElegidos.size > 1

  // 🔑 **La selección sirve para dos cosas opuestas**, y qué se puede hacer con
  // ella lo decide su contenido: los cerrados se agrupan en un remito, los
  // abiertos se arman como una salida de cuadrilla. Mezclar los dos no habilita
  // ninguna de las dos acciones, y la barra dice por qué — un botón apagado sin
  // motivo manda a adivinar.
  const todasRemitables = seleccionadas.every(remitable)
  const todasAgendables = seleccionadas.every(agendable)

  async function generarRemito() {
    setGenerando(true)
    setError(null)
    try {
      const remito = await api.post<{ id: number }>(
        '/api/incidencias/convertir-en-remito',
        { incidencia_ids: seleccionadas.map((i) => i.id) },
      )
      // Al remito recién creado y no de vuelta acá, igual que el botón de a
      // uno de la ficha del reclamo: ahí se completan los importes que el
      // sistema no sabe, y desde ahí se edita. Sin ese paso el remito queda en
      // cero y la bandeja de facturación lo rechaza.
      navigate(`/remitos/${remito.id}`)
    } catch (err) {
      setError(describeError(err))
      setGenerando(false)
    }
  }

  const columns = useMemo<ColumnDef<Incidencia>[]>(() => [
    {
      // El tilde para agrupar en un remito. Sólo aparece en los reclamos que
      // se pueden remitar; en el resto la celda queda vacía, que dice "este no
      // va" sin un control apagado que invite a intentarlo.
      id: 'elegir',
      header: () => null,
      size: 36,
      minSize: 36,
      enableSorting: false,
      cell: ({ row }) => {
        const i = row.original
        // Se ofrece si sirve para ALGUNA de las dos acciones. Un reclamo
        // resuelto pero no cerrado no entra en ninguna, y ahí la celda queda
        // vacía: dice "este no va" sin un control apagado que invite a
        // intentarlo.
        if (!remitable(i) && !agendable(i)) return null
        return (
          <input
            type="checkbox"
            checked={elegidos.includes(i.id)}
            // 🔴 `stopPropagation` **es necesario**: el `onRowClick` de la
            // tabla sólo ignora los clicks que caen en un `button` o un `a`
            // (`closest('button, a')` en libra-ui), así que sin esto tildar
            // navega a la ficha del ticket y la selección se pierde.
            onClick={(e) => e.stopPropagation()}
            onChange={() => setElegidos((prev) => prev.includes(i.id)
              ? prev.filter((x) => x !== i.id)
              : [...prev, i.id])}
            aria-label={`Elegir el reclamo #${i.id}`}
          />
        )
      },
    },
    {
      // El semáforo. Va primero y sin encabezado: es una marca, no un dato que
      // se lea. `aria-label` porque un punto de color no le dice nada a un
      // lector de pantalla — y la columna de Estado, que sí es texto, sigue
      // estando: el color acompaña, no reemplaza.
      id: 'semaforo',
      header: () => null,
      size: 28,
      minSize: 28,
      enableSorting: false,
      cell: ({ row }) => (
        <span
          className={`inline-block h-2.5 w-2.5 rounded-full ${ESTADO_COLOR[row.original.estado]}`}
          aria-label={ESTADO_LABELS[row.original.estado]}
          title={ESTADO_LABELS[row.original.estado]}
        />
      ),
    },
    {
      // Antes del título y con ancho fijo: es el número del papel firmado, y
      // la pregunta que se le hace a esta grilla teniendo el talonario en la
      // mano es "¿qué reclamo es éste?". Ordenable porque el talonario es
      // correlativo, así que ordenar por CDS es ordenar por orden de visita.
      accessorKey: 'nro_cds',
      header: sortableHeader('N° CDS'),
      size: 120, minSize: 100,
      cell: ({ row }) => row.original.nro_cds
        ? <span className="tabular-nums">{row.original.nro_cds}</span>
        // Guión y no vacío: distingue "sin comprobante" de una celda que no
        // cargó.
        : <span className="text-muted-foreground">—</span>,
    },
    // El título, con la marca de preventivo delante. La visita **es** una
    // incidencia —para heredar agenda, hoja de ruta y cierre— así que sin algo
    // que la distinga se lee como un reclamo más, y quien mira la bandeja no
    // sabe si llamó el cliente o si toca por contrato.
    { accessorKey: 'titulo', header: sortableHeader('Título'), size: 240, minSize: 140, meta: { stretch: true }, cell: ({ row }) => (
      <span className="flex min-w-0 items-center gap-1.5">
        {row.original.es_visita_mantenimiento && (
          <Badge variant="outline" className="shrink-0"
                 title="Visita de mantenimiento generada por un contrato">
            Preventivo
          </Badge>
        )}
        <span className="block truncate font-medium" title={row.original.titulo}>{row.original.titulo}</span>
      </span>
    ) },
    { accessorKey: 'cliente_id', header: 'Cliente', size: 150, minSize: 110, cell: ({ row }) => clienteNombre(row.original.cliente_id) },
    { accessorKey: 'equipo_id', header: 'Equipo', size: 130, minSize: 100, cell: ({ row }) => equipoNombre(row.original.equipo_id) },
    {
      accessorKey: 'categoria_id',
      header: 'Categoría',
      size: 150,
      minSize: 110,
      cell: ({ row }) => (
        <span className="block truncate text-muted-foreground" title={categoriaRuta(row.original.categoria_id)}>
          {categoriaRuta(row.original.categoria_id)}
        </span>
      ),
    },
    {
      accessorKey: 'prioridad',
      header: sortableHeader('Prioridad'),
      size: 100,
      minSize: 85,
      cell: ({ row }) => (
        <Badge variant={row.original.prioridad === 'alta' ? 'destructive' : 'outline'}>
          {PRIORIDAD_LABELS[row.original.prioridad]}
        </Badge>
      ),
    },
    {
      accessorKey: 'estado',
      header: sortableHeader('Estado'),
      size: 120,
      minSize: 95,
      // La píldora lleva el color del semáforo (pedido del usuario,
      // 2026-08-13). Antes era `default`/`outline` según si estaba terminado,
      // así que "Abierto" y "En progreso" —los dos estados que hay que mirar—
      // salían con el mismo contorno gris, y el color de la fila vivía sólo en
      // el punto de la primera columna, a media fila de la palabra que
      // significa lo mismo.
      //
      // `variant="outline"` y el color por `className`: `cn()` es tailwind-merge,
      // así que estas clases le ganan a las de la variante dentro de su propio
      // grupo (bg, text, border) sin pelear por especificidad.
      cell: ({ row }) => (
        <Badge variant="outline" className={ESTADO_PILDORA[row.original.estado]}>
          {ESTADO_LABELS[row.original.estado]}
        </Badge>
      ),
    },
    {
      accessorKey: 'fecha_creacion',
      header: sortableHeader('Creada'),
      size: 110,
      minSize: 95,
      cell: ({ row }) => row.original.fecha_creacion ? fechaDeDate(new Date(row.original.fecha_creacion)) : '—',
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [clientes, equipos, categorias, elegidos])

  return (
    <div className="grid gap-4">
      <EncabezadoDePantalla titulo={<TituloPantalla icono={AlertCircle}>Incidencias</TituloPantalla>}>
        <Dialog open={creating} onOpenChange={setCreating}>
          <DialogTrigger asChild>
            <Button onClick={startCreate}><FilePlus />Nueva incidencia</Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-2xl">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CircleAlert className="size-4" />Nueva incidencia
              </DialogTitle>
              <DialogDescription>
                El resto de los campos —categoría, prioridad, técnico, sector,
                horas— se asignan después desde el ticket.
              </DialogDescription>
            </DialogHeader>
            <Form {...form}>
              <form className="flex flex-wrap items-start gap-3" onSubmit={form.handleSubmit(handleSubmit)}>
                {formError && <p className="w-full text-sm text-destructive">{formError}</p>}
                <FormField control={form.control} name="cliente_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Cliente</FormLabel>
                    <FormControl>
                      <SelectBuscable
                        value={field.value}
                        onChange={field.onChange}
                        opciones={opcionesCliente(clientesElegibles)}
                        placeholder="Cliente…"
                        ariaLabel="Cliente"
                        className="w-44"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="equipo_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Equipo</FormLabel>
                    <FormControl>
                      <SelectBuscable
                        value={field.value ?? NONE}
                        onChange={field.onChange}
                        // Sólo los equipos del cliente elegido: ofrecer el
                        // parque entero de todos los clientes es lo que hacía
                        // esta lista inmanejable, y además deja elegir un
                        // equipo que no es de ese cliente.
                        opciones={[
                          { value: NONE, label: 'Sin equipo' },
                          ...opcionesEquipo(equiposDelCliente),
                        ]}
                        ariaLabel="Equipo"
                        className="w-44"
                        emptyMessage="Ese cliente no tiene equipos."
                      />
                    </FormControl>
                    {/* Pedido 38: el equipo con el que se trabajó puede no
                        estar cargado todavía, y hasta ahora eso obligaba a
                        abandonar el alta, ir a Equipos, cargarlo y volver a
                        empezar. Se carga acá mismo y queda elegido. */}
                    <Button
                      type="button" variant="link" size="sm"
                      className="h-auto justify-start p-0 text-xs"
                      disabled={!form.watch('cliente_id')}
                      onClick={abrirAltaEquipo}
                    >
                      <PlusCircle className="size-3" />
                      {form.watch('cliente_id')
                        ? 'El equipo no está en la lista'
                        : 'Elegí un cliente para poder agregar un equipo'}
                    </Button>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="titulo" render={({ field }) => (
                  <FormItem className="w-full">
                    <FormLabel>Título</FormLabel>
                    <FormControl><Input {...field} placeholder="Resumen breve del problema" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="descripcion" render={({ field }) => (
                  <FormItem className="w-full">
                    <FormLabel>Descripción</FormLabel>
                    <FormControl>
                      <Textarea {...field} rows={3} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <DialogFooter className="w-full">
                  <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
                  <Button type="submit" disabled={saving}>{saving ? 'Creando…' : 'Crear incidencia'}</Button>
                </DialogFooter>
              </form>
            </Form>
          </DialogContent>
        </Dialog>
      </EncabezadoDePantalla>

      {/* El alta de equipo vive FUERA del Dialog de la incidencia: anidar dos
          Dialog de Radix cierra el de adentro al hacer foco en el de afuera, y
          el formulario del ticket se perdería. Los dos abiertos a la vez es
          justo lo que se quiere — se vuelve al ticket con el equipo elegido. */}
      <Dialog open={altaEquipo} onOpenChange={setAltaEquipo}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Monitor className="size-4" />Nuevo equipo
            </DialogTitle>
            <DialogDescription>
              Se agrega al parque de{' '}
              {clientes.find((c) => String(c.id) === form.watch('cliente_id'))?.nombre ?? 'el cliente'}
              {' '}y queda elegido en la incidencia.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            {equipoError && <p className="text-sm text-destructive">{equipoError}</p>}
            <div className="grid gap-2">
              <span className="text-sm font-medium">Tipo</span>
              <Input
                autoFocus
                value={equipoNuevo.tipo}
                onChange={(e) => setEquipoNuevo({ ...equipoNuevo, tipo: e.target.value })}
                placeholder="Notebook, Impresora, Router…"
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="grid gap-2">
                <span className="text-sm font-medium">Marca</span>
                <Input
                  value={equipoNuevo.marca}
                  onChange={(e) => setEquipoNuevo({ ...equipoNuevo, marca: e.target.value })}
                />
              </div>
              <div className="grid gap-2">
                <span className="text-sm font-medium">Modelo</span>
                <Input
                  value={equipoNuevo.modelo}
                  onChange={(e) => setEquipoNuevo({ ...equipoNuevo, modelo: e.target.value })}
                />
              </div>
            </div>
            <div className="grid gap-2">
              <span className="text-sm font-medium">Número de serie</span>
              <Input
                value={equipoNuevo.serial}
                onChange={(e) => setEquipoNuevo({ ...equipoNuevo, serial: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
            <Button type="button" onClick={crearEquipo} disabled={creandoEquipo}>
              {creandoEquipo ? 'Creando…' : 'Crear y elegir'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex flex-wrap items-end gap-3">
        <div className="grid gap-2">
          <span className="text-xs text-muted-foreground">Estado</span>
          <Select value={filtroEstado} onValueChange={setFiltroEstado}>
            <SelectTrigger className="w-40" aria-label="Filtrar por estado"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={TODOS}>Todos</SelectItem>
              {(Object.keys(ESTADO_LABELS) as (keyof typeof ESTADO_LABELS)[]).map((e) => (
                <SelectItem key={e} value={e}>{ESTADO_LABELS[e]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-2">
          <span className="text-xs text-muted-foreground">Prioridad</span>
          <Select value={filtroPrioridad} onValueChange={setFiltroPrioridad}>
            <SelectTrigger className="w-36" aria-label="Filtrar por prioridad"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={TODOS}>Todas</SelectItem>
              {(Object.keys(PRIORIDAD_LABELS) as (keyof typeof PRIORIDAD_LABELS)[]).map((p) => (
                <SelectItem key={p} value={p}>{PRIORIDAD_LABELS[p]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-2">
          <span className="text-xs text-muted-foreground">Cliente</span>
          <SelectBuscable
            value={filtroCliente}
            onChange={setFiltroCliente}
            opciones={[{ value: TODOS, label: 'Todos' }, ...opcionesCliente(clientes)]}
            ariaLabel="Filtrar por cliente"
            className="w-48"
          />
        </div>
        {/* Acá se ofrecen TODAS las categorías, raíces incluidas: elegir una
            raíz es el caso interesante ("todo lo de Hardware"). En cambio
            asignarle una a un ticket usa sólo las hojas. */}
        {categorias.length > 0 && (
          <div className="grid gap-2">
            <span className="text-xs text-muted-foreground">Categoría</span>
            <SelectBuscable
              value={filtroCategoria}
              onChange={setFiltroCategoria}
              opciones={[{ value: TODOS, label: 'Todas' }, ...opcionesCategoria(categorias)]}
              ariaLabel="Filtrar por categoría"
              className="w-48"
            />
          </div>
        )}
        {(filtroEstado !== TODOS || filtroPrioridad !== TODOS || filtroCliente !== TODOS || filtroCategoria !== TODOS) && (
          <Button variant="ghost" size="sm" onClick={() => { setFiltroEstado(TODOS); setFiltroPrioridad(TODOS); setFiltroCliente(TODOS); setFiltroCategoria(TODOS) }}>
            Limpiar filtros
          </Button>
        )}
      </div>

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable
              columns={columns}
              data={incidenciasFiltradas}
              emptyMessage="Sin incidencias todavía."
              onRowClick={(i) => navigate(`/incidencias/${i.id}`)}
              search={{
                // El número de ticket entra a propósito: es como se lo nombra
                // por teléfono ("fijate el 14"), y sin él habría que acordarse
                // del título para encontrarlo.
                campos: (i) => [
                  i.id, i.titulo, i.descripcion,
                  clienteNombre(i.cliente_id), equipoNombre(i.equipo_id),
                  categoriaRuta(i.categoria_id),
                ],
                placeholder: 'Buscar por número, título, descripción, cliente, equipo o categoría',
              }}
            />
          )}
        </CardContent>
      </Card>

      {/* La barra aparece recién con algo tildado: hasta entonces no hay nada
          que decir, y una barra siempre visible con un botón apagado le come
          lugar a la grilla todos los días para un flujo que es mensual.

          Y una vez que aparece **queda flotando al pie, siempre a la vista**
          (pedido del humano, 2026-08-16). Es el defecto que tenía al pie de la
          grilla: se tildan reclamos de arriba, la lista es larga, y el botón
          que hace algo con lo tildado está a un scroll de distancia — o peor,
          se tilda algo y no pasa nada visible, porque la barra apareció fuera
          de la pantalla.

          `sticky` y no `fixed`: la barra tiene que respetar el ancho de la
          columna de contenido, que cambia según la sidebar esté abierta,
          cerrada o en mobile. Un `fixed` se posiciona contra el viewport y
          quedaría cruzando por debajo del menú.

          ⚠️ El contenedor de la pantalla sigue siendo `grid gap-4` **a
          propósito**. El primer intento lo pasó a `flex flex-col` por la teoría
          de que el bloque contenedor de un ítem de grid es su propia celda y
          ahí el `sticky` no tendría recorrido. Medido en Chromium sobre un
          arnés con esta misma cadena de contenedores, es falso: con el
          contenedor en `grid`, la barra queda en 704 px de un viewport de 720
          (o sea pegada, a los 16 px de `bottom-4`) y sin la clase `sticky` se
          va a 1236, fuera de la pantalla. La clase alcanza sola; cambiar el
          contenedor era una modificación sin motivo. */}
      {seleccionadas.length > 0 && (
        <Card className="sticky bottom-4 z-20 shadow-lg">
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-sm">
              <span className="font-medium">
                {seleccionadas.length === 1
                  ? '1 reclamo elegido'
                  : `${seleccionadas.length} reclamos elegidos`}
              </span>
              {todasRemitables && mezclaClientes && (
                // El motivo al lado del botón apagado, no en un tooltip: un
                // botón que no se puede apretar y no dice por qué manda a
                // adivinar.
                <span className="ml-2 text-destructive">
                  Son de {clientesElegidos.size} clientes distintos y un remito
                  se emite a nombre de uno solo.
                </span>
              )}
              {!todasRemitables && !todasAgendables && (
                <span className="ml-2 text-destructive">
                  Hay reclamos cerrados y abiertos mezclados: los cerrados se
                  agrupan en un remito y los abiertos se agendan, y son dos cosas
                  distintas.
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => setElegidos([])}>
                Limpiar
              </Button>
              {/* Se ofrece la acción que corresponde a lo elegido, y no las dos
                  apagadas: dos botones muertos al lado de uno vivo se leen como
                  que algo está roto. */}
              {todasAgendables && (
                <Button onClick={() => setSalidaAbierta(true)}>
                  <CalendarPlus />
                  Armar salida
                </Button>
              )}
              {todasRemitables && (
                <Button
                  onClick={generarRemito}
                  disabled={generando || mezclaClientes}
                >
                  <PackageCheck />
                  {generando ? 'Generando…' : 'Generar remito'}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      <ArmarSalida
        abierto={salidaAbierta}
        onCerrar={() => setSalidaAbierta(false)}
        reclamos={seleccionadas}
        onListo={() => {
          setSalidaAbierta(false)
          setElegidos([])
          void loadAll()
        }}
      />
    </div>
  )
}


/**
 * Armar una salida de cuadrilla con varios reclamos (pedido del humano,
 * 2026-08-15).
 *
 * Antes había que abrir cada ticket y agendarlo de a uno, calculando los
 * horarios a mano.
 *
 * 🔑 **No se elige vehículo ni técnicos acá.** Eso es de la cuadrilla, no de la
 * salida (decisión del humano): elegirla ya elige con qué sale y con quiénes,
 * porque vive en `vehiculos.equipo_id` y en sus integrantes. El diálogo lo
 * muestra como confirmación de lo que se está eligiendo, no como campos.
 */
function ArmarSalida({ abierto, onCerrar, reclamos, onListo }: {
  abierto: boolean
  onCerrar: () => void
  reclamos: Incidencia[]
  onListo: () => void
}) {
  const [cuadrillas, setCuadrillas] = useState<EquipoTrabajo[]>([])
  const [equipoId, setEquipoId] = useState('')
  // 🔴 **ISO y no `fechaDeDate`.** El `dd-mm-aaaa` es de PRESENTACIÓN; un
  // `<input type="date">` lee y escribe ISO, y con el formato local queda vacío
  // y `new Date()` de la previa da `Invalid Date`. El primer intento usó el
  // helper de presentación y lo agarró el test de la previa de horarios.
  const [dia, setDia] = useState(() => new Date().toISOString().slice(0, 10))
  const [hora, setHora] = useState('09:00')
  const [duracion, setDuracion] = useState('60')
  const [traslado, setTraslado] = useState('0')
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!abierto) return
    setError(null)
    api.get<EquipoTrabajo[]>('/api/equipos-trabajo')
      .then(setCuadrillas)
      .catch(() => setError('No se pudieron cargar las cuadrillas.'))
  }, [abierto])

  const cuadrilla = cuadrillas.find((c) => String(c.id) === equipoId)

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.post('/api/incidencias/agendar-salida', {
        // 🔑 El orden de la lista es el orden del recorrido, y es el orden en
        // que están tildados en la grilla.
        incidencia_ids: reclamos.map((r) => r.id),
        equipo_trabajo_id: Number(equipoId),
        inicio: `${dia}T${hora}:00`,
        duracion_minutos: Number(duracion),
        traslado_minutos: Number(traslado),
      })
      onListo()
    } catch (err) {
      // El 409 del backend trae el choque con el número del trabajo que se
      // pisa: se muestra tal cual, porque decir "no se pudo" obligaría a ir a
      // buscar cuál era.
      setError(err instanceof ApiError ? err.detail : 'No se pudo armar la salida.')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Armar salida</DialogTitle>
          <DialogDescription>
            {reclamos.length === 1
              ? '1 reclamo, en el orden en que está tildado.'
              : `${reclamos.length} reclamos, en el orden en que están tildados.`}
            {' '}Cada parada arranca cuando termina la anterior.
          </DialogDescription>
        </DialogHeader>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-2 sm:col-span-2">
            <Label htmlFor="salida-cuadrilla">Cuadrilla</Label>
            <Select value={equipoId} onValueChange={setEquipoId}>
              <SelectTrigger id="salida-cuadrilla">
                <SelectValue placeholder="Elegí una cuadrilla" />
              </SelectTrigger>
              <SelectContent>
                {cuadrillas.filter((c) => c.activo).map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>{c.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {/* Con qué sale y con quiénes, como confirmación: son datos de la
                cuadrilla y se muestran para no tener que ir a buscarlos. */}
            {cuadrilla && (
              <p className="text-xs text-muted-foreground">
                {cuadrilla.vehiculos.length > 0
                  ? `Sale en ${cuadrilla.vehiculos.map((v) => v.patente).join(', ')}`
                  : 'Sin vehículo asignado'}
                {' · '}
                {cuadrilla.responsable_nombre ?? 'sin responsable'}
                {cuadrilla.integrantes.length > 0
                  && ` y ${cuadrilla.integrantes.map((i) => i.nombre).join(', ')}`}
              </p>
            )}
          </div>

          <div className="grid gap-2">
            <Label htmlFor="salida-dia">Día</Label>
            <Input id="salida-dia" type="date" value={dia}
                   onChange={(e) => setDia(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="salida-hora">Hora de arranque</Label>
            <Input id="salida-hora" type="time" value={hora}
                   onChange={(e) => setHora(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="salida-duracion">Duración de cada parada (min)</Label>
            <Input id="salida-duracion" type="number" min={1} value={duracion}
                   onChange={(e) => setDuracion(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="salida-traslado">Traslado entre paradas (min)</Label>
            <Input id="salida-traslado" type="number" min={0} value={traslado}
                   onChange={(e) => setTraslado(e.target.value)} />
          </div>
        </div>

        {/* El recorrido con sus horarios, calculado acá para que se vea antes de
            guardar. El backend hace la misma cuenta; ésta es la previa. */}
        <ol className="max-h-[30vh] space-y-1 overflow-y-auto text-sm">
          {reclamos.map((r, i) => {
            const minutos = i * (Number(duracion || 0) + Number(traslado || 0))
            const arranque = new Date(`${dia}T${hora}:00`)
            arranque.setMinutes(arranque.getMinutes() + minutos)
            const valido = !Number.isNaN(arranque.getTime())
            return (
              <li key={r.id} className="flex gap-3">
                <span className="w-14 shrink-0 tabular-nums text-muted-foreground">
                  {valido
                    ? arranque.toTimeString().slice(0, 5)
                    : '--:--'}
                </span>
                <span className="truncate">#{r.id} · {r.titulo}</span>
              </li>
            )
          })}
        </ol>

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancelar</Button>
          </DialogClose>
          <Button onClick={() => void guardar()} disabled={guardando || !equipoId}>
            {guardando ? 'Agendando…' : 'Agendar la salida'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
