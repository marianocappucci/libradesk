// El catálogo de consumibles: qué se compra, se vende y se consume en un
// reclamo.
//
// Separada de `Stock.tsx` a propósito. Aquella contesta "¿de dónde saco un
// plug?" —el eje es el material y la respuesta son los depósitos— y ésta
// contesta "¿qué productos manejo y a cuánto?". Son dos preguntas distintas y
// mezclarlas daba una pantalla con dos ejes.
import { useState } from 'react'
import { api } from '../api'
import { Pagina, Tabla, useDatos } from '@/components/comercial-ui'
import { useSucursal, useSucursalUrl } from '@/components/sucursal'
import { pesos } from '@/lib/format'
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
import { Package as IconoProductos } from 'lucide-react'
import { AlertTriangle, FilePlus, Pencil } from '@/components/iconos-accion'

export type Producto = {
  id: number
  nombre: string
  activo: boolean
  stock_minimo: number
  costo: number
  precio: number
  unidad: string
  descripcion: string
  categoria_id: number | null
  categoria: string
  codigo: string
  stock: number
  bajo_minimo: boolean
}

type Categoria = { id: number; nombre: string }

const UNIDADES = [
  { code: 'u', label: 'Unidad' },
  { code: 'm', label: 'Metro' },
  { code: 'caja', label: 'Caja' },
  { code: 'rollo', label: 'Rollo' },
]

export function Productos() {
  // El catálogo NO se recorta por sucursal: un producto que acá está en cero
  // sigue existiendo y hay que poder pedirlo. Lo que sí cambia con el filtro es
  // la columna de stock y, con ella, quién figura bajo el mínimo.
  const conSucursal = useSucursalUrl()
  const { activa } = useSucursal()
  const { datos: productos, error, cargando, conError } =
    useDatos<Producto[]>(conSucursal('/api/consumibles?solo_activos=false'), [])
  const { datos: categorias } = useDatos<Categoria[]>('/api/consumibles-categorias', [])
  const [busqueda, setBusqueda] = useState('')

  const filtrados = productos.filter((p) => {
    const q = busqueda.toLowerCase().trim()
    if (!q) return true
    return p.nombre.toLowerCase().includes(q)
      || p.codigo.toLowerCase().includes(q)
      || p.categoria.toLowerCase().includes(q)
  })

  const faltantes = productos.filter((p) => p.bajo_minimo).length

  if (cargando) return <p className="text-sm text-muted-foreground">Cargando…</p>

  return (
    <Pagina titulo="Productos" icono={IconoProductos} error={error}
            acciones={<FormProducto categorias={categorias} onGuardar={conError} />}>
      <div className="flex items-center gap-3 flex-wrap">
        <Input placeholder="Buscar por nombre, código o categoría…"
               value={busqueda} onChange={(e) => setBusqueda(e.target.value)}
               className="max-w-sm" />
        {faltantes > 0 && (
          <Badge variant="destructive" className="gap-1">
            <AlertTriangle className="h-3 w-3" />
            {faltantes} bajo el mínimo{activa && ` en ${activa.nombre}`}
          </Badge>
        )}
      </div>
      {activa && (
        <p className="text-xs text-muted-foreground">
          El stock es el de {activa.nombre}. El mínimo es uno solo por producto,
          así que algo puede figurar bajo el mínimo acá y sobrar en la empresa.
        </p>
      )}

      <Tabla<Producto>
        vacio="Todavía no hay productos cargados."
        filas={filtrados}
        columnas={[
          { clave: 'codigo', titulo: 'Código', ancho: '110px',
            render: (p) => <span className="tabular-nums text-muted-foreground">{p.codigo || '—'}</span> },
          { clave: 'nombre', titulo: 'Producto',
            render: (p) => (
              <div>
                <span className={p.activo ? '' : 'text-muted-foreground line-through'}>{p.nombre}</span>
                {p.categoria && <span className="ml-2 text-xs text-muted-foreground">{p.categoria}</span>}
              </div>
            ) },
          { clave: 'unidad', titulo: 'Un.', ancho: '70px', render: (p) => p.unidad },
          { clave: 'costo', titulo: 'Costo', ancho: '110px', alinear: 'derecha',
            render: (p) => pesos(p.costo) },
          { clave: 'precio', titulo: 'Precio', ancho: '110px', alinear: 'derecha',
            render: (p) => pesos(p.precio) },
          { clave: 'stock', titulo: 'Stock', ancho: '110px', alinear: 'derecha',
            render: (p) => (
              // El faltante se marca en la fila y no sólo en el contador de
              // arriba: el contador dice cuántos hay, la fila dice cuál.
              <span className={p.bajo_minimo ? 'font-semibold text-destructive' : ''}>
                {p.stock}
                {p.stock_minimo > 0 && (
                  <span className="ml-1 text-xs text-muted-foreground">/ {p.stock_minimo}</span>
                )}
              </span>
            ) },
          { clave: 'acciones', titulo: 'Acciones', ancho: '60px',
            render: (p) => <FormProducto producto={p} categorias={categorias} onGuardar={conError} /> },
        ]}
      />
    </Pagina>
  )
}

function FormProducto({ producto, categorias, onGuardar }: {
  producto?: Producto
  categorias: Categoria[]
  onGuardar: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const editando = producto !== undefined
  const [abierto, setAbierto] = useState(false)
  const [nombre, setNombre] = useState(producto?.nombre ?? '')
  const [codigo, setCodigo] = useState(producto?.codigo ?? '')
  const [costo, setCosto] = useState(String(producto?.costo ?? ''))
  const [precio, setPrecio] = useState(String(producto?.precio ?? ''))
  const [minimo, setMinimo] = useState(String(producto?.stock_minimo ?? ''))
  const [unidad, setUnidad] = useState(producto?.unidad ?? 'u')
  const [categoriaId, setCategoriaId] = useState(
    producto?.categoria_id ? String(producto.categoria_id) : 'ninguna',
  )

  async function guardar() {
    const cuerpo = {
      nombre: nombre.trim(),
      costo: Number(costo) || 0,
      precio: Number(precio) || 0,
      stock_minimo: Number(minimo) || 0,
      unidad,
      categoria_id: categoriaId === 'ninguna' ? null : Number(categoriaId),
      activo: producto?.activo ?? true,
      // El código sólo viaja en el alta: cambiarlo después es otra operación
      // (un producto puede tener varios códigos) y tiene su propio endpoint.
      ...(editando ? {} : { codigo: codigo.trim() }),
    }
    const ok = await onGuardar(() => (
      editando
        ? api.put(`/api/consumibles/${producto.id}`, cuerpo)
        : api.post('/api/consumibles', cuerpo)
    ))
    if (ok) setAbierto(false)
  }

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        {/* `outline` y no `ghost`: es el tile gris que usan las otras ~39
            columnas de acciones del producto (ver el `compoundVariants` de
            `ui/button.tsx`). Era el único botón de fila sin recuadro, y se nota
            al lado de Listas de precios, que es su vecina de menú. */}
        {editando
          ? <Button variant="outline" size="icon" title="Editar" aria-label="Editar producto">
              <Pencil className="h-4 w-4" />
            </Button>
          : <Button><FilePlus className="mr-2 h-4 w-4" /> Nuevo producto</Button>}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{editando ? 'Editar producto' : 'Nuevo producto'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid gap-2">
            <Label htmlFor="p-nombre">Nombre</Label>
            <Input id="p-nombre" value={nombre} onChange={(e) => setNombre(e.target.value)}
                   placeholder="PLUG RJ 45 CAT 6" />
          </div>
          {!editando && (
            <div className="grid gap-2">
              <Label htmlFor="p-codigo">Código</Label>
              <Input id="p-codigo" value={codigo} onChange={(e) => setCodigo(e.target.value)}
                     placeholder="10000315" />
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label htmlFor="p-costo">Costo</Label>
              <Input id="p-costo" type="number" value={costo}
                     onChange={(e) => setCosto(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="p-precio">Precio de venta</Label>
              <Input id="p-precio" type="number" value={precio}
                     onChange={(e) => setPrecio(e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label htmlFor="p-minimo">Stock mínimo</Label>
              <Input id="p-minimo" type="number" value={minimo}
                     onChange={(e) => setMinimo(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="p-unidad">Unidad</Label>
              <Select value={unidad} onValueChange={setUnidad}>
                <SelectTrigger id="p-unidad"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {UNIDADES.map((u) => (
                    <SelectItem key={u.code} value={u.code}>{u.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="p-categoria">Categoría</Label>
            <Select value={categoriaId} onValueChange={setCategoriaId}>
              <SelectTrigger id="p-categoria"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ninguna">Sin categoría</SelectItem>
                {categorias.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>{c.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancelar</Button></DialogClose>
          <Button onClick={guardar} disabled={!nombre.trim()}>Guardar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
