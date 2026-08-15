// Recepción de equipos para reparación (pedido 43).
//
// Lo que estos tests fijan es lo que se ve y lo que se manda, en ese orden de
// importancia:
//
// 1. **El comprobante se abre solo al recibir.** El punto del pedido es darle
//    el papel al cliente, que está parado en el mostrador. Si hay que buscar un
//    botón más, a veces no se imprime.
// 2. **El equipo de mostrador no necesita estar en el inventario**, y cuando sí
//    está, lo que se manda son los campos copiados.
// 3. **Un equipo ya entregado no ofrece entregar ni borrar.** El backend lo
//    rechaza, así que ofrecerlo sería ofrecer un 409.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RecepcionesEntregados, RecepcionesTaller } from '../pages/Recepciones'
import { escribirEn } from './escribir'

const render = (ui: ReactElement) => renderRTL(<MemoryRouter>{ui}</MemoryRouter>)

const CLIENTE = {
  id: 1, nombre: 'Estudio Sur', empresa: null, email: null, telefono: null,
  ciudad: null, cuit: null, domicilio: null, observaciones: null,
  tipo_facturacion: 'mensual', activo: true, fecha_creacion: null,
}

const EQUIPO = {
  id: 7, cliente_id: 1, tipo: 'Notebook', modelo: 'ThinkPad T14',
  marca: 'Lenovo', serial: 'LN-0001', ubicacion_oficina: null, sector: null,
  deposito_id: null, deposito_nombre: null, estado: 'activo',
  fecha_adicion: null, garantia_vence: null, observaciones: null,
}

const TECNICO = {
  id: 3, nombre: 'Sofía Núñez', activo: true, es_tecnico: true,
  es_recepcionista: false, es_vendedor: false, es_responsable: false,
  roles: ['tecnico'],
}

const EN_TALLER = {
  id: 11, numero: 'REC-00000001', fecha_recepcion: '2026-08-05T10:30:00',
  cliente_id: 1, cliente_nombre: 'Estudio Sur', contacto: 'Marta Ríos',
  contacto_telefono: null, equipo_id: 7, equipo_tipo: 'Notebook',
  equipo_marca: 'Lenovo', equipo_modelo: 'ThinkPad T14', equipo_serial: 'LN-0001',
  equipo_descripcion: 'Notebook Lenovo ThinkPad T14',
  accesorios: 'Cargador original', estado_fisico: 'Tapa rayada',
  falla_declarada: 'No enciende', observaciones: null,
  tecnico_id: 3, tecnico_nombre: 'Sofía Núñez', entregado_por: 'Marta Ríos',
  incidencia_id: 42,
  numero_entrega: null, fecha_entrega: null, retirado_por: null,
  trabajo_realizado: null, observaciones_entrega: null,
  tecnico_entrega_id: null, tecnico_entrega_nombre: null,
  en_taller: true, dias_en_taller: 2, usuario: 'admin', created_at: null,
}

const ENTREGADO = {
  ...EN_TALLER, id: 12, numero: 'REC-00000002',
  equipo_descripcion: 'Impresora HP M404', equipo_id: null,
  equipo_tipo: 'Impresora', equipo_marca: 'HP', equipo_modelo: 'M404',
  equipo_serial: 'HP-9999',
  numero_entrega: 'ENT-00000001', fecha_entrega: '2026-08-06T16:00:00',
  retirado_por: 'Marta Ríos', trabajo_realizado: 'Cambio de fusor',
  en_taller: false, dias_en_taller: 1,
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let pedidos: { url: string; metodo: string; cuerpo: unknown }[] = []
let abiertas: string[] = []

beforeEach(() => {
  pedidos = []
  abiertas = []
  vi.stubGlobal('open', vi.fn((url: string) => { abiertas.push(String(url)) }))
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    const metodo = opciones?.method ?? 'GET'
    pedidos.push({
      url: u, metodo,
      cuerpo: opciones?.body ? JSON.parse(String(opciones.body)) : null,
    })
    if (metodo === 'POST' && u.endsWith('/api/ingresos-reparacion')) {
      return Promise.resolve(json({ ...EN_TALLER, id: 99 }))
    }
    if (metodo !== 'GET') return Promise.resolve(json({ ok: true }))
    if (u.includes('/api/ingresos-reparacion?en_taller=true')) {
      return Promise.resolve(json([EN_TALLER]))
    }
    if (u.includes('/api/ingresos-reparacion?en_taller=false')) {
      return Promise.resolve(json([ENTREGADO]))
    }
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    if (u.includes('/api/equipos')) return Promise.resolve(json([EQUIPO]))
    if (u.includes('/api/tecnicos')) return Promise.resolve(json([TECNICO]))
    return Promise.resolve(json([]))
  }))
})

describe('En el taller', () => {
  it('muestra el número, el equipo y la falla declarada', async () => {
    render(<RecepcionesTaller />)
    await screen.findByText('REC-00000001')

    expect(screen.getByText('Notebook Lenovo ThinkPad T14')).toBeInTheDocument()
    expect(screen.getByText('LN-0001')).toBeInTheDocument()
    expect(screen.getByText(/No enciende/)).toBeInTheDocument()
    expect(screen.getByText(/Accesorios: Cargador original/)).toBeInTheDocument()
    expect(screen.getByText(/hace 2 días/)).toBeInTheDocument()
  })

  it('el comprobante de recepción es un enlace real, no un window.open', async () => {
    // Mismo criterio que el PDF del ticket: un `<a href>` se puede abrir en
    // otra pestaña, copiar y mandar por mail. Un `onClick` no.
    render(<RecepcionesTaller />)
    await screen.findByText('REC-00000001')

    expect(screen.getByRole('link', { name: 'Recepción' }))
      .toHaveAttribute('href', '/api/ingresos-reparacion/11/pdf/recepcion')
  })

  it('🔴 uno en el taller NO ofrece el comprobante de entrega', async () => {
    // Sería darle al cliente un papel que dice que se llevó lo que no se llevó,
    // y además el backend lo rechaza con 409.
    render(<RecepcionesTaller />)
    await screen.findByText('REC-00000001')

    expect(screen.queryByRole('link', { name: 'Entrega' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Entregar/ })).toBeInTheDocument()
  })

  it('pide sólo los que están en el taller', async () => {
    render(<RecepcionesTaller />)
    await screen.findByText('REC-00000001')
    expect(pedidos.some((p) => p.url.includes('en_taller=true'))).toBe(true)
    expect(pedidos.some((p) => p.url.includes('en_taller=false'))).toBe(false)
  })
})

describe('Entregados', () => {
  it('muestra el segundo número, cuándo y a quién', async () => {
    render(<RecepcionesEntregados />)
    await screen.findByText('REC-00000002')

    expect(screen.getByText('ENT-00000001')).toBeInTheDocument()
    expect(screen.getByText(/a Marta Ríos/)).toBeInTheDocument()
    expect(screen.getByText(/Cambio de fusor/)).toBeInTheDocument()
  })

  it('🔴 uno ya entregado no ofrece entregar de nuevo ni borrar', async () => {
    // Las dos cosas las rechaza el backend con 409: el comprobante ya está en
    // manos del cliente. Ofrecerlas sería ofrecer un error.
    render(<RecepcionesEntregados />)
    await screen.findByText('REC-00000002')

    expect(screen.queryByRole('button', { name: /Entregar/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Eliminar/ })).not.toBeInTheDocument()
    // Pero los dos comprobantes se siguen pudiendo reimprimir. Nombres exactos
    // y no `/Entrega/`: esa regex también matchea la pestaña "Entregados" del
    // conmutador, y el test fallaba por ambigüedad en vez de por el hecho.
    expect(screen.getByRole('link', { name: 'Recepción' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Entrega' })).toBeInTheDocument()
  })
})

describe('Recibir un equipo', () => {
  async function abrirAlta() {
    const user = userEvent.setup()
    render(<RecepcionesTaller />)
    await screen.findByText('REC-00000001')
    await user.click(screen.getByRole('button', { name: /Recibir equipo/ }))
    return { user, dialogo: await screen.findByRole('dialog') }
  }

  it('manda los campos del pedido y NO manda cadenas vacías', async () => {
    const { user, dialogo } = await abrirAlta()

    await user.click(within(dialogo).getByRole('combobox', { name: 'Cliente' }))
    await user.click(await within(await screen.findByRole('listbox'))
      .findByRole('option', { name: /Estudio Sur/ }))

    await escribirEn(within(dialogo).getByLabelText('Tipo'), 'Notebook')
    await escribirEn(within(dialogo).getByLabelText('Falla declarada por el cliente'),
                     'No enciende')
    await escribirEn(within(dialogo).getByLabelText('Accesorios entregados'),
                     'Cargador')
    await user.click(within(dialogo).getByRole('button', { name: /Recibir e imprimir/ }))

    await waitFor(() => {
      const alta = pedidos.find((p) => p.metodo === 'POST')
      expect(alta).toBeDefined()
      expect(alta!.cuerpo).toMatchObject({
        cliente_id: 1, equipo_tipo: 'Notebook',
        falla_declarada: 'No enciende', accesorios: 'Cargador',
        // Lo que no se cargó viaja como null, no como "" — así el comprobante
        // imprime "—" y no un renglón en blanco que parece un dato.
        equipo_marca: null, estado_fisico: null, entregado_por: null,
        equipo_id: null,
      })
    })
  })

  it('🔴 al recibir se abre el comprobante para imprimir', async () => {
    // El punto del pedido: el papel se le da al cliente que está en el
    // mostrador. Un botón más para imprimirlo es un papel que a veces no sale.
    const { user, dialogo } = await abrirAlta()

    await user.click(within(dialogo).getByRole('combobox', { name: 'Cliente' }))
    await user.click(await within(await screen.findByRole('listbox'))
      .findByRole('option', { name: /Estudio Sur/ }))
    await escribirEn(within(dialogo).getByLabelText('Tipo'), 'Notebook')
    await user.click(within(dialogo).getByRole('button', { name: /Recibir e imprimir/ }))

    await waitFor(() => {
      expect(abiertas).toContain('/api/ingresos-reparacion/99/pdf/recepcion')
    })
  })

  it('sin cliente no se puede guardar', async () => {
    const { dialogo } = await abrirAlta()
    expect(within(dialogo).getByRole('button', { name: /Recibir e imprimir/ }))
      .toBeDisabled()
  })

  it('el equipo del inventario es opcional y ofrece decirlo', async () => {
    const { user, dialogo } = await abrirAlta()
    await user.click(within(dialogo).getByRole('combobox', { name: 'Cliente' }))
    await user.click(await within(await screen.findByRole('listbox'))
      .findByRole('option', { name: /Estudio Sur/ }))

    await user.click(within(dialogo).getByRole('combobox', { name: 'Equipo del inventario' }))
    const opciones = within(await screen.findByRole('listbox'))
      .getAllByRole('option').map((o) => o.textContent)
    expect(opciones.some((t) => t?.includes('No está en el inventario'))).toBe(true)
    expect(opciones.some((t) => t?.includes('LN-0001'))).toBe(true)
  })
})

describe('Entregar', () => {
  it('manda el trabajo realizado y abre el comprobante de entrega', async () => {
    const user = userEvent.setup()
    render(<RecepcionesTaller />)
    await screen.findByText('REC-00000001')

    await user.click(screen.getByRole('button', { name: /Entregar/ }))
    const dialogo = await screen.findByRole('dialog')
    await escribirEn(within(dialogo).getByLabelText('Trabajo realizado'),
                     'Cambio de teclado')
    await user.click(within(dialogo).getByRole('button', { name: /Entregar e imprimir/ }))

    await waitFor(() => {
      const entrega = pedidos.find((p) => p.url.includes('/entregar'))
      expect(entrega?.cuerpo).toMatchObject({
        trabajo_realizado: 'Cambio de teclado', retirado_por: 'Marta Ríos',
      })
    })
    await waitFor(() => {
      expect(abiertas).toContain('/api/ingresos-reparacion/11/pdf/entrega')
    })
  })

  it('el diálogo avisa que la entrega no se deshace', async () => {
    const user = userEvent.setup()
    render(<RecepcionesTaller />)
    await screen.findByText('REC-00000001')

    await user.click(screen.getByRole('button', { name: /Entregar/ }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText(/no se puede deshacer/)).toBeInTheDocument()
    expect(within(dialogo).getByText(/REC-00000001/)).toBeInTheDocument()
  })
})
