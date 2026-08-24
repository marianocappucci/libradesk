/** Los números con los que **otros** llaman a un equipo.
 *
 *  El caso: el cliente le alquila fotocopiadoras a un tercero y, para pedirle un
 *  tóner, hay que darle el número interno de ESE tercero. También está el
 *  patrimonial del cliente. Son identificadores ajenos y son varios, así que no
 *  entran en un campo del formulario del equipo — ver `EquipoReferencia` en el
 *  backend, que explica por qué es una tabla.
 *
 *  **Diálogo propio y no una sección del alta**: una referencia cuelga de un
 *  equipo que ya existe (`POST /api/equipos/{id}/referencias`), así que en el
 *  alta no habría dónde colgarla. Y son dos campos que se cargan una vez y no se
 *  vuelven a tocar; meterlos en el formulario que se abre todos los días para
 *  corregir un sector sería cobrarle ese espacio a todas las ediciones.
 *
 *  No hay edición, sólo alta y baja: son dos campos y ninguno es historia. Un
 *  número mal tipeado es un error de carga, no un hecho que haya pasado.
 */
import { useEffect, useState } from 'react'
import {
  api, ApiError, opcionesProveedor,
  type Equipo, type Proveedor, type ReferenciaEquipo,
} from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
// `PlusCircle` y no `FilePlus`: se le agrega algo a un equipo que ya existe, no
// se crea un registro nuevo de la pantalla — ver el vocabulario en
// `components/iconos-accion.tsx`.
import { PlusCircle, Trash2 } from '@/components/iconos-accion'

// El número es del propio cliente (patrimonial, inventario interno). Radix no
// admite un <SelectItem value="">, misma convención que `SIN_DEPOSITO`.
const DEL_CLIENTE = '__cliente__'

export function DialogoDeReferencias({ equipo, proveedores, onClose, onGuardado }: {
  equipo: Equipo | null
  proveedores: Proveedor[]
  onClose: () => void
  /** Se llama cuando algo cambió, para que la lista de equipos se refresque:
   *  las referencias viajan dentro del equipo. */
  onGuardado: () => void
}) {
  const [referencias, setReferencias] = useState<ReferenciaEquipo[]>([])
  const [etiqueta, setEtiqueta] = useState('N° interno')
  const [valor, setValor] = useState('')
  const [proveedorId, setProveedorId] = useState(DEL_CLIENTE)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (equipo === null) return
    setError(null)
    setValor('')
    // El default es el dueño del equipo: si la máquina es de un tercero, el
    // número que se va a cargar es casi siempre el de ese tercero.
    setProveedorId(equipo.proveedor_id === null ? DEL_CLIENTE : String(equipo.proveedor_id))
    setEtiqueta(equipo.proveedor_id === null ? 'Patrimonial' : 'N° interno')
    setReferencias(equipo.referencias)
  }, [equipo])

  if (equipo === null) return null

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function agregar() {
    if (equipo === null) return
    setSaving(true)
    setError(null)
    try {
      const creada = await api.post<ReferenciaEquipo>(
        `/api/equipos/${equipo.id}/referencias`,
        {
          etiqueta,
          valor,
          proveedor_id: proveedorId === DEL_CLIENTE ? null : Number(proveedorId),
        },
      )
      setReferencias((previas) => [...previas, creada])
      setValor('')
      onGuardado()
    } catch (err) {
      // El 409 del duplicado dice con qué equipo chocó: es lo que hay que
      // mostrar tal cual, no traducir a "no se pudo guardar".
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function borrar(referencia: ReferenciaEquipo) {
    if (equipo === null) return
    setError(null)
    try {
      await api.del(`/api/equipos/${equipo.id}/referencias/${referencia.id}`)
      setReferencias((previas) => previas.filter((r) => r.id !== referencia.id))
      onGuardado()
    } catch (err) {
      setError(describeError(err))
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Identificadores del equipo</DialogTitle>
          <DialogDescription>
            Los números con los que lo llaman los demás: el interno del proveedor
            —el que pide para despachar un insumo— y el patrimonial del cliente.
          </DialogDescription>
        </DialogHeader>

        {referencias.length === 0 ? (
          <p className="py-2 text-sm text-muted-foreground">
            Todavía no tiene ninguno.
          </p>
        ) : (
          <ul className="divide-y rounded-md border">
            {referencias.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{r.valor}</Badge>
                  <span className="text-sm">{r.etiqueta}</span>
                  <span className="text-xs text-muted-foreground">
                    {r.proveedor_nombre ?? 'del cliente'}
                  </span>
                </div>
                <Button
                  size="sm" variant="ghost"
                  title="Borrar el identificador"
                  onClick={() => borrar(r)}
                >
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-2">
            <Label htmlFor="ref-etiqueta">Cómo se llama</Label>
            <Input
              id="ref-etiqueta" value={etiqueta}
              onChange={(e) => setEtiqueta(e.target.value)}
              placeholder="N° interno"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="ref-valor">Número</Label>
            <Input
              id="ref-valor" value={valor}
              onChange={(e) => setValor(e.target.value)}
              placeholder="4471"
            />
          </div>
          <div className="grid gap-2 sm:col-span-2">
            <Label>De quién es ese número</Label>
            <SelectBuscable
              value={proveedorId}
              onChange={setProveedorId}
              opciones={[
                { value: DEL_CLIENTE, label: 'Del cliente (patrimonial)' },
                ...opcionesProveedor(proveedores),
              ]}
              placeholder="Del cliente"
              ariaLabel="De quién es ese número"
            />
          </div>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <DialogFooter>
          <DialogClose asChild><Button type="button" variant="outline">Cerrar</Button></DialogClose>
          <Button onClick={agregar} disabled={saving || !valor.trim()}>
            <PlusCircle />Agregar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
