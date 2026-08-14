// IVA por ítem y condición del receptor en el formulario de comprobante
// (ítem 2, 2026-08-05).
//
// El modelo, resuelto con el humano: **la alícuota es del servicio** —el 21 /
// 10,5 / 27 / exento sale de QUÉ se vende— y de la condición del cliente
// depende otra cosa: si el comprobante discrimina el impuesto o muestra el
// precio final. El razonamiento está en `app/services/iva.py`.
//
// Lo que afirman estos tests, en orden de lo que se rompe sin que se note:
//
// 1. 🔴 **Que los totales en pantalla coincidan con los del backend.** Se
//    calculan dos veces —acá para mostrarlos en vivo, allá para guardarlos— y
//    si divergen, lo que se ve al cargar no es lo que queda en el comprobante.
// 2. 🔴 **Que abrir un presupuesto viejo no le borre el IVA.** Los guardados
//    antes de este cambio no tienen alícuota por ítem; si cayeran a 0%,
//    guardarlos de nuevo les sacaría el impuesto sin avisar.
// 3. Que elegir un servicio del catálogo traiga su alícuota.
// 4. Que la regla de quién discrimina **no** esté reescrita acá.
import { render, screen, waitFor, within } from '@testing-library/react'
import { useState } from 'react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Cliente, Servicio } from '../api'
import {
  ComprobanteForm, comprobanteADraft, draftAPayload, draftVacio,
  type ComprobanteDraft, type ItemDraft,
} from '../components/comprobante-form'

const RESPONSABLE: Cliente = {
  id: 1, nombre: 'Compulibra', condicion_iva: 'Responsable Inscripto',
  iva_discriminado: true, activo: true,
} as Cliente

const CONSUMIDOR: Cliente = {
  id: 2, nombre: 'Juan Pérez', condicion_iva: 'Consumidor Final',
  iva_discriminado: false, activo: true,
} as Cliente

const SIN_CARGAR: Cliente = {
  id: 3, nombre: 'Cliente viejo', condicion_iva: null,
  iva_discriminado: false, activo: true,
} as Cliente

const CLIENTES = [RESPONSABLE, CONSUMIDOR, SIN_CARGAR]

const EXENTO: Servicio = {
  id: 1, nombre: 'Libro de instructivos', descripcion: '',
  texto: 'Libro de instructivos', precio: 5000, iva_rate: 0, activo: true,
  es_valor_hora: false,
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/api/servicios/alicuotas')) {
      return Promise.resolve(json([0, 0.105, 0.21, 0.27]))
    }
    if (u.includes('/api/servicios/buscar')) return Promise.resolve(json([EXENTO]))
    return Promise.resolve(json([]))
  }))
})

function Anfitrion({ espia, inicial }: {
  espia: (d: ComprobanteDraft) => void
  inicial?: ComprobanteDraft
}) {
  const [draft, setDraft] = useState<ComprobanteDraft>(inicial ?? draftVacio())
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

function montar(inicial?: ComprobanteDraft) {
  let ultimo: ComprobanteDraft = inicial ?? draftVacio()
  render(<Anfitrion inicial={inicial} espia={(d) => { ultimo = d }} />)
  return { leer: () => ultimo }
}

/** Sólo el formulario, sin estado: para los casos que miran lo que se muestra
 *  y no lo que se edita. */
function soloVista(client_id: string, clientes: Cliente[] = CLIENTES) {
  return render(
    <ComprobanteForm
      tipo="presupuesto" titulo="Nuevo presupuesto"
      draft={{ ...draftVacio(), client_id }}
      clientes={clientes} onChange={vi.fn()} onSubmit={vi.fn()}
      onCancel={vi.fn()} saving={false}
    />,
  )
}

function conItems(items: ItemDraft[]): ComprobanteDraft {
  return { ...draftVacio(), items }
}


// ── Los totales de la pantalla ────────────────────────────────────────────

describe('Totales en vivo', () => {
  it('🔴 el IVA se acumula por línea, no sobre el subtotal', async () => {
    // 10.000 al 21% + 5.000 exento = 2.100 de IVA. Sobre el subtotal daría
    // 3.150, que es lo que cobraba de más el cálculo viejo.
    montar(conItems([
      { description: 'Soporte', qty: '1', unit_price: '10000', tax_rate: '21' },
      { description: 'Libro', qty: '1', unit_price: '5000', tax_rate: '0' },
    ]))

    expect(await screen.findByText('$ 2.100,00')).toBeInTheDocument()
    expect(screen.getByText('$ 17.100,00')).toBeInTheDocument()
  })

  it('con una sola alícuota el renglón la nombra', async () => {
    montar(conItems([
      { description: 'Soporte', qty: '1', unit_price: '10000', tax_rate: '10.5' },
    ]))

    expect(await screen.findByText('IVA 10,5 %')).toBeInTheDocument()
  })

  it('🔴 al mezclar, el IVA se abre por alícuota', async () => {
    // Un solo renglón «IVA 21 %» declararía mal la línea exenta.
    montar(conItems([
      { description: 'Soporte', qty: '1', unit_price: '10000', tax_rate: '21' },
      { description: 'Libro', qty: '1', unit_price: '5000', tax_rate: '0' },
    ]))

    expect(await screen.findByText('IVA 21 %')).toBeInTheDocument()
    expect(screen.getByText('IVA 0 %')).toBeInTheDocument()
  })
})


// ── El payload que va al backend ──────────────────────────────────────────

describe('Payload', () => {
  it('cada ítem manda su alícuota como fracción', () => {
    const payload = draftAPayload(conItems([
      { description: 'Soporte', qty: '1', unit_price: '10000', tax_rate: '21' },
      { description: 'Libro', qty: '1', unit_price: '5000', tax_rate: '0' },
    ]), 'presupuesto')

    expect(payload.items.map((i) => i.tax_rate)).toEqual([0.21, 0])
  })

  it('el 10,5 % no se redondea al mandarlo', () => {
    const payload = draftAPayload(conItems([
      { description: 'Soporte', qty: '1', unit_price: '100', tax_rate: '10.5' },
    ]), 'presupuesto')

    expect(payload.items[0].tax_rate).toBe(0.105)
  })
})


// ── Los comprobantes que ya existen ───────────────────────────────────────

describe('Comprobantes guardados antes del cambio', () => {
  it('🔴 una línea sin alícuota propia hereda la del documento', () => {
    // Sin este fallback, abrir un presupuesto viejo lo mostraría con todo al
    // 0 % y guardarlo así le borraría el IVA sin avisar.
    const draft = comprobanteADraft({
      client_id: 1, date: '2026-08-01', client_cuit: null, client_address: null,
      tax_rate: 0.21, observations: null,
      items: [{ description: 'Soporte', qty: 1, unit_price: 10000, subtotal: 10000 }],
    })

    expect(draft.items[0].tax_rate).toBe('21')
  })

  it('una línea con alícuota propia usa la suya, no la del documento', () => {
    const draft = comprobanteADraft({
      client_id: 1, date: '2026-08-05', client_cuit: null, client_address: null,
      tax_rate: 0, observations: null,
      items: [
        { description: 'Soporte', qty: 1, unit_price: 10000, subtotal: 10000, iva_pct: 21 },
        { description: 'Libro', qty: 1, unit_price: 5000, subtotal: 5000, iva_pct: 0 },
      ],
    })

    expect(draft.items.map((i) => i.tax_rate)).toEqual(['21', '0'])
  })

  it('🔴 un ítem exento guardado no se confunde con uno sin dato', () => {
    // `iva_pct: 0` es un valor, no una ausencia: con `||` en vez de `??` caería
    // al 21 % del documento y le pondría IVA a algo exento.
    const draft = comprobanteADraft({
      client_id: 1, date: '2026-08-05', client_cuit: null, client_address: null,
      tax_rate: 0.21, observations: null,
      items: [{ description: 'Libro', qty: 1, unit_price: 5000, subtotal: 5000, iva_pct: 0 }],
    })

    expect(draft.items[0].tax_rate).toBe('0')
  })
})


// ── El catálogo trae su alícuota ──────────────────────────────────────────

describe('Elegir un servicio', () => {
  it('🔴 copia la alícuota del servicio, no sólo el precio', async () => {
    const { leer } = montar()
    const usuario = userEvent.setup()

    await usuario.type(screen.getByLabelText('Descripción del ítem 1'), 'libro')
    await usuario.click(await screen.findByRole('button', { name: /Libro de instructivos/ }))

    await waitFor(() => expect(leer().items[0].tax_rate).toBe('0'))
    expect(leer().items[0].unit_price).toBe('5000')
  })
})


// ── La condición del cliente ──────────────────────────────────────────────

describe('Condición frente al IVA', () => {
  it('🔴 usa el booleano del backend y no vuelve a comparar el texto', async () => {
    // Este cliente dice "Consumidor Final" pero llega con
    // `iva_discriminado: true`. Si la pantalla reprodujera la regla mostraría
    // "precio final", que es lo contrario de lo que hará el PDF.
    const raro = { ...CONSUMIDOR, id: 4, nombre: 'Raro', iva_discriminado: true } as Cliente
    soloVista('4', [raro])

    expect(await screen.findByText(/IVA discriminado/)).toBeInTheDocument()
  })

  it('avisa cuando el PDF va a salir sin desglose', async () => {
    soloVista('2')

    expect(await screen.findByText(/IVA incluido en los precios/)).toBeInTheDocument()
  })

  it('sin condición cargada no es lo mismo que sin cliente elegido', async () => {
    const { unmount } = soloVista('')
    expect(await screen.findByText('Se toma del cliente')).toBeInTheDocument()
    unmount()

    soloVista('3')
    expect(await screen.findByText(/Sin cargar/)).toBeInTheDocument()
  })
})


// ── Las alícuotas que ofrece el selector ──────────────────────────────────

describe('Selector de alícuota', () => {
  it('🔴 las lee del backend, que es donde está la lista cerrada', async () => {
    // ⚠️ El backend devuelve acá una lista **distinta** de la de reserva a
    // propósito. La primera versión de este test usaba las mismas cuatro, y
    // pasaba con la consulta desconectada: el fallback mostraba exactamente lo
    // mismo, así que no había forma de saber de dónde salían. Lo delató el
    // arnés de falla forzada.
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (String(url).includes('/api/servicios/alicuotas')) {
        return Promise.resolve(json([0, 0.21]))
      }
      return Promise.resolve(json([]))
    }))
    const usuario = userEvent.setup()
    montar()

    await usuario.click(await screen.findByLabelText('Alícuota de IVA del ítem 1'))
    const lista = await screen.findByRole('listbox')

    expect(within(lista).getByRole('option', { name: '0 %' })).toBeInTheDocument()
    expect(within(lista).getByRole('option', { name: '21 %' })).toBeInTheDocument()
    expect(within(lista).queryByRole('option', { name: '10,5 %' })).not.toBeInTheDocument()
  })

  it('si la consulta falla, el selector sigue ofreciendo las conocidas', async () => {
    // Quedarse sin `<select>` haría imposible cargar un comprobante. El
    // backend valida igual al guardar.
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))
    const usuario = userEvent.setup()
    montar()

    await usuario.click(await screen.findByLabelText('Alícuota de IVA del ítem 1'))
    const lista = await screen.findByRole('listbox')

    expect(within(lista).getByRole('option', { name: '10,5 %' })).toBeInTheDocument()
    expect(within(lista).getByRole('option', { name: '27 %' })).toBeInTheDocument()
  })

  it('un ítem nuevo arranca al 21 %', () => {
    const { leer } = montar()
    expect(leer().items[0].tax_rate).toBe('21')
  })
})
