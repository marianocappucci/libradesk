/** La semana: siete columnas de lunes a domingo, sobre la rejilla horaria.
 *
 *  Es la vista que faltaba. La agenda del producto mostraba **un solo día**, así
 *  que "¿qué tiene la Cuadrilla Norte el jueves?" obligaba a mover el selector y
 *  perder de vista el resto — y "¿qué día conviene meter esta visita?" no se
 *  podía contestar sin ir día por día.
 *
 *  **Pasó de lista de chips a rejilla horaria el 2026-08-14**, a pedido del
 *  humano y con una captura de Google Calendar como referencia. Lo que gana no
 *  es estética: la lista decía *qué* hay ese día, la rejilla dice **cuánto ocupa
 *  y dónde está el hueco**, que es la pregunta de quien despacha. El encabezado
 *  de cada día sigue siendo el link que entra al detalle.
 *
 *  **Los trabajos de todas las cuadrillas van juntos en la columna del día**,
 *  con el color del equipo encima. La alternativa —un carril por cuadrilla
 *  dentro de cada día— hace explícito el quién, pero con cuatro equipos la
 *  grilla mide cuatro pantallas de alto. El quién lo resuelven el color, la
 *  referencia y el filtro; y al entrar al día, cada cuadrilla tiene su columna.
 */
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { claseChip } from './colores'
import { NOMBRES_DIAS, sumarDias } from './fechas'
import { RejillaHoraria, type ColumnaRejilla } from './rejilla-horaria'
import type { TrabajoConEquipo } from './datos'

/** Un trabajo a bloque de la rejilla. Sin exportar: la vista de día arma las
 *  suyas aparte porque lleva otros campos —el domicilio en la tercera línea, y
 *  el cliente donde acá va la cuadrilla—. Compartirlas pediría un objeto de
 *  opciones más largo que las dos versiones juntas. */
function aEvento(t: TrabajoConEquipo, conEquipo: boolean) {
  return {
    clave: `${t.equipo_id}-${t.incidencia_id}`,
    desde: t.desde,
    hasta: t.hasta,
    titulo: t.titulo,
    // En la semana el subtítulo dice la cuadrilla —es lo que el color insinúa y
    // conviene poder leer—; en el día la columna ya es la cuadrilla, así que
    // ahí va el cliente, que es el dato que falta.
    subtitulo: conEquipo ? t.equipo_nombre : (t.cliente_nombre ?? undefined),
    clase: claseChip(t.equipo_indice),
    to: `/incidencias/${t.incidencia_id}`,
  }
}

/** El encabezado de un día, con la forma de Google: el día de la semana chico
 *  arriba y el número grande abajo, y hoy con el número en un círculo lleno. */
function EncabezadoDia({ dia, esHoy, href }: {
  dia: string
  esHoy: boolean
  href: string
}) {
  const dow = (new Date(`${dia}T12:00:00Z`).getUTCDay() + 6) % 7
  return (
    <Link to={href} className="block hover:underline">
      <span className={cn(
        'block text-[11px] uppercase',
        esHoy ? 'text-primary' : 'text-muted-foreground',
      )}>
        {NOMBRES_DIAS[dow]}
      </span>
      <span className={cn(
        'mx-auto mt-0.5 flex size-7 items-center justify-center rounded-full text-sm font-medium tabular-nums',
        esHoy && 'bg-primary text-primary-foreground',
      )}>
        {Number(dia.slice(8, 10))}
      </span>
    </Link>
  )
}

export function VistaSemana({ desde, porDia, hoy, hrefDia }: {
  /** El lunes de la semana que se muestra. */
  desde: string
  porDia: Record<string, TrabajoConEquipo[]>
  hoy: string
  hrefDia: (dia: string) => string
}) {
  const columnas: ColumnaRejilla[] = Array.from({ length: 7 }, (_, i) => {
    const dia = sumarDias(desde, i)
    return {
      clave: dia,
      esHoy: dia === hoy,
      encabezado: (
        <EncabezadoDia dia={dia} esHoy={dia === hoy} href={hrefDia(dia)} />
      ),
      eventos: (porDia[dia] ?? []).map((t) => aEvento(t, true)),
    }
  })

  return <RejillaHoraria columnas={columnas} />
}
