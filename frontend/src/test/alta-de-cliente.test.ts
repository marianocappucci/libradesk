// El alta de cliente de los campos «Cliente» (ADR-071 de libra-ui) y la condición frente al IVA que pide en las pantallas fiscales.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { IVA_CONDITIONS } from 'libra-ui/facturas'
import { ALTA_FISCAL, payloadDeCliente } from '@/lib/alta-de-cliente'

const vacio = { nombre: 'Taller Norte', documento: '', condicionIva: '', telefono: '', email: '' }

describe('alta de cliente', () => {
  it('lo vacío viaja como null y el CUIT y la condición sólo si se cargaron', () => {
    expect(payloadDeCliente(vacio)).toEqual({ nombre: 'Taller Norte', telefono: null, email: null })
    expect(payloadDeCliente({ ...vacio, documento: '30-71111111-4', condicionIva: 'Monotributista' }))
      .toMatchObject({ cuit: '30-71111111-4', condicion_iva: 'Monotributista' })
  })

  it('las pantallas fiscales piden CUIT y condición frente al IVA', () => {
    expect(ALTA_FISCAL.campos).toEqual(['documento', 'condicionIva', 'telefono', 'email'])
  })

  it('🔴 las condiciones que ofrece el kit son las que el backend sabe leer (`CONDICIONES` de app/services/iva.py)', () => {
    // Si divergen, el alta guardaría una condición que `discrimina()` no reconoce (pasó con «IVA No Responsable», retirada en libra-ui v0.158.2).
    const fuente = readFileSync(join(process.cwd(), '..', 'app', 'services', 'iva.py'), 'utf8')
    const bloque = /CONDICIONES = \(([\s\S]*?)\)/.exec(fuente)?.[1] ?? ''
    const backend = [...bloque.matchAll(/"([^"]+)"/g)].map((m) => m[1])
    expect(backend.length).toBeGreaterThan(0)
    expect([...IVA_CONDITIONS].sort()).toEqual(backend.sort())
  })
})
