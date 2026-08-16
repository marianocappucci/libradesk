// Que una visita de mantenimiento se reconozca en la bandeja (2026-08-16).
//
// 🔴 **Este test existe por el defecto que lo precedió.** La visita **es** una
// incidencia —para heredar agenda, hoja de ruta, cuadrilla y cierre— y el
// sentido de esa decisión es que aparezca en la misma bandeja que los reclamos,
// **distinguible**. Sin la marca, la mitad de la decisión no se cumple: quien
// mira la lista no sabe si llamó el cliente o si toca por contrato.
//
// El backend guardaba el dato desde la revisión `0027`, lo devolvía en
// `_to_dict()`, y el `response_model` de FastAPI lo descartaba en silencio. La
// suite entera pasaba. Lo destapó ejercitar el circuito contra dev.
//
// La lección: un campo nuevo no está terminado hasta que un test lo lee **por
// donde lo lee la pantalla**. Éste lo lee ahí.
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Incidencias } from '../pages/Incidencias'

const CLIENTE = {
  id: 1, nombre: 'Medici Neumatec', empresa: null, email: null, telefono: null,
  ciudad: null, cuit: null, domicilio: null, observaciones: null,
  tipo_facturacion: 'mensual', activo: true, fecha_creacion: null,
}

const BASE = {
  cliente_id: 1, equipo_id: null, activo_id: null,
  tecnico_id: null, recepcionista_id: null, vendedor_id: null,
  modalidad: null, sector_id: null, categoria_id: null,
  descripcion: null, estado: 'abierto', prioridad: 'media',
  horas_invertidas: null, notas: null, resolucion: null,
  estado_facturacion: null, activo: true,
  fecha_creacion: '2026-09-01T10:00:00', fecha_cierre: null,
  cobertura_abono: null, abono_horas_cubiertas: null,
  abono_materiales_incluidos: null, remito_id: null,
  contrato_id: null, periodo_visita: null, es_visita_mantenimiento: false,
}

// Los dos juntos son el punto: con sólo la visita, una marca cableada siempre
// en `true` pasaría el test igual.
const RECLAMO = { ...BASE, id: 1, titulo: 'No hay tono en los internos' }
const VISITA = {
  ...BASE, id: 2, titulo: 'Mantenimiento preventivo — septiembre 2026',
  contrato_id: 7, periodo_visita: '2026-09-01', es_visita_mantenimiento: true,
  cobertura_abono: 'total',
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: unknown) => {
    const u = String(url)
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    if (u.includes('/api/incidencias')) return Promise.resolve(json([RECLAMO, VISITA]))
    return Promise.resolve(json([]))
  }))
})

const montar = () => render(
  <MemoryRouter initialEntries={['/incidencias']}>
    <Routes><Route path="/incidencias" element={<Incidencias />} /></Routes>
  </MemoryRouter>,
)

const filaDe = async (texto: string | RegExp) => {
  const celda = await screen.findByText(texto)
  const fila = celda.closest('tr')
  if (!fila) throw new Error(`sin fila para ${texto}`)
  return fila
}

describe('la visita de mantenimiento en la bandeja', () => {
  it('🔴 sale marcada como preventivo', async () => {
    montar()
    const fila = await filaDe(/Mantenimiento preventivo/)
    expect(within(fila).getByText('Preventivo')).toBeInTheDocument()
  })

  it('🔴 y un reclamo común NO', async () => {
    montar()
    const fila = await filaDe('No hay tono en los internos')
    expect(within(fila).queryByText('Preventivo')).toBeNull()
  })
})
