// El flag «es un equipo» y la conversión de stock a activo (2026-08-16).
//
// Lo que hay que sostener acá:
//
// 1. 🔴 Que el flag **viaje siempre**, también al editar. El PUT reconstruye el
//    producto entero del lado del motor, así que un formulario que no lo mande
//    lo borra en silencio — y las ventas siguientes dejan de dar de alta el
//    equipo sin que nadie se entere.
// 2. 🔴 Que la conversión a activo **sólo se ofrezca en lo que es un equipo**.
//    Convertir una ficha RJ11 en un activo alquilable no significa nada.
// 3. Que la conversión mande de qué depósito sale — sin eso el backend no sabe
//    de dónde descontar.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Productos } from '../pages/Productos'

const CENTRAL = {
  id: 1, nombre: 'Central HiPath 1120', activo: true, stock_minimo: 0,
  costo: 80000, precio: 200000, unidad: 'u', descripcion: '',
  categoria_id: null, categoria: '', codigo: 'PRD-00000001',
  iva_rate: 0.21, es_equipo: true, stock: 5, bajo_minimo: false,
}
const FICHA = {
  ...CENTRAL, id: 2, nombre: 'Ficha RJ11', precio: 800, costo: 200,
  codigo: 'PRD-00000002', es_equipo: false, stock: 100,
}
const DEPOSITOS = [{ id: 7, nombre: 'Depósito central' }]

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let pedidos: { metodo: string; url: string; cuerpo: Record<string, unknown> }[] = []

beforeEach(() => {
  pedidos = []
  vi.stubGlobal('fetch', vi.fn((url: unknown, init?: RequestInit) => {
    const u = String(url)
    if (init?.method && init.method !== 'GET') {
      pedidos.push({
        metodo: init.method, url: u,
        cuerpo: init.body ? JSON.parse(String(init.body)) : {},
      })
      return Promise.resolve(json({ id: 99 }))
    }
    if (u.includes('/api/depositos-stock')) return Promise.resolve(json(DEPOSITOS))
    if (u.includes('/api/consumibles-categorias')) return Promise.resolve(json([]))
    if (u.includes('/api/consumibles')) return Promise.resolve(json([CENTRAL, FICHA]))
    return Promise.resolve(json([]))
  }))
})

const montar = () => render(<MemoryRouter><Productos /></MemoryRouter>)

const filaDe = async (nombre: string) => {
  const celda = await screen.findByText(nombre)
  const fila = celda.closest('tr')
  if (!fila) throw new Error(`sin fila para ${nombre}`)
  return fila
}

describe('el flag «es un equipo»', () => {
  it('🔴 viaja en el PUT aunque no se lo toque', async () => {
    const user = userEvent.setup()
    montar()

    const fila = await filaDe('Central HiPath 1120')
    await user.click(within(fila).getByRole('button', { name: /Editar|Modificar/i }))
    const dialogo = await screen.findByRole('dialog')
    await user.click(within(dialogo).getByRole('button', { name: /Guardar/ }))

    await waitFor(() => expect(pedidos).toHaveLength(1))
    // El corazón del test: sin esto, guardar el precio le borra la marca.
    expect(pedidos[0].cuerpo.es_equipo).toBe(true)
  })

  it('se puede desmarcar, y viaja en false', async () => {
    const user = userEvent.setup()
    montar()

    const fila = await filaDe('Central HiPath 1120')
    await user.click(within(fila).getByRole('button', { name: /Editar|Modificar/i }))
    const dialogo = await screen.findByRole('dialog')
    await user.click(within(dialogo).getByRole('checkbox'))
    await user.click(within(dialogo).getByRole('button', { name: /Guardar/ }))

    await waitFor(() => expect(pedidos).toHaveLength(1))
    expect(pedidos[0].cuerpo.es_equipo).toBe(false)
  })
})

describe('convertir stock en activo', () => {
  it('🔴 sólo se ofrece en lo que es un equipo', async () => {
    montar()

    const central = await filaDe('Central HiPath 1120')
    const ficha = await filaDe('Ficha RJ11')

    expect(within(central).getByRole('button', { name: /Convertir/i })).toBeInTheDocument()
    expect(within(ficha).queryByRole('button', { name: /Convertir/i })).toBeNull()
  })

  it('manda el producto, el depósito y la serie', async () => {
    const user = userEvent.setup()
    montar()

    const fila = await filaDe('Central HiPath 1120')
    await user.click(within(fila).getByRole('button', { name: /Convertir/i }))
    const dialogo = await screen.findByRole('dialog')

    await user.click(within(dialogo).getByRole('combobox', { name: /depósito/i }))
    await user.click(
      await within(await screen.findByRole('listbox')).findByRole('option', {
        name: /Depósito central/,
      }),
    )
    await user.type(within(dialogo).getByLabelText(/serie/i), 'SN-0001')
    await user.click(within(dialogo).getByRole('button', { name: /Convertir en activo/ }))

    await waitFor(() => expect(pedidos).toHaveLength(1))
    expect(pedidos[0].url).toContain('/api/activos/desde-stock')
    expect(pedidos[0].cuerpo).toMatchObject({
      item_id: 1, deposito_stock_id: 7, tipo: 'Central HiPath 1120',
      serial: 'SN-0001',
    })
  })

  it('sin depósito no se puede convertir: el backend no sabría de dónde descontar', async () => {
    const user = userEvent.setup()
    montar()

    const fila = await filaDe('Central HiPath 1120')
    await user.click(within(fila).getByRole('button', { name: /Convertir/i }))
    const dialogo = await screen.findByRole('dialog')

    expect(
      within(dialogo).getByRole('button', { name: /Convertir en activo/ }),
    ).toBeDisabled()
  })
})
