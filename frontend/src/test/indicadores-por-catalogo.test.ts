// Guard: los reportes toman sus íconos del catálogo de la familia (`libra-ui/iconos-indicador`, ADR-038 del kit).
//
// 🔴 **Lee los FUENTES, no el DOM.** Lo que hay que impedir no es que una pantalla se rompa —ninguna se rompe con el ícono equivocado— sino
// que **vuelvan a divergir**: que el próximo reporte importe `FileSpreadsheet` de `lucide-react` porque quedaba bien, y que «Facturación» y
// «Equipamiento» vuelvan a llevar el mismo ícono (antes los diez lo tenían). Eso no se ve en ningún render; se ve en el `import`. El motor
// vive en `libra-ui/auditoria-de-indicadores` (uno para los nueve productos) y tiene sus propios tests allá; acá se lo corre sobre el
// `src/` de este producto.
//
// 📌 **LibraDesk no tiene Dashboard** (se sacó del producto el 2026-09-16): las pantallas medidas son el índice (`Reportes`), el detalle
// (`ReporteDetalle`) y el catálogo (`reportes-definicion`).
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { auditarIndicadores, describirInfracciones } from 'libra-ui/auditoria-de-indicadores'

const SRC = join(process.cwd(), 'src')

describe('los reportes toman el ícono del catálogo', () => {
  it('🔴 ninguna pantalla de reporte importa un ícono de concepto de lucide-react', () => {
    const r = auditarIndicadores(SRC)
    expect(describirInfracciones(r.infracciones)).toEqual([])
    // El control: un parser que no encuentra ninguna pantalla también deja `infracciones` vacío.
    expect(r.pantallas).toBeGreaterThan(0)
  })

  it('🔴 el control — el guard mide el índice, el detalle y el catálogo de reportes', () => {
    const r = auditarIndicadores(SRC, {
      esPantalla: (ruta) => /^pages\/(Reportes|ReporteDetalle|reportes-definicion)\.tsx$/.test(ruta),
    })
    expect(r.pantallas).toBe(3)
    expect(r.infracciones).toEqual([])
  })
})
