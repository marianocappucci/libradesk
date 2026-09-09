// Traer los reclamos cerrados de un cliente al remito (2026-09-09).
//
// Pedido del humano, textual: *"cuando estoy en remitos, nuevo remito, elijo el
// cliente, tengo que poder ver los reclamos cerrados sin facturar para que me
// deje elegirlos uno o más para agregarlos en el remito"*.
//
// 🔑 **Es la ÚNICA puerta desde el 2026-09-09.** Las otras dos —el botón de la
// ficha y el de la grilla— se sacaron el mismo día. La diferencia no es dónde
// está el botón: por los caminos viejos el remito salía **ya emitido** con lo
// que el sistema decidía; por éste los renglones entran al **borrador** y se
// editan antes de emitir.
//
// 🔴 **Y el test que más importa es el del `incidencia_ids` en el payload.** Ese
// campo es lo que ata los reclamos al remito, y sin el vínculo el mismo trabajo
// puede entrar en dos comprobantes — el doble cobro que este producto ya tuvo.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ComprobanteForm, type ComprobanteDraft, draftAPayload, draftVacio,
} from '../components/comprobante-form'

const CLIENTE = {
  id: 1, nombre: 'Metalmax', empresa: null, email: null, telefono: null,
  ciudad: null, cuit: '30-71234567-9', domicilio: null, observaciones: null,
  tipo_facturacion: 'por_servicio', activo: true, fecha_creacion: null,
}

const CERRADO = {
  id: 12, cliente_id: 1, equipo_id: null, activo_id: null, tecnico_id: null,
  recepcionista_id: null, vendedor_id: null, modalidad: null, sector_id: null,
  categoria_id: null, titulo: 'Central sin tono', descripcion: null,
  estado: 'cerrado', prioridad: 'media', horas_invertidas: '2',
  notas: null, resolucion: null, nro_cds: '0001-00041996', reclamante: null,
  estado_facturacion: null, activo: true, remito_id: null,
  cobertura_abono: null, abono_horas_cubiertas: null,
  abono_materiales_incluidos: null,
  fecha_creacion: '2026-09-01T10:00:00', fecha_cierre: '2026-09-05T18:00:00',
}

const YA_REMITADO = { ...CERRADO, id: 13, titulo: 'Ya facturado', remito_id: 9 }

const LINEAS = {
  items: [
    { description: 'CDS 0001-00041996 — #12 Central sin tono', qty: 2, unit_price: 21100, tax_rate: 0.21 },
    { description: 'Ficha RJ45\nReclamo #12', qty: 4, unit_price: 500, tax_rate: 0.21 },
  ],
  observations: 'Generado de los reclamos #12 (CDS 0001-00041996)',
  incidencia_ids: [12],
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let reclamos = [CERRADO, YA_REMITADO]
let pedidos: { url: string; cuerpo: unknown }[] = []

beforeEach(() => {
  reclamos = [CERRADO, YA_REMITADO]
  pedidos = []
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    if ((opciones?.method ?? 'GET') === 'POST') {
      pedidos.push({ url: u, cuerpo: JSON.parse(String(opciones?.body ?? '{}')) })
      if (u.includes('lineas-para-remito')) return Promise.resolve(json(LINEAS))
    }
    if (u.includes('/api/incidencias')) return Promise.resolve(json(reclamos))
    if (u.includes('/api/servicios/alicuotas')) return Promise.resolve(json([0, 0.105, 0.21]))
    return Promise.resolve(json([]))
  }))
})

/** El formulario es controlado; el anfitrión guarda el draft y lo expone. */
let ultimoDraft: ComprobanteDraft = draftVacio()

function Anfitrion({ tipo = 'remito' as const }) {
  const [draft, setDraft] = useState<ComprobanteDraft>({ ...draftVacio(), client_id: '1' })
  ultimoDraft = draft
  return (
    <MemoryRouter>
      <ComprobanteForm
        tipo={tipo}
        titulo="Nuevo remito"
        clientes={[CLIENTE] as never}
        draft={draft}
        onChange={setDraft}
        onSubmit={() => {}}
        onCancel={() => {}}
        saving={false}
      />
    </MemoryRouter>
  )
}

describe('El selector de reclamos en Nuevo remito', () => {
  it('muestra los cerrados sin facturar del cliente elegido', async () => {
    render(<Anfitrion />)

    expect(await screen.findByText(/#12 Central sin tono/)).toBeInTheDocument()
  })

  it('🔴 NO ofrece uno que ya tiene remito', async () => {
    // Es el filtro que evita el doble cobro del lado de la pantalla. El backend
    // además lo rechaza, pero ofrecerlo y que falle al traer sería un camino de
    // ida y vuelta que no lleva a nada.
    render(<Anfitrion />)
    await screen.findByText(/#12 Central sin tono/)

    expect(screen.queryByText(/Ya facturado/)).not.toBeInTheDocument()
  })

  it('muestra el N° CDS, que es por lo que se reconoce el trabajo', async () => {
    render(<Anfitrion />)

    expect(await screen.findByText(/CDS 0001-00041996/)).toBeInTheDocument()
  })

  it('sin reclamos pendientes lo dice, en vez de no dibujar nada', async () => {
    reclamos = [YA_REMITADO]
    render(<Anfitrion />)

    expect(await screen.findByText(/no tiene reclamos cerrados pendientes/i))
      .toBeInTheDocument()
  })

  it('🔑 no aparece en un presupuesto: no factura nada', async () => {
    render(<Anfitrion tipo={'presupuesto' as never} />)
    await screen.findByText('Nuevo remito')

    expect(screen.queryByText(/Reclamos cerrados sin facturar/)).not.toBeInTheDocument()
  })
})

describe('Traer los reclamos al borrador', () => {
  it('los renglones los arma el backend, no la pantalla', async () => {
    // Se piden a `lineas-para-remito`, que es la MISMA función que usa la
    // emisión. Componerlos en el frontend habría sido la segunda
    // implementación que este producto ya pagó tres veces.
    const user = userEvent.setup()
    render(<Anfitrion />)
    await user.click(await screen.findByLabelText(/#12 Central sin tono/))
    await user.click(screen.getByRole('button', { name: /Traer al remito/ }))

    await waitFor(() => {
      expect(pedidos.some((p) => p.url.includes('lineas-para-remito'))).toBe(true)
    })
    const pedido = pedidos.find((p) => p.url.includes('lineas-para-remito'))!
    expect(pedido.cuerpo).toEqual({ incidencia_ids: [12] })
  })

  it('los renglones entran al borrador y se pueden editar', async () => {
    const user = userEvent.setup()
    render(<Anfitrion />)
    await user.click(await screen.findByLabelText(/#12 Central sin tono/))
    await user.click(screen.getByRole('button', { name: /Traer al remito/ }))

    // La descripción llega editable: es el punto entero del cambio.
    const descripcion = await screen.findByDisplayValue(
      'CDS 0001-00041996 — #12 Central sin tono',
    )
    expect(descripcion).toBeInTheDocument()
    expect(descripcion).toBeEnabled()
    // Y con las horas y el precio que el sistema sabe, para no retipearlos.
    expect(screen.getByDisplayValue('21100')).toBeInTheDocument()
  })

  it('🔴 el payload lleva incidencia_ids: es lo que ata y evita el doble cobro', async () => {
    const user = userEvent.setup()
    render(<Anfitrion />)
    await user.click(await screen.findByLabelText(/#12 Central sin tono/))
    await user.click(screen.getByRole('button', { name: /Traer al remito/ }))
    await screen.findByDisplayValue('CDS 0001-00041996 — #12 Central sin tono')

    const payload = draftAPayload(ultimoDraft, 'remito') as { incidencia_ids: number[] }
    expect(payload.incidencia_ids).toEqual([12])
  })

  it('un remito tipeado a mano no ata nada', async () => {
    // La lista vacía es el caso normal de un remito que no sale de reclamos, y
    // tiene que seguir andando igual que antes de que esto existiera.
    const payload = draftAPayload(
      { ...draftVacio(), client_id: '1' }, 'remito',
    ) as { incidencia_ids: number[] }
    expect(payload.incidencia_ids).toEqual([])
  })

  it('un presupuesto no manda incidencia_ids', async () => {
    const payload = draftAPayload({ ...draftVacio(), client_id: '1' }, 'presupuesto')
    expect('incidencia_ids' in payload).toBe(false)
  })

  it('traer dos veces no duplica: el traído sale de la lista', async () => {
    const user = userEvent.setup()
    render(<Anfitrion />)
    await user.click(await screen.findByLabelText(/#12 Central sin tono/))
    await user.click(screen.getByRole('button', { name: /Traer al remito/ }))
    await screen.findByDisplayValue('CDS 0001-00041996 — #12 Central sin tono')

    // Ya no está para volver a tildarlo: del backend recién desaparece al
    // guardar, que es cuando se le pone el `remito_id`.
    expect(screen.queryByLabelText(/#12 Central sin tono/)).not.toBeInTheDocument()
  })
})
