/** Depósitos: dónde está un equipo cuando no está instalado en el puesto.
 *
 *  Dos dueños posibles y una sola pantalla: los **propios** de la empresa (el
 *  taller, el depósito central) y los **de un cliente** (su pañol, su sala de
 *  racks). Se listan separados porque son cosas distintas para quien mira —
 *  "qué tengo yo guardado" y "qué tiene guardado el cliente"— pero son la
 *  misma entidad; ver `app/services/depositos.py`.
 *
 *  Mismo formato que Contalibra: tarjetas con el conteo de lo que hay adentro,
 *  alta y edición en un diálogo, uno marcado como predeterminado y borrado
 *  sólo si está vacío.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, opcionesCliente, type Cliente, type Deposito } from '../api'
import { useAuth } from '../context/AuthContext'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Building2, Check, Eye, Monitor, Pencil, Plus, Star, Trash2, Users } from 'lucide-react'

const EMPRESA = '__empresa__'

export function Depositos() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [depositos, setDepositos] = useState<Deposito[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editando, setEditando] = useState<Deposito | null>(null)
  const [nombre, setNombre] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [duenio, setDuenio] = useState(EMPRESA)
  const [activo, setActivo] = useState(true)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const [aBorrar, setABorrar] = useState<Deposito | null>(null)

  useEffect(() => {
    cargar()
  }, [])

  function describeError(err: unknown): string {
    return err instanceof ApiError ? err.detail : 'Error de conexión.'
  }

  async function cargar() {
    setLoading(true)
    setError(null)
    try {
      const [dep, cl] = await Promise.all([
        api.get<Deposito[]>('/api/depositos'),
        api.get<Cliente[]>('/api/clientes'),
      ])
      setDepositos(dep)
      setClientes(cl)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  function abrirNuevo() {
    setEditando(null)
    setNombre('')
    setDescripcion('')
    setDuenio(EMPRESA)
    setActivo(true)
    setFormError(null)
    setDialogOpen(true)
  }

  function abrirEditar(d: Deposito) {
    setEditando(d)
    setNombre(d.nombre)
    setDescripcion(d.descripcion ?? '')
    setDuenio(d.cliente_id === null ? EMPRESA : String(d.cliente_id))
    setActivo(d.activo)
    setFormError(null)
    setDialogOpen(true)
  }

  async function guardar() {
    if (!nombre.trim()) return
    setSaving(true)
    setFormError(null)
    try {
      if (editando) {
        // El dueño no se edita: mover un depósito de la empresa a un cliente
        // movería con él todos los equipos que tiene adentro, que puede ser
        // parque de varios clientes distintos. Se crea otro y se transfieren.
        await api.put(`/api/depositos/${editando.id}`, {
          nombre, descripcion, activo,
        })
      } else {
        await api.post('/api/depositos', {
          nombre,
          descripcion,
          cliente_id: duenio === EMPRESA ? null : Number(duenio),
        })
      }
      setDialogOpen(false)
      await cargar()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function predeterminar(d: Deposito) {
    setError(null)
    try {
      await api.post(`/api/depositos/${d.id}/set-default`)
      await cargar()
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function borrar(d: Deposito) {
    setError(null)
    try {
      await api.del(`/api/depositos/${d.id}`)
      await cargar()
    } catch (err) {
      setError(describeError(err))
    }
  }

  const propios = depositos.filter((d) => d.cliente_id === null)
  const deClientes = depositos.filter((d) => d.cliente_id !== null)

  function Tarjeta({ d }: { d: Deposito }) {
    return (
      <Card className={d.activo ? '' : 'opacity-60'}>
        <CardContent className="grid gap-3">
          <div>
            <p className="flex items-center gap-2 font-semibold">
              <Building2 className="size-4 text-primary" />{d.nombre}
            </p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {d.es_default && <Badge>Predeterminado</Badge>}
              {!d.activo && <Badge variant="secondary">Inactivo</Badge>}
              {d.cliente_nombre && <Badge variant="outline">{d.cliente_nombre}</Badge>}
            </div>
          </div>
          {d.descripcion && <p className="text-sm text-muted-foreground">{d.descripcion}</p>}
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Monitor className="size-4" />
            {d.total_equipos} equipo{d.total_equipos !== 1 ? 's' : ''} adentro
          </p>
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline">
              <Link to={`/depositos/${d.id}`}><Eye />Ver equipos</Link>
            </Button>
            {isAdmin && (
              <>
                <Button size="sm" variant="outline" onClick={() => abrirEditar(d)}>
                  <Pencil />Editar
                </Button>
                {d.cliente_id === null && !d.es_default && (
                  <Button
                    size="sm" variant="outline"
                    title="Usar como depósito por defecto al retirar un equipo"
                    onClick={() => predeterminar(d)}
                  >
                    <Star />Predeterminar
                  </Button>
                )}
                <Button
                  size="sm" variant="outline"
                  className="text-destructive hover:text-destructive"
                  onClick={() => setABorrar(d)}
                >
                  <Trash2 />
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    )
  }

  function Seccion({ titulo, descripcion, icono, items, vacio }: {
    titulo: string
    descripcion: string
    icono: React.ReactNode
    items: Deposito[]
    vacio: string
  }) {
    return (
      <div className="grid gap-2">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold">{icono}{titulo}</h3>
          <p className="text-sm text-muted-foreground">{descripcion}</p>
        </div>
        {items.length === 0 ? (
          <Card>
            <CardContent className="py-6 text-center text-sm text-muted-foreground">
              {vacio}
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((d) => <Tarjeta key={d.id} d={d} />)}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Building2 className="size-5" />Depósitos
        </h2>
        {isAdmin && <Button onClick={abrirNuevo}><Plus />Nuevo depósito</Button>}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading ? (
        <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
      ) : (
        <>
          <Seccion
            titulo="De la empresa"
            descripcion="El taller y los depósitos propios. Acá va el equipo retirado de un cliente."
            icono={<Building2 className="size-4 text-primary" />}
            items={propios}
            vacio="No hay depósitos propios todavía."
          />
          <Seccion
            titulo="De clientes"
            descripcion="Los depósitos del propio cliente. Sólo pueden guardar equipos de ese cliente."
            icono={<Users className="size-4 text-primary" />}
            items={deClientes}
            vacio="Ningún cliente tiene depósitos cargados."
          />
        </>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Building2 className="size-4" />
              {editando ? 'Editar depósito' : 'Nuevo depósito'}
            </DialogTitle>
            <DialogDescription>
              {editando
                ? 'El dueño no se puede cambiar: mover el depósito arrastraría los equipos que tiene adentro.'
                : 'Un depósito de la empresa recibe equipos de cualquier cliente; uno de cliente, sólo los suyos.'}
            </DialogDescription>
          </DialogHeader>
          {formError && <p className="text-sm text-destructive">{formError}</p>}
          <div className="grid gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="dep-nombre">Nombre</Label>
              <Input
                id="dep-nombre" value={nombre} autoFocus
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Taller, Depósito central…"
              />
            </div>
            {!editando && (
              <div className="grid gap-1.5">
                <Label>Dueño</Label>
                <SelectBuscable
                  value={duenio}
                  onChange={setDuenio}
                  opciones={[
                    { value: EMPRESA, label: 'La empresa' },
                    ...opcionesCliente(clientes.filter((c) => c.activo)),
                  ]}
                  ariaLabel="Dueño del depósito"
                />
              </div>
            )}
            <div className="grid gap-1.5">
              <Label htmlFor="dep-desc">Descripción</Label>
              <Input
                id="dep-desc" value={descripcion}
                onChange={(e) => setDescripcion(e.target.value)}
                placeholder="Estantería del fondo, sala de racks…"
              />
            </div>
            {editando && (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox" checked={activo}
                  onChange={(e) => setActivo(e.target.checked)}
                />
                Activo
              </label>
            )}
          </div>
          <DialogFooter>
            <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
            <Button disabled={saving || !nombre.trim()} onClick={guardar}>
              <Check />{saving ? 'Guardando…' : 'Guardar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={aBorrar !== null}
        onOpenChange={(open) => !open && setABorrar(null)}
        title={`¿Eliminar el depósito «${aBorrar?.nombre}»?`}
        description="Sólo se puede borrar si está vacío. Si tiene equipos adentro hay que moverlos primero: sacarlos automáticamente sería moverlos a ninguna parte."
        onConfirm={() => { const d = aBorrar; setABorrar(null); if (d) borrar(d) }}
      />
    </div>
  )
}
