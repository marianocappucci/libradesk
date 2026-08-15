// Dónde van los controles de una pantalla: una sola definición, la de libra-ui.
//
// Pedido del humano (2026-08-14): *"los botones de volver en las distintas
// pantallas siempre del lado derecho, como en la pantalla de presupuestos"*.
// La forma no se inventó: es la que ya tenía el detalle de comprobante de este
// producto, y de ahí salió `EncabezadoDePantalla` en `libra-ui v0.21.0`.
//
// El problema no era estético. El mismo `flex … justify-between` estaba escrito
// a mano en **20 lugares** de este repo y ya había divergido: `ContratoDetalle`
// ponía el "Volver" a la IZQUIERDA del título y además como botón de sólo
// icono, y `comercial-ui` usaba `gap-4` donde el resto usaba `gap-2` o `gap-3`.
// Con la forma repetida, cada pantalla nueva vuelve a decidir, y una de cada
// tantas decide distinto.
//
// **Este test lee el FUENTE, no el DOM**, por la misma razón que el guard de
// los títulos en `tile-de-iconos.test.tsx`: son 40 pantallas y un test de
// render sólo mira las que monta. La que se olvide queda sin cubrir, que es
// exactamente cómo se llegó a 20 copias.
//
// Lo que sí se prueba renderizando —que el "Volver" quede último— está en
// `comprobante-detalle.test.tsx`. Los dos hacen falta: éste impide que
// aparezcan encabezados nuevos fuera del componente, aquél fija qué hace el
// componente.
//
// 🔴 Los fuentes se leen con `fs`, como DATOS: con `import.meta.glob` cada
// archivo entra al grafo de módulos y su cobertura salta a 100 % sin un solo
// test nuevo, escondiendo los huecos reales.
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const DIRS = ['src/pages', 'src/components']

// Un encabezado escrito a mano: el contenedor `justify-between` con el título
// de la pantalla adentro. La ventana de líneas existe porque entre los dos
// suele haber un comentario o un `<div>` envolvente.
const CONTENEDOR = /className="[^"]*\bjustify-between\b/
const VENTANA = 8

function archivos(dir: string): string[] {
  const base = join(process.cwd(), dir)
  return readdirSync(base, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory()
      ? archivos(join(dir, e.name))
      : /\.tsx$/.test(e.name) ? [join(dir, e.name)] : [],
  )
}

function encabezadosAMano(texto: string): number[] {
  const lineas = texto.split('\n')
  const hallazgos: number[] = []
  lineas.forEach((linea, i) => {
    if (!CONTENEDOR.test(linea)) return
    const ventana = lineas.slice(i + 1, i + 1 + VENTANA).join('\n')
    if (ventana.includes('<TituloPantalla')) hallazgos.push(i + 1)
  })
  return hallazgos
}

const ARCHIVOS = DIRS.flatMap(archivos)

describe('el encabezado de una pantalla sale del componente compartido', () => {
  it('encuentra los fuentes', () => {
    // Sin esto, una ruta mal armada haría pasar al caso de abajo con cero
    // archivos leídos — verde por no haber mirado nada.
    expect(ARCHIVOS.length).toBeGreaterThan(30)
  })

  it('🔴 ninguna pantalla arma su encabezado con `justify-between` a mano', () => {
    const culpables: string[] = []
    for (const rel of ARCHIVOS) {
      for (const linea of encabezadosAMano(readFileSync(join(process.cwd(), rel), 'utf8'))) {
        culpables.push(`${rel.replace(/\\/g, '/')}:${linea}`)
      }
    }
    expect(culpables, 'el encabezado va con `<EncabezadoDePantalla titulo={…}>` '
      + "de 'libra-ui/acciones': ahí vive el orden de los controles, y el "
      + '"Volver" último').toEqual([])
  })

  it('y el patrón detecta de verdad la forma vieja', () => {
    // El control del caso de arriba. Sin esto, un patrón que no matchea nada
    // daría la lista vacía y el test pasaría con las 20 copias presentes — el
    // modo favorito de fallar de un test que busca ausencias.
    expect(encabezadosAMano([
      '      <div className="flex items-center justify-between">',
      '        <TituloPantalla icono={Users}>Clientes</TituloPantalla>',
      '      </div>',
    ].join('\n'))).toEqual([1])

    // Con un comentario en el medio, que es como estaba en Depósitos.
    expect(encabezadosAMano([
      '      <div className="flex flex-wrap items-center justify-between gap-3">',
      '        {/* un comentario largo',
      '            de varias líneas */}',
      '        <TituloPantalla icono={Building2}>Depósitos</TituloPantalla>',
      '      </div>',
    ].join('\n'))).toEqual([1])

    // Y que NO se lleve puesto un `justify-between` que no es un encabezado:
    // la fila interna del Dashboard y el `<h2>` de subsección de Inventario son
    // legítimos y tienen que seguir pasando.
    expect(encabezadosAMano([
      '      <div className="flex items-center justify-between text-sm">',
      '        <span>{clave}</span><strong>{valor}</strong>',
      '      </div>',
    ].join('\n'))).toEqual([])
  })
})
