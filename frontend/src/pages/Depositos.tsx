/** Depósitos **de la empresa**: el taller, el depósito central.
 *
 *  Acá va el equipo que se retira de un cliente. Uno de ellos es el
 *  **predeterminado**: el destino de "vuelve a depósito" cuando nadie elige
 *  cuál, y por eso tiene que ser propio — ese equipo puede ser de cualquier
 *  cliente.
 *
 *  Pantalla separada de la de clientes desde el 2026-08-04 (pedido 35). Antes
 *  eran dos secciones de una sola, y el formulario tenía que preguntar de quién
 *  era el depósito. Separadas, cada una lo sabe.
 *
 *  🔴 **El ABM no está detrás de `isAdmin`**, y eso es un cambio deliberado.
 *  Hasta el 2026-08-04 los botones se le escondían a todo el que no fuera admin
 *  — pero el backend monta este router con `staff_or_admin`, igual que equipos
 *  y sectores. O sea que cualquier staff **ya podía** crear y borrar depósitos
 *  por la API: esconder los botones no restringía nada, sólo hacía que el
 *  módulo se viera roto. Si se decide que esto sea admin-only, el lugar es el
 *  backend (`app/main.py`), no acá.
 */
import { useEffect, useState } from 'react'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import { api, ApiError, type Deposito } from '../api'
import { ConmutadorDepositos, TarjetaDeposito } from '@/components/deposito-piezas'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Building2 } from 'lucide-react'
import { Check, FilePlus } from '@/components/iconos-accion'
import { TituloPantalla } from '@/components/titulo-pantalla'

export function Depositos() {
  const [depositos, setDepositos] = useState<Deposito[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editando, setEditando] = useState<Deposito | null>(null)
  const [nombre, setNombre] = useState('')
  const [descripcion, setDescripcion] = useState('')
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
      // `propios=true` lo filtra el backend, no el navegador: con muchos
      // depósitos de clientes, traerlos todos para descartarlos acá sería
      // pedir una lista entera para mostrar la mitad.
      setDepositos(await api.get<Deposito[]>('/api/depositos?propios=true'))
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
    setActivo(true)
    setFormError(null)
    setDialogOpen(true)
  }

  function abrirEditar(d: Deposito) {
    setEditando(d)
    setNombre(d.nombre)
    setDescripcion(d.descripcion ?? '')
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
        await api.put(`/api/depositos/${editando.id}`, { nombre, descripcion, activo })
      } else {
        // `cliente_id: null` = de la empresa. Esta pantalla no pregunta de
        // quién es porque ya lo sabe.
        await api.post('/api/depositos', { nombre, descripcion, cliente_id: null })
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
      {/* "Depósitos" y no "Depósitos de la empresa": el título nombra la
          sección y el conmutador de abajo dice en cuál de las dos estás,
          mismo patrón que Configuración. Mientras el título cambiaba con la
          pestaña, el ítem del menú no podía llamarse como ninguna de las dos
          pantallas — de ahí el "Depósitos de equipos" que no aparecía en
          ningún lado adentro. El párrafo de abajo sigue siendo distinto por
          pestaña: eso es lo que explica dónde estás parado. */}
      <EncabezadoDePantalla titulo={<TituloPantalla icono={Building2}>Depósitos</TituloPantalla>}>
        <Button onClick={abrirNuevo}><FilePlus />Nuevo depósito</Button>
      </EncabezadoDePantalla>

      <ConmutadorDepositos actual="propios" />

      <p className="text-sm text-muted-foreground">
        El taller y los depósitos propios. Acá va el equipo que se retira de un
        cliente, y el <strong>predeterminado</strong> es a dónde va cuando nadie
        elige destino.
      </p>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading ? (
        <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
      ) : depositos.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No hay depósitos propios todavía. El primero que cargues queda como
            predeterminado.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {depositos.map((d) => (
            <TarjetaDeposito
              key={d.id}
              d={d}
              onEditar={abrirEditar}
              onBorrar={setABorrar}
              onPredeterminar={(x) => accion(() => api.post(`/api/depositos/${x.id}/set-default`))}
            />
          ))}
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Building2 className="size-4" />
              {editando ? `Editar «${editando.nombre}»` : 'Nuevo depósito de la empresa'}
            </DialogTitle>
            <DialogDescription>
              Recibe equipos de cualquier cliente. Para un depósito del propio
              cliente, usá la otra pestaña.
            </DialogDescription>
          </DialogHeader>
          {formError && <p className="text-sm text-destructive">{formError}</p>}
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="dep-nombre">Nombre</Label>
              <Input
                id="dep-nombre" value={nombre} autoFocus
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Taller, Depósito central…"
              />
            </div>
            <div className="grid gap-2">
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
        onConfirm={() => {
          const d = aBorrar
          setABorrar(null)
          if (d) accion(() => api.del(`/api/depositos/${d.id}`))
        }}
      />
    </div>
  )
}
