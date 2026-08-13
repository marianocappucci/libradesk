// El acceso al PDF del recibo es un ícono, no la palabra «Ver» (2026-08-13).
//
// El cambio es de presentación, pero se testea por una razón concreta: **un
// botón sin texto se queda sin nombre accesible sin que nada falle**. La
// pantalla se ve igual de bien, el ojo se dibuja, y para un lector de pantalla
// el control pasa a llamarse "link" o directamente nada. Por eso cada test
// busca el enlace POR SU NOMBRE en vez de por el ícono: si alguien saca el
// `aria-label`, esto se pone en rojo.
//
// Se afirma además que el destino sigue siendo el PDF del recibo correcto —
// cambiar el rótulo de un botón es la clase de retoque donde se pierde el
// `href` sin que se note.
//
// La rama «Emitir recibo» de Ventas **conserva su texto** y también se afirma:
// es la que crea el comprobante, y ya se pagó una vez que emitiera en silencio.
import { render as renderRTL, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Recibos, Ventas } from '../pages/VentasComercial'
import { SucursalProvider } from '@/components/sucursal'

// `Ventas` monta el formulario de alta, que lee la sucursal activa del contexto.
const render = (ui: ReactElement) => renderRTL(
  <MemoryRouter><SucursalProvider>{ui}</SucursalProvider></MemoryRouter>,
)

const RECIBO = {
  id: 12, punto_venta: 1, numero: 6, fecha: '2026-08-13',
  cliente_id: 3, cliente_razon: 'Magnolia Suites S.A.', cliente_cuit: '',
  cliente_domicilio: '', origen_tipo: 'venta', origen_id: 2,
  concepto: 'Venta N° V-00000002', total: 362600, pagos: [],
  observaciones: '', anulado: 0,
}

// Una con recibo emitido y otra sin: son las dos ramas de `AccionRecibo`.
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

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/api/recibos')) return Promise.resolve(json([RECIBO]))
    if (u.includes('/api/ventas')) {
      return Promise.resolve(json([VENTA_CON_RECIBO, VENTA_SIN_RECIBO]))
    }
    return Promise.resolve(json([]))
  }))
})

describe('el acceso al PDF del recibo', () => {
  it('en Recibos es un ícono con nombre accesible, no la palabra «Ver»', async () => {
    render(<Recibos />)

    const link = await screen.findByRole('link', { name: /Ver el recibo 0001-00000006/ })
    expect(link).toHaveAttribute('href', '/api/recibos/12/pdf')
    // El rótulo viejo no quedó suelto en ningún lado de la fila.
    expect(screen.queryByRole('link', { name: 'Ver' })).not.toBeInTheDocument()
  })

  it('en Ventas, la venta ya recibida muestra el mismo ícono', async () => {
    render(<Ventas />)

    const link = await screen.findByRole('link', { name: /Ver el recibo de la venta V-00000002/ })
    expect(link).toHaveAttribute('href', '/api/recibos/12/pdf')
    expect(screen.queryByRole('link', { name: /Ver recibo/ })).not.toBeInTheDocument()
  })

  it('en Ventas, la que NO tiene recibo sigue diciendo «Emitir recibo» con todas las letras', async () => {
    render(<Ventas />)
    await screen.findByText('V-00000003')

    // Emitir crea un comprobante: ese botón no se convierte en ícono.
    expect(screen.getByRole('button', { name: 'Emitir recibo' })).toBeInTheDocument()
  })
})
