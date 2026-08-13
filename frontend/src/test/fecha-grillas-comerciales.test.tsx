// Las grillas comerciales muestran la fecha en `dd-mm-aaaa`, no en ISO.
//
// `lib/format` y su `fecha()` existen desde el 2026-08-12 y están testeados en
// `formato-fecha.test.ts`. **Esas pruebas pasaban y estas pantallas seguían
// mostrando `2026-08-11`**: el helper estaba bien, simplemente no lo llamaba
// nadie acá. Las columnas se declaraban con `accessorKey` y sin `cell`, y
// TanStack Table imprime el valor crudo que viene de la API.
//
// Por eso estos tests no vuelven a probar el helper: prueban que la PANTALLA lo
// use. Cada uno afirma las dos mitades —que aparece `01-08-2026` y que **no**
// aparece `2026-08-01`—, porque sin la segunda el test pasa igual si alguien
// borra el `cell` y la tabla vuelve al ISO.
//
// Lo encontró la demo cargada para la reunión con Lagrace (2026-08-13):
// recibos y recepciones mostraban `13-08-2026` y, dos ítems más abajo en el
// mismo menú, presupuestos y remitos mostraban `2026-08-11`.
import { render as renderRTL, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Facturacion } from '../pages/Facturacion'
import { Presupuestos } from '../pages/Presupuestos'
import { Remitos } from '../pages/Remitos'

const render = (ui: ReactElement) => renderRTL(<MemoryRouter>{ui}</MemoryRouter>)

const CLIENTE = {
  id: 1, nombre: 'Compulibra', empresa: 'Compulibra SRL', email: null, telefono: null,
  ciudad: null, cuit: null, domicilio: null, observaciones: null,
  tipo_facturacion: 'por_servicio', activo: true, fecha_creacion: null,
}

const ITEM = { description: 'Mano de obra', qty: 1, unit_price: 1000 }

// Día y mes de UN SOLO dígito a propósito: es el caso que delata tanto al ISO
// (`2026-08-01`) como al `toLocaleDateString` viejo (`1/8/2026`).
const PRESUPUESTO = {
  id: 7, number: 'P-0007', date: '2026-08-01', valid_until: '2026-09-05',
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

const PENDIENTE = {
  origen_tipo: 'remito' as const, id: 1, numero: 'REM-00000001',
  fecha: '2026-08-01', cliente: 'Compulibra SRL', cliente_cuit: '30-71234567-9',
  total: 12100, envio: null,
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  // El orden importa: `/api/presupuestos/resumen` contiene `/api/presupuestos`.
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/resumen')) return Promise.resolve(json({ borrador: 1 }))
    if (u.includes('/next-number')) return Promise.resolve(json({ number: 'P-0008' }))
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    // `/pendientes` devuelve el estado del enlace y los ítems en un solo
    // objeto, no una lista pelada: con un array la pantalla revienta en
    // `items.filter`.
    if (u.includes('/api/facturacion/pendientes')) {
      return Promise.resolve(json({
        configurado: true, destino_nombre: 'Contalibra', items: [PENDIENTE],
      }))
    }
    if (u.includes('/api/presupuestos')) return Promise.resolve(json([PRESUPUESTO]))
    if (u.includes('/api/remitos')) return Promise.resolve(json([REMITO]))
    return Promise.resolve(json([]))
  }))
})

describe('la fecha en las grillas comerciales', () => {
  it('Presupuestos muestra la emisión en dd-mm-aaaa, no en ISO', async () => {
    render(<Presupuestos />)
    await screen.findByText('P-0007')

    expect(screen.getByText('01-08-2026')).toBeInTheDocument()
    expect(screen.queryByText('2026-08-01')).not.toBeInTheDocument()
  })

  it('Presupuestos también formatea la validez, que es la otra columna de fecha', async () => {
    render(<Presupuestos />)
    await screen.findByText('P-0007')

    expect(screen.getByText('05-09-2026')).toBeInTheDocument()
    expect(screen.queryByText('2026-09-05')).not.toBeInTheDocument()
  })

  it('Remitos muestra la fecha en dd-mm-aaaa, no en ISO', async () => {
    render(<Remitos />)
    await screen.findByText('R-0004')

    expect(screen.getByText('01-08-2026')).toBeInTheDocument()
    expect(screen.queryByText('2026-08-01')).not.toBeInTheDocument()
  })

  it('la bandeja de facturación usa el mismo formato que los comprobantes que lista', async () => {
    // Es la fecha del MISMO remito, en otra pantalla. Mostrarla distinto acá
    // es la inconsistencia que este arreglo elimina, no una pantalla aparte.
    render(<Facturacion />)
    await screen.findByText('REM-00000001')

    expect(screen.getByText('01-08-2026')).toBeInTheDocument()
    expect(screen.queryByText('2026-08-01')).not.toBeInTheDocument()
  })
})
