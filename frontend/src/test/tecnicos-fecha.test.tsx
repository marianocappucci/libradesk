// La fecha de cada técnico en el reclamo (2026-09-09).
//
// Pedido del humano: *"en los técnicos que fueron está bien que se abra para
// poner de qué hora a qué hora pero falta poder poner la fecha también"* — y,
// preguntado si era una del reclamo o una por técnico: **"la fecha en cada
// uno"**.
//
// 🔑 **Y ése es el test que importa.** Un reclamo puede trabajarse en varios
// días y cada técnico ir el suyo: uno el martes y otro el jueves. Con una fecha
// única para todo el reclamo, el segundo quedaría fechado mal — y las horas son
// la base de lo que se cobra.
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TecnicosDelReclamo } from '../components/tecnicos-del-reclamo'

const ANA = {
  id: 1, nombre: 'Ana Gómez', activo: true, es_tecnico: true,
  es_recepcionista: false, es_vendedor: false, es_responsable: false,
  roles: ['tecnico'],
}
const BETO = { ...ANA, id: 2, nombre: 'Beto Ruiz' }

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

/** Las asignaciones que devuelve el backend. Se muta por test. */
let asignaciones: Record<string, unknown>[] = []
/** Lo que se le mandó al backend, para afirmar sobre el payload. */
let patches: { url: string; cuerpo: Record<string, unknown> }[] = []

beforeEach(() => {
  asignaciones = []
  patches = []
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    const metodo = opciones?.method ?? 'GET'
    if (metodo === 'PATCH') {
      const cuerpo = JSON.parse(String(opciones?.body ?? '{}'))
      patches.push({ url: u, cuerpo })
      const id = Number(u.split('/').pop())
      const previa = asignaciones.find((a) => a.id === id) ?? {}
      return Promise.resolve(json({ ...previa, ...cuerpo, horas: 4 }))
    }
    if (u.includes('/tecnicos')) return Promise.resolve(json(asignaciones))
    return Promise.resolve(json([]))
  }))
})

const montar = (dia = '2026-09-08T10:00:00') =>
  render(
    <TecnicosDelReclamo incidenciaId={7} dia={dia} tecnicos={[ANA, BETO] as never} />,
  )

describe('La fecha de cada técnico', () => {
  it('hay un campo de fecha por técnico tildado', async () => {
    asignaciones = [{
      id: 10, incidencia_id: 7, tecnico_id: 1, tecnico: 'Ana Gómez',
      desde: null, hasta: null, horas: null,
    }]
    montar()

    expect(await screen.findByLabelText('Fecha de Ana Gómez')).toBeInTheDocument()
  })

  it('🔑 cada técnico muestra SU fecha, no una del reclamo', async () => {
    // El caso que motivó el pedido: dos técnicos, dos días distintos.
    asignaciones = [
      {
        id: 10, incidencia_id: 7, tecnico_id: 1, tecnico: 'Ana Gómez',
        desde: '2026-09-08T08:00:00', hasta: '2026-09-08T12:00:00', horas: 4,
      },
      {
        id: 11, incidencia_id: 7, tecnico_id: 2, tecnico: 'Beto Ruiz',
        desde: '2026-09-10T14:00:00', hasta: '2026-09-10T16:00:00', horas: 2,
      },
    ]
    montar()

    expect(await screen.findByLabelText('Fecha de Ana Gómez')).toHaveValue('2026-09-08')
    expect(screen.getByLabelText('Fecha de Beto Ruiz')).toHaveValue('2026-09-10')
  })

  it('sin nada cargado cae al día del reclamo, no a hoy', async () => {
    // 🔴 Las horas se cargan **al día siguiente**, así que `new Date()` las
    // fecharía un día después de cuando se trabajó.
    asignaciones = [{
      id: 10, incidencia_id: 7, tecnico_id: 1, tecnico: 'Ana Gómez',
      desde: null, hasta: null, horas: null,
    }]
    montar('2026-09-08T10:00:00')

    expect(await screen.findByLabelText('Fecha de Ana Gómez')).toHaveValue('2026-09-08')
  })

  it('🔑 cambiar la fecha mueve los dos extremos y conserva las horas', async () => {
    // Es lo que espera quien se dio cuenta de que cargó el día equivocado: se
    // corrige la fecha y las horas siguen siendo las del CDS.
    asignaciones = [{
      id: 10, incidencia_id: 7, tecnico_id: 1, tecnico: 'Ana Gómez',
      desde: '2026-09-08T08:00:00', hasta: '2026-09-08T12:00:00', horas: 4,
    }]
    montar()

    // `fireEvent.change` y no `user.type`: en un `<input type="date">` tipear
    // carácter por carácter produce valores intermedios inválidos, y el
    // navegador entrega la fecha **completa** de una cuando se elige del
    // calendario. Esto reproduce eso.
    const fecha = await screen.findByLabelText('Fecha de Ana Gómez')
    fireEvent.change(fecha, { target: { value: '2026-09-11' } })

    await waitFor(() => expect(patches.length).toBeGreaterThan(0))
    const ultimo = patches[patches.length - 1].cuerpo
    expect(ultimo.desde).toBe('2026-09-11T08:00:00')
    expect(ultimo.hasta).toBe('2026-09-11T12:00:00')
  })

  it('cambiar la hora usa la fecha de ESA asignación, no la del reclamo', async () => {
    // 🔴 El defecto que esto evita: con la fecha del reclamo, corregirle la hora
    // a un técnico que fue otro día le movería el tramo a la fecha equivocada.
    const user = userEvent.setup()
    asignaciones = [{
      id: 11, incidencia_id: 7, tecnico_id: 2, tecnico: 'Beto Ruiz',
      desde: '2026-09-10T14:00:00', hasta: '2026-09-10T16:00:00', horas: 2,
    }]
    montar('2026-09-08T10:00:00')

    const hora = await screen.findByLabelText('Hora de inicio de Beto Ruiz')
    await user.clear(hora)
    await user.type(hora, '13:30')
    await user.tab()

    await waitFor(() => expect(patches.length).toBeGreaterThan(0))
    expect(patches[patches.length - 1].cuerpo.desde).toBe('2026-09-10T13:30:00')
  })

  it('un técnico sin tildar no muestra ni fecha ni horas', async () => {
    // Antes de tildar son tres campos vacíos por cada técnico del catálogo, y
    // la lista de Lagrace tiene 14.
    asignaciones = []
    montar()

    await screen.findByLabelText('Ana Gómez')
    expect(screen.queryByLabelText('Fecha de Ana Gómez')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Hora de inicio de Ana Gómez')).not.toBeInTheDocument()
  })
})
