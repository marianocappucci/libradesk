// La ficha de una reparación, al click en la fila (2026-08-14).
//
// Pedido del humano: *"en reparaciones no es necesario que haya tanto detalle
// en cada fila, se debería poder hacer click y que se abra un modal con todos
// los datos y el detalle de la reparación"*.
//
// Lo que se afirma acá es el comportamiento, no el estilo:
//
//  1. la fila abre la ficha, y la ficha trae lo que la fila dejó de mostrar;
//  2. **tocar "Registrar vuelta" no abre la ficha** — es la parte que puede
//     romperse sola, porque el clic de un botón burbujea hasta el `<tr>`. Sin
//     la guarda de `DataTable`, registrar la vuelta abriría además el modal
//     equivocado encima;
//  3. la garantía y el costo se muestran JUNTOS. No es cosmético: una versión
//     vieja de la tabla mostraba la insignia en lugar del importe y escondía
//     plata gastada de verdad. Al mudar el dato a la ficha, el riesgo se muda
//     con él.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Reparaciones } from '../pages/Reparaciones'

const CLIENTE = {
  id: 1, nombre: 'Clínica del Sol', empresa: null, email: null, telefono: null,
  ciudad: null, cuit: null, condicion_iva: null, domicilio: null,
  observaciones: null, tipo_facturacion: 'por_servicio', activo: true,
}

const PROVEEDOR = { id: 5, nombre: 'Service Norte', contacto: null, telefono: null }

// Una en service y otra ya vuelta: la segunda es la que lleva diagnóstico,
// costo y garantía, que son los campos que se mudaron a la ficha.
const ABIERTA = {
  id: 10, equipo_id: 3, activo_id: null, es_activo: false, incidencia_id: 77,
  proveedor_id: 5, proveedor_nombre: 'Service Norte',
  equipo_descripcion: 'Impresora HP M404', equipo_serial: 'HP-99123',
  cliente_id: 1, fecha_envio: '2026-08-01', fecha_retorno: null,
  abierta: true, dias_afuera: 13, remito_salida: 'R-0042', rma: 'RMA-8891',
  en_garantia: false, costo: null, diagnostico: null,
  observaciones: 'Se llevó con el cable de red.', usuario: 'ana',
  created_at: '2026-08-01T10:00:00',
}

const CERRADA = {
  id: 11, equipo_id: 4, activo_id: null, es_activo: false, incidencia_id: null,
  proveedor_id: 5, proveedor_nombre: 'Service Norte',
  equipo_descripcion: 'Scanner Fujitsu fi-800', equipo_serial: 'FJ-5521',
  cliente_id: 1, fecha_envio: '2026-07-02', fecha_retorno: '2026-07-20',
  abierta: false, dias_afuera: 18, remito_salida: 'R-0031', rma: null,
  // 🔴 Los dos a la vez, que es el caso que la tabla vieja mostraba mal.
  en_garantia: true, costo: 45000,
  diagnostico: 'Se cambió el rodillo de arrastre.\nQuedó calibrado.',
  observaciones: null, usuario: 'ana',
  created_at: '2026-07-02T09:00:00',
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    if (u.includes('/api/proveedores')) return Promise.resolve(json([PROVEEDOR]))
    if (u.includes('/api/reparaciones')) return Promise.resolve(json([ABIERTA, CERRADA]))
    return Promise.resolve(json([]))
  }))
})

const montar = () => render(<MemoryRouter><Reparaciones /></MemoryRouter>)

/** La fila de la tabla que contiene ese texto. */
const filaDe = (texto: string) => screen.getByText(texto).closest('tr')!

/** El valor del campo de la ficha con esa etiqueta.
 *
 *  Por etiqueta y no por el texto suelto: la fecha de retorno aparece DOS veces
 *  en la ficha —en el resumen del encabezado y en su propio campo— y las dos
 *  son correctas. Un `getByText` de la fecha revienta con "found multiple", y
 *  cambiarlo por un `getAllByText` haría pasar el caso sin saber si el campo
 *  existe. */
function campo(ficha: HTMLElement, etiqueta: string): string {
  return within(ficha).getByText(etiqueta).parentElement!.textContent!
}

describe('la fila resumida', () => {
  it('ya NO muestra el costo, el remito ni el RMA', async () => {
    // El control de que la fila efectivamente adelgazó. Se mide con la ficha
    // CERRADA, que es la que tiene los tres datos cargados: con la abierta,
    // que los tiene en null, este caso pasaría sin que nada hubiera cambiado.
    montar()
    await screen.findByText('Scanner Fujitsu fi-800')

    const fila = filaDe('Scanner Fujitsu fi-800')
    expect(within(fila).queryByText(/45\.000/)).toBeNull()
    expect(within(fila).queryByText(/R-0031/)).toBeNull()
    expect(within(fila).queryByText(/Garantía/)).toBeNull()
  })

  it('sigue mostrando lo que contesta "qué tengo hoy en service"', async () => {
    // La otra mitad del control de arriba: adelgazar no es vaciar. Si esto se
    // cae, la fila quedó sin lo que la pantalla existe para responder.
    montar()
    await screen.findByText('Impresora HP M404')

    const fila = filaDe('Impresora HP M404')
    expect(within(fila).getByText('HP-99123')).toBeInTheDocument()
    expect(within(fila).getByText('Clínica del Sol')).toBeInTheDocument()
    expect(within(fila).getByText('Service Norte')).toBeInTheDocument()
    expect(within(fila).getByText('13 días')).toBeInTheDocument()
    expect(within(fila).getByText('En service')).toBeInTheDocument()
  })
})

describe('la ficha, al click en la fila', () => {
  it('trae los datos que la fila dejó de mostrar', async () => {
    montar()
    await screen.findByText('Scanner Fujitsu fi-800')
    await userEvent.click(filaDe('Scanner Fujitsu fi-800'))

    const ficha = await screen.findByRole('dialog')
    expect(campo(ficha, 'Remito de salida')).toContain('R-0031')
    expect(campo(ficha, 'Retorno')).toContain('20-07-2026')
    expect(campo(ficha, 'Enviado')).toContain('02-07-2026')
    expect(campo(ficha, 'Cargada por')).toContain('ana')
  })

  it('🔴 muestra el diagnóstico, que hasta ahora no se veía en ninguna pantalla', async () => {
    // El campo se cargaba en el diálogo de cierre y después no había forma de
    // volver a leerlo. Es la razón de peso de la ficha, más que el reacomodo.
    montar()
    await screen.findByText('Scanner Fujitsu fi-800')
    await userEvent.click(filaDe('Scanner Fujitsu fi-800'))

    const ficha = await screen.findByRole('dialog')
    expect(within(ficha).getByText(/Se cambió el rodillo de arrastre/)).toBeInTheDocument()
  })

  it('🔴 la garantía y el costo se muestran los DOS, no uno en lugar del otro', async () => {
    // Con `en_garantia` y `costo: 45000` a la vez. Si alguien vuelve a poner la
    // insignia en lugar del importe, esto se pone rojo — que es lo que no pasó
    // la primera vez y costó una pantalla que decía que no se había gastado
    // nada mientras la ficha del equipo sumaba $45.000.
    montar()
    await screen.findByText('Scanner Fujitsu fi-800')
    await userEvent.click(filaDe('Scanner Fujitsu fi-800'))

    const ficha = await screen.findByRole('dialog')
    expect(within(ficha).getByText('Garantía')).toBeInTheDocument()
    expect(within(ficha).getByText(/45\.000/)).toBeInTheDocument()
  })

  it('el ticket que la originó es un link, y sólo si lo hay', async () => {
    montar()
    await screen.findByText('Impresora HP M404')
    await userEvent.click(filaDe('Impresora HP M404'))

    const ficha = await screen.findByRole('dialog')
    expect(within(ficha).getByRole('link', { name: /ticket #77/ }))
      .toHaveAttribute('href', '/incidencias/77')
  })
})

describe('🔴 los controles de la fila no abren la ficha', () => {
  it('"Registrar vuelta" abre el cierre, y no la ficha encima', async () => {
    // El clic de un botón burbujea hasta el `<tr>`. Sin la guarda de
    // `DataTable` —que ignora los clicks sobre `button` y `a`— este gesto
    // abriría los dos diálogos, y el de arriba taparía al formulario.
    montar()
    await screen.findByText('Impresora HP M404')

    const fila = filaDe('Impresora HP M404')
    await userEvent.click(within(fila).getByRole('button', { name: /Registrar vuelta/ }))

    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText('Registrar la vuelta del equipo')).toBeInTheDocument()
    // Uno solo abierto: si la ficha se hubiera abierto también, habría dos.
    await waitFor(() => expect(screen.getAllByRole('dialog')).toHaveLength(1))
    // Y es el de cierre, no la ficha: el diagnóstico es de la ficha.
    expect(within(dialogo).queryByText('Cargada por')).toBeNull()
  })
})
