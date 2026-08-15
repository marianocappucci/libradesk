// Dos convenciones que se arreglaron a mano una vez y volvieron: el textarea y
// el tope de alto de los modales.
//
// **Este test lee el FUENTE, no el DOM**, por la misma razón que
// `espaciado-de-campos.test.ts` y `tile-de-iconos.test.tsx`: lo que hay que
// impedir no es que una pantalla se rompa —ninguna se rompe con un `<textarea>`
// crudo— sino que las pantallas **vuelvan a divergir**. Eso no se ve en ningún
// render: son 40 pantallas y un test de render sólo mira las que monta.
//
// 🔴 **Los fuentes se leen con `fs`, como DATOS, y no con `import.meta.glob`.**
// Con el glob, cada archivo —aunque se importe `?raw`— entra al grafo de módulos
// y su cobertura salta a 100 % sin un solo test nuevo. Un guard que falsea el
// informe de cobertura hace más daño del que evita.
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const DIRS = ['src/pages', 'src/components']

// El `<textarea>` crudo, con la clase copiada a mano. El primitivo
// `components/ui/textarea.tsx` existe desde el pedido 43 y estas cinco
// instancias eran de antes; se migraron el 2026-08-15.
//
// El propio primitivo rinde un `<textarea>` y queda excluido a mano: es el
// único lugar donde la etiqueta cruda es correcta.
const TEXTAREA_CRUDO = /<textarea\b/
const EXCEPCION_TEXTAREA = 'src/components/ui/textarea.tsx'

// Un tope de alto escrito en la pantalla. Vive en el primitivo del diálogo
// desde el 2026-08-15 — ver el comentario en `components/ui/dialog.tsx`.
const TOPE_EN_LA_PANTALLA = /<DialogContent[^>]*className="[^"]*\bmax-h-\[/

function archivos(dir: string): string[] {
  const base = join(process.cwd(), dir)
  return readdirSync(base, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory()
      ? archivos(join(dir, e.name))
      : /\.tsx?$/.test(e.name) ? [join(dir, e.name)] : [],
  )
}

const ARCHIVOS = DIRS.flatMap(archivos)

function buscar(patron: RegExp, excepto: string[] = []): string[] {
  const culpables: string[] = []
  for (const rel of ARCHIVOS) {
    const normal = rel.replace(/\\/g, '/')
    if (excepto.includes(normal)) continue
    readFileSync(join(process.cwd(), rel), 'utf8').split('\n').forEach((linea, i) => {
      if (patron.test(linea)) culpables.push(`${normal}:${i + 1}`)
    })
  }
  return culpables
}

describe('los primitivos de formulario no vuelven a divergir', () => {
  it('encuentra los fuentes', () => {
    // Sin esto, una ruta mal armada haría pasar a los casos de abajo con cero
    // archivos leídos — verde por no haber mirado nada.
    expect(ARCHIVOS.length).toBeGreaterThan(30)
  })

  it('🔴 ninguna pantalla rinde un `<textarea>` crudo', () => {
    expect(
      buscar(TEXTAREA_CRUDO, [EXCEPCION_TEXTAREA]),
      'va `<Textarea>` de `@/components/ui/textarea`: el crudo lleva la clase '
      + 'copiada a mano y se queda atrás del primitivo (foco, aria-invalid, tamaño)',
    ).toEqual([])
  })

  it('🔴 ningún `<DialogContent>` declara su propio tope de alto', () => {
    expect(
      buscar(TOPE_EN_LA_PANTALLA),
      'el tope vive en `components/ui/dialog.tsx`: parchearlo por pantalla es '
      + 'lo que dejó cuatro valores distintos y 33 modales sin ningún tope',
    ).toEqual([])
  })

  it('y los patrones que los detectan realmente matchean las formas viejas', () => {
    // El control de los dos casos de arriba. Sin esto, un regex que no matchea
    // nada daría la lista vacía y los tests pasarían con todas las instancias
    // presentes — que es el modo favorito de fallar de un test que busca
    // ausencias.
    expect(TEXTAREA_CRUDO.test('<textarea {...field} rows={3} className="w-full" />')).toBe(true)
    expect(TEXTAREA_CRUDO.test('                  <textarea')).toBe(true)
    // Y que no se lleve puesto al primitivo por su nombre.
    expect(TEXTAREA_CRUDO.test('<Textarea rows={3} />')).toBe(false)

    expect(TOPE_EN_LA_PANTALLA.test(
      '<DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-lg">')).toBe(true)
    expect(TOPE_EN_LA_PANTALLA.test(
      '<DialogContent className="max-h-[85vh] grid-rows-[auto_minmax(0,1fr)] p-0">')).toBe(true)
    // El `max-h` de la rejilla de la agenda no es un diálogo y sigue siendo suyo.
    expect(TOPE_EN_LA_PANTALLA.test(
      '<div data-rejilla-scroll className="max-h-[60vh] overflow-y-auto">')).toBe(false)
    // Y un ancho no es un alto.
    expect(TOPE_EN_LA_PANTALLA.test('<DialogContent className="sm:max-w-4xl">')).toBe(false)
  })
})
