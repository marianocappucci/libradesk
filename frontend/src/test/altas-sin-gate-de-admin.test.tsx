// Clientes y Equipos: el ABM no es admin-only (reporte del usuario, 2026-08-13,
// mirando `demo.libradesk.com.ar`).
//
// Las dos pantallas escondían el alta —y la columna entera de acciones— detrás
// de `user.role === 'admin'`, pero `clientes.router` y `equipos.router` se
// montan con `staff_or_admin` en `app/main.py`. O sea: la API le acepta el POST
// a un `staff`, y la UI no le daba dónde tocar. Lo sufre la recepcionista, que
// es justo quien da de alta al cliente y al equipo cuando entran por el
// mostrador, y se ve de golpe en la demo, cuyo visitante es `staff` por diseño
// (`libraauth.bootstrap.ROL_DEMO`, que se niega a entregar `admin`).
//
// Es el MISMO defecto que ya se había reportado para proveedores el 2026-08-04
// —ver la cabecera de `proveedores.test.tsx`—; estas dos pantallas quedaron
// afuera de aquella pasada. Por eso el test se escribe acá y con rol `staff`
// fijo: con `admin` pasaría igual con el gate puesto y no probaría nada.
import { render as renderRTL, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Clientes } from '../pages/Clientes'
import { Equipos } from '../pages/Equipos'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'staff' }, loading: false }),
}))

const render = (ui: ReactElement, ruta: string) =>
  renderRTL(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes><Route path="*" element={ui} /></Routes>
    </MemoryRouter>,
  )

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

const CLIENTE = {
  id: 1, nombre: 'Clínica del Sol', empresa: null, email: null, telefono: null,
  ciudad: null, cuit: null, condicion_iva: null, domicilio: null,
  observaciones: null, tipo_facturacion: 'por_servicio', activo: true,
}

const EQUIPO = {
  id: 7, cliente_id: 1, tipo: 'Notebook', modelo: 'ThinkPad', marca: 'Lenovo',
  serial: 'ABC123', ubicacion_oficina: null, sector: null, deposito_id: null,
  deposito_nombre: null, estado: 'operativo', fecha_adicion: null,
  garantia_vence: null, observaciones: null,
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/api/clientes/condiciones-iva')) return Promise.resolve(json([]))
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    if (u.includes('/api/equipos')) return Promise.resolve(json([EQUIPO]))
    if (u.includes('/api/depositos')) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  }))
})

describe('🔴 Clientes: el ABM lo ve un staff, no sólo un admin', () => {
  it('ofrece el alta', async () => {
    render(<Clientes />, '/clientes')
    await screen.findByText('Clínica del Sol')

    expect(screen.getByRole('button', { name: /Nuevo cliente/ })).toBeInTheDocument()
  })

  it('ofrece editar, desactivar y los sectores de cada fila', async () => {
    // El gate no escondía sólo el alta: se llevaba puesta la columna
    // "Acciones" completa, así que la pantalla quedaba de sólo lectura.
    render(<Clientes />, '/clientes')
    await screen.findByText('Clínica del Sol')

    expect(screen.getByRole('button', { name: 'Editar cliente' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Desactivar cliente' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sectores del cliente' })).toBeInTheDocument()
  })
})

describe('🔴 Equipos: el ABM lo ve un staff, no sólo un admin', () => {
  it('ofrece el alta', async () => {
    render(<Equipos />, '/equipos')
    await screen.findByText('ThinkPad')

    expect(screen.getByRole('button', { name: /Nuevo equipo/ })).toBeInTheDocument()
  })

  it('ofrece editar y eliminar en la fila', async () => {
    // Acá la columna sí se rendía —la lupa de la ficha nunca estuvo gateada—,
    // así que afirmar "hay columna de acciones" habría pasado con el defecto
    // puesto. Se afirma sobre los dos botones que faltaban.
    render(<Equipos />, '/equipos')
    await screen.findByText('ThinkPad')

    expect(screen.getByRole('button', { name: 'Editar equipo' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Eliminar equipo' })).toBeInTheDocument()
  })
})
