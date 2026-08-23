/** El día: la rejilla horaria con **una columna por cuadrilla**.
 *
 *  Es la pantalla de despacho de la mañana, y la que contesta entero el pedido
 *  42: *"cuando un equipo tiene asignado un trabajo ya sabe en qué vehículo sale
 *  de acuerdo a la disponibilidad"*.
 *
 *  **Una columna por cuadrilla y no una sola con todo mezclado.** Es el patrón
 *  de Google Calendar cuando se miran varios calendarios a la vez, y acá es
 *  además lo que la pantalla tiene que contestar: al entrar a un día ya se sabe
 *  *cuándo* —lo dijeron la semana y el mes—, y lo que falta es **quién sale, con
 *  quién, en qué, y a qué direcciones**. Mezcladas en una columna, armar el
 *  recorrido de la Cuadrilla Norte obligaría a pescar sus paradas entre las de
 *  las demás.
 *
 *  Por eso el botón de **hoja de ruta va en el encabezado de su columna**: la
 *  hoja es por equipo y por día, que es exactamente lo que la columna delimita.
 *
 *  🔴 **Ésta es la vista que NO se extrajo a `libra-ui/agenda`** cuando el
 *  calendario pasó a ser compartido (2026-08-22), y este encabezado es la razón:
 *  la patente del vehículo y el botón de la hoja de ruta son de este producto y
 *  de ningún otro. La rejilla, el reparto de ancho y los colores sí vienen del
 *  paquete; lo único que se arma acá son las columnas.
 *
 *  Historia: era una lista de tarjetas por cuadrilla
 *  (`components/agenda-equipos.tsx`, después `vista-dia` a secas). Pasó a
 *  rejilla el 2026-08-14 junto con la semana, a pedido del humano. Lo que gana
 *  es el **cuánto ocupa**: la lista decía que había tres trabajos, la rejilla
 *  muestra que dos son de dos horas y que entre las 12:30 y las 16:00 la
 *  cuadrilla está libre.
 */
import { RejillaHoraria, type ColumnaRejilla } from 'libra-ui/agenda'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Car, Printer } from '@/components/iconos-accion'
import { eventoDeDia } from './eventos'
import type { EquipoTrabajo } from '../../api'
import type { TrabajoConEquipo } from './datos'

export function VistaDia({ dia, equipos, trabajos, esHoy }: {
  dia: string
  equipos: EquipoTrabajo[]
  trabajos: TrabajoConEquipo[]
  /** Si el día que se muestra es hoy: la rejilla dibuja la línea de la hora
   *  actual sólo entonces. */
  esHoy: boolean
}) {
  if (equipos.length === 0) {
    return (
      <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
        No hay equipos activos para agendar.
      </CardContent></Card>
    )
  }

  const columnas: ColumnaRejilla[] = equipos.map((e) => {
    const suyos = trabajos.filter((t) => t.equipo_id === e.id)
    const patentes = e.vehiculos.map((v) => v.patente).join(', ')
    return {
      clave: String(e.id),
      // Todas las columnas llevan la línea de "ahora" cuando el día es hoy: son
      // cuadrillas del mismo día, no días distintos.
      esHoy,
      encabezado: (
        <div className="grid gap-1">
          <span className="truncate text-sm font-medium">{e.nombre}</span>
          <div className="flex flex-wrap items-center justify-center gap-1">
            {patentes && (
              <Badge variant="outline" className="gap-1 font-normal">
                <Car className="size-3" />{patentes}
              </Badge>
            )}
            {/* El día del botón es el que se está mirando, no "hoy": la hoja se
                imprime la noche anterior tanto como a la mañana, y una que
                dijera otra fecha que la grilla de al lado es peor que no
                tenerla. */}
            <Button size="sm" variant="outline" className="h-6 px-2 text-xs" asChild>
              <a
                href={`/api/agenda/equipo/${e.id}/hoja-de-ruta?dia=${dia}`}
                target="_blank"
                rel="noreferrer"
              >
                <Printer />Hoja de ruta
              </a>
            </Button>
          </div>
        </div>
      ),
      eventos: suyos.map(eventoDeDia),
    }
  })

  return <RejillaHoraria columnas={columnas} />
}
