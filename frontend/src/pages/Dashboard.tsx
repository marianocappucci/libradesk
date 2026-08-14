// Dashboard — reescrito el 2026-08-05 (pedido: "está muy incompleto, podría
// tener mucha más información y de mejor manera").
//
// **Es un dashboard operativo**, decidido con el humano: contesta *qué hay que
// hacer hoy*, no *cómo viene el mes*. Son dos pantallas distintas y la que
// había no era ninguna de las dos — cuatro tarjetas con seis totales absolutos
// que no cambiaban de un día para el otro y cubrían 3 de las 23 áreas del
// producto.
//
// El orden de la pantalla es el orden de la urgencia:
//
//   1. Lo que se vence (contratos, garantías, turnos) y lo que está esperando.
//   2. El backlog por antigüedad — la pregunta que un sistema de tickets tiene
//      que contestar, y que el desglose por estado no contestaba.
//   3. Lo que hay físicamente en el taller.
//   4. Los totales de siempre, abajo, que son contexto y no acción.
//
// 🔴 **El filtro de fechas quedó donde de verdad filtra.** Antes movía un solo
// número de seis y la pantalla no lo decía: el usuario cambiaba el rango, veía
// que casi nada se movía y no tenía cómo saber cuáles lo miraban. Ahora los dos
// números que responden al rango están juntos y rotulados, y los totales
// absolutos dicen que lo son.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlarmClock, CalendarClock, FileExclamationPoint as FileWarning, ShieldCheck, UserX, Wrench } from 'lucide-react'
import {
  api, ApiError, ESTADO_LABELS, PRIORIDAD_LABELS,
  type DashboardOperativo, type DashboardSummary,
} from '../api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function firstOfMonthIso(): string {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10)
}

/** Los tramos del backlog, con el rótulo que se lee en pantalla. Las claves
 *  son las que devuelve `app/services/dashboard.py`. */
const TRAMOS: { clave: string; label: string; alarma: boolean }[] = [
  { clave: 'hasta_7_dias', label: 'Hasta 7 días', alarma: false },
  { clave: 'de_8_a_30_dias', label: 'De 8 a 30 días', alarma: false },
  { clave: 'mas_de_30_dias', label: 'Más de 30 días', alarma: true },
]

/** `dias_restantes` → texto. Es negativo cuando ya venció, y eso **no es un
 *  caso raro**: un contrato vigente cuya fecha de fin pasó sigue apareciendo
 *  acá, que es justamente lo que hay que atender. */
function cuando(dias: number): string {
  if (dias < 0) return `vencido hace ${Math.abs(dias)} d`
  if (dias === 0) return 'hoy'
  if (dias === 1) return 'mañana'
  return `en ${dias} d`
}

function tono(dias: number): 'destructive' | 'secondary' | 'outline' {
  if (dias < 0) return 'destructive'
  if (dias <= 7) return 'secondary'
  return 'outline'
}

/** Un bloque de "lo que se vence": el número grande, y los más próximos.
 *
 *  Cuando no hay nada **no se esconde**: una tarjeta que desaparece deja al
 *  usuario sin saber si es que no hay vencimientos o si el bloque se rompió. */
function BloqueVencimiento({
  titulo, icono: Icono, total, mostrados, verMas, children,
}: {
  titulo: string
  icono: typeof CalendarClock
  total: number
  mostrados: number
  verMas: string
  children: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardDescription className="flex items-center gap-2">
          <Icono className="h-4 w-4" />
          {titulo}
        </CardDescription>
        <CardTitle className="text-3xl">{total}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-1.5 text-sm">
        {total === 0 ? (
          <p className="text-muted-foreground">Nada en el horizonte elegido.</p>
        ) : (
          <>
            {children}
            {total > mostrados && (
              <Button asChild variant="link" size="sm" className="h-auto justify-start p-0">
                <Link to={verMas}>Ver los {total}</Link>
              </Button>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

/** Una fila de bloque: descripción a la izquierda, cuándo a la derecha. */
function Fila({ principal, secundario, dias }: {
  principal: string
  secundario?: string
  dias: number
}) {
  return (
    // 🔴 `min-w-0` en la FILA, no sólo en el texto: estas filas son ítems de
    // un grid, y un ítem de grid no baja de su contenido (`min-width: auto`),
    // así que la fila se estiraba y el `truncate` de adentro nunca llegaba a
    // aplicarse. Se veía recién con nombres largos de verdad — con los datos
    // de ejemplo cortos, no.
    <div className="flex min-w-0 items-center justify-between gap-2">
      <span className="min-w-0 truncate">
        {principal}
        {secundario && <span className="text-muted-foreground"> · {secundario}</span>}
      </span>
      <Badge variant={tono(dias)} className="shrink-0 whitespace-nowrap">
        {cuando(dias)}
      </Badge>
    </div>
  )
}

export function Dashboard() {
  const [dateFrom, setDateFrom] = useState(firstOfMonthIso())
  const [dateTo, setDateTo] = useState(todayIso())
  const [dias, setDias] = useState('30')
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [operativo, setOperativo] = useState<DashboardOperativo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let vigente = true
    api.get<DashboardOperativo>(`/api/dashboard/operativo?dias=${dias}`)
      .then((d) => { if (vigente) setOperativo(d) })
      .catch((err) => {
        if (vigente) setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
      })
      .finally(() => { if (vigente) setLoading(false) })
    return () => { vigente = false }
  }, [dias])

  useEffect(() => {
    // Los totales van en su propia consulta: si el rango de fechas se mueve, no
    // hay por qué recalcular vencimientos y backlog, que no dependen de él.
    let vigente = true
    api.get<DashboardSummary>(`/api/dashboard?date_from=${dateFrom}&date_to=${dateTo}`)
      .then((d) => { if (vigente) setSummary(d) })
      .catch(() => { /* el error del bloque principal ya se muestra arriba */ })
    return () => { vigente = false }
  }, [dateFrom, dateTo])

  const backlog = operativo?.backlog
  const respondenAlRango = new Set(summary?.responden_al_rango ?? [])

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Qué hay que hacer</h2>
          <p className="text-sm text-muted-foreground">
            Lo que se vence, lo que espera hace mucho y lo que está en el taller.
          </p>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="horizonte">Horizonte</Label>
          <Select value={dias} onValueChange={setDias}>
            <SelectTrigger id="horizonte" className="w-40" aria-label="Horizonte de vencimientos">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Próximos 7 días</SelectItem>
              <SelectItem value="30">Próximos 30 días</SelectItem>
              <SelectItem value="90">Próximos 90 días</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-44" />)}
        </div>
      )}

      {/* 🔴 La guarda mira `vencimientos`, no `operativo` a secas: un cuerpo
          que llega truncado —o un `{}`— es **truthy**, y con `operativo &&` la
          pantalla entera se cae con un TypeError en lugar de mostrar de menos.
          Lo encontró el smoke test, cuyo mock devuelve `{}` para todo lo que no
          conoce; en producción sería una respuesta a medias. */}
      {operativo?.vencimientos && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <BloqueVencimiento
              titulo="Contratos por vencer" icono={FileWarning}
              total={operativo.vencimientos.contratos.total}
              mostrados={operativo.vencimientos.contratos.items.length}
              verMas="/contratos"
            >
              {operativo.vencimientos.contratos.items.map((c) => (
                <Fila key={c.id} principal={c.numero} secundario={c.cliente}
                      dias={c.dias_restantes} />
              ))}
            </BloqueVencimiento>

            <BloqueVencimiento
              titulo="Garantías por vencer" icono={ShieldCheck}
              total={operativo.vencimientos.garantias.total}
              mostrados={operativo.vencimientos.garantias.items.length}
              verMas="/equipos"
            >
              {operativo.vencimientos.garantias.items.map((g) => (
                <Fila key={g.id} principal={g.equipo} secundario={g.cliente}
                      dias={g.dias_restantes} />
              ))}
            </BloqueVencimiento>

            <BloqueVencimiento
              titulo="Turnos agendados" icono={CalendarClock}
              total={operativo.vencimientos.agenda.total}
              mostrados={operativo.vencimientos.agenda.items.length}
              verMas="/incidencias"
            >
              {operativo.vencimientos.agenda.items.map((t) => (
                <Fila key={t.id} principal={t.titulo} secundario={t.cliente}
                      dias={t.dias_restantes} />
              ))}
            </BloqueVencimiento>

            <BloqueVencimiento
              titulo="En el taller" icono={Wrench}
              total={operativo.taller.total}
              mostrados={operativo.taller.items.length}
              verMas="/recepciones"
            >
              {operativo.taller.items.map((e) => (
                // Acá el número son días **transcurridos**, no restantes: se
                // pasa en negativo para que se lea "hace N d" y se pinte con
                // la misma escala que un vencimiento pasado.
                <Fila key={e.id} principal={e.equipo} secundario={e.cliente}
                      dias={-e.dias} />
              ))}
            </BloqueVencimiento>
          </div>

          {backlog && (
            <Card>
              <CardHeader className="pb-3">
                <CardDescription className="flex items-center gap-2">
                  <AlarmClock className="h-4 w-4" />
                  Incidencias abiertas, por cuánto llevan esperando
                </CardDescription>
                <CardTitle className="text-3xl">{backlog.total_abiertas}</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 lg:grid-cols-2">
                <div className="grid gap-2">
                  {TRAMOS.map(({ clave, label, alarma }) => {
                    const n = backlog.por_antiguedad[clave] ?? 0
                    return (
                      <div key={clave} className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">{label}</span>
                        <span className={
                          alarma && n > 0 ? 'font-semibold text-destructive' : 'font-medium'
                        }>
                          {n}
                        </span>
                      </div>
                    )
                  })}
                  {operativo.sin_asignar > 0 && (
                    <div className="flex items-center justify-between border-t pt-2 text-sm">
                      <span className="flex items-center gap-2 text-muted-foreground">
                        <UserX className="h-4 w-4" />
                        Sin técnico asignado
                      </span>
                      <span className="font-semibold text-destructive">
                        {operativo.sin_asignar}
                      </span>
                    </div>
                  )}
                </div>

                <div className="grid gap-1.5 text-sm">
                  {backlog.mas_viejas.length === 0 ? (
                    <p className="text-muted-foreground">No hay incidencias abiertas.</p>
                  ) : (
                    <>
                      <p className="text-xs text-muted-foreground">Las que más esperan</p>
                      {backlog.mas_viejas.map((i) => (
                        <div key={i.id} className="flex min-w-0 items-center justify-between gap-2">
                          <Link to={`/incidencias/${i.id}`} className="min-w-0 truncate hover:underline">
                            {i.titulo}
                            <span className="text-muted-foreground"> · {i.cliente}</span>
                          </Link>
                          <span className="flex shrink-0 items-center gap-2">
                            <Badge variant="outline">
                              {PRIORIDAD_LABELS[i.prioridad as keyof typeof PRIORIDAD_LABELS] ?? i.prioridad}
                            </Badge>
                            <Badge variant={i.dias > 30 ? 'destructive' : 'secondary'}>
                              {i.dias} d
                            </Badge>
                          </span>
                        </div>
                      ))}
                    </>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* Los totales, abajo: son contexto, no acción. Y con el filtro de fechas
          acá, que es el único lugar donde de verdad filtra. */}
      <div className="grid gap-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h3 className="text-base font-semibold">Totales</h3>
          <div className="flex items-end gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="date-from">Desde</Label>
              <Input id="date-from" type="date" value={dateFrom} className="w-40"
                     onChange={(e) => setDateFrom(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="date-to">Hasta</Label>
              <Input id="date-to" type="date" value={dateTo} className="w-40"
                     onChange={(e) => setDateTo(e.target.value)} />
            </div>
          </div>
        </div>

        {/* Misma guarda por forma que arriba: `summary` truthy no garantiza
            que traiga los números, y un `{}` tumbaría toda la pantalla. */}
        {summary?.responden_al_rango && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader>
                <CardDescription>Incidencias</CardDescription>
                <CardTitle className="text-3xl">{summary.incidencias_en_rango}</CardTitle>
                <CardDescription>
                  {respondenAlRango.has('incidencias_en_rango')
                    ? 'creadas en el rango elegido'
                    : 'en total'}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {Object.entries(summary.incidencias_por_estado)
                    .filter(([, count]) => count > 0)
                    .map(([estado, count]) => (
                      <li key={estado} className="flex justify-between">
                        <span>{ESTADO_LABELS[estado as keyof typeof ESTADO_LABELS] ?? estado}</span>
                        <span className="font-medium text-foreground">{count}</span>
                      </li>
                    ))}
                </ul>
                {/* 🔴 El desglose por estado NO responde al rango, y el número
                    grande de arriba sí. Sin este renglón los dos se leen como
                    lo mismo y no cierran entre sí. */}
                <p className="mt-2 text-xs text-muted-foreground">
                  El desglose por estado es histórico, no del rango.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardDescription>Horas invertidas</CardDescription>
                <CardTitle className="text-3xl">{summary.horas_en_rango.toFixed(1)}</CardTitle>
                <CardDescription>en el rango elegido</CardDescription>
              </CardHeader>
              <CardContent>
                {/* Antes este número era el histórico y colgaba del subtítulo
                    de "Equipos", que no tiene nada que ver con las horas. */}
                <p className="text-sm text-muted-foreground">
                  {summary.horas_totales_invertidas.toFixed(1)} hs desde siempre
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardDescription>Clientes</CardDescription>
                <CardTitle className="text-3xl">{summary.total_clientes_activos}</CardTitle>
                <CardDescription>activos (total, no del rango)</CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {Object.entries(summary.incidencias_por_prioridad_abiertas)
                    .filter(([, count]) => count > 0)
                    .map(([prioridad, count]) => (
                      <li key={prioridad} className="flex justify-between">
                        <span>
                          {PRIORIDAD_LABELS[prioridad as keyof typeof PRIORIDAD_LABELS] ?? prioridad}
                        </span>
                        <span className="font-medium text-foreground">{count}</span>
                      </li>
                    ))}
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardDescription>Equipos</CardDescription>
                <CardTitle className="text-3xl">{summary.total_equipos}</CardTitle>
                <CardDescription>registrados (total, no del rango)</CardDescription>
              </CardHeader>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}
