import { useEffect, useMemo, useRef, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { useNavigate } from 'react-router-dom'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import {
  api, ApiError, ESTADO_EQUIPO_LABELS, describirEquipo, lugarDe, opcionesCliente,
  opcionesDeposito, opcionesProveedor, ubicacionTexto,
  type Cliente, type Deposito, type Equipo, type Proveedor, type Sector,
} from '../api'
import { DialogoDeReferencias } from './equipos-referencias'
import { MoverEquipo } from '@/components/mover-equipo'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { BadgeEstado } from 'libra-ui/badge-estado'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form'
import { DataTable, sortableHeader } from '@/components/data-table'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Dialog, DialogClose, DialogContent, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Monitor } from 'lucide-react'
import { ArrowLeftRight, Eye, FilePlus, Pencil, Tags, Trash2 } from '@/components/iconos-accion'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

// Sin depósito: el equipo está instalado en el sector del cliente. Radix no
// admite un <SelectItem value="">, así que el "ninguno" necesita valor propio.
const SIN_DEPOSITO = '__ninguno__'

// El equipo es del cliente, que es el caso normal del parque. Mismo motivo que
// `SIN_DEPOSITO` para no usar la cadena vacía.
const DEL_CLIENTE = '__del_cliente__'

const equipoSchema = z.object({
  cliente_id: z.string().min(1, 'Elegí un cliente'),
  tipo: z.string().trim().min(1, 'El tipo es obligatorio'),
  marca: z.string().trim().optional(),
  modelo: z.string().trim().optional(),
  serial: z.string().trim().optional(),
  ubicacion_oficina: z.string().trim().optional(),
  sector: z.string().trim().optional(),
  deposito_id: z.string().optional(),
  // El tercero de quien es el equipo, cuando no es del cliente.
  proveedor_id: z.string().optional(),
  estado: z.string().min(1),
  garantia_vence: z.string().trim().optional(),
  observaciones: z.string().trim().optional(),
  // Solo para el historial: si el guardado implica traslado o cambio de
  // estado, este texto queda como motivo del movimiento.
  motivo: z.string().trim().optional(),
})

type EquipoFormValues = z.infer<typeof equipoSchema>

const EMPTY_VALUES: EquipoFormValues = {
  cliente_id: '', tipo: '', marca: '', modelo: '', serial: '',
  ubicacion_oficina: '', sector: '', deposito_id: SIN_DEPOSITO,
  proveedor_id: DEL_CLIENTE, estado: 'activo',
  garantia_vence: '', observaciones: '', motivo: '',
}

const ESTADOS_EQUIPO = ['activo', 'en_reparacion', 'almacenado', 'baja']

// Radix no admite un <SelectItem value="">, así que el "sin filtro" necesita
// un valor propio (misma convención que Incidencias.tsx).
const TODOS = 'todos'

export function Equipos() {
  const navigate = useNavigate()

  const [equipos, setEquipos] = useState<Equipo[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [depositos, setDepositos] = useState<Deposito[]>([])
  const [proveedores, setProveedores] = useState<Proveedor[]>([])
  // El equipo cuyos identificadores ajenos se están mirando. Diálogo aparte
  // del de edición — ver `equipos-referencias.tsx`.
  const [conReferencias, setConReferencias] = useState<Equipo | null>(null)
  // El equipo que se está mandando a otro lado. Diálogo aparte del de
  // edición a propósito — ver `components/mover-equipo.tsx`.
  const [aMover, setAMover] = useState<Equipo | null>(null)
  // Los sectores del cliente elegido en el formulario, para sugerirlos en el
  // campo Sector. Son los mismos que usan incidencias y contratos: el campo
  // del equipo sigue siendo texto libre, esto sólo evita que el mismo lugar
  // se escriba de tres formas distintas.
  const [sectores, setSectores] = useState<Sector[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Alta y edición en un solo Dialog reusado (`editando === null` es alta),
  // mismo patrón que Contalibra. Antes era una card sobre la tabla: al cargar
  // un equipo quedaban a la vista el formulario, la lista entera y el filtro,
  // los tres compitiendo por la atención.
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editando, setEditando] = useState<Equipo | null>(null)
  const [saving, setSaving] = useState(false)
  // El error del formulario va DENTRO del modal; el de la página quedaría tapado.
  const [formError, setFormError] = useState<string | null>(null)
  const [aBorrar, setABorrar] = useState<Equipo | null>(null)
  const [filtroCliente, setFiltroCliente] = useState(TODOS)

  const form = useForm<EquipoFormValues>({
    resolver: zodResolver(equipoSchema),
    defaultValues: EMPTY_VALUES,
  })

  const montado = useRef(false)

  useEffect(() => {
    loadAll()
  }, [])

  // El filtro por cliente recarga SOLO los equipos y sin pasar por `loading`:
  // si la tabla se desmontara para mostrar "Cargando…", el buscador (que vive
  // dentro de DataTable) perdería lo escrito en cada cambio de cliente.
  useEffect(() => {
    if (!montado.current) {
      montado.current = true
      return
    }
    loadEquipos()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtroCliente])

  // Los sectores se recargan al cambiar de cliente en el formulario, no al
  // abrirlo: el alta arranca sin cliente y el select se puede cambiar con el
  // diálogo ya abierto. Sin cliente no hay a quién pedírselos.
  const clienteDelForm = form.watch('cliente_id')
  useEffect(() => {
    if (!clienteDelForm) {
      setSectores([])
      return
    }
    // Son sugerencias: si falla, el campo sigue aceptando texto libre igual
    // que siempre. No hay nada que reportarle al usuario.
    api.get<Sector[]>(`/api/sectores?cliente_id=${clienteDelForm}`)
      .then(setSectores)
      .catch(() => setSectores([]))
  }, [clienteDelForm])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  const clienteNombre = (id: number) => clientes.find((c) => c.id === id)?.nombre ?? `#${id}`

  // Clientes ofrecibles en el formulario: sólo los activos, **más el que ya
  // tiene el equipo que se está editando** aunque esté desactivado. Sin esa
  // excepción, abrir un equipo de un cliente dado de baja mostraría el
  // selector vacío y guardarlo lo movería de cliente sin querer.
  const clientesElegibles = clientes.filter(
    (c) => c.activo || String(c.id) === form.watch('cliente_id'),
  )

  // Depósitos ofrecibles: los propios de la empresa (reciben equipos de
  // cualquier cliente) más los del cliente que se está eligiendo en el
  // formulario. Es la misma regla que valida el backend; ofrecer los de otro
  // cliente sería ofrecer algo que va a volver con un 422.
  const depositosElegibles = depositos.filter(
    (d) => d.cliente_id === null || String(d.cliente_id) === form.watch('cliente_id'),
  )

  // El filtro lo resuelve el backend (`?cliente_id=`, ya existía y no lo usaba
  // nadie), no un filter local: es lo que escala cuando el parque crezca.
  const rutaEquipos = () =>
    filtroCliente === TODOS ? '/api/equipos' : `/api/equipos?cliente_id=${filtroCliente}`

  async function loadEquipos() {
    setError(null)
    try {
      setEquipos(await api.get<Equipo[]>(rutaEquipos()))
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function loadAll() {
    setLoading(true)
    setError(null)
    try {
      // Sólo los activos: el selector del formulario es para elegir a dónde va
      // el equipo, y un depósito dado de baja no es un destino válido.
      const [eq, cl, dep, prov] = await Promise.all([
        api.get<Equipo[]>(rutaEquipos()),
        api.get<Cliente[]>('/api/clientes'),
        api.get<Deposito[]>('/api/depositos?solo_activos=true'),
        api.get<Proveedor[]>('/api/proveedores'),
      ])
      setEquipos(eq)
      setClientes(cl)
      setDepositos(dep)
      setProveedores(prov)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  function abrirNuevo() {
    setEditando(null)
    setFormError(null)
    // Si hay un cliente filtrado, el alta ya viene con ése elegido: es el
    // caso normal (se filtra por cliente y se le carga un equipo).
    form.reset({ ...EMPTY_VALUES, cliente_id: filtroCliente === TODOS ? '' : filtroCliente })
    setDialogOpen(true)
  }

  function abrirEditar(equipo: Equipo) {
    setEditando(equipo)
    setFormError(null)
    form.reset({
      cliente_id: String(equipo.cliente_id),
      tipo: equipo.tipo,
      marca: equipo.marca ?? '',
      modelo: equipo.modelo ?? '',
      serial: equipo.serial ?? '',
      ubicacion_oficina: equipo.ubicacion_oficina ?? '',
      sector: equipo.sector ?? '',
      deposito_id: equipo.deposito_id === null ? SIN_DEPOSITO : String(equipo.deposito_id),
      proveedor_id: equipo.proveedor_id === null ? DEL_CLIENTE : String(equipo.proveedor_id),
      estado: equipo.estado,
      garantia_vence: equipo.garantia_vence ?? '',
      observaciones: equipo.observaciones ?? '',
      motivo: '',
    })
    setDialogOpen(true)
  }

  async function handleSubmit(values: EquipoFormValues) {
    setSaving(true)
    setFormError(null)
    const payload = {
      cliente_id: Number(values.cliente_id),
      tipo: values.tipo,
      marca: values.marca || null,
      modelo: values.modelo || null,
      serial: values.serial || null,
      ubicacion_oficina: values.ubicacion_oficina || null,
      sector: values.sector || null,
      deposito_id: !values.deposito_id || values.deposito_id === SIN_DEPOSITO
        ? null
        : Number(values.deposito_id),
      estado: values.estado,
      // 🔴 Va en el payload aunque el formulario no lo toque casi nunca: el PUT
      // manda el equipo entero, así que una clave ausente llega como `null` y
      // **cada edición borraría el dueño tercero**. Es exactamente lo que le
      // pasó a `garantia_vence` — ver el comentario de acá abajo.
      proveedor_id: !values.proveedor_id || values.proveedor_id === DEL_CLIENTE
        ? null
        : Number(values.proveedor_id),
      observaciones: values.observaciones || null,
      // Antes iba `null` fijo porque el formulario no tenía el campo: cada
      // edición borraba la garantía del equipo y lo sacaba del reporte de
      // Garantías sin que nadie lo notara.
      garantia_vence: values.garantia_vence || null,
    }
    try {
      if (editando === null) {
        await api.post('/api/equipos', payload)
      } else {
        await api.put(`/api/equipos/${editando.id}`, { ...payload, motivo: values.motivo || null })
      }
      setDialogOpen(false)
      // Solo los equipos: la lista de clientes no cambió, y recargarla
      // apagaría la tabla un instante y con ella la búsqueda escrita.
      await loadEquipos()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(equipo: Equipo) {
    setError(null)
    try {
      await api.del(`/api/equipos/${equipo.id}`)
      await loadEquipos()
    } catch (err) {
      setError(describeError(err))
    }
  }

  const columns = useMemo<ColumnDef<Equipo>[]>(() => {
    const base: ColumnDef<Equipo>[] = [
      { accessorKey: 'tipo', header: sortableHeader('Tipo'), size: 140, minSize: 100, meta: { stretch: true }, cell: ({ row }) => <span className="font-medium">{row.original.tipo}</span> },
      { accessorKey: 'cliente_id', header: 'Cliente', size: 160, minSize: 120, cell: ({ row }) => clienteNombre(row.original.cliente_id) },
      // --- por qué tres columnas se esconden -------------------------------
      //
      // `DataTable` fija el `minWidth` de la tabla como la suma de los `size`
      // declarados, así que la lista pedía scroll horizontal en cualquier
      // pantalla normal: las ocho columnas suman 1110 px y la de acciones mide
      // 212 (cinco botones de 36 + cuatro gaps de 4 + 16 de padding), o sea
      // 1322 px de mínimo. Con la sidebar abierta el contenido es la ventana
      // menos 352 px (medido, ver `Cuotas.tsx`), así que hacía falta una
      // pantalla de 1674 px para que no scrolleara. En 1366, 1440 y 1536
      // scrolleaba siempre.
      //
      // `opcional` saca la columna del `minWidth` además de ocultarla — sin
      // eso la tabla sigue pidiendo scroll por una columna que ni se ve.
      // Quedan las seis que contestan para qué se entra acá (cuál es, de quién
      // es, dónde está y cómo está): 140+160+130+160+120+212 = 922, o sea
      // 1274 px de ventana. Las otras tres van apareciendo a medida que entran:
      //
      //   Marca      +120 → 1042 → aparece en 1400
      //   Modelo     +150 → 1192 → aparece en 1550
      //   N° ajeno   +130 → 1322 → aparece en 1680
      //
      // Ninguna se pierde: las cuatro —marca, modelo, serial y el número
      // ajeno— siguen entrando por el buscador de arriba, que es como se las
      // usa de verdad ("me dicen que es la 4471").
      {
        accessorKey: 'marca', header: 'Marca', size: 120, minSize: 90,
        meta: {
          opcional: true,
          className: 'hidden min-[1400px]:table-cell',
          // ⚠️ Un `<col>` NO puede llevar `table-cell` —lo convierte en
          //    celda anónima y descoloca el colgroup entero—: va
          //    `table-column`. Ver `Cuotas.tsx`.
          colClassName: 'hidden min-[1400px]:table-column',
        },
        cell: ({ row }) => row.original.marca ?? '—',
      },
      {
        accessorKey: 'modelo', header: 'Modelo', size: 150, minSize: 100,
        meta: {
          opcional: true,
          className: 'hidden min-[1550px]:table-cell',
          // ⚠️ Un `<col>` NO puede llevar `table-cell` —lo convierte en
          //    celda anónima y descoloca el colgroup entero—: va
          //    `table-column`. Ver `Cuotas.tsx`.
          colClassName: 'hidden min-[1550px]:table-column',
        },
        cell: ({ row }) => row.original.modelo ?? '—',
      },
      { accessorKey: 'serial', header: 'Serial', size: 130, minSize: 100, cell: ({ row }) => row.original.serial ?? '—' },
      {
        id: 'referencias',
        header: 'N° ajeno',
        size: 130,
        minSize: 100,
        meta: {
          opcional: true,
          className: 'hidden min-[1680px]:table-cell',
          // ⚠️ Un `<col>` NO puede llevar `table-cell` —lo convierte en
          //    celda anónima y descoloca el colgroup entero—: va
          //    `table-column`. Ver `Cuotas.tsx`.
          colClassName: 'hidden min-[1680px]:table-column',
        },
        // El número con el que lo llama el tercero, en la lista y no sólo en la
        // ficha: es el dato que se viene a buscar acá cuando hay que pedirle un
        // insumo, y detrás de un click deja de contestarse de un vistazo.
        cell: ({ row }) => {
          const refs = row.original.referencias
          if (refs.length === 0) return '—'
          return (
            <span className="flex flex-wrap gap-1">
              {refs.map((r) => (
                <Badge key={r.id} variant="outline" title={r.proveedor_nombre ?? r.etiqueta}>
                  {r.valor}
                </Badge>
              ))}
            </span>
          )
        },
      },
      {
        id: 'lugar',
        header: 'Dónde está',
        size: 160,
        minSize: 110,
        // Depósito o sector, nunca los dos: un equipo guardado en el taller no
        // está en ningún sector del cliente. Ver `lugarDe`.
        cell: ({ row }) => {
          const e = row.original
          return (
            <span className="flex items-center gap-1.5">
              {ubicacionTexto(lugarDe(e.deposito_nombre, e.sector), e.ubicacion_oficina)}
              {e.deposito_nombre && <Badge variant="secondary">Depósito</Badge>}
            </span>
          )
        },
      },
      {
        accessorKey: 'estado',
        header: 'Estado',
        size: 120,
        minSize: 90,
        cell: ({ row }) => (
          <BadgeEstado tono={row.original.estado === 'activo' ? 'ok' : 'neutro'}>
            {ESTADO_EQUIPO_LABELS[row.original.estado] ?? row.original.estado}
          </BadgeEstado>
        ),
      },
    ]
    // Sin gate de rol: `equipos.router` se monta con `staff_or_admin` (ver
    // `app/main.py`), así que el alta, la edición y la baja las puede hacer
    // cualquier usuario logueado. Estaban detrás de `role === 'admin'`, y eso
    // dejaba a la recepcionista —que es quien carga el equipo cuando entra por
    // el mostrador— sin ningún botón: la pantalla se veía como una lista de
    // sólo lectura aunque la API le aceptara el POST. Quien decide es el
    // backend, como en el resto de las pantallas del producto.
    base.push({
      id: 'actions',
      header: () => <div className="text-right">Acciones</div>,
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          <Button size="icon" variant="outline" title="Ver ficha del equipo" aria-label="Ver ficha del equipo" onClick={() => navigate(`/equipos/${row.original.id}`)}><Eye /></Button>
          {/* `Tags` y no un icono nuevo: son las etiquetas con las que otros
              nombran al equipo, que es lo que ese dibujo ya significa en el
              vocabulario. Ver `components/iconos-accion.tsx`. */}
          <Button size="icon" variant="outline" title="Identificadores del equipo" aria-label="Identificadores del equipo" onClick={() => setConReferencias(row.original)}><Tags /></Button>
          {/* Mover va ANTES de editar y no adentro: sacar un equipo del
              depósito para instalarlo es un gesto propio, no la corrección de
              una ficha, y por el formulario completo se hacía cambiando dos
              campos que ahí no se ven relacionados. */}
          <Button size="icon" variant="outline" title="Mover equipo" aria-label="Mover equipo" onClick={() => setAMover(row.original)}><ArrowLeftRight /></Button>
          <Button size="icon" variant="outline" title="Editar equipo" aria-label="Editar equipo" onClick={() => abrirEditar(row.original)}><Pencil /></Button>
          <Button size="icon" variant="outline" className="text-destructive hover:text-destructive" title="Eliminar equipo" aria-label="Eliminar equipo" onClick={() => setABorrar(row.original)}><Trash2 /></Button>
        </div>
      ),
    })
    return base
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientes])

  return (
    <div className="grid gap-4">
      <EncabezadoDePantalla titulo={<TituloPantalla icono={Monitor}>Equipos</TituloPantalla>}>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button onClick={abrirNuevo}><FilePlus />Nuevo equipo</Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-2xl">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <Monitor className="size-4" />
                  {editando === null ? 'Nuevo equipo' : `Editar equipo — ${describirEquipo(editando)}`}
                </DialogTitle>
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
                        className="w-48"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="tipo" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Tipo</FormLabel>
                    <FormControl><Input {...field} className="w-36" placeholder="Notebook, impresora…" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="marca" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Marca</FormLabel>
                    <FormControl><Input {...field} className="w-32" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="modelo" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Modelo</FormLabel>
                    <FormControl><Input {...field} className="w-36" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="serial" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Serial</FormLabel>
                    <FormControl><Input {...field} className="w-32" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                {/* Texto libre CON sugerencias, no un select: el campo tiene
                    que seguir aceptando cualquier cosa —es como funcionó
                    siempre y hay instancias que no cargan sectores—, y a la vez
                    ofrecer los que el cliente ya tiene para que el mismo lugar
                    no termine escrito de tres formas. El `<datalist>` hace
                    exactamente eso y no cambia nada para quien no lo use. */}
                <FormField control={form.control} name="sector" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Sector</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        list="sectores-del-cliente"
                        className="w-36"
                        placeholder="Admisión, Guardia…"
                      />
                    </FormControl>
                    <datalist id="sectores-del-cliente">
                      {sectores.map((s) => <option key={s.id} value={s.nombre} />)}
                    </datalist>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="ubicacion_oficina" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Ubicación</FormLabel>
                    <FormControl><Input {...field} className="w-36" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                {/* Guardar el equipo en un depósito reemplaza al sector como
                    ubicación efectiva; el sector queda como de dónde salió.
                    Sólo se ofrecen los propios y los del cliente elegido: el
                    backend rechaza el resto (ver `_validar_deposito`). */}
                <FormField control={form.control} name="deposito_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Depósito</FormLabel>
                    <FormControl>
                      <SelectBuscable
                        value={field.value || SIN_DEPOSITO}
                        onChange={field.onChange}
                        opciones={[
                          { value: SIN_DEPOSITO, label: 'Ninguno (en el puesto)' },
                          ...opcionesDeposito(depositosElegibles),
                        ]}
                        ariaLabel="Depósito"
                        className="w-52"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                {/* De quién es el equipo cuando no es del cliente: el tercero
                    que se lo alquila y que suele proveerle los insumos. Con
                    esto cargado, pedir un tóner ya sabe a quién pedírselo. */}
                <FormField control={form.control} name="proveedor_id" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Es de un tercero</FormLabel>
                    <FormControl>
                      <SelectBuscable
                        value={field.value || DEL_CLIENTE}
                        onChange={field.onChange}
                        opciones={[
                          { value: DEL_CLIENTE, label: 'No, es del cliente' },
                          ...opcionesProveedor(proveedores),
                        ]}
                        ariaLabel="Es de un tercero"
                        className="w-52"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="garantia_vence" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Garantía vence</FormLabel>
                    <FormControl><Input type="date" {...field} className="w-40" /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
                <FormField control={form.control} name="estado" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Estado</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="w-40">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {ESTADOS_EQUIPO.map((e) => <SelectItem key={e} value={e}>{ESTADO_EQUIPO_LABELS[e]}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )} />
                {editando !== null && (
                  <FormField control={form.control} name="motivo" render={({ field }) => (
                    <FormItem>
                      <FormLabel>Motivo del movimiento</FormLabel>
                      <FormControl>
                        <Input {...field} className="w-56" placeholder="Si cambia sector o estado" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )} />
                )}
                <DialogFooter className="w-full">
                  <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
                  <Button type="submit" disabled={saving}>
                    {saving ? 'Guardando…' : editando === null ? 'Crear equipo' : 'Guardar'}
                  </Button>
                </DialogFooter>
              </form>
            </Form>
            </DialogContent>
          </Dialog>
      </EncabezadoDePantalla>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex flex-wrap items-end gap-3">
        <div className="grid gap-2">
          <span className="text-xs text-muted-foreground">Cliente</span>
          <SelectBuscable
            value={filtroCliente}
            onChange={setFiltroCliente}
            opciones={[{ value: TODOS, label: 'Todos' }, ...opcionesCliente(clientes)]}
            ariaLabel="Filtrar por cliente"
            className="w-56"
          />
        </div>
        {filtroCliente !== TODOS && (
          <Button variant="ghost" size="sm" onClick={() => setFiltroCliente(TODOS)}>
            Limpiar filtro
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
              data={equipos}
              emptyMessage={filtroCliente === TODOS
                ? 'Sin equipos todavía.'
                : 'Este cliente no tiene equipos cargados.'}
              onRowClick={(e) => navigate(`/equipos/${e.id}`)}
              search={{
                campos: (e) => [
                  e.tipo, e.marca, e.modelo, e.serial,
                  e.sector, e.deposito_nombre, e.ubicacion_oficina,
                  clienteNombre(e.cliente_id),
                  // El número ajeno entra al buscador: tipear "4471" tiene que
                  // encontrar la máquina, que es el gesto que motivó todo esto.
                  ...e.referencias.map((r) => r.valor),
                  e.proveedor_nombre,
                ],
                placeholder: 'Buscar por tipo, marca, modelo, serial, N° interno, depósito, sector o cliente',
              }}
            />
          )}
        </CardContent>
      </Card>

      <MoverEquipo
        equipo={aMover}
        onClose={() => setAMover(null)}
        // Sólo los equipos: mover no cambia la lista de clientes, y recargarla
        // apagaría la tabla un instante y con ella la búsqueda escrita (mismo
        // motivo que en `handleSubmit`).
        onMovido={loadEquipos}
      />

      <DialogoDeReferencias
        equipo={conReferencias}
        proveedores={proveedores}
        onClose={() => setConReferencias(null)}
        // Las referencias viajan DENTRO del equipo, así que la lista se
        // recarga: sin esto, la columna «N° ajeno» seguiría mostrando lo de
        // antes hasta que alguien cambie de filtro.
        onGuardado={loadEquipos}
      />

      <ConfirmDialog
        open={aBorrar !== null}
        onOpenChange={(open) => !open && setABorrar(null)}
        title={`¿Eliminar ${describirEquipo(aBorrar ?? undefined)}?`}
        // Describe lo que el repositorio hace de verdad: los `ondelete` de los
        // modelos no corren (el pragma está apagado), así que el borrado del
        // historial y la desasignación se hacen explícitos en el backend.
        description="Se borra también su historial de movimientos. Las incidencias que lo tengan asignado quedan sin equipo, no se borran. Esta acción no se puede deshacer."
        onConfirm={() => { const e = aBorrar; setABorrar(null); if (e) handleDelete(e) }}
      />
    </div>
  )
}
