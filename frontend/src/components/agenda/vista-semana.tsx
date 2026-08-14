/** La semana: siete columnas, de lunes a domingo.
 *
 *  Es la vista que faltaba. La agenda del producto mostraba **un solo día**, así
 *  que "¿qué tiene la Cuadrilla Norte el jueves?" obligaba a mover el selector y
 *  perder de vista el resto — y "¿qué día conviene meter esta visita?" no se
 *  podía contestar sin ir día por día.
 *
 *  **Los trabajos de todas las cuadrillas van mezclados en la columna del día,
 *  en orden de hora**, con el color del equipo encima. Es la forma de un
 *  calendario, y es la que contesta la pregunta de la semana: *cuándo hay lugar*.
 *  La alternativa —un carril por cuadrilla dentro de cada día— hace explícito el
 *  quién, pero con cuatro equipos la grilla mide cuatro pantallas de alto y hay
 *  que scrollear para ver el viernes. El quién lo resuelven el color, la
 *  referencia de arriba y el filtro; y cuando de verdad importa —al despachar—
 *  se entra al día, que sí está agrupado por cuadrilla.
 */
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { claseChip } from './colores'
import { diaCorto, hora, sumarDias } from './fechas'
import type { TrabajoConEquipo } from './datos'

/** Un trabajo dentro de una celda del calendario.
 *
 *  Linkea al ticket y no al día: el chip **es** el trabajo, y quien lo aprieta
 *  quiere abrirlo. Para entrar al día está el encabezado de la columna. */
export function Chip({ t, compacto = false }: {
  t: TrabajoConEquipo
  compacto?: boolean
}) {
  return (
    <Link
      to={`/incidencias/${t.incidencia_id}`}
      title={`${hora(t.desde)}–${hora(t.hasta)} · ${t.titulo} · ${t.equipo_nombre}`}
      className={cn(
        'block rounded border px-1.5 py-1 text-xs hover:brightness-95 dark:hover:brightness-125',
        claseChip(t.equipo_indice),
      )}
    >
      <span className="flex items-baseline gap-1">
        <span className="font-mono tabular-nums opacity-80">{hora(t.desde)}</span>
        <span className="min-w-0 truncate font-medium">{t.titulo}</span>
      </span>
      {/* En el mes no entra: la celda mide cuatro renglones y el nombre de la
          cuadrilla se lo comería uno entero. Ahí lo dice el color, con la
          referencia arriba de la grilla. */}
      {!compacto && (
        <span className="block truncate opacity-80">
          {t.equipo_nombre}
          {t.cliente_nombre && ` · ${t.cliente_nombre}`}
        </span>
      )}
    </Link>
  )
}

export function VistaSemana({ desde, porDia, hoy, hrefDia, cargando }: {
  /** El lunes de la semana que se muestra. */
  desde: string
  porDia: Record<string, TrabajoConEquipo[]>
  hoy: string
  hrefDia: (dia: string) => string
  cargando: boolean
}) {
  const dias = Array.from({ length: 7 }, (_, i) => sumarDias(desde, i))

  return (
    // `md:grid-cols-7` y no siempre siete: en un teléfono, siete columnas de
    // 50 px no muestran ni la hora. Abajo de `md` la semana se apila y queda
    // una lista de días, que es lo que entra.
    <div className="grid gap-2 md:grid-cols-7">
      {dias.map((dia) => {
        const trabajos = porDia[dia] ?? []
        const esHoy = dia === hoy
        return (
          <div
            key={dia}
            className={cn(
              'flex min-h-32 flex-col gap-1 rounded-md border p-2',
              esHoy && 'border-primary bg-primary/5',
            )}
          >
            {/* El encabezado es el link que entra al día: es el camino a la
                vista de despacho, con sus cuadrillas y su hoja de ruta. */}
            <Link
              to={hrefDia(dia)}
              className={cn(
                'text-sm font-medium hover:underline',
                esHoy ? 'text-primary' : 'text-muted-foreground',
              )}
            >
              {diaCorto(dia)}
              {esHoy && <span className="ml-1 text-xs font-normal">· hoy</span>}
            </Link>
            {trabajos.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                {cargando ? 'Cargando…' : 'Sin trabajos.'}
              </p>
            ) : (
              trabajos.map((t) => <Chip key={`${t.equipo_id}-${t.incidencia_id}`} t={t} />)
            )}
          </div>
        )
      })}
    </div>
  )
}
