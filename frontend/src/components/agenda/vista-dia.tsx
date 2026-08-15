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
 *  Historia: era una lista de tarjetas por cuadrilla
 *  (`components/agenda-equipos.tsx`, después `vista-dia` a secas). Pasó a
 *  rejilla el 2026-08-14 junto con la semana, a pedido del humano. Lo que gana
 *  es el **cuánto ocupa**: la lista decía que había tres trabajos, la rejilla
 *  muestra que dos son de dos horas y que entre las 12:30 y las 16:00 la
 *  cuadrilla está libre.
 */
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Car, Printer } from '@/components/iconos-accion'
import { RejillaHoraria, type ColumnaRejilla } from './rejilla-horaria'
import { claseChip } from './colores'
import { MODALIDAD_LABELS, type EquipoTrabajo } from '../../api'
import type { TrabajoConEquipo } from './datos'

/** El domicilio con su ciudad, sin repetirla si ya viene adentro.
 *
 * Los clientes reales cargan la ciudad **dentro** del domicilio
 * (`Av. Pueyrredón 1640, CABA`) y además llenan el campo `ciudad` con lo mismo,
 * así que concatenar a secas daba `…, CABA, CABA`. Se vio en la demo
 * desplegada, no en un test: con datos inventados las dos mitades no se pisan.
 *
 * Gemela de `direccion()` en `app/services/hoja_ruta_pdf.py`, que es la que usa
 * el PDF. Están duplicadas porque son dos lenguajes; si divergen, la pantalla y
 * el papel dirían dos cosas distintas del mismo cliente. */
export function direccion(domicilio: string | null, ciudad: string | null): string {
  if (!domicilio) return ciudad ?? ''
  if (ciudad && !domicilio.toLowerCase().includes(ciudad.trim().toLowerCase())) {
    return `${domicilio}, ${ciudad}`
  }
  return domicilio
}

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
      eventos: suyos.map((t) => ({
        clave: `${t.equipo_id}-${t.incidencia_id}`,
        desde: t.desde,
        hasta: t.hasta,
        titulo: t.titulo,
        // La columna ya dice la cuadrilla, así que el subtítulo es el cliente —
        // y la modalidad pegada, que en la vista de tarjetas era un badge y en
        // un bloque no entra como tal. **No es decorativa**: un trabajo remoto
        // ocupa la agenda pero NO es una parada, y por eso la hoja de ruta lo
        // deja afuera (`_MODALIDADES_SIN_VISITA` en `app/services/agenda.py`).
        // Sin esto, un remoto y una visita se ven idénticos en la grilla y el
        // PDF sale con una parada menos de las que se contaron en pantalla.
        subtitulo: [t.cliente_nombre, t.modalidad ? MODALIDAD_LABELS[t.modalidad] : null]
          .filter(Boolean).join(' · ') || undefined,
        // El domicilio en el bloque y no sólo en el PDF: el recorrido del día se
        // arma mirando esta pantalla, y armarlo sin ver dónde queda cada trabajo
        // es la misma carencia con otra ropa.
        detalle: direccion(t.cliente_domicilio, t.cliente_ciudad) || undefined,
        clase: claseChip(t.equipo_indice),
        to: `/incidencias/${t.incidencia_id}`,
      })),
    }
  })

  return <RejillaHoraria columnas={columnas} />
}
