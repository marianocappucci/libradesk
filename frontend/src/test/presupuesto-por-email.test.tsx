// Mandar el presupuesto por email desde la ficha (2026-09-08).
//
// LibraDesk no tenia envio de comprobantes: el unico camino a `enviado` era el
// boton «Marcar como enviado», o sea que el estado dependia de que el usuario
// se acordara de apretarlo despues de mandar el PDF por su cuenta.
//
// Lo que se prueba aca y no en un test de API: que tras el envio la pantalla
// RELEA el presupuesto. El backend lo pasa a `enviado`, y si la ficha no
// volviera a pedirlo se quedaria mostrando «Borrador» —contradiciendo a la
// base— y seguiria ofreciendo «Marcar como enviado».
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PresupuestoDetalle } from '../pages/PresupuestoDetalle'

const ITEMS = [{ description: 'Mano de obra', qty: 2, unit_price: 15000, subtotal: 30000 }]

const BORRADOR = {
  id: 7, number: 'PRES-00000007', date: '2026-08-01', valid_until: '2026-09-01',
  client_id: 1, client_name: 'Compulibra SRL', client_cuit: '30-71234567-8',
  client_address: 'Av. Rivadavia 1234', client_email: 'admin@compulibra.test',
  client_phone: '11-5555-5555',
  status: 'borrador', tax_rate: 0.21, observations: null,
  items: ITEMS, subtotal: 30000, tax_amount: 6300, total: 36300,
  remito_id: null, pdf_path: null, created_at: null,
}
const ENVIADO = { ...BORRADOR, status: 'enviado' }

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

let fetchMock: ReturnType<typeof vi.fn>
let mandado: boolean

function prepararFetch(alEnviar: () => Response) {
  mandado = false
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    if (u.includes('/enviar-email')) return Promise.resolve(alEnviar())
    if (u.match(/\/api\/presupuestos\/\d+$/)) {
      return Promise.resolve(json(mandado ? ENVIADO : BORRADOR))
    }
    void init
    return Promise.resolve(json([]))
  })
  vi.stubGlobal('fetch', fetchMock)
}

beforeEach(() => {
  prepararFetch(() => { mandado = true; return json(ENVIADO) })
})

function montar() {
  render(
    <MemoryRouter initialEntries={['/presupuestos/7']}>
      <Routes>
        <Route path="/presupuestos/:id" element={<PresupuestoDetalle />} />
      </Routes>
    </MemoryRouter>,
  )
}

function pedidas(): string[] {
  return fetchMock.mock.calls.map((c) => String(c[0]))
}

describe('enviar el presupuesto por email', () => {
  it('el destinatario viene precargado con el email del cliente', async () => {
    const user = userEvent.setup()
    montar()

    await user.click(await screen.findByRole('button', { name: /Enviar por email/ }))

    expect(screen.getByLabelText('Destinatario')).toHaveValue('admin@compulibra.test')
  })

  it('🔴 tras mandarlo, la ficha se relee y muestra el estado nuevo', async () => {
    const user = userEvent.setup()
    montar()

    await user.click(await screen.findByRole('button', { name: /Enviar por email/ }))
    await user.click(screen.getByRole('button', { name: /^Enviar$/ }))

    // La insignia se dibuja dos veces (encabezado y datos): lo que importa es
    // que ninguna siga diciendo «Borrador».
    await waitFor(() => expect(screen.getAllByText('Enviado').length).toBeGreaterThan(0))
    expect(screen.queryByText('Borrador')).not.toBeInTheDocument()
    // Y el boton de marcarlo a mano ya no corresponde.
    expect(screen.queryByRole('button', { name: /Marcar como enviado/ })).not.toBeInTheDocument()
    // Se volvio a pedir la ficha: es lo que trae el estado nuevo.
    expect(pedidas().filter((u) => u.endsWith('/api/presupuestos/7'))).toHaveLength(2)
  })

  it('lo que se manda es el destinatario editado, no el del cliente', async () => {
    const user = userEvent.setup()
    montar()

    await user.click(await screen.findByRole('button', { name: /Enviar por email/ }))
    const campo = screen.getByLabelText('Destinatario')
    await user.clear(campo)
    await user.type(campo, 'otro@ejemplo.com')
    await user.click(screen.getByRole('button', { name: /^Enviar$/ }))

    await waitFor(() => expect(pedidas().some((u) => u.includes('/enviar-email'))).toBe(true))
    const envio = fetchMock.mock.calls.find((c) => String(c[0]).includes('/enviar-email'))
    expect(JSON.parse(String((envio![1] as RequestInit).body))).toEqual({ email: 'otro@ejemplo.com' })
  })

  it('si el envio falla, el error se ve y el dialogo queda abierto', async () => {
    // El error tipico es el SMTP sin configurar o una direccion mal escrita, y
    // en los dos casos se reintenta desde el mismo dialogo.
    const user = userEvent.setup()
    prepararFetch(() => json({ detail: 'Configurá el servidor SMTP en Configuración → Integraciones → Email / SMTP.' }, 400))
    montar()

    await user.click(await screen.findByRole('button', { name: /Enviar por email/ }))
    await user.click(screen.getByRole('button', { name: /^Enviar$/ }))

    expect(await screen.findByText(/Configurá el servidor SMTP/)).toBeInTheDocument()
    expect(screen.getByLabelText('Destinatario')).toBeInTheDocument()
    // Y el presupuesto sigue siendo un borrador: no se marco nada.
    expect(screen.getAllByText('Borrador').length).toBeGreaterThan(0)
  })
})
