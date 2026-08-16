// Los dos ajustes de pantalla que el humano pidió el 2026-08-16, mirando el
// producto ya desplegado:
//
// 1. La barra con "Armar salida" / "Generar remito" queda **flotando al pie de
//    la lista de incidencias, siempre a la vista**, en vez de vivir al final de
//    una grilla larga.
// 2. En `/listas-precio`, la columna "Acciones" alinea su título con los
//    botones, y el botón de editar es el lápiz del vocabulario y no la palabra
//    "Editar".
//
// ⚠️ **Lo que estos tests NO prueban** — la misma advertencia que
// `ajustes-de-pantalla.test.tsx`, y acá pesa más que allá: jsdom no calcula
// layout ni scroll, así que `sticky` presente en el `className` no demuestra
// que la barra se vea al pie. Estos casos fijan que la clase siga puesta; que
// la clase HAGA algo se midió aparte, en Chromium, sobre un arnés que reproduce
// la cadena de contenedores de la pantalla (`sidebar-wrapper` → `SidebarInset`
// → el `main` de libra-ui → el div de la pantalla → la Card): con `sticky`, la
// barra queda en 704 px de un viewport de 720 —pegada, a los 16 de `bottom-4`—
// y sin la clase se va a 1236, fuera de la pantalla.
//
// 🔑 Esa medición además **desmintió la teoría con la que se escribió el
// arreglo**: que un contenedor `grid` anula el `sticky` de su hijo porque el
// bloque contenedor de un ítem de grid es su propia celda. Es falso en
// Chromium —los dos contenedores pegan igual—, así que el `grid gap-4` de la
// pantalla se dejó como estaba y no hay ningún test sobre él. Queda anotado
// porque el primer intento cambió el contenedor por ese motivo inventado, y sin
// el navegador el cambio se habría ido a producción con un test verde
// custodiándolo.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Incidencias } from '../pages/Incidencias'
import { ListasPrecio } from '../pages/Inventario'
import { SucursalProvider } from '../components/sucursal'

const render = (ui: ReactElement) => renderRTL(<MemoryRouter>{ui}</MemoryRouter>)

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

// ── 1. La barra flotante de incidencias ────────────────────────────────────

const CLIENTE = { id: 1, nombre: 'Estudio Sur', activo: true }

function reclamo(id: number, titulo: string, estado: string) {
  return {
    id, cliente_id: 1, equipo_id: null, activo_id: null, tecnico_id: null,
    recepcionista_id: null, vendedor_id: null, modalidad: null,
    fecha_programada: null, duracion_minutos: null, equipo_trabajo_id: null,
    sector_id: null, categoria_id: null, titulo, descripcion: '',
    estado, prioridad: 'media', horas_invertidas: null, nro_cds: null,
    reclamante: null, remito_id: null, fecha_creacion: '2026-08-16T10:00:00',
    fecha_cierre: null, cobertura_abono: null, abono_horas_cubiertas: null,
    abono_materiales_incluidos: null,
  }
}

const ABIERTO = reclamo(11, 'No enciende el router', 'abierto')

describe('La barra de acciones de incidencias flota al pie', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url)
      if (u.includes('/api/incidencias')) return Promise.resolve(json([ABIERTO]))
      if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
      return Promise.resolve(json([]))
    }))
  })

  afterEach(() => { vi.unstubAllGlobals() })

  /** Tilda un reclamo y devuelve la tarjeta de la barra (el ancestro de los
   *  botones), que es el elemento que se pega. */
  async function barra() {
    const user = userEvent.setup()
    render(<Incidencias />)
    await screen.findByText('No enciende el router')
    await user.click(screen.getByRole('checkbox', { name: 'Elegir el reclamo #11' }))

    const boton = await screen.findByRole('button', { name: /Armar salida/ })
    // Se sube hasta la tarjeta, que es donde vive el `sticky`: el botón está
    // adentro del `CardContent`.
    const tarjeta = boton.closest('[data-slot="card"]')
    expect(tarjeta).not.toBeNull()
    return tarjeta as HTMLElement
  }

  it('la tarjeta con los botones se pega al pie', async () => {
    const tarjeta = await barra()
    expect(tarjeta.className).toMatch(/\bsticky\b/)
    expect(tarjeta.className).toMatch(/\bbottom-/)
  })

  it('queda al final de la pantalla, después de la grilla', async () => {
    // El orden en el DOM sobrevive a un cambio de nombre de clase, y es lo que
    // hace que el `sticky bottom` tenga recorrido: la barra se despega recién
    // al llegar al final del scroll porque su lugar natural es ahí.
    const tarjeta = await barra()
    const grilla = screen.getByText('No enciende el router').closest('table')

    expect(grilla).not.toBeNull()
    expect(
      grilla!.compareDocumentPosition(tarjeta) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it('la barra sigue apareciendo sólo con algo tildado', async () => {
    // El control de las dos de arriba: una barra que flota siempre le come el
    // pie de la pantalla todos los días para un flujo que es mensual.
    render(<Incidencias />)
    await screen.findByText('No enciende el router')

    expect(screen.queryByRole('button', { name: /Armar salida/ })).toBeNull()
  })
})

// ── 1b. La misma barra, en cuotas ──────────────────────────────────────────

const CUOTA = {
  id: 1, contrato_id: 1, contrato_numero: 'CTR-00000001',
  cliente_nombre: 'Estudio Contable Sur',
  periodo_desde: '2026-08-01', periodo_hasta: '2026-08-31',
  concepto: 'Alquiler agosto 2026', tipo_cargo: 'alquiler',
  fecha_emision: '2026-08-01', fecha_vencimiento: '2026-08-10',
  importe_base: 31000, bonificacion: 0, impuestos: 0, interes_mora: 0,
  importe_total: 31000, moneda: 'ARS', estado: 'pendiente',
  precio_id: 1, remito_id: null, factura_numero: null,
  comprobante_pago: null, observaciones: null, created_at: null,
}

describe('La barra de cuotas flota igual que la de incidencias', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url)
      if (u.includes('/api/cuotas')) return Promise.resolve(json([CUOTA]))
      return Promise.resolve(json([]))
    }))
  })

  afterEach(() => { vi.unstubAllGlobals() })

  it('la tarjeta de "Generar remito" se pega al pie', async () => {
    // El humano nombró la barra de incidencias, pero es la misma barra y el
    // mismo botón: sin este caso, la de cuotas queda para dentro de unos días.
    const user = userEvent.setup()
    const { Cuotas } = await import('../pages/Cuotas')
    render(<Cuotas />)
    // Por el contrato y no por el concepto: el concepto se fue de la grilla a
    // la ficha el 2026-08-16, y esperar por él acá se colgaba.
    await screen.findByText('CTR-00000001')

    await user.click(screen.getByRole('checkbox', { name: /Elegir la cuota/ }))

    const boton = await screen.findByRole('button', { name: /Generar remito/ })
    const tarjeta = boton.closest('[data-slot="card"]') as HTMLElement
    expect(tarjeta.className).toMatch(/\bsticky\b/)
    expect(tarjeta.className).toMatch(/\bbottom-/)
  })
})

// ── 3. Cuotas: menos columnas, y la ficha al click ─────────────────────────
//
// Pedido del humano (2026-08-16): *"en cuotas de contratos los datos son tantos
// que hace que tenga que ser scrolleable horizontalmente, no quiero que sea
// scrolleable, mostrá menos cosas y en tal caso que haciendo click en la fila me
// muestre el detalle en un modal"*.
//
// ⚠️ Igual que con el `sticky`: jsdom no calcula anchos, así que **acá no se
// prueba que la tabla entre en la pantalla**. Lo que se fija es lo que sí es
// verificable sin layout —qué columnas quedaron, qué se fue y que la ficha lo
// muestre—; el ancho se midió aparte, en Chromium.

const CUOTA_COMPLETA = {
  ...CUOTA,
  concepto: 'Alquiler agosto 2026 — CTR-00000001',
  importe_base: 50000, bonificacion: -5000, impuestos: 10500, interes_mora: 0,
  importe_total: 55500,
  observaciones: 'Se pactó bonificación por pago adelantado.',
}

describe('Cuotas muestra menos columnas y abre la ficha al click', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url)
      if (u.includes('/api/cuotas')) return Promise.resolve(json([CUOTA_COMPLETA]))
      return Promise.resolve(json([]))
    }))
  })

  afterEach(() => { vi.unstubAllGlobals() })

  async function montar() {
    const user = userEvent.setup()
    const { Cuotas } = await import('../pages/Cuotas')
    render(<Cuotas />)
    await screen.findByText('CTR-00000001')
    return user
  }

  it('la grilla queda en cinco columnas', async () => {
    await montar()
    const encabezados = screen.getAllByRole('columnheader')

    // El número exacto, no "menos que antes": una columna que vuelva a
    // colarse es exactamente lo que hay que ver.
    expect(encabezados).toHaveLength(5)
    // Y las que quedaron son éstas. Sin esta mitad, la de arriba pasaría igual
    // habiendo borrado las columnas equivocadas.
    for (const titulo of ['Contrato', 'Período', 'Importe', 'Estado']) {
      expect(screen.getByRole('columnheader', { name: new RegExp(titulo) })).toBeInTheDocument()
    }
  })

  it('🔴 concepto, cargo y vencimiento ya no están en la grilla', async () => {
    await montar()
    const tabla = screen.getByRole('table')

    expect(within(tabla).queryByText(/Alquiler agosto 2026/)).toBeNull()
    expect(within(tabla).queryByRole('columnheader', { name: /Concepto|Cargo|Vence|Acciones/ })).toBeNull()
    // El control de que la grilla SÍ se dibujó: si no hubiera renderizado nada,
    // las tres ausencias de arriba pasarían solas.
    expect(within(tabla).getByText('CTR-00000001')).toBeInTheDocument()
    expect(within(tabla).getByText('Estudio Contable Sur')).toBeInTheDocument()
  })

  it('el click en la fila abre la ficha con lo que se sacó de la grilla', async () => {
    const user = await montar()
    await user.click(screen.getByText('CTR-00000001').closest('tr')!)

    const ficha = await screen.findByRole('dialog')
    expect(within(ficha).getByText(/Alquiler agosto 2026 — CTR-00000001/)).toBeInTheDocument()
    expect(within(ficha).getByText('Vence')).toBeInTheDocument()
    expect(within(ficha).getByText('Tipo de cargo')).toBeInTheDocument()
    // Y el desglose del importe, que no se veía en NINGUNA pantalla.
    expect(within(ficha).getByText('Importe base')).toBeInTheDocument()
    expect(within(ficha).getByText('Bonificación')).toBeInTheDocument()
    expect(within(ficha).getByText('Impuestos')).toBeInTheDocument()
    expect(within(ficha).getByText(/Se pactó bonificación/)).toBeInTheDocument()
  })

  it('los ajustes en cero no ocupan un renglón', async () => {
    // El control del caso de arriba: la ficha no lista siempre los cuatro. El
    // interés por mora es 0 en la cuota completa, así que no tiene que estar —
    // y bonificación e impuestos, que no son 0, sí están (test anterior).
    const user = await montar()
    await user.click(screen.getByText('CTR-00000001').closest('tr')!)

    const ficha = await screen.findByRole('dialog')
    expect(within(ficha).queryByText('Interés por mora')).toBeNull()
  })

  it('🔴 tildar una cuota NO abre la ficha, pero el resto de la fila sí', async () => {
    // La trampa del `onRowClick` de libra-ui: ignora `button` y `a`, pero no
    // `input`. Sin el `stopPropagation` del casillero, elegir una cuota para el
    // remito abriría el modal encima.
    const user = await montar()
    await user.click(screen.getByRole('checkbox', { name: /Elegir la cuota/ }))

    expect(screen.queryByRole('dialog')).toBeNull()
    // Y el tilde sí hizo lo suyo: la barra del remito apareció.
    expect(await screen.findByRole('button', { name: /Generar remito/ })).toBeInTheDocument()

    // 🔑 La segunda mitad es la que hace que la ausencia de arriba signifique
    // algo: sin ella, este test pasaría igual con el `onRowClick` sacado de
    // cuajo — que es exactamente lo que pasaba antes de este cambio.
    await user.click(screen.getByText('CTR-00000001').closest('tr')!)
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })
})

// ── 2. La columna "Acciones" de listas de precios ──────────────────────────

const SUCURSALES = [{ id: 1, nombre: 'Chivilcoy', codigo: 'CHI', direccion: '' }]

const LISTA = {
  id: 3, nombre: 'Mayorista', descripcion: 'Precios de mostrador',
  activa: true, es_default: true, items: 1,
}

const PRECIO = {
  id: 8, item_id: 40, producto: 'Plug RJ45',
  precio: 1500, costo: 1000, margen_pct: 50,
  propio_de_sucursal: true, sucursal_id: 1, sucursal: 'Chivilcoy',
}

describe('La columna "Acciones" de listas de precios', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url)
      if (u.includes('/precios')) return Promise.resolve(json([PRECIO]))
      if (u.includes('/api/listas-precio')) return Promise.resolve(json([LISTA]))
      if (u.includes('/api/sucursales')) return Promise.resolve(json(SUCURSALES))
      return Promise.resolve(json([]))
    }))
    // Con una sucursal activa la fila trae además el botón de quitar el precio
    // propio: es el otro que decía una palabra en vez de dibujar algo.
    localStorage.setItem('libradesk.sucursal_activa', '1')
  })

  afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

  /** Abre la lista y devuelve la tabla de precios. */
  async function abrirLista() {
    const user = userEvent.setup()
    renderRTL(
      <MemoryRouter><SucursalProvider><ListasPrecio /></SucursalProvider></MemoryRouter>,
    )
    await user.click(await screen.findByText('Mayorista'))
    await waitFor(() => expect(screen.getByText('Plug RJ45')).toBeTruthy())
    // La segunda tabla de la pantalla: la primera es el listado de listas.
    const tablas = screen.getAllByRole('table')
    return tablas[tablas.length - 1]
  }

  it('el título va sobre los botones, no contra el margen izquierdo', async () => {
    const tabla = await abrirLista()
    const encabezado = within(tabla).getByText('Acciones')

    // La celda de los botones ya los mandaba a la derecha con `justify-end`; lo
    // que faltaba era que la columna alineara su título igual.
    expect(encabezado.className).toMatch(/\btext-right\b/)
  })

  it('🔴 editar es el lápiz, no la palabra "Editar"', async () => {
    const tabla = await abrirLista()

    const editar = within(tabla).getByRole('button', {
      name: 'Editar el precio de Plug RJ45',
    })
    // Que dibuje algo, y no que simplemente tenga otro nombre accesible: sin
    // esto, un botón vacío con `aria-label` pasaría igual.
    expect(editar.querySelector('svg')).not.toBeNull()
    expect(editar.textContent).toBe('')
  })

  it('quitar el precio propio también dibuja, y dice de qué sucursal', async () => {
    const tabla = await abrirLista()

    const quitar = within(tabla).getByRole('button', {
      name: 'Quitar el precio propio de Plug RJ45 en Chivilcoy',
    })
    expect(quitar.querySelector('svg')).not.toBeNull()
    expect(quitar.textContent).toBe('')
  })

  it('y el lápiz sigue abriendo el diálogo del precio', async () => {
    // El control de las dos de arriba: cambiar el contenido del botón no sirve
    // de nada si de paso se pierde el `DialogTrigger`.
    const user = userEvent.setup()
    const tabla = await abrirLista()

    await user.click(within(tabla).getByRole('button', {
      name: 'Editar el precio de Plug RJ45',
    }))

    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText('Plug RJ45')).toBeInTheDocument()
  })
})
