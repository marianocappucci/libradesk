// Proveedores: a quién se le compra y a quién se le manda un equipo a service.
//
// Vivía como pestaña de Configuración, y desde el módulo comercial el menú lo
// ofrece dentro de Compras. Las dos cosas juntas daban el efecto que reportó el
// usuario (2026-08-13): entrar por Compras → Proveedores aterrizaba en la
// pantalla de Configuración —mismo título, mismo conmutador con Empresa, Datos
// / Backup y todo lo demás— y el listado quedaba como una tarjeta más al pie.
//
// Ahora es una pantalla propia. Configuración conserva lo que de verdad es
// configuración; el catálogo de proveedores vive donde lo busca quien carga una
// orden de compra. `/configuracion/proveedores` sigue resolviendo: redirige acá,
// para no romper links viejos.
//
// El ABM no está detrás de admin, igual que cuando era pestaña: el router del
// backend monta `proveedores.router` con `staff_or_admin`, así que cualquier
// staff ya podía crear, editar y borrar por la API. Si se decide restringirlo,
// el lugar es el backend, no esta pantalla.
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import { useEffect, useState } from 'react'
import { api, ApiError, type Proveedor } from '../api'
import { Button } from '@/components/ui/button'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Truck } from 'lucide-react'
import { FilePlus, Pencil, Trash2 } from '@/components/iconos-accion'
import { TituloPantalla } from '@/components/titulo-pantalla'

/** Los cuatro campos editables de un proveedor, como strings del formulario
 *  (el backend recibe null donde acá hay cadena vacía). */
type FormProveedor = {
  nombre: string
  contacto: string
  telefono: string
  email: string
}

/** El listado de proveedores.
 *
 *  Un proveedor **con reparaciones no se borra, se desactiva**: la reparación
 *  histórica lo sigue nombrando, y sin él el registro pierde justamente el dato
 *  que lo hacía útil. Mismo criterio que los clientes. */
export function Proveedores() {
  const [proveedores, setProveedores] = useState<Proveedor[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [nuevo, setNuevo] = useState<FormProveedor | null>(null)
  const [editando, setEditando] = useState<(FormProveedor & { id: number }) | null>(null)
  const [aBorrar, setABorrar] = useState<Proveedor | null>(null)

  useEffect(() => {
    recargar()
  }, [])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function recargar() {
    try {
      setProveedores(await api.get<Proveedor[]>('/api/proveedores'))
      setError(null)
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function guardar() {
    const datos = editando ?? nuevo
    if (!datos || !datos.nombre.trim()) return
    setGuardando(true)
    setError(null)
    try {
      const payload = {
        nombre: datos.nombre.trim(),
        contacto: datos.contacto.trim() || null,
        telefono: datos.telefono.trim() || null,
        email: datos.email.trim() || null,
      }
      if (editando) await api.put(`/api/proveedores/${editando.id}`, payload)
      else await api.post('/api/proveedores', payload)
      setNuevo(null)
      setEditando(null)
      await recargar()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setGuardando(false)
    }
  }

  async function toggleActivo(p: Proveedor) {
    setError(null)
    try {
      await api.post(`/api/proveedores/${p.id}/${p.activo ? 'desactivar' : 'activar'}`, {})
      await recargar()
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function borrar(p: Proveedor) {
    setError(null)
    try {
      await api.del(`/api/proveedores/${p.id}`)
      await recargar()
    } catch (err) {
      // El 409 del backend dice cuántas reparaciones lo usan. No lo decide un
      // `except IntegrityError`, que con el pragma de FKs apagado nunca se
      // dispararía — lo cuenta el repositorio.
      setError(describeError(err))
    }
  }

  // Los dos estados que abren el modal, en una sola variable: el alta y la
  // edición comparten formulario, así que comparten diálogo.
  const editandoDatos = editando ?? nuevo
  const abierto = editandoDatos !== null

  function cerrar() {
    setNuevo(null)
    setEditando(null)
  }

  return (
    <div className="grid gap-4">
      {/* El alta va arriba y a la derecha, como en Clientes y Equipos. Estaba
          dentro de la tarjeta, debajo de un `CardDescription` de cuatro
          líneas, y en una notebook había que bajar la vista para encontrarla
          (reporte del usuario, 2026-08-13). */}
      <EncabezadoDePantalla titulo={<TituloPantalla icono={Truck}>Proveedores</TituloPantalla>}>
        <Button
          onClick={() => setNuevo({ nombre: '', contacto: '', telefono: '', email: '' })}
        >
          <FilePlus />Nuevo proveedor
        </Button>
      </EncabezadoDePantalla>

      <Card>
        <CardHeader>
          <CardDescription>
            A quién se le compra, y a quién se le manda un equipo cuando sale a
            service. Son una tabla y no un texto libre para que “Compu Service”
            y “compuservice” no sean dos proveedores distintos — si lo fueran,
            no se podría saber cuánto tarda cada uno en devolver.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {/* El error de una acción del listado —activar, borrar— se lee acá.
              El del guardado va adentro del modal, que es donde está la vista
              cuando falla. */}
          {error && !abierto && <p className="text-sm text-destructive">{error}</p>}

          {proveedores === null ? (
            <p className="py-4 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : proveedores.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              Todavía no hay proveedores. Hasta que haya alguno, un envío a service
              se registra sin decir a dónde fue el equipo.
            </p>
          ) : (
            <ul className="divide-y rounded-md border">
              {proveedores.map((p) => (
                <li key={p.id} className="flex items-center gap-2 px-3 py-2">
                  <div className="grid flex-1 gap-0.5">
                    <span className="text-sm font-medium">{p.nombre}</span>
                    <span className="text-xs text-muted-foreground">
                      {[p.contacto, p.telefono, p.email].filter(Boolean).join(' · ') || '—'}
                    </span>
                  </div>
                  {/* El badge alterna activo/inactivo. `aria-pressed` y no sólo
                      el color: sin él es un `<span>` con onClick, invisible
                      para el teclado y para un lector de pantalla. */}
                  <BadgeEstado
                    asChild
                    tono={p.activo ? 'ok' : 'neutro'}
                  >
                    <button
                      type="button"
                      aria-pressed={p.activo}
                      aria-label={`${p.activo ? 'Desactivar' : 'Activar'} ${p.nombre}`}
                      className="cursor-pointer"
                      onClick={() => toggleActivo(p)}
                    >
                      {p.activo ? 'Activo' : 'Inactivo'}
                    </button>
                  </BadgeEstado>
                  <Button
                    size="icon" variant="outline" className="size-8"
                    title="Editar" aria-label={`Editar ${p.nombre}`}
                    onClick={() => setEditando({
                      id: p.id, nombre: p.nombre,
                      contacto: p.contacto ?? '', telefono: p.telefono ?? '',
                      email: p.email ?? '',
                    })}
                  ><Pencil /></Button>
                  <Button
                    size="icon" variant="outline"
                    className="size-8 text-destructive hover:text-destructive"
                    title="Eliminar" aria-label={`Eliminar ${p.nombre}`}
                    onClick={() => setABorrar(p)}
                  ><Trash2 /></Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>

        {/* Editar abre en modal y no expande la fila (pedido del humano,
            2026-08-15). Expandido, el formulario empujaba el resto del listado
            hacia abajo y la fila que se estaba editando quedaba sin su
            contexto. Alta y edición comparten el diálogo porque son el mismo
            formulario. */}
        <Dialog open={abierto} onOpenChange={(o) => { if (!o) cerrar() }}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>
                {editando ? `Editar ${editando.nombre}` : 'Nuevo proveedor'}
              </DialogTitle>
            </DialogHeader>
            {editandoDatos && (
              <FormularioProveedor
                datos={editandoDatos}
                onChange={(d) => (editando
                  ? setEditando({ ...d, id: editando.id })
                  : setNuevo(d))}
                onSubmit={guardar}
                onCancel={cerrar}
                guardando={guardando}
                error={error}
              />
            )}
          </DialogContent>
        </Dialog>

        <ConfirmDialog
          open={aBorrar !== null}
          onOpenChange={(open) => !open && setABorrar(null)}
          title={`¿Eliminar "${aBorrar?.nombre}"?`}
          description="Sólo se borra si no tiene ninguna reparación registrada. Si tiene, no se borra y te avisa cuántas son — para eso está desactivarlo."
          onConfirm={() => { const p = aBorrar; setABorrar(null); if (p) borrar(p) }}
        />
      </Card>
    </div>
  )
}

/** El cuerpo del modal.
 *
 *  🔴 **Componente de módulo, no una función declarada adentro de
 *  `Proveedores`.** Antes era `formulario(...)`, una función que devolvía JSX y
 *  se llamaba —no se renderizaba— justamente para esquivar el remonte: React
 *  compara los tipos por identidad, y un tipo creado en cada render se desmonta
 *  y se vuelve a montar, así que el input perdía el foco a cada tecla (reporte
 *  del usuario en el catálogo de servicios, 2026-08-14).
 *
 *  Adentro de un diálogo esa vuelta ya no alcanza —el contenido del modal es un
 *  hijo, no se inlinea en el árbol de la pantalla—, así que se sube a nivel de
 *  módulo: definido una sola vez, su identidad no cambia nunca y el foco no se
 *  pierde. Lo cubre `foco-formularios.test.tsx`. */
function FormularioProveedor({ datos, onChange, onSubmit, onCancel, guardando, error }: {
  datos: FormProveedor
  onChange: (d: FormProveedor) => void
  onSubmit: () => void
  onCancel: () => void
  guardando: boolean
  error: string | null
}) {
  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => { e.preventDefault(); onSubmit() }}
    >
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="grid gap-2">
        <Label htmlFor="prov-nombre">Nombre del proveedor</Label>
        <Input
          id="prov-nombre" value={datos.nombre} autoFocus
          placeholder="Compu Service SRL"
          onChange={(e) => onChange({ ...datos, nombre: e.target.value })}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="prov-contacto">Contacto</Label>
        <Input
          id="prov-contacto" value={datos.contacto} placeholder="Juan Pérez"
          onChange={(e) => onChange({ ...datos, contacto: e.target.value })}
        />
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="prov-telefono">Teléfono</Label>
          <Input
            id="prov-telefono" value={datos.telefono}
            onChange={(e) => onChange({ ...datos, telefono: e.target.value })}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="prov-email">Email</Label>
          <Input
            id="prov-email" value={datos.email} type="email"
            onChange={(e) => onChange({ ...datos, email: e.target.value })}
          />
        </div>
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>Cancelar</Button>
        <Button type="submit" disabled={guardando || !datos.nombre.trim()}>Guardar</Button>
      </DialogFooter>
    </form>
  )
}
