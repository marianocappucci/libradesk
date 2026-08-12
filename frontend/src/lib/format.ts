// Formateo de plata y fechas, compartido por las pantallas de alquileres.
//
// Vive acá y no dentro de una página porque lo usan `Contratos` y
// `ContratoDetalle`: exportarlo desde un archivo que también exporta
// componentes dispara `react-refresh/only-export-components`, y copiarlo en las
// dos es la forma de que dentro de un mes muestren los importes distinto.
//
// `Reparaciones.tsx` y `Equipos.tsx` tenían su propia copia de estas dos
// funciones, de antes de que existiera este archivo. Al unificar el formato de
// fecha (2026-08-12) las copias de FECHA se eliminaron y pasaron a importar de
// acá — si no, el formato nuevo habría quedado escrito en ocho lugares y con
// tres variantes distintas. Las copias de `pesos` siguen donde estaban:
// cambiar cómo se muestran importes en pantallas que hoy funcionan no es parte
// de este trabajo.

export function pesos(v: number | null | undefined, moneda = 'ARS'): string {
  if (v === null || v === undefined) return '—'
  return v.toLocaleString('es-AR', {
    style: 'currency', currency: moneda, maximumFractionDigits: 0,
  })
}

// --- fechas para mostrar ---------------------------------------------------
//
// El formato visible del ecosistema es `dd-mm-aaaa`, con GUION (regla del
// 2026-08-12). Se arma por partes en vez de usar `toLocaleDateString('es-AR')`
// porque ese devolvía `1/8/2026`: barra, y sin cero a la izquierda. Y el
// `dateStyle: 'short'` que usaban varias pantallas era peor todavía —
// `1/8/26`, con el año en dos dígitos.
//
// `formatToParts` en vez de un `.replace('/', '-')` sobre el string armado:
// el replace depende de que el locale ponga los separadores donde uno cree, y
// no avisa si algún día deja de hacerlo.

// `formatToParts` TIRA `RangeError: Invalid time value` con un Date inválido,
// mientras que `toLocaleDateString` devolvía la cadena "Invalid Date" sin
// quejarse. O sea que al cambiar de una a la otra, un dato que antes se veía
// feo pasa a romper la pantalla entera.
//
// Y pasa de verdad: `Activos.tsx` le da a `fecha()` el campo `fecha` de un
// hito, que a veces ya trae hora — ahí `fecha()` arma
// `2026-08-01T10:00:00T00:00:00`, que no es una fecha. Antes se veía
// "Invalid Date" en el historial; con `formatToParts` el diálogo directamente
// no renderiza.
function esValida(d: Date): boolean {
  return !Number.isNaN(d.getTime())
}

function partes(d: Date, conHora: boolean): Record<string, string> {
  const fmt = new Intl.DateTimeFormat('es-AR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    ...(conHora ? { hour: '2-digit' as const, minute: '2-digit' as const, hourCycle: 'h23' as const } : {}),
  })
  const p: Record<string, string> = {}
  for (const parte of fmt.formatToParts(d)) p[parte.type] = parte.value
  return p
}

/** Un `Date` ya construido en hora local → `dd-mm-aaaa`.
 *
 * La variante que recibe `Date` existe para las pantallas que arman la fecha
 * a mano (ver `fecha` acá abajo): la construcción es de ellas, el formato es
 * de acá.
 */
export function fechaDeDate(d: Date): string {
  if (!esValida(d)) return '—'
  const p = partes(d, false)
  return `${p.day}-${p.month}-${p.year}`
}

/** Un `Date` → `dd-mm-aaaa HH:MM`, en reloj de 24 h. */
export function fechaHoraDeDate(d: Date): string {
  if (!esValida(d)) return '—'
  const p = partes(d, true)
  return `${p.day}-${p.month}-${p.year} ${p.hour}:${p.minute}`
}

/** Una fecha ISO (`YYYY-MM-DD`) → `dd-mm-aaaa`.
 *
 * El `T00:00:00` no es decorativo: sin él, `new Date('2026-08-01')` se
 * interpreta como UTC y en Argentina (UTC-3) se muestra como el día anterior.
 * Si el valor YA trae hora, se usa tal cual: pegarle el `T00:00:00` encima lo
 * volvía una fecha inválida.
 */
export function fecha(iso: string | null | undefined): string {
  if (!iso) return '—'
  return fechaDeDate(new Date(iso.includes('T') ? iso : `${iso}T00:00:00`))
}

/** Un timestamp ISO completo → `dd-mm-aaaa HH:MM`. */
export function fechaHora(iso: string | null | undefined): string {
  return iso ? fechaHoraDeDate(new Date(iso)) : '—'
}

// --- fecha y hora para `<input type="datetime-local">` ---------------------
//
// El input habla `YYYY-MM-DDTHH:mm` **sin** zona, y el backend guarda un
// naive datetime (SQLite, hora local de la empresa). Las dos funciones son un
// recorte de string a propósito: pasar por `new Date().toISOString()` convierte
// a UTC y la agenda se correría tres horas.

/** Lo que guarda el backend → lo que el input muestra. */
export function deIsoALocal(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 16) : ''
}

/** Lo que el input devuelve → lo que se manda. Vacío es "sin agendar". */
export function deLocalAIso(local: string): string | null {
  return local ? `${local}:00` : null
}
