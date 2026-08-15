// El devengado en pantalla — fase 2 (2026-08-15).
//
// Lo que estos tests fijan es lo que separa esta pantalla de un listado más:
//
// 1. 🔴 **Mirar no emite.** «Generar cuotas» abre una previsualización y no
//    escribe nada; recién «Confirmar y generar» hace el POST. La regla del
//    producto es que nada se factura sin confirmación humana, y acá eso es un
//    hecho verificable: se cuentan los POST.
// 2. **El proporcional se explica.** Un mes que sale menos que el anterior sin
//    decir por qué se lee como un error de la máquina.
// 3. **Lo ya emitido se muestra**, no se esconde: un contrato que simplemente
//    no aparece se lee como "este contrato no devenga".
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Cuotas } from '../pages/Cuotas'

const render = (ui: ReactElement) => renderRTL(<MemoryRouter>{ui}</MemoryRouter>)

const CUOTA_ENTERA = {
  id: 1, contrato_id: 1, contrato_numero: 'CTR-00000001',
  cliente_nombre: 'Estudio Contable Sur',
  periodo_desde: '2026-08-01', periodo_hasta: '2026-08-31',
  concepto: 'Alquiler agosto 2026 — CTR-00000001', tipo_cargo: 'alquiler',
  fecha_emision: '2026-08-01', fecha_vencimiento: '2026-08-10',
  importe_base: 31000, bonificacion: 0, impuestos: 0, interes_mora: 0,
  importe_total: 31000, moneda: 'ARS', estado: 'pendiente',
  precio_id: 1, remito_id: null, factura_numero: null,
  comprobante_pago: null, observaciones: null, created_at: null,
}

// La que ya salió en un remito: no se puede anular, porque el comprobante ya
// está en manos del cliente.
const CUOTA_CON_REMITO = {
  ...CUOTA_ENTERA,
  id: 2, contrato_numero: 'CTR-00000002',
  concepto: 'Alquiler agosto 2026 — CTR-00000002',
  remito_id: 44, estado: 'facturada',
}

const PROPUESTA_ENTERA = {
  contrato_id: 1, contrato_numero: 'CTR-00000001', cliente_id: 1,
  tipo_cargo: 'alquiler',
  periodo_desde: '2026-09-01', periodo_hasta: '2026-09-30',
  concepto: 'Alquiler septiembre 2026 — CTR-00000001',
  fecha_emision: '2026-09-01', fecha_vencimiento: '2026-09-10',
  importe_total: 31000, moneda: 'ARS', precio_id: 1,
  prorrateada: false, dias_cubiertos: 30, dias_del_periodo: 30,
}

const PROPUESTA_PRORRATEADA = {
  ...PROPUESTA_ENTERA,
  contrato_id: 3, contrato_numero: 'CTR-00000003', cliente_id: 2,
  tipo_cargo: 'proporcional',
  periodo_desde: '2026-09-20', periodo_hasta: '2026-09-30',
  concepto:
    'Alquiler septiembre 2026 — CTR-00000003 (proporcional 20-09-2026 al 30-09-2026)',
  importe_total: 11000,
  prorrateada: true, dias_cubiertos: 11, dias_del_periodo: 30,
}

const YA_EMITIDA = {
  ...PROPUESTA_ENTERA,
  contrato_id: 9, contrato_numero: 'CTR-00000009',
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let posts: { url: string; cuerpo: unknown }[] = []
let previa: unknown

beforeEach(() => {
  posts = []
  previa = {
    ancla: '2026-09-01',
    a_generar: [PROPUESTA_ENTERA, PROPUESTA_PRORRATEADA],
    ya_generadas: [YA_EMITIDA],
    total: 42000,
  }
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    if ((init?.method ?? 'GET') !== 'GET') {
      posts.push({ url: u, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
      if (u.includes('/generar')) {
        return Promise.resolve(json({ generadas: [CUOTA_ENTERA], ya_generadas: [] }))
      }
      return Promise.resolve(json(CUOTA_ENTERA))
    }
    // El orden importa: `/api/cuotas/previsualizar` contiene `/api/cuotas`.
    if (u.includes('/api/cuotas/previsualizar')) return Promise.resolve(json(previa))
    if (u.includes('/api/cuotas')) {
      return Promise.resolve(json([CUOTA_ENTERA, CUOTA_CON_REMITO]))
    }
    return Promise.resolve(json([]))
  }))
})


describe('🔴 Mirar no emite', () => {
  it('previsualizar no manda ningún POST', async () => {
    // El punto de que sean dos pasos. Si esto fallara, el botón de mirar sería
    // el botón de emitir — y un remito de más obliga a dar de baja a mano la
    // fila de `envios_facturacion`.
    const user = userEvent.setup()
    render(<Cuotas />)
    await screen.findByText('CTR-00000001')

    await user.click(screen.getByRole('button', { name: /Generar cuotas/ }))
    await screen.findByRole('dialog', { name: /Cuotas a generar/ })

    expect(posts).toHaveLength(0)
  })

  it('recién al confirmar se emite, y con el ancla elegida', async () => {
    const user = userEvent.setup()
    render(<Cuotas />)
    await screen.findByText('CTR-00000001')

    await user.click(screen.getByRole('button', { name: /Generar cuotas/ }))
    const dialogo = await screen.findByRole('dialog', { name: /Cuotas a generar/ })
    await user.click(within(dialogo).getByRole('button', { name: /Confirmar y generar/ }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toContain('/api/cuotas/generar')
    // El ancla es una FECHA, no un mes: el período lo resuelve el backend según
    // la periodicidad de cada contrato.
    expect(posts[0].cuerpo).toHaveProperty('ancla')
  })

  it('sin nada para devengar, confirmar queda deshabilitado', async () => {
    previa = { ancla: '2026-09-01', a_generar: [], ya_generadas: [], total: 0 }
    const user = userEvent.setup()
    render(<Cuotas />)
    await screen.findByText('CTR-00000001')

    await user.click(screen.getByRole('button', { name: /Generar cuotas/ }))
    const dialogo = await screen.findByRole('dialog', { name: /Cuotas a generar/ })

    expect(within(dialogo).getByRole('button', { name: /Confirmar y generar/ }))
      .toBeDisabled()
  })
})


describe('La previsualización explica lo que va a cobrar', () => {
  it('🔴 un proporcional dice cuántos días cubre', async () => {
    // Sin esto, un mes que sale menos que el anterior se lee como un error de
    // la máquina y alguien lo "corrige" a mano.
    const user = userEvent.setup()
    render(<Cuotas />)
    await screen.findByText('CTR-00000001')

    await user.click(screen.getByRole('button', { name: /Generar cuotas/ }))
    const dialogo = await screen.findByRole('dialog', { name: /Cuotas a generar/ })

    const fila = within(dialogo).getByText('CTR-00000003').closest('tr')!
    expect(within(fila).getByText('11 de 30 días')).toBeInTheDocument()

    // Y el mes entero NO lleva esa aclaración: es el control de que el texto no
    // aparece siempre.
    const filaEntera = within(dialogo).getByText('CTR-00000001').closest('tr')!
    expect(within(filaEntera).queryByText(/de 30 días/)).toBeNull()
  })

  it('muestra el total de lo que se va a emitir', async () => {
    const user = userEvent.setup()
    render(<Cuotas />)
    await screen.findByText('CTR-00000001')

    await user.click(screen.getByRole('button', { name: /Generar cuotas/ }))
    const dialogo = await screen.findByRole('dialog', { name: /Cuotas a generar/ })

    expect(within(dialogo).getByText('Total')).toBeInTheDocument()
    expect(within(dialogo).getByText(/42\.000/)).toBeInTheDocument()
  })

  it('🔴 avisa de los períodos que ya estaban emitidos', async () => {
    // Se muestran en vez de esconderse: un contrato que simplemente no aparece
    // en la lista se lee como "este contrato no devenga", que es otra cosa.
    const user = userEvent.setup()
    render(<Cuotas />)
    await screen.findByText('CTR-00000001')

    await user.click(screen.getByRole('button', { name: /Generar cuotas/ }))
    const dialogo = await screen.findByRole('dialog', { name: /Cuotas a generar/ })

    expect(within(dialogo).getByText(/1 contrato ya tiene emitido este período/))
      .toBeInTheDocument()
  })
})


describe('El listado', () => {
  it('una cuota que ya salió en un remito no ofrece anular', async () => {
    // El backend lo rechaza con 422, así que ofrecerlo sería ofrecer un error.
    render(<Cuotas />)
    await screen.findByText('CTR-00000001')

    const conRemito = screen.getByText('CTR-00000002').closest('tr')!
    expect(within(conRemito).queryByRole('button', { name: 'Anular' })).toBeNull()

    // Control: la que sí se puede anular lo ofrece. Sin esto, una condición que
    // escondiera el botón SIEMPRE pasaría este test igual.
    const normal = screen.getByText('CTR-00000001').closest('tr')!
    expect(within(normal).getByRole('button', { name: 'Anular' })).toBeInTheDocument()
  })

  it('el concepto lleva el período adentro, que es lo que viaja al remito', async () => {
    // El PDF de un remito sólo imprime descripción y cantidad: si el período no
    // está en el concepto, no llega a ninguna parte.
    render(<Cuotas />)
    expect(await screen.findByText(/Alquiler agosto 2026 — CTR-00000001/))
      .toBeInTheDocument()
  })
})
