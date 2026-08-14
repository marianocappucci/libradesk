/** El trabajo como etiqueta compacta, para donde no hay rejilla horaria.
 *
 *  Lo usan la vista de **mes** —30 rejillas horarias no entran en una pantalla,
 *  así que ahí el día es una celda con hasta tres etiquetas— y la franja del
 *  **dashboard**. La semana y el día usan bloques posicionados por horario
 *  (`rejilla-horaria.tsx`), que es otra cosa.
 *
 *  Vivía adentro de `vista-semana.tsx` hasta el 2026-08-14, cuando esa vista
 *  pasó a rejilla y se quedó sin chips. Archivo propio y no dentro del mes:
 *  el dashboard también lo importa, y colgarlo de una vista lo ataba a ella.
 */
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { claseChip } from './colores'
import { hora } from './fechas'
import type { TrabajoConEquipo } from './datos'

/** Linkea al ticket y no al día: el chip **es** el trabajo, y quien lo aprieta
 *  quiere abrirlo. Para entrar al día está el número de la celda. */
export function Chip({ t, compacto = false }: {
  t: TrabajoConEquipo
  compacto?: boolean
}) {
  return (
    <Link
      to={`/incidencias/${t.incidencia_id}`}
      title={`${hora(t.desde)}–${hora(t.hasta)} · ${t.titulo} · ${t.equipo_nombre}`}
      className={cn(
        'block rounded border px-1.5 py-0.5 text-xs hover:brightness-95 dark:hover:brightness-125',
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
