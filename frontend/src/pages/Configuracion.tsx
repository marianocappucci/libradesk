// Configuración, en pestañas (pedido 36, 2026-08-04): datos de la empresa,
// catálogo de servicios, tipos de incidencia, facturación y datos / backup.
// Antes eran tarjetas apiladas en una sola pantalla larga.
//
// **Proveedores ya no vive acá** (2026-08-13): es una pantalla propia bajo
// Compras, en `pages/Proveedores.tsx`. Estando en las dos partes a la vez,
// entrar por Compras → Proveedores aterrizaba en esta pantalla, con este título
// y este conmutador, y no se distinguía de Configuración general.
//
// Los datos de la empresa encabezan los PDF de remitos y presupuestos: sin esto
// salen con el encabezado en blanco, porque libracore.config_manager devuelve
// strings vacios cuando no hay config.json. Solo admin puede guardar (el
// backend exige el rol).
//
// 🔴 **`esAdmin` aplica SÓLO a los datos de la empresa.** Los catálogos no
// están detrás de admin, y eso es deliberado (2026-08-04, reporte del usuario:
// "en configuración no se pueden agregar ni editar ni eliminar proveedores y
// tipos de incidencia").
//
// El motivo es el mismo que en depósitos: `app/main.py` monta
// `categorias.router` con `staff_or_admin`, así que cualquier staff **ya
// podía** crear, editar y borrar por la API. Esconderle los botones no
// restringía nada — sólo hacía que la pestaña se viera rota para quien no
// fuera admin. Los datos de empresa sí son distintos: el
// `GET` de `/api/config/empresa` es staff, pero el `PUT` va en un router
// aparte con `require_admin` de verdad, y ahí el gate se queda.
//
// Si se decide que estos catálogos sean admin-only, el lugar es el backend, no
// esta pantalla.
import { useEffect, useRef, useState } from 'react'
import {
  api, ApiError, type BackupGuardado, type CategoriaIncidencia, type ConfigEmpresa,
  type Servicio,
} from '../api'
import { useAuth } from '../context/AuthContext'
import { Conmutador } from '@/components/conmutador'
import { PESTANIAS_CONFIG } from './configuracion-piezas'
import { FacturacionConfigCard } from './configuracion-facturacion'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/confirm-dialog'
import {
  Check, CornerDownRight, Download, FilePlus, Pencil, PlusCircle, Trash2, Upload, X,
} from '@/components/iconos-accion'
import { Settings } from 'lucide-react'
import { TituloPantalla } from '@/components/titulo-pantalla'

/** Los campos editables de un servicio, como strings del formulario. */
type FormServicio = {
  nombre: string
  descripcion: string
  precio: string
  /** La alícuota como fracción, en string (`'0.21'`). El `<select>` trabaja
   *  con strings; guardarla así evita comparar floats para marcar la opción
   *  elegida. */
  iva_rate: string
  activo: boolean
  /** Si éste es el servicio con el que se cotiza la hora de trabajo al
   *  generarle el remito a un reclamo. Uno solo puede estarlo. */
  es_valor_hora: boolean
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
function CategoriasCard() {
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

  // Función que devuelve JSX, **no** un componente — mismo motivo que
  // `formulario` en `ServiciosCard`: declarada acá adentro, cada render creaba
  // un tipo nuevo y React remontaba la fila entera, así que el campo de
  // renombrar perdía el foco después de cada tecla.
  function fila(c: CategoriaIncidencia, esHija: boolean) {
    if (renombrando?.id === c.id) {
      return (
        // La `key` va acá adentro y ya no en el sitio de llamada: el elemento la
        // lleva consigo, y así entrar y salir del modo renombrar reconcilia la
        // MISMA fila en vez de reemplazarla.
        <li key={c.id} className={`flex items-center gap-2 px-3 py-2 ${esHija ? 'pl-9' : ''}`}>
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
      <li key={c.id} className={`flex items-center gap-2 px-3 py-2 ${esHija ? 'pl-9' : ''}`}>
        {esHija && <CornerDownRight className="size-3.5 shrink-0 text-muted-foreground" />}
        <span className={`flex-1 text-sm ${esHija ? '' : 'font-medium'}`}>{c.nombre}</span>
        {!esHija && (
          <Button size="sm" variant="ghost" className="h-8" onClick={() => setNueva({ parent_id: c.id, nombre: '' })}>
            <PlusCircle />Subcategoría
          </Button>
        )}
        <Button size="icon" variant="outline" className="size-8" title="Renombrar" aria-label={`Renombrar ${c.nombre}`} onClick={() => setRenombrando({ id: c.id, nombre: c.nombre })}><Pencil /></Button>
        <Button size="icon" variant="outline" className="size-8 text-destructive hover:text-destructive" title="Eliminar" aria-label={`Eliminar ${c.nombre}`} onClick={() => setABorrar(c)}><Trash2 /></Button>
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

        {nueva !== null ? (
          <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); crear() }}>
            <div className="grid flex-1 gap-2">
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
              <FilePlus />Nueva categoría
            </Button>
          </div>
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
              fila(raiz, false),
              ...categorias
                .filter((c) => c.parent_id === raiz.id)
                .map((hija) => fila(hija, true)),
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
      setConfig(await api.get<ConfigEmpresa>('/api/config/empresa'))
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
      setConfig(await api.put<ConfigEmpresa>('/api/config/empresa', config))
      setGuardado(true)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Pantalla actual="empresa">
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

      <LogoCard esAdmin={esAdmin} />
    </Pantalla>
  )
}

/** El logo que encabeza los PDF.
 *
 *  El generador de LibraCore ya lo buscaba en `LOGO_DIR`; lo que no existía
 *  era el modo de ponerlo ahí sin entrar al volumen del contenedor.
 */
function LogoCard({ esAdmin }: { esAdmin: boolean }) {
  // `version` fuerza a recargar la imagen después de subir o borrar: el
  // navegador cachea `/api/config/empresa/logo` y sin esto se sigue viendo el
  // logo anterior aunque el nuevo ya esté en el servidor.
  const [version, setVersion] = useState(0)
  const [hayLogo, setHayLogo] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [subiendo, setSubiendo] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let vivo = true
    fetch('/api/config/empresa/logo', { credentials: 'include' })
      .then((r) => { if (vivo) setHayLogo(r.ok) })
      .catch(() => { if (vivo) setHayLogo(false) })
    return () => { vivo = false }
  }, [version])

  async function subir(archivo: File) {
    setSubiendo(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('logo', archivo)
      await api.postForm('/api/config/empresa/logo', form)
      setVersion((v) => v + 1)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'No se pudo subir el logo.')
    } finally {
      setSubiendo(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  async function borrar() {
    setError(null)
    try {
      await api.del('/api/config/empresa/logo')
      setVersion((v) => v + 1)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'No se pudo borrar el logo.')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Logo</CardTitle>
        <CardDescription>
          Sale en el encabezado de remitos, presupuestos e informes. PNG o JPG.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {hayLogo === null ? (
          <p className="text-sm text-muted-foreground">Cargando…</p>
        ) : hayLogo ? (
          <img
            src={`/api/config/empresa/logo?v=${version}`}
            alt="Logo de la empresa"
            className="max-h-24 w-auto rounded border bg-white object-contain p-2"
          />
        ) : (
          <p className="text-sm text-muted-foreground">
            Todavía no hay logo cargado; los comprobantes salen sin él.
          </p>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        {esAdmin ? (
          <div className="flex flex-wrap gap-2">
            <input
              ref={inputRef}
              type="file"
              accept="image/png,image/jpeg"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) subir(f) }}
            />
            <Button
              type="button"
              variant="outline"
              disabled={subiendo}
              onClick={() => inputRef.current?.click()}
            >
              <Upload className="mr-2 h-4 w-4" />
              {subiendo ? 'Subiendo…' : hayLogo ? 'Reemplazar' : 'Subir logo'}
            </Button>
            {hayLogo && (
              <Button type="button" variant="outline" onClick={borrar}>
                <Trash2 className="mr-2 h-4 w-4" />
                Quitar
              </Button>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Solo un administrador puede cambiar el logo.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

/** El marco que comparten las tres pestañas: título y conmutador.
 *
 *  Está acá y no repetido en cada una porque el conmutador tiene que verse
 *  idéntico en las tres — si una lo dibujara distinto, cambiar de pestaña se
 *  sentiría como cambiar de pantalla.
 */
function Pantalla({ actual, children }: { actual: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-4">
      <TituloPantalla icono={Settings}>
          Configuración
        </TituloPantalla>
      <Conmutador pestanias={PESTANIAS_CONFIG} actual={actual} />
      {children}
      <CreditosIconos />
    </div>
  )
}

/** Atribución del set de iconos.
 *
 *  La licencia ISC pide que se conserve el aviso de copyright en las
 *  distribuciones, y un producto que se sirve compilado es una distribución. No
 *  es un cartel de agradecimiento: es la condición bajo la que se puede usar.
 *
 *  Va al pie de Configuración —una vez, en el shell y no en cada pestaña—
 *  porque es donde alguien busca "de qué está hecho esto" y no estorba a quien
 *  vino a cambiar un ajuste.
 *
 *  **Nombraba también a Fluent UI System Icons hasta el 2026-08-14**, cuando los
 *  96 iconos volvieron a lucide y los dos sets de Fluent salieron del producto.
 *  Una atribución que sobrevive al set que atribuye no es inofensiva: le dice al
 *  lector que el producto lleva un código que ya no lleva.
 *
 *  Ojo si se agrega un set nuevo: hubo un momento en que los candidatos eran
 *  Streamline Plump (CC BY 4.0), que **exige** atribución visible, e Icons8
 *  Plumpy, cuyo tier gratuito exige un enlace. Si alguna vez entra uno de ésos,
 *  esta tarjeta deja de ser buena práctica y pasa a ser un requisito legal — y
 *  el enlace tiene que ser un enlace de verdad, no texto.
 */
function CreditosIconos() {
  return (
    <p className="text-xs text-muted-foreground">
      Iconos:{' '}
      <a
        className="underline underline-offset-2"
        href="https://lucide.dev"
        target="_blank"
        rel="noreferrer noopener"
      >
        Lucide
      </a>{' '}
      (ISC).
    </p>
  )
}

/** Pestaña de tipos de incidencia. */
export function ConfiguracionCategorias() {
  return (
    <Pantalla actual="categorias">
      <CategoriasCard />
    </Pantalla>
  )
}

/** Pestaña del destino de la facturación: Contalibra, SOS Contador o los dos. */
export function ConfiguracionFacturacion() {
  return (
    <Pantalla actual="facturacion">
      <FacturacionConfigCard />
    </Pantalla>
  )
}

/** Pestaña del catálogo de servicios. */
export function ConfiguracionServicios() {
  return (
    <Pantalla actual="servicios">
      <ServiciosCard />
    </Pantalla>
  )
}

/** El catálogo de servicios que se reusan al armar remitos y presupuestos.
 *
 *  🔴 **No reemplaza al campo libre.** Un ítem de comprobante sigue siendo
 *  texto libre; este catálogo sólo lo sugiere mientras se escribe. Cargar algo
 *  acá no obliga a nadie a usarlo, y no cargarlo deja el sistema como estaba.
 */
function ServiciosCard() {
  const { user } = useAuth()
  const esAdmin = user?.role === 'admin'
  const [servicios, setServicios] = useState<Servicio[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [nuevo, setNuevo] = useState<FormServicio | null>(null)
  const [editando, setEditando] = useState<(FormServicio & { id: number }) | null>(null)
  const [aBorrar, setABorrar] = useState<Servicio | null>(null)
  // Las alícuotas válidas salen del backend, que es donde está la lista
  // cerrada. Si se hardcodearan acá, agregar una allá dejaría el catálogo
  // aceptando por API algo que esta pantalla no deja elegir.
  const [alicuotas, setAlicuotas] = useState<number[]>([0, 0.105, 0.21, 0.27])

  useEffect(() => { recargar() }, [])

  useEffect(() => {
    let vigente = true
    api.get<number[]>('/api/servicios/alicuotas')
      .then((res) => { if (vigente && res.length) setAlicuotas(res) })
      .catch(() => { /* se quedan las conocidas: sin select no se puede cargar nada */ })
    return () => { vigente = false }
  }, [])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function recargar() {
    try {
      // Con inactivos: la pantalla de administración los muestra para poder
      // reactivarlos. El buscador del comprobante sólo ofrece los activos.
      setServicios(await api.get<Servicio[]>('/api/servicios?incluir_inactivos=true'))
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
        descripcion: datos.descripcion.trim(),
        precio: Number(datos.precio) || 0,
        iva_rate: Number(datos.iva_rate),
        activo: datos.activo,
        es_valor_hora: datos.es_valor_hora,
      }
      if (editando) await api.put(`/api/servicios/${editando.id}`, payload)
      else await api.post('/api/servicios', payload)
      setNuevo(null)
      setEditando(null)
      await recargar()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setGuardando(false)
    }
  }

  async function borrar(servicio: Servicio) {
    setError(null)
    try {
      await api.del(`/api/servicios/${servicio.id}`)
      await recargar()
    } catch (err) {
      setError(describeError(err))
    }
  }

  // 🔴 **Es una función que devuelve JSX, no un componente**, y se la llama
  // `formulario(...)` en vez de renderizarla como `<Formulario />`.
  //
  // Declarada adentro de `ServiciosCard`, cada render creaba una función nueva.
  // React compara los tipos por identidad, así que un tipo nuevo no se
  // actualiza: se **desmonta y se vuelve a montar**. El `<input>` pasaba a ser
  // otro nodo del DOM, el que tenía el foco quedaba desprendido, y sólo entraba
  // una letra por click. Reportado por el usuario cargando el valor hora
  // (2026-08-14): *"tenía que escribir una, volver a hacer foco con el mouse,
  // escribir otra letra"*.
  //
  // Llamándola, sus elementos se inlinean en el árbol de esta pantalla y no hay
  // componente intermedio que remontar. Se elige esto y no subirla al módulo
  // porque conserva el closure —`alicuotas`, `guardando`, `guardar`— sin
  // enhebrar cinco props que sólo existirían para eso.
  function formulario(
    datos: FormServicio,
    onCambiar: (d: FormServicio) => void,
  ) {
    return (
      <div className="grid gap-3 rounded border p-3 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="srv-nombre">Nombre</Label>
          <Input
            id="srv-nombre" value={datos.nombre} placeholder="Mantenimiento preventivo"
            onChange={(e) => onCambiar({ ...datos, nombre: e.target.value })}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="srv-precio">Precio</Label>
          <Input
            id="srv-precio" type="number" min="0" step="0.01" value={datos.precio}
            onChange={(e) => onCambiar({ ...datos, precio: e.target.value })}
          />
        </div>
        <div className="grid gap-2">
          {/* La alícuota es del servicio, no del cliente: en Argentina el
              21 / 10,5 / 27 / exento sale de QUÉ se vende. De la condición del
              cliente depende otra cosa — si el comprobante la discrimina. */}
          <Label htmlFor="srv-iva">IVA</Label>
          <select
            id="srv-iva"
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
            value={datos.iva_rate}
            onChange={(e) => onCambiar({ ...datos, iva_rate: e.target.value })}
          >
            {alicuotas.map((r) => (
              <option key={r} value={String(r)}>
                {(r * 100).toLocaleString('es-AR', { maximumFractionDigits: 1 })} %
              </option>
            ))}
          </select>
        </div>
        <div className="grid gap-2 sm:col-span-2">
          <Label htmlFor="srv-desc">Descripción para el comprobante</Label>
          <Input
            id="srv-desc" value={datos.descripcion}
            placeholder="Si queda vacía se usa el nombre"
            onChange={(e) => onCambiar({ ...datos, descripcion: e.target.value })}
          />
        </div>
        {/* El valor hora vive acá y no en una pantalla propia: es un precio
            más del catálogo, con su alícuota, y así se edita donde se editan
            todos los otros precios. */}
        <label className="flex items-start gap-2 text-sm sm:col-span-2">
          <input
            type="checkbox" className="mt-0.5"
            checked={datos.es_valor_hora}
            onChange={(e) => onCambiar({ ...datos, es_valor_hora: e.target.checked })}
          />
          <span>
            Es el <strong>valor hora</strong> del servicio técnico
            <span className="block text-xs text-muted-foreground">
              Con esto se cotiza el trabajo de cada reclamo al generarle el
              remito. Uno solo: marcarlo acá desmarca al que lo esté.
            </span>
          </span>
        </label>
        {/* Mismo pie que el resto: Cancelar primero, a la derecha. */}
        <div className="flex flex-wrap justify-end gap-2 sm:col-span-2">
          <Button
            type="button" variant="outline"
            onClick={() => { setNuevo(null); setEditando(null); setError(null) }}
          >
            Cancelar
          </Button>
          <Button type="button" disabled={guardando} onClick={guardar}>
            {guardando ? 'Guardando…' : 'Guardar'}
          </Button>
        </div>
      </div>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Servicios</CardTitle>
        <CardDescription>
          Los que se ofrecen habitualmente, con su precio. Al armar un remito o
          un presupuesto aparecen como sugerencia mientras se escribe la
          descripción — <strong>el campo sigue siendo libre</strong>: se puede
          elegir uno o escribir cualquier otra cosa.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {error && <p className="text-sm text-destructive">{error}</p>}

        {esAdmin && !nuevo && !editando && (
          <div>
            <Button
              type="button" size="sm"
              onClick={() => setNuevo({
                nombre: '', descripcion: '', precio: '0', iva_rate: '0.21',
                activo: true, es_valor_hora: false,
              })}
            >
              <PlusCircle className="mr-2 h-4 w-4" />
              Agregar servicio
            </Button>
          </div>
        )}
        {nuevo && formulario(nuevo, setNuevo)}
        {editando && formulario(
          editando,
          (d) => setEditando({ ...d, id: editando.id }),
        )}

        {servicios === null ? (
          <p className="text-sm text-muted-foreground">Cargando…</p>
        ) : servicios.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Todavía no hay servicios cargados. Sin ellos los comprobantes se
            arman igual, escribiendo cada ítem a mano.
          </p>
        ) : (
          <ul className="grid gap-1">
            {servicios.map((s) => (
              <li
                key={s.id}
                className="flex flex-wrap items-center gap-2 rounded border px-3 py-2 text-sm"
              >
                <span className={s.activo ? '' : 'text-muted-foreground line-through'}>
                  {s.nombre}
                </span>
                {!s.activo && <BadgeEstado tono="neutro">Inactivo</BadgeEstado>}
                {/* Sin esto no hay forma de saber, mirando la lista, con qué
                    precio se están cotizando los reclamos. */}
                {s.es_valor_hora && <Badge>Valor hora</Badge>}
                {s.descripcion && (
                  <span className="truncate text-xs text-muted-foreground">{s.descripcion}</span>
                )}
                <span className="ml-auto tabular-nums">
                  {s.precio.toLocaleString('es-AR', { style: 'currency', currency: 'ARS' })}
                </span>
                <Badge variant="secondary" className="tabular-nums">
                  {s.iva_rate === 0
                    ? 'Exento'
                    : `IVA ${(s.iva_rate * 100).toLocaleString('es-AR', { maximumFractionDigits: 1 })}%`}
                </Badge>
                {esAdmin && (
                  <>
                    <Button
                      type="button" size="icon" variant="outline" title="Editar"
                      aria-label={`Editar ${s.nombre}`}
                      onClick={() => setEditando({
                        id: s.id, nombre: s.nombre, descripcion: s.descripcion,
                        precio: String(s.precio), iva_rate: String(s.iva_rate),
                        activo: s.activo, es_valor_hora: s.es_valor_hora,
                      })}
                    >
                      <Pencil />
                    </Button>
                    <Button
                      type="button" size="icon" variant="outline"
                      className="text-destructive hover:text-destructive"
                      title="Eliminar" aria-label={`Eliminar ${s.nombre}`}
                      onClick={() => setABorrar(s)}
                    >
                      <Trash2 />
                    </Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}

        {!esAdmin && (
          <p className="text-sm text-muted-foreground">
            Solo un administrador puede modificar el catálogo.
          </p>
        )}
      </CardContent>

      <ConfirmDialog
        open={aBorrar !== null}
        onOpenChange={(abierto) => { if (!abierto) setABorrar(null) }}
        title={`¿Eliminar «${aBorrar?.nombre ?? ''}»?`}
        description={
          'Los remitos y presupuestos que ya lo usaron no cambian: guardaron su ' +
          'propia descripción y su propio precio. Si sólo querés dejar de ' +
          'ofrecerlo, editalo y desactivalo en vez de borrarlo.'
        }
        onConfirm={() => { const s = aBorrar; setABorrar(null); if (s) borrar(s) }}
      />
    </Card>
  )
}


/** Estado de la copia del backup en la nube del cliente (add-on).
 *
 * `contratado: false` es "no tenés el add-on", **no** una falla: la pantalla no
 * tiene que mostrar una alarma a quien no lo contrató. `al_dia: false` con
 * `contratado: true` sí lo es — el backend distingue en `motivo` si la última
 * subida falló o si anduvo pero es de hace días. */
export type ResguardoExterno = {
  contratado: boolean
  al_dia: boolean | null
  motivo: string | null
  detalle: {
    cuando: string | null
    archivo: string | null
    destino: string | null
    bytes: number | null
    en_destino: number | null
    error: string | null
  } | null
}

/** La tarjeta del resguardo externo, con sus tres estados.
 *
 *  Tres y no dos: con "anda / no anda" le mostraría una alarma a quien no
 *  contrató el add-on —que es ruido— y no le mostraría nada a quien lo contrató
 *  y hace días que no sube, que es el caso silencioso que esto vino a cerrar.
 *
 *  Si el endpoint no existe (LibraCore anterior a v1.32.0) no aparece. */
function ResguardoExternoCard() {
  const [estado, setEstado] = useState<ResguardoExterno | null>(null)

  useEffect(() => {
    api.get<ResguardoExterno>('/api/config/resguardo-externo')
      .then(setEstado)
      .catch(() => setEstado(null))
  }, [])

  if (!estado) return null

  if (!estado.contratado) {
    return (
      <Card className="border-dashed">
        <CardHeader>
          <CardTitle className="text-base text-muted-foreground">Copia externa</CardTitle>
          <CardDescription>
            Tus copias viven en este servidor. Con el resguardo externo se guardan
            todas las noches en tu propia cuenta de Google Drive o Dropbox, así
            siguen estando aunque el servidor no esté. Consultanos para activarlo.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <Card className={estado.al_dia ? 'border-emerald-500/40' : 'border-amber-500/60'}>
      <CardHeader>
        <CardTitle className={`text-base ${estado.al_dia ? '' : 'text-amber-600 dark:text-amber-400'}`}>
          Copia externa {estado.al_dia ? 'al día' : 'con problemas'}
        </CardTitle>
        <CardDescription>
          {estado.al_dia
            ? <>También se guarda fuera de este servidor, en <span className="font-mono">{estado.detalle?.destino}</span>.</>
            : estado.motivo}
        </CardDescription>
      </CardHeader>
      {estado.al_dia && estado.detalle && (
        <CardContent>
          <p className="text-xs text-muted-foreground">
            Última copia: {estado.detalle.cuando}
            {estado.detalle.en_destino != null && <> · {estado.detalle.en_destino} guardadas afuera</>}
          </p>
        </CardContent>
      )}
    </Card>
  )
}

/** Pestaña de Datos / Backup. */
export function ConfiguracionDatos() {
  return (
    <Pantalla actual="datos">
      <DatosCard />
    </Pantalla>
  )
}

/** Bajar una copia de los datos, y volver a una anterior.
 *
 *  El archivo es un **ZIP con la base y los archivos de la instancia**, no un
 *  `.db` suelto — el formato es el mismo en los seis productos de la familia,
 *  donde varios tienen dos bases y archivos subidos.
 */
function DatosCard() {
  const { user } = useAuth()
  const esAdmin = user?.role === 'admin'
  const [backups, setBackups] = useState<BackupGuardado[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const [aRestaurar, setARestaurar] = useState<File | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { recargar() }, [])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function recargar() {
    setError(null)
    try {
      setBackups(await api.get<BackupGuardado[]>('/api/config/backups'))
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function crear() {
    setOcupado(true)
    setError(null)
    setAviso(null)
    try {
      await api.post('/api/config/backups')
      setAviso('Copia guardada en el servidor.')
      await recargar()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setOcupado(false)
    }
  }

  async function restaurar(archivo: File) {
    setOcupado(true)
    setError(null)
    setAviso(null)
    try {
      const form = new FormData()
      form.append('backup_file', archivo)
      const r = await api.postForm<{ backup_previo: string }>('/api/config/restore', form)
      setAviso(
        `Datos restaurados. El estado anterior quedó guardado como ${r.backup_previo}.`,
      )
      await recargar()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setOcupado(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  if (!esAdmin) {
    return (
      <Card>
      {/* Arriba de todo: si la copia externa falla, es lo primero
          que el cliente tiene que ver. */}
      <ResguardoExternoCard />
        <CardHeader><CardTitle className="text-base">Datos / Backup</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Solo un administrador puede descargar o restaurar los datos.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Copia de tus datos</CardTitle>
          <CardDescription>
            Un archivo ZIP con la base de datos y los archivos del sistema.
            Guardalo fuera del servidor.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {/* Link directo y no `fetch`: el navegador maneja la descarga con la
              misma cookie, sin pasar el ZIP entero por memoria del JS. */}
          <Button asChild>
            <a href="/api/config/backup-ahora">
              <Download className="mr-2 h-4 w-4" />
              Descargar copia
            </a>
          </Button>
          <Button type="button" variant="outline" disabled={ocupado} onClick={crear}>
            {ocupado ? 'Trabajando…' : 'Guardar copia en el servidor'}
          </Button>
        </CardContent>
      </Card>

      {(error || aviso) && (
        <p className={error ? 'text-sm text-destructive' : 'text-sm text-muted-foreground'}>
          {error ?? aviso}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Copias guardadas en el servidor</CardTitle>
          <CardDescription>
            Se conservan las 10 más recientes. Las de <code>antes_restore</code> las
            hace el sistema solo, justo antes de restaurar.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {backups === null ? (
            <p className="text-sm text-muted-foreground">Cargando…</p>
          ) : backups.length === 0 ? (
            <p className="text-sm text-muted-foreground">Todavía no hay ninguna.</p>
          ) : (
            <ul className="grid gap-2">
              {backups.map((b) => (
                <li key={b.filename} className="flex flex-wrap items-center gap-2 text-sm">
                  <Badge variant="outline">{b.mtime}</Badge>
                  <span className="text-muted-foreground">{b.size_mb} MB</span>
                  <a className="underline" href={`/api/config/backups/${b.filename}`}>
                    {b.filename}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Restaurar</CardTitle>
          <CardDescription>
            Reemplaza <strong>todos</strong> los datos actuales por los del archivo.
            Antes de hacerlo, el sistema guarda solo una copia del estado actual.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <input
            ref={inputRef}
            type="file"
            accept=".zip,application/zip"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) setARestaurar(f) }}
          />
          <Button
            type="button"
            variant="outline"
            disabled={ocupado}
            onClick={() => inputRef.current?.click()}
          >
            <Upload className="mr-2 h-4 w-4" />
            Elegir archivo y restaurar
          </Button>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={aRestaurar !== null}
        onOpenChange={(abierto) => { if (!abierto) setARestaurar(null) }}
        title="¿Restaurar los datos?"
        description={
          `Se van a reemplazar todos los datos actuales por los de ${aRestaurar?.name ?? ''}. ` +
          'El estado de ahora queda guardado como copia por si hace falta volver.'
        }
        confirmLabel="Restaurar"
        onConfirm={() => { const f = aRestaurar; setARestaurar(null); if (f) restaurar(f) }}
      />
    </div>
  )
}
