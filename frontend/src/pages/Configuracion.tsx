// Datos de la empresa que encabezan los PDF de remitos y presupuestos.
// Sin esto los PDF salen con el encabezado en blanco, porque
// libracore.config_manager devuelve strings vacios cuando no hay
// config.json. Solo admin puede guardar (el backend exige el rol).
import { useEffect, useState } from 'react'
import {
  api, ApiError, type CategoriaIncidencia, type ConfigEmpresa, type Proveedor,
} from '../api'
import { useAuth } from '../context/AuthContext'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Check, CornerDownRight, Pencil, Plus, Trash2, X } from 'lucide-react'

/** Los cuatro campos editables de un proveedor, como strings del formulario
 *  (el backend recibe null donde acá hay cadena vacía). */
type FormProveedor = {
  nombre: string
  contacto: string
  telefono: string
  email: string
}

const VACIO: ConfigEmpresa = {
  empresa_nombre: '',
  empresa_direccion: '',
  empresa_cuit: '',
  empresa_telefono: '',
  empresa_email: '',
  empresa_iibb: '',
  empresa_iva_condition: 'Monotributista',
  empresa_inicio_actividades: '',
}

const CAMPOS: { key: keyof ConfigEmpresa; label: string; placeholder?: string }[] = [
  { key: 'empresa_nombre', label: 'Nombre / razón social', placeholder: 'Compulibra' },
  { key: 'empresa_cuit', label: 'CUIT', placeholder: '20-12345678-9' },
  { key: 'empresa_direccion', label: 'Domicilio', placeholder: 'Suipacha 123' },
  { key: 'empresa_telefono', label: 'Teléfono', placeholder: '3514567890' },
  { key: 'empresa_email', label: 'Email', placeholder: 'info@compulibra.com.ar' },
  { key: 'empresa_iibb', label: 'Ingresos Brutos' },
  { key: 'empresa_iva_condition', label: 'Condición frente al IVA', placeholder: 'Monotributista' },
  { key: 'empresa_inicio_actividades', label: 'Inicio de actividades', placeholder: '2020-01-01' },
]

/** Catálogo de tipos de incidencia: dos niveles, global (no por cliente).
 *  Vive acá y no en una pantalla propia porque es configuración que se toca
 *  una vez cada mucho, igual que los datos de la empresa. */
function CategoriasCard({ esAdmin }: { esAdmin: boolean }) {
  const [categorias, setCategorias] = useState<CategoriaIncidencia[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  // `parent_id` del formulario de alta: null = categoría raíz nueva.
  const [nueva, setNueva] = useState<{ parent_id: number | null; nombre: string } | null>(null)
  const [renombrando, setRenombrando] = useState<{ id: number; nombre: string } | null>(null)
  const [aBorrar, setABorrar] = useState<CategoriaIncidencia | null>(null)

  useEffect(() => {
    recargar()
  }, [])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function recargar() {
    try {
      setCategorias(await api.get<CategoriaIncidencia[]>('/api/categorias'))
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function crear() {
    if (!nueva || !nueva.nombre.trim()) return
    setGuardando(true)
    setError(null)
    try {
      await api.post('/api/categorias', { nombre: nueva.nombre.trim(), parent_id: nueva.parent_id })
      setNueva(null)
      await recargar()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setGuardando(false)
    }
  }

  async function renombrar() {
    if (!renombrando || !renombrando.nombre.trim()) return
    setGuardando(true)
    setError(null)
    try {
      await api.put(`/api/categorias/${renombrando.id}`, { nombre: renombrando.nombre.trim() })
      setRenombrando(null)
      await recargar()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setGuardando(false)
    }
  }

  // Sin `forzar`: si la usan incidencias, el backend devuelve 409 con cuántas
  // son y el borrado no ocurre. Desclasificar tickets a ciegas sería peor que
  // no poder borrar la categoría.
  async function borrar(categoria: CategoriaIncidencia) {
    setError(null)
    try {
      await api.del(`/api/categorias/${categoria.id}`)
      await recargar()
    } catch (err) {
      setError(describeError(err))
    }
  }

  const raices = (categorias ?? []).filter((c) => c.parent_id === null)

  function Fila({ c, esHija }: { c: CategoriaIncidencia; esHija: boolean }) {
    if (renombrando?.id === c.id) {
      return (
        <li className={`flex items-center gap-2 px-3 py-2 ${esHija ? 'pl-9' : ''}`}>
          <Input
            value={renombrando.nombre}
            onChange={(e) => setRenombrando({ id: c.id, nombre: e.target.value })}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); renombrar() }
              if (e.key === 'Escape') setRenombrando(null)
            }}
            aria-label={`Nuevo nombre para ${c.nombre}`}
            autoFocus
            className="h-8 flex-1"
          />
          <Button size="icon" variant="outline" className="size-8" title="Guardar" aria-label="Guardar nombre" disabled={guardando || !renombrando.nombre.trim()} onClick={renombrar}><Check /></Button>
          <Button size="icon" variant="ghost" className="size-8" title="Cancelar" aria-label="Cancelar renombrado" onClick={() => setRenombrando(null)}><X /></Button>
        </li>
      )
    }
    return (
      <li className={`flex items-center gap-2 px-3 py-2 ${esHija ? 'pl-9' : ''}`}>
        {esHija && <CornerDownRight className="size-3.5 shrink-0 text-muted-foreground" />}
        <span className={`flex-1 text-sm ${esHija ? '' : 'font-medium'}`}>{c.nombre}</span>
        {esAdmin && (
          <>
            {!esHija && (
              <Button size="sm" variant="ghost" className="h-8" onClick={() => setNueva({ parent_id: c.id, nombre: '' })}>
                <Plus />Subcategoría
              </Button>
            )}
            <Button size="icon" variant="outline" className="size-8" title="Renombrar" aria-label={`Renombrar ${c.nombre}`} onClick={() => setRenombrando({ id: c.id, nombre: c.nombre })}><Pencil /></Button>
            <Button size="icon" variant="outline" className="size-8 text-destructive hover:text-destructive" title="Eliminar" aria-label={`Eliminar ${c.nombre}`} onClick={() => setABorrar(c)}><Trash2 /></Button>
          </>
        )}
      </li>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Tipos de incidencia</CardTitle>
        <CardDescription>
          Dos niveles: una categoría general y sus subcategorías (Hardware →
          Impresoras). Los tickets se clasifican en la subcategoría, y los
          reportes pueden agrupar por la de arriba. Son las mismas para todos
          los clientes.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {error && <p className="text-sm text-destructive">{error}</p>}

        {esAdmin && (
          nueva !== null ? (
            <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); crear() }}>
              <div className="grid flex-1 gap-1.5">
                <span className="text-xs text-muted-foreground">
                  {nueva.parent_id === null
                    ? 'Categoría nueva'
                    : `Subcategoría de "${categorias?.find((c) => c.id === nueva.parent_id)?.nombre}"`}
                </span>
                <Input
                  value={nueva.nombre}
                  onChange={(e) => setNueva({ ...nueva, nombre: e.target.value })}
                  onKeyDown={(e) => { if (e.key === 'Escape') setNueva(null) }}
                  placeholder={nueva.parent_id === null ? 'Hardware, Software, Red…' : 'Impresoras, Notebooks…'}
                  aria-label="Nombre de la categoría"
                  autoFocus
                />
              </div>
              <Button type="submit" disabled={guardando || !nueva.nombre.trim()}>Agregar</Button>
              <Button type="button" variant="outline" onClick={() => setNueva(null)}>Cancelar</Button>
            </form>
          ) : (
            <div>
              <Button variant="outline" onClick={() => setNueva({ parent_id: null, nombre: '' })}>
                <Plus />Nueva categoría
              </Button>
            </div>
          )
        )}

        {categorias === null ? (
          <p className="py-4 text-center text-sm text-muted-foreground">Cargando…</p>
        ) : raices.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            Todavía no hay categorías. Hasta que las haya, los tickets quedan sin clasificar.
          </p>
        ) : (
          <ul className="divide-y rounded-md border">
            {raices.flatMap((raiz) => [
              <Fila key={raiz.id} c={raiz} esHija={false} />,
              ...categorias
                .filter((c) => c.parent_id === raiz.id)
                .map((hija) => <Fila key={hija.id} c={hija} esHija />),
            ])}
          </ul>
        )}
      </CardContent>

      <ConfirmDialog
        open={aBorrar !== null}
        onOpenChange={(open) => !open && setABorrar(null)}
        title={`¿Eliminar "${aBorrar?.nombre}"?`}
        description="Si alguna incidencia la usa, o si tiene subcategorías, no se borra y te avisa cuántas son."
        onConfirm={() => { const c = aBorrar; setABorrar(null); if (c) borrar(c) }}
      />
    </Card>
  )
}

/** Proveedores de reparación: a quién se le manda un equipo cuando sale a
 *  service. Vive acá y no en una pantalla propia por el mismo motivo que el
 *  catálogo de categorías — es configuración que se toca una vez cada mucho.
 *
 *  Un proveedor **con reparaciones no se borra, se desactiva**: la reparación
 *  histórica lo sigue nombrando, y sin él el registro pierde justamente el dato
 *  que lo hacía útil. Mismo criterio que los clientes. */
function ProveedoresCard({ esAdmin }: { esAdmin: boolean }) {
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
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Proveedores de reparación</CardTitle>
        <CardDescription>
          A quién se le manda un equipo cuando sale a service. Son una tabla y
          no un texto libre para que “Compu Service” y “compuservice” no sean
          dos proveedores distintos — si lo fueran, no se podría saber cuánto
          tarda cada uno en devolver.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {error && <p className="text-sm text-destructive">{error}</p>}

        {esAdmin && nuevo === null && editando === null && (
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
                  <Badge
                    variant={p.activo ? 'default' : 'outline'}
                    className={esAdmin ? 'cursor-pointer' : undefined}
                    onClick={() => esAdmin && toggleActivo(p)}
                  >
                    {p.activo ? 'Activo' : 'Inactivo'}
                  </Badge>
                  {esAdmin && (
                    <>
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
                    </>
                  )}
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
  )
}

export function Configuracion() {
  const { user } = useAuth()
  const esAdmin = user?.role === 'admin'
  const [config, setConfig] = useState<ConfigEmpresa>(VACIO)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [guardado, setGuardado] = useState(false)

  useEffect(() => {
    cargar()
  }, [])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function cargar() {
    setLoading(true)
    setError(null)
    try {
      setConfig(await api.get<ConfigEmpresa>('/api/config-empresa'))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setGuardado(false)
    try {
      setConfig(await api.put<ConfigEmpresa>('/api/config-empresa', config))
      setGuardado(true)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="grid gap-4">
      <h2 className="text-lg font-semibold">Configuración</h2>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Datos de la empresa</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-4 text-sm text-muted-foreground">
            Encabezan los PDF de remitos y presupuestos. Si quedan vacíos, los
            comprobantes salen sin datos del emisor.
          </p>

          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <form className="grid gap-4" onSubmit={guardar}>
              <div className="grid gap-3 sm:grid-cols-2">
                {CAMPOS.map(({ key, label, placeholder }) => (
                  <div key={key} className="grid gap-2">
                    <Label htmlFor={`cfg-${key}`}>{label}</Label>
                    <Input
                      id={`cfg-${key}`}
                      value={config[key]}
                      placeholder={placeholder}
                      disabled={!esAdmin}
                      onChange={(e) => setConfig({ ...config, [key]: e.target.value })}
                    />
                  </div>
                ))}
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}
              {guardado && <p className="text-sm text-muted-foreground">Datos guardados.</p>}

              {esAdmin ? (
                <div>
                  <Button type="submit" disabled={saving}>
                    {saving ? 'Guardando…' : 'Guardar'}
                  </Button>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Solo un administrador puede modificar estos datos.
                </p>
              )}
            </form>
          )}
        </CardContent>
      </Card>

      <CategoriasCard esAdmin={esAdmin} />

      <ProveedoresCard esAdmin={esAdmin} />
    </div>
  )
}
