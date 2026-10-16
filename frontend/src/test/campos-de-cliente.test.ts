// Guard: todo campo donde se elige un cliente ofrece darlo de alta ahí mismo (ADR-071, libra-ui v0.158.0).
//
// 🔴 **Lee los FUENTES, no el DOM**, igual que `selects-buscables.test.ts`. Lo que hay que impedir es que vuelva a nacer un desplegable de
// cliente sin el botón «Agregar nuevo cliente»: en el mostrador de LibraDesk, un cliente que no estaba cargado no se podía elegir y había que
// cancelar la recepción para crearlo. El motor vive en `libra-ui/auditoria-de-clientes` y tiene sus propios tests allá.
//
// Un campo de cliente es `SelectCliente`. Un *filtro* de listado o de reporte (no crea nada) se exceptúa con un comentario
// `cliente-sin-alta: <motivo>` en su renglón o en los tres de arriba.
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { auditarCamposDeCliente, describirCamposSinAlta } from 'libra-ui/auditoria-de-clientes'

const SRC = join(process.cwd(), 'src')

// Los campos que se migraron a `SelectCliente` y los filtros marcados, medidos el 2026-10-16. Son pisos, no techos: sumar un campo no rompe.
const MIGRADOS = 10
const FILTROS_MARCADOS = 8

describe('todo campo de cliente ofrece el alta', () => {
  const r = auditarCamposDeCliente(SRC)

  it('🔴 el control — el guard midió campos de cliente (un parser que devuelve cero sería un falso verde)', () => {
    expect(r.archivos).toBeGreaterThan(0)
    expect(r.campos).toBeGreaterThan(0)
    expect(r.conAlta).toBeGreaterThanOrEqual(MIGRADOS)
    expect(r.marcados).toBeGreaterThanOrEqual(FILTROS_MARCADOS)
  })

  it('ningún campo de cliente deja de ser SelectCliente, salvo un filtro marcado con su motivo', () => {
    expect(describirCamposSinAlta(r.infracciones)).toEqual([])
  })
})
