// Las actas en la ficha del contrato — fase 3 (2026-08-17).
//
// Lo que estos tests fijan, en orden de importancia:
//
// 1. 🔴 **La pantalla no ofrece lo que el backend rechaza.** Una devolución
//    sólo puede documentar equipos que ya figuran retirados, y una entrega no
//    lleva faltantes ni cargo. Ofrecerlos sería ofrecer un 409, y el operador
//    se entera recién después de tipear el acta entera.
// 2. **Los campos son de cada equipo**, no del acta: dos equipos elegidos dan
//    dos juegos de campos, y el POST manda dos líneas distintas. Es la
//    corrección al diseño del 2026-08-04 y lo único que esta pantalla no puede
//    perder.
// 3. **Cambiar el tipo limpia la selección.** Sin eso arrastra una línea que el
//    backend va a rechazar por un motivo que no se ve en pantalla.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ContratoDetalle } from '../pages/ContratoDetalle'

const LINEA_PUESTA = {
  id: 10, contrato_id: 1, activo_id: 5,
  activo_descripcion: 'Central telefónica Yeastar S20',
  activo_serial: 'YS-A123', activo_codigo_interno: 'PAT-0001',
  fecha_instalacion: '2026-08-01', fecha_retiro: null, vigente: true,
  motivo_retiro: null, reemplaza_a_id: null, tecnico_instalador_id: null,
  incidencia_id: null, ubicacion: 'Administración', observaciones: null,
}

/** El que ya volvió: es el único que una devolución puede documentar. */
const LINEA_RETIRADA = {
  ...LINEA_PUESTA,
  id: 11, activo_id: 6,
  activo_descripcion: 'Teléfono IP Grandstream GXP1625',
  activo_serial: 'GS-A123', activo_codigo_interno: 'PAT-0002',
  fecha_retiro: '2026-08-20', vigente: false, motivo_retiro: 'devolucion',
}

const CONTRATO = {
  id: 1, numero: 'CTR-00000001', tipo_contrato: 'alquiler',
  cliente_id: 3, cliente_nombre: 'Estudio Contable Sur',
  propietario_cliente_id: null, propietario_nombre: null,
  sector_id: null, domicilio_instalacion: 'Belgrano 450',
  fecha_inicio: '2026-08-01', fecha_fin: null, renovacion_automatica: false,
  periodicidad: 'mensual', frecuencia_visita: null, primera_visita: null,
  dia_vencimiento: 10, moneda: 'ARS', metodo_actualizacion: 'manual',
  estado: 'activo', responsable: null, observaciones: null, archivo_pdf: null,
  created_at: null, importe_vigente: 45000, precio_vigente_desde: '2026-08-01',
  lleva_cuota: true, equipos_vigentes: 1,
  lineas: [LINEA_PUESTA, LINEA_RETIRADA],
  precios: [],
}

const ACTA_EMITIDA = {
  id: 7, numero: 'ACT-00000001', contrato_id: 1,
  contrato_numero: 'CTR-00000001', cliente_nombre: 'Estudio Contable Sur',
  tipo: 'entrega', fecha: '2026-08-03',
  entrega_nombre: 'Rubén Ferreyra', recibe_nombre: 'Marta Ojeda',
  observaciones: null, estado: 'emitida', anulada: false, cuota_id: null,
  usuario: 'admin', created_at: null,
  lineas: [{
    id: 1, acta_id: 7, contrato_equipo_id: LINEA_PUESTA.id, activo_id: 5,
    activo_descripcion: LINEA_PUESTA.activo_descripcion,
    activo_serial: 'YS-A123', activo_codigo_interno: 'PAT-0001',
    estado_fisico: 'Impecable', accesorios: 'Fuente 12V',
    faltantes: null, danios: null, cargo_reposicion: null, observaciones: null,
  }],
  equipos: 1, cargo_total: 0,
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

const render = () => renderRTL(
  <MemoryRouter initialEntries={['/contratos/1']}>
    <Routes><Route path="/contratos/:id" element={<ContratoDetalle />} /></Routes>
  </MemoryRouter>,
)

let posts: { url: string; cuerpo: any }[] = []
let actas: unknown[] = []

beforeEach(() => {
  posts = []
  actas = []
  vi.stubGlobal('open', vi.fn())
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    if ((init?.method ?? 'GET') !== 'GET') {
      posts.push({ url: u, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
      return Promise.resolve(json({ id: 8, numero: 'ACT-00000002' }))
    }
    // El orden importa: `/api/contratos/1/actas` contiene `/api/contratos/1`.
    if (u.includes('/actas')) return Promise.resolve(json(actas))
    if (u.includes('/api/contratos/1')) return Promise.resolve(json(CONTRATO))
    return Promise.resolve(json([]))
  }))
})

/**
 * Entra a la pestaña de actas. Desde el 2026-08-17 la ficha va en pestañas y
 * Radix monta **sólo la activa**, así que la tarjeta no está en el DOM hasta
 * entrar — que es también lo que hace un operador.
 */
async function irAActas(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('tab', { name: 'Actas' })
  await user.click(screen.getByRole('tab', { name: 'Actas' }))
  return screen.findByText('Actas de entrega y devolución')
}

/** Abre el diálogo de «Nueva acta» ya cargada la ficha. */
async function abrirDialogo(user: ReturnType<typeof userEvent.setup>) {
  await irAActas(user)
  await user.click(screen.getByRole('button', { name: /Nueva acta/ }))
  return screen.findByRole('dialog', { name: /Acta de entrega o devolución/ })
}

async function elegirTipo(
  user: ReturnType<typeof userEvent.setup>, dialogo: HTMLElement, opcion: RegExp,
) {
  await user.click(within(dialogo).getByRole('combobox'))
  await user.click(await screen.findByRole('option', { name: opcion }))
}

describe('La tarjeta de actas', () => {
  it('sin actas dice para qué sirve, y no finge que falta un dato', async () => {
    const user = userEvent.setup()
    render()
    await irAActas(user)
    expect(await screen.findByText(/Sin actas todavía/)).toBeInTheDocument()
  })

  it('un contrato sin equipos no tiene ni la pestaña', async () => {
    // El caso es el abono de mantenimiento, que es un contrato **sin equipos**:
    // ofrecerle «el papel que prueba que el equipo se entregó» describe algo
    // que en ese contrato no pasa.
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url)
      if (u.includes('/actas')) return Promise.resolve(json([]))
      if (u.includes('/api/contratos/1')) {
        return Promise.resolve(json({ ...CONTRATO, tipo_contrato: 'abono', lineas: [] }))
      }
      return Promise.resolve(json([]))
    }))
    render()
    await screen.findByRole('tab', { name: 'Contrato' })

    expect(screen.queryByRole('tab', { name: 'Actas' })).not.toBeInTheDocument()
    expect(screen.queryByText('Actas de entrega y devolución')).not.toBeInTheDocument()
  })

  it('el cargo se muestra con centavos, como en el PDF', async () => {
    // 🔴 Sin esto la pantalla dice `$ 7.501` y el acta que firma el cliente
    // dice `$ 7.500,50`: dos números para el mismo cargo. Se encontró mirando
    // la tabla en el navegador, no en un test.
    actas = [{ ...ACTA_EMITIDA, cargo_total: 7500.5 }]
    const user = userEvent.setup()
    render()
    await irAActas(user)

    expect(await screen.findByText('$ 7.500,50')).toBeInTheDocument()
  })

  it('lista el acta con su número y el PDF apunta a esa acta', async () => {
    actas = [ACTA_EMITIDA]
    const user = userEvent.setup()
    render()
    await irAActas(user)

    expect(await screen.findByText('ACT-00000001')).toBeInTheDocument()
    expect(screen.getByText('Entrega')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /PDF/ })).toHaveAttribute(
      'href', '/api/contratos/actas/7/pdf',
    )
  })

  it('anular pega en el endpoint del acta', async () => {
    actas = [ACTA_EMITIDA]
    const user = userEvent.setup()
    render()
    await irAActas(user)
    await screen.findByText('ACT-00000001')

    await user.click(screen.getByRole('button', { name: /Anular/ }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toContain('/api/contratos/actas/7/anular')
  })

  it('una anulada no ofrece anular de nuevo, y se ve que lo está', async () => {
    actas = [{ ...ACTA_EMITIDA, estado: 'anulada', anulada: true }]
    const user = userEvent.setup()
    render()
    await irAActas(user)
    await screen.findByText('ACT-00000001')

    expect(screen.getByText('Anulada')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Anular/ })).not.toBeInTheDocument()
  })
})

describe('🔴 La pantalla no ofrece lo que el backend rechaza', () => {
  it('la devolución sólo ofrece los equipos que ya figuran retirados', async () => {
    // La invariante del módulo: un equipo que el contrato tiene instalado no
    // se puede haber devuelto. Si esto fallara, el operador tipea el acta
    // entera y recién ahí se come el 409.
    const user = userEvent.setup()
    render()
    const dialogo = await abrirDialogo(user)

    // En entrega están los dos.
    expect(within(dialogo).getByLabelText(/Incluir Central/)).toBeInTheDocument()
    expect(within(dialogo).getByLabelText(/Incluir Teléfono/)).toBeInTheDocument()

    await elegirTipo(user, dialogo, /Devolución/)

    expect(within(dialogo).queryByLabelText(/Incluir Central/)).not.toBeInTheDocument()
    expect(within(dialogo).getByLabelText(/Incluir Teléfono/)).toBeInTheDocument()
  })

  it('la entrega no pide faltantes ni cargo, y no los manda', async () => {
    const user = userEvent.setup()
    render()
    const dialogo = await abrirDialogo(user)

    await user.click(within(dialogo).getByLabelText(/Incluir Central/))
    expect(within(dialogo).queryByText('Faltantes')).not.toBeInTheDocument()
    expect(within(dialogo).queryByText('Cargo de reposición')).not.toBeInTheDocument()

    await user.click(within(dialogo).getByRole('button', { name: /Emitir acta/ }))
    await waitFor(() => expect(posts).toHaveLength(1))
    // No alcanza con que no se pidan en pantalla: el POST tampoco los lleva.
    expect(posts[0].cuerpo.lineas[0]).not.toHaveProperty('faltantes')
    expect(posts[0].cuerpo.lineas[0]).not.toHaveProperty('cargo_reposicion')
  })

  it('un equipo que ya tiene acta viva del mismo tipo no se puede volver a elegir', async () => {
    actas = [ACTA_EMITIDA]
    const user = userEvent.setup()
    render()
    const dialogo = await abrirDialogo(user)

    expect(within(dialogo).getByLabelText(/Incluir Central/)).toBeDisabled()
    // Se muestra marcado y no se esconde: que el papel ya exista es
    // información, igual que los períodos ya agendados en «Generar visitas».
    expect(within(dialogo).getByText(/Ya tiene acta de entrega/)).toBeInTheDocument()
  })

  it('una acta anulada libera el equipo', async () => {
    actas = [{ ...ACTA_EMITIDA, estado: 'anulada', anulada: true }]
    const user = userEvent.setup()
    render()
    const dialogo = await abrirDialogo(user)

    expect(within(dialogo).getByLabelText(/Incluir Central/)).toBeEnabled()
  })
})

describe('Los campos son de cada equipo', () => {
  it('dos equipos elegidos dan dos líneas, cada una con lo suyo', async () => {
    const user = userEvent.setup()
    render()
    const dialogo = await abrirDialogo(user)

    await user.click(within(dialogo).getByLabelText(/Incluir Central/))
    await user.click(within(dialogo).getByLabelText(/Incluir Teléfono/))

    const estados = within(dialogo).getAllByRole('textbox').filter(
      (el) => el.tagName === 'TEXTAREA',
    )
    // Dos equipos × (estado físico + accesorios) + las observaciones del acta.
    expect(estados.length).toBeGreaterThanOrEqual(5)

    await user.click(within(dialogo).getByRole('button', { name: /Emitir acta de 2 equipos/ }))
    await waitFor(() => expect(posts).toHaveLength(1))

    const ids = posts[0].cuerpo.lineas.map((l: any) => l.contrato_equipo_id)
    expect(ids).toEqual([LINEA_PUESTA.id, LINEA_RETIRADA.id])
  })

  it('la devolución manda el cargo como número y avisa cuánto se va a cobrar', async () => {
    const user = userEvent.setup()
    render()
    const dialogo = await abrirDialogo(user)
    await elegirTipo(user, dialogo, /Devolución/)

    await user.click(within(dialogo).getByLabelText(/Incluir Teléfono/))
    await user.type(within(dialogo).getByRole('spinbutton'), '7500.5')

    // El aviso existe porque el acta emite una cuota de verdad: sin decirlo,
    // el cargo aparece en el devengado sin que nadie lo haya pedido a la vista.
    // `/Se va a emitir/` y no `/cargo de reposición/`: esa frase también es la
    // etiqueta del campo, y el matcher devolvía los dos.
    expect(await within(dialogo).findByText(/Se va a emitir un cargo/i)).toBeInTheDocument()

    await user.click(within(dialogo).getByRole('button', { name: /Emitir acta/ }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].cuerpo.lineas[0].cargo_reposicion).toBe(7500.5)
  })

  it('cambiar el tipo limpia la selección', async () => {
    // Sin esto queda elegido un equipo que el otro tipo no admite, y se manda
    // una línea que el backend rechaza por un motivo invisible en pantalla.
    const user = userEvent.setup()
    render()
    const dialogo = await abrirDialogo(user)

    await user.click(within(dialogo).getByLabelText(/Incluir Teléfono/))
    expect(within(dialogo).getByRole('button', { name: /Emitir acta de 1 equipo/ }))
      .toBeEnabled()

    await elegirTipo(user, dialogo, /Devolución/)

    expect(within(dialogo).getByLabelText(/Incluir Teléfono/)).not.toBeChecked()
    // Sin nada elegido el botón no nombra una cantidad: dice «Emitir acta» a
    // secas. Se afirma el nombre EXACTO —no un `/Emitir acta/` que también
    // matchearía «…de 1 equipo»— porque lo que se está probando es justamente
    // que la cuenta desapareció.
    expect(within(dialogo).getByRole('button', { name: 'Emitir acta' }))
      .toBeDisabled()
  })

  it('el botón no dice «0 equipos» cuando no hay ninguno elegido', async () => {
    // Deshabilitado no alcanza: el texto nombraba una cantidad donde todavía no
    // hay ninguna, y eso se lee como un error de la máquina.
    const user = userEvent.setup()
    render()
    const dialogo = await abrirDialogo(user)

    expect(within(dialogo).getByRole('button', { name: 'Emitir acta' })).toBeDisabled()
    expect(within(dialogo).queryByText(/0 equipos/)).not.toBeInTheDocument()

    // Y con uno elegido vuelve a contar, que es cuando la cuenta sirve.
    await user.click(within(dialogo).getByLabelText(/Incluir Central/))
    expect(within(dialogo).getByRole('button', { name: 'Emitir acta de 1 equipo' }))
      .toBeEnabled()
  })

  it('emitir abre el PDF del acta recién creada', async () => {
    const user = userEvent.setup()
    render()
    const dialogo = await abrirDialogo(user)

    await user.click(within(dialogo).getByLabelText(/Incluir Central/))
    await user.click(within(dialogo).getByRole('button', { name: /Emitir acta/ }))

    await waitFor(() => expect(window.open).toHaveBeenCalledWith(
      '/api/contratos/actas/8/pdf', '_blank', 'noopener',
    ))
  })
})
