// Depósitos en dos pantallas (pedido 35, 2026-08-04).
//
// Lo que el pedido pedía y estos tests afirman:
//
// 1. **Dos pantallas**, no dos secciones de una. Cada una muestra sólo lo suyo
//    y el formulario ya sabe de quién es el depósito — el de la empresa no
//    pregunta el dueño, el de clientes sí.
// 2. **Se puede agregar, modificar y eliminar.** Antes los botones estaban
//    detrás de `isAdmin` aunque el backend permite a cualquier staff, así que
//    para un no-admin el módulo se veía de sólo lectura. Los tests corren
//    **sin sesión de admin** a propósito.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Depositos } from '../pages/Depositos'
import { DepositosClientes } from '../pages/DepositosClientes'

const render = (ui: ReactElement, ruta = '/depositos') =>
  renderRTL(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/depositos" element={ui} />
        <Route path="/depositos/clientes" element={ui} />
      </Routes>
    </MemoryRouter>,
  )

const TALLER = {
  id: 1, cliente_id: null, cliente_nombre: null, nombre: 'Taller',
  descripcion: 'Estantería del fondo', activo: true, es_default: true,
  total_equipos: 3, created_at: null,
}
const CENTRAL = {
  ...TALLER, id: 2, nombre: 'Depósito central', descripcion: null,
  es_default: false, total_equipos: 0,
}
const PANOL = {
  id: 3, cliente_id: 1, cliente_nombre: 'Estudio Sur', nombre: 'Pañol',
  descripcion: null, activo: true, es_default: false, total_equipos: 2,
  created_at: null,
}
const RACKS = {
  ...PANOL, id: 4, cliente_id: 2, cliente_nombre: 'Otro Cliente',
  nombre: 'Sala de racks', total_equipos: 0,
}

const CLIENTES = [
  {
    id: 1, nombre: 'Estudio Sur', empresa: null, email: null, telefono: null,
    ciudad: null, cuit: null, domicilio: null, observaciones: null,
    tipo_facturacion: 'mensual', activo: true, fecha_creacion: null,
  },
  {
    id: 2, nombre: 'Otro Cliente', empresa: null, email: null, telefono: null,
    ciudad: null, cuit: null, domicilio: null, observaciones: null,
    tipo_facturacion: 'mensual', activo: true, fecha_creacion: null,
  },
]

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let pedidos: { url: string; metodo: string; cuerpo: unknown }[] = []

beforeEach(() => {
  pedidos = []
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    const metodo = opciones?.method ?? 'GET'
    pedidos.push({
      url: u, metodo,
      cuerpo: opciones?.body ? JSON.parse(String(opciones.body)) : null,
    })
    if (metodo !== 'GET') return Promise.resolve(json({ ok: true }))
    if (u.includes('/api/clientes')) return Promise.resolve(json(CLIENTES))
    if (u.includes('/api/depositos')) {
      // El backend filtra `propios=true`; el mock lo respeta para que el test
      // mida lo que la pantalla realmente pide.
      return Promise.resolve(json(
        u.includes('propios=true') ? [TALLER, CENTRAL] : [TALLER, CENTRAL, PANOL, RACKS],
      ))
    }
    return Promise.resolve(json([]))
  }))
})

describe('Depósitos de la empresa', () => {
  it('pide sólo los propios y no muestra los de clientes', async () => {
    render(<Depositos />)
    expect(await screen.findByText('Taller')).toBeInTheDocument()
    expect(screen.getByText('Depósito central')).toBeInTheDocument()
    // La separación es el punto del pedido: acá no entra nada de clientes.
    expect(screen.queryByText('Pañol')).not.toBeInTheDocument()
    expect(pedidos.some((p) => p.url.includes('propios=true'))).toBe(true)
  })

  it('🔴 el ABM está disponible sin ser admin', async () => {
    // El backend monta este router con `staff_or_admin`, así que esconder los
    // botones no restringía nada: sólo hacía que el módulo se viera roto para
    // quien no fuera admin. Nótese que estos tests no montan `AuthContext`.
    render(<Depositos />)
    await screen.findByText('Taller')

    expect(screen.getByRole('button', { name: /Nuevo depósito/ })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Editar' })).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Eliminar Taller' })).toBeInTheDocument()
  })

  it('el alta no pregunta de quién es: manda cliente_id null', async () => {
    const user = userEvent.setup()
    render(<Depositos />)
    await screen.findByText('Taller')

    await user.click(screen.getByRole('button', { name: /Nuevo depósito/ }))
    const dialogo = await screen.findByRole('dialog')
    // La pantalla ya sabe el dueño — ése es el motivo de haberlas separado.
    expect(within(dialogo).queryByLabelText(/Dueño/)).not.toBeInTheDocument()

    await user.type(within(dialogo).getByLabelText('Nombre'), 'Depósito nuevo')
    await user.click(within(dialogo).getByRole('button', { name: /Guardar/ }))

    await waitFor(() => {
      const alta = pedidos.find((p) => p.metodo === 'POST' && p.url.includes('/api/depositos'))
      expect(alta?.cuerpo).toMatchObject({ nombre: 'Depósito nuevo', cliente_id: null })
    })
  })

  it('sólo el que no es predeterminado ofrece predeterminar', async () => {
    render(<Depositos />)
    await screen.findByText('Taller')
    // Taller ya lo es; Depósito central no.
    expect(screen.getAllByRole('button', { name: /Predeterminar/ })).toHaveLength(1)
  })
})

describe('Depósitos de clientes', () => {
  it('muestra sólo los de clientes, con su dueño', async () => {
    render(<DepositosClientes />, '/depositos/clientes')
    expect(await screen.findByText('Pañol')).toBeInTheDocument()
    expect(screen.getByText('Sala de racks')).toBeInTheDocument()
    expect(screen.queryByText('Taller')).not.toBeInTheDocument()
    expect(screen.getByText('Estudio Sur')).toBeInTheDocument()
  })

  it('el alta exige elegir el cliente', async () => {
    const user = userEvent.setup()
    render(<DepositosClientes />, '/depositos/clientes')
    await screen.findByText('Pañol')

    await user.click(screen.getByRole('button', { name: /Nuevo depósito/ }))
    const dialogo = await screen.findByRole('dialog')

    await user.type(within(dialogo).getByLabelText('Nombre'), 'Pañol nuevo')
    // Sin cliente no se puede guardar: un depósito de cliente sin cliente no
    // es nada.
    expect(within(dialogo).getByRole('button', { name: /Guardar/ })).toBeDisabled()

    await user.click(within(dialogo).getByRole('combobox', { name: 'Cliente del depósito' }))
    // Acotado al `listbox`: "Otro Cliente" también aparece como badge en la
    // tarjeta de su depósito, así que una búsqueda global encuentra dos.
    await user.click(await within(await screen.findByRole('listbox')).findByRole('option', { name: /Otro Cliente/ }))

    await waitFor(() => {
      expect(within(dialogo).getByRole('button', { name: /Guardar/ })).toBeEnabled()
    })
    await user.click(within(dialogo).getByRole('button', { name: /Guardar/ }))

    await waitFor(() => {
      const alta = pedidos.find((p) => p.metodo === 'POST' && p.url.includes('/api/depositos'))
      expect(alta?.cuerpo).toMatchObject({ nombre: 'Pañol nuevo', cliente_id: 2 })
    })
  })

  it('no ofrece predeterminar: eso es de los propios', async () => {
    // El backend rechaza marcar como default un depósito de cliente, porque
    // ahí van equipos de cualquiera. Ofrecer el botón sería ofrecer un 409.
    render(<DepositosClientes />, '/depositos/clientes')
    await screen.findByText('Pañol')
    expect(screen.queryByRole('button', { name: /Predeterminar/ })).not.toBeInTheDocument()
  })

  it('el filtro por cliente acota la lista', async () => {
    const user = userEvent.setup()
    render(<DepositosClientes />, '/depositos/clientes')
    await screen.findByText('Pañol')

    await user.click(screen.getByRole('combobox', { name: 'Filtrar por cliente' }))
    await user.click(await within(await screen.findByRole('listbox')).findByRole('option', { name: /Estudio Sur/ }))

    await waitFor(() => {
      expect(screen.queryByText('Sala de racks')).not.toBeInTheDocument()
    })
    expect(screen.getByText('Pañol')).toBeInTheDocument()
  })

  it('editando, el cliente no se puede cambiar', async () => {
    const user = userEvent.setup()
    render(<DepositosClientes />, '/depositos/clientes')
    await screen.findByText('Pañol')

    await user.click(screen.getAllByRole('button', { name: 'Editar' })[0])
    const dialogo = await screen.findByRole('dialog')

    // Mover el depósito a otro cliente arrastraría los equipos que tiene
    // adentro, que son del cliente actual.
    expect(within(dialogo).queryByRole('combobox', { name: 'Cliente del depósito' })).not.toBeInTheDocument()
    expect(within(dialogo).getByText(/no se puede cambiar/)).toBeInTheDocument()
  })
})
