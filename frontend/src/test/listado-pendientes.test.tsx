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

// Las localidades salen de los clientes: se contesta esa lista y vacío el resto.
function conClientes(clientes: unknown[]) {
  vi.stubGlobal('fetch', vi.fn((url: string) =>
    Promise.resolve(json(String(url).endsWith('/api/clientes') ? clientes : [])),
  ))
}

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

  it('la localidad elegida viaja al PDF', async () => {
    // Mismo modo de falla que el orden: un selector que se ve y no cambia nada.
    conClientes([
      { id: 1, nombre: 'Ferretería', ciudad: 'Chivilcoy', activo: true },
      { id: 2, nombre: 'Municipio', ciudad: 'Navarro', activo: true },
    ])
    const user = userEvent.setup()
    render(<Incidencias />)
    await enlace()

    await user.click(screen.getByRole('combobox', {
      name: 'Localidad del listado de pendientes',
    }))
    await user.click(await screen.findByRole('option', { name: 'Navarro' }))

    expect(await enlace()).toHaveAttribute(
      'href', '/api/incidencias/pendientes.pdf?orden=antiguedad&ciudad=Navarro',
    )
  })

  it('la misma ciudad con otras mayúsculas es una sola opción', async () => {
    // En los datos reales conviven `Chivilcoy` y `CHIVILCOY`. El backend las
    // compara sin distinguirlas, así que dos opciones imprimirían lo mismo.
    conClientes([
      { id: 1, nombre: 'A', ciudad: 'Chivilcoy', activo: true },
      { id: 2, nombre: 'B', ciudad: 'CHIVILCOY', activo: true },
      { id: 3, nombre: 'C', ciudad: null, activo: true },
    ])
    const user = userEvent.setup()
    render(<Incidencias />)
    await enlace()

    await user.click(screen.getByRole('combobox', {
      name: 'Localidad del listado de pendientes',
    }))
    const opciones = await screen.findAllByRole('option')
    expect(opciones.map((o) => o.textContent)).toEqual(['Todas las localidades', 'Chivilcoy'])
  })

  it('una localidad con espacios viaja codificada', async () => {
    conClientes([{ id: 1, nombre: 'A', ciudad: 'Norberto de la Riestra', activo: true }])
    const user = userEvent.setup()
    render(<Incidencias />)
    await enlace()

    await user.click(screen.getByRole('combobox', {
      name: 'Localidad del listado de pendientes',
    }))
    await user.click(await screen.findByRole('option', { name: 'Norberto de la Riestra' }))

    expect(await enlace()).toHaveAttribute(
      'href',
      '/api/incidencias/pendientes.pdf?orden=antiguedad&ciudad=Norberto%20de%20la%20Riestra',
    )
  })

  it('abre en otra pestaña, para no perder la grilla', async () => {
    // Se imprime y se sigue trabajando sobre el mismo listado. Mismo criterio
    // que la hoja de ruta de la Agenda.
    render(<Incidencias />)
    expect(await enlace()).toHaveAttribute('target', '_blank')
  })
})
