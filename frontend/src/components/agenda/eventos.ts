/** Un trabajo agendado, dicho en el idioma del calendario compartido.
 *
 *  El calendario (`libra-ui/agenda`) sabe dibujar `EventoRejilla`: algo que
 *  empieza, termina, tiene título, color y un lugar a donde ir. Lo que **es**
 *  ese algo lo pone cada producto; acá es un trabajo de una cuadrilla.
 *
 *  Son tres formas y no una porque el mismo trabajo dice cosas distintas según
 *  dónde se lo mire, y el espacio disponible también es distinto:
 *
 *  - En la **semana** las cuadrillas están mezcladas en la columna del día, así
 *    que el subtítulo dice de quién es — el color lo insinúa y conviene poder
 *    leerlo.
 *  - En el **día** la columna ya *es* la cuadrilla, así que ese renglón se
 *    libera para el cliente, y sobra lugar para una tercera línea con el
 *    domicilio.
 *  - En el **chip** (la celda del mes y la franja del dashboard) entra un
 *    renglón y medio, así que va lo mínimo para reconocerlo.
 */
import { claseChip, type EventoRejilla } from 'libra-ui/agenda'
import { MODALIDAD_LABELS } from '../../api'
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

function base(t: TrabajoConEquipo): EventoRejilla {
  return {
    clave: `${t.equipo_id}-${t.incidencia_id}`,
    desde: t.desde,
    hasta: t.hasta,
    titulo: t.titulo,
    clase: claseChip(t.equipo_indice),
    to: `/incidencias/${t.incidencia_id}`,
  }
}

/** Para la semana: el subtítulo dice la cuadrilla. */
export function eventoDeSemana(t: TrabajoConEquipo): EventoRejilla {
  return { ...base(t), subtitulo: t.equipo_nombre }
}

/** Para el día: el subtítulo dice el cliente y la modalidad, y la tercera
 *  línea el domicilio.
 *
 *  La modalidad **no es decorativa**: un trabajo remoto ocupa la agenda pero NO
 *  es una parada, y por eso la hoja de ruta lo deja afuera
 *  (`_MODALIDADES_SIN_VISITA` en `app/services/agenda.py`). Sin esto, un remoto
 *  y una visita se ven idénticos en la grilla y el PDF sale con una parada
 *  menos de las que se contaron en pantalla.
 *
 *  Y el domicilio en el bloque y no sólo en el PDF: el recorrido del día se
 *  arma mirando esta pantalla, y armarlo sin ver dónde queda cada trabajo es la
 *  misma carencia con otra ropa.
 */
export function eventoDeDia(t: TrabajoConEquipo): EventoRejilla {
  return {
    ...base(t),
    subtitulo: [t.cliente_nombre, t.modalidad ? MODALIDAD_LABELS[t.modalidad] : null]
      .filter(Boolean).join(' · ') || undefined,
    detalle: direccion(t.cliente_domicilio, t.cliente_ciudad) || undefined,
  }
}

/** Para el chip del mes y la franja del dashboard: cuadrilla y cliente. */
export function eventoDeChip(t: TrabajoConEquipo): EventoRejilla {
  return {
    ...base(t),
    subtitulo: [t.equipo_nombre, t.cliente_nombre].filter(Boolean).join(' · ') || undefined,
  }
}

/** Los eventos de cada día, con la forma que pide la vista de semana o de mes. */
export function porDiaComoEventos(
  porDia: Record<string, TrabajoConEquipo[]>,
  como: (t: TrabajoConEquipo) => EventoRejilla,
): Record<string, EventoRejilla[]> {
  return Object.fromEntries(
    Object.entries(porDia).map(([dia, trabajos]) => [dia, trabajos.map(como)]),
  )
}
