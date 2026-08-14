/** El mes: la grilla de semanas completas, de lunes a domingo.
 *
 *  Contesta una pregunta distinta de la semana: no *"a qué hora entra esta
 *  visita"* sino *"cómo viene cargado el mes"* — dónde están los días llenos y
 *  dónde los vacíos, para planificar. Por eso la celda es compacta y muestra
 *  hasta tres trabajos: con seis renglones por celda la grilla no entra en
 *  pantalla y deja de servir para lo único que sirve, que es verla entera.
 *
 *  **Arranca en el lunes anterior al día 1 y dibuja semanas completas.** Los
 *  días del mes de al lado se muestran apagados en vez de dejarse en blanco: son
 *  días reales con trabajos reales, y un lunes 31 de agosto en blanco porque
 *  septiembre empieza el martes escondería una salida de cuadrilla.
 */
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { NOMBRES_DIAS, mismoMes, sumarDias } from './fechas'
import { Chip } from './vista-semana'
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
    <div className="grid gap-2">
      {/* Los rótulos sólo arriba de la grilla de verdad: abajo de `md` las
          celdas se apilan en una columna y una fila de siete nombres sueltos no
          encabezaría nada. */}
      <div className="hidden grid-cols-7 gap-1 md:grid">
        {NOMBRES_DIAS.map((d) => (
          <span key={d} className="text-center text-xs font-medium text-muted-foreground">
            {d}
          </span>
        ))}
      </div>
      <div className="grid gap-1 md:grid-cols-7">
        {dias.map((dia) => {
          const trabajos = porDia[dia] ?? []
          const esHoy = dia === hoy
          const delMes = mismoMes(dia, mes)
          return (
            <div
              key={dia}
              className={cn(
                'flex min-h-24 flex-col gap-0.5 rounded-md border p-1',
                esHoy && 'border-primary bg-primary/5',
                !delMes && 'opacity-50',
              )}
            >
              <Link
                to={hrefDia(dia)}
                className={cn(
                  'text-xs font-medium hover:underline',
                  esHoy ? 'text-primary' : 'text-muted-foreground',
                )}
              >
                {/* En la grilla de mes el número solo alcanza; abajo de `md`,
                    donde las celdas se apilan, haría falta el día de la semana
                    — por eso va el mes y día completos como texto secundario. */}
                <span className="md:hidden">{dia.slice(8, 10)}/{dia.slice(5, 7)}</span>
                <span className="hidden md:inline">{Number(dia.slice(8, 10))}</span>
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
