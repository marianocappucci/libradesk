// El alta de venta dejó de ser un modal (pedido del humano, 2026-09-08):
//
// > *"se abre una ventana modal para cargar la nueva venta cuando se tendría
// > que abrir la pantalla como cuando estamos generando un presupuesto, ya que
// > puede contener más de un ítem y en un modal es incómodo trabajar una
// > venta"*.
//
// Es el mismo cambio que ya se hizo con el alta de contrato el 2026-08-17, así
// que este archivo es el espejo de `contrato-alta-en-pagina.test.tsx`. Lo que
// fija:
//
// 1. **La lista navega, no abre un diálogo.** Es el cambio pedido, y sin
//    afirmarlo por la ausencia del diálogo un `<Dialog>` que quedara colgado
//    pasaría igual.
// 2. 🔴 **`/ventas/nueva` no cae en `/ventas/:id`.** Es la trampa de la ruta
//    nueva: si la capturara la de la ficha, la pantalla pediría
//    `/api/ventas/nueva` y el backend contestaría 422. Se afirma sobre las URLs
//    que se piden, no sobre lo que se ve.
// 3. **Varios ítems entran y cada uno muestra su importe.** Es el motivo del
//    pedido, y es lo que el modal no podía dar: tres cajas por línea sin rótulo
//    y sin subtotal.
// 4. **El aviso de los equipos dados de alta sobrevive a la navegación.** Antes
//    vivía en un `useState` de la lista porque el modal se cerraba encima; ahora
//    viaja en el estado de la navegación, que es lo único que queda cuando la
//    pantalla del formulario se desmonta.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Ventas, VentaDetalle, VentaNueva } from '../pages/VentasComercial'
import { SucursalProvider } from '@/components/sucursal'
import { escribirEn } from './escribir'

const VENTA = {
  id: 2, numero: 'V-00000002', fecha: '2026-09-08', cliente: 'Magnolia Suites S.A.',
  total: 362600, en_cuenta_corriente: 0, estado: 'confirmed', recibo_id: null,
}

const CLIENTE = {
  id: 3, nombre: 'Estudio Contable Sur', empresa: null, email: null, telefono: null,
  ciudad: null, cuit: null, condicion_iva: null, domicilio: null,
  observaciones: null, tipo_facturacion: 'por_servicio', activo: true,
}

const PRODUCTO = {
  id: 7, nombre: 'Central telefónica', activo: true, stock_minimo: 0,
  costo: 100000, precio: 150000, unidad: 'u', descripcion: '',
  categoria_id: null, categoria: '', codigo: 'CT-01', iva_rate: 0.21,
  es_equipo: true, stock: 4, bajo_minimo: false,
}

const DEPOSITO = {
  id: 1, nombre: 'Depósito central', activo: true, descripcion: '',
  es_default: true, sucursal_id: null, sucursal: '',
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

/** Las tres rutas en el MISMO orden que `App.tsx`. */
const render = (ruta: string) => renderRTL(
  <MemoryRouter initialEntries={[ruta]}>
    <SucursalProvider>
      <Routes>
        <Route path="/ventas" element={<Ventas />} />
        <Route path="/ventas/nueva" element={<VentaNueva />} />
        <Route path="/ventas/:id" element={<VentaDetalle />} />
      </Routes>
    </SucursalProvider>
  </MemoryRouter>,
)

let pedidos: string[] = []
let posts: { url: string; cuerpo: any }[] = []

beforeEach(() => {
  pedidos = []
  posts = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    pedidos.push(u)
    if ((init?.method ?? 'GET') !== 'GET') {
      posts.push({ url: u, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
      // Dos equipos: es lo que dispara el aviso de la lista.
      return Promise.resolve(json({ id: 9, numero: 'V-00000009', equipos_dados_de_alta: 2 }))
    }
    if (u.includes('/api/medios-pago')) {
      return Promise.resolve(json([
        { id: 'efectivo', label: 'Efectivo' },
        { id: 'cuenta_corriente', label: 'Cuenta corriente' },
      ]))
    }
    if (u.includes('/api/precios/resolver')) return Promise.resolve(json({ precio: 150000 }))
    if (u.includes('/api/consumibles')) return Promise.resolve(json([PRODUCTO]))
    if (u.includes('/api/depositos-stock')) return Promise.resolve(json([DEPOSITO]))
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    if (u.includes('/api/ventas')) return Promise.resolve(json([VENTA]))
    return Promise.resolve(json([]))
  }))
})

/** Deja la pantalla de alta con el depósito elegido y un producto cargado.
 *  Es el punto de partida de casi todos los casos. */
async function altaConUnProducto(user: ReturnType<typeof userEvent.setup>) {
  render('/ventas/nueva')
  await screen.findByRole('heading', { name: 'Nueva venta' })

  await user.click(screen.getByRole('combobox', { name: 'Depósito' }))
  await user.click(await screen.findByRole('option', { name: /Depósito central/ }))

  await user.click(screen.getByRole('combobox', { name: 'Producto del catálogo' }))
  await user.click(await screen.findByRole('option', { name: /Central telefónica/ }))
  await user.click(screen.getByRole('button', { name: 'Agregar' }))

  await screen.findByText('Central telefónica')
}

describe('La lista', () => {
  it('«Nueva venta» navega a la pantalla y no abre ningún diálogo', async () => {
    const user = userEvent.setup()
    render('/ventas')
    await screen.findByText('V-00000002')

    await user.click(screen.getByRole('button', { name: /Nueva venta/ }))

    expect(await screen.findByRole('heading', { name: 'Nueva venta' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('dejó de pedir el catálogo que sólo usaba el formulario', async () => {
    // Clientes, consumibles y depósitos los cargaba la lista para pasárselos al
    // modal. Con el formulario en su propia pantalla, esos tres GET son de la
    // pantalla que los usa: la lista de ventas los pedía en cada visita para
    // dibujar una tabla que no los mira.
    render('/ventas')
    await screen.findByText('V-00000002')

    expect(pedidos.filter((u) => u.includes('/api/clientes'))).toEqual([])
    expect(pedidos.filter((u) => u.includes('/api/consumibles'))).toEqual([])
    expect(pedidos.filter((u) => u.includes('/api/depositos-stock'))).toEqual([])
  })
})

describe('🔴 La ruta nueva no la captura la de la ficha', () => {
  it('entrar directo a /ventas/nueva no pide /api/ventas/nueva', async () => {
    render('/ventas/nueva')
    await screen.findByRole('heading', { name: 'Nueva venta' })

    // La ficha carga la venta apenas monta. Si `nueva` hubiera caído en el
    // parámetro, acá habría un GET a `/api/ventas/nueva` — que es un 422.
    expect(pedidos.filter((u) => u.includes('/api/ventas/nueva'))).toEqual([])
    // Y la ficha no se montó: su encabezado es «Venta <número>».
    expect(screen.queryByRole('heading', { name: /^Venta / })).not.toBeInTheDocument()
  })
})

describe('La pantalla de alta', () => {
  it('🔴 toma más de un ítem, y cada línea muestra su importe', async () => {
    // El motivo del pedido. En el modal las tres cajas de una línea no tenían
    // rótulo visible ni importe: con dos ítems ya había que sacar la
    // calculadora para saber si el total cerraba.
    const user = userEvent.setup()
    await altaConUnProducto(user)

    await user.click(screen.getByRole('button', { name: 'Servicio' }))
    await escribirEn(screen.getByLabelText('Descripción'), 'Instalación')
    const filas = screen.getAllByRole('row')
    // Encabezado + dos líneas.
    expect(filas).toHaveLength(3)

    await escribirEn(
      within(filas[2]).getByLabelText(/^Precio de/), '50000',
    )

    // El importe de cada línea, y el total abajo.
    // Por regex y no por el string exacto: pesos() arma el importe con
    // toLocaleString, que separa el signo de la cifra con un espacio duro.
    expect(within(filas[1]).getByText(/150\.000/)).toBeInTheDocument()
    await waitFor(() =>
      expect(within(filas[2]).getByText(/50\.000/)).toBeInTheDocument())
    expect(screen.getByText(/200\.000/)).toBeInTheDocument()
  })

  it('registra la venta y vuelve a la lista con el aviso de los equipos', async () => {
    const user = userEvent.setup()
    await altaConUnProducto(user)

    await user.click(screen.getByRole('button', { name: 'Registrar venta' }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toBe('/api/ventas')
    expect(posts[0].cuerpo.deposito_id).toBe(1)
    expect(posts[0].cuerpo.items).toHaveLength(1)
    expect(posts[0].cuerpo.items[0]).toMatchObject({ item_id: 7, cantidad: 1, precio: 150000 })

    // Termina en la lista, y el aviso del alta automática llegó con ella. Ese
    // dato no lo puede mostrar el formulario: en el momento en que existe, la
    // pantalla que lo pidió ya se desmontó.
    expect(await screen.findByText(/2 equipos/)).toBeInTheDocument()
    expect(screen.getByText('V-00000002')).toBeInTheDocument()
  })

  it('cada botón de quitar se lleva SU línea, con lo que se hubiera escrito', async () => {
    // Cada fila tiene su propio botón y su propio nombre accesible; lo que se
    // afirma es que el de arriba no arrastra a la de abajo.
    //
    // ⚠️ **Esto NO prueba la key estable (`uid`).** Se midió: con `key={i}` el
    // archivo entero pasa igual, porque los campos son controlados y React
    // repone el valor correcto aunque reuse el nodo de la fila de arriba. El
    // `uid` queda como la forma correcta de listar algo editable, no como el
    // arreglo de un defecto observable — y esta nota está para que nadie lo
    // lea como probado.
    const user = userEvent.setup()
    await altaConUnProducto(user)
    await user.click(screen.getByRole('button', { name: 'Servicio' }))
    await escribirEn(screen.getByLabelText('Descripción'), 'Instalación')

    await user.click(screen.getByRole('button', { name: 'Quitar Central telefónica' }))

    await waitFor(() =>
      expect(screen.queryByText('Central telefónica')).not.toBeInTheDocument())
    expect(screen.getByLabelText('Descripción')).toHaveValue('Instalación')
    // Encabezado + la línea que quedó.
    expect(screen.getAllByRole('row')).toHaveLength(2)
  })

  it('una venta en cuenta corriente sin cliente no se puede registrar', async () => {
    const user = userEvent.setup()
    await altaConUnProducto(user)

    await user.click(screen.getByRole('combobox', { name: 'Cómo se cobra' }))
    await user.click(await screen.findByRole('option', { name: 'Cuenta corriente' }))

    expect(await screen.findByText('Una venta en cuenta corriente necesita un cliente.'))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Registrar venta' })).toBeDisabled()
  })

  it('sin ítems no se puede registrar, y «Volver» no manda nada', async () => {
    const user = userEvent.setup()
    render('/ventas/nueva')
    await screen.findByRole('heading', { name: 'Nueva venta' })

    expect(screen.getByRole('button', { name: 'Registrar venta' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Volver' }))

    expect(await screen.findByText('V-00000002')).toBeInTheDocument()
    expect(posts).toHaveLength(0)
  })
})
