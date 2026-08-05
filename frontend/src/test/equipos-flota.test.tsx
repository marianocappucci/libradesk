// Equipos de trabajo y flota (pedido 42, fase A).
//
// Lo que la pantalla tiene que dejar claro:
//
// 1. **"En qué vehículo sale el equipo"** — la asignación, y que el selector
//    ofrezca sólo los disponibles. Un vehículo ya asignado a otro equipo no
//    puede salir dos veces, y ofrecerlo sería ofrecer un 409.
// 2. **El responsable sale del catálogo de personal**, filtrado por su rol.
//
// Los nombres de equipo se buscan en plural (`findAllByText`) desde la fase B:
// la pantalla ahora tiene también la agenda del día, con una tarjeta por
// equipo, así que cada nombre aparece dos veces. Lo que sigue siendo único —
// los botones, "Sin vehículo asignado." — se busca en singular.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EquiposYFlota } from '../pages/EquiposYFlota'

const render = (ui: ReactElement) => renderRTL(<MemoryRouter>{ui}</MemoryRouter>)

const persona = (id: number, nombre: string, extra = {}) => ({
  id, nombre, activo: true, es_tecnico: true, es_recepcionista: false,
  es_vendedor: false, es_responsable: false, roles: ['tecnico'], ...extra,
})

const SOFIA = persona(1, 'Sofía Núñez', {
  es_responsable: true, roles: ['tecnico', 'responsable'],
})
const DIEGO = persona(2, 'Diego Ramos')
const ANA = persona(3, 'Ana Paz')

const KANGOO = {
  id: 10, patente: 'AB123CD', marca: 'Renault', modelo: 'Kangoo', anio: 2019,
  estado: 'asignado', equipo_id: 1, equipo_nombre: 'Cuadrilla Norte',
  descripcion: 'Renault Kangoo', observaciones: null, created_at: null,
}
const PARTNER = {
  ...KANGOO, id: 11, patente: 'CD456EF', marca: 'Volkswagen', modelo: 'Partner',
  estado: 'disponible', equipo_id: null, equipo_nombre: null,
  descripcion: 'Volkswagen Partner',
}
const EN_TALLER = {
  ...PARTNER, id: 12, patente: 'EF789GH', estado: 'en_taller',
  descripcion: 'Fiat Fiorino', marca: 'Fiat', modelo: 'Fiorino',
}

const NORTE = {
  id: 1, nombre: 'Cuadrilla Norte', responsable_id: 1,
  responsable_nombre: 'Sofía Núñez', observaciones: null, activo: true,
  created_at: null,
  integrantes: [{ id: 2, nombre: 'Diego Ramos' }, { id: 3, nombre: 'Ana Paz' }],
  vehiculos: [KANGOO],
}
const SUR = {
  ...NORTE, id: 2, nombre: 'Cuadrilla Sur', integrantes: [], vehiculos: [],
  responsable_id: null, responsable_nombre: null,
}

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
    // El orden importa: /vehiculos cuelga de /equipos-trabajo.
    if (u.includes('/api/equipos-trabajo/vehiculos')) {
      return Promise.resolve(json([KANGOO, PARTNER, EN_TALLER]))
    }
    if (u.includes('/api/equipos-trabajo')) return Promise.resolve(json([NORTE, SUR]))
    if (u.includes('/api/tecnicos')) return Promise.resolve(json([SOFIA, DIEGO, ANA]))
    return Promise.resolve(json([]))
  }))
})

describe('Equipos de trabajo', () => {
  it('muestra el responsable, los integrantes y en qué sale', async () => {
    render(<EquiposYFlota />)
    expect((await screen.findAllByText('Cuadrilla Norte')).length).toBeGreaterThan(0)
    expect(screen.getByText(/Responsable: Sofía Núñez/)).toBeInTheDocument()
    expect(screen.getByText('Diego Ramos')).toBeInTheDocument()
    // El vehículo asignado: es la respuesta al pedido.
    expect(screen.getAllByText('AB123CD').length).toBeGreaterThan(0)
  })

  it('el equipo sin vehículo lo dice, no lo deja en blanco', async () => {
    render(<EquiposYFlota />)
    await screen.findAllByText('Cuadrilla Sur')
    expect(screen.getByText('Sin vehículo asignado.')).toBeInTheDocument()
    expect(screen.getByText('Sin integrantes.')).toBeInTheDocument()
  })

  it('🔴 el selector de responsable ofrece sólo a quien tiene el rol', async () => {
    // Ofrecer el personal entero haría que el rol no quisiera decir nada — y el
    // backend rechaza a quien no lo tiene, así que sería ofrecer un 409.
    const user = userEvent.setup()
    render(<EquiposYFlota />)
    await screen.findAllByText('Cuadrilla Norte')

    await user.click(screen.getByRole('button', { name: /Nuevo equipo/ }))
    const dialogo = await screen.findByRole('dialog')
    await user.click(within(dialogo).getByRole('combobox', { name: 'Responsable del equipo' }))

    const lista = await screen.findByRole('listbox')
    const opciones = within(lista).getAllByRole('option').map((o) => o.textContent)
    expect(opciones.some((t) => t?.includes('Sofía Núñez'))).toBe(true)
    expect(opciones.some((t) => t?.includes('Diego Ramos'))).toBe(false)
  })

  it('el alta manda la lista completa de integrantes', async () => {
    const user = userEvent.setup()
    render(<EquiposYFlota />)
    await screen.findAllByText('Cuadrilla Norte')

    await user.click(screen.getByRole('button', { name: /Nuevo equipo/ }))
    const dialogo = await screen.findByRole('dialog')
    await user.type(within(dialogo).getByLabelText('Nombre'), 'Cuadrilla Este')
    await user.click(within(dialogo).getByRole('checkbox', { name: 'Diego Ramos' }))
    await user.click(within(dialogo).getByRole('button', { name: /Guardar/ }))

    await waitFor(() => {
      const alta = pedidos.find((p) => p.metodo === 'POST' && p.url.endsWith('/api/equipos-trabajo'))
      expect(alta?.cuerpo).toMatchObject({ nombre: 'Cuadrilla Este', integrantes: [2] })
    })
  })
})

describe('Flota y asignación', () => {
  it('🔴 asignar ofrece sólo los disponibles', async () => {
    const user = userEvent.setup()
    render(<EquiposYFlota />)
    await screen.findAllByText('Cuadrilla Sur')

    await user.click(screen.getAllByRole('button', { name: /Asignar vehículo/ })[0])
    const dialogo = await screen.findByRole('dialog', { name: /Asignar vehículo/ })
    await user.click(within(dialogo).getByRole('combobox', { name: 'Vehículo a asignar' }))

    const lista = await screen.findByRole('listbox')
    const opciones = within(lista).getAllByRole('option').map((o) => o.textContent)
    // Sólo el Partner: la Kangoo ya está en otro equipo y el Fiorino en taller.
    expect(opciones.some((t) => t?.includes('CD456EF'))).toBe(true)
    expect(opciones.some((t) => t?.includes('AB123CD'))).toBe(false)
    expect(opciones.some((t) => t?.includes('EF789GH'))).toBe(false)
  })

  it('asignar manda el equipo elegido', async () => {
    const user = userEvent.setup()
    render(<EquiposYFlota />)
    await screen.findAllByText('Cuadrilla Sur')

    // El segundo botón es el de Cuadrilla Sur.
    await user.click(screen.getAllByRole('button', { name: /Asignar vehículo/ })[1])
    const dialogo = await screen.findByRole('dialog', { name: /Asignar vehículo/ })
    await user.click(within(dialogo).getByRole('combobox', { name: 'Vehículo a asignar' }))
    await user.click(await within(await screen.findByRole('listbox')).findByRole('option', { name: /CD456EF/ }))
    await user.click(within(dialogo).getByRole('button', { name: 'Asignar' }))

    await waitFor(() => {
      const asignar = pedidos.find((p) => p.url.includes('/asignar'))
      expect(asignar?.url).toContain('/vehiculos/11/asignar')
      expect(asignar?.cuerpo).toEqual({ equipo_id: 2 })
    })
  })

  it('el estado de un vehículo asignado no se puede editar', async () => {
    const user = userEvent.setup()
    render(<EquiposYFlota />)
    await screen.findByText('Renault Kangoo')

    await user.click(screen.getByRole('button', { name: 'Editar AB123CD' }))
    const dialogo = await screen.findByRole('dialog')

    // En vez de un selector con "asignado" adentro, explica por qué no se
    // puede: el backend lo rechaza, así que ofrecerlo sería ofrecer un 409.
    expect(within(dialogo).getByText(/Desasignalo para/)).toBeInTheDocument()
    expect(within(dialogo).queryByRole('combobox', { name: 'Estado del vehículo' })).not.toBeInTheDocument()
  })

  it('sin vehículos libres, el botón de asignar lo dice', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url)
      if (u.includes('/api/equipos-trabajo/vehiculos')) return Promise.resolve(json([KANGOO]))
      if (u.includes('/api/equipos-trabajo')) return Promise.resolve(json([NORTE]))
      if (u.includes('/api/tecnicos')) return Promise.resolve(json([SOFIA]))
      return Promise.resolve(json([]))
    }))
    render(<EquiposYFlota />)
    await screen.findAllByText('Cuadrilla Norte')

    const boton = screen.getByRole('button', { name: /No hay vehículos libres/ })
    expect(boton).toBeDisabled()
  })

  it('desasignar sale desde la tarjeta del equipo', async () => {
    const user = userEvent.setup()
    render(<EquiposYFlota />)
    await screen.findAllByText('Cuadrilla Norte')

    await user.click(screen.getByRole('button', { name: 'Desasignar AB123CD' }))

    await waitFor(() => {
      expect(pedidos.some((p) => p.url.includes('/vehiculos/10/desasignar'))).toBe(true)
    })
  })
})
