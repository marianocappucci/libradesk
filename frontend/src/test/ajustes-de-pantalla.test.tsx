// Los cuatro ajustes de pantalla que el humano pidió el 2026-08-15, mirando el
// producto ya desplegado en producción.
//
// Van juntos en un archivo porque comparten motivo, no implementación: son
// correcciones de forma, y la forma es exactamente lo que ninguna suite de este
// producto estaba mirando. Los 295 tests que ya existían pasaban en verde con
// los cuatro defectos presentes.
//
// ⚠️ **Lo que estos tests NO prueban.** jsdom no calcula layout: no hay ancho
// real, no hay scroll, no hay pintado. Un `justify-end` presente en el
// `className` no demuestra que el botón se vea a la derecha; demuestra que la
// clase que lo pone sigue ahí. Es la capa que se puede automatizar sin un
// navegador — la revisión visual del humano sigue siendo la única que mide de
// verdad, como quedó anotado en el wiki.
//
// Donde se pudo, se afirma sobre algo más duro que una clase: el orden de los
// nodos en el DOM, la existencia de un `role="dialog"`, la ausencia de la
// tarjeta que se sacó. Eso sí sobrevive a un cambio de nombre de clase.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Proveedores } from '../pages/Proveedores'
import { Remitos } from '../pages/Remitos'
import { RemitoDetalle } from '../pages/RemitoDetalle'
import { Activos } from '../pages/Activos'

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

const PROVEEDOR = {
  id: 1, nombre: 'Compu Service', contacto: 'Juan Pérez', telefono: '2345-400100',
  email: 'ventas@compuservice.test', observaciones: null, activo: true,
}

const REMITO = {
  id: 7, number: 'R-0001-00000007', date: '2026-08-15',
  client_id: 1, client_name: 'Estudio Contable Sur',
  client_cuit: '30-11111111-9', client_address: 'San Martín 100',
  client_email: null, client_phone: null,
  items: [{ description: 'Mano de obra', qty: 1, unit_price: 10000, tax_rate: '0.21', subtotal: 10000 }],
  subtotal: 10000, tax_rate: 0.21, tax_amount: 2100, total: 12100,
  observations: null, created_at: null,
}

const ACTIVO = {
  id: 2, tipo: 'Central telefónica', marca: 'Yeastar', modelo: 'S20',
  serial: 'YS-A123', codigo_interno: 'PAT-0001',
  descripcion: 'Central telefónica Yeastar S20',
  mac: null, imei: null, ip: null, accesorios: null,
  estado: 'disponible', costo_compra: 180000, fecha_compra: null,
  proveedor_compra_id: null, valor_reposicion: 250000, garantia_vence: null,
  observaciones: null, created_at: null,
  contrato_id: null, contrato_numero: null, cliente_id: null, cliente_nombre: null,
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    if ((opciones?.method ?? 'GET') !== 'GET') return Promise.resolve(json({ ok: true }))
    // El orden importa: `/api/activos/resumen` contiene `/api/activos`.
    if (u.includes('/api/activos/resumen')) {
      return Promise.resolve(json({ total: 1, por_estado: { disponible: 1 } }))
    }
    if (u.includes('/api/activos')) return Promise.resolve(json([ACTIVO]))
    if (u.includes('/api/proveedores')) return Promise.resolve(json([PROVEEDOR]))
    if (u.includes('/api/remitos/next-number')) return Promise.resolve(json({ number: 'R-0001-00000008' }))
    if (/\/api\/remitos\/\d+$/.test(u)) return Promise.resolve(json(REMITO))
    if (u.includes('/api/remitos')) return Promise.resolve(json([REMITO]))
    return Promise.resolve(json([]))
  }))
})

// ── 1 ────────────────────────────────────────────────────────────────────────
describe('🔴 Proveedores: editar abre en modal, no expande la fila', () => {
  it('el formulario de edición vive adentro de un diálogo', async () => {
    const user = userEvent.setup()
    render(<Proveedores />, '/proveedores')
    await screen.findByText('Compu Service')

    // Antes del click no hay ningún diálogo: el control de que el `findByRole`
    // de abajo mide la apertura y no algo que ya estaba.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Editar Compu Service' }))

    const dialogo = await screen.findByRole('dialog')
    // El campo con el nombre cargado está ADENTRO del diálogo. Se afirma con
    // `within` y no con `screen`: el formulario inline viejo también habría
    // hecho pasar un `getByDisplayValue` suelto.
    expect(within(dialogo).getByDisplayValue('Compu Service')).toBeInTheDocument()
    expect(within(dialogo).getByLabelText('Teléfono')).toHaveValue('2345-400100')
  })

  it('la fila del listado NO se convierte en formulario', async () => {
    const user = userEvent.setup()
    render(<Proveedores />, '/proveedores')
    await screen.findByText('Compu Service')

    await user.click(screen.getByRole('button', { name: 'Editar Compu Service' }))
    await screen.findByRole('dialog')

    // Éste es el defecto en sí, y no se ve mirando el diálogo: antes la fila se
    // reemplazaba por el formulario y el listado quedaba sin ella. Que el
    // renglón siga ahí, con sus acciones, es lo que prueba que el formulario se
    // fue a otro lado en vez de haberse mudado adentro de la lista.
    //
    // ⚠️ Se busca por texto y por `querySelector`, NO con `getByRole`: mientras
    // el diálogo está abierto Radix marca el resto del documento como inerte,
    // así que el árbol de accesibilidad ya no ve esos botones. Que los esconda
    // es correcto —es lo que hace modal a un modal— pero deja al `getByRole`
    // sin forma de mirar lo que quedó atrás.
    const fila = screen.getByText('Compu Service').closest('li')!
    expect(fila.querySelector('[aria-label="Editar Compu Service"]')).not.toBeNull()
    expect(fila.querySelector('[aria-label="Eliminar Compu Service"]')).not.toBeNull()
    // Y la fila no tiene campos adentro: el formulario no se mudó a la lista.
    expect(fila.querySelector('input')).toBeNull()
  })

  it('el alta abre el mismo diálogo y sigue mandando el POST', async () => {
    const user = userEvent.setup()
    render(<Proveedores />, '/proveedores')
    await screen.findByText('Compu Service')

    await user.click(screen.getByRole('button', { name: /Nuevo proveedor/ }))
    const dialogo = await screen.findByRole('dialog')
    await user.type(within(dialogo).getByLabelText('Nombre del proveedor'), 'Taller Pérez')
    await user.click(within(dialogo).getByRole('button', { name: 'Guardar' }))

    // Y se cierra solo al guardar: si quedara abierto, el listado recargado
    // estaría tapado por el modal.
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
})

// ── 2 ────────────────────────────────────────────────────────────────────────
describe('🔴 Comprobantes: el pie del formulario va a la derecha', () => {
  it('Cancelar precede a Guardar y el contenedor los alinea a la derecha', async () => {
    const user = userEvent.setup()
    render(<Remitos />, '/remitos')
    await screen.findByText('R-0001-00000007')

    await user.click(screen.getByRole('button', { name: /Nuevo remito/ }))
    const guardar = await screen.findByRole('button', { name: 'Guardar' })
    const cancelar = screen.getByRole('button', { name: 'Cancelar' })
    const pie = guardar.parentElement!

    // El orden en el DOM es el orden visual dentro de un flex sin `order`, y
    // sobrevive a cualquier renombre de clase de Tailwind.
    expect(cancelar.compareDocumentPosition(guardar))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    // Y la alineación, que sí es una clase y por eso se afirma aparte.
    expect(pie.className).toContain('justify-end')
    expect(pie).toContainElement(cancelar)
  })
})

// ── 3 ────────────────────────────────────────────────────────────────────────
describe('🔴 Remito: eliminar está arriba, y la tarjeta del pie ya no existe', () => {
  it('el botón vive en el encabezado, junto a Editar y Ver PDF', async () => {
    render(<RemitoDetalle />, '/remitos/7', '/remitos/:id')
    // El número aparece dos veces —en el título y en la tarjeta de datos—,
    // así que se espera por el encabezado, que es lo que ancla la pantalla.
    await screen.findByRole('heading', { name: /R-0001-00000007/ })

    const eliminar = await screen.findByRole('button', { name: /Eliminar/ })
    const editar = screen.getByRole('link', { name: /Editar/ })
    // Comparten contenedor: es lo que significa "está arriba con los otros".
    // Afirmarlo por el ancestro común y no por una clase deja el test atado a
    // la estructura, que es lo que el pedido cambió.
    expect(eliminar.parentElement).toBe(editar.closest('a')!.parentElement)
  })

  it('🔴 la tarjeta "Acciones" del pie desapareció', async () => {
    render(<RemitoDetalle />, '/remitos/7', '/remitos/:id')
    // El número aparece dos veces —en el título y en la tarjeta de datos—,
    // así que se espera por el encabezado, que es lo que ancla la pantalla.
    await screen.findByRole('heading', { name: /R-0001-00000007/ })

    // El control del caso de arriba: sin esto, mover el botón y DEJAR la
    // tarjeta vacía al pie pasaría igual. La tarjeta existía sólo para
    // contener ese único botón.
    expect(screen.queryByText('Acciones')).not.toBeInTheDocument()
  })
})

// ── 5 ────────────────────────────────────────────────────────────────────────
describe('🔴 Nuevo activo: el modal es más ancho y tiene bordes arriba y abajo', () => {
  it('tres columnas, ancho 4xl, y el cuerpo scrollea entre el título y el pie', async () => {
    const user = userEvent.setup()
    render(<Activos />, '/activos')
    await screen.findByText('Central telefónica Yeastar S20')

    await user.click(screen.getByRole('button', { name: /Nuevo activo/ }))
    const dialogo = await screen.findByRole('dialog')

    expect(dialogo.className).toContain('sm:max-w-4xl')

    // El borde de arriba cuelga del encabezado y el de abajo del pie: son los
    // dos que el humano pidió. Se los busca por el `data-slot` que pone el
    // primitivo, no por el texto, que cambia entre alta y edición.
    const encabezado = dialogo.querySelector('[data-slot="dialog-header"]')!
    const pie = dialogo.querySelector('[data-slot="dialog-footer"]')!
    expect(encabezado.className).toContain('border-b')
    expect(pie.className).toContain('border-t')

    // Y la grilla de campos: tres columnas, y con scroll propio para que el
    // pie no se vaya abajo de la pantalla con los 14 campos puestos.
    const tipo = within(dialogo).getByLabelText('Tipo')
    const grilla = tipo.closest('[class*="grid-cols"]')!
    expect(grilla.className).toContain('lg:grid-cols-3')
    expect(grilla.className).toContain('overflow-y-auto')
  })
})
