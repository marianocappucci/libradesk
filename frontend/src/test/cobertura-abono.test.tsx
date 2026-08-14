// La cobertura del abono, en la pantalla donde se decide.
//
// El backend se niega a generar el remito de un cliente con abono hasta que
// alguien diga qué parte cubre. Esta pantalla es donde se dice, y lo que se
// rompe acá es de las dos formas caras:
//
// - **Preguntarle a quien no corresponde**: un cliente `por_servicio` no tiene
//   abono, y ofrecerle la decisión invita a marcar "cubierto" un trabajo que
//   había que cobrar.
// - **Perder la decisión al guardar otra cosa**: el PUT manda el objeto entero,
//   así que un campo que la pantalla no reenvía vuelve a null. Es exactamente
//   como este producto perdió el `nro_cds` una vez, y acá el síntoma sería un
//   remito que se frena pidiendo algo que ya se había elegido.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { IncidenciaDetalle } from '../pages/IncidenciaDetalle'

const render = (ui: ReactElement) =>
  renderRTL(
    <MemoryRouter initialEntries={['/incidencias/1']}>
      <Routes>
        <Route path="/incidencias/:id" element={ui} />
      </Routes>
    </MemoryRouter>,
  )

const CLIENTE_BASE = {
  id: 1, nombre: 'Medici Neumatec', empresa: 'NEUMYSER SRL', email: null,
  telefono: null, ciudad: 'Chivilcoy', cuit: '30-11111111-7', domicilio: null,
  observaciones: null, activo: true, fecha_creacion: null,
}

const BASE = {
  id: 1, cliente_id: 1, equipo_id: null, activo_id: null,
  tecnico_id: null, recepcionista_id: null, vendedor_id: null,
  modalidad: null, sector_id: null, categoria_id: null,
  fecha_programada: null, duracion_minutos: null, equipo_trabajo_id: null,
  titulo: 'Central sin tono', descripcion: null,
  nro_cds: null, reclamante: null,
  estado: 'cerrado', prioridad: 'media',
  horas_invertidas: 5, notas: null, resolucion: null,
  estado_facturacion: null,
  cobertura_abono: null, abono_horas_cubiertas: null,
  abono_materiales_incluidos: null,
  remito_id: null, activo: true,
  fecha_creacion: '2026-08-14T10:00:00', fecha_cierre: '2026-08-14T18:00:00',
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

/** Los cuerpos de cada PUT, que es donde se ve qué se guardó de verdad. */
let puts: Record<string, unknown>[]

function montar(incidencia: Record<string, unknown>, tipoFacturacion = 'mensual') {
  puts = []
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    const metodo = opciones?.method ?? 'GET'

    if (metodo === 'PUT' && u.includes('/api/incidencias/1')) {
      const cuerpo = JSON.parse(String(opciones?.body)) as Record<string, unknown>
      puts.push(cuerpo)
      // Devuelve lo guardado, como el backend: si devolviera el objeto viejo,
      // la pantalla se pisaría a sí misma y el test mediría otra cosa.
      return Promise.resolve(json({ ...incidencia, ...cuerpo }))
    }
    if (u.includes('/api/incidencias/1/actividades')) return Promise.resolve(json([]))
    if (u.includes('/api/incidencias/1/estados')) return Promise.resolve(json([]))
    if (u.includes('/api/incidencias/1/movimientos')) return Promise.resolve(json([]))
    if (u.includes('/api/incidencias/1')) return Promise.resolve(json(incidencia))
    if (u.includes('/api/clientes')) {
      return Promise.resolve(json([{ ...CLIENTE_BASE, tipo_facturacion: tipoFacturacion }]))
    }
    return Promise.resolve(json([]))
  }))
}

async function elegir(nombre: RegExp) {
  await userEvent.click(screen.getByRole('combobox', { name: /Cobertura del abono/i }))
  const lista = await screen.findByRole('listbox')
  await userEvent.click(within(lista).getByRole('option', { name: nombre }))
}

beforeEach(() => { puts = [] })

describe('cobertura del abono', () => {
  it('a un cliente con abono se le pregunta qué parte cubre', async () => {
    montar(BASE)
    render(<IncidenciaDetalle />)
    await screen.findByDisplayValue('Central sin tono')

    expect(screen.getByRole('combobox', { name: /Cobertura del abono/i })).toBeInTheDocument()
  })

  it('a un cliente por servicio no, porque no tiene abono', async () => {
    montar(BASE, 'por_servicio')
    render(<IncidenciaDetalle />)
    await screen.findByDisplayValue('Central sin tono')

    expect(screen.queryByRole('combobox', { name: /Cobertura del abono/i })).toBeNull()
  })

  it('elegir parcial deja los materiales FUERA del abono por defecto', async () => {
    // El default seguro: si el abono sí los cubre se destilda y no se cobran.
    // Al revés, un default en `true` regalaría repuestos por omisión.
    montar(BASE)
    render(<IncidenciaDetalle />)
    await screen.findByDisplayValue('Central sin tono')

    await elegir(/Parcial/i)

    await waitFor(() => expect(puts).toHaveLength(1))
    expect(puts[0].cobertura_abono).toBe('parcial')
    expect(puts[0].abono_materiales_incluidos).toBe(false)
  })

  it('volver a total limpia las horas y los materiales', async () => {
    montar({
      ...BASE, cobertura_abono: 'parcial', abono_horas_cubiertas: 2,
      abono_materiales_incluidos: true,
    })
    render(<IncidenciaDetalle />)
    await screen.findByDisplayValue('Central sin tono')

    await elegir(/Todo dentro del abono/i)

    await waitFor(() => expect(puts).toHaveLength(1))
    expect(puts[0].cobertura_abono).toBe('total')
    expect(puts[0].abono_horas_cubiertas).toBeNull()
    expect(puts[0].abono_materiales_incluidos).toBeNull()
  })

  it('con parcial se ve cuántas horas se terminan facturando', async () => {
    montar({
      ...BASE, horas_invertidas: 5, cobertura_abono: 'parcial',
      abono_horas_cubiertas: 2, abono_materiales_incluidos: false,
    })
    render(<IncidenciaDetalle />)
    await screen.findByDisplayValue('Central sin tono')

    expect(screen.getByText(/Se facturan 3 de 5 h/i)).toBeInTheDocument()
  })

  it('guardar otro campo NO borra la cobertura', async () => {
    // La regresión cara: el PUT manda el objeto entero, así que si la pantalla
    // no reenvía estos tres campos, tocar cualquier cosa deja el reclamo sin
    // decisión y el remito vuelve a frenarse.
    montar({
      ...BASE, cobertura_abono: 'parcial', abono_horas_cubiertas: 2,
      abono_materiales_incluidos: false,
    })
    render(<IncidenciaDetalle />)
    await screen.findByDisplayValue('Central sin tono')

    await userEvent.type(screen.getByLabelText('Reclamante'), 'Facundo')
    await userEvent.tab()

    await waitFor(() => expect(puts).toHaveLength(1))
    expect(puts[0].reclamante).toBe('Facundo')
    expect(puts[0].cobertura_abono).toBe('parcial')
    expect(puts[0].abono_horas_cubiertas).toBe(2)
    expect(puts[0].abono_materiales_incluidos).toBe(false)
  })
})
