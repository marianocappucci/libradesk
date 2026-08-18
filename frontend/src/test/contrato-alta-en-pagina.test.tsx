// El alta de contrato dejó de ser un modal (pedido del humano, 2026-08-17).
//
// Lo que estos tests fijan:
//
// 1. **La lista navega, no abre un diálogo.** Es el cambio pedido, y sin
//    afirmarlo por la ausencia del diálogo un `<Dialog>` que quedara colgado
//    pasaría igual.
// 2. 🔴 **`/contratos/nuevo` no cae en `/contratos/:id`.** Es la trampa de la
//    ruta nueva: si la capturara la de la ficha, la pantalla pediría
//    `/api/contratos/nuevo` y el backend contestaría 422. Se afirma sobre las
//    URLs que se piden, no sobre lo que se ve.
// 3. **El bloque de cobro sigue atado a la modalidad**: un comodato con importe
//    es un 409 del backend, así que la pantalla no lo ofrece.
import { render as renderRTL, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Contratos } from '../pages/Contratos'
import { ContratoNuevo } from '../pages/ContratoNuevo'
import { ContratoDetalle } from '../pages/ContratoDetalle'

const CLIENTE = {
  id: 3, nombre: 'Estudio Contable Sur', email: null, telefono: null,
  cuit: null, domicilio: null, activo: true,
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

/** Las tres rutas en el MISMO orden que `App.tsx`. */
const render = (ruta: string) => renderRTL(
  <MemoryRouter initialEntries={[ruta]}>
    <Routes>
      <Route path="/contratos" element={<Contratos />} />
      <Route path="/contratos/nuevo" element={<ContratoNuevo />} />
      <Route path="/contratos/:id" element={<ContratoDetalle />} />
    </Routes>
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
      return Promise.resolve(json({ id: 42, numero: 'CTR-00000042' }))
    }
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    return Promise.resolve(json([]))
  }))
})

describe('La lista', () => {
  it('«Nuevo contrato» navega a la pantalla y no abre ningún diálogo', async () => {
    const user = userEvent.setup()
    render('/contratos')
    await screen.findByText('Equipos en alquiler')

    await user.click(screen.getByRole('button', { name: /Nuevo contrato/ }))

    // La pantalla nueva, con su encabezado propio.
    expect(await screen.findByRole('heading', { name: 'Nuevo contrato' }))
      .toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

describe('🔴 La ruta nueva no la captura la de la ficha', () => {
  it('entrar directo a /contratos/nuevo no pide /api/contratos/nuevo', async () => {
    render('/contratos/nuevo')
    await screen.findByRole('heading', { name: 'Nuevo contrato' })

    // La ficha carga el contrato apenas monta. Si `nuevo` hubiera caído en el
    // parámetro, acá habría un GET a `/api/contratos/nuevo` — que es un 422.
    expect(pedidos.filter((u) => u.includes('/api/contratos/nuevo'))).toEqual([])
    // Y la ficha no se montó. Se mira por sus **pestañas** y no por el título
    // "Datos del contrato": esta pantalla también tiene una tarjeta con ese
    // título, así que buscarlo daría verde con la ficha montada.
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  })
})

describe('La pantalla de alta', () => {
  it('🔴 «Crear contrato» está en el encabezado y aun así envía el formulario', async () => {
    // Vive **fuera** del `<form>`, así que lo ata el atributo `form={id}`. Sin
    // él el botón queda inerte y la pantalla no da ningún error: sólo no pasa
    // nada. Por eso se afirman las dos cosas —dónde está y que envía—, y no
    // sólo que el texto aparece en algún lado.
    const user = userEvent.setup()
    render('/contratos/nuevo')
    const boton = await screen.findByRole('button', { name: /Crear contrato/ })

    expect(boton.closest('form')).toBeNull()
    expect(boton).toHaveAttribute('form')
    // Y no quedó una segunda copia al pie.
    expect(screen.getAllByRole('button', { name: /Crear contrato/ })).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Cancelar' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('combobox', { name: 'Cliente (locatario)' }))
    await user.click(await screen.findByText('Estudio Contable Sur'))
    await user.click(boton)

    await waitFor(() => expect(posts).toHaveLength(1))
  })

  it('crea el contrato y se va a su ficha', async () => {
    const user = userEvent.setup()
    render('/contratos/nuevo')
    await screen.findByRole('heading', { name: 'Nuevo contrato' })

    // El cliente es el único campo obligatorio que no viene con default. Se lo
    // busca **por su nombre accesible**, que es lo que un lector de pantalla
    // anuncia: para `role="combobox"` el contenido no nombra al control, así
    // que sin el `ariaLabel` del `SelectBuscable` esta línea no lo encuentra —
    // y así estaba antes de esta pantalla. Las opciones no están en el DOM
    // hasta abrirlo.
    await user.click(screen.getByRole('combobox', { name: 'Cliente (locatario)' }))
    await user.click(await screen.findByText('Estudio Contable Sur'))
    await user.click(screen.getByRole('button', { name: /Crear contrato/ }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toBe('/api/contratos')
    expect(posts[0].cuerpo.cliente_id).toBe(3)
    expect(posts[0].cuerpo.tipo_contrato).toBe('alquiler')
    // `'ninguna'` es el centinela de pantalla; a la API va `null`.
    expect(posts[0].cuerpo.frecuencia_visita).toBeNull()

    // Y termina en la ficha del creado, no de vuelta en la lista.
    await waitFor(() => expect(
      pedidos.some((u) => u.includes('/api/contratos/42')),
    ).toBe(true))
  })

  it('sin cliente no se manda nada, y lo dice', async () => {
    const user = userEvent.setup()
    render('/contratos/nuevo')
    await screen.findByRole('heading', { name: 'Nuevo contrato' })

    await user.click(screen.getByRole('button', { name: /Crear contrato/ }))

    // Se busca el mensaje del formulario por su `data-slot` y no por el texto:
    // el mensaje de zod dice lo mismo que el placeholder del campo, así que un
    // `findByText` encuentra dos elementos y falla por ambigüedad.
    await waitFor(() => expect(
      document.querySelector('[data-slot="form-message"]')?.textContent,
    ).toBe('Elegí un cliente'))
    expect(posts).toHaveLength(0)
  })

  it('un comodato no ofrece el bloque de cobro', async () => {
    // El backend rechaza un importe en un contrato sin cuota, así que ofrecerlo
    // sería ofrecer un 409.
    const user = userEvent.setup()
    render('/contratos/nuevo')
    await screen.findByRole('heading', { name: 'Nuevo contrato' })

    expect(screen.getByText('Cobro y visitas')).toBeInTheDocument()

    await user.click(screen.getByRole('combobox', { name: /Modalidad/ }))
    await user.click(await screen.findByRole('option', { name: 'Comodato' }))

    await waitFor(() =>
      expect(screen.queryByText('Cobro y visitas')).not.toBeInTheDocument())
    expect(screen.queryByLabelText('Importe')).not.toBeInTheDocument()
  })
})
