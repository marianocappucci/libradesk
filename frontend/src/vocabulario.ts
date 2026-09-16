/** Cómo llama esta instancia a las cosas.
 *
 *  Salió del pedido del humano del 2026-09-09: *"quiero que también pueda
 *  parametrizar el nombre incidencias, que en la instancia de Lagrace sea
 *  tratado como reclamos"*. Se armó con dos vocabularios (`VOCABULARIO_COMPLETO`
 *  / `VOCABULARIO_SIMPLE`) elegidos por el add-on `modo_simple`.
 *
 *  🔴 **Decisión del humano, 2026-09-13: LibraDesk pasa a decir «Reclamo» en
 *  TODAS las instancias.** Lagrace —la única razón de que existiera un segundo
 *  vocabulario— ya no va. No queda ninguna instancia que hable de
 *  "Incidencias", así que los dos juegos de palabras colapsan en uno solo.
 *
 *  **Por qué queda una constante y no se borra el archivo.** El add-on
 *  `modo_simple` sigue vivo — sigue reduciendo la ficha y ocultando Agenda
 *  (ver `components/Layout.tsx` y `pages/Incidencias.tsx`) — sólo el
 *  VOCABULARIO dejó de depender de él. El Dashboard, que hasta el 2026-09-16
 *  también escondía, se sacó del producto entero. Y
 *  `vocabularioDe(user)` se mantiene con la misma firma —recibe el usuario y no
 *  lo consulta por su cuenta— por si algún otro punto del código (o un test)
 *  todavía la llama: hoy devuelve siempre el mismo valor, pero ningún llamador
 *  tiene que cambiar para enterarse.
 */

/** El juego de palabras del producto. */
export type Vocabulario = {
  /** "Reclamo". Para títulos de ficha y mensajes en singular. */
  singular: string
  /** "Reclamos". Para el menú y los títulos de listado. */
  plural: string
  /** "Nuevo reclamo". Frase entera y no compuesta: si algún día vuelve a
   *  hacer falta un vocabulario cuyo género cambie el artículo, esta forma ya
   *  lo soporta sin tocar a quien la consume. */
  nuevo: string
}

export const VOCABULARIO: Vocabulario = {
  singular: 'Reclamo',
  plural: 'Reclamos',
  nuevo: 'Nuevo reclamo',
}

/** El vocabulario de esta instancia.
 *
 *  Ya no depende del usuario —todas las instancias hablan de "Reclamos"— pero
 *  conserva la firma `(user: unknown) => Vocabulario` para no obligar a
 *  reescribir a quien todavía la llama así.
 */
export function vocabularioDe(_user: unknown): Vocabulario {
  return VOCABULARIO
}
