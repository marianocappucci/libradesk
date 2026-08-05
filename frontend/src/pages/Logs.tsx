import { Fragment, useCallback, useEffect, useState } from 'react'
import { api, ApiError, type LogsData, type ActividadLog } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  ChevronDown, ChevronRight, KeyRound, LogIn, LogOut, ScrollText, ShieldAlert,
} from 'lucide-react'

const TODOS = '__todos__'

const EVENTO_META: Record<string, { label: string; icon: typeof LogIn; className: string }> = {
  login: { label: 'Ingreso', icon: LogIn, className: 'text-emerald-600' },
  logout: { label: 'Salida', icon: LogOut, className: 'text-muted-foreground' },
  login_fallido: { label: 'Intento fallido', icon: ShieldAlert, className: 'text-destructive' },
}

/** `2026-08-05 14:32:10` → `05/08 14:32`. La fecha completa queda en el title:
 *  la tabla se lee de arriba hacia abajo y el año repetido 100 veces es ruido. */
function cuando(ts: string): string {
  const [fecha, hora] = ts.split(' ')
  if (!fecha || !hora) return ts
  const [, mes, dia] = fecha.split('-')
  return `${dia}/${mes} ${hora.slice(0, 5)}`
}

function valor(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'sí' : 'no'
  return String(v)
}

/** Las columnas que cambiaron, una por línea. Se muestra sólo al desplegar:
 *  en la fila va el qué y el quién, que es lo que se escanea. */
function Cambios({ cambios }: { cambios: Record<string, [unknown, unknown]> }) {
  return (
    <table className="w-full text-xs">
      <tbody>
        {Object.entries(cambios).map(([campo, [antes, despues]]) => (
          <tr key={campo} className="border-b last:border-0">
            <td className="py-1 pr-3 font-medium text-muted-foreground">{campo}</td>
            <td className="py-1 pr-2 text-muted-foreground line-through">{valor(antes)}</td>
            <td className="py-1 font-medium">{valor(despues)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/**
 * Logs — admin-only, gateado también en el backend (`require_admin`).
 *
 * Dos tablas y no una: la actividad del sistema y los accesos son dos preguntas
 * distintas ("quién borró esto" / "quién entró"), se filtran distinto y se
 * miran en momentos distintos. Contalibra las muestra igual.
 *
 * La actividad la escribe el `flush` de SQLAlchemy, así que **no hay nada que
 * activar por entidad**: lo que aparece acá es todo lo que el sistema escribió.
 */
export function Logs() {
  const [data, setData] = useState<LogsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [abierta, setAbierta] = useState<number | null>(null)

  const [entidad, setEntidad] = useState(TODOS)
  const [accion, setAccion] = useState(TODOS)
  const [usuario, setUsuario] = useState(TODOS)
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')

  const cargar = useCallback(async () => {
    setLoading(true)
    setError(null)
    const qs = new URLSearchParams({ page: String(page) })
    if (entidad !== TODOS) qs.set('entidad', entidad)
    if (accion !== TODOS) qs.set('accion', accion)
    if (usuario !== TODOS) qs.set('usuario', usuario)
    if (desde) qs.set('desde', desde)
    if (hasta) qs.set('hasta', hasta)
    try {
      setData(await api.get<LogsData>(`/api/logs?${qs}`))
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    } finally {
      setLoading(false)
    }
  }, [page, entidad, accion, usuario, desde, hasta])

  useEffect(() => { void cargar() }, [cargar])

  // Cualquier filtro nuevo vuelve a la página 1: quedarse en la 4 de un
  // resultado que ahora tiene 2 muestra una tabla vacía que parece un error.
  function filtrar(set: (v: string) => void) {
    return (v: string) => { set(v); setPage(1); setAbierta(null) }
  }

  if (loading && !data) {
    return <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
  }
  if (error && !data) {
    return <p className="py-6 text-center text-sm text-destructive">{error}</p>
  }
  if (!data) return null

  return (
    <div className="grid gap-4">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        <ScrollText className="size-5" />Logs
      </h2>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Actividad del sistema</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {/* `htmlFor` + `id` en el trigger: sin eso el `Label` queda suelto
                y un lector de pantalla anuncia el select sin nombre. */}
            <div className="grid gap-1.5">
              <Label htmlFor="filtro-entidad">Entidad</Label>
              <Select value={entidad} onValueChange={filtrar(setEntidad)}>
                <SelectTrigger id="filtro-entidad"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={TODOS}>Todas</SelectItem>
                  {data.entidades.map((e) => (
                    <SelectItem key={e} value={e}>{e.replace('_', ' ')}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="filtro-accion">Acción</Label>
              <Select value={accion} onValueChange={filtrar(setAccion)}>
                <SelectTrigger id="filtro-accion"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={TODOS}>Todas</SelectItem>
                  {Object.entries(data.acciones).map(([id, meta]) => (
                    <SelectItem key={id} value={id}>{meta.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="filtro-usuario">Usuario</Label>
              <Select value={usuario} onValueChange={filtrar(setUsuario)}>
                <SelectTrigger id="filtro-usuario"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={TODOS}>Todos</SelectItem>
                  {data.usuarios.map((u) => (
                    <SelectItem key={u} value={u}>{u}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="desde">Desde</Label>
              <Input id="desde" type="date" value={desde}
                onChange={(e) => filtrar(setDesde)(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="hasta">Hasta</Label>
              <Input id="hasta" type="date" value={hasta}
                onChange={(e) => filtrar(setHasta)(e.target.value)} />
            </div>
          </div>

          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="w-8 p-2" />
                  <th className="p-2 font-medium">Fecha</th>
                  <th className="p-2 font-medium">Acción</th>
                  <th className="p-2 font-medium">Qué</th>
                  <th className="p-2 font-medium">Usuario</th>
                </tr>
              </thead>
              <tbody>
                {data.actividad.length === 0 && (
                  <tr><td colSpan={5} className="p-6 text-center text-muted-foreground">
                    {data.total === 0 && entidad === TODOS && accion === TODOS && usuario === TODOS && !desde && !hasta
                      ? 'Todavía no hay actividad registrada.'
                      : 'No hay actividad con esos filtros.'}
                  </td></tr>
                )}
                {data.actividad.map((fila: ActividadLog) => {
                  const meta = data.acciones[fila.accion]
                  const tieneCambios = fila.cambios !== null && Object.keys(fila.cambios).length > 0
                  const desplegada = abierta === fila.id
                  return (
                    <Fragment key={fila.id}>
                      <tr
                        className={`border-t ${tieneCambios ? 'cursor-pointer hover:bg-muted/40' : ''}`}
                        onClick={() => tieneCambios && setAbierta(desplegada ? null : fila.id)}
                      >
                        <td className="p-2 text-muted-foreground">
                          {tieneCambios && (desplegada ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />)}
                        </td>
                        <td className="whitespace-nowrap p-2 text-muted-foreground" title={fila.ts}>
                          {cuando(fila.ts)}
                        </td>
                        <td className="p-2">
                          <Badge variant="outline" style={meta ? { borderColor: meta.color, color: meta.color } : undefined}>
                            {meta?.label ?? fila.accion}
                          </Badge>
                        </td>
                        <td className="p-2">
                          {fila.descripcion}
                          {fila.entidad_id !== null && (
                            <span className="ml-1 text-xs text-muted-foreground">#{fila.entidad_id}</span>
                          )}
                        </td>
                        <td className="whitespace-nowrap p-2">{fila.usuario}</td>
                      </tr>
                      {desplegada && fila.cambios && (
                        <tr className="border-t bg-muted/20">
                          <td />
                          <td colSpan={4} className="p-2"><Cambios cambios={fila.cambios} /></td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>

          {data.total_pages > 1 && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">
                Página {data.page} de {data.total_pages} · {data.total} registros
              </span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={data.page <= 1}
                  onClick={() => { setPage((p) => p - 1); setAbierta(null) }}>Anterior</Button>
                <Button variant="outline" size="sm" disabled={data.page >= data.total_pages}
                  onClick={() => { setPage((p) => p + 1); setAbierta(null) }}>Siguiente</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="size-4" />Accesos
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="p-2 font-medium">Fecha</th>
                  <th className="p-2 font-medium">Evento</th>
                  <th className="p-2 font-medium">Usuario</th>
                  <th className="p-2 font-medium">IP</th>
                </tr>
              </thead>
              <tbody>
                {data.accesos.length === 0 && (
                  <tr><td colSpan={4} className="p-6 text-center text-muted-foreground">
                    Todavía no hay accesos registrados.
                  </td></tr>
                )}
                {data.accesos.map((a) => {
                  const meta = EVENTO_META[a.evento]
                  const Icono = meta?.icon ?? LogIn
                  return (
                    <tr key={a.id} className="border-t">
                      <td className="whitespace-nowrap p-2 text-muted-foreground" title={a.ts}>{cuando(a.ts)}</td>
                      <td className="p-2">
                        <span className={`flex items-center gap-1.5 ${meta?.className ?? ''}`}>
                          <Icono className="size-4" />{meta?.label ?? a.evento}
                        </span>
                      </td>
                      <td className="p-2">{a.username}</td>
                      <td className="p-2 font-mono text-xs text-muted-foreground">{a.ip || '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
