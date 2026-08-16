// El camino de una venta a facturación, en la ficha de la venta (2026-08-16).
//
// La bandeja de «Enviar a facturar» acepta **sólo remitos**, así que hasta hoy
// una venta no tenía ningún camino a la factura — mientras la pantalla decía lo
// contrario.
//
// Lo que hay que sostener acá:
//
// 1. 🔴 Que **con remito ya emitido el botón no vuelva a emitir**. Es el mismo
//    riesgo que tenía el de recibos: un botón que dice "generar" sobre algo que
//    ya existe emite un segundo comprobante en silencio.
// 2. 🔴 Que una venta **sin cliente pida a nombre de quién** antes de generar.
//    Un remito se emite a nombre de alguien.
// 3. Que con cliente en la venta **no pregunte nada** y genere directo.
// 4. Que la pantalla **ya no prometa** que la venta se manda sola a facturar.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { VentaDetalle, Ventas } from '../pages/VentasComercial'

const CLIENTES = [
  { id: 7, nombre: 'Juan Medici', empresa: 'NEUMYSER SRL', cuit: '30-11111111-7' },
  { id: 9, nombre: 'Ana Diaz', empresa: '', cuit: '' },
]

const BASE = {
  id: 3, numero: 'V-00000003', estado: 'confirmed', fecha: '2026-08-16',
  cliente_nombre: 'NEUMYSER SRL', notas: null, recibo_id: null,
  items: [{ descripcion: 'Central HiPath', cantidad: 1, precio: 200000, subtotal: 200000 }],
  pagos: [{ medio: 'efectivo', monto: 200000, referencia: '' }],
  subtotal: 200000, total: 200000,
}

const CON_CLIENTE = {
  ...BASE,
  cliente: { id: 7, nombre: 'Juan Medici', cuit: '30-11111111-7', domicilio: 'Av. 1' },
  remito_id: null,
}
const SIN_CLIENTE = { ...BASE, cliente: null, cliente_nombre: 'Consumidor final', remito_id: null }
const YA_REMITADA = { ...CON_CLIENTE, remito_id: 42 }

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let venta: unknown = CON_CLIENTE
let posteos: { url: string; body: unknown }[] = []

beforeEach(() => {
  venta = CON_CLIENTE
  posteos = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    if (init?.method === 'POST') {
      posteos.push({ url: u, body: init.body ? JSON.parse(String(init.body)) : {} })
      return Promise.resolve(json({ id: 99 }))
    }
    if (u.includes('/api/clientes')) return Promise.resolve(json(CLIENTES))
    // Sin anclar en `$`: la URL puede traer query string (sucursal), y con el
    // ancla caía en el listado de abajo y devolvía `[]` — o sea una "venta" sin
    // `pagos`, que revienta al render y no se parece en nada a la causa.
    if (/\/api\/ventas\/\d+/.test(u)) return Promise.resolve(json(venta))
    if (u.includes('/api/ventas')) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  }))
})

// Con `<Routes>/<Route>` y no `<VentaDetalle />` suelto: la ficha lee el id con
// `useParams()`, y sin la ruta declarada devuelve vacío — la pantalla termina
// pidiendo `/api/ventas/NaN` y el mock contesta otra cosa. El síntoma es un
// `datos.pagos is undefined` al render, que no se parece en nada a la causa.
const montar = () => render(
  <MemoryRouter initialEntries={['/ventas/3']}>
    <Routes><Route path="/ventas/:id" element={<VentaDetalle />} /></Routes>
  </MemoryRouter>,
)

describe('el remito de una venta', () => {
  it('🔴 con remito ya emitido, lleva a verlo y NO ofrece generar otro', async () => {
    venta = YA_REMITADA
    montar()

    expect(await screen.findByRole('link', { name: /Ver remito/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Generar remito/ })).not.toBeInTheDocument()
  })

  it('con cliente en la venta, genera sin preguntar nada', async () => {
    const user = userEvent.setup()
    montar()

    await user.click(await screen.findByRole('button', { name: /Generar remito/ }))

    await waitFor(() => expect(posteos).toHaveLength(1))
    expect(posteos[0].url).toContain('/api/ventas/3/convertir-en-remito')
    // Sin `cliente_id`: lo dice la venta, y mandarlo desde la pantalla abriría
    // la puerta a emitir a nombre de otro.
    expect(posteos[0].body).toEqual({})
  })

  it('🔴 sin cliente, pregunta a nombre de quién antes de generar', async () => {
    venta = SIN_CLIENTE
    const user = userEvent.setup()
    montar()

    await user.click(await screen.findByRole('button', { name: /Generar remito/ }))

    // El click abre el modal y **no** postea: es la mitad que importa.
    expect(posteos).toHaveLength(0)
    // Por rol y no por texto: «a nombre de» aparece en el título y otra vez en
    // la explicación, y `findByText` con dos coincidencias falla.
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByRole('combobox', { name: /Cliente/ })).toBeInTheDocument()
  })

  it('sin cliente, elegir uno lo manda en el cuerpo', async () => {
    venta = SIN_CLIENTE
    const user = userEvent.setup()
    montar()

    await user.click(await screen.findByRole('button', { name: /Generar remito/ }))
    const dialogo = await screen.findByRole('dialog')
    await user.click(within(dialogo).getByRole('combobox', { name: /Cliente/ }))
    // Acotado al `listbox`, como el resto de los tests de Select del producto:
    // una búsqueda global encuentra también el nombre dibujado en la ficha.
    await user.click(
      await within(await screen.findByRole('listbox')).findByRole('option', { name: /NEUMYSER/ }),
    )
    await user.click(within(dialogo).getByRole('button', { name: /Generar remito/ }))

    await waitFor(() => expect(posteos).toHaveLength(1))
    expect(posteos[0].body).toEqual({ cliente_id: 7 })
  })
})

describe('el texto de la pantalla de ventas', () => {
  it('🔴 ya no dice que la venta se manda sola a facturar', async () => {
    render(<MemoryRouter><Ventas /></MemoryRouter>)

    // Lo que tiene que decir es que hay que generar el remito. Asertar sobre el
    // texto nuevo y no sólo sobre la ausencia del viejo: «ya no está» pasaría en
    // verde también si la línea entera hubiera desaparecido.
    const nota = await screen.findByText(/Comprobante interno/)
    expect(nota.textContent).toMatch(/remito/i)
  })
})
