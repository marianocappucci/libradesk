// La agenda de los equipos (pedido 42, fase B).
//
// Lo que la pantalla tiene que dejar claro:
//
// 1. **Qué hace cada equipo y en qué sale** — las dos mitades del pedido juntas
//    y en la misma vista, que es lo que se mira a la mañana para despachar.
// 2. **Que la fecha del ticket sobreviva a editar cualquier otro campo.** El
//    PUT manda el objeto entero: un campo que no viaja vuelve a null, y el
//    ticket se desagenda solo. Es el defecto más caro de esta fase y no se ve
//    mirando la pantalla.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgendaEquipos } from '../components/agenda-equipos'
import { IncidenciaDetalle } from '../pages/IncidenciaDetalle'

const render = (ui: ReactElement) => renderRTL(<MemoryRouter>{ui}</MemoryRouter>)

/** El detalle lee el id de la ruta, así que necesita el `Routes` alrededor —
 *  sin él `useParams` devuelve undefined y la página pide `/api/incidencias/NaN`. */
const renderTicket = () =>
  renderRTL(
    <MemoryRouter initialEntries={['/incidencias/77']}>
      <Routes>
        <Route path="/incidencias/:id" element={<IncidenciaDetalle />} />
      </Routes>
    </MemoryRouter>,
  )

const KANGOO = {
  id: 10, patente: 'AB123CD', marca: 'Renault', modelo: 'Kangoo', anio: 2019,
  estado: 'asignado', equipo_id: 1, equipo_nombre: 'Cuadrilla Norte',
  descripcion: 'Renault Kangoo', observaciones: null, created_at: null,
}
const NORTE = {
  id: 1, nombre: 'Cuadrilla Norte', responsable_id: 1,
  responsable_nombre: 'Sofía Núñez', observaciones: null, activo: true,
  created_at: null, integrantes: [], vehiculos: [KANGOO],
}
const SUR = {
  ...NORTE, id: 2, nombre: 'Cuadrilla Sur', vehiculos: [],
  responsable_id: null, responsable_nombre: null,
}
const DE_BAJA = { ...SUR, id: 3, nombre: 'Cuadrilla Vieja', activo: false }

const TRABAJO = {
  incidencia_id: 77, titulo: 'Cambio de switch', cliente_id: 5,
  cliente_nombre: 'Estudio Sur',
  cliente_domicilio: 'Av. San Martín 1240', cliente_ciudad: 'Suipacha',
  estado: 'abierto', modalidad: 'on_site',
  desde: '2026-08-11T09:00:00', hasta: '2026-08-11T11:00:00',
  duracion_minutos: 120, vehiculos: ['AB123CD'],
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
    if (u.includes('/api/agenda/equipo/1')) return Promise.resolve(json([TRABAJO]))
    if (u.includes('/api/agenda/equipo/')) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  }))
})

describe('Agenda del día', () => {
  it('muestra el horario, el trabajo y en qué sale el equipo', async () => {
    render(<AgendaEquipos equipos={[NORTE, SUR]} />)

    const norte = (await screen.findByText('Cuadrilla Norte'))
      .closest('[data-slot="card"]') as HTMLElement
    expect(within(norte).getByText('AB123CD')).toBeInTheDocument()
    expect(within(norte).getByText('09:00–11:00')).toBeInTheDocument()
    expect(within(norte).getByText('Cambio de switch')).toBeInTheDocument()
    expect(within(norte).getByText('Estudio Sur')).toBeInTheDocument()
    expect(within(norte).getByText('On-site')).toBeInTheDocument()
  })

  it('el trabajo linkea al ticket', async () => {
    render(<AgendaEquipos equipos={[NORTE]} />)
    const link = await screen.findByRole('link', { name: 'Cambio de switch' })
    expect(link).toHaveAttribute('href', '/incidencias/77')
  })

  it('un equipo sin nada ese día lo dice, no queda en blanco', async () => {
    render(<AgendaEquipos equipos={[NORTE, SUR]} />)
    expect(await screen.findByText('Sin trabajos ese día.')).toBeInTheDocument()
  })

  it('no pide la agenda de un equipo dado de baja', async () => {
    render(<AgendaEquipos equipos={[NORTE, DE_BAJA]} />)
    await screen.findByText('Cambio de switch')

    expect(screen.queryByText('Cuadrilla Vieja')).not.toBeInTheDocument()
    expect(pedidos.some((p) => p.url.includes('/api/agenda/equipo/3'))).toBe(false)
  })

  it('cambiar el día vuelve a pedir la agenda de ese día', async () => {
    const user = userEvent.setup()
    render(<AgendaEquipos equipos={[NORTE]} />)
    await screen.findByText('Cambio de switch')

    await user.clear(screen.getByLabelText('Día'))
    await user.type(screen.getByLabelText('Día'), '2026-12-24')

    await waitFor(() => {
      expect(pedidos.some((p) => p.url.includes('desde=2026-12-24'))).toBe(true)
    })
  })

  it('muestra el domicilio del cliente, que es lo que ordena el recorrido', async () => {
    render(<AgendaEquipos equipos={[NORTE]} />)
    expect(await screen.findByText('Av. San Martín 1240, Suipacha')).toBeInTheDocument()
  })

  it('no repite la ciudad si ya viene adentro del domicilio', async () => {
    // Se vio en la demo desplegada: los clientes reales cargan la ciudad
    // adentro del domicilio Y en su propio campo, y la pantalla decía
    // "Av. Pueyrredón 1640, CABA, CABA".
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json([{
      ...TRABAJO,
      cliente_domicilio: 'Av. Pueyrredón 1640, CABA', cliente_ciudad: 'CABA',
    }]))))
    render(<AgendaEquipos equipos={[NORTE]} />)
    expect(await screen.findByText('Av. Pueyrredón 1640, CABA')).toBeInTheDocument()
    expect(screen.queryByText(/CABA, CABA/)).not.toBeInTheDocument()
  })

  it('un trabajo sin domicilio no deja un renglón vacío', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json([{
      ...TRABAJO, cliente_domicilio: null, cliente_ciudad: null,
    }]))))
    render(<AgendaEquipos equipos={[NORTE]} />)
    await screen.findByText('Cambio de switch')
    // El nombre del cliente sigue estando; lo que no tiene que aparecer es la
    // segunda línea con una coma suelta o un guión.
    expect(screen.getByText('Estudio Sur')).toBeInTheDocument()
    expect(screen.queryByText(', ')).not.toBeInTheDocument()
  })

  it('el botón de hoja de ruta apunta al equipo y al día que se está mirando', async () => {
    // El día sale del selector, no de `hoy`: la hoja se imprime la noche
    // anterior tanto como a la mañana. Con un `hoy` hardcodeado este test
    // pasaría igual, así que abajo se cambia el día y se vuelve a mirar.
    const user = userEvent.setup()
    render(<AgendaEquipos equipos={[NORTE]} />)
    await screen.findByText('Cambio de switch')

    const boton = screen.getByRole('link', { name: /hoja de ruta/i })
    expect(boton).toHaveAttribute(
      'href', expect.stringContaining('/api/agenda/equipo/1/hoja-de-ruta'),
    )

    await user.clear(screen.getByLabelText('Día'))
    await user.type(screen.getByLabelText('Día'), '2026-12-24')

    await waitFor(() => {
      expect(screen.getByRole('link', { name: /hoja de ruta/i }))
        .toHaveAttribute('href', '/api/agenda/equipo/1/hoja-de-ruta?dia=2026-12-24')
    })
  })

  it('cada equipo tiene la suya: son salidas distintas', async () => {
    render(<AgendaEquipos equipos={[NORTE, SUR]} />)
    await screen.findByText('Cambio de switch')

    const enlaces = screen.getAllByRole('link', { name: /hoja de ruta/i })
      .map((a) => a.getAttribute('href'))
    expect(enlaces.some((h) => h?.includes('/equipo/1/'))).toBe(true)
    expect(enlaces.some((h) => h?.includes('/equipo/2/'))).toBe(true)
  })

  it('abre en el día de hoy en hora local, no en UTC', async () => {
    // A las 22:00 de Argentina `toISOString()` ya es el día siguiente. Si la
    // agenda abriera en UTC, media tarde mostraría el día equivocado.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date('2026-08-11T22:30:00-03:00'))
    try {
      render(<AgendaEquipos equipos={[NORTE]} />)
      await waitFor(() => {
        expect(pedidos.some((p) => p.url.includes('desde=2026-08-11'))).toBe(true)
      })
    } finally {
      vi.useRealTimers()
    }
  })
})

// --- la fecha en el ticket -------------------------------------------------

const INCIDENCIA = {
  id: 77, cliente_id: 5, equipo_id: null, activo_id: null, tecnico_id: null,
  recepcionista_id: null, vendedor_id: null, modalidad: 'on_site',
  sector_id: null, categoria_id: null,
  fecha_programada: '2026-08-11T09:00:00', duracion_minutos: 120,
  equipo_trabajo_id: 1,
  titulo: 'Cambio de switch', descripcion: null, estado: 'abierto',
  prioridad: 'media', horas_invertidas: null, notas: null, resolucion: null,
  estado_facturacion: null, activo: true, fecha_creacion: '2026-08-10T10:00:00',
  fecha_cierre: null,
}

function stubTicket() {
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    const metodo = opciones?.method ?? 'GET'
    pedidos.push({
      url: u, metodo,
      cuerpo: opciones?.body ? JSON.parse(String(opciones.body)) : null,
    })
    if (metodo === 'PUT') return Promise.resolve(json(INCIDENCIA))
    if (metodo !== 'GET') return Promise.resolve(json({ ok: true }))
    if (u.includes('/api/incidencias/77/')) return Promise.resolve(json([]))
    if (u.includes('/api/incidencias/77')) return Promise.resolve(json(INCIDENCIA))
    if (u.includes('/api/equipos-trabajo')) return Promise.resolve(json([NORTE, SUR]))
    if (u.includes('/api/clientes')) {
      return Promise.resolve(json([{
        id: 5, nombre: 'Estudio Sur', empresa: null, email: null, telefono: null,
        ciudad: null, cuit: null, domicilio: null, observaciones: null,
        tipo_facturacion: 'mensual', activo: true, fecha_creacion: null,
      }]))
    }
    return Promise.resolve(json([]))
  }))
}

describe('Agendar desde el ticket', () => {
  beforeEach(stubTicket)

  it('muestra la fecha guardada y en qué vehículo sale el equipo elegido', async () => {
    renderTicket()
    await waitFor(() => {
      expect(screen.getByLabelText('Fecha y hora del trabajo'))
        .toHaveValue('2026-08-11T09:00')
    })
    expect(screen.getByLabelText('Duración (minutos)')).toHaveValue(120)
    expect(screen.getByText(/Sale en AB123CD/)).toBeInTheDocument()
  })

  it('editar otro campo NO desagenda el ticket', async () => {
    // El PUT lleva el objeto entero. Si los tres campos de agenda no viajan,
    // tocar las horas invertidas le borra la fecha al ticket sin que nadie lo
    // note hasta que el trabajo desaparece de la agenda.
    const user = userEvent.setup()
    renderTicket()
    await waitFor(() => {
      expect(screen.getByLabelText('Fecha y hora del trabajo')).toBeInTheDocument()
    })

    // Horas invertidas guarda `onBlur`, no `onChange` — sin el `tab()` el PUT
    // no sale nunca y el test pasaría por no haber medido nada.
    await user.type(screen.getByLabelText('Horas invertidas'), '2')
    await user.tab()

    await waitFor(() => {
      const put = pedidos.find((p) => p.metodo === 'PUT')
      expect(put).toBeDefined()
      expect(put!.cuerpo).toMatchObject({
        fecha_programada: '2026-08-11T09:00:00',
        duracion_minutos: 120,
        equipo_trabajo_id: 1,
      })
    })
  })

  it('vaciar la fecha desagenda: manda null, no un string vacío', async () => {
    const user = userEvent.setup()
    renderTicket()
    await waitFor(() => {
      expect(screen.getByLabelText('Fecha y hora del trabajo')).toBeInTheDocument()
    })

    await user.clear(screen.getByLabelText('Fecha y hora del trabajo'))

    await waitFor(() => {
      const put = pedidos.find((p) => p.metodo === 'PUT')
      expect(put).toBeDefined()
      expect((put!.cuerpo as Record<string, unknown>).fecha_programada).toBeNull()
    })
  })
})
