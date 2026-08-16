/** La agenda de las cuadrillas, como calendario y con lugar propio en el menú.
 *
 *  **Antes vivía adentro de "Equipos y flota"**, como la pestaña del medio entre
 *  el armado de los equipos y el catálogo de vehículos, y mostraba un solo día.
 *  Pedido del humano (2026-08-14): sacarla de ahí, que se vea *"como una agenda
 *  de verdad, como un calendario donde se vea no sólo el día de hoy sino los
 *  próximos también"*, y que desde ahí se entre a un día a ver qué incidencias
 *  tiene cargada cada cuadrilla e imprimir la hoja de ruta.
 *
 *  Los dos límites que tenía y que esto levanta: no se veía el futuro (para
 *  saber qué hay el jueves había que mover el selector y perder de vista el
 *  resto) y estaba enterrada detrás de un ítem de menú que se llama por el
 *  catálogo de vehículos, siendo lo que se abre todas las mañanas.
 *
 *  **La vista y el día viven en la URL** (`/agenda?vista=semana&dia=2026-08-14`)
 *  y no en un `useState`. Es la regla del producto para las pestañas —la misma
 *  de depósitos, configuración y recepción—: así se puede mandar "mirá el
 *  jueves", el botón "atrás" del navegador vuelve de un día a la semana, y
 *  recargar la página deja al usuario donde estaba. Con estado interno, entrar a
 *  un día desde la semana sería un viaje de ida.
 *
 *  **El filtro de cuadrilla recorta lo que se dibuja, no lo que se pide** (ver
 *  `components/agenda/datos.ts`).
 */
import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react'
import { api, ApiError, type EquipoTrabajo } from '../api'
import { TituloPantalla } from '@/components/titulo-pantalla'
import { Conmutador, type Pestania } from '@/components/conmutador'
import { GenerarVisitas } from '@/components/generar-visitas'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { useAgendaRango } from '@/components/agenda/datos'
import { clasePunto } from '@/components/agenda/colores'
import { VistaDia } from '@/components/agenda/vista-dia'
import { VistaSemana } from '@/components/agenda/vista-semana'
import { VistaMes } from '@/components/agenda/vista-mes'
import {
  celdasGrillaMes, diaLargo, hoyLocal, inicioGrillaMes, lunesDe, mesLargo,
  rangoSemana, sumarDias, sumarMeses,
} from '@/components/agenda/fechas'

type Vista = 'dia' | 'semana' | 'mes'

const VISTAS: Vista[] = ['dia', 'semana', 'mes']
const TODAS = '__todas__'

/** El rango que hay que pedir para dibujar cada vista.
 *
 *  El mes pide **la grilla, no el mes**: arranca en el lunes anterior al día 1 y
 *  llega hasta el domingo que cierra la última semana. Pedir sólo el mes dejaría
 *  esas celdas de los bordes vacías aunque tengan trabajos — y son días reales.
 */
function rango(vista: Vista, dia: string): { desde: string; dias: number } {
  if (vista === 'semana') return { desde: lunesDe(dia), dias: 7 }
  if (vista === 'mes') return { desde: inicioGrillaMes(dia), dias: celdasGrillaMes(dia) }
  return { desde: dia, dias: 1 }
}

/** Cuánto se mueve la flecha en cada vista. */
function correr(vista: Vista, dia: string, signo: 1 | -1): string {
  if (vista === 'semana') return sumarDias(dia, 7 * signo)
  if (vista === 'mes') return sumarMeses(dia, signo)
  return sumarDias(dia, signo)
}

function titulo(vista: Vista, dia: string): string {
  if (vista === 'semana') return rangoSemana(lunesDe(dia))
  if (vista === 'mes') return mesLargo(dia)
  return diaLargo(dia)
}

const LABEL: Record<Vista, string> = { dia: 'Día', semana: 'Semana', mes: 'Mes' }

export function Agenda() {
  const [params, setParams] = useSearchParams()
  const [equipos, setEquipos] = useState<EquipoTrabajo[]>([])
  const [errorEquipos, setErrorEquipos] = useState<string | null>(null)

  // La semana es el default: es lo que el pedido nombra ("no sólo el día de hoy
  // sino los próximos también"). El día sigue a un click de distancia y es a
  // donde llevan todos los encabezados de la grilla.
  const crudo = params.get('vista')
  const vista: Vista = VISTAS.includes(crudo as Vista) ? (crudo as Vista) : 'semana'
  // `hoyLocal()` en cada render y no en un `useState`: si alguien deja la
  // pantalla abierta pasada la medianoche, "hoy" tiene que ser el día nuevo.
  const hoy = hoyLocal()
  const dia = /^\d{4}-\d{2}-\d{2}$/.test(params.get('dia') ?? '')
    ? params.get('dia')!
    : hoy
  const filtro = params.get('equipo') ?? TODAS

  useEffect(() => {
    let vigente = true
    api.get<EquipoTrabajo[]>('/api/equipos-trabajo')
      // `Array.isArray` y no confiar en el tipo: un cuerpo truncado o un `{}`
      // es truthy, y el `.filter()` de adentro del hook tumbaría la pantalla
      // entera con un TypeError en vez de mostrar de menos.
      .then((e) => { if (vigente) setEquipos(Array.isArray(e) ? e : []) })
      .catch((err) => {
        if (vigente) {
          setErrorEquipos(err instanceof ApiError ? err.detail : 'Error de conexión.')
        }
      })
    return () => { vigente = false }
  }, [])

  const { desde, dias } = rango(vista, dia)
  const { porDia, activos, cargando, error } = useAgendaRango(equipos, desde, dias)

  /** Los parámetros de la pantalla con algunos cambiados. Los demás se
   *  conservan: cambiar de vista no tiene por qué olvidar la cuadrilla elegida. */
  const con = useCallback((cambios: Record<string, string>) => {
    const p = new URLSearchParams(params)
    for (const [k, v] of Object.entries(cambios)) p.set(k, v)
    return p
  }, [params])

  const href = useCallback(
    (cambios: Record<string, string>) => `/agenda?${con(cambios)}`,
    [con],
  )

  const pestanias: readonly Pestania[] = VISTAS.map((v) => ({
    clave: v,
    to: href({ vista: v }),
    label: LABEL[v],
    icono: CalendarDays,
  }))

  // El filtro no toca el fetch (ver `datos.ts`): se aplica acá, al dibujar.
  const visibles = filtro === TODAS
    ? porDia
    : Object.fromEntries(Object.entries(porDia).map(([d, ts]) => [
      d, ts.filter((t) => String(t.equipo_id) === filtro),
    ]))
  const equiposVisibles = filtro === TODAS
    ? activos
    : activos.filter((e) => String(e.id) === filtro)

  return (
    <div className="grid gap-4">
      {/* `items-end` pisa al `items-center` del componente (su `cn` es
          `twMerge`, así que gana la clase de acá). Lo que va a la derecha no es
          un botón sino un filtro CON etiqueta: alineado al centro, el select
          queda flotando contra un bloque de título de dos renglones; alineado
          abajo, su base coincide con la del párrafo. */}
      <EncabezadoDePantalla
        className="items-end"
        titulo={
          <div>
            <TituloPantalla icono={CalendarDays}>Agenda</TituloPantalla>
            <p className="text-sm text-muted-foreground">
              Qué tiene cada cuadrilla y en qué sale. Entrá a un día para ver el
              detalle e imprimir la hoja de ruta.
            </p>
          </div>
        }
      >
        {/* Los dos controles van envueltos en UN solo hijo con `items-end`
            propio, y no sueltos. El contenedor de los children del componente
            es `items-center` y desde acá no se lo puede pisar (el `className`
            de arriba va al contenedor de afuera, no a este): con el filtro
            siendo un bloque de dos pisos —etiqueta arriba, select abajo— y el
            botón siendo un control de un piso, centrarlos dejaba al botón a
            media altura del bloque, alineado con nada. Lo reportó el humano
            (2026-08-16). Con este envoltorio las bases del select y del botón
            coinciden, que es el mismo criterio que usa el propio diálogo de
            «Generar visitas» para su fecha + botón. */}
        <div className="flex flex-wrap items-end gap-2">
          <div className="grid gap-2">
            <label htmlFor="filtro-cuadrilla" className="text-sm font-medium">
              Cuadrilla
            </label>
            <Select
              value={filtro}
              onValueChange={(v) => setParams(con({ equipo: v }))}
            >
              <SelectTrigger id="filtro-cuadrilla" className="w-52">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TODAS}>Todas las cuadrillas</SelectItem>
                {activos.map((e) => (
                  <SelectItem key={e.id} value={String(e.id)}>{e.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {/* Generar las visitas de mantenimiento va acá y no en una pantalla
              propia: lo que produce **son** entradas de esta agenda, así que se
              hace donde se ve el resultado. */}
          <GenerarVisitas onGenerado={() => setParams(con({}))} />
        </div>
      </EncabezadoDePantalla>

      {/* La barra de navegación, con la forma de Google Calendar: `Hoy`, las dos
          flechas y el título, **en ese orden y anclados a la izquierda**.
          🔴 El orden importa y no es cosmético. Hasta el 2026-08-14 el grupo
          estaba pegado al borde **derecho** (`justify-between` con el
          conmutador), así que su ancho lo fijaba el largo del título: pasar de
          "Agosto 2026" a "10 al 16 de agosto de 2026" corría las flechas de
          lugar, y apretar dos veces seguidas obligaba a perseguirlas con el
          mouse. Lo reportó el humano. Anclado a la izquierda, el título crece
          hacia la derecha y los controles no se mueven nunca. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <Button size="sm" variant="outline" className="rounded-full px-4" asChild>
            <Link to={href({ dia: hoy })}>Hoy</Link>
          </Button>
          <Button size="icon" variant="ghost" className="rounded-full" asChild aria-label="Anterior">
            <Link to={href({ dia: correr(vista, dia, -1) })}><ChevronLeft /></Link>
          </Button>
          <Button size="icon" variant="ghost" className="rounded-full" asChild aria-label="Siguiente">
            <Link to={href({ dia: correr(vista, dia, 1) })}><ChevronRight /></Link>
          </Button>
          <span className="ml-2 text-xl first-letter:uppercase">
            {titulo(vista, dia)}
          </span>
        </div>
        <Conmutador pestanias={pestanias} actual={vista} />
      </div>

      {/* La referencia de colores: sin ella el color del chip no significa nada
          hasta que se abre uno. No se muestra en la vista de día, que ya viene
          agrupada por cuadrilla y con el nombre en cada tarjeta. */}
      {vista !== 'dia' && activos.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {activos.map((e, i) => (
            <span key={e.id} className="flex items-center gap-1.5">
              <span className={cn('size-2.5 rounded-full', clasePunto(i))} />
              {e.nombre}
            </span>
          ))}
        </div>
      )}

      {(errorEquipos || error) && (
        <p className="text-sm text-destructive">{errorEquipos ?? error}</p>
      )}

      {activos.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
          {cargando || equipos.length === 0
            ? 'Cargando…'
            : 'No hay equipos activos para agendar.'}
        </CardContent></Card>
      ) : vista === 'dia' ? (
        <VistaDia
          dia={dia}
          equipos={equiposVisibles}
          trabajos={visibles[dia] ?? []}
          esHoy={dia === hoy}
        />
      ) : vista === 'semana' ? (
        <VistaSemana
          desde={desde} porDia={visibles} hoy={hoy}
          hrefDia={(d) => href({ vista: 'dia', dia: d })}
        />
      ) : (
        <VistaMes
          desde={desde} celdas={dias} mes={dia} porDia={visibles} hoy={hoy}
          hrefDia={(d) => href({ vista: 'dia', dia: d })}
        />
      )}
    </div>
  )
}
