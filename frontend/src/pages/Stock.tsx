// Stock de consumibles. Todo lo que hay debajo sale de LibraCommerce; esta
// pantalla sólo lo muestra.
//
// La organiza una pregunta y no un CRUD: **"¿de dónde saco un plug?"**. Por eso
// el eje es el consumible y no el depósito — se elige qué material y la tabla
// dice cuánto hay en cada lugar, que es el orden en que lo piensa el técnico.
// Un ABM de depósitos existe, pero abajo y chico: se carga una vez.
//
// ## Por qué el stock se pide SIN filtrar y se filtra acá
//
// La tabla muestra los depósitos de la sucursal activa, pero **la transferencia
// necesita ver los de las otras** — si no, el depósito al que se quiere mandar
// la mercadería es justamente el que no aparece en el selector. Pedir la lista
// completa una vez y recortarla para la tabla resuelve las dos cosas con un
// request; pedirla filtrada obligaría a un segundo pedido para el destino.
import { EncabezadoDePantalla } from 'libra-ui/acciones'
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
import { useSucursal } from '@/components/sucursal'

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
  //: `null` = depósito sin sucursal, que es el caso de la empresa de un solo
  //: local. No es "sin asignar todavía".
  sucursal_id: number | null
  sucursal: string
}

export type StockPorDeposito = DepositoStock & { stock: number }

export function Stock() {
  const [consumibles, setConsumibles] = useState<Consumible[]>([])
  const [depositos, setDepositos] = useState<DepositoStock[]>([])
  const [elegido, setElegido] = useState<Consumible | null>(null)
  const [porDeposito, setPorDeposito] = useState<StockPorDeposito[]>([])
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(true)
  const { activa } = useSucursal()

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

  // Lo que se ve en la tabla: los depósitos de la sucursal activa. Con «Todas»
  // elegido, todos. `porDeposito` sigue completo para la transferencia.
  const visibles = useMemo(
    () => (activa ? porDeposito.filter((d) => d.sucursal_id === activa.id) : porDeposito),
    [porDeposito, activa],
  )

  const total = useMemo(
    () => visibles.reduce((acc, d) => acc + d.stock, 0),
    [visibles],
  )

  // El mínimo se compara contra el TOTAL y no contra cada depósito: tener 5
  // plugs en la camioneta y 200 en el central no es faltante, es logística.
  //
  // ⚠️ Con una sucursal elegida, ese total es **el de la sucursal**, así que un
  // consumible puede figurar bajo mínimo acá y sobrar en la empresa. Es lo que
  // hace útil la vista —dice dónde reponer— y por eso el cartel lo aclara.
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
      <EncabezadoDePantalla titulo={<TituloPantalla icono={IconoStock}>Stock de consumibles</TituloPantalla>}>
        <div className="flex gap-2">
          <NuevoConsumible onListo={(fn) => conError(fn)} />
          <NuevoDeposito onListo={(fn) => conError(fn)} />
        </div>
      </EncabezadoDePantalla>

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
                <Label htmlFor="st-consumible">Consumible</Label>
                {/* `''` y no `undefined`: con `undefined` el Select arranca
                    NO controlado y pasa a controlado al elegir algo, y React
                    avisa por consola. Lo caza el test de esta pantalla, que
                    falla ante cualquier warning. */}
                <Select
                  value={elegido ? String(elegido.id) : ''}
                  onValueChange={(v) =>
                    setElegido(consumibles.find((c) => String(c.id) === v) ?? null)}
                >
                  <SelectTrigger id="st-consumible">
                    <SelectValue placeholder="Elegí un consumible" />
                  </SelectTrigger>
                  <SelectContent>
                    {consumibles.map((c) => (
                      <SelectItem key={c.id} value={String(c.id)}>{c.nombre}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {elegido && (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">
                    {activa ? `Total en ${activa.nombre}:` : 'Total:'}
                  </span>
                  <Badge variant={bajoMinimo ? 'destructive' : 'secondary'}>{total}</Badge>
                  {bajoMinimo && (
                    <span className="text-xs text-destructive">
                      por debajo del mínimo ({elegido.stock_minimo})
                      {activa && ' contando sólo esta sucursal'}
                    </span>
                  )}
                </div>
              )}
              {elegido && depositos.length > 1 && (
                <Transferir
                  item={elegido} origenes={visibles} destinos={porDeposito}
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
                  {visibles.map((d) => (
                    <tr key={d.id} className="border-b last:border-0">
                      <td className="py-2">
                        {d.nombre}
                        {d.es_default && (
                          <span className="ml-2 text-xs text-muted-foreground">(por defecto)</span>
                        )}
                        {/* La sucursal se muestra sólo mirando «Todas»: con una
                            elegida sería la misma etiqueta en cada fila. */}
                        {!activa && d.sucursal && (
                          <span className="ml-2 text-xs text-muted-foreground">· {d.sucursal}</span>
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

/**
 * Mueve consumibles entre depósitos, sean o no de la misma sucursal.
 *
 * `origenes` son los depósitos visibles (los de la sucursal activa) y
 * `destinos` **son todos**: mandar mercadería a otra sucursal es el caso que
 * este diálogo tiene que poder hacer, y filtrando el destino sería el único
 * que no.
 *
 * ⚠️ **Es un movimiento directo, no un envío con recepción.** Sale y entra en la
 * misma transacción: apenas se confirma, el sistema ya cuenta la mercadería en
 * el destino aunque físicamente esté en la camioneta. El cartel de abajo lo dice
 * cuando la transferencia cruza sucursales, que es cuando el viaje dura.
 */
function Transferir({ item, origenes, destinos, onListo }: ConAccion & {
  item: Consumible; origenes: StockPorDeposito[]; destinos: StockPorDeposito[]
}) {
  const [abierto, setAbierto] = useState(false)
  const [origen, setOrigen] = useState('')
  const [destino, setDestino] = useState('')
  const [cantidad, setCantidad] = useState('')

  const depOrigen = origenes.find((d) => String(d.id) === origen) ?? null
  const depDestino = destinos.find((d) => String(d.id) === destino) ?? null
  const disponible = depOrigen?.stock ?? 0
  const cruzaSucursal = depOrigen !== null && depDestino !== null
    && depOrigen.sucursal_id !== depDestino.sucursal_id
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
            {/* `htmlFor` + `id`: sin la asociación el select no tiene nombre
                accesible y queda como "un combobox más" del diálogo, tanto para
                un lector de pantalla como para quien lo busque desde un test. */}
            <Label htmlFor="tr-origen">Desde</Label>
            <Select value={origen} onValueChange={setOrigen}>
              <SelectTrigger id="tr-origen"><SelectValue placeholder="Depósito de origen" /></SelectTrigger>
              <SelectContent>
                {origenes.map((d) => (
                  <SelectItem key={d.id} value={String(d.id)}>
                    {d.nombre} ({d.stock})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="tr-destino">Hacia</Label>
            <Select value={destino} onValueChange={setDestino}>
              <SelectTrigger id="tr-destino"><SelectValue placeholder="Depósito de destino" /></SelectTrigger>
              <SelectContent>
                {destinos.filter((d) => String(d.id) !== origen).map((d) => (
                  <SelectItem key={d.id} value={String(d.id)}>
                    {d.nombre}
                    {d.sucursal && (
                      <span className="ml-2 text-xs text-muted-foreground">· {d.sucursal}</span>
                    )}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
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
          {cruzaSucursal && (
            <p className="text-xs text-amber-600 dark:text-amber-500">
              Sale de {depOrigen.sucursal || 'sin sucursal'} y entra en{' '}
              {depDestino.sucursal || 'sin sucursal'}. El stock se mueve en el
              acto: el destino lo cuenta apenas confirmes, aunque la mercadería
              todavía esté viajando.
            </p>
          )}
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="ghost">Cancelar</Button></DialogClose>
          <Button
            disabled={!valido}
            onClick={() => {
              onListo(() => api.post('/api/consumibles/transferir', {
                item_id: item.id, origen_id: Number(origen),
                destino_id: Number(destino), cantidad: n,
                nota: cruzaSucursal
                  ? `Transferencia ${depOrigen.sucursal || 'sin sucursal'} → ${depDestino.sucursal || 'sin sucursal'}`
                  : 'Transferencia entre depósitos',
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
          <div className="grid gap-2">
            <Label>Nombre</Label>
            <Input value={nombre} onChange={(e) => setNombre(e.target.value)}
                   placeholder="Plug RJ45" />
          </div>
          <div className="grid gap-2">
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
  const { activa } = useSucursal()

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
        <div className="grid gap-2">
          <Label>Nombre</Label>
          <Input value={nombre} onChange={(e) => setNombre(e.target.value)}
                 placeholder="Camioneta Norte" />
        </div>
        {/* Se dice a qué sucursal va a quedar asignado en vez de ofrecer un
            selector más: con «Todas» elegido queda sin sucursal, que es lo
            correcto para la empresa de un solo local. Reasignarlo después es
            editarlo desde Depósitos de stock. */}
        {activa && (
          <p className="text-xs text-muted-foreground">
            Queda en la sucursal {activa.nombre}.
          </p>
        )}
        <DialogFooter>
          <DialogClose asChild><Button variant="ghost">Cancelar</Button></DialogClose>
          <Button
            disabled={nombre.trim() === ''}
            onClick={() => {
              onListo(() => api.post('/api/depositos-stock', {
                nombre: nombre.trim(), sucursal_id: activa?.id ?? null,
              }))
              setAbierto(false); setNombre('')
            }}
          >Crear</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default Stock
