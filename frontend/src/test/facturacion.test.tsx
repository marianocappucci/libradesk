// "Enviar a facturar" — la pantalla del emisor (fase B del puente con
// Contalibra).
//
// Lo que fijan estos tests es el malentendido caro de esta pantalla: que
// **mandar no es facturar**. Un botón que dice "Enviar" al lado de importes
// invita a leerlo como "cobrar", y del otro lado todavía tiene que intervenir
// una persona. Por eso se afirma sobre el texto que ve el usuario y no sólo
// sobre el request que sale.
import { render as renderRTL, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Facturacion } from '../pages/Facturacion'

const render = (ui: ReactElement) => renderRTL(<MemoryRouter>{ui}</MemoryRouter>)

const REMITO = {
  origen_tipo: 'remito' as const,
  id: 1,
  numero: 'REM-00000001',
  fecha: '2026-08-08',
  cliente: 'Ferretería San Martín',
  cliente_cuit: '30-71234567-9',
  total: 12100,
  envio: null,
}

const PRESUPUESTO = {
  ...REMITO,
  origen_tipo: 'presupuesto' as const,
  id: 1,
  numero: 'PRE-00000001',
  total: 5000,
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

let posts: { url: string; body: unknown }[]

function montar(items: unknown[], configurado = true, resultados: unknown[] = []) {
  posts = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    if (init?.method === 'POST') {
      posts.push({ url: u, body: JSON.parse(String(init.body)) })
      return Promise.resolve(json({ resultados }))
    }
    if (u.includes('/api/facturacion/pendientes')) {
      return Promise.resolve(json({ configurado, items }))
    }
    return Promise.resolve(json({}))
  }))
}

beforeEach(() => { posts = [] })

describe('enviar a facturar', () => {
  it('deja claro que desde acá no se emite ninguna factura', async () => {
    montar([REMITO])
    render(<Facturacion />)
    expect(
      await screen.findByText(/no se emite ninguna factura/i),
    ).toBeInTheDocument()
  })

  it('sin enlace configurado lo dice y no ofrece mandar', async () => {
    montar([REMITO], false)
    render(<Facturacion />)

    expect(await screen.findByText(/no está enlazada con Contalibra/i)).toBeInTheDocument()

    await userEvent.click(screen.getAllByRole('checkbox')[0])
    const boton = await screen.findByRole('button', { name: /Enviar a Contalibra/i })
    expect(boton).toBeDisabled()
  })

  it('manda lo elegido con su tipo y su id', async () => {
    montar([REMITO])
    render(<Facturacion />)
    await screen.findByText('REM-00000001')

    await userEvent.click(screen.getAllByRole('checkbox')[0])
    await userEvent.click(screen.getByRole('button', { name: /Enviar a Contalibra/i }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toContain('/api/facturacion/enviar')
    expect(posts[0].body).toEqual({ origen_tipo: 'remito', ids: [1] })
  })

  it('un remito y un presupuesto con el mismo id no se mezclan', async () => {
    // Las dos numeraciones arrancan en 1. Con una clave que fuera sólo el id,
    // tildar el remito 1 tildaría también el presupuesto 1 — y se mandaría a
    // facturar algo que nadie eligió.
    montar([REMITO, PRESUPUESTO])
    render(<Facturacion />)
    await screen.findByText('REM-00000001')

    await userEvent.click(screen.getAllByRole('checkbox')[0])

    expect(await screen.findByText(/1 comprobante elegido/)).toBeInTheDocument()
  })

  it('elegidos de los dos tipos salen en dos requests, uno por tipo', async () => {
    montar([REMITO, PRESUPUESTO])
    render(<Facturacion />)
    await screen.findByText('PRE-00000001')

    // Se vuelve a consultar entre clicks: la tabla se rerenderiza y los nodos
    // de antes quedan desprendidos, así que el segundo click sobre la
    // referencia vieja no llega a ninguna parte.
    await userEvent.click(screen.getAllByRole('checkbox')[0])
    await userEvent.click(screen.getAllByRole('checkbox')[1])
    expect(await screen.findByText(/2 comprobantes elegidos/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Enviar a Contalibra/i }))

    await waitFor(() => expect(posts).toHaveLength(2))
    const tipos = posts.map((p) => (p.body as { origen_tipo: string }).origen_tipo)
    expect(tipos.sort()).toEqual(['presupuesto', 'remito'])
  })

  it('lo ya enviado se ve como "en la bandeja", no como facturado', async () => {
    montar([{
      ...REMITO,
      envio: {
        id: 1, origen_tipo: 'remito', origen_id: 1, estado: 'enviado',
        comprobante_remoto_id: 7, detalle: '',
        enviado_at: '2026-08-08 10:00:00', actualizado_at: '2026-08-08 10:00:00',
      },
    }])
    render(<Facturacion />)

    expect(await screen.findByText('En la bandeja')).toBeInTheDocument()
    expect(screen.queryByText(/facturado/i)).not.toBeInTheDocument()
  })

  it('un envío fallido se ve como tal y se puede reintentar', async () => {
    montar([{
      ...REMITO,
      envio: {
        id: 1, origen_tipo: 'remito', origen_id: 1, estado: 'error',
        comprobante_remoto_id: null,
        detalle: 'No se pudo contactar a Contalibra',
        enviado_at: '2026-08-08 10:00:00', actualizado_at: '2026-08-08 10:00:00',
      },
    }])
    render(<Facturacion />)

    expect(await screen.findByText('Falló')).toBeInTheDocument()
    // La casilla sigue habilitada: reintentar es gratis porque el destino es
    // idempotente.
    expect(screen.getAllByRole('checkbox')[0]).toBeEnabled()
  })

  it('el resultado del envío se muestra sin recargar la pantalla', async () => {
    montar([REMITO], true, [{
      id: 1, origen_tipo: 'remito', origen_id: 1, estado: 'error',
      comprobante_remoto_id: null, detalle: 'No se pudo contactar a Contalibra',
      enviado_at: '', actualizado_at: '',
    }])
    render(<Facturacion />)
    await screen.findByText('REM-00000001')

    await userEvent.click(screen.getAllByRole('checkbox')[0])
    await userEvent.click(screen.getByRole('button', { name: /Enviar a Contalibra/i }))

    expect(
      await screen.findByText(/No se pudo contactar a Contalibra/),
    ).toBeInTheDocument()
  })

  it('sin nada para mandar lo dice', async () => {
    montar([])
    render(<Facturacion />)
    expect(
      await screen.findByText(/No hay remitos ni presupuestos aceptados/i),
    ).toBeInTheDocument()
  })
})
