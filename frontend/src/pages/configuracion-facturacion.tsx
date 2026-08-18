/** A dónde manda lo facturable esta instancia.
 *
 *  Se pueden habilitar **Contalibra, SOS Contador o los dos**. Con los dos
 *  habilitados, el destino se elige al enviar en la pantalla de Facturación:
 *  un comprobante va a uno solo, decidido el 2026-08-12.
 *
 *  🔴 **Las credenciales entran pero no salen.** El backend nunca devuelve el
 *  valor de un secreto, sólo un booleano de "cargada". Por eso el campo de
 *  contraseña arranca **vacío** aunque haya una guardada: no es un bug, es que
 *  la pantalla no la recibió nunca. Dejarlo vacío al guardar significa "no la
 *  toqué", y para sacarla está el botón de borrar.
 *
 *  Los secretos se guardan cifrados con una clave derivada de `SECRET_KEY`,
 *  que vive en el entorno y no viaja en el respaldo — ver
 *  `app/services/facturacion_config.py`.
 */
import { useEffect, useState } from 'react'
import { Check, Search, Send } from 'lucide-react'
import { api, ApiError } from '../api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { AlertTriangle, KeyRound, Trash2 } from '@/components/iconos-accion'

/** Una CUIT como la devuelve `POST /api/facturacion/config/sos/cuits`. */
export type CuitDeSos = {
  idcuit: string
  cuit: string
  razonsocial: string
  habilitado: boolean
}

export type DestinoConfig = {
  destino: string
  habilitado: boolean
  configurado: boolean
  desde_entorno: boolean
  secretos_ilegibles: boolean
  [campo: string]: string | boolean
}

const NOMBRES: Record<string, string> = {
  contalibra: 'Contalibra',
  sos: 'SOS Contador',
}

/** Qué se edita de cada destino. El campo secreto va aparte porque se comporta
 *  distinto: se escribe, no se lee, y tiene su propio botón de borrar. */
const CAMPOS: Record<string, { campo: string; label: string; ayuda?: string; ancho?: string }[]> = {
  contalibra: [
    { campo: 'url', label: 'URL de la instancia', ayuda: 'https://cliente.contalibra.com.ar' },
    { campo: 'instancia', label: 'Slug de esta instancia', ayuda: 'Cómo la identifica el otro lado' },
  ],
  sos: [
    { campo: 'usuario', label: 'Usuario de la API', ayuda: 'Que sea uno dedicado: un usuario del estudio alcanza todas las CUITs de su cartera' },
    { campo: 'idcuit', label: 'ID de CUIT', ayuda: 'El id de SOS, no el número de CUIT', ancho: 'w-40' },
    { campo: 'puntoventa', label: 'Punto de venta', ayuda: 'Tiene que ser exclusivo de LibraDesk: la numeración la lleva este lado', ancho: 'w-28' },
    { campo: 'letra', label: 'Letra', ayuda: 'Según la condición del emisor ante ARCA', ancho: 'w-24' },
    { campo: 'idtipo_operacion', label: 'Tipo de operación', ayuda: 'Vacío = 2. Los tipos 1, 3 y 5 fallan', ancho: 'w-28' },
    { campo: 'idproducto', label: 'Producto genérico (opcional)', ayuda: 'Si se completa, todos los ítems van contra ese producto en vez de crear uno por descripción', ancho: 'w-40' },
  ],
}

const SECRETO: Record<string, { campo: string; label: string }> = {
  contalibra: { campo: 'token', label: 'Token de servicio' },
  sos: { campo: 'password', label: 'Contraseña' },
}

function DestinoCard({ inicial, onGuardado }: {
  inicial: DestinoConfig
  onGuardado: (d: DestinoConfig) => void
}) {
  const destino = inicial.destino
  const [datos, setDatos] = useState<DestinoConfig>(inicial)
  const [secreto, setSecreto] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [guardado, setGuardado] = useState(false)
  // El listado de CUITs que trae el botón. `null` = todavía no se buscó, que
  // no es lo mismo que "se buscó y no hay ninguna".
  const [cuits, setCuits] = useState<CuitDeSos[] | null>(null)
  const [buscandoCuits, setBuscandoCuits] = useState(false)
  const [errorCuits, setErrorCuits] = useState<string | null>(null)

  useEffect(() => { setDatos(inicial) }, [inicial])

  const campoSecreto = SECRETO[destino]
  const secretoCargado = Boolean(datos[`${campoSecreto.campo}_cargado`])

  function set(campo: string, valor: string) {
    setDatos((prev) => ({ ...prev, [campo]: valor }))
    setGuardado(false)
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const valores: Record<string, string> = {}
      for (const { campo } of CAMPOS[destino]) valores[campo] = String(datos[campo] ?? '')
      // El secreto sólo viaja si el usuario escribió algo. Vacío significa "no
      // lo toqué" — mandarlo igual borraría una credencial que sigue estando.
      if (secreto.trim()) valores[campoSecreto.campo] = secreto.trim()

      const r = await api.put<DestinoConfig>(`/api/facturacion/config/${destino}`, {
        habilitado: datos.habilitado, valores,
      })
      setDatos(r)
      setSecreto('')
      setGuardado(true)
      onGuardado(r)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    } finally {
      setSaving(false)
    }
  }

  /** Trae las CUITs que ve el usuario de SOS y completa el id.
   *
   *  El `idcuit` no aparece en ninguna pantalla de SOS: es un id interno que
   *  sólo devuelve la API. Sin esto hay que ir a buscarlo con un script, que es
   *  como se consiguió el de Lagrace.
   *
   *  Manda lo que está **tipeado** en la pantalla, no lo guardado: el momento
   *  natural para apretar el botón es mientras se cargan usuario y contraseña,
   *  antes del primer Guardar — que además no se puede completar sin el id. Si
   *  el campo de contraseña está vacío significa "la guardada sirve", y el
   *  backend usa esa.
   */
  async function buscarCuits() {
    setBuscandoCuits(true)
    setErrorCuits(null)
    try {
      const r = await api.post<{ cuits: CuitDeSos[] }>(
        '/api/facturacion/config/sos/cuits',
        { usuario: String(datos.usuario ?? ''), password: secreto },
      )
      setCuits(r.cuits)
      // Con una sola no se hace elegir: se completa y se muestra cuál quedó.
      // Con varias hay que decidir, y decidir por el usuario acá es mandarle
      // los comprobantes a la razón social equivocada.
      if (r.cuits.length === 1) set('idcuit', r.cuits[0].idcuit)
    } catch (err) {
      setErrorCuits(err instanceof ApiError ? err.detail : 'Error de conexión.')
      setCuits(null)
    } finally {
      setBuscandoCuits(false)
    }
  }

  async function borrarSecreto() {
    setSaving(true)
    try {
      const r = await api.del<DestinoConfig>(
        `/api/facturacion/config/${destino}/secreto/${campoSecreto.campo}`)
      setDatos(r)
      onGuardado(r)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Send className="size-4" />
          {NOMBRES[destino] ?? destino}
          {datos.configurado
            ? <Badge variant="secondary">Habilitado</Badge>
            : <Badge variant="outline">Sin usar</Badge>}
          {datos.desde_entorno && (
            <Badge variant="outline" title="Todavía se lee del entorno del contenedor. Guardar acá pasa a mandar esta configuración.">
              desde el compose
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          {destino === 'sos'
            ? 'El sistema del estudio contable. Los comprobantes llegan sin CAE y los emite el contador.'
            : 'La instancia de Contalibra del mismo cliente. Los comprobantes quedan en su bandeja.'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="grid gap-3" onSubmit={guardar}>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={datos.habilitado}
              onChange={(e) => { setDatos((p) => ({ ...p, habilitado: e.target.checked })); setGuardado(false) }}
            />
            Habilitar este destino
          </label>

          {datos.secretos_ilegibles && (
            <p className="flex items-start gap-2 rounded border border-destructive/40 p-2 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              Hay una credencial guardada que no se puede leer. Suele pasar si
              cambió <code>SECRET_KEY</code> — por ejemplo al restaurar un
              backup en otra instancia. Hay que volver a cargarla.
            </p>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            {CAMPOS[destino].map(({ campo, label, ayuda, ancho }) => {
              const esIdCuit = destino === 'sos' && campo === 'idcuit'
              return (
              <div key={campo} className="grid gap-1">
                <Label htmlFor={`${destino}-${campo}`}>{label}</Label>
                <div className="flex gap-2">
                  <Input
                    id={`${destino}-${campo}`}
                    className={ancho}
                    value={String(datos[campo] ?? '')}
                    onChange={(e) => set(campo, e.target.value)}
                  />
                  {esIdCuit && (
                    <Button type="button" variant="outline" size="sm"
                            onClick={buscarCuits}
                            disabled={buscandoCuits || !String(datos.usuario ?? '').trim()}
                            title="Consulta SOS con el usuario y la contraseña y trae las CUITs de esa cuenta">
                      <Search className="size-4" />
                      {buscandoCuits ? 'Buscando…' : 'Buscar en SOS'}
                    </Button>
                  )}
                </div>
                {ayuda && <p className="text-xs text-muted-foreground">{ayuda}</p>}
                {esIdCuit && errorCuits && (
                  <p className="text-xs text-destructive">{errorCuits}</p>
                )}
                {esIdCuit && cuits !== null && cuits.length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    Ese usuario no tiene ninguna CUIT asociada en SOS.
                  </p>
                )}
                {esIdCuit && cuits !== null && cuits.length > 0 && (
                  <div className="grid gap-1 rounded border p-2">
                    <p className="text-xs text-muted-foreground">
                      {cuits.length === 1
                        ? 'La única CUIT de esa cuenta, ya cargada:'
                        : 'Elegí a cuál se factura desde esta instancia:'}
                    </p>
                    {cuits.map((c) => (
                      <button
                        key={c.idcuit}
                        type="button"
                        onClick={() => set('idcuit', c.idcuit)}
                        className={`flex flex-wrap items-center gap-2 rounded px-2 py-1 text-left text-sm hover:bg-accent ${
                          String(datos.idcuit ?? '') === c.idcuit ? 'bg-accent' : ''
                        }`}
                      >
                        <span className="font-mono text-xs">{c.idcuit}</span>
                        <span>{c.razonsocial}</span>
                        <span className="text-xs text-muted-foreground">{c.cuit}</span>
                        {!c.habilitado && <Badge variant="outline">deshabilitada en SOS</Badge>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )})}

            <div className="grid gap-1">
              <Label htmlFor={`${destino}-secreto`} className="flex items-center gap-1.5">
                <KeyRound className="size-3.5" />
                {campoSecreto.label}
                {secretoCargado && <Badge variant="secondary">cargada</Badge>}
              </Label>
              <div className="flex gap-2">
                <Input
                  id={`${destino}-secreto`}
                  type="password"
                  autoComplete="new-password"
                  placeholder={secretoCargado ? 'Sin cambios' : 'Sin cargar'}
                  value={secreto}
                  onChange={(e) => { setSecreto(e.target.value); setGuardado(false) }}
                />
                {secretoCargado && (
                  <Button type="button" variant="outline" size="icon" title="Borrar la credencial guardada"
                          onClick={borrarSecreto} disabled={saving}>
                    <Trash2 className="size-4" />
                  </Button>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                Se guarda cifrada y no se puede volver a leer desde acá. Dejarlo
                vacío no la borra.
              </p>
            </div>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex items-center gap-2">
            <Button type="submit" disabled={saving}>
              {saving ? 'Guardando…' : 'Guardar'}
            </Button>
            {guardado && (
              <span className="flex items-center gap-1 text-sm text-muted-foreground">
                <Check className="size-4" /> Guardado
              </span>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

export function FacturacionConfigCard() {
  const [destinos, setDestinos] = useState<DestinoConfig[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { cargar() }, [])

  async function cargar() {
    try {
      const r = await api.get<{ destinos: DestinoConfig[] }>('/api/facturacion/config')
      setDestinos(r.destinos)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    }
  }

  function actualizar(d: DestinoConfig) {
    setDestinos((prev) => prev?.map((x) => (x.destino === d.destino ? d : x)) ?? null)
  }

  if (error) return <p className="text-sm text-destructive">{error}</p>
  if (!destinos) return <p className="text-sm text-muted-foreground">Cargando…</p>

  const habilitados = destinos.filter((d) => d.configurado)

  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted-foreground">
        Se puede habilitar uno o los dos. Con los dos habilitados, el destino se
        elige al enviar. <strong className="text-foreground">Desde acá no se
        emite ninguna factura</strong>: los comprobantes llegan sin CAE y los
        emite una persona del otro lado.
      </p>
      {habilitados.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Ningún destino habilitado: la pantalla de Facturación no va a poder
          mandar nada.
        </p>
      )}
      {destinos.map((d) => (
        <DestinoCard key={d.destino} inicial={d} onGuardado={actualizar} />
      ))}
    </div>
  )
}
