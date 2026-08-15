// Sucursales de la empresa.
//
// **Sucursal es un eje transversal** (decidido el 2026-08-14). Esta pantalla es
// el ABM; lo que cada módulo hace con la sucursal está en `components/sucursal.tsx`.
//
// **No hay botón de borrar y no es un olvido**: las cuatro columnas `branch_id`
// del motor no tienen FK contra esta tabla, así que un borrado dejaría depósitos,
// ventas, órdenes y precios apuntando a un id inexistente, sin error y sin
// cascada. Lo que hay es baja lógica, y encima gateada: una sucursal con
// depósitos de stock activos no se puede dar de baja, porque ese stock quedaría
// invisible sin que nadie lo haya movido.
import { useState } from 'react'
import { api } from '../api'
import { Pagina, Tabla, useDatos } from '@/components/comercial-ui'
import { useSucursal, type Sucursal } from '@/components/sucursal'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { MapPin } from 'lucide-react'
import { FilePlus } from '@/components/iconos-accion'

//: La respuesta trae además cuántos depósitos de stock activos cuelgan de cada
//: sucursal. Se muestra en la grilla porque es exactamente lo que impide darla
//: de baja: sin el número, el 422 aparece sin explicación a la vista.
type SucursalFila = Sucursal & { activa: boolean; depositos: number }

export function Sucursales() {
  const { datos, error, cargando, conError } =
    useDatos<SucursalFila[]>('/api/sucursales?solo_activas=false', [])
  const { recargar: recargarContexto } = useSucursal()

  // El selector del encabezado vive en un contexto propio: sin esto, un alta o
  // una baja no se reflejan ahí hasta recargar la página entera.
  async function guardarYRefrescar(fn: () => Promise<unknown>) {
    const ok = await conError(fn)
    if (ok) await recargarContexto()
    return ok
  }

  if (cargando) return <p className="text-sm text-muted-foreground">Cargando…</p>

  return (
    <Pagina titulo="Sucursales" icono={MapPin} error={error}
            acciones={<FormSucursal onGuardar={guardarYRefrescar} />}>
      <p className="text-sm text-muted-foreground">
        El stock, los depósitos, las ventas, las compras y las listas de precio
        se filtran por la sucursal elegida arriba. La mesa de ayuda y la cuenta
        corriente no: el saldo de un cliente es uno solo entre sucursales.
      </p>
      <Tabla<SucursalFila>
        vacio="Todavía no hay sucursales cargadas."
        filas={datos}
        columnas={[
          { clave: 'codigo', titulo: 'Código', ancho: '110px',
            render: (s) => <span className="tabular-nums text-muted-foreground">{s.codigo || '—'}</span> },
          { clave: 'nombre', titulo: 'Sucursal',
            render: (s) => (
              <span className={s.activa ? '' : 'text-muted-foreground line-through'}>
                {s.nombre}
              </span>
            ) },
          { clave: 'direccion', titulo: 'Dirección',
            render: (s) => <span className="text-muted-foreground">{s.direccion || '—'}</span> },
          { clave: 'depositos', titulo: 'Depósitos', ancho: '110px',
            render: (s) => <span className="tabular-nums">{s.depositos}</span> },
          { clave: 'acciones', titulo: '', ancho: '220px',
            render: (s) => (
              <div className="flex justify-end gap-2">
                <FormSucursal sucursal={s} onGuardar={guardarYRefrescar} />
                <Button variant="outline" size="sm"
                        onClick={() => guardarYRefrescar(() =>
                          api.post(`/api/sucursales/${s.id}/estado`, { activa: !s.activa }))}>
                  {s.activa ? 'Dar de baja' : 'Reactivar'}
                </Button>
              </div>
            ) },
        ]}
      />
    </Pagina>
  )
}

function FormSucursal({ sucursal, onGuardar }: {
  sucursal?: SucursalFila
  onGuardar: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const editando = sucursal !== undefined
  const [abierto, setAbierto] = useState(false)
  const [nombre, setNombre] = useState(sucursal?.nombre ?? '')
  const [codigo, setCodigo] = useState(sucursal?.codigo ?? '')
  const [direccion, setDireccion] = useState(sucursal?.direccion ?? '')

  async function guardar() {
    const cuerpo = { nombre: nombre.trim(), codigo, direccion }
    const ok = await onGuardar(() =>
      editando
        ? api.put(`/api/sucursales/${sucursal.id}`, cuerpo)
        : api.post('/api/sucursales', cuerpo))
    if (!ok) return
    setAbierto(false)
    if (!editando) { setNombre(''); setCodigo(''); setDireccion('') }
  }

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        {editando
          ? <Button variant="outline" size="sm">Editar</Button>
          : <Button><FilePlus className="mr-2 h-4 w-4" /> Nueva sucursal</Button>}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{editando ? 'Editar sucursal' : 'Nueva sucursal'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid gap-2">
            <Label htmlFor="s-nombre">Nombre</Label>
            <Input id="s-nombre" value={nombre} onChange={(e) => setNombre(e.target.value)}
                   placeholder="CHIVILCOY" />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="s-codigo">Código</Label>
            <Input id="s-codigo" value={codigo} onChange={(e) => setCodigo(e.target.value)}
                   placeholder="CHI" />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="s-dir">Dirección</Label>
            <Input id="s-dir" value={direccion} onChange={(e) => setDireccion(e.target.value)} />
          </div>
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
