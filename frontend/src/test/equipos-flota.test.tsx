// Equipos de trabajo y flota (pedido 42, fase A).
//
// Lo que la pantalla tiene que dejar claro:
//
// 1. **"En qué vehículo sale el equipo"** — la asignación, y que el selector
//    ofrezca sólo los disponibles. Un vehículo ya asignado a otro equipo no
//    puede salir dos veces, y ofrecerlo sería ofrecer un 409.
// 2. **El responsable sale del catálogo de personal**, filtrado por su rol.
//
// Los nombres de equipo vuelven a buscarse en singular (`findByText`) desde que
// las tres secciones son pestañas: la agenda, que también dibuja una tarjeta por
// equipo, ya no se renderiza junto al armado. Que cada nombre aparezca una sola
// vez es parte de lo que se pidió, así que el singular lo verifica.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EquiposDeTrabajo, Flota } from '../pages/EquiposYFlota'

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

// Las secciones separadas en pestañas (2026-08-07, a pedido del usuario).
//
// Lo que hay que sostener: que el conmutador **no sea decorativo**. Si las dos
// siguieran renderizándose juntas, la pantalla seguiría siendo la misma tira
// larga y el pedido no estaría hecho.
//
// **Eran tres.** La agenda se fue a pantalla propia el 2026-08-14 (`/agenda`),
// y lo que hay que sostener acá es que **no quedó ningún rastro**: ni pestaña,
// ni tarjetas de agenda dibujándose de nuevo al lado del armado.
const pestania = (nombre: string | RegExp) => screen.getByRole('link', { name: nombre })

describe('Equipos y flota en pestañas', () => {
  it('las dos pestañas están, y apuntan a rutas propias', async () => {
    render(<EquiposDeTrabajo />)
    await screen.findByText('Cuadrilla Norte')

    expect(pestania('Equipos de trabajo')).toHaveAttribute('href', '/equipos-trabajo')
    expect(pestania('Flota')).toHaveAttribute('href', '/equipos-trabajo/flota')
  })

  it('🔴 la agenda ya no es una pestaña de acá', async () => {
    // Se afirma sobre el conmutador y no sobre la pantalla entera: mientras la
    // agenda fue pestaña, este archivo probaba su `href`. Si vuelve a colarse
    // —por un merge, o por alguien que "restaura" PESTANIAS_EQUIPOS— la pantalla
    // se llenaría de tarjetas por equipo al lado del armado, que es lo que la
    // separación en pestañas vino a sacar.
    render(<EquiposDeTrabajo />)
    await screen.findByText('Cuadrilla Norte')

    expect(screen.queryByRole('link', { name: /Agenda/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /agenda/ })).not.toBeInTheDocument()
    // El selector de día era el control propio de la agenda vieja: si aparece,
    // la agenda se está volviendo a dibujar acá aunque no tenga pestaña.
    expect(screen.queryByLabelText('Día')).not.toBeInTheDocument()
  })

  it('🔴 la pestaña de equipos no dibuja la flota', async () => {
    render(<EquiposDeTrabajo />)
    await screen.findByText('Sin vehículo asignado.')
    expect(screen.queryByText('Renault Kangoo')).not.toBeInTheDocument()
  })

  it('🔴 la pestaña de flota muestra sólo los vehículos', async () => {
    render(<Flota />)
    await screen.findByText('Renault Kangoo')
    expect(screen.queryByText('Sin vehículo asignado.')).not.toBeInTheDocument()
  })

  it('la pestaña activa se marca con aria-current, no sólo con color', async () => {
    render(<Flota />)
    await screen.findByText('Renault Kangoo')

    expect(pestania('Flota')).toHaveAttribute('aria-current', 'page')
    expect(pestania('Equipos de trabajo')).not.toHaveAttribute('aria-current')
  })

  it('el botón de alta es el de la pestaña que se está mirando', async () => {
    // Los dos botones siempre visibles ofrecerían dar de alta un vehículo desde
    // la pantalla de equipos, que no es lo que se vino a hacer ahí.
    render(<EquiposDeTrabajo />)
    await screen.findByText('Cuadrilla Norte')
    expect(screen.getByRole('button', { name: /Nuevo equipo/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Nuevo vehículo/ })).not.toBeInTheDocument()
  })

  it('la flota ofrece dar de alta un vehículo, no un equipo', async () => {
    render(<Flota />)
    await screen.findByText('Renault Kangoo')
    expect(screen.getByRole('button', { name: /Nuevo vehículo/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Nuevo equipo/ })).not.toBeInTheDocument()
  })
})

describe('Equipos de trabajo', () => {
  it('muestra el responsable, los integrantes y en qué sale', async () => {
    render(<EquiposDeTrabajo />)
    expect(await screen.findByText('Cuadrilla Norte')).toBeInTheDocument()
    expect(screen.getByText(/Responsable: Sofía Núñez/)).toBeInTheDocument()
    expect(screen.getByText('Diego Ramos')).toBeInTheDocument()
    // El vehículo asignado: es la respuesta al pedido.
    expect(screen.getByText('AB123CD')).toBeInTheDocument()
  })

  it('el equipo sin vehículo lo dice, no lo deja en blanco', async () => {
    render(<EquiposDeTrabajo />)
    await screen.findByText('Cuadrilla Sur')
    expect(screen.getByText('Sin vehículo asignado.')).toBeInTheDocument()
    expect(screen.getByText('Sin integrantes.')).toBeInTheDocument()
  })

  it('🔴 el selector de responsable ofrece sólo a quien tiene el rol', async () => {
    // Ofrecer el personal entero haría que el rol no quisiera decir nada — y el
    // backend rechaza a quien no lo tiene, así que sería ofrecer un 409.
    const user = userEvent.setup()
    render(<EquiposDeTrabajo />)
    await screen.findByText('Cuadrilla Norte')

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
    render(<EquiposDeTrabajo />)
    await screen.findByText('Cuadrilla Norte')

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
    render(<EquiposDeTrabajo />)
    await screen.findByText('Cuadrilla Sur')

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
    render(<EquiposDeTrabajo />)
    await screen.findByText('Cuadrilla Sur')

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
    render(<Flota />)
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
    render(<EquiposDeTrabajo />)
    await screen.findByText('Cuadrilla Norte')

    const boton = screen.getByRole('button', { name: /No hay vehículos libres/ })
    expect(boton).toBeDisabled()
  })

  it('desasignar sale desde la tarjeta del equipo', async () => {
    const user = userEvent.setup()
    render(<EquiposDeTrabajo />)
    await screen.findByText('Cuadrilla Norte')

    await user.click(screen.getByRole('button', { name: 'Desasignar AB123CD' }))

    await waitFor(() => {
      expect(pedidos.some((p) => p.url.includes('/vehiculos/10/desasignar'))).toBe(true)
    })
  })
})
