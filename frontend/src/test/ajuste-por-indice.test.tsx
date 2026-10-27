// El ajuste por índice de un contrato (ADR-018, revisión 0043): el alta lo pide
// y la ficha lo muestra y lo aplica.
//
// Lo que estos tests fijan:
//
// 1. **El alta con método «índice» pide el índice y cada cuánto, y los manda.**
//    Con cualquier otro método los manda en `null` (la API los espera así, no
//    ausentes), y sin ellos no se deja guardar.
// 2. 🔴 **Un «índice» que quedó escondido no viaja.** El selector del método
//    vive en el bloque de cobro; si se elige «índice» y después se cambia la
//    modalidad a una sin cuota, el bloque desaparece. Sin la guarda, el POST
//    saldría con método «índice» y sin índice —un error del backend por campos
//    que la pantalla ya no muestra.
// 3. **La tarjeta de la ficha dibuja las cuatro respuestas** del backend: la
//    propuesta, el «ya ajustado», el 409 de texto y el 409 de «falta un valor».
// 4. **«Aplicar ajuste» manda sólo la `fecha_ajuste` de la propuesta**, y la
//    ficha se recarga: el precio nuevo aparece en el historial.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ContratoNuevo } from '../pages/ContratoNuevo'
import { ContratoDetalle } from '../pages/ContratoDetalle'

const NOMBRE_ICL = 'Índice para Contratos de Locación (ICL, base 30-06-2020 = 1)'
const NOMBRE_CASA_PROPIA = 'Casa Propia'

const INDICES = [
  { clave: 'icl', nombre: NOMBRE_ICL, periodicidad: 'diaria', se_baja_solo: true },
  { clave: 'ipc', nombre: 'Índice de Precios al Consumidor (IPC)', periodicidad: 'mensual', se_baja_solo: true },
  { clave: 'casa_propia', nombre: NOMBRE_CASA_PROPIA, periodicidad: 'mensual', se_baja_solo: false },
]

const CLIENTE = {
  id: 3, nombre: 'Estudio Contable Sur', email: null, telefono: null,
  cuit: null, domicilio: null, activo: true,
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

const render = (ruta: string) => renderRTL(
  <MemoryRouter initialEntries={[ruta]}>
    <Routes>
      <Route path="/contratos/nuevo" element={<ContratoNuevo />} />
      <Route path="/contratos/:id" element={<ContratoDetalle />} />
    </Routes>
  </MemoryRouter>,
)

/** Elige una opción de un `Select` de Radix, por el nombre del disparador. */
async function elegirEnRadix(user: ReturnType<typeof userEvent.setup>, campo: string, opcion: string) {
  await user.click(screen.getByRole('combobox', { name: campo }))
  await user.click(await screen.findByRole('option', { name: opcion }))
}

// --- el alta ---------------------------------------------------------------

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
    if (u.includes('/api/contratos/ajustes/indices')) return Promise.resolve(json(INDICES))
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    return Promise.resolve(json([]))
  }))
})

async function elegirCliente(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('combobox', { name: 'Cliente (locatario)' }))
  await user.click(await screen.findByText('Estudio Contable Sur'))
}

describe('El alta con ajuste por índice', () => {
  it('con otro método no ofrece los dos campos, no pide el catálogo y manda null', async () => {
    const user = userEvent.setup()
    render('/contratos/nuevo')
    await screen.findByRole('heading', { name: 'Nuevo contrato' })

    expect(screen.queryByRole('combobox', { name: 'Índice' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Se ajusta cada' })).not.toBeInTheDocument()

    await elegirCliente(user)
    await user.click(screen.getByRole('button', { name: /Crear contrato/ }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].cuerpo.metodo_actualizacion).toBe('manual')
    // `null` y no ausentes: es lo que la API espera.
    expect(posts[0].cuerpo).toHaveProperty('indice_ajuste', null)
    expect(posts[0].cuerpo).toHaveProperty('periodicidad_ajuste', null)
    // Y nadie pidió el catálogo: la mayoría de los contratos no se ajusta así.
    expect(pedidos.filter((u) => u.includes('ajustes/indices'))).toEqual([])
  })

  it('con método índice ofrece el índice y cada cuánto, y los manda en el alta', async () => {
    const user = userEvent.setup()
    render('/contratos/nuevo')
    await screen.findByRole('heading', { name: 'Nuevo contrato' })

    await elegirEnRadix(user, 'Actualización del precio', 'Índice configurable')

    // Las dos con nombre accesible: son las que un lector de pantalla anuncia.
    await user.click(await screen.findByRole('combobox', { name: 'Índice' }))
    await user.click(await screen.findByText(NOMBRE_ICL))
    await elegirEnRadix(user, 'Se ajusta cada', 'Trimestral')

    await elegirCliente(user)
    await user.click(screen.getByRole('button', { name: /Crear contrato/ }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].url).toBe('/api/contratos')
    expect(posts[0].cuerpo.metodo_actualizacion).toBe('indice')
    expect(posts[0].cuerpo.indice_ajuste).toBe('icl')
    expect(posts[0].cuerpo.periodicidad_ajuste).toBe('trimestral')
  })

  it('sin índice ni periodicidad no se manda nada, y dice qué falta', async () => {
    const user = userEvent.setup()
    render('/contratos/nuevo')
    await screen.findByRole('heading', { name: 'Nuevo contrato' })

    await elegirEnRadix(user, 'Actualización del precio', 'Índice configurable')
    await screen.findByRole('combobox', { name: 'Índice' })
    // El cliente sí está: lo único que falta es lo del ajuste, así que el
    // formulario no puede estar frenado por otra cosa.
    await elegirCliente(user)
    await user.click(screen.getByRole('button', { name: /Crear contrato/ }))

    await waitFor(() => {
      const mensajes = [...document.querySelectorAll('[data-slot="form-message"]')]
        .map((m) => m.textContent)
      expect(mensajes).toEqual(['Elegí el índice', 'Elegí cada cuánto se ajusta'])
    })
    expect(posts).toHaveLength(0)
  })

  it('con el índice y sin la periodicidad tampoco se manda', async () => {
    const user = userEvent.setup()
    render('/contratos/nuevo')
    await screen.findByRole('heading', { name: 'Nuevo contrato' })

    await elegirEnRadix(user, 'Actualización del precio', 'Índice configurable')
    await user.click(await screen.findByRole('combobox', { name: 'Índice' }))
    await user.click(await screen.findByText(NOMBRE_ICL))
    await elegirCliente(user)
    await user.click(screen.getByRole('button', { name: /Crear contrato/ }))

    await waitFor(() => expect(
      document.querySelector('[data-slot="form-message"]')?.textContent,
    ).toBe('Elegí cada cuánto se ajusta'))
    expect(posts).toHaveLength(0)
  })

  it('un índice que se carga a mano lo avisa al elegirlo', async () => {
    const user = userEvent.setup()
    render('/contratos/nuevo')
    await screen.findByRole('heading', { name: 'Nuevo contrato' })

    await elegirEnRadix(user, 'Actualización del precio', 'Índice configurable')
    await user.click(await screen.findByRole('combobox', { name: 'Índice' }))
    await user.click(await screen.findByText(NOMBRE_CASA_PROPIA))

    expect(await screen.findByText(/se carga a mano: hasta que estén sus valores/))
      .toBeInTheDocument()
  })

  it('🔴 un método índice que quedó escondido no viaja: sale manual y sin índice', async () => {
    const user = userEvent.setup()
    render('/contratos/nuevo')
    await screen.findByRole('heading', { name: 'Nuevo contrato' })

    await elegirEnRadix(user, 'Actualización del precio', 'Índice configurable')
    await screen.findByRole('combobox', { name: 'Índice' })
    // Se cambia la modalidad a una sin cuota: el bloque entero desaparece, con
    // el método y los dos campos del ajuste adentro.
    await elegirEnRadix(user, 'Modalidad', 'Comodato')
    await waitFor(() =>
      expect(screen.queryByText('Cobro y visitas')).not.toBeInTheDocument())

    await elegirCliente(user)
    await user.click(screen.getByRole('button', { name: /Crear contrato/ }))

    // Sin la guarda no se llegaba acá: los campos escondidos frenaban el envío
    // sin decir por qué, o el backend lo rechazaba por falta de índice.
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].cuerpo.metodo_actualizacion).toBe('manual')
    expect(posts[0].cuerpo.indice_ajuste).toBeNull()
    expect(posts[0].cuerpo.periodicidad_ajuste).toBeNull()
  })
})

// --- la ficha --------------------------------------------------------------

const PRECIO_VIGENTE = {
  id: 1, contrato_id: 1, vigencia_desde: '2026-08-15', vigencia_hasta: null,
  vigente: true, importe: 100000, moneda: 'ARS', motivo: 'alta',
  usuario: 'admin', created_at: null,
}

const CONTRATO_INDICE = {
  id: 1, numero: 'CTR-00000001', tipo_contrato: 'alquiler',
  cliente_id: 1, cliente_nombre: 'Estudio Contable Sur',
  propietario_cliente_id: null, propietario_nombre: null,
  sector_id: null, domicilio_instalacion: 'Sucursal Mercedes',
  fecha_inicio: '2026-08-15', fecha_fin: null, renovacion_automatica: false,
  periodicidad: 'mensual', dia_vencimiento: 10, moneda: 'ARS',
  metodo_actualizacion: 'indice', indice_ajuste: 'icl', periodicidad_ajuste: 'trimestral',
  estado: 'activo', responsable: null,
  observaciones: null, archivo_pdf: null, created_at: null,
  importe_vigente: 100000, precio_vigente_desde: '2026-08-15',
  lleva_cuota: true, equipos_vigentes: 0,
  lineas: [], precios: [PRECIO_VIGENTE],
}

const AJUSTE = {
  indice: 'icl', indice_nombre: NOMBRE_ICL,
  fecha_base: '2026-08-15', fecha_ajuste: '2026-11-15',
  importe_anterior: 100000, importe_nuevo: 112500.5,
  coeficiente: '1.1250050000', variacion_pct: 12.50050,
  valores: [
    { fecha: '2026-08-15', valor: '1.8', fuente: 'BCRA' },
    { fecha: '2026-11-15', valor: '2.025009', fuente: 'BCRA' },
  ],
}

const PROPUESTA = {
  corresponde: true, indice: 'icl', periodicidad_ajuste: 'trimestral',
  fecha_ajuste: '2026-11-15', proximo_ajuste: '2027-02-15',
  precio_vigente: 100000, precio_vigente_desde: '2026-08-15',
  ajuste: AJUSTE,
}

const YA_AJUSTADO = {
  ...PROPUESTA, corresponde: false, ajuste: null,
  precio_vigente: 112500.5, precio_vigente_desde: '2026-11-15',
  proximo_ajuste: '2027-02-15',
}

type Ficha = {
  contrato?: Record<string, unknown>
  /** Lo que contesta `GET .../ajuste`: `[status, cuerpo]`. */
  ajuste: [number, unknown]
  /** Lo que contesta `POST .../ajuste`. */
  aplicar?: [number, unknown]
}

/** Arma el `fetch` de la ficha. Devuelve lo que se pidió, para afirmar sobre
 *  las URLs y los cuerpos y no sólo sobre lo que se ve. */
function montarFicha(ficha: Ficha) {
  const log: { metodo: string; url: string; cuerpo: any }[] = []
  let aplicado = false
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    log.push({ metodo, url: u, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })

    if (u.includes('/api/contratos/ajustes/indices')) return Promise.resolve(json(INDICES))
    // Antes que `/api/contratos/1`, que lo contiene.
    if (u.endsWith('/api/contratos/1/ajuste')) {
      if (metodo === 'POST') {
        const [status, cuerpo] = ficha.aplicar ?? [201, { precio: {}, ajuste: AJUSTE }]
        if (status < 300) aplicado = true
        return Promise.resolve(json(cuerpo, status))
      }
      const [status, cuerpo] = aplicado ? [200, YA_AJUSTADO] : ficha.ajuste
      return Promise.resolve(json(cuerpo, status))
    }
    if (u.includes('/actas')) return Promise.resolve(json([]))
    if (u.includes('/api/contratos/1')) {
      const base = ficha.contrato ?? CONTRATO_INDICE
      if (!aplicado) return Promise.resolve(json(base))
      // Ya aplicado: el precio viejo se cierra y el ajustado queda vigente,
      // con el motivo que escribe el backend.
      return Promise.resolve(json({
        ...base,
        importe_vigente: 112500.5, precio_vigente_desde: '2026-11-15',
        precios: [
          {
            ...PRECIO_VIGENTE, id: 2, vigencia_desde: '2026-11-15', importe: 112500.5,
            motivo: 'ajuste_indice:icl',
          },
          { ...PRECIO_VIGENTE, vigencia_hasta: '2026-11-14', vigente: false },
        ],
      }))
    }
    return Promise.resolve(json([]))
  }))
  return log
}

/** La tarjeta, por su título: la pestaña «Contrato» la abre sola. */
async function tarjeta() {
  const titulo = await screen.findByText('Ajuste por índice')
  return titulo.closest('[data-slot="card"]') as HTMLElement
}

describe('Ficha del contrato — datos del ajuste', () => {
  it('muestra el índice (por su nombre) y cada cuánto se ajusta', async () => {
    montarFicha({ ajuste: [200, PROPUESTA] })
    render('/contratos/1')

    expect(await screen.findByText('Índice de ajuste')).toBeInTheDocument()
    // El nombre sale del catálogo, no la clave del contrato. Dentro de «Datos
    // del contrato» y no en la pantalla: la tarjeta del ajuste lo repite.
    const datos = screen.getByText('Datos del contrato').closest('[data-slot="card"]') as HTMLElement
    await waitFor(() => expect(within(datos).getByText(NOMBRE_ICL)).toBeInTheDocument())
    expect(within(datos).getByText('Se ajusta cada')).toBeInTheDocument()
    expect(within(datos).getByText('Trimestral')).toBeInTheDocument()
  })

  it('un contrato que no se ajusta por índice no tiene la tarjeta ni pide el ajuste', async () => {
    const log = montarFicha({
      ajuste: [409, { detail: 'Este contrato no se actualiza por índice.' }],
      contrato: { ...CONTRATO_INDICE, metodo_actualizacion: 'manual', indice_ajuste: null, periodicidad_ajuste: null },
    })
    render('/contratos/1')

    await screen.findByText('Datos del contrato')
    expect(screen.queryByText('Ajuste por índice')).not.toBeInTheDocument()
    expect(screen.queryByText('Índice de ajuste')).not.toBeInTheDocument()
    expect(log.filter((p) => p.url.includes('/ajuste') || p.url.includes('ajustes/indices')))
      .toEqual([])
  })
})

describe('Ficha del contrato — la tarjeta «Ajuste por índice»', () => {
  it('con un ajuste que corresponde, muestra la propuesta y los valores que tomó', async () => {
    const log = montarFicha({ ajuste: [200, PROPUESTA] })
    render('/contratos/1')
    const t = within(await tarjeta())

    // Importe vigente y ajustado, con centavos: el ajuste los tiene.
    expect(await t.findByText('$ 100.000,00')).toBeInTheDocument()
    expect(t.getByText('$ 112.500,50')).toBeInTheDocument()
    expect(t.getByText('+12,50 %')).toBeInTheDocument()
    // La fecha del ajuste, en el formato del producto.
    expect(t.getAllByText('15-11-2026').length).toBeGreaterThan(0)
    // Los valores del índice: fecha, valor (con coma) y fuente.
    const filas = t.getAllByRole('row').slice(1)
    expect(filas.map((f) => within(f).getAllByRole('cell').map((c) => c.textContent))).toEqual([
      ['15-08-2026', '1,8', 'BCRA'],
      ['15-11-2026', '2,025009', 'BCRA'],
    ])
    expect(t.getByRole('button', { name: /Aplicar ajuste/ })).toBeInTheDocument()
    // Pedir la propuesta no escribe nada.
    expect(log.filter((p) => p.metodo === 'POST')).toEqual([])
  })

  it('«Ya ajustado»: dice cuándo es el próximo y no ofrece aplicar', async () => {
    montarFicha({ ajuste: [200, YA_AJUSTADO] })
    render('/contratos/1')
    const t = within(await tarjeta())

    expect(await t.findByText('Ya ajustado; próximo ajuste el 15-02-2027.')).toBeInTheDocument()
    expect(t.queryByRole('button', { name: /Aplicar ajuste/ })).not.toBeInTheDocument()
    expect(t.queryByRole('table')).not.toBeInTheDocument()
  })

  it('si falta un valor del índice, dice cuáles fechas faltan', async () => {
    montarFicha({
      ajuste: [409, { detail: {
        mensaje: 'Faltan valores del índice icl.', indice: 'icl',
        fechas_faltantes: ['2026-11-15', '2026-11-16'],
      } }],
    })
    render('/contratos/1')
    const t = within(await tarjeta())

    expect(await t.findByText('Faltan valores del índice icl.')).toBeInTheDocument()
    // Con el nombre del catálogo y las fechas en dd-mm-aaaa.
    expect(await t.findByText(new RegExp(`Faltan los valores de ${NOMBRE_ICL.replace(/[()]/g, '\\$&')} de: 15-11-2026, 16-11-2026\\.`)))
      .toBeInTheDocument()
    // Un índice que se baja solo no dice que se carga a mano.
    expect(t.queryByText(/se carga a mano/)).not.toBeInTheDocument()
    // Y se puede volver a consultar, pero no aplicar.
    expect(t.getByRole('button', { name: 'Volver a consultar' })).toBeInTheDocument()
    expect(t.queryByRole('button', { name: /Aplicar ajuste/ })).not.toBeInTheDocument()
  })

  it('Casa Propia se carga a mano, y la tarjeta lo dice', async () => {
    montarFicha({
      contrato: { ...CONTRATO_INDICE, indice_ajuste: 'casa_propia' },
      ajuste: [409, { detail: {
        mensaje: 'Faltan valores del índice casa_propia.', indice: 'casa_propia',
        fechas_faltantes: ['2026-10-01'],
      } }],
    })
    render('/contratos/1')
    const t = within(await tarjeta())

    expect(await t.findByText(/Faltan los valores de Casa Propia de: 01-10-2026\./)).toBeInTheDocument()
    expect(await t.findByText(/Este índice se carga a mano/)).toBeInTheDocument()
  })

  it('«Volver a consultar» pide la propuesta otra vez', async () => {
    const user = userEvent.setup()
    const log = montarFicha({
      ajuste: [409, { detail: { mensaje: 'Faltan.', indice: 'icl', fechas_faltantes: ['2026-11-15'] } }],
    })
    render('/contratos/1')
    const t = within(await tarjeta())

    await user.click(await t.findByRole('button', { name: 'Volver a consultar' }))

    await waitFor(() => expect(
      log.filter((p) => p.metodo === 'GET' && p.url.endsWith('/api/contratos/1/ajuste')),
    ).toHaveLength(2))
  })

  it('un 409 de texto (sin precio vigente) se muestra tal cual', async () => {
    montarFicha({
      ajuste: [409, { detail: 'El contrato no tiene un precio vigente sobre el que ajustar.' }],
    })
    render('/contratos/1')
    const t = within(await tarjeta())

    expect(await t.findByText('El contrato no tiene un precio vigente sobre el que ajustar.'))
      .toBeInTheDocument()
    expect(t.queryByRole('button', { name: /Aplicar ajuste/ })).not.toBeInTheDocument()
  })
})

describe('Ficha del contrato — «Aplicar ajuste»', () => {
  it('pide confirmación y, al confirmar, manda la fecha de la propuesta y recarga la ficha', async () => {
    const user = userEvent.setup()
    const log = montarFicha({ ajuste: [200, PROPUESTA] })
    render('/contratos/1')
    const t = within(await tarjeta())

    await user.click(await t.findByRole('button', { name: /Aplicar ajuste/ }))

    // El diálogo dice qué va a pasar con los importes y todavía no escribió.
    const dialogo = within(await screen.findByRole('dialog'))
    // El importe nuevo va en negrita, así que el texto se mide en el párrafo
    // entero y no con un `getByText` que lo parte en dos.
    expect(dialogo.getByText(/El importe pasa de/).textContent).toMatch(
      /^El importe pasa de \$\s100\.000,00 a \$\s112\.500,50 \(\+12,50 %\), vigente desde el 15-11-2026\.$/,
    )
    expect(log.filter((p) => p.metodo === 'POST')).toEqual([])

    await user.click(dialogo.getByRole('button', { name: 'Confirmar' }))

    await waitFor(() => expect(log.filter((p) => p.metodo === 'POST')).toHaveLength(1))
    const post = log.find((p) => p.metodo === 'POST')!
    expect(post.url).toBe('/api/contratos/1/ajuste')
    // 🔑 Sólo la fecha: el backend rehace la cuenta, no se manda el importe.
    expect(post.cuerpo).toEqual({ fecha_ajuste: '2026-11-15' })

    // La ficha se recargó: la tarjeta ahora dice que ya está ajustado…
    expect(await screen.findByText('Ya ajustado; próximo ajuste el 15-02-2027.')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    // …y el precio ajustado está en el historial, con su motivo en castellano.
    await user.click(screen.getByRole('tab', { name: 'Historial' }))
    expect(await screen.findByText('$ 112.501')).toBeInTheDocument()
    expect(screen.getByText('Ajuste por índice (icl)')).toBeInTheDocument()
  })

  it('Cancelar no escribe nada', async () => {
    const user = userEvent.setup()
    const log = montarFicha({ ajuste: [200, PROPUESTA] })
    render('/contratos/1')
    const t = within(await tarjeta())

    await user.click(await t.findByRole('button', { name: /Aplicar ajuste/ }))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancelar' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(log.filter((p) => p.metodo === 'POST')).toEqual([])
  })

  it('si el backend lo rechaza (409), el diálogo queda abierto y dice por qué', async () => {
    const user = userEvent.setup()
    const log = montarFicha({
      ajuste: [200, PROPUESTA],
      aplicar: [409, { detail: 'El período de ajuste en curso ya tiene su precio.' }],
    })
    render('/contratos/1')
    const t = within(await tarjeta())

    await user.click(await t.findByRole('button', { name: /Aplicar ajuste/ }))
    const dialogo = within(await screen.findByRole('dialog'))
    await user.click(dialogo.getByRole('button', { name: 'Confirmar' }))

    expect(await dialogo.findByText('El período de ajuste en curso ya tiene su precio.'))
      .toBeInTheDocument()
    // Sigue abierto, y la ficha no se recargó (un solo GET del contrato).
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(log.filter((p) => p.metodo === 'GET' && p.url.endsWith('/api/contratos/1'))).toHaveLength(1)
  })
})
