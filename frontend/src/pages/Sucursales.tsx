// Sucursales de la empresa.
//
// 🟡 **Alcance corto y declarado.** El ABM existe, la sucursal se elige en el
// encabezado y viaja en el alta de depósitos, ventas y órdenes de compra — pero
// **ninguna pantalla filtra por sucursal todavía**. La nota de abajo lo dice en
// la pantalla misma en vez de esconderlo, porque una demo donde el selector
// parece filtrar y no filtra es peor que una sin selector.
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
import MapPin from '~icons/fluent-color/location-ripple-16'
import Plus from '~icons/fluent-color/add-circle-16'

export function Sucursales() {
  const { datos, error, cargando, conError } = useDatos<Sucursal[]>('/api/sucursales?solo_activas=false', [])
  const { recargar: recargarContexto } = useSucursal()

  if (cargando) return <p className="text-sm text-muted-foreground">Cargando…</p>

  return (
    <Pagina titulo="Sucursales" icono={MapPin} error={error}
            acciones={
              <FormSucursal onGuardar={async (fn) => {
                const ok = await conError(fn)
                // El selector del encabezado vive en un contexto propio: sin
                // esto, la sucursal recién creada no aparece ahí hasta recargar
                // la página entera.
                if (ok) await recargarContexto()
                return ok
              }} />
            }>
      <p className="text-sm text-muted-foreground">
        Los depósitos de stock, las ventas y las órdenes de compra se pueden
        asignar a una sucursal. El resto de las pantallas todavía no filtra por
        sucursal.
      </p>
      <Tabla<Sucursal>
        vacio="Todavía no hay sucursales cargadas."
        filas={datos}
        columnas={[
          { clave: 'codigo', titulo: 'Código', ancho: '110px',
            render: (s) => <span className="tabular-nums text-muted-foreground">{s.codigo || '—'}</span> },
          { clave: 'nombre', titulo: 'Sucursal', render: (s) => s.nombre },
          { clave: 'direccion', titulo: 'Dirección',
            render: (s) => <span className="text-muted-foreground">{s.direccion || '—'}</span> },
        ]}
      />
    </Pagina>
  )
}

function FormSucursal({ onGuardar }: {
  onGuardar: (accion: () => Promise<unknown>) => Promise<boolean>
}) {
  const [abierto, setAbierto] = useState(false)
  const [nombre, setNombre] = useState('')
  const [codigo, setCodigo] = useState('')
  const [direccion, setDireccion] = useState('')

  async function guardar() {
    const ok = await onGuardar(() => api.post('/api/sucursales', {
      nombre: nombre.trim(), codigo, direccion,
    }))
    if (ok) { setAbierto(false); setNombre(''); setCodigo(''); setDireccion('') }
  }

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button><Plus className="mr-2 h-4 w-4" /> Nueva sucursal</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Nueva sucursal</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="s-nombre">Nombre</Label>
            <Input id="s-nombre" value={nombre} onChange={(e) => setNombre(e.target.value)}
                   placeholder="CHIVILCOY" />
          </div>
          <div>
            <Label htmlFor="s-codigo">Código</Label>
            <Input id="s-codigo" value={codigo} onChange={(e) => setCodigo(e.target.value)}
                   placeholder="CHI" />
          </div>
          <div>
            <Label htmlFor="s-dir">Dirección</Label>
            <Input id="s-dir" value={direccion} onChange={(e) => setDireccion(e.target.value)} />
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
