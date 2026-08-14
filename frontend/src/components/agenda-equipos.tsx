/** La agenda del día, una columna por equipo (pedido 42, fase B).
 *
 *  Es la vista que contesta el pedido entero: *"cuando un equipo tiene asignado
 *  un trabajo ya sabe en qué vehículo sale de acuerdo a la disponibilidad"*.
 *  La fase A dejó lo del vehículo; lo que faltaba era el **cuándo**, y sin una
 *  pantalla que lo muestre lado a lado la disponibilidad sigue sin verse.
 *
 *  **Por día y no por semana.** El despacho de una empresa de soporte se hace a
 *  la mañana para ese día; una grilla semanal de 7×N equipos no entra en
 *  pantalla y obliga a scrollear para responder la única pregunta que se hace
 *  todos los días. El endpoint acepta `dias`, así que la semana es agregable
 *  después sin tocar el backend.
 *
 *  **Una llamada por equipo, en paralelo.** El endpoint es por equipo porque la
 *  validación de choques también lo es (el recurso es el equipo). Con la
 *  cantidad de cuadrillas que tiene una empresa de esto —unas pocas— el fan-out
 *  es más barato que sostener un segundo endpoint agregador que diga lo mismo.
 */
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api, ApiError, ESTADO_LABELS, MODALIDAD_LABELS,
  type EquipoTrabajo, type TrabajoAgendado,
} from '../api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Car, Printer } from '@/components/iconos-accion'

/** Hoy en `YYYY-MM-DD`, hora local.
 *
 * `toISOString()` daría UTC y en Argentina (UTC-3) antes de las 21:00 devuelve
 * el día anterior — la agenda abriría en el día equivocado media tarde. */
function hoyLocal(): string {
  const d = new Date()
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 10)
}

/** La hora en 24 h, siempre.
 *
 * `hour12: false` explícito y no el default del locale: los datos de ICU de
 * Node dan `09:00 a. m.` para es-AR donde el navegador da `09:00`, así que sin
 * esto el formato de la grilla dependería de dónde corra. Y una agenda de
 * despacho se lee en 24 h. */
function hora(iso: string): string {
  return new Date(iso).toLocaleTimeString('es-AR', {
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

export function AgendaEquipos({ equipos }: { equipos: EquipoTrabajo[] }) {
  const [dia, setDia] = useState(hoyLocal)
  const [agendas, setAgendas] = useState<Record<number, TrabajoAgendado[]>>({})
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Sólo los activos: un equipo dado de baja no se despacha, y su columna vacía
  // sería ruido permanente en la única pantalla que se mira todos los días.
  const activos = equipos.filter((e) => e.activo)
  const ids = activos.map((e) => e.id).join(',')

  const cargar = useCallback(async () => {
    if (!ids) { setAgendas({}); return }
    setCargando(true)
    setError(null)
    try {
      const resultados = await Promise.all(
        ids.split(',').map(async (id) => [
          Number(id),
          await api.get<TrabajoAgendado[]>(`/api/agenda/equipo/${id}?desde=${dia}`),
        ] as const),
      )
      setAgendas(Object.fromEntries(resultados))
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    } finally {
      setCargando(false)
    }
  }, [ids, dia])

  useEffect(() => { void cargar() }, [cargar])

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-end justify-between gap-3">
        {/* Sin título propio: desde que la agenda es una pestaña, el conmutador
            ya la nombra, y repetirlo debajo haría parecer que son dos cosas. */}
        <p className="max-w-prose text-sm text-muted-foreground">
          Qué tiene cada equipo y en qué sale. Dos trabajos del mismo equipo no
          se pueden pisar: al agendarlos, el sistema los rechaza.
        </p>
        <div className="grid gap-1.5">
          <Label htmlFor="dia-agenda">Día</Label>
          <Input
            id="dia-agenda"
            type="date"
            className="w-auto"
            value={dia}
            onChange={(e) => setDia(e.target.value)}
          />
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {activos.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
          No hay equipos activos para agendar.
        </CardContent></Card>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {activos.map((e) => {
            const trabajos = agendas[e.id] ?? []
            const patentes = e.vehiculos.map((v) => v.patente).join(', ')
            return (
              <Card key={e.id}>
                <CardHeader className="pb-3">
                  <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                    {e.nombre}
                    {patentes && (
                      <Badge variant="outline" className="gap-1 font-normal">
                        <Car className="size-3" />{patentes}
                      </Badge>
                    )}
                    {/* El día del botón es el del selector de arriba, no "hoy":
                        la hoja se imprime la noche anterior tanto como a la
                        mañana, y una que dijera otra fecha que la grilla que se
                        está mirando es peor que no tenerla. */}
                    <Button size="sm" variant="outline" className="ml-auto" asChild>
                      <a
                        href={`/api/agenda/equipo/${e.id}/hoja-de-ruta?dia=${dia}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <Printer />Hoja de ruta
                      </a>
                    </Button>
                  </CardTitle>
                </CardHeader>
                <CardContent className="grid gap-2">
                  {cargando && trabajos.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Cargando…</p>
                  ) : trabajos.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Sin trabajos ese día.</p>
                  ) : (
                    trabajos.map((t) => (
                      <div
                        key={t.incidencia_id}
                        className="grid gap-y-0.5 border-l-2 pl-3"
                      >
                        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                          <span className="font-mono text-sm tabular-nums">
                            {hora(t.desde)}–{hora(t.hasta)}
                          </span>
                          <Link
                            to={`/incidencias/${t.incidencia_id}`}
                            className="text-sm font-medium hover:underline"
                          >
                            {t.titulo}
                          </Link>
                          <span className="text-sm text-muted-foreground">
                            {t.cliente_nombre ?? 'Sin cliente'}
                          </span>
                          <Badge variant="secondary" className="font-normal">
                            {ESTADO_LABELS[t.estado]}
                          </Badge>
                          {t.modalidad && (
                            <Badge variant="outline" className="font-normal">
                              {MODALIDAD_LABELS[t.modalidad]}
                            </Badge>
                          )}
                        </div>
                        {/* En renglón propio y no como una etiqueta más: es lo
                            que se lee para ordenar el recorrido, y apretado
                            entre los badges se pierde. No se muestra nada si el
                            cliente no tiene domicilio cargado — un "—" acá sería
                            una fila de ruido en cada trabajo remoto. */}
                        {t.cliente_domicilio && (
                          <span className="text-xs text-muted-foreground">
                            {[t.cliente_domicilio, t.cliente_ciudad]
                              .filter(Boolean).join(', ')}
                          </span>
                        )}
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
