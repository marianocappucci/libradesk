// Depósitos de stock y listas de precios.
//
// Las dos son ABM de baja frecuencia —se cargan una vez y se consultan— así
// que van juntas y compactas. La operación diaria del inventario está en
// `Stock.tsx` (mover) y `Productos.tsx` (qué manejo).
import { useState } from 'react'
import { api } from '../api'
import { Pagina, Tabla, useDatos } from '@/components/comercial-ui'
import { useSucursal } from '@/components/sucursal'
import { pesos } from '@/lib/format'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import IconoDepositosStock from '~icons/fluent-color/vault-24'
import IconoListasPrecio from '~icons/fluent-color/list-bar-24'
import { FilePlus, Percent } from '@/components/iconos-accion'

// ── Depósitos de stock ─────────────────────────────────────────────────────

export type DepositoStock = {
  id: number
  nombre: string
  activo: boolean
  descripcion: string
  es_default: boolean
  sucursal_id: number | null
  sucursal: string
}

export function DepositosStock() {
  const { datos, error, cargando, conError } = useDatos<DepositoStock[]>('/api/depositos-stock', [])
  const { sucursales } = useSucursal()

  if (cargando) return <p className="text-sm text-muted-foreground">Cargando…</p>

  return (
    <Pagina titulo="Depósitos de stock" icono={IconoDepositosStock} error={error}
            acciones={<FormDeposito sucursales={sucursales} onGuardar={conError} />}>
      <p className="text-sm text-muted-foreground">
        Dónde hay existencias por cantidad. No confundir con los{' '}
        <strong>depósitos de equipos</strong>, que guardan una unidad serializada
        —dónde está un equipo cuando no está instalado—. Son dos cosas distintas
        que en castellano se llaman igual.
      </p>
      <Tabla<DepositoStock>
        vacio="Todavía no hay depósitos de stock."
        filas={datos}
        columnas={[
          { clave: 'nombre', titulo: 'Depósito',
            render: (d) => (
              <span className="flex items-center gap-2">
                {d.nombre}
                {d.es_default && <Badge variant="secondary">Principal</Badge>}
                {!d.activo && <Badge variant="outline">Inactivo</Badge>}
              </span>
            ) },
          { clave: 'sucursal', titulo: 'Sucursal', ancho: '180px',
            render: (d) => d.sucursal || <span className="text-muted-foreground">—</span> },
          { clave: 'descripcion', titulo: 'Descripción',
            render: (d) => <span className="text-muted-foreground">{d.descripcion || '—'}</span> },
        ]}
      />
    </Pagina>
  )
}

function FormDeposito({ sucursales, onGuardar }: {
  sucursales: { id: number; nombre: string }[]
  onGuardar: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const [abierto, setAbierto] = useState(false)
  const [nombre, setNombre] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [sucursalId, setSucursalId] = useState('ninguna')

  async function guardar() {
    const ok = await onGuardar(() => api.post('/api/depositos-stock', {
      nombre: nombre.trim(), descripcion,
      sucursal_id: sucursalId === 'ninguna' ? null : Number(sucursalId),
    }))
    if (ok) { setAbierto(false); setNombre(''); setDescripcion('') }
  }

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button><FilePlus className="mr-2 h-4 w-4" /> Nuevo depósito</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Nuevo depósito de stock</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="d-nombre">Nombre</Label>
            {/* El placeholder es una patente a propósito: en Lagrace los
                depósitos son las camionetas, y es el caso que hay que hacer
                obvio que entra. */}
            <Input id="d-nombre" value={nombre} onChange={(e) => setNombre(e.target.value)}
                   placeholder="DEPOSITO CENTRAL, o la patente de una camioneta" />
          </div>
          <div>
            <Label htmlFor="d-desc">Descripción</Label>
            <Input id="d-desc" value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
          </div>
          {sucursales.length > 0 && (
            <div>
              <Label htmlFor="d-suc">Sucursal</Label>
              <Select value={sucursalId} onValueChange={setSucursalId}>
                <SelectTrigger id="d-suc"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="ninguna">Sin sucursal</SelectItem>
                  {sucursales.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>{s.nombre}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancelar</Button></DialogClose>
          <Button onClick={guardar} disabled={!nombre.trim()}>Crear</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Listas de precios ──────────────────────────────────────────────────────

type Lista = {
  id: number; nombre: string; descripcion: string
  activa: boolean; es_default: boolean; items: number
}
type Precio = {
  id: number; item_id: number; producto: string
  precio: number; costo: number; margen_pct: number | null
}

export function ListasPrecio() {
  const { datos: listas, error, cargando, conError } = useDatos<Lista[]>('/api/listas-precio', [])
  const [abierta, setAbierta] = useState<Lista | null>(null)

  if (cargando) return <p className="text-sm text-muted-foreground">Cargando…</p>

  return (
    <Pagina titulo="Listas de precios" icono={IconoListasPrecio} error={error}
            acciones={<FormLista onGuardar={conError} />}>
      <Tabla<Lista>
        vacio="Todavía no hay listas de precios."
        filas={listas}
        onFila={setAbierta}
        columnas={[
          { clave: 'nombre', titulo: 'Lista',
            render: (l) => (
              <span className="flex items-center gap-2">
                {l.nombre}
                {l.es_default && <Badge variant="secondary">Por defecto</Badge>}
                {!l.activa && <Badge variant="outline">Inactiva</Badge>}
              </span>
            ) },
          { clave: 'descripcion', titulo: 'Descripción',
            render: (l) => <span className="text-muted-foreground">{l.descripcion || '—'}</span> },
          { clave: 'items', titulo: 'Productos', ancho: '110px', alinear: 'derecha',
            render: (l) => l.items },
        ]}
      />
      {abierta && (
        <DetalleLista lista={abierta} onCerrar={() => setAbierta(null)}
                      onCambio={conError} />
      )}
    </Pagina>
  )
}

function DetalleLista({ lista, onCerrar, onCambio }: {
  lista: Lista
  onCerrar: () => void
  onCambio: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const { datos: precios, recargar, conError } = useDatos<Precio[]>(
    `/api/listas-precio/${lista.id}/precios`, [],
  )
  const [pct, setPct] = useState('')

  async function ajustar() {
    const ok = await conError(() => api.post(`/api/listas-precio/${lista.id}/ajuste`, {
      porcentaje: Number(pct),
    }))
    if (ok) { setPct(''); await onCambio(async () => {}) }
  }

  return (
    <Card>
      <CardContent className="pt-6 space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h2 className="text-lg font-semibold">{lista.nombre}</h2>
          <Button variant="ghost" onClick={onCerrar}>Cerrar</Button>
        </div>

        {/* El ajuste masivo va arriba y no escondido en un menú: es la
            operación que más se usa de esta pantalla ("subime todo un 12%") y
            es la razón por la que las listas existen como entidad. */}
        <div className="flex items-end gap-2 flex-wrap rounded-md border bg-muted/40 p-3">
          <div>
            <Label htmlFor="l-pct">Ajustar todos los precios</Label>
            <div className="flex items-center gap-2">
              <Input id="l-pct" type="number" value={pct} className="w-28"
                     onChange={(e) => setPct(e.target.value)} placeholder="12" />
              <Percent className="h-4 w-4 text-muted-foreground" />
            </div>
          </div>
          <Button onClick={ajustar} disabled={!pct || Number.isNaN(Number(pct))}>
            Aplicar
          </Button>
          <p className="text-xs text-muted-foreground">
            Un valor negativo baja los precios.
          </p>
        </div>

        <Tabla<Precio>
          vacio="Esta lista todavía no tiene precios cargados."
          filas={precios}
          columnas={[
            { clave: 'producto', titulo: 'Producto', render: (p) => p.producto },
            { clave: 'costo', titulo: 'Costo', ancho: '110px', alinear: 'derecha',
              render: (p) => pesos(p.costo) },
            { clave: 'precio', titulo: 'Precio', ancho: '110px', alinear: 'derecha',
              render: (p) => pesos(p.precio) },
            { clave: 'margen', titulo: 'Margen', ancho: '90px', alinear: 'derecha',
              render: (p) => p.margen_pct === null
                ? <span className="text-muted-foreground">—</span>
                : `${p.margen_pct}%` },
            { clave: 'acciones', titulo: '', ancho: '60px',
              render: (p) => (
                <FormPrecio listaId={lista.id} precio={p}
                            onGuardar={async (fn) => { const ok = await conError(fn); if (ok) await recargar(); return ok }} />
              ) },
          ]}
        />
      </CardContent>
    </Card>
  )
}

function FormPrecio({ listaId, precio, onGuardar }: {
  listaId: number
  precio: Precio
  onGuardar: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const [abierto, setAbierto] = useState(false)
  const [valor, setValor] = useState(String(precio.precio))

  async function guardar() {
    const ok = await onGuardar(() => api.put(`/api/listas-precio/${listaId}/precios`, {
      item_id: precio.item_id, precio: Number(valor) || 0,
    }))
    if (ok) setAbierto(false)
  }

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">Editar</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>{precio.producto}</DialogTitle></DialogHeader>
        <div>
          <Label htmlFor="pr-valor">Precio</Label>
          <Input id="pr-valor" type="number" value={valor}
                 onChange={(e) => setValor(e.target.value)} />
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancelar</Button></DialogClose>
          <Button onClick={guardar}>Guardar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function FormLista({ onGuardar }: {
  onGuardar: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const [abierto, setAbierto] = useState(false)
  const [nombre, setNombre] = useState('')
  const [descripcion, setDescripcion] = useState('')

  async function guardar() {
    const ok = await onGuardar(() => api.post('/api/listas-precio', {
      nombre: nombre.trim(), descripcion,
    }))
    if (ok) { setAbierto(false); setNombre(''); setDescripcion('') }
  }

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button><FilePlus className="mr-2 h-4 w-4" /> Nueva lista</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Nueva lista de precios</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="li-nombre">Nombre</Label>
            <Input id="li-nombre" value={nombre} onChange={(e) => setNombre(e.target.value)}
                   placeholder="Mayorista" />
          </div>
          <div>
            <Label htmlFor="li-desc">Descripción</Label>
            <Input id="li-desc" value={descripcion}
                   onChange={(e) => setDescripcion(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancelar</Button></DialogClose>
          <Button onClick={guardar} disabled={!nombre.trim()}>Crear</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

