/** El formato de fecha visible es dd-mm-aaaa, con guion (regla del 2026-08-12).
 *
 *  Antes esta app mostraba tres formatos distintos segun la pantalla:
 *  `toLocaleDateString('es-AR')` daba `1/8/2026`, `dateStyle: 'short'` daba
 *  `1/8/26` (año en dos digitos) y el backend armaba `01/08/2026`. Ahora sale
 *  todo de `lib/format`.
 *
 *  La TZ de la suite esta fijada en `vitest.config.ts`
 *  (`America/Argentina/Buenos_Aires`), asi que estas aserciones no dependen de
 *  la maquina donde corre.
 */
import { describe, expect, it } from 'vitest'
import { fecha, fechaDeDate, fechaHora, fechaHoraDeDate } from '@/lib/format'

describe('formato de fecha', () => {
  it('usa guion y dos digitos, no barra', () => {
    // El caso que delataba al formato viejo: dia y mes de un solo digito.
    expect(fecha('2026-08-01')).toBe('01-08-2026')
  })

  it('no corre la fecha un dia para atras', () => {
    // `new Date('2026-08-01')` se parsea como UTC; en UTC-3 eso es el 31/07.
    // El `T00:00:00` de `fecha()` es lo que lo evita.
    expect(fecha('2026-08-01')).not.toBe('31-07-2026')
  })

  it('el año va completo, no en dos digitos', () => {
    expect(fecha('2026-12-31')).toBe('31-12-2026')
  })

  it('con hora, agrega HH:MM en reloj de 24', () => {
    expect(fechaHora('2026-08-01T14:05:00')).toBe('01-08-2026 14:05')
  })

  it('la medianoche es 00, no 24', () => {
    expect(fechaHora('2026-08-01T00:30:00')).toBe('01-08-2026 00:30')
  })

  it('sin valor devuelve el guion largo', () => {
    expect(fecha(null)).toBe('—')
    expect(fechaHora(undefined)).toBe('—')
  })

  // Los dos que siguen salieron de una rotura real, no de imaginar casos.
  // `formatToParts` tira `RangeError` con un Date invalido (a diferencia de
  // `toLocaleDateString`, que devolvia la cadena "Invalid Date"), asi que el
  // historial de `Activos` dejo de renderizar entero.

  it('un valor que ya trae hora no se rompe', () => {
    // `Activos` pasa hitos cuyo campo `fecha` a veces incluye la hora. Pegarle
    // `T00:00:00` encima daba `2026-08-01T10:00:00T00:00:00`.
    expect(fecha('2026-08-01T10:00:00')).toBe('01-08-2026')
  })

  it('una fecha impresentable devuelve el guion, no revienta', () => {
    expect(() => fecha('cualquier cosa')).not.toThrow()
    expect(fecha('cualquier cosa')).toBe('—')
    expect(fechaHoraDeDate(new Date('x'))).toBe('—')
  })

  it('las variantes que reciben Date dan lo mismo', () => {
    const d = new Date(2026, 7, 1, 14, 5)
    expect(fechaDeDate(d)).toBe('01-08-2026')
    expect(fechaHoraDeDate(d)).toBe('01-08-2026 14:05')
  })

  it('ninguna salida contiene una barra', () => {
    const salidas = [
      fecha('2026-08-01'),
      fecha('2026-12-31'),
      fechaHora('2026-08-01T14:05:00'),
      fechaHoraDeDate(new Date(2026, 0, 9, 9, 9)),
    ]
    for (const s of salidas) expect(s).not.toContain('/')
    // Y que la lista no este vacia por un error de armado.
    expect(salidas).toHaveLength(4)
  })
})
