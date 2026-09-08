// El detalle por ítem: la aclaración corta que va DEBAJO del nombre de un ítem.
//
// Es opcional renglón por renglón, y NO es «Observaciones»: eso es una sola y
// describe el comprobante entero. Los dos conviven en la misma pantalla, así
// que hay un caso que los manda juntos para que no se pisen.
//
// Lo que se prueba acá y no en un test de API: que el campo esté por renglón
// —no uno para todo el comprobante—, que el que no se llena viaje vacío, que
// un comprobante viejo (sin la clave) no deje el input descontrolado, y que en
// la ficha el detalle se vea DISTINTO del nombre del ítem. Eso último importa:
// si saliera con el mismo peso, se leería como un segundo ítem.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PresupuestoDetalle } from '../pages/PresupuestoDetalle'
import { Presupuestos } from '../pages/Presupuestos'
import { comprobanteADraft, draftAPayload, draftVacio } from '../components/comprobante-form'

const ITEMS = [
  { description: 'Mano de obra', qty: 2, unit_price: 15000, subtotal: 30000, detalle: 'dos técnicos, media jornada' },
  { description: 'Toner HP 26A', qty: 1, unit_price: 48000, subtotal: 48000 },
]

const PRESUPUESTO = {
  id: 7, number: 'PRES-00000007', date: '2026-08-01', valid_until: '2026-09-01',
  client_id: 1, client_name: 'Compulibra SRL', client_cuit: '30-71234567-8',
  client_address: 'Av. Rivadavia 1234', client_email: null, client_phone: null,
  status: 'borrador', tax_rate: 0.21, observations: 'Entrega en 48 h',
  items: ITEMS, subtotal: 78000, tax_amount: 16380, total: 94380,
  remito_id: null, pdf_path: null, created_at: null,
}

const CLIENTE = {
  id: 1, nombre: 'Compulibra', empresa: 'Compulibra SRL', email: null, telefono: null,
  ciudad: null, cuit: null, domicilio: null, observaciones: null,
  tipo_facturacion: 'por_servicio', activo: true, fecha_creacion: null,
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/resumen')) return Promise.resolve(json({ borrador: 1 }))
    if (u.includes('/next-number')) return Promise.resolve(json({ number: 'PRES-8' }))
    if (u.includes('/api/servicios/alicuotas')) return Promise.resolve(json([0, 0.105, 0.21, 0.27]))
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    if (u.match(/\/api\/presupuestos\/\d+$/)) return Promise.resolve(json(PRESUPUESTO))
    if (u.includes('/api/presupuestos')) return Promise.resolve(json([PRESUPUESTO]))
    return Promise.resolve(json([]))
  }))
})

describe('el formulario', () => {
  it('cada ítem tiene su propio campo de detalle, aparte de las observaciones', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><Presupuestos /></MemoryRouter>)
    await user.click(await screen.findByRole('button', { name: '+ Nuevo presupuesto' }))

    expect(await screen.findByLabelText('Detalle del ítem 1')).toBeInTheDocument()
    // Uno por renglón: agregar un ítem agrega su detalle.
    await user.click(screen.getByRole('button', { name: '+ Agregar ítem' }))
    expect(await screen.findByLabelText('Detalle del ítem 2')).toBeInTheDocument()
    // Y las observaciones siguen siendo UNA, del comprobante entero.
    expect(screen.getAllByLabelText(/^Detalle del ítem/)).toHaveLength(2)
    expect(screen.getByLabelText('Observaciones')).toBeInTheDocument()
  })

  it('lo que se escribe en un renglón no toca al otro', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><Presupuestos /></MemoryRouter>)
    await user.click(await screen.findByRole('button', { name: '+ Nuevo presupuesto' }))
    await user.click(await screen.findByRole('button', { name: '+ Agregar ítem' }))

    await user.type(screen.getByLabelText('Detalle del ítem 1'), 'con balanceo')
    expect(screen.getByLabelText('Detalle del ítem 1')).toHaveValue('con balanceo')
    expect(screen.getByLabelText('Detalle del ítem 2')).toHaveValue('')
  })
})

describe('el draft y el payload', () => {
  it('el detalle viaja en el payload, recortado', () => {
    const draft = draftVacio()
    const payload = draftAPayload({
      ...draft,
      client_id: '1',
      items: [
        { description: 'Mano de obra', detalle: '  dos técnicos  ', qty: '2', unit_price: '15000', tax_rate: '21' },
        { description: 'Toner', detalle: '', qty: '1', unit_price: '48000', tax_rate: '21' },
      ],
    }, 'presupuesto') as { items: { description: string; detalle: string }[] }

    expect(payload.items[0]).toMatchObject({ description: 'Mano de obra', detalle: 'dos técnicos' })
    // El que no se llenó viaja vacío: el backend lo lee como «sin detalle» y no
    // escribe la clave. Mandar `undefined` lo dejaría con el detalle anterior.
    expect(payload.items[1]).toMatchObject({ description: 'Toner', detalle: '' })
  })

  it('🔴 un comprobante sin la clave precarga vacío, no `undefined`', () => {
    // El backend no escribe `detalle` cuando el campo va vacío, así que los
    // comprobantes anteriores a la feature llegan sin ella. Sin el `?? ''` el
    // input queda descontrolado y React lo avisa por consola.
    const draft = comprobanteADraft({
      client_id: 1, date: '2026-08-01', client_cuit: null, client_address: null,
      tax_rate: 0.21, observations: null, items: ITEMS,
    })
    expect(draft.items[0].detalle).toBe('dos técnicos, media jornada')
    expect(draft.items[1].detalle).toBe('')
  })
})

describe('la ficha', () => {
  function montar() {
    render(
      <MemoryRouter initialEntries={['/presupuestos/7']}>
        <Routes>
          <Route path="/presupuestos/:id" element={<PresupuestoDetalle />} />
        </Routes>
      </MemoryRouter>,
    )
  }

  it('el detalle sale debajo del ítem, más chico y más claro', async () => {
    montar()
    const detalle = await screen.findByText('dos técnicos, media jornada')
    // Que aparezca no alcanza: tiene que verse distinto del nombre del ítem.
    expect(detalle).toHaveClass('text-xs', 'text-muted-foreground')
    expect(screen.getByText('Mano de obra').closest('td')).toContainElement(detalle)
  })

  it('🔴 el ítem sin detalle no dibuja ningún renglón secundario', async () => {
    // Control del caso de arriba: sin esto, la ficha pasaría igual si pintara
    // un `<span>` vacío bajo cada ítem y le metiera aire a todas las filas.
    montar()
    await waitFor(() => expect(screen.getByText('Toner HP 26A')).toBeInTheDocument())
    expect(screen.getByText('Toner HP 26A').closest('td')).toHaveTextContent(/^Toner HP 26A$/)
  })
})
