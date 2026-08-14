/** La vista de un día: una tarjeta por cuadrilla, con lo que tiene y en qué sale.
 *
 *  **Es la pantalla de despacho de la mañana**, y la que contesta entero el
 *  pedido 42: *"cuando un equipo tiene asignado un trabajo ya sabe en qué
 *  vehículo sale de acuerdo a la disponibilidad"*. Viene de
 *  `components/agenda-equipos.tsx`, donde era la agenda entera; desde que la
 *  agenda es un calendario (2026-08-14) es **una de sus tres vistas**, y la que
 *  se abre al entrar a un día desde la semana o el mes.
 *
 *  Por eso sigue siendo por cuadrilla y no por hora: la semana y el mes ya
 *  contestan "cuándo", y lo que falta al entrar a un día es "quién sale, con
 *  quién, en qué, y a qué direcciones". Agrupado por hora, armar el recorrido de
 *  la Cuadrilla Norte obligaría a pescar sus paradas entre las de las demás.
 *
 *  Al mudarse perdió dos cosas: su propio selector de fecha (ahora el día lo
 *  manda la pantalla, y vive en la URL) y su fetch (ahora es `useAgendaRango`,
 *  compartido con las otras dos vistas).
 */
import { Link } from 'react-router-dom'
import { ESTADO_LABELS, MODALIDAD_LABELS, type EquipoTrabajo } from '../../api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Car, Printer } from '@/components/iconos-accion'
import { hora } from './fechas'
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

export function VistaDia({ dia, equipos, trabajos, cargando }: {
  dia: string
  equipos: EquipoTrabajo[]
  trabajos: TrabajoConEquipo[]
  cargando: boolean
}) {
  if (equipos.length === 0) {
    return (
      <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
        No hay equipos activos para agendar.
      </CardContent></Card>
    )
  }

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {equipos.map((e) => {
        const suyos = trabajos.filter((t) => t.equipo_id === e.id)
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
                {/* El día del botón es el que se está mirando, no "hoy": la hoja
                    se imprime la noche anterior tanto como a la mañana, y una
                    que dijera otra fecha que la grilla de al lado es peor que no
                    tenerla. */}
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
              {cargando && suyos.length === 0 ? (
                <p className="text-sm text-muted-foreground">Cargando…</p>
              ) : suyos.length === 0 ? (
                <p className="text-sm text-muted-foreground">Sin trabajos ese día.</p>
              ) : (
                suyos.map((t) => (
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
                    {/* En renglón propio y no como una etiqueta más: es lo que
                        se lee para ordenar el recorrido, y apretado entre los
                        badges se pierde. No se muestra nada si el cliente no
                        tiene domicilio cargado — un "—" acá sería una fila de
                        ruido en cada trabajo remoto. */}
                    {t.cliente_domicilio && (
                      <span className="text-xs text-muted-foreground">
                        {direccion(t.cliente_domicilio, t.cliente_ciudad)}
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
  )
}
