// Mover un equipo del depósito a un sector del cliente (2026-08-31).
//
// ## El reporte
//
// «Si voy a equipos y toco en la ficha de equipo, si está en depósito no me
// permite darlo de alta en ningún lado». Era cierto por dos motivos que se
// tapaban entre sí:
//
//   1. La ficha `/equipos/:id` no tenía **ninguna** acción — sólo imprimir y
//      volver—, así que desde donde se mira la trazabilidad no se podía
//      generar el movimiento siguiente.
//   2. El traslado existía sólo como efecto secundario de editar el equipo, y
//      había que cambiar dos campos que en ese formulario no se ven
//      relacionados: «Depósito = Ninguno» *y* «Sector». Escribir sólo el
//      sector guardaba un dato que no aparecía en ninguna pantalla, porque
//      `lugar_de()` muestra el depósito cuando hay uno.
//
// ## Lo que estos tests fijan, en orden de lo que puede romperse en silencio
//
// 1. **Que el traslado NO viaje por el `PUT` del equipo.** Es lo único que no
//    se ve: el equipo queda movido y correcto en la columna que uno mira,
//    mientras el payload completo le apagó la garantía o el dueño tercero. Ya
//    pasó dos veces en esta pantalla. Por eso el test mira el método y la URL
//    de la llamada, no el resultado en la grilla.
// 2. Que la ficha tenga el botón — el punto 1 del reporte.
// 3. Que un sector nuevo se registre en los del cliente, y que uno que ya
//    existe no se duplique.
// 4. Que la lista deje de pedir scroll horizontal.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Equipos } from '../pages/Equipos'
import { EquipoDetalle } from '../pages/EquipoDetalle'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'staff' }, loading: false }),
}))

const render = (ui: ReactElement, ruta: string, patron = '*') =>
  renderRTL(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes><Route path={patron} element={ui} /></Routes>
    </MemoryRouter>,
  )

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

const CLIENTE = {
  id: 1, nombre: 'Hospital Municipal Esteban Iribarne', empresa: null,
  email: null, telefono: null, ciudad: null, cuit: null, condicion_iva: null,
  domicilio: null, observaciones: null, tipo_facturacion: 'mensual',
  activo: true,
}

// Guardado en el pañol del hospital: el estado del que parte el reporte.
const EQUIPO = {
  id: 7, cliente_id: 1, tipo: 'Monitor multiparamétrico', modelo: 'uMEC12',
  marca: 'Mindray', serial: 'MP-1', ubicacion_oficina: null,
  sector: null, deposito_id: 4, deposito_nombre: 'Pañol',
  estado: 'almacenado', fecha_adicion: null,
  proveedor_id: null, proveedor_nombre: null, referencias: [],
  garantia_vence: '2027-05-30', observaciones: null,
}

const PANOL = {
  id: 4, nombre: 'Pañol', cliente_id: 1, cliente_nombre: 'Hospital',
  descripcion: null, activo: true, es_default: false, total_equipos: 1,
  created_at: null,
}
const TALLER = {
  ...PANOL, id: 5, nombre: 'Taller', cliente_id: null, cliente_nombre: null,
  es_default: true, total_equipos: 0,
}

const SECTOR_ADMISION = { id: 2, cliente_id: 1, nombre: 'Admisión' }

const FICHA = {
  equipo: { ...EQUIPO, descripcion: 'Monitor multiparamétrico Mindray uMEC12', lugar: 'Pañol', dias_garantia_restantes: 272 },
  cliente: {
    id: 1, nombre: 'Hospital Municipal Esteban Iribarne', empresa: null,
    telefono: null, email: null, ciudad: null, activo: true,
  },
  resumen: {
    total_incidencias: 0, incidencias_abiertas: 0, horas_invertidas: 0,
    total_reparaciones: 0, reparaciones_abiertas: 0, gastado_reparaciones: 0,
    dias_en_service: 0, total_movimientos: 1,
  },
  incidencias: [], reparaciones: [], movimientos: [],
}

/** Todas las llamadas que hizo la pantalla, para poder preguntar por método y
 *  URL y no sólo por lo que quedó en la grilla. */
let llamadas: { metodo: string; url: string; body: unknown }[]

beforeEach(() => {
  llamadas = []
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    const metodo = opciones?.method ?? 'GET'
    llamadas.push({
      metodo, url: u,
      body: opciones?.body ? JSON.parse(String(opciones.body)) : null,
    })
    if (metodo !== 'GET') return Promise.resolve(json(EQUIPO))
    if (u.includes('/api/clientes/condiciones-iva')) return Promise.resolve(json([]))
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    if (u.includes('/api/dashboard/equipo/')) return Promise.resolve(json(FICHA))
    if (u.includes('/api/sectores')) return Promise.resolve(json([SECTOR_ADMISION]))
    if (u.includes('/api/depositos')) return Promise.resolve(json([PANOL, TALLER]))
    if (u.includes('/api/equipos')) return Promise.resolve(json([EQUIPO]))
    return Promise.resolve(json([]))
  }))
})

/** Abre el diálogo desde la lista y deja elegida la pestaña del sector. */
async function abrirMoverAUnSector(user: ReturnType<typeof userEvent.setup>) {
  render(<Equipos />, '/equipos')
  await user.click(await screen.findByRole('button', { name: /Mover equipo/ }))
  const dialogo = await screen.findByRole('dialog')
  // El equipo está en un depósito, así que el diálogo abre en «A un sector»
  // solo. El click es explícito igual: si esa preselección cambia, este test
  // no debería empezar a probar otra cosa en silencio.
  await user.click(within(dialogo).getByRole('tab', { name: /sector del cliente/i }))
  return dialogo
}

const llamadasDeMover = () =>
  llamadas.filter((l) => l.url.includes('/mover'))

describe('el traslado no pasa por el PUT del equipo', () => {
  it('manda un POST a /mover con sólo la ubicación', async () => {
    const user = userEvent.setup()
    const dialogo = await abrirMoverAUnSector(user)

    await user.type(within(dialogo).getByLabelText('Sector'), 'Consultorios')
    await user.type(within(dialogo).getByLabelText(/Ubicación/), 'Consultorio 6')
    await user.type(within(dialogo).getByLabelText(/Motivo/), 'Se instala')
    await user.click(within(dialogo).getByRole('button', { name: /^Mover equipo$/ }))

    await waitFor(() => expect(llamadasDeMover()).toHaveLength(1))
    const mover = llamadasDeMover()[0]
    expect(mover.metodo).toBe('POST')
    expect(mover.url).toContain('/api/equipos/7/mover')
    expect(mover.body).toEqual({
      sector: 'Consultorios',
      ubicacion_oficina: 'Consultorio 6',
      motivo: 'Se instala',
    })

    // 🔴 Lo que de verdad se está fijando: que el payload no traiga el equipo
    // entero. Con las doce claves adentro el traslado sale igual de bien y
    // `garantia_vence` se apaga sin que nada lo muestre.
    expect(Object.keys(mover.body as object)).not.toContain('garantia_vence')
    expect(Object.keys(mover.body as object)).not.toContain('proveedor_id')
    expect(Object.keys(mover.body as object)).not.toContain('estado')

    // Y ningún PUT al equipo por el camino.
    expect(llamadas.filter((l) => l.metodo === 'PUT')).toHaveLength(0)
  })

  it('a un depósito manda el id y nada del sector', async () => {
    const user = userEvent.setup()
    render(<Equipos />, '/equipos')
    await user.click(await screen.findByRole('button', { name: /Mover equipo/ }))
    const dialogo = await screen.findByRole('dialog')
    await user.click(within(dialogo).getByRole('tab', { name: /dep[óo]sito/i }))

    await user.click(within(dialogo).getByRole('combobox', { name: 'Depósito' }))
    await user.click(await screen.findByRole('option', { name: /Taller/ }))
    await user.click(within(dialogo).getByRole('button', { name: /^Mover equipo$/ }))

    await waitFor(() => expect(llamadasDeMover()).toHaveLength(1))
    expect(llamadasDeMover()[0].body).toEqual({ deposito_id: 5, motivo: null })
  })
})

describe('los sectores del cliente', () => {
  it('un sector nuevo se registra para que la próxima vez se pueda elegir', async () => {
    const user = userEvent.setup()
    const dialogo = await abrirMoverAUnSector(user)

    await user.type(within(dialogo).getByLabelText('Sector'), 'Tomografía')
    await user.click(within(dialogo).getByRole('button', { name: /^Mover equipo$/ }))

    await waitFor(() => expect(llamadasDeMover()).toHaveLength(1))
    const alta = llamadas.filter(
      (l) => l.metodo === 'POST' && l.url.includes('/api/sectores'),
    )
    expect(alta).toHaveLength(1)
    expect(alta[0].body).toEqual({ cliente_id: 1, nombre: 'Tomografía' })
  })

  it('uno que ya existe no se vuelve a dar de alta', async () => {
    const user = userEvent.setup()
    const dialogo = await abrirMoverAUnSector(user)

    // «Admisión» ya está en los sectores del cliente. Escrito en minúscula a
    // propósito: la comparación no puede ser sensible a mayúsculas o cada
    // tipeo distinto crearía un sector nuevo, que es el problema que este
    // campo vino a resolver.
    await user.type(within(dialogo).getByLabelText('Sector'), 'admisión')
    await user.click(within(dialogo).getByRole('button', { name: /^Mover equipo$/ }))

    await waitFor(() => expect(llamadasDeMover()).toHaveLength(1))
    expect(llamadas.filter(
      (l) => l.metodo === 'POST' && l.url.includes('/api/sectores'),
    )).toHaveLength(0)
  })

  it('el interruptor apagado deja el traslado pero no crea el sector', async () => {
    const user = userEvent.setup()
    const dialogo = await abrirMoverAUnSector(user)

    await user.type(within(dialogo).getByLabelText('Sector'), 'Tomografía')
    await user.click(within(dialogo).getByRole('switch'))
    await user.click(within(dialogo).getByRole('button', { name: /^Mover equipo$/ }))

    await waitFor(() => expect(llamadasDeMover()).toHaveLength(1))
    expect(llamadas.filter(
      (l) => l.metodo === 'POST' && l.url.includes('/api/sectores'),
    )).toHaveLength(0)
  })
})

describe('la ficha del equipo', () => {
  it('tiene el botón de mover — era el punto 1 del reporte', async () => {
    const user = userEvent.setup()
    render(<EquipoDetalle />, '/equipos/7', '/equipos/:id')

    await user.click(await screen.findByRole('button', { name: /^Mover$/ }))
    const dialogo = await screen.findByRole('dialog')
    // Y sabe de dónde lo está sacando: sin eso el diálogo es el mismo para un
    // equipo guardado y para uno instalado.
    expect(within(dialogo).getByText(/Pañol \(depósito\)/)).toBeInTheDocument()
  })
})

describe('la lista entra en una pantalla normal', () => {
  it('no pide más ancho del que hay', async () => {
    render(<Equipos />, '/equipos')
    await screen.findByRole('table')

    // `DataTable` fija el `minWidth` de la tabla como la suma de los `size` de
    // las columnas que NO son `opcional`; si no entra, el contenedor scrollea.
    // Con la sidebar abierta el contenido es la ventana menos 352 px (medido,
    // ver `Cuotas.tsx`), así que el presupuesto en una pantalla de 1366 es
    // 1014 px. Antes de marcar marca/modelo/N° ajeno como opcionales, esta
    // tabla pedía 1322.
    //
    // ⚠️ El número que se lee acá es ~62 px MENOR que el del navegador: la
    // columna de acciones se mide con `getBoundingClientRect()`, que en jsdom
    // da 0, así que cae al default de TanStack (150) en vez de los 212 que
    // miden los cinco botones de verdad. Por eso el margen contra 1014 tiene
    // que ser holgado y no al ras.
    const tabla = screen.getByRole('table')
    const minimo = parseInt(tabla.style.minWidth, 10)
    expect(minimo).toBeGreaterThan(0)
    expect(minimo + 62).toBeLessThan(1014)
  })
})
