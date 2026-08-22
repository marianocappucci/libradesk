// El icono del título es el que el sidebar le da a esa misma pantalla.
//
// 🔴 **Lee los FUENTES, no el DOM.** Lo que hay que impedir no es que una
// pantalla se rompa —ninguna se rompe con el icono equivocado— sino que
// **vuelvan a divergir**: eso se ve cruzando el mapa de navegación contra cada
// pantalla, y sólo si alguien se acuerda de cruzar. El motor vive en
// `libra-ui/auditoria-de-titulos` y tiene sus propios tests allá.
//
// 📌 **Este producto ya cumplía el criterio antes del guard** — de acá salió
// `TituloPantalla`, y las 26 pantallas del menú ya usaban el icono correcto.
// El guard no vino a arreglar nada: vino a que siga así.
//
// ⚠️ **Lo que NO cubre**: las pantallas que `libra-ui` rinde enteras
// (`/usuarios`, `/logs`), porque no están en `pages/` de este producto —los
// archivos de acá son envoltorios de dos líneas—. A ésas las cubre el TIPO:
// desde la v0.34.0 el `icono` es una prop requerida y el compilador no deja
// montarlas sin pasarlo.
import { describe, expect, it } from 'vitest'
import { join } from 'node:path'
import { auditarTitulos, describirDesajustes } from 'libra-ui/auditoria-de-titulos'

const SRC = join(process.cwd(), 'src')

describe('el icono del título sale del sidebar', () => {
  it('🔴 ninguna pantalla usa un icono distinto al de su entrada del menú', () => {
    expect(describirDesajustes(auditarTitulos(SRC).distinto)).toEqual([])
  })

  it('🔴 ninguna pantalla del menú tiene el título sin icono', () => {
    expect(describirDesajustes(auditarTitulos(SRC).sinIcono)).toEqual([])
  })

  it('🔴 el control — el guard midió algo', () => {
    // Sin esto, los dos casos de arriba pasarían en verde si el parser dejara
    // de encontrar el Layout, el router o las pantallas: dos listas vacías
    // contra dos listas vacías. Es la forma en que este guard falló mientras se
    // escribía, y en este producto importa más que en ninguno, porque acá el
    // verde es el estado esperado desde el primer día.
    const { rutasDelNav, pantallas, conIcono } = auditarTitulos(SRC)
    expect(rutasDelNav).toBeGreaterThanOrEqual(30)
    expect(pantallas).toBeGreaterThanOrEqual(25)
    expect(conIcono).toBeGreaterThanOrEqual(24)
  })
})
