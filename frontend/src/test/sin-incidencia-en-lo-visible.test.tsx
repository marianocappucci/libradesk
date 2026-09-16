// Guard de la propiedad: ninguna pantalla principal dice "incidencia" en lo
// que el usuario VE. Decisión del humano (2026-09-13): LibraDesk pasa a decir
// "Reclamo/Reclamos" en todas las instancias; "incidencia" deja de usarse en
// lo visible (identificadores de código, rutas y nombres de columna quedan
// igual — ver AGENTS.md/CLAUDE.md del wiki, sección de convenciones).
//
// ## Por qué un test estático y no uno que renderiza cada pantalla
//
// Rendir las ~12 pantallas con datos completos (clientes, equipos, técnicos,
// categorías, resúmenes con la forma exacta que cada una espera) es el mismo
// costo que escribir de nuevo cada test de integración que ya existe para
// ellas — y esos ya afirman sus textos puntuales. Lo que hace falta acá es
// la propiedad transversal: que a NINGUNA lectura de estos archivos le quede
// un "incidencia" visible, incluida la que nadie pensó en armar un caso para
// ella.
//
// ## Por qué un tokenizer propio y no el compilador de TypeScript
//
// El primer intento usó el paquete `typescript` para parsear el AST de
// verdad. No sirvió: la versión instalada acá (7.x, el motor reescrito en Go)
// ya NO expone `createSourceFile`/`forEachChild` desde el entry point
// clásico — sólo utilidades sueltas (`is*`, `SyntaxKind`) bajo
// `typescript/unstable/ast`, sin manera directa de armar un `SourceFile` y
// recorrerlo. Migrar a la API nueva (basada en un `Program`/sistema de
// archivos virtual) era un proyecto en sí mismo para lo que hace falta acá.
//
// El intento antes de ése usaba regex ingenuas (`{[^{}]*}` hasta el punto
// fijo) y **pasaba en VERDE con la mutación de abajo puesta** — el peor
// resultado posible para un guard. La causa: nada distingue, mirando sólo el
// balance de llaves, el `{...}` de una prop JSX (`onClick={() => {...}}`) del
// `{...}` que abre el CUERPO ENTERO de la función del componente
// (`export function Incidencias(...) {`) — iterar hasta el punto fijo termina
// pelando los dos por igual y se lleva puesto el `return (...)` con el JSX
// adentro. Un tope fijo de pasadas tampoco alcanza: hay pantallas con
// condicionales más anidados que ese tope, y sin llegar al punto fijo quedan
// con basura suelta (falsos positivos).
//
// Lo que sigue es un tokenizer chico que sí entiende la diferencia, porque
// no cuenta llaves sueltas: entra en "modo expresión" únicamente cuando el
// `{` aparece DENTRO de una etiqueta JSX (atributo o hijos) — nunca desde el
// nivel superior del archivo — así que el `{`/`}` del cuerpo de la función,
// de un `if`, o de un objeto literal fuera de JSX no lo tocan nunca. Adentro
// de una expresión puede reconocer un tag JSX anidado
// (`{cond && (<Foo>texto</Foo>)}`) y volver a bajar. La apertura de un tag se
// reconoce por el `<` sin un identificador pegado antes —lo que lo distingue
// de un genérico de TypeScript (`Record<string, string>`) o un
// "menor que"— y con una letra, `/` o `>` pegados después.
//
// Aparte, se extraen los strings literales (comilla simple, doble y
// template) del archivo entero — para eso alcanza una regex simple, porque
// ahí no hay ambigüedad de gramática que resolver.
//
// Y se filtran, con una lista de excepciones documentada, las cadenas que son
// identificadores y no lo que se lee en pantalla: rutas (`/incidencias`, que
// sigue funcionando a propósito) y los `slug`/`id`/`grupo` internos de
// `reportes-definicion.tsx` (la palabra que se LEE es su `titulo`, que sí
// queda sujeto al chequeo).
//
// No sustituye a los tests de pantalla que afirman un texto puntual — es la
// red que agarra lo que ninguno de ellos preguntó.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const ARCHIVOS = [
  '../pages/Incidencias.tsx',
  '../pages/IncidenciaDetalle.tsx',
  '../pages/Configuracion.tsx',
  '../pages/ClienteDetalle.tsx',
  '../pages/EquipoDetalle.tsx',
  '../pages/Clientes.tsx',
  '../pages/Tecnicos.tsx',
  '../pages/Equipos.tsx',
  '../pages/Reparaciones.tsx',
  '../pages/reportes-definicion.tsx',
  '../components/Layout.tsx',
]

// Identificadores, no texto visible. Cada uno con su motivo — agregar acá es
// agregar una excepción real, no una forma de silenciar el test.
const EXCEPCIONES: RegExp[] = [
  // Rutas del front: `/incidencias` sigue funcionando a propósito (no romper
  // links guardados — ver App.tsx), `/reclamos` es la canónica. Nadie las
  // lee, las tipea el navegador.
  /^\/incidencias(\/|$|\?)/,
  // Cualquier ruta de API — nunca es texto que lea nadie.
  /^\/api\//,
  // Especificadores de import (`@/...`, `./...`, `../...`): nombres de
  // archivo, no contenido.
  /^[.@]/,
  // Claves de objetos JS que viajan como string literal para comparar o
  // indexar (`.has('incidencias_en_rango')`) — lo que el usuario lee es la
  // etiqueta con la que se las presenta, no la clave.
  /^incidencias_en_rango$/,
  /^incidencias_por_estado$/,
  /^incidencias_por_prioridad_abiertas$/,
  /^incidencias_abiertas$/,
  /^total_incidencias$/,
  // `reportes-definicion.tsx`: `id`/`slug`/`grupo` son claves internas del
  // catálogo de reportes, no lo que se lee — lo que se lee es el `titulo` de
  // cada uno, que este mismo test recorre igual (están en el archivo, sin
  // excepción).
  /^incidencias$/,
  /^incidencias-periodo$/,
]

function esExcepcion(candidato: string): boolean {
  return EXCEPCIONES.some((re) => re.test(candidato))
}

/** Saca `/* ... *\/` y las líneas que son puro comentario (`//…`, `*…` de
 *  JSDoc). Un comentario documenta código, no es lo que ve el usuario.
 */
function sinComentarios(fuente: string): string {
  const sinBloques = fuente.replace(/\/\*[\s\S]*?\*\//g, '')
  return sinBloques
    .split('\n')
    .filter((linea) => !/^\s*(\/\/|\*)/.test(linea))
    .join('\n')
}

/** El texto entre tags JSX — el tokenizer descripto arriba. Recorre todo el
 *  archivo buscando aperturas de tag; nunca "entra en modo expresión" desde
 *  el nivel superior, sólo desde adentro de un tag (atributo o hijos), así
 *  que el `{`/`}` que no es de JSX queda afuera.
 */
function textoJSXDe(s: string): string[] {
  const textos: string[] = []
  const n = s.length

  function esInicioDeTag(pos: number): boolean {
    if (s[pos] !== '<') return false
    const prev = pos > 0 ? s[pos - 1] : ''
    if (/[\w$]/.test(prev)) return false // pegado a un identificador: genérico o "menor que"
    const next = pos + 1 < n ? s[pos + 1] : ''
    return next === '>' || next === '/' || /[A-Za-z]/.test(next)
  }

  function saltarString(pos: number): number {
    const quote = s[pos]
    let j = pos + 1
    while (j < n) {
      if (s[j] === '\\') { j += 2; continue }
      if (s[j] === quote) return j + 1
      if (quote === '`' && s[j] === '$' && s[j + 1] === '{') {
        // `j` está en el '$'; el '{' está en `j+1`, así que "después del
        // '{'" es `j+2`. Con `j+1` acá (el off-by-one real, el que costó
        // encontrar), `saltarExpresion` cuenta el '{' de apertura como si
        // fuera uno anidado de más, y el `}` que en verdad cierra la
        // interpolación deja la profundidad en 1 en vez de 0 — sigue
        // buscando un `}` extra y se come el que cierra el ATRIBUTO entero.
        // Con un solo template con interpolación en un atributo (el de
        // `aria-label` de la columna "elegir" en Incidencias.tsx) alcanzaba
        // para desincronizar el resto del archivo y dar CERO textos JSX —
        // que es exactamente por qué la mutación de más abajo pasaba en
        // VERDE la primera vez: el guard nunca llegaba a ver nada.
        j = saltarExpresion(j + 2)
        continue
      }
      j++
    }
    return j
  }

  function saltarExpresion(pos: number): number {
    // `pos` apunta justo DESPUÉS del '{' que abre. Balancea `{}` propios,
    // saltea strings enteros y vuelve a bajar a JSX si aparece un tag.
    let depth = 1
    let j = pos
    while (j < n && depth > 0) {
      if (esInicioDeTag(j)) { j = procesarElemento(j); continue }
      const c = s[j]
      if (c === '{') { depth++; j++ }
      else if (c === '}') { depth--; j++ }
      else if (c === "'" || c === '"' || c === '`') { j = saltarString(j) }
      else j++
    }
    return j
  }

  function procesarTag(pos: number): { fin: number, autocerrado: boolean } {
    // `pos` en el '<' de apertura. Recorre atributos saltando sus strings y
    // sus `{...}`, hasta '>' o '/>'.
    let j = pos + 1
    while (j < n) {
      const c = s[j]
      if (c === '>') return { fin: j + 1, autocerrado: false }
      if (c === '/' && s[j + 1] === '>') return { fin: j + 2, autocerrado: true }
      if (c === '{') { j = saltarExpresion(j + 1); continue }
      if (c === '"' || c === "'") { j = saltarString(j); continue }
      j++
    }
    return { fin: j, autocerrado: true }
  }

  function procesarElemento(pos: number): number {
    const { fin, autocerrado } = procesarTag(pos)
    if (autocerrado) return fin
    let j = fin
    let acumulado = ''
    const cerrar = () => {
      const t = acumulado.trim().replace(/\s+/g, ' ')
      if (t) textos.push(t)
      acumulado = ''
    }
    while (j < n) {
      if (s[j] === '<' && s[j + 1] === '/') {
        cerrar()
        while (j < n && s[j] !== '>') j++
        return j + 1
      }
      if (esInicioDeTag(j)) {
        cerrar()
        j = procesarElemento(j)
        continue
      }
      if (s[j] === '{') {
        cerrar()
        j = saltarExpresion(j + 1)
        continue
      }
      acumulado += s[j]
      j++
    }
    cerrar()
    return j
  }

  let i = 0
  while (i < n) {
    if (esInicioDeTag(i)) i = procesarElemento(i)
    else i++
  }
  return textos
}

function candidatosDe(fuenteOriginal: string): string[] {
  const fuente = sinComentarios(fuenteOriginal)
  const candidatos: string[] = [...textoJSXDe(fuente)]

  for (const m of fuente.matchAll(/'(?:[^'\\]|\\.)*'/g)) candidatos.push(m[0].slice(1, -1))
  for (const m of fuente.matchAll(/"(?:[^"\\]|\\.)*"/g)) candidatos.push(m[0].slice(1, -1))
  for (const m of fuente.matchAll(/`(?:[^`\\]|\\.)*`/g)) {
    candidatos.push(m[0].slice(1, -1).replace(/\$\{[^{}]*\}/g, ''))
  }

  return candidatos
}

function leer(rutaRelativa: string): string {
  return readFileSync(fileURLToPath(new URL(rutaRelativa, import.meta.url)), 'utf-8')
}

describe('Ninguna pantalla principal dice "incidencia" en lo visible', () => {
  for (const archivo of ARCHIVOS) {
    it(`${archivo}: sin "incidencia" fuera de rutas/identificadores`, () => {
      const candidatos = candidatosDe(leer(archivo))
      const filtrados = candidatos.filter((c) => c.trim() && !esExcepcion(c.trim()))
      const conIncidencia = filtrados.filter((c) => /incidencia/i.test(c))

      expect(conIncidencia).toEqual([])
    })
  }
})
