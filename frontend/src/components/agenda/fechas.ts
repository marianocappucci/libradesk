/** Aritmética de días para el calendario, en `YYYY-MM-DD` de punta a punta.
 *
 *  **Todo el cálculo se hace en UTC al mediodía**, y ese es el único truco de
 *  este archivo. Un `new Date('2026-08-11')` se interpreta como medianoche UTC,
 *  que en Argentina (UTC-3) es el 10 a las 21:00 — o sea que preguntarle el día
 *  devuelve el anterior. Y sumar días con `setDate()` sobre una fecha local se
 *  corre una hora en los saltos de horario de verano de otros husos, que es
 *  suficiente para que "sumar 7" caiga en el día equivocado. Anclando al
 *  mediodía UTC no hay corrimiento posible: ningún huso del mundo está a más de
 *  12 horas, así que la fecha del día nunca cambia.
 *
 *  La única función que mira el reloj local es `hoyLocal()`, y tiene que ser
 *  así: "hoy" es el día de pared del usuario, no el de UTC.
 */

/** Un `YYYY-MM-DD` a `Date` anclada al mediodía UTC. */
function aFecha(iso: string): Date {
  const [anio, mes, dia] = iso.split('-').map(Number)
  return new Date(Date.UTC(anio, mes - 1, dia, 12))
}

function aIso(d: Date): string {
  return d.toISOString().slice(0, 10)
}

/** Hoy en `YYYY-MM-DD`, **hora local**.
 *
 *  `toISOString()` a secas daría UTC y en Argentina (UTC-3) después de las
 *  21:00 devuelve el día siguiente — la agenda abriría en el día equivocado
 *  toda la noche. */
export function hoyLocal(): string {
  const d = new Date()
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 10)
}

export function sumarDias(iso: string, n: number): string {
  const d = aFecha(iso)
  d.setUTCDate(d.getUTCDate() + n)
  return aIso(d)
}

export function sumarMeses(iso: string, n: number): string {
  const d = aFecha(iso)
  // Al día 1 antes de mover el mes: sumarle uno al 31 de enero daría el 3 de
  // marzo, y "mes siguiente" tiene que ser febrero.
  d.setUTCDate(1)
  d.setUTCMonth(d.getUTCMonth() + n)
  return aIso(d)
}

/** El lunes de la semana que contiene a `iso`.
 *
 *  Lunes y no domingo: es la semana laboral, y esta agenda es de despacho. */
export function lunesDe(iso: string): string {
  const dow = aFecha(iso).getUTCDay() // 0 = domingo
  return sumarDias(iso, dow === 0 ? -6 : 1 - dow)
}

/** El primer día que dibuja la grilla del mes de `iso`: el lunes de la semana
 *  del día 1, que casi siempre cae en el mes anterior. */
export function inicioGrillaMes(iso: string): string {
  return lunesDe(`${iso.slice(0, 7)}-01`)
}

/** Cuántas celdas ocupa la grilla del mes de `iso`: 28, 35 o 42.
 *
 *  Se calcula en vez de usar 42 siempre. Un mes que entra en 5 semanas dibujaría
 *  un renglón entero vacío al pie, y además le pediría al backend una semana de
 *  agenda que nadie va a mirar. */
export function celdasGrillaMes(iso: string): number {
  const primero = aFecha(`${iso.slice(0, 7)}-01`)
  const dias = new Date(Date.UTC(
    primero.getUTCFullYear(), primero.getUTCMonth() + 1, 0,
  )).getUTCDate()
  const offset = (primero.getUTCDay() + 6) % 7 // lunes = 0
  return Math.ceil((offset + dias) / 7) * 7
}

/** `true` si los dos `YYYY-MM-DD` son del mismo mes calendario. */
export function mismoMes(a: string, b: string): boolean {
  return a.slice(0, 7) === b.slice(0, 7)
}

const DIAS_CORTOS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']

/** `Jue 14` — el encabezado de una columna de la semana. */
export function diaCorto(iso: string): string {
  const dow = (aFecha(iso).getUTCDay() + 6) % 7
  return `${DIAS_CORTOS[dow]} ${Number(iso.slice(8, 10))}`
}

/** Los siete rótulos de la fila de encabezados, de lunes a domingo. */
export const NOMBRES_DIAS = DIAS_CORTOS

/** `jueves 14 de agosto de 2026` — el título de la vista de día. */
export function diaLargo(iso: string): string {
  return aFecha(iso).toLocaleDateString('es-AR', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    timeZone: 'UTC', // la fecha ya está anclada; sin esto el locale la corre
  })
}

/** `11 al 17 de agosto de 2026` — el título de la vista de semana.
 *
 *  El mes se nombra una sola vez cuando la semana no lo cruza. Las que sí lo
 *  cruzan lo dicen dos veces (`29 de junio al 5 de julio de 2026`), que es la
 *  única forma de que se entienda dónde termina. */
export function rangoSemana(lunes: string): string {
  const domingo = sumarDias(lunes, 6)
  const mes = (iso: string) => aFecha(iso).toLocaleDateString('es-AR', {
    month: 'long', timeZone: 'UTC',
  })
  const dia = (iso: string) => Number(iso.slice(8, 10))
  const cierre = `${dia(domingo)} de ${mes(domingo)} de ${domingo.slice(0, 4)}`
  return mismoMes(lunes, domingo)
    ? `${dia(lunes)} al ${cierre}`
    : `${dia(lunes)} de ${mes(lunes)} al ${cierre}`
}

/** `agosto 2026` — el título de la vista de mes. */
export function mesLargo(iso: string): string {
  return aFecha(iso).toLocaleDateString('es-AR', {
    month: 'long', year: 'numeric', timeZone: 'UTC',
  })
}

/** La hora en 24 h, siempre.
 *
 *  `hour12: false` explícito y no el default del locale: los datos de ICU de
 *  Node dan `09:00 a. m.` para es-AR donde el navegador da `09:00`, así que sin
 *  esto el formato dependería de dónde corra. Y una agenda de despacho se lee
 *  en 24 h. */
export function hora(iso: string): string {
  return new Date(iso).toLocaleTimeString('es-AR', {
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
}
