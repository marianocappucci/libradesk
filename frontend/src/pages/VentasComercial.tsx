// Ventas, recibos y cuenta corriente.
//
// 🔑 **Acá no se emite ninguna factura.** El comprobante fiscal lo emite SOS
// Contador; una venta de LibraDesk es el comprobante interno —qué se vendió, a
// quién, a cuánto y cómo se cobró—.
//
// ⚠️ **Una venta NO va sola a «Enviar a facturar»**: la bandeja acepta sólo
// remitos. El camino es generar el remito de la venta (el botón de la ficha) y
// mandar ese. Hasta el 2026-08-16 este comentario y el texto de la pantalla
// decían que la venta se mandaba directo, y era falso — no existía ningún
// camino de una venta a la bandeja.
//
// Por eso no hay tipo A/B/C, ni CAE, ni punto de venta fiscal en ninguna de
// estas pantallas. Si aparecen, algo se entendió mal.
import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { Cifras, Pagina, Tabla, useDatos } from '@/components/comercial-ui'
import { DetalleEstado } from '@/components/comprobante-detalle'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useSucursal, useSucursalUrl } from '@/components/sucursal'
import { fecha, pesos } from '@/lib/format'
import type { Cliente } from '../api'
import type { Producto } from './Productos'
import type { DepositoStock } from './Inventario'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { BadgeEstado, type TonoEstado } from 'libra-ui/badge-estado'
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
import { hoyISO } from 'libra-ui/fechas'

type Venta = {
  id: number; numero: string; estado: string; fecha: string
  total: number; cliente: string; cliente_id: number | null
  en_cuenta_corriente: number
  /** El recibo vigente de esta venta, si ya se emitió. `null` = todavía no.
   *  Un recibo anulado no cuenta: la venta vuelve a estar pendiente. */
  recibo_id: number | null
}
/** Lo que devuelve `GET /api/ventas/{id}`: la venta con sus líneas y cobros. */
type VentaDetalleData = {
  id: number; numero: string; estado: string; fecha: string
  cliente: { id: number; nombre: string; cuit: string; domicilio: string } | null
  cliente_nombre: string
  notas: string | null
  /** Mismo dato y misma regla que el de la lista: lo calcula el servicio, en un
   *  solo lugar. Derivarlo en la pantalla es cómo la ficha y la lista terminan
   *  diciendo cosas distintas de la misma venta. */
  recibo_id: number | null
  /** El remito que ya salió por esta venta, o `null`. Es lo que hace que el
   *  botón diga «Ver remito» en vez de generar un segundo comprobante. */
  remito_id: number | null
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

// 🔴 Acá había un `MEDIOS` escrito a mano, espejo de la tupla del backend
// (`services/ventas.MEDIOS_PAGO`). Las dos divergían de la lista canónica de la
// familia en las dos direcciones: tenían `tarjeta` —que ya no se escribe, se
// parte en débito y crédito como lo declara ARCA— y les faltaban `mercadopago`,
// `cuenta_dni` y `billetera`, o sea que este producto no podía registrar un
// cobro por MercadoPago aunque el resto de la casa sí.
//
// Ahora sale de `GET /api/medios-pago`, que la sirve `libracore.medios_pago`.
// Ver `wiki/concepts/medios-de-pago-familia-libra.md`.

type MedioPago = { id: string; label: string }

/** Cache de módulo: la lista es de constantes del motor y no cambia mientras la
 *  pestaña esté abierta. */
let cacheMedios: MedioPago[] | null = null

function useMediosPago() {
  const [medios, setMedios] = useState<MedioPago[]>(cacheMedios ?? [])
  useEffect(() => {
    if (cacheMedios) return
    api.get<MedioPago[]>('/api/medios-pago')
      .then((ms) => {
        // Se comprueba la forma, no se confía en ella: un cuerpo truncado o el
        // HTML del catch-all es truthy, y el `.map()` de abajo tumbaría el
        // formulario entero con un TypeError.
        cacheMedios = Array.isArray(ms) ? ms : []
        setMedios(cacheMedios)
      })
      .catch(() => {})
  }, [])
  return medios
}

/** Cómo se muestra un medio. **Nunca vacío**: uno que el motor no nombró sale
 *  con su slug crudo, que es la única forma de enterarse de que existe. Cubre
 *  las ventas viejas con `tarjeta`, que se leen aunque ya no se escriban. */
const medioLabel = (valor: string, medios: MedioPago[]) =>
  medios.find((m) => m.id === valor)?.label ?? ETIQUETA_HISTORICA[valor] ?? valor

/** Las grafías que el motor ya no ofrece pero están en ventas de antes. Espeja
 *  a `medios_pago.HISTORICOS`; sin esto la grilla muestra el slug. */
const ETIQUETA_HISTORICA: Record<string, string> = {
  tarjeta: 'Tarjeta',
  mercado_pago: 'Mercado Pago',
  debito: 'Tarjeta de débito',
  credito: 'Tarjeta de crédito',
}

/** Los estados de `SaleStatus` de libracommerce, en castellano. */
const ESTADOS: Record<string, { label: string; tono: TonoEstado }> = {
  draft: { label: 'Borrador', tono: 'neutro' },
  confirmed: { label: 'Confirmada', tono: 'ok' },
  cancelled: { label: 'Anulada', tono: 'negativo' },
  partially_returned: { label: 'Devuelta en parte', tono: 'atencion' },
  returned: { label: 'Devuelta', tono: 'atencion' },
}

// ── Ventas ─────────────────────────────────────────────────────────────────

export function Ventas() {
  const navigate = useNavigate()
  const conSucursal = useSucursalUrl()
  const { activa } = useSucursal()
  const { datos, error, cargando, conError } =
    useDatos<Venta[]>(conSucursal('/api/ventas'), [])
  // El aviso del alta de equipos llega en el **estado de la navegación**, no de
  // un `useState` de esta pantalla: desde el 2026-09-08 el formulario es una
  // pantalla propia (`VentaNueva`), así que quien tiene el dato es la vuelta a
  // esta lista. `?? 0` porque a `/ventas` se entra también desde el menú, sin
  // estado ninguno.
  const { state } = useLocation()
  const altaDeEquipos = (state as { altaDeEquipos?: number } | null)?.altaDeEquipos ?? 0

  if (cargando) return <p className="text-sm text-muted-foreground">Cargando…</p>

  return (
    <Pagina titulo="Ventas" icono={ClipboardList} error={error}
            acciones={
              <Button onClick={() => navigate('/ventas/nueva')}>
                <FilePlus />Nueva venta
              </Button>
            }>
      {altaDeEquipos > 0 && (
        <p className="rounded-md border border-dashed p-3 text-sm">
          Se {altaDeEquipos === 1 ? 'registró' : 'registraron'}{' '}
          <strong>{altaDeEquipos} {altaDeEquipos === 1 ? 'equipo' : 'equipos'}</strong>{' '}
          en el parque del cliente. Cargales el número de serie cuando los
          instales.
        </p>
      )}
      <p className="text-sm text-muted-foreground">
        Comprobante interno. Para facturarla, abrí la venta y generá su{' '}
        <strong>remito</strong>: es lo que se manda desde{' '}
        <strong>Enviar a facturar</strong>.
        {activa && ` Se muestran las ventas de ${activa.nombre}.`}
      </p>
      {activa && (
        <p className="text-xs text-muted-foreground">
          La <strong>cuenta corriente no se filtra</strong>: el saldo de un
          cliente es uno solo entre sucursales.
        </p>
      )}
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
 *
 * Lo usan la lista y la ficha de la venta. Pide **los tres campos que mira**, no
 * una `Venta` entera: es lo que deja que las dos pantallas ofrezcan el recibo
 * con el mismo botón en vez de tener cada una el suyo, que es como una termina
 * diciendo «ver» y la otra «emitir» sobre la misma venta.
 */
function AccionRecibo({ venta, onEmitido }: {
  venta: { id: number; numero: string; recibo_id: number | null }
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

// ── Alta de una venta ──────────────────────────────────────────────────────

/** Una línea del formulario de alta.
 *
 * `item_id === null` es un **servicio**: se cobra y no mueve stock. Es como el
 * motor distingue producto de servicio, y en una mesa de ayuda la mano de obra
 * es la mitad de lo que se factura.
 *
 * `uid` es la key de la fila: estable por construcción, que es la forma
 * correcta de listar algo que se edita y se reordena. **No arregla ningún
 * defecto medido** — con la key por índice esta pantalla se comporta igual,
 * porque los campos son controlados y React repone el valor aunque reuse el
 * nodo de la fila de arriba. Está dicho así, y no como "corrige el foco",
 * porque se lo intentó probar y el test pasaba con las dos formas: ver
 * `test/venta-alta-en-pagina.test.tsx`.
 */
type LineaVenta = {
  uid: number
  item_id: number | null
  descripcion: string
  cantidad: string
  precio: string
}

/** Contador de módulo para las keys. No hace falta que sea único en el mundo:
 *  alcanza con que no se repita entre las líneas vivas de un formulario. */
let proximaLinea = 1

/** Alta de venta — **una pantalla, no un modal** (pedido del humano,
 *  2026-09-08):
 *
 *  > *"se abre una ventana modal para cargar la nueva venta cuando se tendría
 *  > que abrir la pantalla como cuando estamos generando un presupuesto, ya que
 *  > puede contener más de un ítem y en un modal es incómodo trabajar una
 *  > venta"*.
 *
 * Una venta no tiene un número fijo de campos: tiene tantas líneas como haga
 * falta, y cada una con descripción, cantidad y precio editables. En un diálogo
 * eso obliga a scrollear adentro de una caja que además tapa la lista de atrás.
 * Como pantalla las líneas entran en una tabla con encabezados y con el importe
 * de cada una, que es lo que el modal no podía mostrar.
 *
 * Es el mismo cambio que ya se hizo con el alta de contrato el 2026-08-17
 * (`ContratoNuevo`), y deja el alta de venta con la misma forma que el
 * formulario de presupuesto — que fue la referencia que dio el humano.
 *
 * 🔴 **La ruta va antes que `/ventas/:id`** en el router: `nueva` es un
 * segmento estático y no puede quedar interpretado como un id. Si lo capturara
 * la ficha, la pantalla pediría `/api/ventas/nueva` y el backend contestaría
 * 422.
 *
 * Al guardar vuelve a `/ventas` **con el número de equipos dados de alta en el
 * estado de la navegación**: ese aviso no puede vivir acá, porque esta pantalla
 * deja de existir en el mismo momento en que hay algo que avisar.
 */
export function VentaNueva() {
  const navigate = useNavigate()
  const { activa } = useSucursal()
  const { datos: clientes, error: errorClientes } =
    useDatos<Cliente[]>('/api/clientes', [])
  const { datos: productos, error: errorProductos } =
    useDatos<Producto[]>('/api/consumibles', [])
  // Sin filtrar: se puede vender descontando de un depósito de otra sucursal
  // —el central que abastece a las dos— y el selector muestra cuál es cuál.
  const { datos: depositos, error: errorDepositos } =
    useDatos<DepositoStock[]>('/api/depositos-stock', [])
  const medios = useMediosPago()

  const [clienteId, setClienteId] = useState('')
  const [depositoId, setDepositoId] = useState('')
  const [medio, setMedio] = useState('efectivo')
  const [productoId, setProductoId] = useState('')
  const [lineas, setLineas] = useState<LineaVenta[]>([])
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState('')

  const total = lineas.reduce(
    (acc, l) => acc + (Number(l.cantidad) || 0) * (Number(l.precio) || 0), 0,
  )

  function cambiar(uid: number, campo: 'descripcion' | 'cantidad' | 'precio', valor: string) {
    setLineas((ls) => ls.map((l) => l.uid === uid ? { ...l, [campo]: valor } : l))
  }

  async function agregar() {
    const p = productos.find((x) => x.id === Number(productoId))
    if (!p) return
    // 🔑 **El precio se le pide al backend, no se lee del catálogo.** Tiene que
    // ser el de la lista de ESTE cliente, que es el mismo con el que después
    // sale el comprobante. Resolverlo acá duplicaría la precedencia —operación
    // > cliente > defecto > catálogo— y es así como este producto ya terminó
    // con la misma regla escrita distinto en dos vistas.
    //
    // Si la consulta falla se usa el del catálogo: que no responda no puede
    // impedir cargar una venta, y el número queda editable igual.
    let precio = p.precio || p.costo || 0
    try {
      const q = new URLSearchParams({ item_id: String(p.id) })
      if (clienteId) q.set('cliente_id', clienteId)
      const r = await api.get<{ precio: number }>(`/api/precios/resolver?${q}`)
      precio = r.precio
    } catch { /* se usa el del catálogo */ }
    setLineas((ls) => [...ls, {
      uid: proximaLinea++, item_id: p.id, descripcion: p.nombre,
      cantidad: '1', precio: String(precio),
    }])
    setProductoId('')
  }

  function agregarServicio() {
    setLineas((ls) => [...ls, {
      uid: proximaLinea++, item_id: null, descripcion: '',
      cantidad: '1', precio: '',
    }])
  }

  // Una venta en cuenta corriente sin cliente no tiene a quién cargarle la
  // deuda: quedaría cobrada y sin deudor.
  const faltaDeudor = medio === 'cuenta_corriente' && !clienteId

  async function guardar() {
    setGuardando(true)
    setError('')
    try {
      const r = await api.post<{ equipos_dados_de_alta?: number }>('/api/ventas', {
        cliente_id: clienteId ? Number(clienteId) : null,
        deposito_id: Number(depositoId),
        sucursal_id: activa?.id ?? null,
        items: lineas.map((l) => ({
          item_id: l.item_id, descripcion: l.descripcion,
          cantidad: Number(l.cantidad) || 0, precio: Number(l.precio) || 0,
        })),
        pagos: total > 0 ? [{ medio, monto: total }] : [],
      })
      // Un alta automática que nadie ve es indistinguible de que no haya
      // pasado. El número viaja siempre; la lista lo muestra **sólo cuando hubo
      // algo**, para que un "0 equipos" no sea ruido en cada venta de
      // consumibles.
      navigate('/ventas', {
        state: { altaDeEquipos: r.equipos_dados_de_alta ?? 0 },
        replace: true,
      })
    } catch (e) {
      // Sin `setGuardando(false)` en el camino feliz: ahí la pantalla ya se
      // desmontó y el setter sería sobre un componente que no existe.
      setGuardando(false)
      setError(e instanceof ApiError ? e.detail : 'No se pudo registrar la venta.')
    }
  }

  return (
    <Pagina
      titulo="Nueva venta"
      icono={ClipboardList}
      error={[error, errorClientes, errorProductos, errorDepositos].find(Boolean) ?? ''}
      acciones={
        <>
          {/* La acción principal va arriba a la derecha, como en el alta de
              contrato: con el formulario largo, un botón al pie obliga a bajar
              hasta el final para confirmar algo que ya se terminó de cargar
              arriba. Y sin «Cancelar» al pie, que sería un segundo «Volver». */}
          <Button size="sm" variant="outline" onClick={() => navigate('/ventas')}>
            <ArrowLeft />Volver
          </Button>
          <Button onClick={() => void guardar()}
                  disabled={guardando || !depositoId || lineas.length === 0 || faltaDeudor}>
            {guardando ? 'Registrando…' : 'Registrar venta'}
          </Button>
        </>
      }
    >
      <p className="text-sm text-muted-foreground">
        Comprobante interno: qué se vendió, a quién, a cuánto y cómo se cobró.
        No emite factura — para eso, una vez registrada, generá su{' '}
        <strong>remito</strong> desde la ficha.
        {activa && ` Se registra en ${activa.nombre}.`}
      </p>

      <Card>
        <CardHeader><CardTitle className="text-base">Datos de la venta</CardTitle></CardHeader>
        <CardContent className="grid items-start gap-3 sm:grid-cols-2">
          <div className="grid gap-2">
            <Label htmlFor="v-cliente">Cliente</Label>
            <Select value={clienteId} onValueChange={setClienteId}>
              <SelectTrigger id="v-cliente"><SelectValue placeholder="Consumidor final" /></SelectTrigger>
              <SelectContent>
                {clientes.filter((c) => c.activo).map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>{c.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Sin cliente es una venta de mostrador. El precio de cada ítem sale
              de la lista del cliente elegido, así que conviene elegirlo antes de
              cargarlos.
            </p>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="v-dep">Depósito</Label>
            <Select value={depositoId} onValueChange={setDepositoId}>
              <SelectTrigger id="v-dep"><SelectValue placeholder="Elegir…" /></SelectTrigger>
              <SelectContent>
                {depositos.filter((d) => d.activo).map((d) => (
                  <SelectItem key={d.id} value={String(d.id)}>{d.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              De acá se descuenta el stock de los productos.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Ítems</CardTitle></CardHeader>
        <CardContent className="grid gap-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid min-w-64 flex-1 gap-2">
              <Label htmlFor="v-producto">Producto del catálogo</Label>
              <Select value={productoId} onValueChange={setProductoId}>
                <SelectTrigger id="v-producto">
                  <SelectValue placeholder="Elegir producto…" />
                </SelectTrigger>
                <SelectContent>
                  {productos.map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>
                      {p.nombre} · stock {p.stock}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button variant="outline" onClick={() => void agregar()} disabled={!productoId}>
              Agregar
            </Button>
            <Button variant="outline" onClick={agregarServicio}>Servicio</Button>
          </div>

          {lineas.length === 0 ? (
            <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
              Todavía no hay ítems. Agregá un producto del catálogo —descuenta
              stock— o un <strong>servicio</strong>, que se cobra y no lo mueve.
            </p>
          ) : (
            // La tabla escrita a mano y no con `Tabla`: esa rinde celdas de
            // sólo lectura y acá cada fila es un formulario. Los encabezados
            // son la mitad del pedido — en el modal las tres cajas de una línea
            // no tenían rótulo visible y había que adivinar cuál era el precio.
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="py-2 pr-4 text-left font-medium">Descripción</th>
                    <th className="w-24 py-2 pr-4 text-right font-medium">Cantidad</th>
                    <th className="w-36 py-2 pr-4 text-right font-medium">Precio unit.</th>
                    <th className="w-32 py-2 pr-4 text-right font-medium">Importe</th>
                    <th className="w-12 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {lineas.map((l) => (
                    <tr key={l.uid} className="border-b last:border-0">
                      <td className="py-2 pr-4">
                        {l.item_id === null ? (
                          <Input value={l.descripcion} placeholder="Mano de obra…"
                                 aria-label="Descripción"
                                 onChange={(e) => cambiar(l.uid, 'descripcion', e.target.value)} />
                        ) : (
                          <span className="block truncate">{l.descripcion}</span>
                        )}
                      </td>
                      <td className="py-2 pr-4">
                        <Input type="number" min="0" value={l.cantidad} className="text-right"
                               aria-label={`Cantidad de ${l.descripcion || 'la línea'}`}
                               onChange={(e) => cambiar(l.uid, 'cantidad', e.target.value)} />
                      </td>
                      <td className="py-2 pr-4">
                        <Input type="number" min="0" step="0.01" value={l.precio} className="text-right"
                               aria-label={`Precio de ${l.descripcion || 'la línea'}`}
                               onChange={(e) => cambiar(l.uid, 'precio', e.target.value)} />
                      </td>
                      {/* El importe de la línea. Es lo que deja controlar una
                          venta de ocho ítems sin sacar la calculadora, y no
                          existía en el modal. */}
                      <td className="py-2 pr-4 text-right tabular-nums">
                        {pesos((Number(l.cantidad) || 0) * (Number(l.precio) || 0))}
                      </td>
                      <td className="py-2 text-right">
                        <Button variant="ghost" size="icon"
                                aria-label={`Quitar ${l.descripcion || 'la línea'}`}
                                onClick={() => setLineas((ls) => ls.filter((x) => x.uid !== l.uid))}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Cobro</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap items-end justify-between gap-3">
          <div className="grid gap-2">
            <Label htmlFor="v-medio">Cómo se cobra</Label>
            <Select value={medio} onValueChange={setMedio}>
              <SelectTrigger id="v-medio" className="w-56"><SelectValue /></SelectTrigger>
              <SelectContent>
                {medios.map((m) => (
                  <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-baseline gap-4">
            <span className="text-sm text-muted-foreground">Total</span>
            <span className="text-2xl font-semibold tabular-nums">{pesos(total)}</span>
          </div>
          {faltaDeudor && (
            <p className="w-full text-sm text-destructive">
              Una venta en cuenta corriente necesita un cliente.
            </p>
          )}
        </CardContent>
      </Card>
    </Pagina>
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
/** «Generar remito» — el camino de una venta a facturación.
 *
 * La bandeja de «Enviar a facturar» acepta **sólo remitos**, así que sin esto
 * una venta no tiene ningún camino a la factura. Es el gemelo del botón de
 * conversión de un presupuesto y del de un reclamo cerrado.
 *
 * Tres estados, y el del medio es el que justifica el componente:
 *
 * - **Ya tiene remito** → lleva a verlo. No vuelve a emitir.
 * - **La venta no tiene cliente** (mostrador) → pide a nombre de quién, porque
 *   un remito se emite a nombre de alguien.
 * - **Todo listo** → genera y navega al remito.
 */
function AccionRemito({ venta, clientes, onGenerado }: {
  venta: VentaDetalleData
  clientes: Cliente[]
  onGenerado: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const navigate = useNavigate()
  const [generando, setGenerando] = useState(false)
  const [abierto, setAbierto] = useState(false)
  const [elegido, setElegido] = useState('')

  if (venta.remito_id) {
    return (
      <Button asChild size="sm" variant="outline">
        <Link to={`/remitos/${venta.remito_id}`}>
          <Eye />Ver remito
        </Link>
      </Button>
    )
  }

  async function generar(clienteId?: number) {
    setGenerando(true)
    let creado: number | null = null
    const ok = await onGenerado(async () => {
      const r = await api.post<{ id: number }>(
        `/api/ventas/${venta.id}/convertir-en-remito`,
        clienteId ? { cliente_id: clienteId } : {},
      )
      creado = r.id
    })
    setGenerando(false)
    if (ok && creado) navigate(`/remitos/${creado}`)
  }

  // Con cliente en la venta no hay nada que preguntar.
  if (venta.cliente) {
    return (
      <Button size="sm" disabled={generando} onClick={() => generar()}>
        <FilePlus />{generando ? 'Generando…' : 'Generar remito'}
      </Button>
    )
  }

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button size="sm"><FilePlus />Generar remito</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>¿A nombre de quién?</DialogTitle></DialogHeader>
        <p className="text-sm text-muted-foreground">
          Esta venta se cargó sin cliente y un remito se emite a nombre de
          alguien. Elegí a quién antes de generarlo.
        </p>
        <div className="grid gap-2">
          <Label htmlFor="cliente-remito">Cliente</Label>
          <Select value={elegido} onValueChange={setElegido}>
            <SelectTrigger id="cliente-remito">
              <SelectValue placeholder="Elegí un cliente" />
            </SelectTrigger>
            <SelectContent>
              {clientes.map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>
                  {c.empresa || c.nombre}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" size="sm">Cancelar</Button>
          </DialogClose>
          <Button
            size="sm"
            disabled={!elegido || generando}
            onClick={async () => {
              await generar(Number(elegido))
              setAbierto(false)
            }}
          >
            {generando ? 'Generando…' : 'Generar remito'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function VentaDetalle() {
  const { id } = useParams<{ id: string }>()
  const medios = useMediosPago()
  const { datos, error, cargando, conError } = useDatos<VentaDetalleData | null>(
    `/api/ventas/${Number(id)}`, null,
  )
  const { datos: clientes } = useDatos<Cliente[]>('/api/clientes', [])

  if (cargando || error || !datos) return <DetalleEstado loading={cargando} error={error || null} />

  const estado = ESTADOS[datos.estado] ?? { label: datos.estado, tono: 'neutro' as const }
  const cobrado = datos.pagos.reduce((acc, p) => acc + p.monto, 0)

  return (
    <Pagina
      titulo={`Venta ${datos.numero}`}
      icono={ClipboardList}
      acciones={
        <>
          <BadgeEstado tono={estado.tono}>{estado.label}</BadgeEstado>
          {/* El mismo botón que la lista, no una copia: emite si falta y muestra
              el PDF si ya está. Quien abre la venta para mandar el comprobante
              no tiene que volver a la lista a buscarlo. */}
          <AccionRecibo venta={datos} onEmitido={conError} />
          {/* El camino a facturación. Va acá y no en la lista a propósito: pide
              decidir a nombre de quién cuando la venta es de mostrador, y esa
              decisión necesita ver la venta. */}
          <AccionRemito venta={datos} clientes={clientes} onGenerado={conError} />
          <Button asChild size="sm" variant="outline">
            <Link to="/ventas"><ArrowLeft />Volver</Link>
          </Button>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Cliente</CardTitle></CardHeader>
          <CardContent className="grid gap-2 text-sm">
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
          <CardContent className="grid gap-2 text-sm">
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
        <CardContent className="grid gap-2 text-sm">
          {datos.pagos.length === 0
            ? <p className="text-muted-foreground">Sin cobros registrados.</p>
            : datos.pagos.map((p, i) => (
              <p key={i} className="flex justify-between gap-4">
                <span>{medioLabel(p.medio, medios)}{p.referencia && ` · ${p.referencia}`}</span>
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
            render: (r) => r.anulado ? <BadgeEstado tono="negativo">Anulado</BadgeEstado> : null },
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
      fecha: hoyISO(), concepto: 'Pago a cuenta',
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
            <div className="grid gap-2">
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
