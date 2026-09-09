/** Cómo llama esta instancia a las cosas.
 *
 *  Sale del pedido del humano del 2026-09-09: *"quiero que también pueda
 *  parametrizar el nombre incidencias, que en la instancia de Lagrace sea
 *  tratado como reclamos"*.
 *
 *  🔑 **El vocabulario viaja con el modo, no como texto libre.** Un campo de
 *  configuración por instancia obligaría a tipear el singular y el plural bien
 *  en cada alta, admitiría quedar vacío, y en la práctica nadie pondría otra
 *  cosa que "Reclamos". Acá son dos juegos cerrados y agregar un tercero
 *  —"Tickets", si aparece— es una entrada más en este archivo.
 *
 *  Si algún día hace falta de verdad que cada instancia escriba el suyo, esto
 *  es el único lugar que cambia: todas las pantallas ya preguntan acá.
 */

/** El juego de palabras de una instancia. */
export type Vocabulario = {
  /** "Incidencia" / "Reclamo". Para títulos de ficha y mensajes en singular. */
  singular: string
  /** "Incidencias" / "Reclamos". Para el menú y los títulos de listado. */
  plural: string
  /** "Nueva incidencia" / "Nuevo reclamo". El género cambia el artículo, así
   *  que la frase entera se guarda armada en vez de componerla. */
  nuevo: string
}

export const VOCABULARIO_COMPLETO: Vocabulario = {
  singular: 'Incidencia',
  plural: 'Incidencias',
  nuevo: 'Nueva incidencia',
}

export const VOCABULARIO_SIMPLE: Vocabulario = {
  singular: 'Reclamo',
  plural: 'Reclamos',
  nuevo: 'Nuevo reclamo',
}

/** El vocabulario de esta instancia, según corra o no el add-on `modo_simple`.
 *
 *  Recibe el usuario de la sesión —donde viajan los módulos— y no lo consulta
 *  por su cuenta: así la misma función sirve en un componente, en un test y en
 *  un helper que no está adentro de un `AuthProvider`.
 */
export function vocabularioDe(user: unknown): Vocabulario {
  const modulos = (user as { modulos?: string[] } | null)?.modulos ?? []
  return modulos.includes('modo_simple') ? VOCABULARIO_SIMPLE : VOCABULARIO_COMPLETO
}
