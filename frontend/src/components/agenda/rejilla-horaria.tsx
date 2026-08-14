/** La rejilla horaria: las horas bajan por la izquierda y cada trabajo se
 *  posiciona y se estira según su horario. Es la forma de Google Calendar, y la
 *  pidió el humano el 2026-08-14 mostrando una captura.
 *
 *  **Es lo que la lista de chips no podía decir.** Una columna con
 *  `09:00 Cambio de switch` / `14:30 Revisión de cableado` dice *qué* hay ese
 *  día, pero no **cuánto ocupa** ni **dónde está el hueco**, que es la pregunta
 *  de quien despacha. Acá un trabajo de 3 horas mide el triple que uno de una, y
 *  el espacio en blanco entre las 11:00 y las 14:30 se ve como lo que es.
 *
 *  La usan las tres vistas con columnas distintas: la **semana** pone una
 *  columna por día, el **día** una por cuadrilla (el patrón de Google cuando
 *  mirás varios calendarios a la vez). El mes no la usa — un mes con rejilla
 *  horaria son 30 rejillas y no entra en ninguna pantalla.
 *
 *  ⚠️ **El solapamiento es la razón por la que este archivo no es tres divs.**
 *  Dos cuadrillas a las 09:00 del mismo día —que es exactamente lo que tienen
 *  los datos de ejemplo— se dibujarían una encima de la otra, y la de abajo
 *  desaparecería sin que nada avise. `colocar()` reparte el ancho.
 */
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { colocar, minutos, ventanaHoraria } from './colocacion'

/** Alto de una hora, en píxeles. 56 px es lo que hace que un trabajo de media
 *  hora (28 px) todavía muestre su título en una línea. */
const ALTO_HORA = 56

/** Alto mínimo de un bloque. Un trabajo de 15 minutos son 14 px y no se puede
 *  leer; se dibuja más alto de lo que dura. Es lo mismo que hace Google, y es
 *  preferible a un bloque exacto e ilegible — el horario exacto está en el
 *  texto y en el `title`. */
const ALTO_MINIMO = 22

export type EventoRejilla = {
  clave: string
  /** ISO local sin huso, tal como lo manda el backend. */
  desde: string
  hasta: string
  titulo: string
  subtitulo?: string
  /** Tercera línea, para lo que sólo entra en bloques anchos: en la vista de
   *  día lleva el **domicilio**, que es lo que se lee para ordenar el recorrido.
   *  Si el bloque es corto queda recortado por el `overflow-hidden`, que es el
   *  comportamiento buscado: se prioriza el título y la hora. */
  detalle?: string
  /** Las clases de color de la cuadrilla (ver `colores.ts`). */
  clase: string
  /** A dónde lleva el bloque. */
  to: string
}

export type ColumnaRejilla = {
  clave: string
  encabezado: ReactNode
  eventos: EventoRejilla[]
  /** Marca la columna de hoy: fondo tenue y línea de la hora actual. */
  esHoy?: boolean
}

function dosDigitos(n: number): string {
  return String(n).padStart(2, '0')
}

/** Los minutos desde la medianoche **local**, ahora. */
function minutosDeAhora(): number {
  const d = new Date()
  return d.getHours() * 60 + d.getMinutes()
}

export function RejillaHoraria({ columnas }: { columnas: ColumnaRejilla[] }) {
  // La línea de "ahora" la calcula la rejilla y se actualiza sola. Pasarla por
  // props desde la pantalla la dejaba congelada en el minuto en que se cargó:
  // en una agenda que se deja abierta toda la mañana, una línea roja quieta
  // miente más que no tenerla. Sólo se dibuja en las columnas marcadas `esHoy`,
  // así que mirando otra semana no aparece.
  const [minutosAhora, setMinutosAhora] = useState(minutosDeAhora)
  useEffect(() => {
    const id = setInterval(() => setMinutosAhora(minutosDeAhora()), 60_000)
    return () => clearInterval(id)
  }, [])

  const [horaDesde, horaHasta] = ventanaHoraria(columnas)
  const horas = Array.from({ length: horaHasta - horaDesde }, (_, i) => horaDesde + i)
  const alto = horas.length * ALTO_HORA
  const cuerpo = useRef<HTMLDivElement>(null)

  // Arranca mostrando la franja con trabajo, no el tope de la ventana. Con la
  // ventana estirada por un trabajo de madrugada, abrir arriba de todo dejaría
  // la jornada normal fuera de cuadro.
  const primerEvento = Math.min(
    ...columnas.flatMap((c) => c.eventos.map((e) => minutos(e.desde))),
    horaDesde * 60,
  )
  useEffect(() => {
    if (cuerpo.current) {
      cuerpo.current.scrollTop = Math.max(
        0, ((primerEvento - horaDesde * 60) / 60) * ALTO_HORA - ALTO_HORA / 2,
      )
    }
  }, [primerEvento, horaDesde])

  const anchoColumnas = { gridTemplateColumns: `repeat(${columnas.length}, minmax(0, 1fr))` }

  return (
    <div className="overflow-hidden rounded-md border">
      {/* 🔴 Encabezado y cuerpo van DENTRO del mismo contenedor que scrollea, y
          el encabezado se queda pegado arriba con `sticky`.
          Hasta el 2026-08-14 el encabezado estaba **afuera**: como sólo el
          cuerpo scrollea, la barra de scroll le comía ~15 px de ancho al cuerpo
          y no al encabezado, así que las columnas se iban desfasando y el
          desfase se acumulaba hacia la derecha —LUN casi alineado, DOM corrido
          un dedo—. Lo reportó el humano con una captura.
          Adentro del mismo caja no hay aritmética que hacer: los dos anchos
          disponibles son el mismo por construcción. */}
      <div ref={cuerpo} data-rejilla-scroll className="max-h-[60vh] overflow-y-auto">
        <div className="sticky top-0 z-30 flex border-b bg-muted/95 backdrop-blur">
          <div className="w-14 shrink-0" />
          <div className="grid flex-1" style={anchoColumnas}>
            {columnas.map((c) => (
              <div
                key={c.clave}
                data-columna-encabezado={c.clave}
                className={cn('min-w-0 border-l px-2 py-1.5 text-center', c.esHoy && 'bg-primary/5')}
              >
                {c.encabezado}
              </div>
            ))}
          </div>
        </div>

        {/* `pt-2` para que la etiqueta de la primera hora, que va subida media
            línea, no quede cortada contra el encabezado. */}
        <div className="flex pt-2">
          {/* Canaleta de horas. La etiqueta va **subida media línea** para que
              quede a caballo de su raya, como en un calendario de papel. */}
          <div className="w-14 shrink-0" style={{ height: alto }}>
            {horas.map((h) => (
              <div key={h} className="relative" style={{ height: ALTO_HORA }}>
                <span className="absolute -top-2 right-2 text-[11px] tabular-nums text-muted-foreground">
                  {dosDigitos(h)}:00
                </span>
              </div>
            ))}
          </div>

          <div className="relative flex-1" style={{ height: alto }}>
            {/* Las rayas de las horas, corridas por debajo de todo. */}
            <div className="pointer-events-none absolute inset-0">
              {horas.map((h) => (
                <div key={h} className="border-t border-border/60" style={{ height: ALTO_HORA }} />
              ))}
            </div>

            <div className="grid h-full" style={anchoColumnas}>
              {columnas.map((c) => (
                <div
                  key={c.clave}
                  // Anclaje estable de la columna: en una rejilla, "este trabajo
                  // cae en el jueves" es una afirmación **posicional**, y los
                  // bloques ya no cuelgan del encabezado sino de este cuerpo. Sin
                  // el atributo, la única forma de verificarlo sería por clases
                  // de Tailwind o por índice de hermano.
                  data-columna={c.clave}
                  className={cn('relative min-w-0 border-l', c.esHoy && 'bg-primary/5')}
                >
                  {colocar(c.eventos).map((e) => {
                    const top = ((e.inicioMin - horaDesde * 60) / 60) * ALTO_HORA
                    const altoBloque = Math.max(
                      ALTO_MINIMO, ((e.finMin - e.inicioMin) / 60) * ALTO_HORA,
                    )
                    return (
                      <Link
                        key={e.clave}
                        to={e.to}
                        title={`${e.desde.slice(11, 16)}–${e.hasta.slice(11, 16)} · ${e.titulo}${e.subtitulo ? ` · ${e.subtitulo}` : ''}`}
                        className={cn(
                          'absolute overflow-hidden rounded border px-1 py-0.5 text-[11px] leading-tight',
                          'hover:z-10 hover:brightness-95 dark:hover:brightness-125',
                          e.clase,
                        )}
                        style={{
                          top,
                          height: altoBloque,
                          // 1 % de aire a la derecha para que dos bloques
                          // pegados no parezcan uno solo partido.
                          left: `${(e.col / e.total) * 100}%`,
                          width: `${(1 / e.total) * 100 - 1}%`,
                        }}
                      >
                        <span className="block truncate font-medium">{e.titulo}</span>
                        <span className="block truncate opacity-80">
                          {e.desde.slice(11, 16)}
                          {e.subtitulo && ` · ${e.subtitulo}`}
                        </span>
                        {e.detalle && (
                          <span className="block truncate opacity-70">{e.detalle}</span>
                        )}
                      </Link>
                    )
                  })}

                  {c.esHoy
                    && minutosAhora >= horaDesde * 60 && minutosAhora <= horaHasta * 60 && (
                    <div
                      className="pointer-events-none absolute left-0 right-0 z-20 border-t-2 border-red-500"
                      style={{ top: ((minutosAhora - horaDesde * 60) / 60) * ALTO_HORA }}
                      aria-hidden
                    >
                      <span className="absolute -left-1 -top-1 block size-2 rounded-full bg-red-500" />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
