// Sugerencias del catálogo de servicios en el formulario de comprobante
// (ítem 3, 2026-08-05).
//
// Lo que afirman, en orden de lo que se rompe sin que se note:
//
// 1. 🔴 **El campo sigue siendo libre.** Es la mitad del pedido: escribir algo
//    que no está en el catálogo tiene que quedar tal cual. Si las sugerencias
//    pisaran el texto, el formulario se volvería inusable para todo lo que no
//    esté cargado.
// 2. Elegir una sugerencia copia texto y precio, y **no toca la cantidad** —
//    la puso el usuario.
// 3. No se consulta al backend por cada tecla.
// 4. Si el catálogo falla, se sigue pudiendo cargar el comprobante a mano.
import { render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Cliente } from '../api'
import {
  ComprobanteForm, draftVacio, type ComprobanteDraft,
} from '../components/comprobante-form'

const CLIENTES: Cliente[] = [
  {
    id: 1, nombre: 'Compulibra', email: null, telefono: null, ciudad: null,
    cuit: null, activo: true,
  } as Cliente,
]

const SERVICIOS = [
  {
    id: 1, nombre: 'Mantenimiento preventivo', descripcion: '',
    texto: 'Mantenimiento preventivo', precio: 15000, activo: true,
  },
  {
    id: 2, nombre: 'Service anual', descripcion: 'Incluye limpieza y pasta térmica',
    texto: 'Incluye limpieza y pasta térmica', precio: 22000, activo: true,
  },
]

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let consultas: string[] = []
let fallaElCatalogo = false

beforeEach(() => {
  consultas = []
  fallaElCatalogo = false
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/api/servicios/buscar')) {
      consultas.push(u)
      if (fallaElCatalogo) return Promise.reject(new TypeError('Failed to fetch'))
      const q = decodeURIComponent(new URL(u, 'http://x').searchParams.get('q') ?? '')
      return Promise.resolve(json(
        SERVICIOS.filter((s) =>
          s.nombre.toLowerCase().includes(q.toLowerCase())
          || s.descripcion.toLowerCase().includes(q.toLowerCase()),
        ),
      ))
    }
    return Promise.resolve(json([]))
  }))
})

/** El formulario es controlado: sin estado real, el input nunca se actualiza
 *  entre teclas y `userEvent.type` no escribe nada. Este wrapper le da el
 *  `useState` que en la app le da la pantalla. */
function Anfitrion({ espia }: { espia: (d: ComprobanteDraft) => void }) {
  const [draft, setDraft] = useState<ComprobanteDraft>(draftVacio())
  espia(draft)
  return (
    <ComprobanteForm
      tipo="presupuesto"
      titulo="Nuevo presupuesto"
      draft={draft}
      clientes={CLIENTES}
      onChange={(d) => setDraft(d)}
      onSubmit={vi.fn()}
      onCancel={vi.fn()}
      saving={false}
    />
  )
}

function montar() {
  let ultimo: ComprobanteDraft = draftVacio()
  render(<Anfitrion espia={(d) => { ultimo = d }} />)
  return { leer: () => ultimo }
}


describe('🔴 El campo sigue siendo libre', () => {
  it('se puede escribir algo que no está en el catálogo y queda tal cual', async () => {
    const { leer } = montar()
    const usuario = userEvent.setup()

    const campo = screen.getByLabelText(/Descripción del ítem 1/)
    await usuario.type(campo, 'Algo que no está en la lista')

    expect(leer().items[0].description).toBe('Algo que no está en la lista')
  })

  it('con menos de dos letras no molesta con sugerencias', async () => {
    montar()
    const usuario = userEvent.setup()

    await usuario.type(screen.getByLabelText(/Descripción del ítem 1/), 'M')

    await new Promise((r) => setTimeout(r, 350))
    expect(consultas).toHaveLength(0)
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('si el catálogo falla, el formulario sigue andando', async () => {
    fallaElCatalogo = true
    const { leer } = montar()
    const usuario = userEvent.setup()

    await usuario.type(screen.getByLabelText(/Descripción del ítem 1/), 'Mantenimiento')

    await new Promise((r) => setTimeout(r, 350))
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(leer().items[0].description).toBe('Mantenimiento')
  })
})


describe('Elegir una sugerencia', () => {
  it('copia el texto y el precio al ítem', async () => {
    const { leer } = montar()
    const usuario = userEvent.setup()

    await usuario.type(screen.getByLabelText(/Descripción del ítem 1/), 'Manten')

    const opcion = await screen.findByRole('button', { name: /Mantenimiento preventivo/ })
    await usuario.click(opcion)

    expect(leer().items[0].description).toBe('Mantenimiento preventivo')
    expect(leer().items[0].unit_price).toBe('15000')
  })

  it('usa la descripción larga cuando el servicio la tiene', async () => {
    const { leer } = montar()
    const usuario = userEvent.setup()

    await usuario.type(screen.getByLabelText(/Descripción del ítem 1/), 'Service')

    await usuario.click(await screen.findByRole('button', { name: /pasta térmica/ }))

    expect(leer().items[0].description).toBe('Incluye limpieza y pasta térmica')
  })

  it('🔴 no pisa la cantidad que puso el usuario', async () => {
    const { leer } = montar()
    const usuario = userEvent.setup()

    const cantidad = screen.getByLabelText(/Cantidad del ítem 1/)
    await usuario.clear(cantidad)
    await usuario.type(cantidad, '3')

    await usuario.type(screen.getByLabelText(/Descripción del ítem 1/), 'Manten')
    await usuario.click(await screen.findByRole('button', { name: /Mantenimiento preventivo/ }))

    expect(leer().items[0].qty).toBe('3')
  })

  it('muestra el precio en la sugerencia, para elegir sin abrir el catálogo', async () => {
    montar()
    const usuario = userEvent.setup()

    await usuario.type(screen.getByLabelText(/Descripción del ítem 1/), 'Manten')

    const opcion = await screen.findByRole('button', { name: /Mantenimiento preventivo/ })
    expect(opcion.textContent).toMatch(/15\.000/)
  })
})


describe('No consulta por cada tecla', () => {
  it('agrupa lo que se escribe seguido en una sola consulta', async () => {
    montar()
    const usuario = userEvent.setup()

    await usuario.type(screen.getByLabelText(/Descripción del ítem 1/), 'Mantenimiento')

    await waitFor(() => expect(consultas.length).toBeGreaterThan(0))
    // 13 teclas, una consulta: sin el debounce serían 12 de más.
    expect(consultas.length).toBeLessThanOrEqual(2)
  })
})
