// Formateo de plata y fechas, compartido por las pantallas de alquileres.
//
// Vive acá y no dentro de una página porque lo usan `Contratos` y
// `ContratoDetalle`: exportarlo desde un archivo que también exporta
// componentes dispara `react-refresh/only-export-components`, y copiarlo en las
// dos es la forma de que dentro de un mes muestren los importes distinto.
//
// `Reparaciones.tsx` y `Equipos.tsx` tienen su propia copia de estas dos
// funciones, de antes de que existiera este archivo. Unificarlas es una
// limpieza aparte — cambiar cómo se muestran importes en pantallas que hoy
// funcionan no es parte de este módulo.

export function pesos(v: number | null | undefined, moneda = 'ARS'): string {
  if (v === null || v === undefined) return '—'
  return v.toLocaleString('es-AR', {
    style: 'currency', currency: moneda, maximumFractionDigits: 0,
  })
}

/** Una fecha ISO (`YYYY-MM-DD`) en formato local.
 *
 * El `T00:00:00` no es decorativo: sin él, `new Date('2026-08-01')` se
 * interpreta como UTC y en Argentina (UTC-3) se muestra como 31/07.
 */
export function fecha(iso: string | null | undefined): string {
  return iso ? new Date(`${iso}T00:00:00`).toLocaleDateString('es-AR') : '—'
}
