// `fecha()` con un valor que YA trae hora.
//
// El defecto estaba documentado en `lib/format.ts` y vivo: la funcion le pegaba
// `T00:00:00` a todo valor que no tuviera una `T`, asi que un
// `2026-08-01 10:00:00` --la misma columna servida con espacio en vez de `T`--
// se volvia `2026-08-01 10:00:00T00:00:00`, que no es una fecha. Desde que el
// formateo pasa por `formatToParts` eso no se ve como "Invalid Date": tira
// `RangeError` y la pantalla no renderiza.
//
// 🔴 Estos asserts fallan con la version anterior de `fecha()`. Sin ese cuidado
// el test pasaria igual con el defecto puesto y no estaria probando nada.
import { describe, expect, it } from 'vitest'

import { fecha, fechaHora } from '../lib/format'

describe('fecha() con hora incluida', () => {
  it('acepta el separador espacio, no solo la T', () => {
    expect(fecha('2026-08-01 10:00:00')).toBe('01-08-2026')
  })

  it('sigue aceptando la T', () => {
    expect(fecha('2026-08-01T10:00:00')).toBe('01-08-2026')
  })

  it('no rompe con un valor cerca de medianoche', () => {
    // Con hora propia no se le pega el `T00:00:00`, asi que el valor se parsea
    // en hora local y el dia no se corre.
    expect(fecha('2026-08-01 23:30:00')).toBe('01-08-2026')
    expect(fecha('2026-08-01 00:30:00')).toBe('01-08-2026')
  })

  it('una fecha sola sigue sin correrse un dia para atras', () => {
    // El caso que el `T00:00:00` existe para cubrir: `new Date('2026-08-01')`
    // es medianoche UTC, o sea las 21:00 del 31 de julio en Argentina.
    expect(fecha('2026-08-01')).toBe('01-08-2026')
    expect(fecha('2026-08-01')).not.toBe('31-07-2026')
  })

  it('no confunde el dia con el mes', () => {
    // Con `2026-01-01` las dos lecturas dan lo mismo: hace falta una fecha
    // donde `dd-mm` y `mm-dd` se distingan.
    expect(fecha('2026-03-11')).toBe('11-03-2026')
  })

  it('un dato sucio no tumba la pantalla', () => {
    expect(() => fecha('cualquier cosa')).not.toThrow()
    expect(fecha('cualquier cosa')).toBe('—')
    expect(fecha(null)).toBe('—')
  })
})

describe('el sello de los backups', () => {
  it('el mtime que manda LibraCore sale en dd-mm-aaaa HH:MM', () => {
    // `libracore/respaldo.py` lo arma como 'YYYY-MM-DD HH:MM:SS'.
    expect(fechaHora('2026-08-22 10:15:33')).toBe('22-08-2026 10:15')
  })
})
