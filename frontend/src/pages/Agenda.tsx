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
 *  🔴 **El calendario en sí ya no vive acá** (2026-08-22): la rejilla horaria,
 *  las vistas de semana y mes, la aritmética de días, la paleta y la barra de
 *  navegación salieron a `libra-ui/agenda` para que Gestiolibra las use también.
 *  Lo que queda en este archivo es lo que **es** de LibraDesk: de dónde salen
 *  los datos, el filtro por cuadrilla, generar visitas, el conmutador de vistas
 *  y la vista de día con su hoja de ruta.
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
import { useSearchParams } from 'react-router-dom'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import { CalendarDays } from 'lucide-react'
import { api, ApiError, type EquipoTrabajo } from '../api'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'
import {
  LABEL_VISTA, NavegadorCalendario, ReferenciaDeColores, VISTAS, VistaMes,
  VistaSemana, clasePunto, diaDeLaUrl, hoyLocal, rangoDeVista, vistaDeLaUrl,
} from 'libra-ui/agenda'
import { Conmutador, type Pestania } from '@/components/conmutador'
import { GenerarVisitas } from '@/components/generar-visitas'
import { Card, CardContent } from '@/components/ui/card'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useAgendaRango } from '@/components/agenda/datos'
import { eventoDeChip, eventoDeSemana, porDiaComoEventos } from '@/components/agenda/eventos'
import { VistaDia } from '@/components/agenda/vista-dia'

const TODAS = '__todas__'

export function Agenda() {
  const [params, setParams] = useSearchParams()
  const [equipos, setEquipos] = useState<EquipoTrabajo[]>([])
  const [errorEquipos, setErrorEquipos] = useState<string | null>(null)

  const vista = vistaDeLaUrl(params.get('vista'))
  // `hoyLocal()` en cada render y no en un `useState`: si alguien deja la
  // pantalla abierta pasada la medianoche, "hoy" tiene que ser el día nuevo.
  const hoy = hoyLocal()
  const dia = diaDeLaUrl(params.get('dia'), hoy)
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

  const { desde, dias } = rangoDeVista(vista, dia)
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
    label: LABEL_VISTA[v],
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

      <NavegadorCalendario vista={vista} dia={dia} hoy={hoy} href={href}>
        <Conmutador pestanias={pestanias} actual={vista} />
      </NavegadorCalendario>

      {/* La referencia de colores no se muestra en la vista de día, que ya
          viene con una columna por cuadrilla y el nombre en cada encabezado. */}
      {vista !== 'dia' && (
        <ReferenciaDeColores carriles={activos.map((e, i) => ({
          clave: String(e.id), nombre: e.nombre, clasePunto: clasePunto(i),
        }))} />
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
          desde={desde} porDia={porDiaComoEventos(visibles, eventoDeSemana)} hoy={hoy}
          hrefDia={(d) => href({ vista: 'dia', dia: d })}
        />
      ) : (
        <VistaMes
          desde={desde} celdas={dias} mes={dia}
          porDia={porDiaComoEventos(visibles, eventoDeChip)} hoy={hoy}
          hrefDia={(d) => href({ vista: 'dia', dia: d })}
        />
      )}
    </div>
  )
}
