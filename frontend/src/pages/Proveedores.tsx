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
import { useEffect, useState } from 'react'
import { api, ApiError, type Proveedor } from '../api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ConfirmDialog } from '@/components/confirm-dialog'
import Pencil from '~icons/fluent-color/edit-16'
import Plus from '~icons/fluent-color/add-circle-16'
import { Trash2 } from 'lucide-react'

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

  function Formulario({ datos, onChange, onCancel, titulo }: {
    datos: FormProveedor
    onChange: (d: FormProveedor) => void
    onCancel: () => void
    titulo: string
  }) {
    return (
      <form
        className="grid gap-2 rounded-md border p-3"
        onSubmit={(e) => { e.preventDefault(); guardar() }}
      >
        <span className="text-xs text-muted-foreground">{titulo}</span>
        <div className="grid gap-2 sm:grid-cols-2">
          <Input
            value={datos.nombre} autoFocus
            placeholder="Compu Service SRL"
            aria-label="Nombre del proveedor"
            onChange={(e) => onChange({ ...datos, nombre: e.target.value })}
            onKeyDown={(e) => { if (e.key === 'Escape') onCancel() }}
          />
          <Input
            value={datos.contacto} placeholder="Contacto (Juan Pérez)"
            aria-label="Contacto"
            onChange={(e) => onChange({ ...datos, contacto: e.target.value })}
          />
          <Input
            value={datos.telefono} placeholder="Teléfono"
            aria-label="Teléfono"
            onChange={(e) => onChange({ ...datos, telefono: e.target.value })}
          />
          <Input
            value={datos.email} placeholder="Email" type="email"
            aria-label="Email"
            onChange={(e) => onChange({ ...datos, email: e.target.value })}
          />
        </div>
        <div className="flex gap-2">
          <Button type="submit" disabled={guardando || !datos.nombre.trim()}>Guardar</Button>
          <Button type="button" variant="outline" onClick={onCancel}>Cancelar</Button>
        </div>
      </form>
    )
  }

  return (
    <div className="grid gap-4">
      <h2 className="text-lg font-semibold">Proveedores</h2>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Proveedores</CardTitle>
          <CardDescription>
            A quién se le compra, y a quién se le manda un equipo cuando sale a
            service. Son una tabla y no un texto libre para que “Compu Service”
            y “compuservice” no sean dos proveedores distintos — si lo fueran,
            no se podría saber cuánto tarda cada uno en devolver.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {error && <p className="text-sm text-destructive">{error}</p>}

          {nuevo === null && editando === null && (
            <div>
              <Button
                variant="outline"
                onClick={() => setNuevo({ nombre: '', contacto: '', telefono: '', email: '' })}
              >
                <Plus />Nuevo proveedor
              </Button>
            </div>
          )}

          {nuevo !== null && (
            <Formulario
              datos={nuevo} onChange={setNuevo} onCancel={() => setNuevo(null)}
              titulo="Proveedor nuevo"
            />
          )}

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
                editando?.id === p.id ? (
                  <li key={p.id} className="p-2">
                    <Formulario
                      datos={editando}
                      onChange={(d) => setEditando({ ...d, id: p.id })}
                      onCancel={() => setEditando(null)}
                      titulo={`Editando ${p.nombre}`}
                    />
                  </li>
                ) : (
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
                    <Badge
                      asChild
                      variant={p.activo ? 'default' : 'outline'}
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
                    </Badge>
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
                )
              ))}
            </ul>
          )}
        </CardContent>

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
