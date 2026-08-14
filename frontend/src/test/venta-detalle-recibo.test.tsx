// La ficha de la venta ofrece el recibo, igual que la lista (2026-08-14).
//
// `GET /api/ventas/{id}` no devolvía `recibo_id`: el dato estaba sólo en
// `listar()`. La ficha no podía ni mostrar el comprobante ni decir que faltaba,
// así que abrir una venta para mandar el recibo obligaba a volver a la lista.
//
// Los dos estados se afirman por separado porque son ramas distintas de
// `AccionRecibo`, y la de emitir hace un `POST` que **crea un comprobante**.
import { render as renderRTL, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { VentaDetalle } from '../pages/VentasComercial'

const VENTA = {
  id: 2, numero: 'V-00000002', estado: 'confirmed', fecha: '2026-08-13',
  cliente: { id: 3, nombre: 'Magnolia Suites S.A.', cuit: '30-71234567-9', domicilio: 'Rivadavia 120' },
  cliente_nombre: 'Magnolia Suites S.A.',
  notas: null,
  recibo_id: null as number | null,
  items: [{ descripcion: 'Mano de obra', cantidad: 2, precio: 40000, subtotal: 80000 }],
  pagos: [{ medio: 'efectivo', monto: 80000, referencia: '' }],
  subtotal: 80000, total: 80000,
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

const render = () => renderRTL(
  <MemoryRouter initialEntries={['/ventas/2']}>
    <Routes><Route path="/ventas/:id" element={<VentaDetalle />} /></Routes>
  </MemoryRouter>,
)

/** El `recibo_id` que contesta el backend. Lo mueve el POST, como en serio. */
let reciboEmitido: number | null = null
let posts: string[] = []

beforeEach(() => {
  reciboEmitido = null
  posts = []
  vi.stubGlobal('open', vi.fn())
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    if ((init?.method ?? 'GET') === 'POST' && u.includes('/recibo')) {
      posts.push(u)
      reciboEmitido = 77
      return Promise.resolve(json({ id: 77 }))
    }
    return Promise.resolve(json({ ...VENTA, recibo_id: reciboEmitido }))
  }))
})

describe('el recibo en la ficha de la venta', () => {
  it('cuando ya está emitido, la ficha lo enlaza al PDF', async () => {
    reciboEmitido = 12

    render()

    const link = await screen.findByRole('link', { name: /Ver el recibo de la venta V-00000002/ })
    expect(link).toHaveAttribute('href', '/api/recibos/12/pdf')
    // Si la ficha lo ofreciera, no puede además pedir que se emita.
    expect(screen.queryByRole('button', { name: 'Emitir recibo' })).not.toBeInTheDocument()
  })

  it('cuando falta, lo emite desde la ficha y pasa a mostrarlo', async () => {
    render()
    const boton = await screen.findByRole('button', { name: 'Emitir recibo' })

    await userEvent.click(boton)

    await waitFor(() => expect(posts).toEqual(['/api/ventas/2/recibo']))
    // Lo que importa no es el POST: es que el comprobante quede a la vista.
    // Emitir sin mostrar es la mitad de la operación.
    const link = await screen.findByRole('link', { name: /Ver el recibo de la venta V-00000002/ })
    expect(link).toHaveAttribute('href', '/api/recibos/77/pdf')
  })
})
