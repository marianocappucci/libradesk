/** Dónde va cada bloque en la rejilla horaria. Aritmética pura, sin DOM.
 *
 *  En archivo aparte de `rejilla-horaria.tsx` por dos motivos que apuntan al
 *  mismo lado: se puede probar sin montar nada, y exportar funciones desde un
 *  archivo que también exporta componentes rompe el fast-refresh de React.
 *
 *  **Es donde vive el defecto que peor se ve.** Un bloque tapando a otro no deja
 *  ningún rastro en pantalla: los dos textos siguen en el DOM, el `getByText`
 *  los encuentra a los dos, y el trabajo de abajo simplemente no existe para
 *  quien mira. Por eso el reparto de ancho se prueba midiendo `left` y `width`,
 *  no leyendo texto.
 */
import type { EventoRejilla } from './rejilla-horaria'

/** Los minutos desde la medianoche de un ISO local.
 *
 *  Se leen del **string**, no de un `Date`. El backend manda la fecha sin huso
 *  (`2026-08-14T09:00:00`), así que `new Date(...)` la interpreta como local y
 *  cualquier reformateo puede correrla; acá lo único que hace falta es la
 *  posición vertical. */
export function minutos(iso: string): number {
  return Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16))
}

export type Colocado = EventoRejilla & {
  col: number
  total: number
  inicioMin: number
  finMin: number
}

/** Reparte el ancho entre los trabajos que se pisan.
 *
 *  Agrupa en **racimos** de eventos encadenados por solapamiento y, dentro de
 *  cada racimo, le da a cada uno la primera columna que quedó libre. Un racimo
 *  de dos ocupa media columna cada uno; uno de tres, un tercio. Es el criterio
 *  de Google: el ancho lo fija el racimo, no el día entero, así que un choque a
 *  las 9 de la mañana no adelgaza el trabajo de la tarde.
 */
export function colocar(eventos: EventoRejilla[]): Colocado[] {
  const items = eventos
    .map((e) => ({
      ...e,
      inicioMin: minutos(e.desde),
      // Un evento que termina antes de empezar (dato roto) no puede volverse un
      // alto negativo: se lo trata como instantáneo.
      finMin: Math.max(minutos(e.hasta), minutos(e.desde)),
    }))
    .sort((a, b) => a.inicioMin - b.inicioMin || b.finMin - a.finMin)

  const salida: Colocado[] = []
  let racimo: typeof items = []
  let finRacimo = -1

  const cerrar = () => {
    // `libres[c]` es el minuto en que se desocupa la columna `c`.
    const libres: number[] = []
    const asignados = racimo.map((it) => {
      // `fin <= it.inicioMin`: uno que empieza justo cuando el otro termina
      // **reusa su columna** en vez de abrir una nueva. Los datos de ejemplo
      // tienen ese caso a propósito (uno termina 11:00 y el siguiente empieza
      // 11:00), y a media columna cada uno la agenda diría que la cuadrilla
      // está doblemente ocupada cuando no lo está.
      //
      // ⚠️ Redundante a propósito con el `>=` del racimo, abajo: **cualquiera de
      // los dos alcanza**. Se verificó rompiendo cada uno por separado y los 24
      // tests siguen verdes; hace falta romper los dos a la vez para que el test
      // se ponga rojo. No es un test flojo — es que el caso está doblemente
      // cubierto —, pero conviene saberlo antes de "simplificar" uno de los dos
      // creyendo que el otro no hace nada.
      let col = libres.findIndex((fin) => fin <= it.inicioMin)
      if (col === -1) {
        col = libres.length
        libres.push(0)
      }
      libres[col] = it.finMin
      return { ...it, col }
    })
    for (const a of asignados) salida.push({ ...a, total: libres.length })
    racimo = []
    finRacimo = -1
  }

  for (const it of items) {
    // `>=` cierra el racimo también cuando uno arranca justo al terminar el
    // anterior — la otra mitad de la defensa redundante que explica `cerrar()`.
    // Además acota el tamaño del racimo, que es lo que hace que un choque a las
    // 9 de la mañana no adelgace el trabajo de la tarde.
    if (racimo.length > 0 && it.inicioMin >= finRacimo) cerrar()
    racimo.push(it)
    finRacimo = Math.max(finRacimo, it.finMin)
  }
  if (racimo.length > 0) cerrar()
  return salida
}

/** La ventana de horas que se dibuja: de 07:00 a 20:00, estirada para que entre
 *  todo lo que haya afuera.
 *
 *  Google dibuja las 24 y scrollea. Acá la jornada de una cuadrilla entra en el
 *  horario laboral, y 24 horas dejarían dos tercios de la pantalla en blanco
 *  para mostrar lo mismo. Pero la ventana **se estira, nunca recorta**: un
 *  trabajo a las 05:00 baja el piso a las 5. Si recortara, el trabajo
 *  desaparecería de la grilla sin que nada lo dijera, que es la peor forma de
 *  fallar de un calendario. */
export function ventanaHoraria(
  columnas: { eventos: EventoRejilla[] }[],
): [number, number] {
  let desde = 7
  let hasta = 20
  for (const c of columnas) {
    for (const e of c.eventos) {
      desde = Math.min(desde, Math.floor(minutos(e.desde) / 60))
      hasta = Math.max(hasta, Math.ceil(minutos(e.hasta) / 60))
    }
  }
  return [Math.max(0, desde), Math.min(24, Math.max(hasta, desde + 1))]
}
