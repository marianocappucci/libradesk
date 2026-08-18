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

const OTRO_REMITO = {
  ...REMITO,
  id: 2,
  numero: 'REM-00000002',
  total: 5000,
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

let posts: { url: string; body: unknown }[]

function montar(items: unknown[], configurado = true, resultados: unknown[] = [],
                destinoNombre = 'Contalibra',
                opciones: { destino?: string; estadosSos?: unknown[] } = {}) {
  posts = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    if (init?.method === 'POST') {
      posts.push({ url: u, body: JSON.parse(String(init.body)) })
      return Promise.resolve(json({ resultados }))
    }
    if (u.includes('/api/facturacion/estados-sos')) {
      return Promise.resolve(json({ items: opciones.estadosSos ?? [] }))
    }
    if (u.includes('/api/facturacion/pendientes')) {
      // `destino_nombre` lo manda el backend: la pantalla no sabe a dónde
      // apunta la instancia y no tiene por qué adivinarlo. `destino` es el
      // slug, que es lo que decide si se ofrece consultar el estado.
      return Promise.resolve(json({
        configurado, destino: opciones.destino ?? 'contalibra',
        destino_nombre: destinoNombre, items,
      }))
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

  // 🔴 El destino lo decide la instancia, y la pantalla tiene que decir el que
  // corresponde. Con el nombre escrito en el .tsx, una instancia que mandaba a
  // SOS Contador seguía ofreciendo "Enviar a Contalibra" — reportado en
  // producción el 2026-08-12, antes de que existiera este test.
  it('nombra el destino que informa el backend, no uno fijo', async () => {
    montar([REMITO], true, [], 'SOS Contador')
    render(<Facturacion />)

    expect(await screen.findByText(/bandeja de SOS Contador/i)).toBeInTheDocument()

    // El botón sólo existe con algo elegido.
    await userEvent.click((await screen.findAllByRole('checkbox'))[0])
    expect(await screen.findByRole('button', { name: /Enviar a SOS Contador/i }))
      .toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Enviar a Contalibra/i })).toBeNull()
  })

  it('sin destino informado no inventa un nombre', async () => {
    // Backend viejo que todavía no manda `destino_nombre`: la pantalla se
    // degrada a un texto genérico, nunca a "undefined".
    montar([REMITO], true, [], undefined as unknown as string)
    render(<Facturacion />)

    await userEvent.click((await screen.findAllByRole('checkbox'))[0])
    const boton = await screen.findByRole('button', { name: /^Enviar a/i })
    expect(boton.textContent).not.toMatch(/undefined/i)
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

  it('el número abre el remito, sin salir a buscarlo a otra pantalla', async () => {
    // Reportado probando en la demo (2026-08-14): "tampoco puedo ver el remito
    // desde ese listado, no puedo entrar al remito". Es la pantalla donde se
    // decide si algo se manda a facturar, y era la única lista del producto
    // desde la que no se podía abrir el comprobante que se estaba por mandar.
    montar([REMITO, OTRO_REMITO])
    render(<Facturacion />)

    const link = await screen.findByRole('link', { name: 'REM-00000001' })

    expect(link).toHaveAttribute('href', '/remitos/1')
    expect(await screen.findByRole('link', { name: 'REM-00000002' }))
      .toHaveAttribute('href', '/remitos/2')
  })

  it('abrir el remito no lo tilda para enviar', async () => {
    // El link vive en una fila que además tiene checkbox. Si navegar arrastrara
    // la selección, mirar un comprobante lo dejaría elegido para mandar a
    // facturar sin que nadie lo pidiera.
    montar([REMITO])
    render(<Facturacion />)

    await userEvent.click(await screen.findByRole('link', { name: 'REM-00000001' }))

    expect(screen.queryByText(/comprobante elegido/)).toBeNull()
    expect((screen.getAllByRole('checkbox')[0] as HTMLInputElement).checked)
      .toBe(false)
  })

  it('tildar uno no arrastra al otro', async () => {
    montar([REMITO, OTRO_REMITO])
    render(<Facturacion />)
    await screen.findByText('REM-00000001')

    await userEvent.click(screen.getAllByRole('checkbox')[0])

    expect(await screen.findByText(/1 comprobante elegido/)).toBeInTheDocument()
  })

  it('todo lo elegido sale en un solo request', async () => {
    // Mientras la bandeja ofrecía presupuestos, esto eran dos requests, uno
    // por tipo. Ahora hay un solo origen posible.
    montar([REMITO, OTRO_REMITO])
    render(<Facturacion />)
    await screen.findByText('REM-00000002')

    // Se vuelve a consultar entre clicks: la tabla se rerenderiza y los nodos
    // de antes quedan desprendidos, así que el segundo click sobre la
    // referencia vieja no llega a ninguna parte.
    await userEvent.click(screen.getAllByRole('checkbox')[0])
    await userEvent.click(screen.getAllByRole('checkbox')[1])
    expect(await screen.findByText(/2 comprobantes elegidos/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Enviar a Contalibra/i }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].body).toEqual({ origen_tipo: 'remito', ids: [1, 2] })
  })

  // 🔴 La fila del presupuesto desapareció de esta pantalla el 2026-08-13. El
  // que la venía usando así necesita leer acá a dónde se fue: sin esto, la
  // pantalla se ve rota en vez de cambiada.
  it('explica que sólo se manda el remito y cómo llega lo demás', async () => {
    montar([REMITO])
    render(<Facturacion />)

    const aviso = await screen.findByText(/un presupuesto aceptado o un reclamo/i)
    expect(aviso).toBeInTheDocument()
    expect(aviso.textContent).toMatch(/convirtiéndose en remito/i)
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

  it('sin nada para mandar lo dice, y dice cómo aparece algo', async () => {
    montar([])
    render(<Facturacion />)
    expect(
      await screen.findByText(/No hay remitos para mandar/i),
    ).toBeInTheDocument()
  })
})

// ── El estado del comprobante del lado del contador ─────────────────────────
//
// Lo pidió el humano el 2026-08-18, después del primer envío real: *"podemos
// ver cuál es el estado del remito que mandamos... para saber si todavía está
// sin CAE, si obtuvo CAE"*. Antes no había forma de saberlo sin entrar a SOS.

describe('consultar el estado en el contador', () => {
  const CON_ENVIO = {
    ...REMITO,
    envio: {
      id: 1, origen_tipo: 'remito', origen_id: 1, estado: 'enviado',
      comprobante_remoto_id: 906683730, detalle: '',
      enviado_at: '2026-08-18', actualizado_at: '2026-08-18',
    },
  }

  it('🔴 con Contalibra no se ofrece: esa bandeja no expone el estado', async () => {
    montar([CON_ENVIO], true, [], 'Contalibra', { destino: 'contalibra' })
    render(<Facturacion />)
    await screen.findByText('REM-00000001')

    expect(screen.queryByRole('button', { name: /Consultar estado/i }))
      .not.toBeInTheDocument()
  })

  it('antes de consultar no dice nada, que no es lo mismo que "sin emitir"', async () => {
    montar([CON_ENVIO], true, [], 'SOS Contador', { destino: 'sos' })
    render(<Facturacion />)
    await screen.findByText('REM-00000001')

    // El botón está, pero la columna todavía no afirma nada. Sin este control,
    // una pantalla que mostrara "Sin emitir" de arranque se vería igual —
    // y estaría diciendo algo que no consultó.
    expect(screen.getByRole('button', { name: /Consultar estado/i })).toBeInTheDocument()
    expect(screen.queryByText(/Sin emitir/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Emitido/i)).not.toBeInTheDocument()
  })

  it('un comprobante sin CAE se lee "Sin emitir", con su número', async () => {
    montar([CON_ENVIO], true, [], 'SOS Contador', {
      destino: 'sos',
      estadosSos: [{ origen_id: 1, comprobante_remoto_id: 906683730,
                     emitido: false, cae: '', comprobante: 'FA 0015-00000001' }],
    })
    render(<Facturacion />)
    await screen.findByText('REM-00000001')

    await userEvent.click(screen.getByRole('button', { name: /Consultar estado/i }))

    expect(await screen.findByText(/Sin emitir/i)).toBeInTheDocument()
    expect(screen.getByText('FA 0015-00000001')).toBeInTheDocument()
  })

  it('cuando el contador emite aparece el CAE', async () => {
    montar([CON_ENVIO], true, [], 'SOS Contador', {
      destino: 'sos',
      estadosSos: [{ origen_id: 1, comprobante_remoto_id: 906683730,
                     emitido: true, cae: '71234567890123',
                     comprobante: 'FA 0015-00000001' }],
    })
    render(<Facturacion />)
    await screen.findByText('REM-00000001')

    await userEvent.click(screen.getByRole('button', { name: /Consultar estado/i }))

    expect(await screen.findByText(/Emitido/i)).toBeInTheDocument()
    expect(screen.getByText(/71234567890123/)).toBeInTheDocument()
  })

  it('una fila que no se pudo leer lo dice, y no tumba a las demás', async () => {
    const OTRO_CON_ENVIO = { ...CON_ENVIO, id: 2, numero: 'REM-00000002' }
    montar([CON_ENVIO, OTRO_CON_ENVIO], true, [], 'SOS Contador', {
      destino: 'sos',
      estadosSos: [
        { origen_id: 1, comprobante_remoto_id: 1, error: 'SOS no devolvió la cabecera' },
        { origen_id: 2, comprobante_remoto_id: 2, emitido: true, cae: '999' },
      ],
    })
    render(<Facturacion />)
    await screen.findByText('REM-00000001')

    await userEvent.click(screen.getByRole('button', { name: /Consultar estado/i }))

    expect(await screen.findByText(/No se pudo leer/i)).toBeInTheDocument()
    // Y la otra fila igual muestra lo suyo: con veinte comprobantes, que uno
    // falle no puede dejar la pantalla sin los diecinueve.
    expect(screen.getByText(/Emitido/i)).toBeInTheDocument()
  })
})
