// El circuito de compras: lo que se pide, lo que llega y lo que se paga.
//
// Las tres pantallas van juntas porque son el mismo circuito en tres momentos,
// y porque quien las usa es la misma persona en la misma sesión de trabajo.
//
// 🔑 **La recepción es la que mueve el stock, no la orden.** Es la regla del
// motor y también cómo opera Lagrace hoy: la mercadería entra por "recepción de
// mercadería de proveedores", con factura o sin ella (el caso de las
// garantías). Una orden de compra es una intención.
import { useState } from 'react'
import { api } from '../api'
import { Cifras, Pagina, Tabla, useDatos } from '@/components/comercial-ui'
import { useSucursal } from '@/components/sucursal'
import { fecha, pesos } from '@/lib/format'
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
import ArrowDownToLine from '~icons/fluent-color/arrow-square-down-20'
import Wallet from '~icons/fluent-color/savings-16'
import IconoOrdenesCompra from '~icons/fluent-color/approvals-app-24'
import { FilePlus, Trash2 } from '@/components/iconos-accion'

type Proveedor = { id: number; nombre: string; activo: boolean }
type Orden = {
  id: number; numero: string; estado: string; proveedor: string
  fecha: string | null; items: number; total: number; recibido_pct: number
}
type Recepcion = {
  id: number; estado: string; proveedor: string; fecha: string | null
  documento: string; orden_id: number | null; items: number; total: number
}
type Egreso = {
  id: number; fecha: string; proveedor_nombre: string; concepto: string
  numero: string; categoria: string; total: number; estado: string
  tipo_comprobante: string
}

/** Una línea de comprobante en construcción. */
type Linea = { item_id: number; producto: string; cantidad: string; costo: string }

// ── Órdenes de compra ──────────────────────────────────────────────────────

export function OrdenesCompra() {
  const { datos, error, cargando, conError } = useDatos<Orden[]>('/api/ordenes-compra', [])
  const { datos: proveedores } = useDatos<Proveedor[]>('/api/proveedores', [])
  const { datos: productos } = useDatos<Producto[]>('/api/consumibles', [])

  if (cargando) return <p className="text-sm text-muted-foreground">Cargando…</p>

  return (
    <Pagina titulo="Órdenes de compra" icono={IconoOrdenesCompra} error={error}
            acciones={<FormOrden proveedores={proveedores} productos={productos}
                                 onGuardar={conError} />}>
      <Tabla<Orden>
        vacio="Todavía no hay órdenes de compra."
        filas={datos}
        columnas={[
          { clave: 'numero', titulo: 'Número', ancho: '130px',
            render: (o) => <span className="tabular-nums">{o.numero}</span> },
          { clave: 'fecha', titulo: 'Fecha', ancho: '110px', render: (o) => fecha(o.fecha) },
          { clave: 'proveedor', titulo: 'Proveedor', render: (o) => o.proveedor },
          { clave: 'items', titulo: 'Ítems', ancho: '70px', alinear: 'derecha',
            render: (o) => o.items },
          { clave: 'recibido', titulo: 'Recibido', ancho: '110px', alinear: 'derecha',
            render: (o) => (
              <Badge variant={o.recibido_pct === 100 ? 'secondary' : 'outline'}>
                {o.recibido_pct}%
              </Badge>
            ) },
          { clave: 'total', titulo: 'Total', ancho: '130px', alinear: 'derecha',
            render: (o) => pesos(o.total) },
        ]}
      />
    </Pagina>
  )
}

// ── Recepción de mercadería ────────────────────────────────────────────────

export function RecepcionesCompra() {
  const { datos, error, cargando, conError } = useDatos<Recepcion[]>('/api/recepciones-compra', [])
  const { datos: proveedores } = useDatos<Proveedor[]>('/api/proveedores', [])
  const { datos: productos } = useDatos<Producto[]>('/api/consumibles', [])
  const { datos: depositos } = useDatos<DepositoStock[]>('/api/depositos-stock', [])

  if (cargando) return <p className="text-sm text-muted-foreground">Cargando…</p>

  return (
    <Pagina titulo="Recepción de mercadería" icono={ArrowDownToLine} error={error}
            acciones={<FormRecepcion proveedores={proveedores} productos={productos}
                                     depositos={depositos} onGuardar={conError} />}>
      <p className="text-sm text-muted-foreground">
        Registrar una recepción <strong>suma el stock en el acto</strong> y
        actualiza el costo del producto con el de esta compra.
      </p>
      <Tabla<Recepcion>
        vacio="Todavía no se recibió mercadería."
        filas={datos}
        columnas={[
          { clave: 'fecha', titulo: 'Fecha', ancho: '110px', render: (r) => fecha(r.fecha) },
          { clave: 'proveedor', titulo: 'Proveedor', render: (r) => r.proveedor },
          { clave: 'documento', titulo: 'Comprobante', ancho: '190px',
            render: (r) => r.documento || <span className="text-muted-foreground">sin comprobante</span> },
          { clave: 'items', titulo: 'Ítems', ancho: '70px', alinear: 'derecha',
            render: (r) => r.items },
          { clave: 'total', titulo: 'Total', ancho: '130px', alinear: 'derecha',
            render: (r) => pesos(r.total) },
        ]}
      />
    </Pagina>
  )
}

// ── Egresos ────────────────────────────────────────────────────────────────

const ESTADO_VARIANT: Record<string, 'secondary' | 'outline' | 'destructive'> = {
  pagado: 'secondary', parcial: 'outline', pendiente: 'destructive',
}

export function Egresos() {
  const { datos, error, cargando, conError } = useDatos<Egreso[]>('/api/egresos', [])
  // ⚠️ La clave del total es `total_periodo`, no `total`. Con el nombre
  // equivocado el tipo compila igual y la tarjeta muestra «—» al lado de dos
  // cifras correctas, que se lee como "no hay egresos" en vez de "leí mal la
  // respuesta". Lo mismo que pasó con `cliente_id` en cuenta corriente.
  const { datos: resumen } = useDatos<{
    total_periodo: number; pagado: number; pendiente: number
  }>('/api/egresos/resumen', { total_periodo: 0, pagado: 0, pendiente: 0 })
  const { datos: proveedores } = useDatos<Proveedor[]>('/api/proveedores', [])
  const [abierto, setAbierto] = useState<Egreso | null>(null)

  if (cargando) return <p className="text-sm text-muted-foreground">Cargando…</p>

  return (
    <Pagina titulo="Egresos" icono={Wallet} error={error}
            acciones={<FormEgreso proveedores={proveedores} onGuardar={conError} />}>
      <Cifras items={[
        { label: 'Total del período', valor: pesos(resumen.total_periodo) },
        { label: 'Pagado', valor: pesos(resumen.pagado) },
        { label: 'Pendiente', valor: pesos(resumen.pendiente) },
      ]} />
      <Tabla<Egreso>
        vacio="Todavía no hay egresos cargados."
        filas={datos}
        onFila={setAbierto}
        columnas={[
          { clave: 'fecha', titulo: 'Fecha', ancho: '110px', render: (e) => fecha(e.fecha) },
          { clave: 'proveedor', titulo: 'Proveedor',
            render: (e) => e.proveedor_nombre || <span className="text-muted-foreground">—</span> },
          { clave: 'concepto', titulo: 'Concepto', render: (e) => e.concepto },
          { clave: 'numero', titulo: 'Comprobante', ancho: '160px',
            render: (e) => <span className="tabular-nums text-muted-foreground">{e.numero || '—'}</span> },
          { clave: 'estado', titulo: 'Estado', ancho: '110px',
            render: (e) => <Badge variant={ESTADO_VARIANT[e.estado] ?? 'outline'}>{e.estado}</Badge> },
          { clave: 'total', titulo: 'Total', ancho: '130px', alinear: 'derecha',
            render: (e) => pesos(e.total) },
        ]}
      />
      {abierto && <DetalleEgreso egreso={abierto} onCerrar={() => setAbierto(null)}
                                 onCambio={conError} />}
    </Pagina>
  )
}

function DetalleEgreso({ egreso, onCerrar, onCambio }: {
  egreso: Egreso
  onCerrar: () => void
  onCambio: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const { datos, recargar } = useDatos<{
    pagos: { fecha: string; monto: number; medio_pago: string }[]
    pagado: number; saldo: number; total: number
  }>(`/api/egresos/${egreso.id}`, { pagos: [], pagado: 0, saldo: 0, total: 0 })
  const [monto, setMonto] = useState('')

  async function pagar() {
    const ok = await onCambio(() => api.post(`/api/egresos/${egreso.id}/pagos`, {
      fecha: new Date().toISOString().slice(0, 10),
      monto: Number(monto), medio_pago: 'transferencia',
    }))
    if (ok) { setMonto(''); await recargar() }
  }

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onCerrar() }}>
      <DialogContent>
        <DialogHeader><DialogTitle>{egreso.concepto}</DialogTitle></DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-3 gap-2">
            <div><p className="text-muted-foreground">Total</p><p className="tabular-nums">{pesos(datos.total)}</p></div>
            <div><p className="text-muted-foreground">Pagado</p><p className="tabular-nums">{pesos(datos.pagado)}</p></div>
            <div><p className="text-muted-foreground">Saldo</p><p className="font-semibold tabular-nums">{pesos(datos.saldo)}</p></div>
          </div>
          {datos.pagos.length > 0 && (
            <div>
              <p className="mb-1 font-medium">Pagos</p>
              {datos.pagos.map((p, i) => (
                <p key={i} className="text-muted-foreground">
                  {fecha(p.fecha)} · {p.medio_pago} · <span className="tabular-nums">{pesos(p.monto)}</span>
                </p>
              ))}
            </div>
          )}
          <div className="flex items-end gap-2 rounded-md border bg-muted/40 p-3">
            <div>
              <Label htmlFor="eg-monto">Registrar pago</Label>
              <Input id="eg-monto" type="number" value={monto} className="w-36"
                     onChange={(e) => setMonto(e.target.value)} />
            </div>
            <Button onClick={pagar} disabled={!monto || Number(monto) <= 0}>Pagar</Button>
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cerrar</Button></DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Formularios ────────────────────────────────────────────────────────────

/** El armado de líneas, compartido por la orden y la recepción.
 *
 * Es el mismo gesto en las dos —elegir producto, cantidad y costo— y tenerlo
 * dos veces era garantizar que una de las dos calculara mal el total.
 */
function EditorLineas({ productos, lineas, setLineas }: {
  productos: Producto[]
  lineas: Linea[]
  setLineas: (l: Linea[]) => void
}) {
  const [productoId, setProductoId] = useState('')

  function agregar() {
    const p = productos.find((x) => x.id === Number(productoId))
    if (!p) return
    setLineas([...lineas, {
      item_id: p.id, producto: p.nombre, cantidad: '1', costo: String(p.costo || 0),
    }])
    setProductoId('')
  }

  const total = lineas.reduce(
    (acc, l) => acc + (Number(l.cantidad) || 0) * (Number(l.costo) || 0), 0,
  )

  return (
    <div className="space-y-2">
      <Label>Ítems</Label>
      <div className="flex gap-2">
        <Select value={productoId} onValueChange={setProductoId}>
          <SelectTrigger><SelectValue placeholder="Elegir producto…" /></SelectTrigger>
          <SelectContent>
            {productos.map((p) => (
              <SelectItem key={p.id} value={String(p.id)}>
                {p.codigo ? `${p.codigo} · ${p.nombre}` : p.nombre}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" onClick={agregar} disabled={!productoId}>Agregar</Button>
      </div>
      {lineas.map((l, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="flex-1 truncate text-sm">{l.producto}</span>
          <Input type="number" value={l.cantidad} className="w-20" aria-label="Cantidad"
                 onChange={(e) => setLineas(lineas.map((x, j) => j === i ? { ...x, cantidad: e.target.value } : x))} />
          <Input type="number" value={l.costo} className="w-28" aria-label="Costo unitario"
                 onChange={(e) => setLineas(lineas.map((x, j) => j === i ? { ...x, costo: e.target.value } : x))} />
          <Button variant="ghost" size="icon" aria-label="Quitar ítem"
                  onClick={() => setLineas(lineas.filter((_, j) => j !== i))}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ))}
      {lineas.length > 0 && (
        <p className="text-right text-sm font-medium tabular-nums">Total {pesos(total)}</p>
      )}
    </div>
  )
}

function FormOrden({ proveedores, productos, onGuardar }: {
  proveedores: Proveedor[]; productos: Producto[]
  onGuardar: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const { activa } = useSucursal()
  const [abierto, setAbierto] = useState(false)
  const [proveedorId, setProveedorId] = useState('')
  const [lineas, setLineas] = useState<Linea[]>([])

  async function guardar() {
    const ok = await onGuardar(() => api.post('/api/ordenes-compra', {
      proveedor_id: Number(proveedorId),
      sucursal_id: activa?.id ?? null,
      items: lineas.map((l) => ({
        item_id: l.item_id, cantidad: Number(l.cantidad) || 0, costo: Number(l.costo) || 0,
      })),
    }))
    if (ok) { setAbierto(false); setLineas([]); setProveedorId('') }
  }

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button><FilePlus className="mr-2 h-4 w-4" /> Nueva orden</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Nueva orden de compra</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="oc-prov">Proveedor</Label>
            <Select value={proveedorId} onValueChange={setProveedorId}>
              <SelectTrigger id="oc-prov"><SelectValue placeholder="Elegir…" /></SelectTrigger>
              <SelectContent>
                {proveedores.filter((p) => p.activo).map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>{p.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <EditorLineas productos={productos} lineas={lineas} setLineas={setLineas} />
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancelar</Button></DialogClose>
          <Button onClick={guardar} disabled={!proveedorId || lineas.length === 0}>Crear</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function FormRecepcion({ proveedores, productos, depositos, onGuardar }: {
  proveedores: Proveedor[]; productos: Producto[]; depositos: DepositoStock[]
  onGuardar: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const [abierto, setAbierto] = useState(false)
  const [proveedorId, setProveedorId] = useState('')
  const [depositoId, setDepositoId] = useState('')
  const [documento, setDocumento] = useState('')
  const [lineas, setLineas] = useState<Linea[]>([])

  async function guardar() {
    const ok = await onGuardar(() => api.post('/api/recepciones-compra', {
      proveedor_id: Number(proveedorId), deposito_id: Number(depositoId),
      documento,
      items: lineas.map((l) => ({
        item_id: l.item_id, cantidad: Number(l.cantidad) || 0, costo: Number(l.costo) || 0,
      })),
    }))
    if (ok) { setAbierto(false); setLineas([]); setProveedorId(''); setDocumento('') }
  }

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button><FilePlus className="mr-2 h-4 w-4" /> Recibir mercadería</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Recepción de mercadería</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="rc-prov">Proveedor</Label>
              <Select value={proveedorId} onValueChange={setProveedorId}>
                <SelectTrigger id="rc-prov"><SelectValue placeholder="Elegir…" /></SelectTrigger>
                <SelectContent>
                  {proveedores.filter((p) => p.activo).map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>{p.nombre}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="rc-dep">Depósito de entrada</Label>
              <Select value={depositoId} onValueChange={setDepositoId}>
                <SelectTrigger id="rc-dep"><SelectValue placeholder="Elegir…" /></SelectTrigger>
                <SelectContent>
                  {depositos.filter((d) => d.activo).map((d) => (
                    <SelectItem key={d.id} value={String(d.id)}>{d.nombre}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label htmlFor="rc-doc">Comprobante</Label>
            {/* Opcional a propósito: la mercadería en garantía vuelve sin
                factura, y ése es un caso normal del negocio, no un olvido. */}
            <Input id="rc-doc" value={documento} onChange={(e) => setDocumento(e.target.value)}
                   placeholder="FC A 0001-00012345 (opcional)" />
          </div>
          <EditorLineas productos={productos} lineas={lineas} setLineas={setLineas} />
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancelar</Button></DialogClose>
          <Button onClick={guardar}
                  disabled={!proveedorId || !depositoId || lineas.length === 0}>
            Recibir y sumar al stock
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function FormEgreso({ proveedores, onGuardar }: {
  proveedores: Proveedor[]
  onGuardar: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const [abierto, setAbierto] = useState(false)
  const [concepto, setConcepto] = useState('')
  const [total, setTotal] = useState('')
  const [numero, setNumero] = useState('')
  const [categoria, setCategoria] = useState('')
  const [proveedorId, setProveedorId] = useState('')

  async function guardar() {
    const prov = proveedores.find((p) => p.id === Number(proveedorId))
    const ok = await onGuardar(() => api.post('/api/egresos', {
      fecha: new Date().toISOString().slice(0, 10),
      concepto: concepto.trim(), total: Number(total) || 0,
      proveedor_id: prov?.id ?? null, proveedor_nombre: prov?.nombre ?? '',
      numero, categoria,
    }))
    if (ok) { setAbierto(false); setConcepto(''); setTotal(''); setNumero('') }
  }

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button><FilePlus className="mr-2 h-4 w-4" /> Nuevo egreso</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Nuevo egreso</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="eg-concepto">Concepto</Label>
            <Input id="eg-concepto" value={concepto}
                   onChange={(e) => setConcepto(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="eg-total">Total</Label>
              <Input id="eg-total" type="number" value={total}
                     onChange={(e) => setTotal(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="eg-numero">Comprobante</Label>
              <Input id="eg-numero" value={numero}
                     onChange={(e) => setNumero(e.target.value)} />
            </div>
          </div>
          <div>
            <Label htmlFor="eg-prov">Proveedor</Label>
            <Select value={proveedorId} onValueChange={setProveedorId}>
              <SelectTrigger id="eg-prov"><SelectValue placeholder="Elegir…" /></SelectTrigger>
              <SelectContent>
                {proveedores.filter((p) => p.activo).map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>{p.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="eg-cat">Categoría</Label>
            <Input id="eg-cat" value={categoria}
                   onChange={(e) => setCategoria(e.target.value)}
                   placeholder="Mercadería, Servicios, Combustible…" />
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancelar</Button></DialogClose>
          <Button onClick={guardar} disabled={!concepto.trim() || !total}>Crear</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
