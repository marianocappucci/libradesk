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
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import { AlarmClock, CalendarClock, CalendarDays, FileExclamationPoint as FileWarning, LayoutDashboard, ShieldCheck, UserX, Wrench } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'
import {
  api, ApiError, ESTADO_LABELS, PRIORIDAD_LABELS,
  type DashboardOperativo, type DashboardSummary, type EquipoTrabajo,
} from '../api'
import { useAgendaRango } from '@/components/agenda/datos'
import { Chip } from '@/components/agenda/chip'
import { diaCorto, hoyLocal, lunesDe, sumarDias } from '@/components/agenda/fechas'
import { Badge } from '@/components/ui/badge'
import { BadgeEstado, type TonoEstado } from 'libra-ui/badge-estado'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

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

function tono(dias: number): TonoEstado {
  if (dias < 0) return 'negativo'
  if (dias <= 7) return 'atencion'
  return 'neutro'
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
        {/* El número también lleva a la pantalla, no sólo el «Ver los N» del
            pie: es lo más grande de la tarjeta y es lo que la mano busca.
            Cuando el total es 0 no se linkea — un link a una lista vacía es un
            viaje al vacío. */}
        <CardTitle className="text-3xl">
          {total === 0
            ? total
            : <Link to={verMas} className="hover:underline">{total}</Link>}
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-2 text-sm">
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
function Fila({ principal, secundario, dias, a }: {
  principal: string
  secundario?: string
  dias: number
  /** A dónde lleva la fila. Sin esto es sólo texto, que es lo que el humano
   *  reportó el 2026-08-16: «la mayoría de las cosas que están en el dashboard
   *  no se pueden clickear para ir hasta el evento». Un dashboard que dice que
   *  hay algo y no lleva hasta eso obliga a buscarlo a mano en otra pantalla. */
  a?: string
}) {
  const texto = (
    <>
      {principal}
      {secundario && <span className="text-muted-foreground"> · {secundario}</span>}
    </>
  )
  return (
    // 🔴 `min-w-0` en la FILA, no sólo en el texto: estas filas son ítems de
    // un grid, y un ítem de grid no baja de su contenido (`min-width: auto`),
    // así que la fila se estiraba y el `truncate` de adentro nunca llegaba a
    // aplicarse. Se veía recién con nombres largos de verdad — con los datos
    // de ejemplo cortos, no.
    <div className="flex min-w-0 items-center justify-between gap-2">
      {a
        ? <Link to={a} className="min-w-0 truncate hover:underline">{texto}</Link>
        : <span className="min-w-0 truncate">{texto}</span>}
      <BadgeEstado tono={tono(dias)} className="shrink-0 whitespace-nowrap">
        {cuando(dias)}
      </BadgeEstado>
    </div>
  )
}

/** Un número grande que lleva a su pantalla.
 *
 *  El 0 NO se linkea: un link a una lista vacía es un viaje al vacío, y de paso
 *  distingue a simple vista lo que tiene algo para mirar de lo que no.
 */
function Numero({ valor, a }: { valor: number | string; a?: string }) {
  if (!a || valor === 0) return <>{valor}</>
  return <Link to={a} className="hover:underline">{valor}</Link>
}

/** La semana de las cuadrillas, en el dashboard.
 *
 *  Pedido del humano (2026-08-14): que la agenda esté presente en la pantalla
 *  principal. Es una **mirilla**, no la agenda: siete columnas con lo que hay y
 *  el link a la pantalla de verdad, que es donde se filtra, se cambia de mes y
 *  se imprime la hoja de ruta.
 *
 *  Componente aparte y no un bloque inline porque tiene su propio `useEffect` y
 *  su propio hook de datos, y los hooks no pueden colgar de un `&&`.
 *
 *  ⚠️ Agrega una llamada por cuadrilla activa al abrir la pantalla que se abre
 *  primero. Con las pocas que tiene una empresa de esto es el mismo costo que ya
 *  paga la agenda; si algún día son decenas, el arreglo es un endpoint agregador
 *  —no sacar el bloque—. */
function SemanaDeCuadrillas() {
  const [equipos, setEquipos] = useState<EquipoTrabajo[]>([])
  const hoy = hoyLocal()
  const lunes = lunesDe(hoy)

  useEffect(() => {
    let vigente = true
    api.get<EquipoTrabajo[]>('/api/equipos-trabajo')
      // Misma guarda por forma que el resto de la pantalla: un `{}` es truthy y
      // el `.filter()` del hook tumbaría el dashboard entero.
      .then((e) => { if (vigente) setEquipos(Array.isArray(e) ? e : []) })
      .catch(() => { /* el bloque se muestra vacío; el error grande ya está arriba */ })
    return () => { vigente = false }
  }, [])

  const { porDia, activos, cargando } = useAgendaRango(equipos, lunes, 7)
  const dias = Array.from({ length: 7 }, (_, i) => sumarDias(lunes, i))

  // Sin cuadrillas no hay bloque: en una instalación que no usa equipos de
  // trabajo, siete columnas vacías serían ruido permanente en la pantalla
  // principal. No es lo mismo que un bloque de vencimientos en cero, que sí
  // informa ("no vence nada").
  if (!cargando && activos.length === 0) return null

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardDescription className="flex items-center gap-2">
          <CalendarDays className="h-4 w-4" />
          Las cuadrillas, esta semana
        </CardDescription>
        <Button asChild variant="link" size="sm" className="h-auto justify-start p-0">
          <Link to="/agenda">Ver la agenda</Link>
        </Button>
      </CardHeader>
      <CardContent className="grid gap-2 md:grid-cols-7">
        {dias.map((dia) => {
          const trabajos = porDia[dia] ?? []
          const esHoy = dia === hoy
          return (
            <div
              key={dia}
              className={cn(
                'flex flex-col gap-1 rounded-md border p-2',
                esHoy && 'border-primary bg-primary/5',
              )}
            >
              <Link
                to={`/agenda?vista=dia&dia=${dia}`}
                className={cn(
                  'text-xs font-medium hover:underline',
                  esHoy ? 'text-primary' : 'text-muted-foreground',
                )}
              >
                {diaCorto(dia)}
              </Link>
              {trabajos.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  {cargando ? '…' : '—'}
                </p>
              ) : (
                <>
                  {trabajos.slice(0, 2).map((t) => (
                    <Chip key={`${t.equipo_id}-${t.incidencia_id}`} t={t} compacto />
                  ))}
                  {trabajos.length > 2 && (
                    <Link
                      to={`/agenda?vista=dia&dia=${dia}`}
                      className="px-1 text-xs text-muted-foreground hover:underline"
                    >
                      +{trabajos.length - 2} más
                    </Link>
                  )}
                </>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
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
      {/* `items-end` por lo mismo que la Agenda: a la derecha va un filtro con
          etiqueta, no un botón, y su base tiene que coincidir con la del
          párrafo del título. El `cn` del componente es `twMerge`, así que esta
          clase le gana al `items-center` de adentro. */}
      <EncabezadoDePantalla
        className="items-end"
        titulo={
          <div>
            {/* Es el título de ESTA pantalla, no una sección adentro: el
                Dashboard no tenía otro. Por eso sale del mismo componente que el
                resto y no de un `<h2>` a mano — era el único que quedaba con el
                tamaño del título pero sin su tratamiento. */}
            <TituloPantalla icono={LayoutDashboard}>Qué hay que hacer</TituloPantalla>
            <p className="text-sm text-muted-foreground">
              Lo que se vence, lo que espera hace mucho y lo que está en el taller.
            </p>
          </div>
        }
      >
        <div className="grid gap-2">
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
      </EncabezadoDePantalla>

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
                      dias={c.dias_restantes} a={`/contratos/${c.id}`} />
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
                      dias={g.dias_restantes} a={`/equipos/${g.id}`} />
              ))}
            </BloqueVencimiento>

            <BloqueVencimiento
              titulo="Turnos agendados" icono={CalendarClock}
              total={operativo.vencimientos.agenda.total}
              mostrados={operativo.vencimientos.agenda.items.length}
              // A la agenda y no al listado de tickets: éste es el link que se
              // aprieta queriendo ver la agenda, y hasta el 2026-08-14 caía en
              // `/incidencias`, que es otra pregunta.
              verMas="/agenda"
            >
              {operativo.vencimientos.agenda.items.map((t) => (
                // A la ficha del ticket y no a la agenda: la agenda es a dónde
                // lleva «Ver los N», y desde una fila lo que se quiere es el
                // trabajo que dice esa fila.
                <Fila key={t.id} principal={t.titulo} secundario={t.cliente}
                      dias={t.dias_restantes} a={`/incidencias/${t.id}`} />
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
                      dias={-e.dias} a={`/equipos/${e.id}`} />
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
                <CardTitle className="text-3xl">
                  <Numero valor={backlog.total_abiertas} a="/incidencias" />
                </CardTitle>
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

                <div className="grid gap-2 text-sm">
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
                            <BadgeEstado tono={i.dias > 30 ? 'negativo' : 'atencion'}>
                              {i.dias} d
                            </BadgeEstado>
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

      {/* Fuera de la guarda de `operativo`: la agenda tiene su propia consulta y
          no tiene por qué desaparecer porque el bloque operativo falle. */}
      <SemanaDeCuadrillas />

      {/* Los totales, abajo: son contexto, no acción. Y con el filtro de fechas
          acá, que es el único lugar donde de verdad filtra. */}
      <div className="grid gap-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h3 className="text-base font-semibold">Totales</h3>
          <div className="flex items-end gap-3">
            <div className="grid gap-2">
              <Label htmlFor="date-from">Desde</Label>
              <Input id="date-from" type="date" value={dateFrom} className="w-40"
                     onChange={(e) => setDateFrom(e.target.value)} />
            </div>
            <div className="grid gap-2">
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
                <CardTitle className="text-3xl">
                  <Numero valor={summary.incidencias_en_rango} a="/incidencias" />
                </CardTitle>
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
                {/* Las horas NO llevan a ninguna parte, a proposito: son una SUMA,
                    no una lista de cosas que se puedan abrir. Linkearlas a
                    /incidencias mandaria a un listado que no explica el numero. */}
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
                <CardTitle className="text-3xl">
                  <Numero valor={summary.total_clientes_activos} a="/clientes" />
                </CardTitle>
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
                <CardTitle className="text-3xl">
                  <Numero valor={summary.total_equipos} a="/equipos" />
                </CardTitle>
                <CardDescription>registrados (total, no del rango)</CardDescription>
              </CardHeader>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}
