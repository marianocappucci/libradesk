// La pre-factura con renglones en pesos y en dólares (2026-09-09).
//
// **Qué se afirma acá.** Que la pantalla hace las tres cosas que el backend no
// puede hacer por ella: pedir la cotización cuando hace falta, mostrar el
// importe **en pesos** de un renglón cargado en dólares, y mandar el precio en
// su moneda de origen.
//
// 🔴 **El test que hay que mirar primero es `abrir_un_comprobante_en_dolares`.**
// Un ítem guardado vuelve con `unit_price` **ya convertido a pesos** y con el
// dólar en `unit_price_origen`. Si el formulario mostrara el peso y lo
// reenviara con `moneda: 'USD'`, el backend lo convertiría otra vez y el
// comprobante se guardaría por mil veces su valor — sin que nada falle.
import { render as renderRTL, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ComprobanteForm, type ComprobanteDraft, comprobanteADraft, draftAPayload, draftVacio,
} from '../components/comprobante-form'
import { Cotizaciones } from '../pages/Cotizaciones'

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

const CLIENTE = {
  id: 1, nombre: 'Metalmax', empresa: null, email: null, telefono: null,
  ciudad: null, cuit: '30-71234567-9', domicilio: null, observaciones: null,
  tipo_facturacion: 'por_servicio', activo: true, fecha_creacion: null,
}

let vigenteStub: unknown = { fecha: '2026-09-03', valor: 1450.5 }

beforeEach(() => {
  vigenteStub = { fecha: '2026-09-03', valor: 1450.5 }
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/api/cotizaciones/vigente')) return Promise.resolve(json(vigenteStub))
    if (u.includes('/api/servicios/alicuotas')) return Promise.resolve(json([0, 0.105, 0.21, 0.27]))
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    return Promise.resolve(json([]))
  }))
})

/** El formulario es controlado: sin un padre que guarde el draft, cambiar un
 *  campo no se ve. */
function Anfitrion({ inicial }: { inicial: ComprobanteDraft }) {
  const [draft, setDraft] = useState(inicial)
  return (
    <MemoryRouter>
      <ComprobanteForm
        tipo="remito"
        draft={draft}
        onChange={setDraft}
        clientes={[CLIENTE] as never}
        onSubmit={() => {}}
        guardando={false}
      />
    </MemoryRouter>
  )
}

const render = (inicial = draftVacio()) => renderRTL(<Anfitrion inicial={inicial} />)

async function ponerEnDolares(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('combobox', { name: 'Moneda del ítem 1' }))
  await user.click(await screen.findByRole('option', { name: 'U$S' }))
}

describe('Pre-factura con dos monedas', () => {
  it('la cotización no está hasta que hay un renglón en dólares', async () => {
    // Antes de eso es una caja vacía que no explica nada, y son casi todos los
    // comprobantes.
    const user = userEvent.setup()
    render()
    expect(screen.queryByLabelText(/Cotización del dólar/)).not.toBeInTheDocument()

    await ponerEnDolares(user)

    expect(await screen.findByLabelText(/Cotización del dólar/)).toBeInTheDocument()
  })

  it('ofrece la última cargada diciendo de qué día es', async () => {
    // 🔴 Con la fecha, no sólo el número: si la de hoy no se cargó, la vigente
    // puede ser de hace dos semanas y nadie tendría cómo notarlo.
    const user = userEvent.setup()
    render()
    await ponerEnDolares(user)

    const boton = await screen.findByRole('button', { name: /Usar la del 03-09-2026/ })
    await user.click(boton)

    expect(screen.getByLabelText(/Cotización del dólar/)).toHaveValue(1450.5)
  })

  it('sin ninguna cargada lo dice, en vez de ofrecer un botón vacío', async () => {
    vigenteStub = null
    const user = userEvent.setup()
    render()
    await ponerEnDolares(user)

    expect(await screen.findByText(/No hay ninguna cargada/)).toBeInTheDocument()
  })

  it('el importe del renglón se muestra en pesos, y de dónde salió', async () => {
    const user = userEvent.setup()
    render()
    await ponerEnDolares(user)
    await user.clear(screen.getByLabelText('Precio unitario del ítem 1'))
    await user.type(screen.getByLabelText('Precio unitario del ítem 1'), '100')
    await user.click(await screen.findByRole('button', { name: /Usar la del/ }))

    // 100 × 1450,50. El importe de la fila y el subtotal, los dos en pesos.
    await waitFor(() => {
      expect(screen.getAllByText(/145\.050,00/).length).toBeGreaterThan(0)
    })
    expect(screen.getByText(/U\$S 100 × 1450\.5/)).toBeInTheDocument()
  })

  it('mientras falta la cotización el total NO usa el valor nominal', async () => {
    // 🔴 Un renglón de USD 100 sin cotización vale **cero** en pantalla, no
    // $100. El total tiene que verse mal mientras falta el dato, no razonable:
    // un $100 plausible es exactamente lo que nadie mira dos veces.
    const user = userEvent.setup()
    render()
    await ponerEnDolares(user)
    await user.clear(screen.getByLabelText('Precio unitario del ítem 1'))
    await user.type(screen.getByLabelText('Precio unitario del ítem 1'), '100')

    expect(await screen.findByText(/falta la cotización/)).toBeInTheDocument()
    expect(screen.queryByText(/\$\s?100,00/)).not.toBeInTheDocument()
  })
})

describe('La pantalla de cotizaciones', () => {
  it('carga con PUT, porque hay una sola por día', async () => {
    // `POST` daría 409 al corregir un valor mal tipeado a la mañana, y
    // corregirlo es el caso normal — no el excepcional.
    const user = userEvent.setup()
    const llamadas: { url: string; metodo: string }[] = []
    vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
      llamadas.push({ url: String(url), metodo: opciones?.method ?? 'GET' })
      return Promise.resolve(json([]))
    }))

    renderRTL(<MemoryRouter><Cotizaciones /></MemoryRouter>)
    await user.type(await screen.findByLabelText('Pesos por dólar'), '1450.5')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    await waitFor(() => {
      expect(llamadas.some((l) => l.metodo === 'PUT' && l.url.includes('/api/cotizaciones')))
        .toBe(true)
    })
  })

  it('dice que corregir no le cambia el total a lo ya emitido', async () => {
    // Va en la pantalla y no en un tooltip: es lo que evita que alguien deje un
    // valor mal cargado por miedo a romper una factura vieja.
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json([]))))
    renderRTL(<MemoryRouter><Cotizaciones /></MemoryRouter>)
    expect(await screen.findByText(/no les cambia el total/)).toBeInTheDocument()
  })
})

describe('El ida y vuelta con la API', () => {
  it('manda el precio en su moneda de origen, no el peso', () => {
    const draft = draftVacio()
    draft.client_id = '1'
    draft.cotizacion = '1450.5'
    draft.items = [{
      description: 'Central', detalle: '', qty: '1', unit_price: '100',
      tax_rate: '21', moneda: 'USD',
    }]

    const payload = draftAPayload(draft, 'remito') as {
      cotizacion: number | null
      items: { unit_price: number; moneda: string }[]
    }
    expect(payload.items[0].unit_price).toBe(100)
    expect(payload.items[0].moneda).toBe('USD')
    expect(payload.cotizacion).toBe(1450.5)
  })

  it('sin cotización manda null y no cero', () => {
    // El backend la valida con `gt=0`: un 0 daría un 422 confuso en vez de
    // "falta la cotización".
    const draft = draftVacio()
    draft.client_id = '1'
    const payload = draftAPayload(draft, 'remito') as { cotizacion: number | null }
    expect(payload.cotizacion).toBeNull()
  })

  it('🔴 abrir un comprobante en dólares muestra el DÓLAR, no el peso', () => {
    // El caso que se guardaría por mil veces su valor si esto se rompe.
    const draft = comprobanteADraft({
      client_id: 1, date: '2026-09-09', client_cuit: '', client_address: null,
      tax_rate: 0.21, observations: '',
      items: [{
        description: 'Central', qty: 1, unit_price: 145050, subtotal: 145050,
        iva_pct: 21, moneda: 'USD', unit_price_origen: 100, cotizacion: 1450.5,
      }],
    })

    expect(draft.items[0].unit_price).toBe('100')
    expect(draft.items[0].moneda).toBe('USD')
    // Y la cotización que se ofrece es la CONGELADA del comprobante, no la de
    // hoy: reabrir y guardar sin tocar nada da el mismo total.
    expect(draft.cotizacion).toBe('1450.5')
  })

  it('un comprobante viejo sin moneda se abre en pesos', () => {
    // Los que ya existen no tienen la clave: el backend no la escribe cuando la
    // línea es en pesos.
    const draft = comprobanteADraft({
      client_id: 1, date: '2026-09-09', client_cuit: '', client_address: null,
      tax_rate: 0.21, observations: '',
      items: [{ description: 'Mano de obra', qty: 1, unit_price: 5000, subtotal: 5000 }],
    })
    expect(draft.items[0].moneda).toBe('ARS')
    expect(draft.items[0].unit_price).toBe('5000')
    expect(draft.cotizacion).toBe('')
  })
})
