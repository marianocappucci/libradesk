// Bloque de incidencias: pedidos 38, 40 y 41 (2026-08-04).
//
// Los tres son de pantalla, así que los tests afirman lo que el usuario ve:
//
// - **40** era un defecto: la ficha guardaba sola al perder el foco y no había
//   ni forma de saberlo ni forma de terminar. Se afirma que el botón existe,
//   que el indicador aparece y —lo que importa— que al volver **espera** a que
//   el guardado termine. Sin eso, lo último tipeado se pierde.
// - **38** — poder cargar el equipo sin abandonar el alta del ticket, y que
//   quede elegido.
// - **41** — cada selector ofrece sólo a quien tiene ese rol.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MODALIDAD_LABELS } from '../api'
import { IncidenciaDetalle } from '../pages/IncidenciaDetalle'
import { Incidencias } from '../pages/Incidencias'

const navegado: string[] = []
vi.mock('react-router-dom', async () => {
  const real = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...real, useNavigate: () => (destino: string) => { navegado.push(destino) } }
})

const render = (ui: ReactElement, ruta = '/incidencias/1') =>
  renderRTL(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/incidencias/:id" element={ui} />
        <Route path="/incidencias" element={ui} />
      </Routes>
    </MemoryRouter>,
  )

const CLIENTE = {
  id: 1, nombre: 'Estudio Sur', empresa: null, email: null, telefono: null,
  ciudad: null, cuit: null, domicilio: null, observaciones: null,
  tipo_facturacion: 'mensual', activo: true, fecha_creacion: null,
}

// Ana ejecuta y vende; Beto sólo recepciona. Es el caso que descarta un campo
// `rol` único.
const ANA = {
  id: 1, nombre: 'Ana', activo: true,
  es_tecnico: true, es_recepcionista: false, es_vendedor: true,
  roles: ['tecnico', 'vendedor'],
}
const BETO = {
  id: 2, nombre: 'Beto', activo: true,
  es_tecnico: false, es_recepcionista: true, es_vendedor: false,
  roles: ['recepcionista'],
}

const EQUIPO = {
  id: 5, cliente_id: 1, tipo: 'Notebook', modelo: 'T14', marca: 'Lenovo',
  serial: 'LN-1', ubicacion_oficina: null, sector: null, deposito_id: null,
  estado: 'activo', fecha_adicion: null, garantia_vence: null, observaciones: null,
}

const INCIDENCIA = {
  id: 1, cliente_id: 1, equipo_id: 5, activo_id: null,
  tecnico_id: null, recepcionista_id: null, vendedor_id: null,
  modalidad: null, sector_id: null, categoria_id: null,
  titulo: 'No arranca', descripcion: null, estado: 'abierto', prioridad: 'media',
  horas_invertidas: null, notas: null, resolucion: null,
  estado_facturacion: null, activo: true,
  fecha_creacion: '2026-08-04T10:00:00', fecha_cierre: null,
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let puts = 0
let resolverPut: (() => void) | null = null

beforeEach(() => {
  navegado.length = 0
  puts = 0
  resolverPut = null
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    const metodo = opciones?.method ?? 'GET'

    if (metodo === 'PUT' && u.includes('/api/incidencias/1')) {
      puts += 1
      // Un PUT que NO resuelve solo: así se puede probar que "Guardar y
      // volver" espera en vez de navegar con el guardado en vuelo.
      return new Promise<Response>((resolve) => {
        resolverPut = () => resolve(json({ ...INCIDENCIA, titulo: 'editado' }))
      })
    }
    if (metodo === 'POST' && u.includes('/api/equipos')) {
      return Promise.resolve(json({ ...EQUIPO, id: 9, tipo: 'Impresora', marca: 'HP' }))
    }
    if (u.includes('/api/incidencias/1/actividades')) return Promise.resolve(json([]))
    if (u.includes('/api/incidencias/1/estados')) return Promise.resolve(json([]))
    if (u.includes('/api/incidencias/1/movimientos')) return Promise.resolve(json([]))
    if (u.includes('/api/incidencias/1')) return Promise.resolve(json(INCIDENCIA))
    if (u.includes('/api/incidencias')) return Promise.resolve(json([INCIDENCIA]))
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    if (u.includes('/api/equipos')) return Promise.resolve(json([EQUIPO]))
    if (u.includes('/api/tecnicos')) return Promise.resolve(json([ANA, BETO]))
    return Promise.resolve(json([]))
  }))
})

describe('Ficha de la incidencia — el botón que faltaba (pedido 40)', () => {
  it('el guardado automático deja de ser invisible', async () => {
    render(<IncidenciaDetalle />)
    // Antes no había ninguna señal de que lo tipeado quedaba guardado.
    expect(await screen.findByText(/se guardan solos/i)).toBeInTheDocument()
  })

  it('hay un botón que guarda y vuelve al listado', async () => {
    const user = userEvent.setup()
    render(<IncidenciaDetalle />)
    await screen.findByText(/se guardan solos/i)

    await user.click(screen.getByRole('button', { name: /Guardar y volver/ }))

    await waitFor(() => expect(navegado).toContain('/incidencias'))
  })

  it('🔴 el botón no se deshabilita solo al tocarlo', async () => {
    // El click hace blur en el campo editado → arranca el guardado →
    // `guardando` pasa a true. Con `disabled={guardando}` el botón quedaba
    // deshabilitado ANTES de que llegara el click, y el handler no corría
    // nunca: se rompía justo en el caso para el que existe.
    const user = userEvent.setup()
    render(<IncidenciaDetalle />)
    await screen.findByText(/se guardan solos/i)

    const titulo = screen.getByDisplayValue('No arranca')
    await user.clear(titulo)
    await user.type(titulo, 'Otro')
    await user.click(screen.getByRole('button', { name: /Guardar/ }))

    await waitFor(() => expect(puts).toBe(1))
    resolverPut?.()
    await waitFor(() => expect(navegado).toContain('/incidencias'))
  })

  it('🔴 espera a que termine el guardado antes de irse', async () => {
    // El caso que motivó el pedido: se tipea, se toca el botón, y lo último
    // escrito tiene que llegar. Si navegara sin esperar, el PUT quedaría a
    // mitad de camino sobre un componente ya desmontado.
    const user = userEvent.setup()
    render(<IncidenciaDetalle />)
    await screen.findByText(/se guardan solos/i)

    const titulo = screen.getByDisplayValue('No arranca')
    await user.clear(titulo)
    await user.type(titulo, 'Otro título')

    await user.click(screen.getByRole('button', { name: /Guardar/ }))

    // El blur del campo disparó el PUT…
    await waitFor(() => expect(puts).toBe(1))
    // …y todavía NO navegó, porque el PUT sigue en vuelo.
    expect(navegado).not.toContain('/incidencias')

    resolverPut?.()
    await waitFor(() => expect(navegado).toContain('/incidencias'))
  })

  it('ofrece imprimir el ticket (pedido 39)', async () => {
    render(<IncidenciaDetalle />)
    const imprimir = await screen.findByRole('link', { name: /Imprimir/ })
    expect(imprimir).toHaveAttribute('href', '/api/incidencias/1/pdf')
  })
})

describe('Ficha de la incidencia — los tres papeles (pedido 41)', () => {
  it('cada selector ofrece sólo a quien tiene ese rol', async () => {
    const user = userEvent.setup()
    render(<IncidenciaDetalle />)
    await screen.findByText(/se guardan solos/i)

    // Recepcionista: Beto sí, Ana no.
    await user.click(screen.getByRole('combobox', { name: 'Recepcionó' }))
    expect(await screen.findByText('Beto')).toBeInTheDocument()
    expect(screen.queryByText('Ana')).not.toBeInTheDocument()
    await user.keyboard('{Escape}')

    // Vendedor: al revés. Ofrecer el personal entero en los tres dejaría la
    // pregunta "quién lo ejecutó" sin contestar.
    await user.click(screen.getByRole('combobox', { name: 'Vendedor' }))
    expect(await screen.findByText('Ana')).toBeInTheDocument()
    expect(screen.queryByText('Beto')).not.toBeInTheDocument()
  })

  it('ofrece la modalidad, y un ticket viejo la muestra sin definir (pedido 37)', async () => {
    render(<IncidenciaDetalle />)
    await screen.findByText(/se guardan solos/i)

    // No se abre el desplegable: el Select de Radix monta las opciones en un
    // portal que jsdom no llega a montar sin polyfills de pointer capture, y
    // pelearse con eso probaría la librería, no el pedido.
    //
    // Lo que sí importa afirmar es que el campo existe y que un ticket sin
    // modalidad —los 23 que ya había— se muestra como **Sin definir** y no
    // como on-site, que sería inventar el dato.
    const modalidad = screen.getByRole('combobox', { name: 'Modalidad' })
    expect(modalidad).toHaveTextContent('Sin definir')
    expect(MODALIDAD_LABELS).toEqual({ on_site: 'On-site', remoto: 'Remoto' })
  })
})

describe('Alta de incidencia — cargar el equipo ahí mismo (pedido 38)', () => {
  it('el atajo aparece recién con un cliente elegido', async () => {
    const user = userEvent.setup()
    render(<Incidencias />, '/incidencias')
    await screen.findByText('No arranca')

    await user.click(screen.getByRole('button', { name: /Nueva incidencia/ }))

    // Sin cliente no se puede: el equipo se carga en el parque de alguien.
    const atajo = await screen.findByRole('button', { name: /Elegí un cliente/ })
    expect(atajo).toBeDisabled()
  })

  it('el equipo creado queda elegido, sin salir del alta', async () => {
    const user = userEvent.setup()
    render(<Incidencias />, '/incidencias')
    await screen.findByText('No arranca')
    await user.click(screen.getByRole('button', { name: /Nueva incidencia/ }))

    // Dentro del diálogo del alta: "Estudio Sur" también aparece en el filtro
    // de la pantalla de atrás, así que una búsqueda global encuentra dos.
    const alta = await screen.findByRole('dialog', { name: /Nueva incidencia/ })
    await user.click(within(alta).getByRole('combobox', { name: 'Cliente' }))
    await user.click(await within(alta).findByText('Estudio Sur'))

    await user.click(await screen.findByRole('button', { name: /no está en la lista/ }))

    const dialogo = await screen.findByRole('dialog', { name: /Nuevo equipo/ })
    // Por el placeholder: los cuatro inputs del diálogo son textboxes sin
    // label asociado, así que buscar por rol encuentra los cuatro.
    //
    // Se pega en vez de teclear: este test abre DOS diálogos anidados sobre el
    // listado, así que cada tecla vuelve a renderizar todo eso. Es el más caro
    // de la suite y el que quedó al borde del timeout de 5 s cuando entró la
    // pantalla de stock (de ~2,1 s a ~4,4 s sin que nadie lo tocara).
    await user.click(within(dialogo).getByPlaceholderText(/Notebook, Impresora/))
    await user.paste('Impresora')
    await user.click(within(dialogo).getByRole('button', { name: /Crear y elegir/ }))

    // Vuelve al alta del ticket con el equipo nuevo puesto — que es la mitad
    // del problema que el atajo viene a sacar.
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: /Nuevo equipo/ })).not.toBeInTheDocument()
    })
    expect(await screen.findByText(/Impresora HP/)).toBeInTheDocument()
  })
})
