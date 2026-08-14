// De un reclamo cerrado al remito — el camino a facturación de un servicio.
//
// La bandeja de "Enviar a facturar" sólo acepta remitos, así que sin este botón
// un trabajo por servicio no tiene cómo llegar a facturarse. Lo que fijan estos
// tests es lo que el usuario ve, que es donde se rompe:
//
// - Que el botón **no aparezca** antes de tiempo: en el circuito real es al
//   cerrar cuando se decide si va a facturación.
// - Que una vez convertido deje de ofrecer generar y pase a llevar al remito.
//   Ofrecerlo de nuevo —aunque el servidor sea idempotente— le hace creer al
//   usuario que no se generó, y el remito emitido queda sin quién lo encuentre.
// - Que aterrice en el remito: nace con los precios en cero y hay que cargarlos.
import { render as renderRTL, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { IncidenciaDetalle } from '../pages/IncidenciaDetalle'

const navegado: string[] = []
vi.mock('react-router-dom', async () => {
  const real = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...real, useNavigate: () => (destino: string) => { navegado.push(destino) } }
})

const render = (ui: ReactElement) =>
  renderRTL(
    <MemoryRouter initialEntries={['/incidencias/1']}>
      <Routes>
        <Route path="/incidencias/:id" element={ui} />
      </Routes>
    </MemoryRouter>,
  )

const CLIENTE = {
  id: 1, nombre: 'Medici Neumatec', empresa: 'NEUMYSER SRL', email: null,
  telefono: null, ciudad: 'Chivilcoy', cuit: '30-11111111-7', domicilio: null,
  observaciones: null, tipo_facturacion: 'mensual', activo: true,
  fecha_creacion: null,
}

const BASE = {
  id: 1, cliente_id: 1, equipo_id: null, activo_id: null,
  tecnico_id: null, recepcionista_id: null, vendedor_id: null,
  modalidad: null, sector_id: null, categoria_id: null,
  fecha_programada: null, duracion_minutos: null, equipo_trabajo_id: null,
  titulo: 'Central sin tono', descripcion: null,
  nro_cds: null, reclamante: null,
  estado: 'abierto', prioridad: 'media',
  horas_invertidas: 2, notas: null, resolucion: null,
  estado_facturacion: null, remito_id: null, activo: true,
  fecha_creacion: '2026-08-13T10:00:00', fecha_cierre: null,
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let posts: string[]

function montar(incidencia: Record<string, unknown>) {
  posts = []
  navegado.length = 0
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    const metodo = opciones?.method ?? 'GET'

    if (metodo === 'POST' && u.includes('/convertir-en-remito')) {
      posts.push(u)
      return Promise.resolve(json({ id: 7, number: 'REM-00000007' }))
    }
    if (u.includes('/api/incidencias/1/actividades')) return Promise.resolve(json([]))
    if (u.includes('/api/incidencias/1/estados')) return Promise.resolve(json([]))
    if (u.includes('/api/incidencias/1/movimientos')) return Promise.resolve(json([]))
    if (u.includes('/api/incidencias/1')) return Promise.resolve(json(incidencia))
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    return Promise.resolve(json([]))
  }))
}

beforeEach(() => { posts = [] })

describe('generar el remito de un reclamo', () => {
  it('un reclamo abierto todavía no lo ofrece', async () => {
    montar(BASE)
    render(<IncidenciaDetalle />)
    await screen.findByDisplayValue('Central sin tono')

    expect(screen.queryByRole('button', { name: /Generar remito/i })).toBeNull()
  })

  it('un reclamo resuelto tampoco: falta el control del comprobante', async () => {
    // `resuelta` es el estado en el que el técnico ya terminó pero el papel
    // todavía no se controló contra la hoja de ruta. Es el caso donde un
    // "cerrado o resuelta" de más facturaría trabajo sin verificar.
    montar({ ...BASE, estado: 'resuelta' })
    render(<IncidenciaDetalle />)
    await screen.findByDisplayValue('Central sin tono')

    expect(screen.queryByRole('button', { name: /Generar remito/i })).toBeNull()
  })

  it('cerrado lo ofrece, y al tocarlo lleva al remito para ponerle precios', async () => {
    montar({ ...BASE, estado: 'cerrado', fecha_cierre: '2026-08-13T18:00:00' })
    render(<IncidenciaDetalle />)
    await screen.findByDisplayValue('Central sin tono')

    await userEvent.click(await screen.findByRole('button', { name: /Generar remito/i }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]).toContain('/api/incidencias/1/convertir-en-remito')
    // Aterriza en el remito: nace con los importes en cero y hay que cargarlos
    // antes de poder mandarlo a facturar.
    await waitFor(() => expect(navegado).toContain('/remitos/7'))
  })

  it('ya convertido deja de ofrecer generar y lleva al remito que existe', async () => {
    montar({ ...BASE, estado: 'cerrado', remito_id: 7 })
    render(<IncidenciaDetalle />)
    await screen.findByDisplayValue('Central sin tono')

    expect(screen.queryByRole('button', { name: /Generar remito/i })).toBeNull()
    const link = await screen.findByRole('link', { name: /Ver remito/i })
    expect(link).toHaveAttribute('href', '/remitos/7')
  })
})
