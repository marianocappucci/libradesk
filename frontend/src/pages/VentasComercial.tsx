// Ventas, recibos y cuenta corriente.
//
// 🔑 **Acá no se emite ninguna factura.** El comprobante fiscal lo emite SOS
// Contador; una venta de LibraDesk es el comprobante interno —qué se vendió, a
// quién, a cuánto y cómo se cobró— y es lo que después se manda a facturar
// desde «Enviar a facturar».
//
// Por eso no hay tipo A/B/C, ni CAE, ni punto de venta fiscal en ninguna de
// estas pantallas. Si aparecen, algo se entendió mal.
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { Cifras, Pagina, Tabla, useDatos } from '@/components/comercial-ui'
import { DetalleEstado } from '@/components/comprobante-detalle'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useSucursal } from '@/components/sucursal'
import { fecha, pesos } from '@/lib/format'
import type { Cliente } from '../api'
import type { Producto } from './Productos'
import type { DepositoStock } from './Inventario'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { ClipboardList, Coins, Wallet } from 'lucide-react'
// `Eye` llegó de develop (el PDF del recibo se abre con un ojo, PR #127) y es
// una ACCIÓN, así que entra por el módulo de acciones como el resto.
import { ArrowLeft, Eye, FilePlus, Trash2 } from '@/components/iconos-accion'

type Venta = {
  id: number; numero: string; estado: string; fecha: string
  total: number; cliente: string; cliente_id: number | null
  en_cuenta_corriente: number
  /** El recibo vigente de esta venta, si ya se emitió. `null` = todavía no.
   *  Un recibo anulado no cuenta: la venta vuelve a estar pendiente. */
  recibo_id: number | null
}
/** Lo que devuelve `GET /api/ventas/{id}`: la venta con sus líneas y cobros.
 *
 * No trae `recibo_id` — el recibo se maneja desde la lista. Si algún día el
 * detalle tiene que ofrecerlo, se agrega al servicio, no se deriva acá. */
type VentaDetalleData = {
  id: number; numero: string; estado: string; fecha: string
  cliente: { id: number; nombre: string; cuit: string; domicilio: string } | null
  cliente_nombre: string
  notas: string | null
  items: { descripcion: string; cantidad: number; precio: number; subtotal: number }[]
  pagos: { medio: string; monto: number; referencia: string }[]
  subtotal: number; total: number
}
type Recibo = {
  id: number; numero: number; punto_venta: number; fecha: string
  cliente_razon: string; total: number; anulado: number; concepto: string
}
type ClienteSaldo = { cliente_id: number; nombre: string; saldo: number }
type MovimientoCC = {
  fecha: string; tipo: string; concepto: string; monto: number; referencia: string
}

const MEDIOS = [
  { valor: 'efectivo', label: 'Efectivo' },
  { valor: 'transferencia', label: 'Transferencia' },
  { valor: 'cheque', label: 'Cheque' },
  { valor: 'tarjeta', label: 'Tarjeta' },
  { valor: 'cuenta_corriente', label: 'Cuenta corriente' },
]

const medioLabel = (valor: string) =>
  MEDIOS.find((m) => m.valor === valor)?.label ?? valor

/** Los estados de `SaleStatus` de libracommerce, en castellano. */
const ESTADOS: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  draft: { label: 'Borrador', variant: 'outline' },
  confirmed: { label: 'Confirmada', variant: 'default' },
  cancelled: { label: 'Anulada', variant: 'destructive' },
  partially_returned: { label: 'Devuelta en parte', variant: 'secondary' },
  returned: { label: 'Devuelta', variant: 'secondary' },
}

// ── Ventas ─────────────────────────────────────────────────────────────────

export function Ventas() {
  const navigate = useNavigate()
  const { datos, error, cargando, conError } = useDatos<Venta[]>('/api/ventas', [])
  const { datos: clientes } = useDatos<Cliente[]>('/api/clientes', [])
  const { datos: productos } = useDatos<Producto[]>('/api/consumibles', [])
  const { datos: depositos } = useDatos<DepositoStock[]>('/api/depositos-stock', [])

  if (cargando) return <p className="text-sm text-muted-foreground">Cargando…</p>

  return (
    <Pagina titulo="Ventas" icono={ClipboardList} error={error}
            acciones={<FormVenta clientes={clientes} productos={productos}
                                 depositos={depositos} onGuardar={conError} />}>
      <p className="text-sm text-muted-foreground">
        Comprobante interno. La factura la emite SOS Contador desde{' '}
        <strong>Enviar a facturar</strong>.
      </p>
      <Tabla<Venta>
        vacio="Todavía no hay ventas registradas."
        filas={datos}
        // La fila entera abre la venta. Es lo que la persona quiere hacer nueve
        // de cada diez veces, y hasta ahora esta pantalla no tenía **ninguna**
        // forma de ver una venta: la única columna de acciones era la del
        // recibo, disfrazada de acción de la venta porque no tenía encabezado.
        //
        // El clic sobre los controles de la fila NO navega — la guarda está en
        // `Tabla`, para que no haya que acordarse pantalla por pantalla.
        onFila={(v) => navigate(`/ventas/${v.id}`)}
        columnas={[
          { clave: 'numero', titulo: 'Número', ancho: '130px',
            render: (v) => <span className="tabular-nums">{v.numero}</span> },
          { clave: 'fecha', titulo: 'Fecha', ancho: '110px', render: (v) => fecha(v.fecha) },
          { clave: 'cliente', titulo: 'Cliente', render: (v) => v.cliente },
          { clave: 'cc', titulo: 'En cta. cte.', ancho: '130px', alinear: 'derecha',
            render: (v) => v.en_cuenta_corriente > 0
              ? <Badge variant="outline">{pesos(v.en_cuenta_corriente)}</Badge>
              : <span className="text-muted-foreground">—</span> },
          { clave: 'total', titulo: 'Total', ancho: '130px', alinear: 'derecha',
            render: (v) => pesos(v.total) },
          // El recibo es una columna con nombre, no una acción sin rótulo. Es
          // un objeto propio con dos estados —emitido o no— y mezclarlo con las
          // acciones de la venta hacía que el ojo del recibo se leyera como
          // «ver la venta». Mismo criterio que la columna «Factura» de las
          // ventas de Contalibra y Restolibra.
          //
          // 🔴 La primera versión era un botón «Recibo» que hacía el POST y
          // nada más: emitía un comprobante **en silencio** y no mostraba
          // nada. Quien lo tocaba no sabía si había pasado algo, y volver a
          // tocarlo parecía no hacer nada tampoco (el motor es idempotente y
          // devuelve el mismo recibo). Un botón que emite un comprobante
          // tiene que decir que lo emite, y después mostrarlo.
          { clave: 'recibo', titulo: 'Recibo', ancho: '150px',
            render: (v) => <AccionRecibo venta={v} onEmitido={conError} /> },
          // El ojo hace lo mismo que el clic en la fila, y se queda igual: un
          // `<tr>` clickeable no recibe foco ni se puede activar con el
          // teclado. Sin este enlace, la pantalla sería inoperable sin mouse.
          { clave: 'acciones', titulo: 'Acciones', ancho: '90px', alinear: 'derecha',
            render: (v) => (
              <Button asChild variant="outline" size="icon-sm">
                <Link to={`/ventas/${v.id}`} title="Ver la venta"
                      aria-label={`Ver la venta ${v.numero}`}>
                  <Eye />
                </Link>
              </Button>
            ) },
        ]}
      />
    </Pagina>
  )
}

/** «Ver recibo» si ya está emitido; «Emitir recibo» si todavía no.
 *
 * Las dos ramas terminan **abriendo el PDF**, que es lo que la persona quiere:
 * el comprobante para entregar o mandar. Emitir sin mostrar es la mitad de la
 * operación, y es lo que hacía la primera versión.
 *
 * El PDF se abre por navegación directa (`<a target="_blank">`) y no con
 * `window.open()`: es una descarga con cookie de sesión, y `window.open`
 * depende de que el navegador permita popups. Mismo patrón que Remitos.
 *
 * ⚠️ En la rama de emitir hay que abrir la pestaña **después** de que el POST
 * conteste, porque recién ahí se conoce el id. Eso puede activar el bloqueo de
 * popups —la apertura ya no cuelga del click—, así que si falla se muestra el
 * recibo emitido como enlace en vez de dejar a la persona sin nada.
 */
function AccionRecibo({ venta, onEmitido }: {
  venta: Venta
  onEmitido: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const [emitiendo, setEmitiendo] = useState(false)
  const [reciénEmitido, setReciénEmitido] = useState<number | null>(null)

  const id = venta.recibo_id ?? reciénEmitido
  if (id) {
    // Ya emitido: sólo se muestra, así que alcanza el ícono. **La rama de
    // emitir de acá abajo conserva su texto a propósito** — crea un
    // comprobante, y un botón que emite tiene que decir que emite (ver el
    // comentario de la columna en `Ventas`).
    return (
      <Button asChild variant="outline" size="icon-sm">
        <a href={`/api/recibos/${id}/pdf`} target="_blank" rel="noreferrer"
           title="Ver el PDF del recibo"
           aria-label={`Ver el recibo de la venta ${venta.numero}`}>
          <Eye />
        </a>
      </Button>
    )
  }

  async function emitir() {
    setEmitiendo(true)
    let emitido: number | null = null
    const ok = await onEmitido(async () => {
      const r = await api.post<{ id: number }>(`/api/ventas/${venta.id}/recibo`)
      emitido = r.id
    })
    setEmitiendo(false)
    if (ok && emitido) {
      setReciénEmitido(emitido)
      window.open(`/api/recibos/${emitido}/pdf`, '_blank', 'noreferrer')
    }
  }

  return (
    <Button variant="ghost" size="sm" onClick={emitir} disabled={emitiendo}>
      {emitiendo ? 'Emitiendo…' : 'Emitir recibo'}
    </Button>
  )
}

function FormVenta({ clientes, productos, depositos, onGuardar }: {
  clientes: Cliente[]; productos: Producto[]; depositos: DepositoStock[]
  onGuardar: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const { activa } = useSucursal()
  const [abierto, setAbierto] = useState(false)
  const [clienteId, setClienteId] = useState('')
  const [depositoId, setDepositoId] = useState('')
  const [medio, setMedio] = useState('efectivo')
  const [productoId, setProductoId] = useState('')
  const [lineas, setLineas] = useState<
    { item_id: number | null; descripcion: string; cantidad: string; precio: string }[]
  >([])

  const total = lineas.reduce(
    (acc, l) => acc + (Number(l.cantidad) || 0) * (Number(l.precio) || 0), 0,
  )

  function agregar() {
    const p = productos.find((x) => x.id === Number(productoId))
    if (!p) return
    setLineas([...lineas, {
      item_id: p.id, descripcion: p.nombre, cantidad: '1',
      precio: String(p.precio || p.costo || 0),
    }])
    setProductoId('')
  }

  function agregarServicio() {
    // Una línea sin `item_id` es un servicio: se cobra y no mueve stock. Es
    // como el motor distingue producto de servicio, y en una mesa de ayuda la
    // mano de obra es la mitad de lo que se factura.
    setLineas([...lineas, { item_id: null, descripcion: '', cantidad: '1', precio: '' }])
  }

  async function guardar() {
    const ok = await onGuardar(() => api.post('/api/ventas', {
      cliente_id: clienteId ? Number(clienteId) : null,
      deposito_id: Number(depositoId),
      sucursal_id: activa?.id ?? null,
      items: lineas.map((l) => ({
        item_id: l.item_id, descripcion: l.descripcion,
        cantidad: Number(l.cantidad) || 0, precio: Number(l.precio) || 0,
      })),
      pagos: total > 0 ? [{ medio, monto: total }] : [],
    }))
    if (ok) { setAbierto(false); setLineas([]); setClienteId('') }
  }

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button><FilePlus className="mr-2 h-4 w-4" /> Nueva venta</Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader><DialogTitle>Nueva venta</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="v-cliente">Cliente</Label>
              <Select value={clienteId} onValueChange={setClienteId}>
                <SelectTrigger id="v-cliente"><SelectValue placeholder="Consumidor final" /></SelectTrigger>
                <SelectContent>
                  {clientes.filter((c) => c.activo).map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>{c.nombre}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="v-dep">Depósito</Label>
              <Select value={depositoId} onValueChange={setDepositoId}>
                <SelectTrigger id="v-dep"><SelectValue placeholder="Elegir…" /></SelectTrigger>
                <SelectContent>
                  {depositos.filter((d) => d.activo).map((d) => (
                    <SelectItem key={d.id} value={String(d.id)}>{d.nombre}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <Label>Ítems</Label>
            <div className="flex gap-2">
              <Select value={productoId} onValueChange={setProductoId}>
                <SelectTrigger><SelectValue placeholder="Elegir producto…" /></SelectTrigger>
                <SelectContent>
                  {productos.map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>
                      {p.nombre} · stock {p.stock}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button variant="outline" onClick={agregar} disabled={!productoId}>Agregar</Button>
              <Button variant="outline" onClick={agregarServicio}>Servicio</Button>
            </div>
            {lineas.map((l, i) => (
              <div key={i} className="flex items-center gap-2">
                {l.item_id === null ? (
                  <Input value={l.descripcion} className="flex-1" placeholder="Mano de obra…"
                         aria-label="Descripción"
                         onChange={(e) => setLineas(lineas.map((x, j) => j === i ? { ...x, descripcion: e.target.value } : x))} />
                ) : (
                  <span className="flex-1 truncate text-sm">{l.descripcion}</span>
                )}
                <Input type="number" value={l.cantidad} className="w-20" aria-label="Cantidad"
                       onChange={(e) => setLineas(lineas.map((x, j) => j === i ? { ...x, cantidad: e.target.value } : x))} />
                <Input type="number" value={l.precio} className="w-28" aria-label="Precio"
                       onChange={(e) => setLineas(lineas.map((x, j) => j === i ? { ...x, precio: e.target.value } : x))} />
                <Button variant="ghost" size="icon" aria-label="Quitar ítem"
                        onClick={() => setLineas(lineas.filter((_, j) => j !== i))}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>

          <div className="flex items-end justify-between gap-3">
            <div>
              <Label htmlFor="v-medio">Cómo se cobra</Label>
              <Select value={medio} onValueChange={setMedio}>
                <SelectTrigger id="v-medio" className="w-56"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {MEDIOS.map((m) => (
                    <SelectItem key={m.valor} value={m.valor}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <p className="text-lg font-semibold tabular-nums">{pesos(total)}</p>
          </div>
          {medio === 'cuenta_corriente' && !clienteId && (
            // Una venta en cuenta corriente sin cliente no tiene a quién
            // cargarle la deuda: quedaría cobrada y sin deudor.
            <p className="text-sm text-destructive">
              Una venta en cuenta corriente necesita un cliente.
            </p>
          )}
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancelar</Button></DialogClose>
          <Button onClick={guardar}
                  disabled={!depositoId || lineas.length === 0
                            || (medio === 'cuenta_corriente' && !clienteId)}>
            Registrar venta
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Detalle de una venta ───────────────────────────────────────────────────

/** La ficha de una venta: qué se vendió, a quién y cómo se cobró.
 *
 * El endpoint `GET /api/ventas/{id}` existía desde el principio y no lo llamaba
 * nadie: la lista no tenía forma de abrir una venta, así que la única manera de
 * ver qué contenía era el PDF del recibo — que no muestra las líneas.
 *
 * No reusa `ComprobanteDetalle` (Remitos, Presupuestos) a propósito: esa ficha
 * tiene IVA discriminado, botón de PDF y una ruta de vuelta por tipo, y una
 * venta no tiene nada de eso pero sí tiene cobros. Encajarla ahí obligaba a
 * volver opcional media ficha de dos pantallas que hoy andan.
 */
export function VentaDetalle() {
  const { id } = useParams<{ id: string }>()
  const { datos, error, cargando } = useDatos<VentaDetalleData | null>(
    `/api/ventas/${Number(id)}`, null,
  )

  if (cargando || error || !datos) return <DetalleEstado loading={cargando} error={error || null} />

  const estado = ESTADOS[datos.estado] ?? { label: datos.estado, variant: 'outline' as const }
  const cobrado = datos.pagos.reduce((acc, p) => acc + p.monto, 0)

  return (
    <Pagina
      titulo={`Venta ${datos.numero}`}
      icono={ClipboardList}
      acciones={
        <>
          <Badge variant={estado.variant}>{estado.label}</Badge>
          <Button asChild size="sm" variant="outline">
            <Link to="/ventas"><ArrowLeft />Volver</Link>
          </Button>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Cliente</CardTitle></CardHeader>
          <CardContent className="grid gap-1.5 text-sm">
            <p><span className="text-muted-foreground">Nombre:</span> {datos.cliente_nombre}</p>
            {datos.cliente?.cuit && (
              <p><span className="text-muted-foreground">CUIT / DNI:</span> {datos.cliente.cuit}</p>
            )}
            {datos.cliente?.domicilio && (
              <p><span className="text-muted-foreground">Domicilio:</span> {datos.cliente.domicilio}</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Datos de la venta</CardTitle></CardHeader>
          <CardContent className="grid gap-1.5 text-sm">
            <p><span className="text-muted-foreground">Número:</span>{' '}
              <span className="font-mono">{datos.numero}</span></p>
            <p><span className="text-muted-foreground">Fecha:</span> {fecha(datos.fecha)}</p>
            {datos.notas && (
              <p className="whitespace-pre-line">
                <span className="text-muted-foreground">Notas:</span> {datos.notas}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Tabla<VentaDetalleData['items'][number]>
        vacio="La venta no tiene líneas."
        filas={datos.items}
        columnas={[
          { clave: 'descripcion', titulo: 'Descripción', render: (i) => i.descripcion },
          { clave: 'cantidad', titulo: 'Cantidad', ancho: '110px', alinear: 'derecha',
            render: (i) => i.cantidad },
          { clave: 'precio', titulo: 'Precio unit.', ancho: '130px', alinear: 'derecha',
            render: (i) => pesos(i.precio) },
          { clave: 'subtotal', titulo: 'Importe', ancho: '130px', alinear: 'derecha',
            render: (i) => pesos(i.subtotal) },
        ]}
      />

      <div className="flex items-baseline justify-end gap-4 border-t pt-3">
        <span className="text-sm text-muted-foreground">Total</span>
        <span className="text-2xl font-semibold tabular-nums">{pesos(datos.total)}</span>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Cobros</CardTitle></CardHeader>
        <CardContent className="grid gap-1.5 text-sm">
          {datos.pagos.length === 0
            ? <p className="text-muted-foreground">Sin cobros registrados.</p>
            : datos.pagos.map((p, i) => (
              <p key={i} className="flex justify-between gap-4">
                <span>{medioLabel(p.medio)}{p.referencia && ` · ${p.referencia}`}</span>
                <span className="tabular-nums">{pesos(p.monto)}</span>
              </p>
            ))}
          {/* Lo cobrado contra el total: es la diferencia que explica por qué
              una venta figura en cuenta corriente, y verlo acá evita ir a
              buscarla a la pantalla de saldos. */}
          {cobrado !== datos.total && (
            <p className="flex justify-between gap-4 border-t pt-1.5 font-medium">
              <span>Pendiente</span>
              <span className="tabular-nums">{pesos(datos.total - cobrado)}</span>
            </p>
          )}
        </CardContent>
      </Card>
    </Pagina>
  )
}

// ── Recibos ────────────────────────────────────────────────────────────────

export function Recibos() {
  const { datos, error, cargando } = useDatos<Recibo[]>('/api/recibos', [])

  if (cargando) return <p className="text-sm text-muted-foreground">Cargando…</p>

  return (
    <Pagina titulo="Recibos" icono={Coins} error={error}>
      <p className="text-sm text-muted-foreground">
        El comprobante de que entró plata. Se emite desde una venta o desde un
        pago de cuenta corriente, y <strong>no se borra: se anula</strong>.
      </p>
      <Tabla<Recibo>
        vacio="Todavía no se emitieron recibos."
        filas={datos}
        columnas={[
          { clave: 'numero', titulo: 'Número', ancho: '130px',
            render: (r) => (
              <span className="tabular-nums">
                {String(r.punto_venta).padStart(4, '0')}-{String(r.numero).padStart(8, '0')}
              </span>
            ) },
          { clave: 'fecha', titulo: 'Fecha', ancho: '110px', render: (r) => fecha(r.fecha) },
          { clave: 'cliente', titulo: 'Cliente', render: (r) => r.cliente_razon },
          { clave: 'concepto', titulo: 'Concepto',
            render: (r) => <span className="text-muted-foreground">{r.concepto || '—'}</span> },
          { clave: 'estado', titulo: '', ancho: '90px',
            render: (r) => r.anulado ? <Badge variant="destructive">Anulado</Badge> : null },
          { clave: 'total', titulo: 'Total', ancho: '130px', alinear: 'derecha',
            render: (r) => pesos(r.total) },
          { clave: 'pdf', titulo: 'Acciones', ancho: '90px', alinear: 'derecha',
            // También en los anulados: el papel anulado sigue siendo el
            // documento de lo que pasó, y es lo que hay que poder mostrar si
            // alguien pregunta por qué se anuló.
            //
            // Va a la derecha como en todas las tablas del módulo. La
            // separación con la columna de importes la da el gutter de
            // `Tabla`, no un `pl-4` propio de esta pantalla.
            render: (r) => (
              <Button asChild variant="outline" size="icon-sm">
                {/* Sin texto, el botón necesita nombre accesible propio, y el
                    número lo hace distinguible entre filas. El `title` da la
                    misma información al pasar el mouse. */}
                <a href={`/api/recibos/${r.id}/pdf`} target="_blank" rel="noreferrer"
                   title="Ver el PDF del recibo"
                   aria-label={`Ver el recibo ${String(r.punto_venta).padStart(4, '0')}-${String(r.numero).padStart(8, '0')}`}>
                  <Eye />
                </a>
              </Button>
            ) },
        ]}
      />
    </Pagina>
  )
}

// ── Cuenta corriente ───────────────────────────────────────────────────────

export function CuentaCorriente() {
  const { datos, error, cargando, conError } = useDatos<{
    resumen: { clientes_con_saldo: number; total_adeudado: number; saldo_mayor: number }
    clientes: ClienteSaldo[]
  }>('/api/cuenta-corriente', {
    resumen: { clientes_con_saldo: 0, total_adeudado: 0, saldo_mayor: 0 }, clientes: [],
  })
  const [abierto, setAbierto] = useState<ClienteSaldo | null>(null)

  if (cargando) return <p className="text-sm text-muted-foreground">Cargando…</p>

  return (
    <Pagina titulo="Cuenta corriente" icono={Wallet} error={error}>
      <Cifras items={[
        { label: 'Clientes con saldo', valor: datos.resumen.clientes_con_saldo },
        { label: 'Total adeudado', valor: pesos(datos.resumen.total_adeudado) },
        { label: 'Saldo mayor', valor: pesos(datos.resumen.saldo_mayor) },
      ]} />
      <Tabla<ClienteSaldo>
        vacio="Ningún cliente tiene saldo pendiente."
        filas={datos.clientes}
        onFila={setAbierto}
        columnas={[
          { clave: 'nombre', titulo: 'Cliente', render: (c) => c.nombre },
          { clave: 'saldo', titulo: 'Saldo', ancho: '150px', alinear: 'derecha',
            render: (c) => (
              <span className={c.saldo > 0 ? 'font-semibold text-destructive' : ''}>
                {pesos(c.saldo)}
              </span>
            ) },
        ]}
      />
      {abierto && (
        <DetalleCuenta cliente={abierto} onCerrar={() => setAbierto(null)}
                       onCambio={conError} />
      )}
    </Pagina>
  )
}

function DetalleCuenta({ cliente, onCerrar, onCambio }: {
  cliente: ClienteSaldo
  onCerrar: () => void
  onCambio: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const { datos, recargar } = useDatos<{ saldo: number; movimientos: MovimientoCC[] }>(
    `/api/cuenta-corriente/${cliente.cliente_id}`, { saldo: 0, movimientos: [] },
  )
  const [monto, setMonto] = useState('')

  async function cobrar() {
    const ok = await onCambio(() => api.post('/api/cuenta-corriente/pagos', {
      cliente_id: cliente.cliente_id, monto: Number(monto),
      fecha: new Date().toISOString().slice(0, 10), concepto: 'Pago a cuenta',
    }))
    if (ok) { setMonto(''); await recargar() }
  }

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onCerrar() }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader><DialogTitle>{cliente.nombre}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <p className="text-sm">
            Saldo: <span className="text-lg font-semibold tabular-nums">{pesos(datos.saldo)}</span>
          </p>
          <div className="max-h-72 overflow-y-auto">
            <Tabla<MovimientoCC>
              vacio="Sin movimientos."
              filas={datos.movimientos}
              columnas={[
                { clave: 'fecha', titulo: 'Fecha', ancho: '110px',
                  render: (m) => fecha(m.fecha) },
                { clave: 'concepto', titulo: 'Concepto', render: (m) => m.concepto },
                { clave: 'monto', titulo: 'Monto', ancho: '130px', alinear: 'derecha',
                  render: (m) => (
                    <span className={m.tipo === 'debito' ? '' : 'text-emerald-600'}>
                      {m.tipo === 'debito' ? '' : '−'}{pesos(m.monto)}
                    </span>
                  ) },
              ]}
            />
          </div>
          <div className="flex items-end gap-2 rounded-md border bg-muted/40 p-3">
            <div>
              <Label htmlFor="cc-monto">Registrar cobro</Label>
              <Input id="cc-monto" type="number" value={monto} className="w-36"
                     onChange={(e) => setMonto(e.target.value)} />
            </div>
            <Button onClick={cobrar} disabled={!monto || Number(monto) <= 0}>Cobrar</Button>
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cerrar</Button></DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
