// La agenda de las cuadrillas (pedido 42 fase B, hecha calendario el 2026-08-14).
//
// Lo que la pantalla tiene que dejar claro:
//
// 1. **Qué hace cada equipo y en qué sale** — las dos mitades del pedido juntas
//    y en la misma vista, que es lo que se mira a la mañana para despachar.
// 2. **Que se vean los próximos días y no sólo hoy**, que es el pedido nuevo. La
//    semana y el mes se piden en **un solo rango por cuadrilla**: el fan-out por
//    día multiplicaría por 7 o por 42 y no se ve mirando la pantalla.
// 3. **Que se pueda entrar a un día** desde la grilla, y que ahí siga estando el
//    detalle por cuadrilla con su hoja de ruta — que es el camino entero del
//    pedido y lo que no hay que romper al mover el componente.
// 4. **Que la fecha del ticket sobreviva a editar cualquier otro campo.** El
//    PUT manda el objeto entero: un campo que no viaja vuelve a null, y el
//    ticket se desagenda solo. Es el defecto más caro de esta fase y no se ve
//    mirando la pantalla.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Agenda } from '../pages/Agenda'
import { IncidenciaDetalle } from '../pages/IncidenciaDetalle'

/** La pantalla montada sobre su propia ruta.
 *
 *  El `Routes` no es decorativo: la vista y el día viven en la query string, así
 *  que apretar una flecha o entrar a un día es una navegación. Sin ruta que
 *  matchee, el `Link` cambia la URL y la pantalla no se vuelve a dibujar — y los
 *  tests de navegación pasarían midiendo la pantalla vieja. */
const renderAgenda = (query = '') =>
  renderRTL(
    <MemoryRouter initialEntries={[`/agenda${query}`]}>
      <Routes><Route path="/agenda" element={<Agenda />} /></Routes>
    </MemoryRouter>,
  )

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

// El 11 de agosto de 2026 es martes; el lunes de esa semana es el 10.
const MARTES = '2026-08-11'
const LUNES = '2026-08-10'
const JUEVES = '2026-08-13'

const TRABAJO = {
  incidencia_id: 77, titulo: 'Cambio de switch', cliente_id: 5,
  cliente_nombre: 'Estudio Sur',
  cliente_domicilio: 'Av. San Martín 1240', cliente_ciudad: 'Suipacha',
  estado: 'abierto', modalidad: 'on_site',
  desde: `${MARTES}T09:00:00`, hasta: `${MARTES}T11:00:00`,
  duracion_minutos: 120, vehiculos: ['AB123CD'],
}
const DEL_JUEVES = {
  ...TRABAJO, incidencia_id: 78, titulo: 'Tendido de fibra',
  desde: `${JUEVES}T14:00:00`, hasta: `${JUEVES}T16:00:00`,
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let pedidos: { url: string; metodo: string; cuerpo: unknown }[] = []

/** Mockea `fetch` devolviendo `equipos` en el catálogo y `trabajos` en la agenda
 *  de la Cuadrilla Norte. El resto de las cuadrillas, sin nada. */
function stub(trabajos: unknown[] = [TRABAJO], equipos: unknown[] = [NORTE, SUR]) {
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    const metodo = opciones?.method ?? 'GET'
    pedidos.push({
      url: u, metodo,
      cuerpo: opciones?.body ? JSON.parse(String(opciones.body)) : null,
    })
    if (metodo !== 'GET') return Promise.resolve(json({ ok: true }))
    if (u.includes('/api/agenda/equipo/1')) return Promise.resolve(json(trabajos))
    if (u.includes('/api/agenda/equipo/')) return Promise.resolve(json([]))
    if (u.includes('/api/equipos-trabajo')) return Promise.resolve(json(equipos))
    return Promise.resolve(json([]))
  }))
}

/** Las URLs de agenda que se pidieron, sin el catálogo de equipos. */
const pedidosDeAgenda = () =>
  pedidos.filter((p) => p.url.includes('/api/agenda/equipo/')).map((p) => p.url)

beforeEach(() => {
  pedidos = []
  stub()
})

// --- la vista de día -------------------------------------------------------
//
// Es la pantalla de despacho, la que había antes de que la agenda fuera
// calendario. Estos tests son la red que dice que mudarla de
// `components/agenda-equipos.tsx` a `components/agenda/vista-dia.tsx` —y
// sacarle su selector de fecha y su fetch— no le rompió nada.

const DIA = `?vista=dia&dia=${MARTES}`

describe('Agenda — la vista de día', () => {
  it('muestra el horario, el trabajo y en qué sale el equipo', async () => {
    renderAgenda(DIA)

    // Se espera por el TRABAJO y no por el nombre del equipo. La pantalla carga
    // en dos tiempos —primero el catálogo de cuadrillas, después su agenda—, así
    // que la tarjeta existe un instante antes que su contenido: esperar por el
    // nombre daba una tarjeta que todavía decía "Cargando…".
    await screen.findByText('Cambio de switch')
    const norte = screen.getByText('Cuadrilla Norte')
      .closest('[data-slot="card"]') as HTMLElement
    expect(within(norte).getByText('AB123CD')).toBeInTheDocument()
    expect(within(norte).getByText('09:00–11:00')).toBeInTheDocument()
    expect(within(norte).getByText('Cambio de switch')).toBeInTheDocument()
    expect(within(norte).getByText('Estudio Sur')).toBeInTheDocument()
    expect(within(norte).getByText('On-site')).toBeInTheDocument()
  })

  it('el trabajo linkea al ticket', async () => {
    renderAgenda(DIA)
    const link = await screen.findByRole('link', { name: 'Cambio de switch' })
    expect(link).toHaveAttribute('href', '/incidencias/77')
  })

  it('un equipo sin nada ese día lo dice, no queda en blanco', async () => {
    renderAgenda(DIA)
    expect(await screen.findByText('Sin trabajos ese día.')).toBeInTheDocument()
  })

  it('no pide la agenda de un equipo dado de baja', async () => {
    stub([TRABAJO], [NORTE, DE_BAJA])
    renderAgenda(DIA)
    await screen.findByText('Cambio de switch')

    expect(screen.queryByText('Cuadrilla Vieja')).not.toBeInTheDocument()
    expect(pedidos.some((p) => p.url.includes('/api/agenda/equipo/3'))).toBe(false)
  })

  it('muestra el domicilio del cliente, que es lo que ordena el recorrido', async () => {
    renderAgenda(DIA)
    expect(await screen.findByText('Av. San Martín 1240, Suipacha')).toBeInTheDocument()
  })

  it('no repite la ciudad si ya viene adentro del domicilio', async () => {
    // Se vio en la demo desplegada: los clientes reales cargan la ciudad
    // adentro del domicilio Y en su propio campo, y la pantalla decía
    // "Av. Pueyrredón 1640, CABA, CABA".
    stub([{
      ...TRABAJO,
      cliente_domicilio: 'Av. Pueyrredón 1640, CABA', cliente_ciudad: 'CABA',
    }])
    renderAgenda(DIA)
    expect(await screen.findByText('Av. Pueyrredón 1640, CABA')).toBeInTheDocument()
    expect(screen.queryByText(/CABA, CABA/)).not.toBeInTheDocument()
  })

  it('un trabajo sin domicilio no deja un renglón vacío', async () => {
    stub([{ ...TRABAJO, cliente_domicilio: null, cliente_ciudad: null }])
    renderAgenda(DIA)
    await screen.findByText('Cambio de switch')
    // El nombre del cliente sigue estando; lo que no tiene que aparecer es la
    // segunda línea con una coma suelta o un guión.
    expect(screen.getByText('Estudio Sur')).toBeInTheDocument()
    expect(screen.queryByText(', ')).not.toBeInTheDocument()
  })

  it('el botón de hoja de ruta apunta al equipo y al día que se está mirando', async () => {
    // El día sale de la URL, no de `hoy`: la hoja se imprime la noche anterior
    // tanto como a la mañana. Con un `hoy` hardcodeado este test pasaría igual,
    // así que abajo se cambia de día con la flecha y se vuelve a mirar.
    const user = userEvent.setup()
    // Una sola cuadrilla: con dos hay dos botones y la forma singular de
    // `getByRole` tira error antes de medir nada. Que cada equipo tenga el suyo
    // lo prueba el test de abajo.
    stub([TRABAJO], [NORTE])
    renderAgenda(DIA)
    await screen.findByText('Cambio de switch')

    expect(screen.getByRole('link', { name: /hoja de ruta/i }))
      .toHaveAttribute('href', `/api/agenda/equipo/1/hoja-de-ruta?dia=${MARTES}`)

    await user.click(screen.getByRole('link', { name: 'Siguiente' }))

    await waitFor(() => {
      expect(screen.getByRole('link', { name: /hoja de ruta/i }))
        .toHaveAttribute('href', '/api/agenda/equipo/1/hoja-de-ruta?dia=2026-08-12')
    })
  })

  it('cada equipo tiene la suya: son salidas distintas', async () => {
    renderAgenda(DIA)
    await screen.findByText('Cambio de switch')

    const enlaces = screen.getAllByRole('link', { name: /hoja de ruta/i })
      .map((a) => a.getAttribute('href'))
    expect(enlaces.some((h) => h?.includes('/equipo/1/'))).toBe(true)
    expect(enlaces.some((h) => h?.includes('/equipo/2/'))).toBe(true)
  })

  it('pide un solo día', async () => {
    renderAgenda(DIA)
    await screen.findByText('Cambio de switch')
    expect(pedidosDeAgenda().every((u) => u.includes(`desde=${MARTES}&dias=1`))).toBe(true)
  })
})

// --- la vista de semana ----------------------------------------------------

const SEMANA = `?vista=semana&dia=${MARTES}`

describe('Agenda — la vista de semana', () => {
  it('pide UN rango de 7 días por cuadrilla, no siete rangos de un día', async () => {
    // El defecto obvio de esta vista, y el que no se ve mirando la pantalla: con
    // un fetch por día y por equipo, dos cuadrillas son catorce llamadas y el
    // mes son ochenta y cuatro. El endpoint acepta `dias` desde el día uno.
    renderAgenda(SEMANA)
    await screen.findByText('Cambio de switch')

    await waitFor(() => expect(pedidosDeAgenda()).toHaveLength(2))
    expect(pedidosDeAgenda().sort()).toEqual([
      `/api/agenda/equipo/1?desde=${LUNES}&dias=7`,
      `/api/agenda/equipo/2?desde=${LUNES}&dias=7`,
    ])
  })

  it('el trabajo del jueves cae en la columna del jueves', async () => {
    // La afirmación central de la vista. Sin ella, una grilla que amontone todos
    // los chips en la primera columna pasa igual: los textos están todos en
    // pantalla.
    stub([TRABAJO, DEL_JUEVES])
    renderAgenda(SEMANA)

    const columna = (await screen.findByRole('link', { name: /Jue 13/ }))
      .parentElement as HTMLElement
    expect(within(columna).getByText('Tendido de fibra')).toBeInTheDocument()
    expect(within(columna).queryByText('Cambio de switch')).not.toBeInTheDocument()
  })

  it('el encabezado del día entra a la vista de día de ESE día', async () => {
    // Es el camino de entrada del pedido: de la semana al detalle de un día, con
    // sus cuadrillas y su hoja de ruta.
    const user = userEvent.setup()
    stub([TRABAJO, DEL_JUEVES], [NORTE])
    renderAgenda(SEMANA)

    await user.click(await screen.findByRole('link', { name: /Jue 13/ }))

    // Ya no es la grilla: es el detalle por cuadrilla, con su hoja de ruta del
    // jueves. Mirar sólo que el título cambió no probaría que se ve el día.
    await waitFor(() => {
      expect(screen.getByRole('link', { name: /hoja de ruta/i }))
        .toHaveAttribute('href', `/api/agenda/equipo/1/hoja-de-ruta?dia=${JUEVES}`)
    })
    expect(screen.getByText('Tendido de fibra')).toBeInTheDocument()
  })

  it('sin día en la URL arranca en la semana de hoy, en hora local', async () => {
    // A las 22:00 de Argentina `toISOString()` ya es el día siguiente. Si la
    // agenda calculara el lunes en UTC, media noche mostraría la semana
    // equivocada — y un domingo a las 22:00, la semana entera de al lado.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date(`${MARTES}T22:30:00-03:00`))
    try {
      renderAgenda('?vista=semana')
      await waitFor(() => {
        expect(pedidosDeAgenda().some((u) => u.includes(`desde=${LUNES}&dias=7`))).toBe(true)
      })
    } finally {
      vi.useRealTimers()
    }
  })
})

// --- la vista de mes -------------------------------------------------------

describe('Agenda — la vista de mes', () => {
  it('pide la GRILLA del mes, no el mes', async () => {
    // Agosto de 2026 empieza sábado, así que la grilla arranca el lunes 27 de
    // julio y ocupa 6 semanas: 42 celdas. Pedir sólo el mes dejaría en blanco
    // los días de los bordes, que son días reales con trabajos reales. Es
    // también la razón por la que el tope de `dias` del backend subió de 31.
    renderAgenda(`?vista=mes&dia=${MARTES}`)
    await waitFor(() => expect(pedidosDeAgenda()).toHaveLength(2))
    expect(pedidosDeAgenda()[0]).toBe('/api/agenda/equipo/1?desde=2026-07-27&dias=42')
  })

  it('lo que no entra en la celda linkea al día, no se esconde', async () => {
    const cuatro = [0, 1, 2, 3].map((i) => ({
      ...TRABAJO, incidencia_id: 100 + i, titulo: `Trabajo ${i}`,
      desde: `${MARTES}T0${8 + i}:00:00`, hasta: `${MARTES}T1${i}:00:00`,
    }))
    stub(cuatro)
    renderAgenda(`?vista=mes&dia=${MARTES}`)

    // Por texto y no por rol: `getByRole('link', …)` no lo encuentra en esta
    // grilla, aunque el elemento sea un `<a href>` — la celda del mes tiene tres
    // anclas hermanas (el número del día, los chips y ésta) y la resolución del
    // nombre accesible no da con ella. El `toHaveAttribute` de abajo prueba lo
    // que importa igual: que es un ancla y a dónde lleva.
    const mas = await screen.findByText('+1 más')
    expect(mas.tagName).toBe('A')
    expect(mas).toHaveAttribute('href', `/agenda?vista=dia&dia=${MARTES}`)
  })
})

// --- el filtro de cuadrilla ------------------------------------------------

describe('Agenda — el filtro de cuadrilla', () => {
  it('recorta lo que se dibuja, pero sigue pidiendo la agenda de todas', async () => {
    // Si el filtro además recortara el fetch, el "+N más" de la celda del mes y
    // la cuenta del día pasarían a mentir en cuanto alguien elige una cuadrilla:
    // la pantalla no sabría que existen los trabajos que dejó de pedir.
    stub([TRABAJO])
    renderAgenda(`?vista=semana&dia=${MARTES}&equipo=2`)
    await waitFor(() => expect(pedidosDeAgenda()).toHaveLength(2))

    // La Norte es la única con trabajos, y está filtrada afuera.
    expect(screen.queryByText('Cambio de switch')).not.toBeInTheDocument()
    expect(pedidosDeAgenda().some((u) => u.includes('/equipo/1?'))).toBe(true)
  })
})

// --- la fecha en el ticket -------------------------------------------------

const INCIDENCIA = {
  id: 77, cliente_id: 5, equipo_id: null, activo_id: null, tecnico_id: null,
  recepcionista_id: null, vendedor_id: null, modalidad: 'on_site',
  sector_id: null, categoria_id: null,
  fecha_programada: `${MARTES}T09:00:00`, duracion_minutos: 120,
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
        .toHaveValue(`${MARTES}T09:00`)
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
        fecha_programada: `${MARTES}T09:00:00`,
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
