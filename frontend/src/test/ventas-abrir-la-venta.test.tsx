// Desde la lista de ventas se puede abrir la venta (2026-08-14).
//
// Hasta ahora no se podía: la única columna de acciones era la del recibo, sin
// encabezado, así que el ojo que abría el PDF del recibo se leía como «ver la
// venta». El endpoint `GET /api/ventas/{id}` ya existía y no lo llamaba nadie.
//
// Lo que se afirma acá es el comportamiento, no el estilo:
//
//  1. la fila entera navega al detalle;
//  2. **tocar los controles de la fila no navega** — es la parte que puede
//     romperse sola, porque el clic de un botón burbujea hasta el `<tr>`. Sin
//     la guarda de `Tabla`, «Emitir recibo» emitiría el comprobante y encima
//     sacaría a la persona de la pantalla antes de que lo viera;
//  3. el ojo sigue existiendo y apunta al detalle. No es redundante con la
//     fila: un `<tr>` clickeable no toma foco ni se activa con el teclado.
import { render as renderRTL, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Ventas } from '../pages/VentasComercial'
import { SucursalProvider } from '@/components/sucursal'

const VENTA_CON_RECIBO = {
  id: 2, numero: 'V-00000002', fecha: '2026-08-13', cliente: 'Magnolia Suites S.A.',
  total: 362600, en_cuenta_corriente: 0, estado: 'confirmed', recibo_id: 12,
}
const VENTA_SIN_RECIBO = {
  id: 3, numero: 'V-00000003', fecha: '2026-08-13', cliente: 'Neumyser S.A.',
  total: 471688, en_cuenta_corriente: 471688, estado: 'confirmed', recibo_id: null,
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

/** El detalle se reemplaza por una sonda: lo que se mide es a dónde se navegó,
 *  no qué dibuja la ficha. Muestra el id para distinguir una venta de la otra. */
function SondaDetalle() {
  return <p>detalle de la venta</p>
}

const render = (ui: ReactElement) => renderRTL(
  <MemoryRouter initialEntries={['/ventas']}>
    <SucursalProvider>
      <Routes>
        <Route path="/ventas" element={ui} />
        <Route path="/ventas/:id" element={<SondaDetalle />} />
      </Routes>
    </SucursalProvider>
  </MemoryRouter>,
)

let emitidos: string[] = []

beforeEach(() => {
  emitidos = []
  vi.stubGlobal('open', vi.fn())
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    if ((init?.method ?? 'GET') === 'POST' && u.includes('/recibo')) {
      emitidos.push(u)
      return Promise.resolve(json({ id: 99 }))
    }
    if (u.includes('/api/ventas')) {
      return Promise.resolve(json([VENTA_CON_RECIBO, VENTA_SIN_RECIBO]))
    }
    return Promise.resolve(json([]))
  }))
})

describe('abrir una venta desde la lista', () => {
  it('el clic en la fila lleva al detalle', async () => {
    render(<Ventas />)
    const numero = await screen.findByText('V-00000002')

    await userEvent.click(numero)

    expect(await screen.findByText('detalle de la venta')).toBeInTheDocument()
  })

  it('la columna de acciones tiene el ojo de ver la venta, apuntando al detalle', async () => {
    render(<Ventas />)

    const ojo = await screen.findByRole('link', { name: 'Ver la venta V-00000002' })
    expect(ojo).toHaveAttribute('href', '/ventas/2')

    // El otro ojo de la fila es el del recibo, y sigue yendo al PDF: son dos
    // acciones distintas, y fusionarlas es justo el defecto que se corrige.
    expect(screen.getByRole('link', { name: /Ver el recibo de la venta V-00000002/ }))
      .toHaveAttribute('href', '/api/recibos/12/pdf')
  })

  it('emitir el recibo no saca a la persona de la lista', async () => {
    render(<Ventas />)
    const boton = await screen.findByRole('button', { name: 'Emitir recibo' })

    await userEvent.click(boton)

    await waitFor(() => expect(emitidos).toEqual(['/api/ventas/3/recibo']))
    expect(screen.queryByText('detalle de la venta')).not.toBeInTheDocument()
    expect(screen.getByText('V-00000003')).toBeInTheDocument()
  })

  it('abrir el PDF del recibo tampoco navega al detalle', async () => {
    render(<Ventas />)
    const pdf = await screen.findByRole('link', { name: /Ver el recibo de la venta V-00000002/ })

    await userEvent.click(pdf)

    expect(screen.queryByText('detalle de la venta')).not.toBeInTheDocument()
  })
})
