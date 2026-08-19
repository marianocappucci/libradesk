// La grilla de tareas del reclamo (2026-08-19) — brecha 4 de Lagrace.
//
// Lo que se afirma acá no es el dibujo sino las tres cosas que, si se rompen,
// no se ven rotas:
//
// 1. **Que editar una celda mande SÓLO ese campo.** El backend usa
//    `exclude_unset`, así que mandar el resto convertiría un "no lo toqué" en
//    un "ponelo en null" — y borraría datos sin que nadie lo pida.
// 2. **Que vaciar una fecha mande `null` y no `""`.** Es el caso de reabrir una
//    tarea cerrada por error, y con `""` el backend lo rechaza.
// 3. **Que cada control tenga nombre accesible.** La grilla es toda inputs sin
//    texto visible al lado; sin `aria-label` un lector de pantalla lee siete
//    campos llamados "textbox".
//
// Se stubea `fetch` y no el cliente `api`: así el `patch` real es el que arma
// el cuerpo, que es la mitad que estos tests vienen a defender.
//
// 🔴 **Se sale del campo con `focusOut`, no con `blur`.** React escucha
// `focusout` —que burbujea— y no `blur`, que no burbujea y por eso nunca llega
// al listener de la raíz. `fireEvent.blur(el)` deja el `onBlur` del componente
// **sin ejecutar**, y lo peor es cómo se manifiesta: los tests que esperan una
// llamada se ponen rojos (ruidoso, se arregla), pero el que espera **cero**
// llamadas pasa en verde sin haber ejercitado nada. Medido acá: con `blur` el
// `fetch` sólo registra los dos GET del montaje; con `focusOut` aparece el
// PATCH. Por eso el test del "no cambió" lleva su control positivo adentro.
import { render, screen, waitFor, within } from '@testing-library/react'
import { fireEvent } from '@testing-library/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TareasDelReclamo } from '@/components/tareas-del-reclamo'

const TAREAS = [
  {
    id: 7, incidencia_id: 3, orden: 1, detalle: 'Diagnóstico en el lugar',
    fecha_inicio: '2026-08-03', fecha_fin: '2026-08-05', estado: 'terminada',
    observacion: 'Llamar antes', item_id: 4, tipo_servicio: 'Hora normal',
  },
  {
    id: 8, incidencia_id: 3, orden: 2, detalle: 'Cambio de placa',
    fecha_inicio: null, fecha_fin: null, estado: 'pendiente',
    observacion: null, item_id: null, tipo_servicio: null,
  },
]

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

function stub() {
  const fn = vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/tareas')) return Promise.resolve(json(TAREAS))
    if (u.includes('/api/servicios')) return Promise.resolve(json([{ id: 4, nombre: 'Hora normal' }]))
    return Promise.resolve(json([]))
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

function llamadas(fn: ReturnType<typeof vi.fn>, metodo: string) {
  return fn.mock.calls.filter((c) => (c[1] as RequestInit | undefined)?.method === metodo)
}

beforeEach(() => { stub() })

describe('la grilla de tareas del reclamo', () => {
  it('muestra una fila por tarea, con su estado y sus fechas', async () => {
    render(<TareasDelReclamo incidenciaId={3} />)

    expect(await screen.findByDisplayValue('Diagnóstico en el lugar')).toBeTruthy()
    expect(screen.getByDisplayValue('Cambio de placa')).toBeTruthy()
    // 🔴 Cada una con SU estado: es el punto de la brecha.
    expect(screen.getByLabelText('Estado de la tarea 1').textContent).toContain('Terminada')
    expect(screen.getByLabelText('Estado de la tarea 2').textContent).toContain('Pendiente')
    expect(screen.getByLabelText('Fecha de inicio de la tarea 1')).toHaveProperty('value', '2026-08-03')
    // La que no tiene fecha se muestra vacía, no con la de otra fila.
    expect(screen.getByLabelText('Fecha de inicio de la tarea 2')).toHaveProperty('value', '')
  })

  it('el tipo de servicio se muestra resuelto, y vacío se dibuja como raya', async () => {
    render(<TareasDelReclamo incidenciaId={3} />)
    const filas = await screen.findAllByRole('row')
    expect(within(filas[1]).getByText('Hora normal')).toBeTruthy()
    expect(within(filas[2]).getByText('—')).toBeTruthy()
  })

  it('editar una celda manda SÓLO ese campo', async () => {
    const fn = stub()
    render(<TareasDelReclamo incidenciaId={3} />)
    const detalle = await screen.findByLabelText('Detalle de la tarea 1')

    fireEvent.change(detalle, { target: { value: 'Diagnóstico y prueba' } })
    fireEvent.focusOut(detalle)

    await waitFor(() => expect(llamadas(fn, 'PATCH').length).toBe(1))
    const [url, opciones] = llamadas(fn, 'PATCH')[0]
    expect(String(url)).toBe('/api/incidencias/3/tareas/7')
    // 🔴 Un solo campo. Mandar el resto convertiría "no lo toqué" en "null".
    expect(JSON.parse(String((opciones as RequestInit).body))).toEqual({
      detalle: 'Diagnóstico y prueba',
    })
  })

  it('vaciar una fecha manda null, no cadena vacía', async () => {
    const fn = stub()
    render(<TareasDelReclamo incidenciaId={3} />)
    const fin = await screen.findByLabelText('Fecha de fin de la tarea 1')

    fireEvent.change(fin, { target: { value: '' } })
    fireEvent.focusOut(fin)

    await waitFor(() => expect(llamadas(fn, 'PATCH').length).toBe(1))
    const body = JSON.parse(String((llamadas(fn, 'PATCH')[0][1] as RequestInit).body))
    expect(body).toEqual({ fecha_fin: null })
  })

  it('no manda nada si el valor no cambió', async () => {
    const fn = stub()
    render(<TareasDelReclamo incidenciaId={3} />)
    const detalle = await screen.findByLabelText('Detalle de la tarea 1')

    fireEvent.change(detalle, { target: { value: 'Diagnóstico en el lugar' } })
    fireEvent.focusOut(detalle)

    await new Promise((r) => setTimeout(r, 20))
    expect(llamadas(fn, 'PATCH').length).toBe(0)

    // 🔴 Control positivo, en el mismo test: sin esto un cero no prueba nada
    // --con el evento equivocado también da cero, y el test pasa sin haber
    // ejercitado el componente--.
    fireEvent.change(detalle, { target: { value: 'Otra cosa' } })
    fireEvent.focusOut(detalle)
    await waitFor(() => expect(llamadas(fn, 'PATCH').length).toBe(1))
  })

  it('agregar manda el detalle y el tipo elegido', async () => {
    const fn = stub()
    render(<TareasDelReclamo incidenciaId={3} />)
    const nueva = await screen.findByLabelText('Nueva tarea')

    fireEvent.change(nueva, { target: { value: 'Pedido de repuesto' } })
    fireEvent.click(screen.getByRole('button', { name: /agregar/i }))

    await waitFor(() => expect(llamadas(fn, 'POST').length).toBe(1))
    const [url, opciones] = llamadas(fn, 'POST')[0]
    expect(String(url)).toBe('/api/incidencias/3/tareas')
    const body = JSON.parse(String((opciones as RequestInit).body))
    expect(body.detalle).toBe('Pedido de repuesto')
    // `orden` NO se manda: lo pone el backend, para que no haya dos en la
    // misma posición.
    expect('orden' in body).toBe(false)
  })

  it('cada control de la grilla tiene nombre accesible', async () => {
    render(<TareasDelReclamo incidenciaId={3} />)
    await screen.findByDisplayValue('Diagnóstico en el lugar')

    for (const nombre of [
      'Detalle de la tarea 1', 'Fecha de inicio de la tarea 1',
      'Fecha de fin de la tarea 1', 'Estado de la tarea 1',
      'Observación de la tarea 1', 'Borrar la tarea 1',
    ]) {
      expect(screen.getByLabelText(nombre)).toBeTruthy()
    }
  })

  it('sin tareas lo dice, en vez de dibujar una tabla vacía', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json([]))))
    render(<TareasDelReclamo incidenciaId={3} />)
    expect(await screen.findByText(/todavía no hay tareas/i)).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
  })
})
