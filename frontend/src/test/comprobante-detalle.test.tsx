// La ficha de un comprobante ya emitido (2026-08-03).
//
// Hasta hoy no existía: desde el listado no había forma de abrir un
// presupuesto o un remito y ver qué tenía adentro. El pedido fue explícito —
// "algo parecido al detalle de una factura en Contalibra".
//
// Lo que se prueba acá y no en un test de API: que los ítems y los totales
// LLEGUEN A LA PANTALLA, y que el PDF sea un `<a href>` y no un
// `window.open()`. Lo segundo importa por una razón concreta: un popup lo
// puede bloquear el navegador sin avisar, y el síntoma —"hago click y no pasa
// nada"— es idéntico al del 500 que motivó todo esto.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PresupuestoDetalle } from '../pages/PresupuestoDetalle'
import { RemitoDetalle } from '../pages/RemitoDetalle'
import { Presupuestos } from '../pages/Presupuestos'

const ITEMS = [
  { description: 'Mano de obra', qty: 2, unit_price: 15000, subtotal: 30000 },
  { description: 'Toner HP 26A', qty: 1, unit_price: 48000, subtotal: 48000 },
]

const PRESUPUESTO = {
  id: 7, number: 'PRES-00000007', date: '2026-08-01', valid_until: '2026-09-01',
  client_id: 1, client_name: 'Compulibra SRL', client_cuit: '30-71234567-8',
  client_address: 'Av. Rivadavia 1234', client_email: 'admin@compulibra.test',
  client_phone: '11-5555-5555',
  status: 'borrador', tax_rate: 0.21, observations: 'Entrega en 48 h',
  items: ITEMS, subtotal: 78000, tax_amount: 16380, total: 94380,
  remito_id: null, pdf_path: null, created_at: null,
}

const REMITO = {
  id: 4, number: '0001-00000004', date: '2026-08-01',
  client_id: 1, client_name: 'Compulibra SRL', client_cuit: null,
  client_address: null, client_email: null, client_phone: null,
  tax_rate: 0.21, observations: null,
  items: ITEMS, subtotal: 78000, tax_amount: 16380, total: 94380,
  pdf_path: null, created_at: null,
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/resumen')) return Promise.resolve(json({ borrador: 1 }))
    if (u.includes('/next-number')) return Promise.resolve(json({ number: 'PRES-8' }))
    if (u.includes('/api/clientes')) return Promise.resolve(json([]))
    if (u.match(/\/api\/presupuestos\/\d+$/)) return Promise.resolve(json(PRESUPUESTO))
    if (u.match(/\/api\/remitos\/\d+$/)) return Promise.resolve(json(REMITO))
    if (u.includes('/api/presupuestos')) return Promise.resolve(json([PRESUPUESTO]))
    if (u.includes('/api/remitos')) return Promise.resolve(json([REMITO]))
    return Promise.resolve(json([]))
  })
  vi.stubGlobal('fetch', fetchMock)
})

function montar(ruta: string, path: string, Componente: () => React.ReactElement) {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path={path} element={<Componente />} />
        <Route path="/presupuestos" element={<Presupuestos />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('detalle de presupuesto', () => {
  it('muestra los ítems y los totales', async () => {
    montar('/presupuestos/7', '/presupuestos/:id', PresupuestoDetalle)

    // El número aparece dos veces a propósito (encabezado y tarjeta de datos),
    // igual que en Contalibra: se ancla en el encabezado.
    expect(await screen.findByRole('heading', { name: /PRES-00000007/ })).toBeInTheDocument()
    expect(screen.getByText('Mano de obra')).toBeInTheDocument()
    expect(screen.getByText('Toner HP 26A')).toBeInTheDocument()
    // El total, que es el número por el que se abre la ficha.
    expect(screen.getByText('$ 94.380,00')).toBeInTheDocument()
    expect(screen.getByText('IVA 21%')).toBeInTheDocument()
  })

  it('muestra los datos del cliente y la validez', async () => {
    montar('/presupuestos/7', '/presupuestos/:id', PresupuestoDetalle)

    expect(await screen.findByText(/Compulibra SRL/)).toBeInTheDocument()
    expect(screen.getByText(/30-71234567-8/)).toBeInTheDocument()
    expect(screen.getByText(/Av. Rivadavia 1234/)).toBeInTheDocument()
    // La validez se muestra formateada, no en el ISO que devuelve la API. Esta
    // línea afirmaba `2026-09-01` y era la que sostenía el formato viejo en el
    // detalle (cambiada el 2026-08-13, junto con el de las grillas).
    expect(screen.getByText(/01-09-2026/)).toBeInTheDocument()
    expect(screen.getByText(/Entrega en 48 h/)).toBeInTheDocument()
  })

  it('el PDF es un enlace real, no un window.open', async () => {
    montar('/presupuestos/7', '/presupuestos/:id', PresupuestoDetalle)

    const link = await screen.findByRole('link', { name: /Ver PDF/ })
    expect(link).toHaveAttribute('href', '/api/presupuestos/7/pdf')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('ofrece las acciones que corresponden a un borrador', async () => {
    montar('/presupuestos/7', '/presupuestos/:id', PresupuestoDetalle)

    expect(await screen.findByRole('button', { name: /Marcar como enviado/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Rechazar/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Eliminar presupuesto/ })).toBeInTheDocument()
    // Aceptar es del estado `enviado`, no del borrador.
    expect(screen.queryByRole('button', { name: /^Aceptar$/ })).not.toBeInTheDocument()
  })
})

describe('detalle de remito', () => {
  it('muestra los ítems y los totales', async () => {
    montar('/remitos/4', '/remitos/:id', RemitoDetalle)

    expect(await screen.findByRole('heading', { name: /0001-00000004/ })).toBeInTheDocument()
    expect(screen.getByText('Mano de obra')).toBeInTheDocument()
    expect(screen.getByText('$ 94.380,00')).toBeInTheDocument()
  })

  it('el PDF es un enlace real', async () => {
    montar('/remitos/4', '/remitos/:id', RemitoDetalle)

    const link = await screen.findByRole('link', { name: /Ver PDF/ })
    expect(link).toHaveAttribute('href', '/api/remitos/4/pdf')
  })

  it('un remito no tiene estado ni conversión', async () => {
    montar('/remitos/4', '/remitos/:id', RemitoDetalle)

    await screen.findByRole('heading', { name: /0001-00000004/ })
    expect(screen.queryByRole('button', { name: /Convertir en remito/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/Válido hasta/)).not.toBeInTheDocument()
  })
})

describe('desde el listado se llega al detalle', () => {
  it('el click en la fila navega a la ficha', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/presupuestos']}>
        <Routes>
          <Route path="/presupuestos" element={<Presupuestos />} />
          <Route path="/presupuestos/:id" element={<PresupuestoDetalle />} />
        </Routes>
      </MemoryRouter>,
    )

    // En el listado el número está en la tabla; en la ficha, en el encabezado.
    await user.click(await screen.findByText('PRES-00000007'))

    await waitFor(() =>
      expect(screen.getByRole('link', { name: /Ver PDF/ })).toBeInTheDocument())
    expect(screen.getByText('Toner HP 26A')).toBeInTheDocument()
  })

  it('el botón de PDF del listado no dispara la navegación de la fila', async () => {
    // `onRowClick` de libra-ui ignora los clicks sobre `button, a`. Sin eso,
    // bajar el PDF desde la tabla te sacaba de la tabla.
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/presupuestos']}>
        <Routes>
          <Route path="/presupuestos" element={<Presupuestos />} />
          <Route path="/presupuestos/:id" element={<PresupuestoDetalle />} />
        </Routes>
      </MemoryRouter>,
    )

    const pdf = await screen.findByRole('link', { name: 'Descargar PDF' })
    expect(pdf).toHaveAttribute('href', '/api/presupuestos/7/pdf')
    await user.click(pdf)

    // Sigue en el listado: el buscador sólo existe ahí.
    expect(screen.getByLabelText('Buscar presupuestos')).toBeInTheDocument()
  })
})
