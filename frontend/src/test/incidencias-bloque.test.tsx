// Bloque de incidencias: pedidos 38, 40 y 41 (2026-08-04).
//
// Los tres son de pantalla, así que los tests afirman lo que el usuario ve:
//
// - **40** era un defecto: la ficha guardaba sola al perder el foco y no había
//   ni forma de saberlo ni forma de terminar. Se afirma que el botón existe,
//   que el indicador aparece y —lo que importa— que al volver **espera** a que
//   el guardado termine. Sin eso, lo último tipeado se pierde.
// - **38** — poder cargar el equipo sin abandonar el alta del ticket, y que
//   quede elegido. 🔴 **Retirado el 2026-09-13**: el alta dejó de ofrecer
//   equipo (se asigna después, desde la ficha) y en su lugar entra "Quién hizo
//   el reclamo". El describe de ese pedido se reemplazó por uno que afirma
//   justamente eso — ver "Alta de reclamo — sin equipo, con quién hizo el
//   reclamo" más abajo.
// - **41** — cada selector ofrece sólo a quien tiene ese rol.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MODALIDAD_LABELS } from '../api'
import { IncidenciaDetalle } from '../pages/IncidenciaDetalle'
import { Incidencias } from '../pages/Incidencias'
import { escribirEn } from './escribir'

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
// El body del POST de alta, para afirmar qué viaja al crear un reclamo
// (pedido del usuario, 2026-09-13: sin equipo, con `reclamante`).
let postBody: Record<string, unknown> | null = null

beforeEach(() => {
  navegado.length = 0
  puts = 0
  resolverPut = null
  postBody = null
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
    if (metodo === 'POST' && u.endsWith('/api/incidencias')) {
      postBody = opciones?.body ? JSON.parse(String(opciones.body)) : null
      return Promise.resolve(json({ ...INCIDENCIA, id: 2 }))
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

    await waitFor(() => expect(navegado).toContain('/reclamos'))
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
    // El `click` es parte del caso, no adorno: lo que dispara el guardado es el
    // **blur** del campo, y `escribirEn` cambia el valor sin enfocar. Sin foco
    // previo no habría blur y el PUT nunca saldría.
    await user.click(titulo)
    await escribirEn(titulo, 'Otro')
    await user.click(screen.getByRole('button', { name: /Guardar/ }))

    await waitFor(() => expect(puts).toBe(1))
    resolverPut?.()
    await waitFor(() => expect(navegado).toContain('/reclamos'))
  })

  it('🔴 espera a que termine el guardado antes de irse', async () => {
    // El caso que motivó el pedido: se tipea, se toca el botón, y lo último
    // escrito tiene que llegar. Si navegara sin esperar, el PUT quedaría a
    // mitad de camino sobre un componente ya desmontado.
    const user = userEvent.setup()
    render(<IncidenciaDetalle />)
    await screen.findByText(/se guardan solos/i)

    const titulo = screen.getByDisplayValue('No arranca')
    await user.click(titulo)
    await escribirEn(titulo, 'Otro título')

    await user.click(screen.getByRole('button', { name: /Guardar/ }))

    // El blur del campo disparó el PUT…
    await waitFor(() => expect(puts).toBe(1))
    // …y todavía NO navegó, porque el PUT sigue en vuelo.
    expect(navegado).not.toContain('/reclamos')

    resolverPut?.()
    await waitFor(() => expect(navegado).toContain('/reclamos'))
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

describe('Alta de reclamo — sin equipo, con quién hizo el reclamo (decisión del usuario, 2026-09-13)', () => {
  it('el modal ya no ofrece elegir ni cargar un equipo', async () => {
    const user = userEvent.setup()
    render(<Incidencias />, '/incidencias')
    await screen.findByText('No arranca')

    await user.click(screen.getByRole('button', { name: /Nuevo reclamo/ }))
    const alta = await screen.findByRole('dialog', { name: /Nuevo reclamo/ })

    // El campo desapareció, y con él el atajo del pedido 38 que lo cargaba
    // ahí mismo. El equipo se sigue asignando — pero desde la ficha de
    // detalle, no acá.
    expect(within(alta).queryByRole('combobox', { name: 'Equipo' })).not.toBeInTheDocument()
    expect(within(alta).queryByRole('button', { name: /no está en la lista/ })).not.toBeInTheDocument()
  })

  it('tiene "Quién hizo el reclamo", texto libre y opcional', async () => {
    const user = userEvent.setup()
    render(<Incidencias />, '/incidencias')
    await screen.findByText('No arranca')

    await user.click(screen.getByRole('button', { name: /Nuevo reclamo/ }))
    const alta = await screen.findByRole('dialog', { name: /Nuevo reclamo/ })

    expect(within(alta).getByLabelText('Quién hizo el reclamo')).toBeInTheDocument()
  })

  it('"quién hizo el reclamo" viaja en el POST del alta', async () => {
    const user = userEvent.setup()
    render(<Incidencias />, '/incidencias')
    await screen.findByText('No arranca')

    await user.click(screen.getByRole('button', { name: /Nuevo reclamo/ }))
    const alta = await screen.findByRole('dialog', { name: /Nuevo reclamo/ })

    await user.click(within(alta).getByRole('combobox', { name: 'Cliente' }))
    await user.click(await within(alta).findByText('Estudio Sur'))
    await escribirEn(within(alta).getByLabelText('Título'), 'No prende')
    await escribirEn(within(alta).getByLabelText('Quién hizo el reclamo'), 'Juana Pérez')

    await user.click(within(alta).getByRole('button', { name: /Crear reclamo/ }))

    await waitFor(() => expect(postBody).not.toBeNull())
    expect(postBody).toMatchObject({ reclamante: 'Juana Pérez', equipo_id: null })
  })

  it('sin nada tipeado, "reclamante" viaja null y no una cadena vacía', async () => {
    const user = userEvent.setup()
    render(<Incidencias />, '/incidencias')
    await screen.findByText('No arranca')

    await user.click(screen.getByRole('button', { name: /Nuevo reclamo/ }))
    const alta = await screen.findByRole('dialog', { name: /Nuevo reclamo/ })

    await user.click(within(alta).getByRole('combobox', { name: 'Cliente' }))
    await user.click(await within(alta).findByText('Estudio Sur'))
    await escribirEn(within(alta).getByLabelText('Título'), 'No prende')

    await user.click(within(alta).getByRole('button', { name: /Crear reclamo/ }))

    await waitFor(() => expect(postBody).not.toBeNull())
    expect(postBody?.reclamante).toBeNull()
  })
})

// La píldora de Estado lleva el color del semáforo (pedido del usuario,
// 2026-08-13). Antes "Abierto" y "En progreso" salían las dos con el mismo
// contorno gris, y el color de la fila vivía sólo en el punto de la primera
// columna, lejos de la palabra que significa lo mismo.
//
// 🔴 **Estos tests miran el TONO, no color renderizado.** En jsdom no hay hoja
// de Tailwind: el estilo computado devolvería el default para las cuatro, así
// que un test sobre color pasaría en verde con las cuatro píldoras iguales. Lo
// que se puede fijar acá es que cada estado resuelve a SU tono y que los cuatro
// son distintos. El color de verdad se verificó midiendo estilo computado en el
// navegador, que es donde el CSS existe.
//
// Se afirma `data-tono` y no el nombre de la clase: desde el 2026-08-21 la
// píldora la pinta `BadgeEstado` de libra-ui, y atar el test a `bg-red-50` lo
// rompe cada vez que cambia el criterio visual sin que la grilla deje de
// distinguir nada — que es exactamente lo que pasó.
describe('El estado se lee por color, no sólo por texto', () => {
  const POR_ESTADO = [
    { estado: 'abierto', label: 'Abierto', tono: 'negativo' },
    { estado: 'en_progreso', label: 'En progreso', tono: 'atencion' },
    { estado: 'resuelta', label: 'Resuelta', tono: 'ok' },
    { estado: 'cerrado', label: 'Cerrado', tono: 'neutro' },
  ]

  function conCuatroEstados() {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url)
      if (u.includes('/api/incidencias')) {
        return Promise.resolve(json(POR_ESTADO.map((e, i) => ({
          ...INCIDENCIA, id: i + 1, titulo: `Ticket ${i + 1}`, estado: e.estado,
        }))))
      }
      if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
      if (u.includes('/api/equipos')) return Promise.resolve(json([EQUIPO]))
      return Promise.resolve(json([]))
    }))
  }

  it('cada estado pinta su propia píldora, con el tono que le corresponde', async () => {
    conCuatroEstados()
    render(<Incidencias />, '/incidencias')
    await screen.findByText('Ticket 1')

    for (const e of POR_ESTADO) {
      const pildora = screen.getByText(e.label)
      expect(pildora).toHaveAttribute('data-tono', e.tono)
      // tailwind-merge se queda con la última clase de cada grupo. Si el tono
      // perdiera contra la clase base, el `data-tono` seguiría estando pero la
      // píldora saldría gris — por eso además se afirma que el
      // `border-transparent` de la base NO sobrevivió.
      expect(pildora.className).not.toContain('border-transparent')
      expect(pildora.className).not.toContain('bg-primary')
    }
  })

  it('🔴 las cuatro píldoras son distintas entre sí', async () => {
    // El grupo de control. Sin esto, un mapa que devolviera el mismo tono para
    // los cuatro estados pasaría el test de arriba en uno de los cuatro casos y
    // la grilla volvería a no distinguir nada.
    conCuatroEstados()
    render(<Incidencias />, '/incidencias')
    await screen.findByText('Ticket 1')

    const tonos = POR_ESTADO.map((e) => screen.getByText(e.label).getAttribute('data-tono'))
    expect(tonos.every(Boolean)).toBe(true)
    expect(new Set(tonos).size).toBe(4)
  })

  it('el punto del semáforo sigue estando, y con el tono fuerte', async () => {
    // El color acompaña al texto, no lo reemplaza: el punto de la primera
    // columna es lo que hace escaneable la grilla desde el borde izquierdo, y
    // usa el tono fuerte (`bg-red-500`), no el suave de la píldora.
    conCuatroEstados()
    render(<Incidencias />, '/incidencias')
    await screen.findByText('Ticket 1')

    const punto = screen.getAllByLabelText('Abierto')[0]
    expect(punto.className).toContain('bg-red-500')
    expect(punto.className).toContain('rounded-full')
  })
})
