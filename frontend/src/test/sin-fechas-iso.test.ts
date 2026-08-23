// Guard: ninguna pantalla de LibraDesk muestra una fecha en ISO.
//
// 🔴 Busca la propiedad final --"ningun campo de fecha llega al texto
// renderizado sin pasar por `lib/format`"-- y no el patron viejo. La
// normalizacion del 2026-08-12 dejo cero `%d/%m` en el producto y aun asi
// cuatro pantallas seguian imprimiendo el ISO crudo, porque nunca habian
// llamado a un formateador: no habia patron que buscar.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const RAIZ = new URL('..', import.meta.url).pathname

const CAMPO = String.raw`(?:fecha|fecha_[a-z_]+|date|[a-z_]+_at|valid_until|vencimiento|periodo|mtime|ts)`
const HELPERS = String.raw`(?:fecha|fechaHora|fechaDeDate|fechaHoraDeDate|formatFecha|formatFechaHora|deIsoALocal|deLocalAIso)`

const INTERPOLADO = new RegExp(String.raw`\{\s*[A-Za-z_][\w.]*\.${CAMPO}\s*(?:\?\?[^}]*|\|\|[^}]*)?\}`)
// La interpolacion de un template string: `Salio el ${x.fecha_envio}`. Es la
// forma que tenian tres de las cuatro fugas de este producto.
const EN_TEMPLATE = new RegExp(String.raw`\$\{\s*[A-Za-z_][\w.]*\.${CAMPO}\s*\}`)
// El `(?:\?\?\s*''\s*)?` cubre `(x ?? '').slice(0, 10)`.
const RECORTADO = new RegExp(String.raw`\.${CAMPO}[\w.]*\s*(?:\?\?\s*''\s*)?\)?\s*\.(?:slice|substring)\(0,\s*(?:10|16|19)\)`)
const USA_HELPER = new RegExp(String.raw`\b${HELPERS}\s*\(`)

/** Lo que la regla excluye: los `<input type="date">` hablan el formato del
 *  navegador, y `deIsoALocal` alimenta un `datetime-local`, no una pantalla. */
const EXCLUIDO = [
  /type="date"/, /type="datetime-local"/, /\bkey=\{/, /^\s*(?:\/\/|\/\*|\*)/,
  /\bz\.(?:string|date|coerce)/, /\baria-label=|\btitle=/,
  /\bapi\.(?:get|post|put|del|patch)\(/, /\bfetch\(/,
]

export function fugasEn(texto: string): number[] {
  const fugas: number[] = []
  texto.split('\n').forEach((linea, i) => {
    if (EXCLUIDO.some((r) => r.test(linea))) return
    const recortado = RECORTADO.test(linea)
    if (!INTERPOLADO.test(linea) && !EN_TEMPLATE.test(linea) && !recortado) return
    if (USA_HELPER.test(linea) && !recortado) return
    if (!recortado && /[A-Za-z_-]+=\{[^{}]*\}\s*$/.test(linea.trim())) return
    fugas.push(i + 1)
  })
  return fugas
}

function archivos(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    if (statSync(p).isDirectory()) return archivos(p)
    return /\.tsx?$/.test(n) && !/\.test\./.test(n) ? [p] : []
  })
}

describe('ninguna fecha visible queda en ISO', () => {
  it('el detector encuentra una fuga cuando la hay', () => {
    // 🔴 Control POSITIVO. Sin el, un regex roto daria el mismo verde que un
    // codigo limpio -- el cero de abajo solo significa algo si este test pasa.
    // Y paso de verdad: la primera version de este detector no veia la forma
    // `(x ?? '').slice(0, 10)`, que era una de las fugas reales.
    expect(fugasEn('<Badge variant="outline">{b.mtime}</Badge>')).toEqual([1])
    expect(fugasEn('`Enviado el ${entry.data.fecha_envio} y listo`')).toEqual([1])
    expect(fugasEn("{(v.confirmed_at ?? '').slice(0, 10)}")).toEqual([1])
  })

  it('el detector NO marca lo que la regla excluye', () => {
    expect(fugasEn('<Input type="date" value={reemplazo.fechaEnvio} />')).toEqual([])
    expect(fugasEn('<Badge>{fechaHora(b.mtime)}</Badge>')).toEqual([])
    expect(fugasEn('`Enviado el ${fecha(entry.data.fecha_envio)}`')).toEqual([])
  })

  it('no queda ninguna en pages/ ni components/', () => {
    const sitios: string[] = []
    for (const dir of ['pages', 'components']) {
      let lista: string[]
      try {
        lista = archivos(join(RAIZ, dir))
      } catch {
        continue
      }
      for (const f of lista) {
        for (const linea of fugasEn(readFileSync(f, 'utf8'))) {
          sitios.push(`${f.replace(RAIZ, '')}:${linea}`)
        }
      }
    }
    expect(sitios).toEqual([])
  })
})
