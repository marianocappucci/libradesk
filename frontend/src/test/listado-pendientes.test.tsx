// El botón que imprime la bandeja de pendientes (pedido del humano, 2026-09-08).
//
// **Qué se afirma y por qué.** El circuito de Lagrace empieza imprimiendo todo
// lo que está esperando; recién con ese papel en la mano los técnicos arman el
// día. La hoja de ruta de la Agenda es el otro extremo —por cuadrilla y por
// día, y exige haber asignado antes—, así que este botón va en Incidencias y
// no allá.
//
// Lo único que la pantalla decide es **el orden**, y viaja en la URL. Por eso
// el test mira el `href`: es todo el contrato entre la pantalla y el PDF.
import { render as renderRTL, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Incidencias } from '../pages/Incidencias'

const render = (ui: ReactElement) =>
  renderRTL(<MemoryRouter initialEntries={['/incidencias']}>{ui}</MemoryRouter>)

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json([]))))
})

const enlace = () => screen.findByRole('link', { name: /Imprimir pendientes/ })

describe('Listado de reclamos pendientes', () => {
  it('se imprime por antigüedad sin elegir nada', async () => {
    // El default importa: es el que se va a usar la mayoría de las veces, y
    // una URL sin `orden` dejaría que lo decida el backend por accidente.
    render(<Incidencias />)
    expect(await enlace()).toHaveAttribute(
      'href', '/api/incidencias/pendientes.pdf?orden=antiguedad',
    )
  })

  it('el orden elegido viaja al PDF', async () => {
    // 🔑 Sin esto, el selector se ve, se puede cambiar y no cambia nada — que
    // es el modo de falla exacto de un control conectado a un `useState` que
    // nadie lee.
    const user = userEvent.setup()
    render(<Incidencias />)
    await enlace()

    await user.click(screen.getByRole('combobox', {
      name: 'Orden del listado de pendientes',
    }))
    await user.click(await screen.findByText('Por localidad'))

    expect(await enlace()).toHaveAttribute(
      'href', '/api/incidencias/pendientes.pdf?orden=localidad',
    )
  })

  it('abre en otra pestaña, para no perder la grilla', async () => {
    // Se imprime y se sigue trabajando sobre el mismo listado. Mismo criterio
    // que la hoja de ruta de la Agenda.
    render(<Incidencias />)
    expect(await enlace()).toHaveAttribute('target', '_blank')
  })
})
