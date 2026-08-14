/** La carga de la agenda, una sola vez para las tres vistas.
 *
 *  **Una llamada por equipo, en paralelo, con el rango entero.** El endpoint es
 *  por equipo porque la validación de choques también lo es (el recurso es el
 *  equipo, ver `app/services/agenda.py`), pero acepta `dias` desde el día uno:
 *  la semana es **una** llamada por cuadrilla con `dias=7`, no siete de un día.
 *  Con la cantidad de cuadrillas que tiene una empresa de esto —unas pocas— el
 *  fan-out por equipo es más barato que sostener un segundo endpoint agregador
 *  que diga lo mismo; el fan-out por *día*, en cambio, multiplicaría por siete
 *  o por cuarenta y dos, y ése sí no se sostiene.
 *
 *  **El filtro de cuadrilla no toca esto.** Se filtra al dibujar, no al pedir:
 *  si el fetch se recortara, el "+3 más" de la celda del mes y la cuenta del día
 *  pasarían a mentir en cuanto alguien elige una cuadrilla.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, type EquipoTrabajo, type TrabajoAgendado } from '../../api'

/** Un trabajo con el equipo que lo hace pegado encima.
 *
 *  El endpoint es por equipo, así que la respuesta no lo repite adentro de cada
 *  fila — pero en cuanto los trabajos de todas las cuadrillas se mezclan en la
 *  celda de un día, saber de quién es cada uno deja de ser derivable. */
export type TrabajoConEquipo = TrabajoAgendado & {
  equipo_id: number
  equipo_nombre: string
  /** Posición del equipo en la lista de activos: de acá sale su color. */
  equipo_indice: number
}

export type AgendaRango = {
  /** Los trabajos de cada día, `YYYY-MM-DD` → lista ordenada por hora. */
  porDia: Record<string, TrabajoConEquipo[]>
  /** Las cuadrillas activas, en el orden que fija los colores. */
  activos: EquipoTrabajo[]
  cargando: boolean
  error: string | null
  recargar: () => void
}

/** El día al que pertenece un trabajo.
 *
 *  Se corta el string en vez de construir un `Date`: el backend manda la fecha
 *  **sin huso** (`2026-08-14T09:00:00`, un `isoformat()` de un datetime naive),
 *  así que `new Date(...)` la interpreta como local, y cualquier reformateo
 *  posterior puede devolver el día de al lado. El primer tramo del string ya es
 *  el día en el que el backend lo guardó, que es el único que importa. */
function diaDe(t: TrabajoAgendado): string {
  return t.desde.slice(0, 10)
}

export function useAgendaRango(
  equipos: EquipoTrabajo[], desde: string, dias: number,
): AgendaRango {
  const [porDia, setPorDia] = useState<Record<string, TrabajoConEquipo[]>>({})
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Sólo los activos: un equipo dado de baja no se despacha, y sus trabajos
  // viejos en la grilla serían ruido permanente.
  const activos = equipos.filter((e) => e.activo)
  // La clave del efecto es esta cadena y no el array: `equipos` es un objeto
  // nuevo en cada render del padre, y usarlo como dependencia dispararía el
  // fan-out entero en cada tecla que se toque en la pantalla. Se serializa con
  // JSON y no con un `join` de separadores: una cuadrilla que se llame
  // "Norte | Sur" partiría la cadena y el fan-out pediría un equipo inventado.
  const clave = JSON.stringify(activos.map((e) => ({ id: e.id, nombre: e.nombre })))

  // Marca de la carga en curso. Cambiar de semana mientras la anterior está en
  // vuelo deja dos respuestas compitiendo, y la vieja puede llegar última: sin
  // esto, la grilla termina mostrando el rango que el usuario ya dejó atrás.
  const enVuelo = useRef(0)

  const cargar = useCallback(async () => {
    const mio = ++enVuelo.current
    const lista: { id: number; nombre: string }[] = JSON.parse(clave)

    if (lista.length === 0) {
      setPorDia({})
      return
    }
    setCargando(true)
    setError(null)
    try {
      const respuestas = await Promise.all(lista.map((e) => api.get<TrabajoAgendado[]>(
        `/api/agenda/equipo/${e.id}?desde=${desde}&dias=${dias}`,
      )))
      if (mio !== enVuelo.current) return

      const agrupado: Record<string, TrabajoConEquipo[]> = {}
      respuestas.forEach((trabajos, i) => {
        const e = lista[i]
        for (const t of trabajos) {
          const dia = diaDe(t)
          ;(agrupado[dia] ??= []).push({
            ...t, equipo_id: e.id, equipo_nombre: e.nombre, equipo_indice: i,
          })
        }
      })
      // Cada respuesta viene ordenada, pero la mezcla de varias cuadrillas no:
      // sin este sort, la columna del día lista la agenda entera de la Norte y
      // recién después la de la Sur, que no es un día.
      for (const dia of Object.keys(agrupado)) {
        agrupado[dia].sort((a, b) => a.desde.localeCompare(b.desde))
      }
      setPorDia(agrupado)
    } catch (err) {
      if (mio !== enVuelo.current) return
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    } finally {
      if (mio === enVuelo.current) setCargando(false)
    }
  }, [clave, desde, dias])

  useEffect(() => { void cargar() }, [cargar])

  return { porDia, activos, cargando, error, recargar: cargar }
}
