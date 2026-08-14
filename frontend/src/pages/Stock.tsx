// Stock de consumibles. Todo lo que hay debajo sale de LibraCommerce; esta
// pantalla sólo lo muestra.
//
// La organiza una pregunta y no un CRUD: **"¿de dónde saco un plug?"**. Por eso
// el eje es el consumible y no el depósito — se elige qué material y la tabla
// dice cuánto hay en cada lugar, que es el orden en que lo piensa el técnico.
// Un ABM de depósitos existe, pero abajo y chico: se carga una vez.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ApiError } from '../api'
import { Card, CardContent } from '@/components/ui/card'
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
import { PackageSearch as IconoStock } from 'lucide-react'
import { ArrowLeftRight, Building2, FilePlus, Minus, Plus } from '@/components/iconos-accion'
import { TituloPantalla } from '@/components/titulo-pantalla'

export type Consumible = {
  id: number
  nombre: string
  activo: boolean
  stock_minimo: number
  costo: number
}

export type DepositoStock = {
  id: number
  nombre: string
  activo: boolean
  descripcion: string
  es_default: boolean
}

export type StockPorDeposito = DepositoStock & { stock: number }

export function Stock() {
  const [consumibles, setConsumibles] = useState<Consumible[]>([])
  const [depositos, setDepositos] = useState<DepositoStock[]>([])
  const [elegido, setElegido] = useState<Consumible | null>(null)
  const [porDeposito, setPorDeposito] = useState<StockPorDeposito[]>([])
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(true)

  const cargarBase = useCallback(async () => {
    const [items, deps] = await Promise.all([
      api.get<Consumible[]>('/api/consumibles'),
      api.get<DepositoStock[]>('/api/depositos-stock'),
    ])
    setConsumibles(items)
    setDepositos(deps)
    setCargando(false)
    return items
  }, [])

  const cargarStock = useCallback(async (item: Consumible | null) => {
    if (!item) { setPorDeposito([]); return }
    setPorDeposito(await api.get<StockPorDeposito[]>(`/api/consumibles/${item.id}/stock`))
  }, [])

  useEffect(() => { void cargarBase() }, [cargarBase])
  useEffect(() => { void cargarStock(elegido) }, [elegido, cargarStock])

  const total = useMemo(
    () => porDeposito.reduce((acc, d) => acc + d.stock, 0),
    [porDeposito],
  )

  // El mínimo se compara contra el TOTAL y no contra cada depósito: tener 5
  // plugs en la camioneta y 200 en el central no es faltante, es logística.
  const bajoMinimo = elegido !== null && elegido.stock_minimo > 0 && total < elegido.stock_minimo

  async function conError(accion: () => Promise<unknown>) {
    setError('')
    try {
      await accion()
      const items = await cargarBase()
      const vigente = elegido ? items.find((i) => i.id === elegido.id) ?? null : null
      setElegido(vigente)
      await cargarStock(vigente)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudo completar la operación.')
    }
  }

  if (cargando) return <p className="text-sm text-muted-foreground">Cargando…</p>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <TituloPantalla icono={IconoStock}>
          Stock de consumibles
        </TituloPantalla>
        <div className="flex gap-2">
          <NuevoConsumible onListo={(fn) => conError(fn)} />
          <NuevoDeposito onListo={(fn) => conError(fn)} />
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {consumibles.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
          Todavía no hay consumibles cargados. El primero se crea con «Nuevo consumible».
        </CardContent></Card>
      ) : (
        <Card>
          <CardContent className="pt-6 space-y-4">
            <div className="flex items-end gap-3 flex-wrap">
              <div className="min-w-64">
                <Label>Consumible</Label>
                {/* `''` y no `undefined`: con `undefined` el Select arranca
                    NO controlado y pasa a controlado al elegir algo, y React
                    avisa por consola. Lo caza el test de esta pantalla, que
                    falla ante cualquier warning. */}
                <Select
                  value={elegido ? String(elegido.id) : ''}
                  onValueChange={(v) =>
                    setElegido(consumibles.find((c) => String(c.id) === v) ?? null)}
                >
                  <SelectTrigger><SelectValue placeholder="Elegí un consumible" /></SelectTrigger>
                  <SelectContent>
                    {consumibles.map((c) => (
                      <SelectItem key={c.id} value={String(c.id)}>{c.nombre}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {elegido && (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">Total:</span>
                  <Badge variant={bajoMinimo ? 'destructive' : 'secondary'}>{total}</Badge>
                  {bajoMinimo && (
                    <span className="text-xs text-destructive">
                      por debajo del mínimo ({elegido.stock_minimo})
                    </span>
                  )}
                </div>
              )}
              {elegido && depositos.length > 1 && (
                <Transferir
                  item={elegido} depositos={porDeposito}
                  onListo={(fn) => conError(fn)}
                />
              )}
            </div>

            {elegido && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2">Depósito</th>
                    <th className="py-2 w-24 text-right">Cantidad</th>
                    <th className="py-2 w-40 text-right">Ajuste</th>
                  </tr>
                </thead>
                <tbody>
                  {porDeposito.map((d) => (
                    <tr key={d.id} className="border-b last:border-0">
                      <td className="py-2">
                        {d.nombre}
                        {d.es_default && (
                          <span className="ml-2 text-xs text-muted-foreground">(por defecto)</span>
                        )}
                      </td>
                      <td className="py-2 text-right tabular-nums">{d.stock}</td>
                      <td className="py-2">
                        <Ajuste
                          item={elegido} deposito={d} onListo={(fn) => conError(fn)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

type ConAccion = { onListo: (fn: () => Promise<unknown>) => void }

function Ajuste({ item, deposito, onListo }: ConAccion & {
  item: Consumible; deposito: StockPorDeposito
}) {
  const [cantidad, setCantidad] = useState('')

  function mover(signo: 1 | -1) {
    const n = Number(cantidad)
    if (!Number.isFinite(n) || n <= 0) return
    onListo(() => api.post(`/api/consumibles/${item.id}/ajuste`, {
      deposito_id: deposito.id, cantidad: signo * n, nota: 'Ajuste manual',
    }))
    setCantidad('')
  }

  return (
    <div className="flex items-center justify-end gap-1">
      <Input
        value={cantidad} onChange={(e) => setCantidad(e.target.value)}
        className="h-8 w-20 text-right" inputMode="decimal" placeholder="0"
        aria-label={`Cantidad a ajustar en ${deposito.nombre}`}
      />
      <Button size="icon" variant="outline" className="h-8 w-8"
              aria-label={`Sumar en ${deposito.nombre}`} onClick={() => mover(1)}>
        <Plus className="h-4 w-4" />
      </Button>
      <Button size="icon" variant="outline" className="h-8 w-8"
              aria-label={`Restar en ${deposito.nombre}`} onClick={() => mover(-1)}>
        <Minus className="h-4 w-4" />
      </Button>
    </div>
  )
}

function Transferir({ item, depositos, onListo }: ConAccion & {
  item: Consumible; depositos: StockPorDeposito[]
}) {
  const [abierto, setAbierto] = useState(false)
  const [origen, setOrigen] = useState('')
  const [destino, setDestino] = useState('')
  const [cantidad, setCantidad] = useState('')

  const disponible = depositos.find((d) => String(d.id) === origen)?.stock ?? 0
  const n = Number(cantidad)
  const valido = origen !== '' && destino !== '' && origen !== destino
    && Number.isFinite(n) && n > 0 && n <= disponible

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <ArrowLeftRight className="h-4 w-4 mr-2" /> Transferir
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Transferir {item.nombre}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Desde</Label>
            <Select value={origen} onValueChange={setOrigen}>
              <SelectTrigger><SelectValue placeholder="Depósito de origen" /></SelectTrigger>
              <SelectContent>
                {depositos.map((d) => (
                  <SelectItem key={d.id} value={String(d.id)}>
                    {d.nombre} ({d.stock})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Hacia</Label>
            <Select value={destino} onValueChange={setDestino}>
              <SelectTrigger><SelectValue placeholder="Depósito de destino" /></SelectTrigger>
              <SelectContent>
                {depositos.filter((d) => String(d.id) !== origen).map((d) => (
                  <SelectItem key={d.id} value={String(d.id)}>{d.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Cantidad</Label>
            <Input value={cantidad} onChange={(e) => setCantidad(e.target.value)}
                   inputMode="decimal" placeholder="0" />
            {/* El tope se muestra acá y además lo valida el servidor: esto es
                para no hacer tipear algo que va a ser rechazado, no la defensa. */}
            {origen !== '' && (
              <p className="text-xs text-muted-foreground mt-1">
                Disponible en el origen: {disponible}
              </p>
            )}
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="ghost">Cancelar</Button></DialogClose>
          <Button
            disabled={!valido}
            onClick={() => {
              onListo(() => api.post('/api/consumibles/transferir', {
                item_id: item.id, origen_id: Number(origen),
                destino_id: Number(destino), cantidad: n,
                nota: 'Transferencia entre depósitos',
              }))
              setAbierto(false); setCantidad('')
            }}
          >Transferir</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function NuevoConsumible({ onListo }: ConAccion) {
  const [abierto, setAbierto] = useState(false)
  const [nombre, setNombre] = useState('')
  const [minimo, setMinimo] = useState('')

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button size="sm"><FilePlus className="h-4 w-4 mr-2" /> Nuevo consumible</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Nuevo consumible</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Nombre</Label>
            <Input value={nombre} onChange={(e) => setNombre(e.target.value)}
                   placeholder="Plug RJ45" />
          </div>
          <div>
            <Label>Stock mínimo (opcional)</Label>
            <Input value={minimo} onChange={(e) => setMinimo(e.target.value)}
                   inputMode="decimal" placeholder="0" />
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="ghost">Cancelar</Button></DialogClose>
          <Button
            disabled={nombre.trim() === ''}
            onClick={() => {
              onListo(() => api.post('/api/consumibles', {
                nombre: nombre.trim(), stock_minimo: Number(minimo) || 0,
              }))
              setAbierto(false); setNombre(''); setMinimo('')
            }}
          >Crear</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function NuevoDeposito({ onListo }: ConAccion) {
  const [abierto, setAbierto] = useState(false)
  const [nombre, setNombre] = useState('')

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <Building2 className="h-4 w-4 mr-2" /> Nuevo depósito
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Nuevo depósito de consumibles</DialogTitle></DialogHeader>
        {/* La aclaración va en la pantalla y no sólo en el código: en castellano
            los dos se llaman "depósito" y el de equipos ya existe en el menú. */}
        <p className="text-sm text-muted-foreground">
          Es un lugar con existencias por cantidad —el depósito central, la
          camioneta de una cuadrilla—, distinto de los depósitos de equipos.
        </p>
        <div>
          <Label>Nombre</Label>
          <Input value={nombre} onChange={(e) => setNombre(e.target.value)}
                 placeholder="Camioneta Norte" />
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="ghost">Cancelar</Button></DialogClose>
          <Button
            disabled={nombre.trim() === ''}
            onClick={() => {
              onListo(() => api.post('/api/depositos-stock', { nombre: nombre.trim() }))
              setAbierto(false); setNombre('')
            }}
          >Crear</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default Stock
