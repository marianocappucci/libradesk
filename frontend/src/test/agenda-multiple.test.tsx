// Armar una salida de cuadrilla desde la lista de reclamos (pedido del humano,
// 2026-08-15).
//
// Lo que estos tests fijan, en orden de lo que se rompe sin que se note:
//
// 1. 🔴 **El tilde ahora sirve para dos cosas opuestas.** Antes sólo aparecía en
//    los reclamos cerrados, para agruparlos en un remito. Ahora también en los
//    abiertos, para agendarlos — y la barra ofrece la acción que corresponde a
//    lo elegido, no las dos.
// 2. 🔴 **El orden tildado es el orden del recorrido**, y viaja así en el POST.
// 3. La previa muestra los horarios encadenados antes de guardar.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Incidencias } from '../pages/Incidencias'

const render = (ui: ReactElement) => renderRTL(<MemoryRouter>{ui}</MemoryRouter>)

const CLIENTE = { id: 1, nombre: 'Estudio Sur', activo: true }

function reclamo(id: number, titulo: string, estado: string, extra = {}) {
  return {
    id, cliente_id: 1, equipo_id: null, activo_id: null, tecnico_id: null,
    recepcionista_id: null, vendedor_id: null, modalidad: null,
    fecha_programada: null, duracion_minutos: null, equipo_trabajo_id: null,
    sector_id: null, categoria_id: null, titulo, descripcion: '',
    estado, prioridad: 'media', horas_invertidas: null, nro_cds: null,
    reclamante: null, remito_id: null, fecha_creacion: '2026-08-15T10:00:00',
    fecha_cierre: null, cobertura_abono: null, abono_horas_cubiertas: null,
    abono_materiales_incluidos: null, ...extra,
  }
}

// Dos abiertos (agendables) y uno cerrado sin remito (remitable). El resuelto
// no es ninguna de las dos cosas: es el control de que el tilde no aparece
// siempre.
const ABIERTO_1 = reclamo(11, 'No enciende el router', 'abierto')
const ABIERTO_2 = reclamo(12, 'Cambio de cableado', 'en_progreso')
const CERRADO = reclamo(13, 'Ya se hizo', 'cerrado')
const RESUELTO = reclamo(14, 'Resuelto sin cerrar', 'resuelta')

const CUADRILLAS = [
  {
    id: 5, nombre: 'Cuadrilla Norte', responsable_id: 1,
    responsable_nombre: 'Juan Pérez', observaciones: null, activo: true,
    created_at: null,
    integrantes: [{ id: 2, nombre: 'Ana Gómez' }],
    vehiculos: [{ id: 9, patente: 'AB123CD', marca: 'Renault', modelo: 'Kangoo' }],
  },
]

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let posts: { url: string; cuerpo: Record<string, unknown> }[] = []

beforeEach(() => {
  posts = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    if ((init?.method ?? 'GET') !== 'GET') {
      posts.push({ url: u, cuerpo: JSON.parse(String(init?.body ?? '{}')) })
      return Promise.resolve(json([]))
    }
    if (u.includes('/api/equipos-trabajo')) return Promise.resolve(json(CUADRILLAS))
    if (u.includes('/api/incidencias')) {
      return Promise.resolve(json([ABIERTO_1, ABIERTO_2, CERRADO, RESUELTO]))
    }
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    return Promise.resolve(json([]))
  }))
})

const tilde = (id: number) =>
  screen.getByRole('checkbox', { name: `Elegir el reclamo #${id}` })


describe('🔴 El tilde sirve para dos acciones opuestas', () => {
  it('los reclamos abiertos ahora se pueden tildar', async () => {
    // Antes el tilde sólo aparecía en los cerrados: agendar de a varios era
    // imposible desde acá.
    render(<Incidencias />)
    await screen.findByText('No enciende el router')

    expect(tilde(11)).toBeInTheDocument()
    expect(tilde(12)).toBeInTheDocument()
    // Y el cerrado lo sigue teniendo, para el remito.
    expect(tilde(13)).toBeInTheDocument()
  })

  it('🔴 un reclamo resuelto pero no cerrado no se puede tildar', async () => {
    // El control. Sin esto, mostrar el tilde en TODAS las filas pasaría el
    // test de arriba igual — y ofrecería un tilde que siempre termina en 409.
    render(<Incidencias />)
    await screen.findByText('Resuelto sin cerrar')

    expect(screen.queryByRole('checkbox', { name: 'Elegir el reclamo #14' }))
      .toBeNull()
  })

  it('con abiertos elegidos ofrece armar la salida, y NO generar remito', async () => {
    const user = userEvent.setup()
    render(<Incidencias />)
    await screen.findByText('No enciende el router')

    await user.click(tilde(11))

    expect(await screen.findByRole('button', { name: /Armar salida/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Generar remito/ })).toBeNull()
  })

  it('con un cerrado elegido ofrece el remito, y NO la salida', async () => {
    const user = userEvent.setup()
    render(<Incidencias />)
    await screen.findByText('Ya se hizo')

    await user.click(tilde(13))

    expect(await screen.findByRole('button', { name: /Generar remito/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Armar salida/ })).toBeNull()
  })

  it('🔴 mezclando abiertos y cerrados no ofrece ninguna, y dice por qué', async () => {
    // Un botón apagado sin motivo manda a adivinar; acá directamente no está,
    // y el texto explica que son dos cosas distintas.
    const user = userEvent.setup()
    render(<Incidencias />)
    await screen.findByText('No enciende el router')

    await user.click(tilde(11))
    await user.click(tilde(13))

    expect(screen.queryByRole('button', { name: /Armar salida/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Generar remito/ })).toBeNull()
    expect(screen.getByText(/cerrados y abiertos mezclados/)).toBeInTheDocument()
  })
})


describe('El diálogo de la salida', () => {
  async function abrir() {
    const user = userEvent.setup()
    render(<Incidencias />)
    await screen.findByText('No enciende el router')
    await user.click(tilde(11))
    await user.click(tilde(12))
    await user.click(screen.getByRole('button', { name: /Armar salida/ }))
    return { user, dialogo: await screen.findByRole('dialog', { name: 'Armar salida' }) }
  }

  it('muestra con qué vehículo y con quiénes sale la cuadrilla', async () => {
    // No son campos: son datos de la cuadrilla. Se muestran como confirmación
    // de lo que se está eligiendo, para no tener que ir a buscarlos.
    const { user, dialogo } = await abrir()

    await user.click(within(dialogo).getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: 'Cuadrilla Norte' }))

    expect(await within(dialogo).findByText(/AB123CD/)).toBeInTheDocument()
    expect(within(dialogo).getByText(/Juan Pérez/)).toBeInTheDocument()
    expect(within(dialogo).getByText(/Ana Gómez/)).toBeInTheDocument()
  })

  it('🔴 la previa encadena los horarios antes de guardar', async () => {
    // Se ve el recorrido con sus horas SIN haber escrito nada. Si esto no
    // estuviera, la única forma de saber a qué hora queda cada parada sería
    // guardar y mirar.
    const { dialogo } = await abrir()

    // 09:00 de arranque y 60 minutos por parada, que son los valores por
    // defecto del diálogo.
    expect(within(dialogo).getByText('09:00')).toBeInTheDocument()
    expect(within(dialogo).getByText('10:00')).toBeInTheDocument()
  })

  it('🔴 manda los reclamos en el orden tildado, con la cuadrilla y la hora', async () => {
    const { user, dialogo } = await abrir()

    await user.click(within(dialogo).getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: 'Cuadrilla Norte' }))
    await user.click(within(dialogo).getByRole('button', { name: /Agendar la salida/ }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toContain('/api/incidencias/agendar-salida')
    // El orden es el del recorrido: reordenar acá le cambiaría la ruta.
    expect(posts[0].cuerpo.incidencia_ids).toEqual([11, 12])
    expect(posts[0].cuerpo.equipo_trabajo_id).toBe(5)
    expect(String(posts[0].cuerpo.inicio)).toContain('T09:00:00')
    expect(posts[0].cuerpo.duracion_minutos).toBe(60)
  })

  it('sin cuadrilla elegida no deja agendar', async () => {
    const { dialogo } = await abrir()

    expect(within(dialogo).getByRole('button', { name: /Agendar la salida/ }))
      .toBeDisabled()
  })
})
