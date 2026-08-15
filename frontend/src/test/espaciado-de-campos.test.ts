// El espaciado entre el label y su control, en un solo valor.
//
// De dónde salió: el humano reportó (2026-08-14) que en los formularios "los
// labels y los cuadros de inputs casi se solapan", y señaló el del **login**
// como el correcto. Medido: el login va en `gap-2` (8 px) y el resto de las
// pantallas usaba `gap-1.5` (6 px). El paquete [[libra-ui]] ya convergió al 8 px
// en su `v0.21.0`; acá se hace lo mismo con las 118 instancias del producto.
//
// **Este test lee el FUENTE, no el DOM**, y es a propósito — misma razón que el
// guard de los títulos en `tile-de-iconos.test.tsx`. Lo que hay que impedir no
// es que una pantalla se rompa (ninguna se rompe con 6 px en vez de 8) sino que
// las pantallas **vuelvan a divergir**. Eso no se ve en ningún render: son 40
// pantallas y un test de render sólo mira las que monta.
//
// 🔴 **El patrón NO es el literal `grid gap-1.5`.** Ese es el que usa libra-ui
// en su propio guard, y acá se le habrían escapado dos: `Clientes.tsx` y
// `Configuracion.tsx` escriben el contenedor como `grid flex-1 gap-1.5`, con
// una clase en el medio. Son campos igual —label arriba, input abajo— y estaban
// en 6 px como los otros 116. Por eso se pregunta por `grid` y `gap-1.5` en la
// misma línea, y no por una cadena contigua.
//
// ⚠️ **No se puede resolver con una regla CSS global.** Un `margin-bottom` sobre
// `[data-slot="label"]` tocaría también al login, que ya está en 8 px y pasaría
// a 10. El único lugar donde vive el espaciado es la clase del contenedor.
//
// 🔴 **Los fuentes se leen con `fs`, como DATOS, y no con `import.meta.glob`.**
// Con el glob, cada archivo —aunque se importe `?raw`— entra al grafo de módulos
// y su cobertura salta a 100 % sin un solo test nuevo. Un guard que falsea el
// informe de cobertura hace más daño del que evita: esconde los huecos reales.
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// Desde el root del proyecto, que es donde vitest corre.
const DIRS = ['src/pages', 'src/components']

// `grid` y `gap-1.5` en la misma línea: cubre `grid gap-1.5` y también
// `grid flex-1 gap-1.5`. Los `gap-1.5` que quedan vivos en el producto son
// todos de `flex` —el aire entre un icono y su texto—, que es otra cosa y no
// se toca.
const CAMPO_APRETADO = /className="[^"]*\bgrid\b[^"]*\bgap-1\.5\b/

function archivos(dir: string): string[] {
  const base = join(process.cwd(), dir)
  return readdirSync(base, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory()
      ? archivos(join(dir, e.name))
      : /\.tsx?$/.test(e.name) ? [join(dir, e.name)] : [],
  )
}

const ARCHIVOS = DIRS.flatMap(archivos)

describe('el espaciado de los campos no vuelve a divergir', () => {
  it('encuentra los fuentes', () => {
    // Sin esto, una ruta mal armada haría pasar a los casos de abajo con cero
    // archivos leídos — verde por no haber mirado nada.
    expect(ARCHIVOS.length).toBeGreaterThan(30)
  })

  it('🔴 ningún contenedor de campo queda en `gap-1.5`', () => {
    const culpables: string[] = []
    for (const rel of ARCHIVOS) {
      readFileSync(join(process.cwd(), rel), 'utf8').split('\n').forEach((linea, i) => {
        if (CAMPO_APRETADO.test(linea)) {
          culpables.push(`${rel.replace(/\\/g, '/')}:${i + 1}`)
        }
      })
    }
    // El mensaje va en el `expect` y no en un comentario: cuando esto se ponga
    // rojo, lo que se lee es esta línea, no el archivo.
    expect(culpables, 'los campos van con `gap-2` (8 px, el del login): '
      + '`gap-1.5` deja el label pegado al input').toEqual([])
  })

  it('🔴 ningún campo va dentro de un `<div>` sin clase', () => {
    // La OTRA forma de no tener separación, y la que el humano reportó el
    // 2026-08-15 en los modales de nueva venta y editar sucursal: el
    // contenedor no diverge a 6 px, **no tiene ninguna clase**, así que el
    // label queda pegado al input.
    //
    // El guard original no la veía: buscaba `gap-1.5`, y acá no hay `gap` que
    // buscar. Eran 36 en 6 archivos, casi todas del módulo comercial —que se
    // escribió con otra convención—, y el humano reportó 2. Las otras 34 las
    // encontró este chequeo.
    const culpables: string[] = []
    for (const rel of ARCHIVOS) {
      const lineas = readFileSync(join(process.cwd(), rel), 'utf8').split('\n')
      lineas.forEach((linea, i) => {
        if (!/^\s*<div>\s*$/.test(linea)) return
        // La primera línea con contenido después del `<div>`, salteando
        // comentarios: entre el contenedor y el label suele haber uno.
        let j = i + 1
        while (j < lineas.length && (!lineas[j].trim() || /^\s*(\{?\/\*|\*|\/\/)/.test(lineas[j]))) j++
        if (/^\s*<Label\b/.test(lineas[j] ?? '')) {
          culpables.push(`${rel.replace(/\\/g, '/')}:${i + 1}`)
        }
      })
    }
    expect(culpables, 'un campo va en `<div className="grid gap-2">`: un `<div>` '
      + 'pelado deja el label pegado al input').toEqual([])
  })

  it('y el patrón que los detecta realmente matchea las dos formas viejas', () => {
    // El control del caso de arriba. Sin esto, un regex que no matchea nada
    // daría la lista vacía y el test pasaría con las 118 instancias presentes —
    // que es el modo favorito de fallar de un test que busca ausencias.
    expect(CAMPO_APRETADO.test('<div className="grid gap-1.5">')).toBe(true)
    expect(CAMPO_APRETADO.test('<div className="grid flex-1 gap-1.5">')).toBe(true)
    // Y que no se lleve puesto el aire entre un icono y su texto, que es `flex`
    // y sigue legítimamente en 6 px.
    expect(CAMPO_APRETADO.test('<span className="flex items-center gap-1.5">')).toBe(false)
    expect(CAMPO_APRETADO.test('<div className="mt-1 flex flex-wrap gap-1.5">')).toBe(false)
    // Y que `gap-15` o `gap-1` no se cuelen por un borde de palabra flojo.
    expect(CAMPO_APRETADO.test('<div className="grid gap-1">')).toBe(false)
  })
})
