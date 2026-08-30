/** El adaptador que `libra-ui` pide en `@/lib/fechas`.
 *
 *  🔴 **No es un formateador nuevo: re-exporta el del producto.** La regla del
 *  ecosistema es un helper único por producto, y el de LibraDesk vive en
 *  `lib/format.ts`, junto a `pesos()` y al resto del formateo de presentación.
 *  Escribir una segunda implementación acá sería exactamente lo que esa regla
 *  prohíbe.
 *
 *  Lo pide `libra-ui/Configuracion` (v0.47.0+) para mostrar la fecha de cada
 *  copia de backup en `dd-mm-aaaa HH:MM`.
 */
export { fecha, fechaHora } from '@/lib/format'
