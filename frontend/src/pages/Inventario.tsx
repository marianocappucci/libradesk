// Depósitos de stock y listas de precios.
//
// Las dos son ABM de baja frecuencia —se cargan una vez y se consultan— así
// que van juntas y compactas. La operación diaria del inventario está en
// `Stock.tsx` (mover) y `Productos.tsx` (qué manejo).
import { useState } from 'react'
import { api } from '../api'
import { Pagina, Tabla, useDatos } from '@/components/comercial-ui'
import { useSucursal, useSucursalUrl } from '@/components/sucursal'
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
import { Boxes as IconoDepositosStock, Tags as IconoListasPrecio } from 'lucide-react'
import { FilePlus, Pencil, Percent, Trash2 } from '@/components/iconos-accion'

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
  const conSucursal = useSucursalUrl()
  const { datos, error, cargando, conError } =
    useDatos<DepositoStock[]>(conSucursal('/api/depositos-stock'), [])
  const { sucursales, activa } = useSucursal()

  if (cargando) return <p className="text-sm text-muted-foreground">Cargando…</p>

  return (
    <Pagina titulo="Depósitos de stock" icono={IconoDepositosStock} error={error}
            acciones={<FormDeposito sucursales={sucursales} onGuardar={conError} />}>
      <p className="text-sm text-muted-foreground">
        Dónde hay existencias por cantidad. No confundir con los{' '}
        <strong>depósitos de equipos</strong>, que guardan una unidad serializada
        —dónde está un equipo cuando no está instalado—. Son dos cosas distintas
        que en castellano se llaman igual.
        {/* Una lista recortada que parece completa es peor que no filtrar. */}
        {activa && ` Se muestran sólo los de ${activa.nombre}.`}
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
          { clave: 'acciones', titulo: 'Acciones', ancho: '90px',
            render: (d) => (
              <FormDeposito deposito={d} sucursales={sucursales} onGuardar={conError} />
            ) },
        ]}
      />
    </Pagina>
  )
}

/**
 * Alta y edición de un depósito de stock.
 *
 * La edición existe sobre todo para **reasignar la sucursal**: mover el
 * depósito mueve con él todas sus existencias, porque el stock cuelga del
 * depósito y no de la sucursal. Es la forma de corregir uno mal asignado —no
 * la forma de mover mercadería, que es la transferencia de `Stock.tsx`— y por
 * eso el diálogo lo dice.
 */
function FormDeposito({ deposito, sucursales, onGuardar }: {
  deposito?: DepositoStock
  sucursales: { id: number; nombre: string }[]
  onGuardar: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const editando = deposito !== undefined
  const [abierto, setAbierto] = useState(false)
  const [nombre, setNombre] = useState(deposito?.nombre ?? '')
  const [descripcion, setDescripcion] = useState(deposito?.descripcion ?? '')
  const [sucursalId, setSucursalId] = useState(
    deposito?.sucursal_id == null ? 'ninguna' : String(deposito.sucursal_id),
  )

  const cambiaDeSucursal = editando
    && (deposito.sucursal_id ?? null) !== (sucursalId === 'ninguna' ? null : Number(sucursalId))

  async function guardar() {
    const cuerpo = {
      nombre: nombre.trim(), descripcion,
      sucursal_id: sucursalId === 'ninguna' ? null : Number(sucursalId),
      // `es_default` no viaja: el servicio lo conserva de la fila actual, y
      // mandarlo desde acá sería otra fuente de verdad para el mismo dato.
      ...(editando ? { activo: deposito.activo } : {}),
    }
    const ok = await onGuardar(() =>
      editando
        ? api.put(`/api/depositos-stock/${deposito.id}`, cuerpo)
        : api.post('/api/depositos-stock', cuerpo))
    if (!ok) return
    setAbierto(false)
    if (!editando) { setNombre(''); setDescripcion('') }
  }

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        {/* Mismo lápiz que en el resto del producto. Este no lo reportó el
            humano —reportó el de listas de precios— pero era la MISMA palabra
            suelta en el mismo archivo: arreglar sólo la instancia vista deja
            la otra para que vuelva dentro de unos días. */}
        {editando
          ? <Button variant="outline" size="icon" title="Editar"
                    aria-label={`Editar ${deposito.nombre}`}>
              <Pencil />
            </Button>
          : <Button><FilePlus className="mr-2 h-4 w-4" /> Nuevo depósito</Button>}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {editando ? deposito.nombre : 'Nuevo depósito de stock'}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid gap-2">
            <Label htmlFor="d-nombre">Nombre</Label>
            {/* El placeholder es una patente a propósito: en Lagrace los
                depósitos son las camionetas, y es el caso que hay que hacer
                obvio que entra. */}
            <Input id="d-nombre" value={nombre} onChange={(e) => setNombre(e.target.value)}
                   placeholder="DEPOSITO CENTRAL, o la patente de una camioneta" />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="d-desc">Descripción</Label>
            <Input id="d-desc" value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
          </div>
          {sucursales.length > 0 && (
            <div className="grid gap-2">
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
          {cambiaDeSucursal && (
            <p className="text-xs text-amber-600 dark:text-amber-500">
              El depósito se muda con todas sus existencias. Para mover
              mercadería de una sucursal a otra dejando el depósito donde está,
              usá una transferencia desde Stock.
            </p>
          )}
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancelar</Button></DialogClose>
          <Button onClick={guardar} disabled={!nombre.trim()}>
            {editando ? 'Guardar' : 'Crear'}
          </Button>
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
  //: `true` = esta fila es un precio cargado para la sucursal que se está
  //: mirando. `false` = es el general de la lista, que se aplica ahí porque la
  //: sucursal no tiene uno propio.
  propio_de_sucursal: boolean
  sucursal_id: number | null
  sucursal: string
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
  const conSucursal = useSucursalUrl()
  const { activa } = useSucursal()
  const { datos: precios, recargar, conError } = useDatos<Precio[]>(
    conSucursal(`/api/listas-precio/${lista.id}/precios`), [],
  )
  const [pct, setPct] = useState('')

  async function ajustar() {
    const ok = await conError(() => api.post(`/api/listas-precio/${lista.id}/ajuste`, {
      porcentaje: Number(pct),
      // Con una sucursal elegida, el ajuste masivo mueve **sólo** sus precios
      // propios. Los productos que ahí cotizan por el general no se tocan:
      // moverlos movería también el precio de la otra sucursal.
      sucursal_id: activa?.id ?? null,
    }))
    if (ok) { setPct(''); await onCambio(async () => {}) }
  }

  return (
    <Card>
      <CardContent className="pt-6 space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          {/* Subsección, no título de pantalla: es el panel de la lista elegida
              adentro de "Listas de precios", que ya trae su propio encabezado
              desde `comercial-ui`. Usaba el tamaño del título, y eso era parte
              del desorden que se vino a ordenar. */}
          <h2 className="text-base font-semibold">{lista.nombre}</h2>
          <Button variant="ghost" onClick={onCerrar}>Cerrar</Button>
        </div>

        {/* El ajuste masivo va arriba y no escondido en un menú: es la
            operación que más se usa de esta pantalla ("subime todo un 12%") y
            es la razón por la que las listas existen como entidad. */}
        <div className="flex items-end gap-2 flex-wrap rounded-md border bg-muted/40 p-3">
          <div className="grid gap-2">
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
            {activa
              ? ` Sólo mueve los precios propios de ${activa.nombre}.`
              : ' Mueve todos los precios de la lista, incluidos los propios de cada sucursal.'}
          </p>
        </div>

        {activa && (
          <p className="text-xs text-muted-foreground">
            Se muestra el precio que se aplica en {activa.nombre}: el propio de
            la sucursal si tiene, o el general de la lista si no.
          </p>
        )}

        <Tabla<Precio>
          vacio="Esta lista todavía no tiene precios cargados."
          filas={precios}
          columnas={[
            { clave: 'producto', titulo: 'Producto',
              render: (p) => (
                <span className="flex items-center gap-2">
                  {p.producto}
                  {/* Mirando «Todas», la etiqueta dice de qué sucursal es la
                      fila. Con una elegida, dice si el precio es propio o
                      heredado del general — que es la pregunta de ahí. */}
                  {activa
                    ? p.propio_de_sucursal
                      ? <Badge variant="secondary">Propio</Badge>
                      : <Badge variant="outline">General</Badge>
                    : p.sucursal && <Badge variant="secondary">{p.sucursal}</Badge>}
                </span>
              ) },
            { clave: 'costo', titulo: 'Costo', ancho: '110px', alinear: 'derecha',
              render: (p) => pesos(p.costo) },
            { clave: 'precio', titulo: 'Precio', ancho: '110px', alinear: 'derecha',
              render: (p) => pesos(p.precio) },
            { clave: 'margen', titulo: 'Margen', ancho: '90px', alinear: 'derecha',
              render: (p) => p.margen_pct === null
                ? <span className="text-muted-foreground">—</span>
                : `${p.margen_pct}%` },
            // `alinear: 'derecha'` para que el título quede sobre los botones:
            // la celda los manda a la derecha con `justify-end` y el
            // encabezado se dibujaba a la izquierda, o sea la palabra
            // "Acciones" arriba del margen vacío de la columna.
            { clave: 'acciones', titulo: 'Acciones', ancho: '100px', alinear: 'derecha',
              render: (p) => (
                <div className="flex justify-end gap-1">
                  <FormPrecio listaId={lista.id} precio={p} sucursalId={activa?.id ?? null}
                              onGuardar={async (fn) => { const ok = await conError(fn); if (ok) await recargar(); return ok }} />
                  {activa && p.propio_de_sucursal && (
                    // Tacho y no la palabra "Quitar", por lo mismo que el lápiz
                    // de al lado. El `title`/`aria-label` es el que dice qué
                    // quita: borra el precio PROPIO de la sucursal, con lo que
                    // la fila vuelve a cotizar por el general de la lista.
                    <Button variant="outline" size="icon"
                            title={`Quitar el precio propio de ${activa.nombre}`}
                            aria-label={`Quitar el precio propio de ${p.producto} en ${activa.nombre}`}
                            onClick={async () => {
                              const ok = await conError(() => api.del(
                                `/api/listas-precio/${lista.id}/precios/${p.item_id}?sucursal_id=${activa.id}`))
                              if (ok) await recargar()
                            }}>
                      <Trash2 />
                    </Button>
                  )}
                </div>
              ) },
          ]}
        />
      </CardContent>
    </Card>
  )
}

/**
 * Edita el precio de un producto en una lista.
 *
 * ⚠️ **Con una sucursal elegida, guardar crea el precio DE ESA SUCURSAL**, aunque
 * la fila que se abrió fuera el precio general heredado. Es lo que se espera al
 * estar parado en una sucursal —"acá vale otra cosa"— pero cambia el resultado
 * de la operación, así que el diálogo lo dice antes de guardar en vez de que se
 * descubra viendo que el precio de la otra sucursal no se movió.
 */
function FormPrecio({ listaId, precio, sucursalId, onGuardar }: {
  listaId: number
  precio: Precio
  sucursalId: number | null
  onGuardar: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const [abierto, setAbierto] = useState(false)
  const [valor, setValor] = useState(String(precio.precio))
  const creaUnoPropio = sucursalId !== null && !precio.propio_de_sucursal

  async function guardar() {
    const ok = await onGuardar(() => api.put(`/api/listas-precio/${listaId}/precios`, {
      item_id: precio.item_id, precio: Number(valor) || 0,
      sucursal_id: sucursalId,
    }))
    if (ok) setAbierto(false)
  }

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        {/* El lápiz, como en el resto de las grillas del producto (Productos,
            Clientes, Sucursales…). Era la palabra "Editar" y desentonaba con
            todas: una columna de acciones se escanea por el dibujo, y la
            leyenda va en el `title`/`aria-label`, que es lo que además leen el
            lector de pantalla y los tests. */}
        <Button variant="outline" size="icon" title="Editar"
                aria-label={`Editar el precio de ${precio.producto}`}>
          <Pencil />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>{precio.producto}</DialogTitle></DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor="pr-valor">Precio</Label>
          <Input id="pr-valor" type="number" value={valor}
                 onChange={(e) => setValor(e.target.value)} />
        </div>
        {creaUnoPropio && (
          <p className="text-xs text-amber-600 dark:text-amber-500">
            Hoy este producto usa el precio general de la lista. Al guardar se
            crea un precio propio de esta sucursal; el general no cambia y las
            demás sucursales lo siguen usando.
          </p>
        )}
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
          <div className="grid gap-2">
            <Label htmlFor="li-nombre">Nombre</Label>
            <Input id="li-nombre" value={nombre} onChange={(e) => setNombre(e.target.value)}
                   placeholder="Mayorista" />
          </div>
          <div className="grid gap-2">
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

