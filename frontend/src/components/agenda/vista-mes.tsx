/** El mes: la grilla de semanas completas, de lunes a domingo.
 *
 *  Contesta una pregunta distinta de la semana: no *"a qué hora entra esta
 *  visita"* sino *"cómo viene cargado el mes"* — dónde están los días llenos y
 *  dónde los vacíos, para planificar.
 *
 *  **Es la única de las tres que NO usa la rejilla horaria**, igual que en
 *  Google: treinta rejillas de un día no entran en una pantalla, y el mes se
 *  mira para verlo entero. La celda es compacta y muestra hasta tres etiquetas.
 *
 *  **Arranca en el lunes anterior al día 1 y dibuja semanas completas.** Los
 *  días del mes de al lado se muestran apagados en vez de dejarse en blanco: son
 *  días reales con trabajos reales, y un lunes 31 de agosto en blanco porque
 *  septiembre empieza el martes escondería una salida de cuadrilla.
 */
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { NOMBRES_DIAS, mismoMes, sumarDias } from './fechas'
import { Chip } from './chip'
import type { TrabajoConEquipo } from './datos'

/** Cuántos trabajos entran en una celda antes del "+N más". */
const TOPE = 3

export function VistaMes({ desde, celdas, mes, porDia, hoy, hrefDia }: {
  /** El primer día de la grilla: el lunes de la semana del día 1. */
  desde: string
  /** Cuántas celdas dibuja: 28, 35 o 42. */
  celdas: number
  /** Un día cualquiera del mes que se está mirando, para apagar los de al lado. */
  mes: string
  porDia: Record<string, TrabajoConEquipo[]>
  hoy: string
  hrefDia: (dia: string) => string
}) {
  const dias = Array.from({ length: celdas }, (_, i) => sumarDias(desde, i))

  return (
    <div className="overflow-hidden rounded-md border">
      {/* Los rótulos sólo arriba de la grilla de verdad: abajo de `md` las
          celdas se apilan en una columna y una fila de siete nombres sueltos no
          encabezaría nada. */}
      <div className="hidden grid-cols-7 border-b bg-muted/30 md:grid">
        {NOMBRES_DIAS.map((d) => (
          <span key={d} className="border-l py-1 text-center text-[11px] uppercase text-muted-foreground first:border-l-0">
            {d}
          </span>
        ))}
      </div>
      <div className="grid md:grid-cols-7">
        {dias.map((dia) => {
          const trabajos = porDia[dia] ?? []
          const esHoy = dia === hoy
          const delMes = mismoMes(dia, mes)
          return (
            <div
              key={dia}
              className={cn(
                'flex min-h-24 flex-col gap-0.5 border-b border-l p-1',
                esHoy && 'bg-primary/5',
                !delMes && 'bg-muted/20 text-muted-foreground',
              )}
            >
              {/* El número arriba, y hoy en un círculo lleno — la forma de
                  Google, y la misma que el encabezado de la semana. */}
              <Link
                to={hrefDia(dia)}
                className="self-center text-xs font-medium hover:underline md:self-start"
              >
                <span className="md:hidden">{dia.slice(8, 10)}/{dia.slice(5, 7)}</span>
                <span className={cn(
                  'hidden size-5 items-center justify-center rounded-full tabular-nums md:flex',
                  esHoy && 'bg-primary text-primary-foreground',
                )}>
                  {Number(dia.slice(8, 10))}
                </span>
              </Link>
              {trabajos.slice(0, TOPE).map((t) => (
                <Chip key={`${t.equipo_id}-${t.incidencia_id}`} t={t} compacto />
              ))}
              {trabajos.length > TOPE && (
                // Linkea al día, que es donde están los que no entraron. Un
                // "+2 más" que no lleve a ningún lado esconde trabajos sin dar
                // forma de verlos.
                <Link
                  to={hrefDia(dia)}
                  className="px-1 text-xs text-muted-foreground hover:underline"
                >
                  +{trabajos.length - TOPE} más
                </Link>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
