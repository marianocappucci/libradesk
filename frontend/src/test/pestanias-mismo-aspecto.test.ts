// Las pestañas del producto se ven todas igual, y siguen viéndose igual.
//
// **Este test lee los FUENTES, no el DOM**, por el mismo motivo que el guard
// de espaciado de `libra-ui`: lo que hay que impedir no es que una pantalla se
// rompa —ninguna se rompe con un borde de más— sino que las pestañas **vuelvan
// a divergir**. Eso no se ve en ningún render: se ve comparando archivos, y
// sólo si alguien se acuerda de comparar.
//
// De dónde salió: al 2026-08-22 la familia tenía **tres** conmutadores de
// pestañas distintos —la píldora de shadcn en Contalibra y Restolibra, un
// `<nav>` con subrayado en `libra-ui/Configuracion`, y la caja con borde y
// botones de este archivo— más **cuatro variantes distintas del propio
// `tabs.tsx`** repartidas entre los ocho productos. Ninguna de esas diferencias
// la había decidido nadie. El humano pidió que se vieran iguales, y la
// referencia es Contalibra.
//
// Acá `Conmutador` **no** usa Radix (ver su docstring: sus pestañas son
// enlaces, y `TabsTrigger asChild` les pisaría el rol). Lo que comparte con el
// primitivo es la cadena de clases, copiada literal. Este guard es lo que
// sostiene ese "literal": si alguien toca `tabs.tsx` y no el conmutador —o al
// revés— se pone rojo acá y no seis meses después, mirando dos pantallas.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import { CLASES_LISTA, CLASES_PESTANIA } from '@/components/conmutador'

// Desde el root donde corre vitest (`frontend/`). **No** desde
// `import.meta.url`: en este setup no es una URL `file:` y `fileURLToPath`
// revienta, con lo que el archivo entero queda sin correr — que se lee como
// "1 suite failed" y no como "el guard no midió nada".
const TABS = join(process.cwd(), 'src/components/ui/tabs.tsx')
const FUENTE = readFileSync(TABS, 'utf8')

describe('las pestañas no vuelven a divergir', () => {
  it('encuentra el primitivo', () => {
    // Sin esto, una ruta mal armada dejaría los dos casos de abajo comparando
    // contra la cadena vacía — verde por no haber leído nada.
    expect(FUENTE).toContain('data-slot="tabs-trigger"')
    expect(FUENTE.length).toBeGreaterThan(500)
  })

  it('🔴 el conmutador usa la MISMA clase de lista que `TabsList`', () => {
    expect(FUENTE, 'copiar la cadena de `TabsList` en `conmutador.tsx`: '
      + 'las pestañas de este producto tienen que verse como las de Contalibra')
      .toContain(CLASES_LISTA)
  })

  it('🔴 el conmutador usa la MISMA clase de pestaña que `TabsTrigger`', () => {
    expect(FUENTE, 'copiar la cadena de `TabsTrigger` en `conmutador.tsx`')
      .toContain(CLASES_PESTANIA)
  })

  it('y el guard detecta de verdad una cadena que no está', () => {
    // El control del caso de arriba. Sin esto, un `toContain` contra un fuente
    // que se leyó mal —o contra una constante vacía— pasaría igual: la cadena
    // vacía está contenida en cualquier texto, que es el modo favorito de
    // fallar de un guard escrito así.
    expect(FUENTE).not.toContain(CLASES_LISTA + ' rounded-none')
    expect(CLASES_LISTA.length).toBeGreaterThan(40)
    expect(CLASES_PESTANIA.length).toBeGreaterThan(200)
  })

  it('las variantes del primitivo cuelgan de `data-state`, que es lo que pone el conmutador', () => {
    // Es la pieza que hace que la cadena se pueda copiar tal cual: sin
    // `data-state` en el `<a>`, `data-[state=active]:bg-background` no aplica
    // nunca y la pestaña activa queda igual que las otras — mismo aspecto en
    // el fuente, ninguna diferencia en pantalla.
    expect(CLASES_PESTANIA).toContain('data-[state=active]:bg-background')
    const conmutador = readFileSync(join(process.cwd(), 'src/components/conmutador.tsx'), 'utf8')
    expect(conmutador).toContain("data-state={activa ? 'active' : 'inactive'}")
  })
})
