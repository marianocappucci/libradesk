// De un reclamo cerrado al remito — y **por qué este archivo dice ahora lo
// contrario que antes**.
//
// Hasta el 2026-09-09 había TRES puertas para convertir un reclamo en remito: un
// botón en la ficha, otro en la grilla, y el endpoint de a varios. El humano
// decidió dejar **una sola**: se arma desde "Nuevo remito", eligiendo el cliente
// y trayendo sus reclamos cerrados.
//
// 🔑 **La diferencia no es dónde está el botón.** Por los caminos viejos el
// remito salía **ya emitido** con lo que el sistema decidía, y corregirlo era
// editar un comprobante hecho. Por el nuevo, los renglones entran al **borrador**
// y se editan antes de emitir — que es como Lagrace arma la pre-factura.
//
// Lo que estos tests custodian ahora es que las puertas viejas **no vuelvan**:
// una que reaparezca es un segundo camino que puede facturar distinto, y este
// producto ya pagó ese error. Lo que sí se conserva —y tiene su test— es
// **"Ver remito"**, que no es una puerta sino la forma de llegar a lo emitido.
import { render as renderRTL, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { IncidenciaDetalle } from '../pages/IncidenciaDetalle'
import { Incidencias } from '../pages/Incidencias'

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

  it('🔴 un reclamo CERRADO tampoco lo ofrece: la puerta se cerró', async () => {
    // Antes este test afirmaba lo contrario —que cerrado sí lo ofrecía y
    // llevaba al remito—. Se dio vuelta el 2026-09-09 con la decisión de dejar
    // una sola puerta. Si vuelve a aparecer, hay dos caminos otra vez.
    montar({ ...BASE, estado: 'cerrado', fecha_cierre: '2026-08-13T18:00:00' })
    render(<IncidenciaDetalle />)
    await screen.findByDisplayValue('Central sin tono')

    expect(screen.queryByRole('button', { name: /Generar remito/i })).toBeNull()
    // Y no manda nada: no es que el botón esté escondido y el POST igual salga.
    expect(posts).toHaveLength(0)
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


// ── Varios reclamos, un solo remito ──────────────────────────────────────
//
// El caso que motiva todo: tres visitas a un cliente en el mes, una sola
// factura. Lo que se rompe en pantalla y estos tests fijan:
//
// - Que el tilde **no se ofrezca** en un reclamo que no se puede remitar: un
//   checkbox que siempre termina en 409 es peor que no tenerlo.
// - Que no se pueda armar un remito con reclamos de dos clientes, **y que se
//   vea por qué**: un botón apagado sin motivo manda a adivinar.
// - Que tildar no navegue a la ficha. El `onRowClick` de la tabla sólo ignora
//   los clicks sobre `button` y `a`, así que sin `stopPropagation` tildar se
//   llevaría puesta la selección entera.

const OTRO_CLIENTE = { ...CLIENTE, id: 2, nombre: 'Otro', empresa: 'OTRA SRL' }
const CERRADO = { ...BASE, estado: 'cerrado', fecha_cierre: '2026-08-13T18:00:00' }

let enviado: { url: string; body: unknown } | null = null

function montarGrilla(incidencias: Record<string, unknown>[]) {
  enviado = null
  navegado.length = 0
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    if ((opciones?.method ?? 'GET') === 'POST' && u.includes('/convertir-en-remito')) {
      enviado = { url: u, body: JSON.parse(String(opciones?.body ?? '{}')) }
      return Promise.resolve(json({ id: 7, number: 'REM-00000007' }))
    }
    if (u.includes('/api/incidencias')) return Promise.resolve(json(incidencias))
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE, OTRO_CLIENTE]))
    return Promise.resolve(json([]))
  }))
}

// Anclado al final (`$`) y sin el espacio: el `aria-label` decía «…#1 para el
// remito» y desde el 2026-08-15 dice «Elegir el reclamo #1» a secas, porque el
// tilde dejó de ser sólo para remitos — con reclamos abiertos arma una salida
// de cuadrilla.
const tilde = (id: number) =>
  screen.queryByRole('checkbox', { name: new RegExp(`reclamo #${id}$`, 'i') })

describe('🔴 la grilla ya no genera el remito', () => {
  it('un reclamo cerrado sin facturar ya no se puede tildar', async () => {
    // El tilde servía para dos acciones opuestas: agendar los abiertos y
    // remitar los cerrados. Con el remito fuera, tildar un cerrado no haría
    // nada — y un control que se deja apretar y no lleva a ninguna acción es
    // peor que no ofrecerlo.
    montarGrilla([
      { ...CERRADO, id: 1 },
      { ...BASE, id: 2, titulo: 'Todavía abierto' },
    ])
    renderRTL(<MemoryRouter><Incidencias /></MemoryRouter>)
    await screen.findByText('Todavía abierto')

    expect(tilde(1)).toBeNull()
    // El abierto sí: es lo que se elige para armar la salida de cuadrilla.
    expect(tilde(2)).not.toBeNull()
  })

  it('con un cerrado elegido no ofrece ningún botón de remito', async () => {
    montarGrilla([{ ...BASE, id: 2, titulo: 'Todavía abierto' }])
    renderRTL(<MemoryRouter><Incidencias /></MemoryRouter>)
    await screen.findByText('Todavía abierto')

    await userEvent.click(tilde(2)!)

    expect(screen.queryByRole('button', { name: /Generar remito/i })).toBeNull()
    // La otra mitad del tilde sigue viva, y es lo que no había que romper.
    expect(screen.getByRole('button', { name: /Armar salida/i })).toBeTruthy()
    expect(enviado).toBeNull()
  })
})
