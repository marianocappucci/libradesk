// La ficha reducida del modo simple (2026-09-09).
//
// Lo que pidió el humano, textual: arriba **nombre del cliente, título del
// reclamo, detalle y quién hizo el reclamo**; al costado **estado, prioridad,
// número de contacto, N° CDS y técnicos asignados**. Y afuera: tareas,
// actividad, materiales usados, y notas internas/resolución.
//
// 🔑 **El test más importante de este archivo es el último**: que la ficha
// COMPLETA no cambió. La garantía que se prometió es que prender el add-on en
// una instancia no le toca nada a las otras, y eso sólo se sostiene si algo lo
// mide.
import { render as renderRTL, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { IncidenciaDetalle } from '../pages/IncidenciaDetalle'

const CLIENTE = {
  id: 1, nombre: 'Metalmax Soluciones', empresa: null, email: null,
  telefono: '2324-40-1234', ciudad: 'Suipacha', cuit: null,
  domicilio: 'Av. San Martín 1240', observaciones: null,
  tipo_facturacion: 'por_servicio', activo: true, fecha_creacion: null,
}

const CLIENTE_CON_ABONO = { ...CLIENTE, id: 2, tipo_facturacion: 'mensual' }

const ANA = {
  id: 1, nombre: 'Ana Gómez', activo: true, es_tecnico: true,
  es_recepcionista: false, es_vendedor: false, es_responsable: false,
  roles: ['tecnico'],
}

const INCIDENCIA = {
  id: 7, cliente_id: 1, equipo_id: null, activo_id: null,
  tecnico_id: null, recepcionista_id: null, vendedor_id: null,
  modalidad: null, sector_id: null, categoria_id: null,
  titulo: 'Central sin tono', descripcion: 'No da tono el interno 5.',
  estado: 'abierto', prioridad: 'media', horas_invertidas: null,
  notas: null, resolucion: null, nro_cds: null, reclamante: 'FACUNDO',
  estado_facturacion: null, activo: true, cobertura_abono: null,
  abono_horas_cubiertas: null, abono_materiales_incluidos: null,
  fecha_creacion: '2026-09-08T10:00:00', fecha_cierre: null,
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let incidencia = { ...INCIDENCIA }
// `typeof CLIENTE` y no el tipo `Cliente` del producto: los stubs son la forma
// del JSON que devuelve la API, no el modelo. El `telefono: null` del caso
// "sin telefono cargado" es un valor legitimo del dato y el tipo del stub
// tiene que admitirlo.
let clientes: (Omit<typeof CLIENTE, 'telefono'> & { telefono: string | null })[] = [CLIENTE]

beforeEach(() => {
  incidencia = { ...INCIDENCIA }
  clientes = [CLIENTE]
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/tecnicos') && u.includes('/api/incidencias/')) return Promise.resolve(json([]))
    if (u.match(/\/api\/incidencias\/\d+$/)) return Promise.resolve(json(incidencia))
    if (u.includes('/api/clientes')) return Promise.resolve(json(clientes))
    if (u.includes('/api/tecnicos')) return Promise.resolve(json([ANA]))
    return Promise.resolve(json([]))
  }))
})

function render(simple: boolean) {
  return renderRTL(
    <MemoryRouter initialEntries={['/x/7']}>
      <Routes>
        <Route path="/x/:id" element={<IncidenciaDetalle simple={simple} />} />
      </Routes>
    </MemoryRouter>,
  )
}

// ── Lo que la ficha simple muestra ─────────────────────────────────────────

describe('La ficha en modo simple', () => {
  it('muestra los cuatro datos de arriba', async () => {
    render(true)

    expect(await screen.findByDisplayValue('Central sin tono')).toBeInTheDocument()
    expect(screen.getByText('Metalmax Soluciones')).toBeInTheDocument()
    expect(screen.getByDisplayValue('No da tono el interno 5.')).toBeInTheDocument()
    expect(screen.getByDisplayValue('FACUNDO')).toBeInTheDocument()
  })

  it('el costado tiene estado, prioridad, teléfono, CDS y técnicos', async () => {
    render(true)
    await screen.findByDisplayValue('Central sin tono')

    expect(screen.getByLabelText('Estado')).toBeInTheDocument()
    expect(screen.getByLabelText('Prioridad')).toBeInTheDocument()
    expect(screen.getByText('2324-40-1234')).toBeInTheDocument()
    expect(screen.getByLabelText('N° CDS')).toBeInTheDocument()
    expect(screen.getByText('Técnicos que fueron')).toBeInTheDocument()
  })

  it('se pueden tildar varios técnicos de la lista', async () => {
    render(true)
    await screen.findByDisplayValue('Central sin tono')

    expect(await screen.findByLabelText('Ana Gómez')).toBeInTheDocument()
  })

  it('el teléfono es de sólo lectura y dice cuándo falta', async () => {
    // Se corrige en la ficha del cliente, que es donde vive. Un campo editable
    // acá abriría una segunda copia del teléfono por reclamo.
    clientes = [{ ...CLIENTE, telefono: null }]
    render(true)
    await screen.findByDisplayValue('Central sin tono')

    expect(screen.getByText('sin teléfono cargado')).toBeInTheDocument()
  })
})

// ── Lo que la ficha simple esconde ─────────────────────────────────────────

describe('Lo que el modo simple saca', () => {
  it('no dibuja tareas, actividad, materiales ni notas', async () => {
    render(true)
    await screen.findByDisplayValue('Central sin tono')

    expect(screen.queryByText('Actividad')).not.toBeInTheDocument()
    expect(screen.queryByText(/Notas internas/)).not.toBeInTheDocument()
    expect(screen.queryByText('Tareas')).not.toBeInTheDocument()
    expect(screen.queryByText(/Materiales/)).not.toBeInTheDocument()
  })

  it('el costado no tiene sector, modalidad ni los tres papeles', async () => {
    render(true)
    await screen.findByDisplayValue('Central sin tono')

    expect(screen.queryByLabelText('Sector')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Modalidad')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Recepcionó')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Vendedor')).not.toBeInTheDocument()
  })
})

// ── La cobertura del abono, que NO se saca ─────────────────────────────────

describe('La cobertura del abono', () => {
  it('no aparece para un cliente al que se le factura cada trabajo', async () => {
    render(true)
    await screen.findByDisplayValue('Central sin tono')

    expect(screen.queryByLabelText('Cobertura del abono')).not.toBeInTheDocument()
  })

  it('🔴 SÍ aparece para un cliente con abono, también en modo simple', async () => {
    // Sin esto, el único cliente `mensual` de Lagrace queda sin camino a
    // facturación: `convertir_a_remito()` se niega a convertir un reclamo suyo
    // con la cobertura sin decidir.
    incidencia = { ...INCIDENCIA, cliente_id: 2 }
    clientes = [CLIENTE, CLIENTE_CON_ABONO]
    render(true)
    await screen.findByDisplayValue('Central sin tono')

    expect(await screen.findByLabelText('Cobertura del abono')).toBeInTheDocument()
  })
})

// ── La garantía: el modo completo no cambió ────────────────────────────────

describe('🔑 La ficha completa sigue igual', () => {
  it('mantiene tareas, actividad, notas y el costado entero', async () => {
    // **La promesa que se le hizo al humano**: prender el add-on en una
    // instancia no le toca nada a las otras. Si esto se pone rojo, la promesa
    // se rompió.
    render(false)
    await screen.findByDisplayValue('Central sin tono')

    await waitFor(() => {
      expect(screen.getByText('Actividad')).toBeInTheDocument()
    })
    expect(screen.getByText(/Notas internas/)).toBeInTheDocument()
    expect(screen.getByLabelText('Sector')).toBeInTheDocument()
    expect(screen.getByLabelText('Modalidad')).toBeInTheDocument()
    expect(screen.getByLabelText('Recepcionó')).toBeInTheDocument()
  })

  it('no dibuja el bloque de técnicos del reclamo', async () => {
    // La vía por tarea sigue siendo la del modo completo: las dos formas de
    // trabajar conviven, pero cada ficha muestra la suya.
    render(false)
    await screen.findByDisplayValue('Central sin tono')

    expect(screen.queryByText('Técnicos que fueron')).not.toBeInTheDocument()
  })
})
