// Los técnicos de una tarea (2026-08-19) — brechas 3 y 5 de Lagrace.
//
// Lo que se afirma acá son las tres cosas que, si se rompen, no se ven rotas:
//
// 1. 🔴 **Que un tramo sin cargar se dibuje como raya y no como `0`.** Un
//    técnico tildado al que todavía nadie le puso las horas no trabajó cero
//    horas: no se sabe cuántas. Un `0` en esa celda es el número que alguien
//    mira antes de facturar.
// 2. 🔴 **Que no haya campo para editar el importe.** Se muestra derivado; un
//    input ahí sería una segunda fuente de verdad para la plata, al lado de los
//    cargos de mano de obra.
// 3. **Que editar un tramo mande sólo ese campo**, y que vaciarlo mande `null`.
//
// Se sale de los campos con `focusOut` y no con `blur`: React escucha
// `focusout`, y con `blur` el `onBlur` del componente no corre --el test que
// espera cero llamadas pasaría en verde sin ejercitar nada--.
import { render, screen, waitFor, within } from '@testing-library/react'
import { fireEvent } from '@testing-library/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TecnicosDeTarea } from '@/components/tecnicos-de-tarea'

const ASIGNADOS = [
  {
    id: 11, tarea_id: 5, tecnico_id: 2, tecnico: 'Oteiza',
    desde: '2026-08-19T08:00:00', hasta: '2026-08-19T11:30:00',
    horas: 3.5, importe: 73850,
  },
  {
    id: 12, tarea_id: 5, tecnico_id: 3, tecnico: 'Cantone',
    desde: null, hasta: null, horas: null, importe: null,
  },
]

const TECNICOS = [
  { id: 2, nombre: 'Oteiza' }, { id: 3, nombre: 'Cantone' },
  { id: 4, nombre: 'Zeballos' },
]

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

function stub() {
  const fn = vi.fn(() => Promise.resolve(json({ ok: true })))
  vi.stubGlobal('fetch', fn)
  return fn
}

function pintar(props: Partial<Parameters<typeof TecnicosDeTarea>[0]> = {}) {
  return render(
    <TecnicosDeTarea
      tareaId={5} incidenciaId={3} orden={1}
      asignados={ASIGNADOS} horasTotal={3.5} importeTotal={73850}
      tecnicos={TECNICOS} onCambio={() => {}}
      {...props}
    />,
  )
}

function llamadas(fn: ReturnType<typeof vi.fn>, metodo: string) {
  return fn.mock.calls.filter((c) => (c[1] as RequestInit | undefined)?.method === metodo)
}

beforeEach(() => { stub() })

describe('los técnicos de una tarea', () => {
  it('el botón resume cuántos son y cuántas horas llevan', () => {
    pintar()
    expect(screen.getByLabelText('Técnicos de la tarea 1').textContent).toContain('2 · 3.5 h')
  })

  it('sin nadie asignado el botón invita a asignar', () => {
    pintar({ asignados: [], horasTotal: null, importeTotal: null })
    expect(screen.getByLabelText('Técnicos de la tarea 1').textContent).toContain('Asignar')
  })

  it('🔴 un tramo sin cargar se dibuja como raya, no como cero', async () => {
    pintar()
    fireEvent.click(screen.getByLabelText('Técnicos de la tarea 1'))

    const filas = await screen.findAllByRole('row')
    const cantone = filas.find((f) => f.textContent?.includes('Cantone'))!
    // Ni "0" ni "$ 0": no se sabe cuántas horas trabajó.
    expect(within(cantone).getAllByText('—').length).toBe(2)
    expect(cantone.textContent).not.toContain('$ 0')

    // Y el de Oteiza sí muestra sus números.
    const oteiza = filas.find((f) => f.textContent?.includes('Oteiza'))!
    expect(oteiza.textContent).toContain('3.5')
  })

  it('🔴 el importe no tiene campo para editarlo', async () => {
    pintar()
    fireEvent.click(screen.getByLabelText('Técnicos de la tarea 1'))
    await screen.findByRole('dialog')

    // Los UNICOS inputs del dialogo son los dos tramos por fila: cuatro para
    // dos tecnicos. Si apareciera uno mas, seria el del importe.
    //
    // Se cuentan por el DOM y no con `getAllByRole('textbox')`: un
    // `datetime-local` **no tiene ese rol**, asi que esa consulta devolvia cero
    // y el test fallaba por el arnes y no por el componente.
    const dialogo = screen.getByRole('dialog')
    const inputs = dialogo.querySelectorAll('input')
    expect(inputs.length).toBe(4)
    for (const i of inputs) {
      expect(i.type).toBe('datetime-local')
    }
    expect(screen.queryByLabelText(/importe/i)).toBeNull()
    // Y el importe esta, como texto: no es que falte la columna.
    expect(dialogo.textContent).toContain('73.850')
  })

  it('editar un tramo manda sólo ese campo', async () => {
    const fn = stub()
    pintar()
    fireEvent.click(screen.getByLabelText('Técnicos de la tarea 1'))
    const desde = await screen.findByLabelText('Desde, de Oteiza')

    fireEvent.change(desde, { target: { value: '2026-08-19T09:00' } })
    fireEvent.focusOut(desde)

    await waitFor(() => expect(llamadas(fn, 'PATCH').length).toBe(1))
    const [url, opciones] = llamadas(fn, 'PATCH')[0]
    expect(String(url)).toBe('/api/incidencias/3/tareas/5/tecnicos/11')
    expect(JSON.parse(String((opciones as RequestInit).body))).toEqual({
      desde: '2026-08-19T09:00',
    })
  })

  it('vaciar un tramo manda null', async () => {
    const fn = stub()
    pintar()
    fireEvent.click(screen.getByLabelText('Técnicos de la tarea 1'))
    const hasta = await screen.findByLabelText('Hasta, de Oteiza')

    fireEvent.change(hasta, { target: { value: '' } })
    fireEvent.focusOut(hasta)

    await waitFor(() => expect(llamadas(fn, 'PATCH').length).toBe(1))
    expect(JSON.parse(String((llamadas(fn, 'PATCH')[0][1] as RequestInit).body)))
      .toEqual({ hasta: null })
  })

  it('sólo ofrece asignar a los que no están', async () => {
    pintar()
    fireEvent.click(screen.getByLabelText('Técnicos de la tarea 1'))
    const disparador = await screen.findByLabelText('Asignar técnico')
    fireEvent.click(disparador)

    // Oteiza y Cantone ya están; queda Zeballos.
    expect(await screen.findByText('Zeballos')).toBeTruthy()
    expect(screen.queryAllByRole('option', { name: 'Oteiza' })).toHaveLength(0)
  })

  it('cada control del diálogo tiene nombre accesible', async () => {
    pintar()
    fireEvent.click(screen.getByLabelText('Técnicos de la tarea 1'))
    await screen.findByRole('dialog')

    for (const nombre of [
      'Desde, de Oteiza', 'Hasta, de Oteiza',
      'Desde, de Cantone', 'Hasta, de Cantone',
      'Quitar a Oteiza de la tarea', 'Asignar técnico',
    ]) {
      expect(screen.getByLabelText(nombre)).toBeTruthy()
    }
  })
})
