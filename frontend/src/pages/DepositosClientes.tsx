/** Depósitos **de los clientes**: su pañol, su sala de racks.
 *
 *  Sólo pueden guardar equipos de ese cliente — el backend lo valida— y ninguno
 *  puede ser el predeterminado de la empresa, porque ahí van a parar equipos de
 *  cualquiera.
 *
 *  Pantalla separada de la de propios desde el 2026-08-04 (pedido 35). Acá el
 *  cliente **sí** se elige al crear, que es la diferencia real entre las dos:
 *  en la de la empresa ese campo no existe.
 *
 *  El ABM tampoco está detrás de `isAdmin` — ver el comentario de `Depositos`.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  api, ApiError, opcionesCliente, type Cliente, type Deposito,
} from '../api'
import { ConmutadorDepositos, TarjetaDeposito } from '@/components/deposito-piezas'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Building2, Check, Plus, Users } from 'lucide-react'

const TODOS = '__todos__'

export function DepositosClientes() {
  const [depositos, setDepositos] = useState<Deposito[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filtro, setFiltro] = useState(TODOS)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editando, setEditando] = useState<Deposito | null>(null)
  const [nombre, setNombre] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [clienteId, setClienteId] = useState('')
  const [activo, setActivo] = useState(true)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [aBorrar, setABorrar] = useState<Deposito | null>(null)

  useEffect(() => { cargar() }, [])

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
      // El backend filtra por un cliente concreto (`?cliente_id=`) o por
      // propios, pero no tiene un "todos los de clientes": se descarta acá.
      setDepositos(dep.filter((d) => d.cliente_id !== null))
      setClientes(cl)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  const visibles = useMemo(
    () => filtro === TODOS
      ? depositos
      : depositos.filter((d) => String(d.cliente_id) === filtro),
    [depositos, filtro],
  )

  function abrirNuevo() {
    setEditando(null)
    setNombre('')
    setDescripcion('')
    // Si hay un cliente filtrado, el alta arranca con ése — mismo criterio que
    // el alta de incidencias.
    setClienteId(filtro === TODOS ? '' : filtro)
    setActivo(true)
    setFormError(null)
    setDialogOpen(true)
  }

  function abrirEditar(d: Deposito) {
    setEditando(d)
    setNombre(d.nombre)
    setDescripcion(d.descripcion ?? '')
    setClienteId(String(d.cliente_id))
    setActivo(d.activo)
    setFormError(null)
    setDialogOpen(true)
  }

  async function guardar() {
    if (!nombre.trim() || (!editando && !clienteId)) return
    setSaving(true)
    setFormError(null)
    try {
      if (editando) {
        // El dueño no se edita: mover un depósito a otro cliente arrastraría
        // los equipos que tiene adentro, que son del cliente actual. Se crea
        // otro y se transfieren.
        await api.put(`/api/depositos/${editando.id}`, { nombre, descripcion, activo })
      } else {
        await api.post('/api/depositos', {
          nombre, descripcion, cliente_id: Number(clienteId),
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

  async function accion(fn: () => Promise<unknown>) {
    setError(null)
    try {
      await fn()
      await cargar()
    } catch (err) {
      setError(describeError(err))
    }
  }

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Mismo título e ícono que la otra pestaña, a propósito: las dos son
            "Depósitos" y quien dice en cuál estás es el conmutador de abajo.
            Un ícono distinto con el mismo título se lee como otra pantalla. */}
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Building2 className="size-5" />Depósitos
        </h2>
        <Button onClick={abrirNuevo}><Plus />Nuevo depósito</Button>
      </div>

      <ConmutadorDepositos actual="clientes" />

      <p className="text-sm text-muted-foreground">
        El pañol o la sala de racks del propio cliente. Sólo puede guardar
        equipos <strong>de ese cliente</strong>, y ninguno puede ser el
        predeterminado de la empresa.
      </p>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent className="grid gap-1.5 sm:max-w-sm">
          <Label>Cliente</Label>
          <SelectBuscable
            value={filtro}
            onChange={setFiltro}
            opciones={[{ value: TODOS, label: 'Todos los clientes' }, ...opcionesCliente(clientes)]}
            ariaLabel="Filtrar por cliente"
          />
        </CardContent>
      </Card>

      {loading ? (
        <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
      ) : visibles.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {depositos.length === 0
              ? 'Ningún cliente tiene depósitos cargados todavía.'
              : 'Ese cliente no tiene depósitos.'}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {visibles.map((d) => (
            <TarjetaDeposito key={d.id} d={d} onEditar={abrirEditar} onBorrar={setABorrar} />
          ))}
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Users className="size-4" />
              {editando ? `Editar «${editando.nombre}»` : 'Nuevo depósito de cliente'}
            </DialogTitle>
            <DialogDescription>
              {editando
                ? 'El cliente no se puede cambiar: mover el depósito arrastraría los equipos que tiene adentro.'
                : 'Sólo va a poder guardar equipos de este cliente.'}
            </DialogDescription>
          </DialogHeader>
          {formError && <p className="text-sm text-destructive">{formError}</p>}
          <div className="grid gap-4">
            <div className="grid gap-1.5">
              <Label>Cliente</Label>
              {editando ? (
                <p className="text-sm">{editando.cliente_nombre}</p>
              ) : (
                <SelectBuscable
                  value={clienteId}
                  onChange={setClienteId}
                  opciones={opcionesCliente(clientes.filter((c) => c.activo))}
                  placeholder="Elegí un cliente"
                  ariaLabel="Cliente del depósito"
                />
              )}
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="depc-nombre">Nombre</Label>
              <Input
                id="depc-nombre" value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Pañol, Sala de racks…"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="depc-desc">Descripción</Label>
              <Input
                id="depc-desc" value={descripcion}
                onChange={(e) => setDescripcion(e.target.value)}
                placeholder="Subsuelo, al lado del tablero…"
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
            <Button disabled={saving || !nombre.trim() || (!editando && !clienteId)} onClick={guardar}>
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
        onConfirm={() => {
          const d = aBorrar
          setABorrar(null)
          if (d) accion(() => api.del(`/api/depositos/${d.id}`))
        }}
      />
    </div>
  )
}
