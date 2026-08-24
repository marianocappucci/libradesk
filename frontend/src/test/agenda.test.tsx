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

/** Mockea `fetch` devolviendo `equipos` en el catálogo, `trabajos` en la agenda
 *  de la Cuadrilla Norte y `deSur` en la de la Sur. */
function stub(
  trabajos: unknown[] = [TRABAJO],
  equipos: unknown[] = [NORTE, SUR],
  deSur: unknown[] = [],
) {
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    const metodo = opciones?.method ?? 'GET'
    pedidos.push({
      url: u, metodo,
      cuerpo: opciones?.body ? JSON.parse(String(opciones.body)) : null,
    })
    if (metodo !== 'GET') return Promise.resolve(json({ ok: true }))
    if (u.includes('/api/agenda/equipo/1')) return Promise.resolve(json(trabajos))
    if (u.includes('/api/agenda/equipo/2')) return Promise.resolve(json(deSur))
    if (u.includes('/api/agenda/equipo/')) return Promise.resolve(json([]))
    if (u.includes('/api/equipos-trabajo')) return Promise.resolve(json(equipos))
    return Promise.resolve(json([]))
  }))
}

/** Las URLs de agenda que se pidieron, sin el catálogo de equipos. */
const pedidosDeAgenda = () =>
  pedidos.filter((p) => p.url.includes('/api/agenda/equipo/')).map((p) => p.url)

/** El cuerpo de una columna de la rejilla: el día en la vista de semana, el id
 *  de la cuadrilla en la de día. Es donde viven los bloques — el encabezado es
 *  otro nodo, en otra fila. */
const columna = (clave: string) =>
  document.querySelector(`[data-columna="${clave}"]`) as HTMLElement

/** El alto en píxeles de un bloque, que es lo que dice cuánto dura. Sale del
 *  `style` inline porque en jsdom no hay layout: `getBoundingClientRect()`
 *  devuelve 0 para todo y el test pasaría con el alto roto. */
const altoDe = (el: HTMLElement) => Number.parseFloat(el.style.height)

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
  it('cada cuadrilla tiene su columna, con su vehículo y su trabajo adentro', async () => {
    // Una columna por cuadrilla es la decisión de la vista: al entrar a un día
    // ya se sabe *cuándo*, y lo que falta es quién sale y a dónde. Si los
    // trabajos de las dos cayeran mezclados en una sola columna, armar el
    // recorrido de la Norte obligaría a pescar sus paradas entre las de la Sur.
    renderAgenda(DIA)
    await screen.findByText('Cambio de switch')

    const norte = columna('1')
    expect(within(norte).getByText('Cambio de switch')).toBeInTheDocument()
    // El horario, el cliente y la modalidad, en el bloque; la patente, en el
    // encabezado. La modalidad no es decorativa: un remoto no es una parada y la
    // hoja de ruta lo deja afuera, así que la grilla tiene que distinguirlo.
    expect(within(norte).getByText(/09:00 · Estudio Sur · On-site/)).toBeInTheDocument()
    expect(screen.getByText('AB123CD')).toBeInTheDocument()
    // Y NO en la de la Sur, que ese día no tiene nada.
    expect(within(columna('2')).queryByText('Cambio de switch')).not.toBeInTheDocument()
  })

  it('el trabajo linkea al ticket', async () => {
    renderAgenda(DIA)
    await screen.findByText('Cambio de switch')
    // Por el bloque y no por el nombre accesible: el bloque acumula título,
    // hora, cliente y domicilio, así que `name: 'Cambio de switch'` ya no
    // matchea. Lo que importa es a dónde lleva.
    const bloque = screen.getByText('Cambio de switch').closest('a') as HTMLElement
    expect(bloque).toHaveAttribute('href', '/incidencias/77')
  })

  it('una cuadrilla sin trabajos conserva su columna y su hoja de ruta', async () => {
    // En una rejilla, el día vacío **es** la columna vacía — no hace falta un
    // cartel. Lo que no puede pasar es que la cuadrilla desaparezca: su hoja de
    // ruta se imprime igual, y el PDF dice "sin trabajos agendados".
    renderAgenda(DIA)
    await screen.findByText('Cambio de switch')

    expect(columna('2')).toBeInTheDocument()
    expect(screen.getByText('Cuadrilla Sur')).toBeInTheDocument()
    const hojas = screen.getAllByRole('link', { name: /hoja de ruta/i })
      .map((a) => a.getAttribute('href'))
    expect(hojas.some((h) => h?.includes('/equipo/2/'))).toBe(true)
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
    // El cliente sigue estando en su renglón; lo que no tiene que aparecer es
    // la tercera línea con una coma suelta o un guión.
    expect(screen.getByText(/09:00 · Estudio Sur/)).toBeInTheDocument()
    expect(screen.queryByText(', ')).not.toBeInTheDocument()
    expect(screen.queryByText('—')).not.toBeInTheDocument()
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

    // Se espera por el CHIP y no por el encabezado de la columna: la grilla se
    // dibuja en cuanto llega el catálogo de cuadrillas, con las siete columnas
    // vacías, así que esperar por "Jue 13" devuelve una grilla sin datos y el
    // `getByText` de abajo —que es sincrónico— corre antes que la agenda.
    await screen.findByText('Tendido de fibra')
    // Por el cuerpo de la columna y no por el encabezado: en la rejilla los
    // bloques cuelgan de otra fila, así que el `parentElement` del link del día
    // es la celda del título y no contiene ningún trabajo.
    expect(within(columna(JUEVES)).getByText('Tendido de fibra')).toBeInTheDocument()
    expect(within(columna(JUEVES)).queryByText('Cambio de switch')).not.toBeInTheDocument()
    expect(within(columna(MARTES)).getByText('Cambio de switch')).toBeInTheDocument()
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

// --- la rejilla horaria ----------------------------------------------------
//
// Lo que la rejilla agrega sobre la lista de chips es que el bloque **mide lo
// que dura** y que dos trabajos pisados se reparten el ancho. Las dos cosas son
// invisibles en el DOM si no se las mide: un bloque de alto cero y uno tapando
// a otro se ven igual de bien en un `getByText`.

const bloqueDe = (titulo: string) =>
  screen.getByText(titulo).closest('a') as HTMLElement

describe('Agenda — la rejilla horaria', () => {
  it('el bloque mide lo que dura el trabajo', async () => {
    // Es el punto entero del cambio: la lista decía que había dos trabajos, la
    // rejilla dice que uno ocupa el doble. Sin esta afirmación, un alto fijo
    // —o cero— pasaría con todos los textos en pantalla.
    stub([
      TRABAJO, // 09:00–11:00, dos horas
      { ...TRABAJO, incidencia_id: 78, titulo: 'Visita corta',
        desde: `${MARTES}T14:00:00`, hasta: `${MARTES}T15:00:00` },
    ])
    renderAgenda(DIA)
    await screen.findByText('Cambio de switch')

    const largo = altoDe(bloqueDe('Cambio de switch'))
    const corto = altoDe(bloqueDe('Visita corta'))
    expect(largo).toBeGreaterThan(0)
    expect(largo).toBeCloseTo(corto * 2, 0)
  })

  it('dos trabajos pisados se reparten el ancho, no se tapan', async () => {
    // El caso vivo: los datos de ejemplo tienen dos cuadrillas a las 09:00. En
    // la vista de semana caen en la misma columna del día, y sin reparto el de
    // abajo desaparece sin que nada avise.
    stub(
      [TRABAJO],
      [NORTE, SUR],
      [{ ...TRABAJO, incidencia_id: 91, titulo: 'Ronda del Sur' }],
    )
    renderAgenda(SEMANA)
    await screen.findByText('Ronda del Sur')

    const a = bloqueDe('Cambio de switch')
    const b = bloqueDe('Ronda del Sur')
    // Media columna cada uno (49 %, con 1 % de aire), y arrancando en lugares
    // distintos: si los dos salieran de 0 % con 100 % de ancho, uno taparía al
    // otro y los dos textos seguirían en el DOM igual.
    for (const el of [a, b]) {
      expect(Number.parseFloat(el.style.width)).toBeCloseTo(49, 0)
    }
    expect(a.style.left).not.toBe(b.style.left)
    expect([a.style.left, b.style.left].sort()).toEqual(['0%', '50%'])
  })

  it('🔴 uno que empieza cuando el otro termina NO se pisa', async () => {
    // Los datos de ejemplo tienen ese caso a propósito (uno termina 11:00 y el
    // siguiente empieza 11:00). Con un `>` en vez de `>=` los dos saldrían a
    // media columna por un choque que no existe, y la agenda mentiría diciendo
    // que la cuadrilla está doblemente ocupada.
    stub([
      TRABAJO, // 09:00–11:00
      { ...TRABAJO, incidencia_id: 79, titulo: 'Pegado al anterior',
        desde: `${MARTES}T11:00:00`, hasta: `${MARTES}T12:00:00` },
    ])
    renderAgenda(DIA)
    await screen.findByText('Pegado al anterior')

    for (const t of ['Cambio de switch', 'Pegado al anterior']) {
      expect(Number.parseFloat(bloqueDe(t).style.width)).toBeGreaterThan(90)
      expect(bloqueDe(t).style.left).toBe('0%')
    }
  })

  it('🔴 los controles van ANTES del título, para que no se muevan', async () => {
    // Lo reportó el humano: al cambiar de día las flechas se corrían de lugar.
    // El grupo estaba pegado al borde derecho, así que su ancho lo fijaba el
    // largo del título — "Agosto 2026" y "10 al 16 de agosto de 2026" no miden
    // lo mismo — y apretar dos veces seguidas obligaba a perseguir el botón.
    //
    // En jsdom no hay layout, así que la posición no se puede medir: lo que se
    // afirma es la **causa estructural**, que el título vaya después de los
    // controles dentro del mismo grupo anclado a la izquierda. Si alguien lo
    // vuelve a poner delante —o separa el grupo del título—, esto se pone rojo.
    renderAgenda(`?vista=mes&dia=${MARTES}`)
    await screen.findByRole('link', { name: 'Hoy' })

    // `asChild`: el `<a>` ES el botón, así que su padre ya es el grupo.
    const grupo = screen.getByRole('link', { name: 'Hoy' }).parentElement as HTMLElement
    const orden = [...grupo.children].map((n) => n.textContent?.trim() ?? '')
    expect(orden[0]).toBe('Hoy')
    expect(orden.at(-1)).toMatch(/agosto de 2026/i)
  })

  it('🔴 el encabezado y el cuerpo scrollean en la MISMA caja', async () => {
    // Lo reportó el humano con una captura: las cabeceras estaban desfasadas de
    // las filas. La causa es la barra de scroll — con el encabezado afuera del
    // contenedor que scrollea, la barra le come ~15 px de ancho SÓLO al cuerpo y
    // las columnas se van corriendo, con el desfase acumulándose hacia la
    // derecha (el lunes casi alineado, el domingo corrido un dedo).
    //
    // En jsdom no hay layout, así que medir el ancho daría 0 para todo y el test
    // pasaría con el defecto entero puesto. Lo que sí se puede afirmar es la
    // causa estructural: los dos tienen que colgar del mismo contenedor que
    // scrollea, que es lo que hace que el ancho disponible sea el mismo por
    // construcción.
    renderAgenda(SEMANA)
    await screen.findByText('Cambio de switch')

    const caja = document.querySelector('[data-rejilla-scroll]') as HTMLElement
    expect(caja).toBeInTheDocument()
    for (const clave of [MARTES, JUEVES]) {
      expect(caja.contains(columna(clave))).toBe(true)
      expect(caja.contains(
        document.querySelector(`[data-columna-encabezado="${clave}"]`),
      )).toBe(true)
    }
    // Y el encabezado tiene que quedar pegado arriba, o al bajar por la tarde se
    // deja de saber qué columna es cuál.
    const encabezado = document.querySelector('[data-columna-encabezado]')
      ?.parentElement?.parentElement as HTMLElement
    expect(encabezado.className).toMatch(/sticky/)
  })

  it('un trabajo fuera del horario laboral estira la ventana, no se recorta', async () => {
    // La rejilla arranca a las 07:00. Una salida a las 05:00 tiene que bajar el
    // piso: si la ventana recortara, el trabajo desaparecería de la grilla sin
    // que nada lo dijera, que es la peor forma de fallar de un calendario.
    stub([{ ...TRABAJO, titulo: 'Salida de madrugada',
      desde: `${MARTES}T05:00:00`, hasta: `${MARTES}T06:00:00` }])
    renderAgenda(DIA)
    await screen.findByText('Salida de madrugada')

    // `getAllByText`: "05:00" está en la canaleta de horas Y adentro del bloque.
    expect(screen.getAllByText('05:00').length).toBeGreaterThan(0)
    // Y arriba del bloque no puede quedar espacio negativo.
    expect(Number.parseFloat(bloqueDe('Salida de madrugada').style.top))
      .toBeGreaterThanOrEqual(0)
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
    //
    // La Sur tiene su propio trabajo **a propósito**: sin él, la ausencia del de
    // la Norte se cumpliría sola mientras la grilla está vacía, y el test daría
    // verde con el filtro roto. El de la Sur es el ancla que dice que la agenda
    // ya llegó y se dibujó.
    stub([TRABAJO], [NORTE, SUR], [{ ...TRABAJO, incidencia_id: 90, titulo: 'Ronda del Sur' }])
    renderAgenda(`?vista=semana&dia=${MARTES}&equipo=2`)

    expect(await screen.findByText('Ronda del Sur')).toBeInTheDocument()
    expect(screen.queryByText('Cambio de switch')).not.toBeInTheDocument()
    // Y la agenda de la Norte se pidió igual, aunque no se dibuje.
    await waitFor(() => expect(pedidosDeAgenda()).toHaveLength(2))
    expect(pedidosDeAgenda().some((u) => u.includes('/equipo/1?'))).toBe(true)
  })
})

// --- la instancia sin cuadrillas -------------------------------------------
//
// La agenda es core del producto: no la gatea ningún módulo, así que aparece en
// el menú de TODA instancia, incluida la que nunca cargó una cuadrilla porque no
// despacha a nadie. Hasta el 2026-08-24 esa instancia veía «Cargando…» para
// siempre: el catálogo vacío y el catálogo en vuelo son los dos
// `equipos.length === 0`, y la pantalla resolvía el empate a favor del cartel de
// carga. Lo reportó el humano contra `compulibra.libradesk.com.ar`, que tiene
// cero filas en `equipos_trabajo` contra dos en cada una de las otras dos
// instancias. Ningún test cubría el catálogo vacío: por eso salió.

describe('Agenda — la instancia sin cuadrillas', () => {
  it('con el catálogo vacío dice que no hay cuadrillas, y deja de decir "Cargando"', async () => {
    stub([], [])
    renderAgenda(`?vista=semana&dia=${MARTES}`)

    expect(await screen.findByText(/Todavía no hay cuadrillas cargadas/)).toBeInTheDocument()
    // La mitad que importa. Sin este assert el test pasaría con el defecto
    // puesto: el texto nuevo podría convivir con el cartel de carga.
    expect(screen.queryByText('Cargando…')).not.toBeInTheDocument()
    // Y manda a donde se resuelve, que es otra pantalla.
    expect(screen.getByRole('link', { name: /Equipos y flota/ }))
      .toHaveAttribute('href', '/equipos-trabajo')
  })

  it('mientras el catálogo está en vuelo sigue diciendo "Cargando"', async () => {
    // El control positivo del test de arriba: sin él, "no dice Cargando" se
    // cumpliría también borrando el estado de carga — que es el defecto
    // opuesto, un parpadeo de "no hay cuadrillas" en toda instancia que sí las
    // tiene.
    let responder: (v: Response) => void = () => {}
    const enVuelo = new Promise<Response>((r) => { responder = r })
    vi.stubGlobal('fetch', vi.fn((url: string) => (
      String(url).includes('/api/equipos-trabajo') ? enVuelo : Promise.resolve(json([]))
    )))

    renderAgenda(`?vista=semana&dia=${MARTES}`)
    expect(await screen.findByText('Cargando…')).toBeInTheDocument()

    responder(json([NORTE]))
    await waitFor(() => expect(screen.queryByText('Cargando…')).not.toBeInTheDocument())
  })

  it('con todas las cuadrillas dadas de baja el cartel es el otro', async () => {
    // Dos vacíos distintos, y no dan la misma instrucción: el primero se
    // arregla creando una cuadrilla, el segundo reactivando la que hay.
    stub([], [DE_BAJA])
    renderAgenda(`?vista=semana&dia=${MARTES}`)

    expect(await screen.findByText('No hay equipos activos para agendar.')).toBeInTheDocument()
    expect(screen.queryByText(/Todavía no hay cuadrillas cargadas/)).not.toBeInTheDocument()
  })

  it('si el catálogo falla se ve el error y no un "no hay cuadrillas" inventado', async () => {
    // Con la API caída la pantalla no sabe cuántas cuadrillas hay: afirmar que
    // no hay ninguna es afirmar sobre el dato que justamente no llegó.
    vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(
      String(url).includes('/api/equipos-trabajo')
        ? new Response(JSON.stringify({ detail: 'La base no responde.' }), {
          status: 500, headers: { 'content-type': 'application/json' },
        })
        : json([]),
    )))

    renderAgenda(`?vista=semana&dia=${MARTES}`)
    expect(await screen.findByText('La base no responde.')).toBeInTheDocument()
    expect(screen.queryByText('Cargando…')).not.toBeInTheDocument()
    expect(screen.queryByText(/Todavía no hay cuadrillas cargadas/)).not.toBeInTheDocument()
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
