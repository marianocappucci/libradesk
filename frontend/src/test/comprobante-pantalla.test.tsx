// El formulario de comprobante REEMPLAZA al listado (2026-08-03).
//
// Hasta hoy "Nuevo presupuesto" abria el formulario ARRIBA y dejaba debajo el
// resumen por estado, el buscador y la tabla de los presupuestos anteriores.
// Cargar un comprobante quedaba mezclado con consultar los ya emitidos en la
// misma pantalla. Mismo caso en Remitos.
//
// No alcanza con afirmar que el formulario aparece —eso ya pasaba—: hay que
// afirmar que el listado NO esta. Por eso cada test chequea las dos cosas, y
// ademas que al cancelar el listado vuelve (si el formulario lo escondiera
// para siempre, la pantalla quedaria inutil y un test que solo mire el alta
// no lo notaria).
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Presupuestos } from '../pages/Presupuestos'
import { Remitos } from '../pages/Remitos'

const CLIENTE = {
  id: 1, nombre: 'Compulibra', empresa: 'Compulibra SRL', email: null, telefono: null,
  ciudad: null, cuit: null, domicilio: null, observaciones: null,
  tipo_facturacion: 'por_servicio', activo: true, fecha_creacion: null,
}

const ITEM = { description: 'Mano de obra', qty: 1, unit_price: 1000 }

const PRESUPUESTO = {
  id: 7, number: 'P-0007', date: '2026-08-01', valid_until: '2026-08-31',
  client_id: 1, client_name: 'Compulibra SRL', client_cuit: null, client_address: null,
  status: 'borrador', tax_rate: 0.21, observations: null, items: [ITEM],
  subtotal: 1000, tax: 210, total: 1210, remito_id: null,
}

const REMITO = {
  id: 4, number: 'R-0004', date: '2026-08-01',
  client_id: 1, client_name: 'Compulibra SRL', client_cuit: null, client_address: null,
  tax_rate: 0.21, observations: null, items: [ITEM],
  subtotal: 1000, tax: 210, total: 1210,
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  // El orden importa: /api/presupuestos/resumen contiene /api/presupuestos.
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/resumen')) return Promise.resolve(json({ borrador: 1 }))
    if (u.includes('/next-number')) return Promise.resolve(json({ number: 'P-0008' }))
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    if (u.includes('/api/presupuestos')) return Promise.resolve(json([PRESUPUESTO]))
    if (u.includes('/api/remitos')) return Promise.resolve(json([REMITO]))
    return Promise.resolve(json([]))
  }))
})

describe('Presupuestos', () => {
  it('al abrir el formulario, el listado y el resumen desaparecen', async () => {
    const user = userEvent.setup()
    render(<Presupuestos />)

    // Estado de partida: el listado esta.
    expect(await screen.findByText('P-0007')).toBeInTheDocument()
    expect(screen.getByLabelText('Buscar presupuestos')).toBeInTheDocument()
    expect(screen.getByText(/^Borrador: /)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '+ Nuevo presupuesto' }))

    expect(await screen.findByText(/Nuevo presupuesto/)).toBeInTheDocument()
    expect(screen.queryByText('P-0007')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Buscar presupuestos')).not.toBeInTheDocument()
    expect(screen.queryByText(/^Borrador: /)).not.toBeInTheDocument()
    // Y el boton que abre el alta tampoco, para no reabrir sobre lo cargado.
    expect(screen.queryByRole('button', { name: '+ Nuevo presupuesto' })).not.toBeInTheDocument()
  })

  it('al editar uno existente pasa lo mismo', async () => {
    const user = userEvent.setup()
    render(<Presupuestos />)
    await screen.findByText('P-0007')

    await user.click(screen.getByRole('button', { name: 'Editar presupuesto' }))

    expect(await screen.findByText(/Editar presupuesto/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Buscar presupuestos')).not.toBeInTheDocument()
  })

  it('al cancelar, el listado vuelve', async () => {
    const user = userEvent.setup()
    render(<Presupuestos />)
    await screen.findByText('P-0007')

    await user.click(screen.getByRole('button', { name: '+ Nuevo presupuesto' }))
    await screen.findByText(/Nuevo presupuesto/)
    await user.click(screen.getByRole('button', { name: 'Cancelar' }))

    await waitFor(() => expect(screen.getByText('P-0007')).toBeInTheDocument())
    expect(screen.getByLabelText('Buscar presupuestos')).toBeInTheDocument()
  })
})

describe('Remitos', () => {
  it('al abrir el formulario, el listado desaparece', async () => {
    const user = userEvent.setup()
    render(<Remitos />)

    expect(await screen.findByText('R-0004')).toBeInTheDocument()
    expect(screen.getByLabelText('Buscar remitos')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '+ Nuevo remito' }))

    expect(await screen.findByText(/Nuevo remito/)).toBeInTheDocument()
    expect(screen.queryByText('R-0004')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Buscar remitos')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+ Nuevo remito' })).not.toBeInTheDocument()
  })

  it('al cancelar, el listado vuelve', async () => {
    const user = userEvent.setup()
    render(<Remitos />)
    await screen.findByText('R-0004')

    await user.click(screen.getByRole('button', { name: '+ Nuevo remito' }))
    await screen.findByText(/Nuevo remito/)
    await user.click(screen.getByRole('button', { name: 'Cancelar' }))

    await waitFor(() => expect(screen.getByText('R-0004')).toBeInTheDocument())
    expect(screen.getByLabelText('Buscar remitos')).toBeInTheDocument()
  })
})
