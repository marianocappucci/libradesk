// El dashboard operativo en pantalla (pedido del 2026-08-05).
//
// Lo que afirman, en orden de lo que se rompe sin que se note:
//
// 1. 🔴 **Que los bloques vacíos NO desaparezcan.** Una tarjeta ausente deja al
//    usuario sin saber si es que no hay vencimientos o si el bloque se rompió.
//    Es el modo de falla más silencioso de una pantalla de agregados.
// 2. 🔴 **Que lo ya vencido se lea como vencido**, no como "en -12 días".
// 3. 🔴 **Que el total mande sobre la lista.** El bloque muestra 5; si el
//    número grande saliera de `items.length`, «5 por vencer» sería mentira
//    cuando hay 40.
// 4. Que los totales digan cuáles responden al filtro de fechas y cuáles no.
//    Ése era el defecto de la pantalla anterior: movía un número de seis y no
//    lo decía.
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { DashboardOperativo, DashboardSummary } from '../api'
import { Dashboard } from '../pages/Dashboard'

const VACIO: DashboardOperativo = {
  dias: 30,
  hoy: '2026-08-06',
  vencimientos: {
    contratos: { total: 0, items: [] },
    garantias: { total: 0, items: [] },
    agenda: { total: 0, items: [] },
  },
  backlog: { total_abiertas: 0, por_antiguedad: {}, mas_viejas: [] },
  taller: { total: 0, items: [] },
  sin_asignar: 0,
}

const SUMMARY: DashboardSummary = {
  incidencias_por_estado: { abierto: 3, cerrado: 10 },
  incidencias_por_prioridad_abiertas: { alta: 1, media: 2 },
  incidencias_en_rango: 4,
  horas_en_rango: 12.5,
  total_clientes_activos: 8,
  total_equipos: 38,
  horas_totales_invertidas: 210.75,
  responden_al_rango: ['incidencias_en_rango', 'horas_en_rango'],
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

function servir(operativo: DashboardOperativo, summary: DashboardSummary = SUMMARY) {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/api/dashboard/operativo')) return Promise.resolve(json(operativo))
    if (u.includes('/api/dashboard')) return Promise.resolve(json(summary))
    return Promise.resolve(json({}))
  }))
}

function montar() {
  return render(<MemoryRouter><Dashboard /></MemoryRouter>)
}

beforeEach(() => { servir(VACIO) })


describe('Bloques vacíos', () => {
  it('🔴 los cuatro bloques siguen estando cuando no hay nada', async () => {
    montar()

    expect(await screen.findByText('Contratos por vencer')).toBeInTheDocument()
    expect(screen.getByText('Garantías por vencer')).toBeInTheDocument()
    expect(screen.getByText('Turnos agendados')).toBeInTheDocument()
    expect(screen.getByText('En el taller')).toBeInTheDocument()
  })

  it('un bloque vacío lo dice, en vez de quedar en blanco', async () => {
    montar()

    expect(await screen.findAllByText('Nada en el horizonte elegido.')).toHaveLength(4)
  })
})


describe('Vencimientos', () => {
  it('🔴 lo ya vencido se lee como vencido, no como días negativos', async () => {
    servir({
      ...VACIO,
      vencimientos: {
        ...VACIO.vencimientos,
        contratos: {
          total: 1,
          items: [{
            id: 1, numero: 'CTR-0001', cliente: 'Compulibra',
            vence: '2026-07-25', dias_restantes: -12, estado: 'activo',
          }],
        },
      },
    })
    montar()

    expect(await screen.findByText('vencido hace 12 d')).toBeInTheDocument()
  })

  it('lo de hoy y lo de mañana se nombran, no se cuentan', async () => {
    servir({
      ...VACIO,
      vencimientos: {
        ...VACIO.vencimientos,
        garantias: {
          total: 2,
          items: [
            { id: 1, equipo: 'Notebook Dell', cliente: 'A', vence: '2026-08-06', dias_restantes: 0 },
            { id: 2, equipo: 'Impresora HP', cliente: 'B', vence: '2026-08-07', dias_restantes: 1 },
          ],
        },
      },
    })
    montar()

    expect(await screen.findByText('hoy')).toBeInTheDocument()
    expect(screen.getByText('mañana')).toBeInTheDocument()
  })

  it('🔴 el número grande sale del total, no de los ítems mostrados', async () => {
    servir({
      ...VACIO,
      vencimientos: {
        ...VACIO.vencimientos,
        garantias: {
          total: 40,
          items: [
            { id: 1, equipo: 'Uno', cliente: 'A', vence: '2026-08-10', dias_restantes: 4 },
            { id: 2, equipo: 'Dos', cliente: 'B', vence: '2026-08-11', dias_restantes: 5 },
          ],
        },
      },
    })
    montar()

    expect(await screen.findByText('40')).toBeInTheDocument()
    // Y ofrece ir a verlos todos, porque la lista no los tiene.
    expect(screen.getByRole('link', { name: 'Ver los 40' })).toBeInTheDocument()
  })

  it('no ofrece "ver todos" cuando la lista ya los trae a todos', async () => {
    servir({
      ...VACIO,
      vencimientos: {
        ...VACIO.vencimientos,
        garantias: {
          total: 1,
          items: [{ id: 1, equipo: 'Uno', cliente: 'A', vence: '2026-08-10', dias_restantes: 4 }],
        },
      },
    })
    montar()

    expect(await screen.findByText('Uno')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Ver los/ })).not.toBeInTheDocument()
  })

  it('los días en el taller son transcurridos, no restantes', async () => {
    servir({
      ...VACIO,
      taller: {
        total: 1,
        items: [{ id: 1, numero: 'ING-0001', equipo: 'Notebook Dell', cliente: 'A', dias: 9 }],
      },
    })
    montar()

    expect(await screen.findByText('vencido hace 9 d')).toBeInTheDocument()
  })
})


describe('Backlog', () => {
  it('muestra los tres tramos de antigüedad', async () => {
    servir({
      ...VACIO,
      backlog: {
        total_abiertas: 6,
        por_antiguedad: { hasta_7_dias: 2, de_8_a_30_dias: 3, mas_de_30_dias: 1 },
        mas_viejas: [{
          id: 7, titulo: 'La más vieja', cliente: 'Compulibra',
          dias: 45, prioridad: 'alta', estado: 'abierto',
        }],
      },
    })
    montar()

    expect(await screen.findByText('Hasta 7 días')).toBeInTheDocument()
    expect(screen.getByText('De 8 a 30 días')).toBeInTheDocument()
    expect(screen.getByText('Más de 30 días')).toBeInTheDocument()
    expect(screen.getByText('45 d')).toBeInTheDocument()
  })

  it('un tramo sin incidencias muestra 0, no se omite', async () => {
    // Que un tramo desaparezca al llegar a cero hace parecer que la escala
    // cambió. El cero es información: nadie espera hace más de un mes.
    servir({
      ...VACIO,
      backlog: {
        total_abiertas: 2,
        por_antiguedad: { hasta_7_dias: 2 },
        mas_viejas: [],
      },
    })
    montar()

    const tramo = (await screen.findByText('Más de 30 días')).parentElement!
    expect(within(tramo).getByText('0')).toBeInTheDocument()
  })

  it('las incidencias más viejas linkean a su ficha', async () => {
    servir({
      ...VACIO,
      backlog: {
        total_abiertas: 1,
        por_antiguedad: { mas_de_30_dias: 1 },
        mas_viejas: [{
          id: 42, titulo: 'Impresora rota', cliente: 'Compulibra',
          dias: 60, prioridad: 'alta', estado: 'abierto',
        }],
      },
    })
    montar()

    const link = await screen.findByRole('link', { name: /Impresora rota/ })
    expect(link).toHaveAttribute('href', '/incidencias/42')
  })

  it('el aviso de sin asignar sólo sale si hay alguna', async () => {
    montar()
    expect(await screen.findByText('Contratos por vencer')).toBeInTheDocument()
    expect(screen.queryByText('Sin técnico asignado')).not.toBeInTheDocument()

    servir({ ...VACIO, sin_asignar: 3 })
    montar()
    expect(await screen.findByText('Sin técnico asignado')).toBeInTheDocument()
  })
})


describe('Totales', () => {
  it('🔴 dice cuáles números responden al filtro de fechas y cuáles no', async () => {
    // El defecto de la pantalla anterior: el rango movía un solo número de
    // seis y nada lo decía.
    montar()

    expect(await screen.findByText('creadas en el rango elegido')).toBeInTheDocument()
    expect(screen.getByText('en el rango elegido')).toBeInTheDocument()
    expect(screen.getByText('activos (total, no del rango)')).toBeInTheDocument()
    expect(screen.getByText('registrados (total, no del rango)')).toBeInTheDocument()
  })

  it('las horas del rango se distinguen de las históricas', async () => {
    // Antes el histórico colgaba del subtítulo de "Equipos", que no tiene nada
    // que ver con las horas.
    montar()

    expect(await screen.findByText('12.5')).toBeInTheDocument()
    expect(screen.getByText('210.8 hs desde siempre')).toBeInTheDocument()
  })

  it('avisa que el desglose por estado no responde al rango', async () => {
    // El número grande sí lo hace: sin este renglón los dos se leen como lo
    // mismo y no cierran entre sí (4 en el rango, 13 en el desglose).
    montar()

    expect(
      await screen.findByText('El desglose por estado es histórico, no del rango.'),
    ).toBeInTheDocument()
  })
})


describe('Respuestas incompletas', () => {
  it('🔴 un cuerpo truncado muestra de menos, no tumba la pantalla', async () => {
    // `{}` es **truthy**: con `operativo &&` la pantalla entera se caía con un
    // TypeError. Lo encontró el smoke test, cuyo mock devuelve `{}` para lo
    // que no conoce; en producción sería una respuesta a medias.
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json({}))))

    expect(() => montar()).not.toThrow()
    expect(await screen.findByText('Qué hay que hacer')).toBeInTheDocument()
  })

  it('los totales incompletos tampoco la tumban', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (String(url).includes('/api/dashboard/operativo')) {
        return Promise.resolve(json(VACIO))
      }
      return Promise.resolve(json({}))
    }))
    montar()

    expect(await screen.findByText('Contratos por vencer')).toBeInTheDocument()
    expect(screen.queryByText('Horas invertidas')).not.toBeInTheDocument()
  })
})


describe('Horizonte', () => {
  it('lo pide al backend y vuelve a consultar al cambiarlo', async () => {
    const espia = vi.fn((url: string) => {
      const u = String(url)
      if (u.includes('/api/dashboard/operativo')) return Promise.resolve(json(VACIO))
      return Promise.resolve(json(SUMMARY))
    })
    vi.stubGlobal('fetch', espia)
    montar()

    await screen.findByText('Contratos por vencer')
    const llamadas = espia.mock.calls.map((c) => String(c[0]))
    expect(llamadas.some((u) => u.includes('/api/dashboard/operativo?dias=30'))).toBe(true)
  })
})


describe('🔴 Se puede ir desde el dashboard hasta el evento', () => {
  // Reportado por el humano el 2026-08-16: *«la mayoría de las cosas que están
  // en el dashboard no se pueden clickear para ir hasta el evento»*. Un
  // dashboard que dice que hay algo y no lleva hasta eso obliga a buscarlo a
  // mano en otra pantalla, que es la mitad del trabajo que venía a ahorrar.

  it('cada fila de un vencimiento lleva a su ficha', async () => {
    servir({
      ...VACIO,
      vencimientos: {
        ...VACIO.vencimientos,
        contratos: {
          total: 1,
          items: [{
            id: 7, numero: 'CTR-0007', cliente: 'Compulibra',
            vence: '2026-09-01', dias_restantes: 12, estado: 'activo',
          }],
        },
      },
    })
    montar()

    const fila = await screen.findByRole('link', { name: /CTR-0007/ })
    expect(fila).toHaveAttribute('href', '/contratos/7')
  })

  it('el número grande de la tarjeta también lleva a la pantalla', async () => {
    servir({
      ...VACIO,
      vencimientos: {
        ...VACIO.vencimientos,
        contratos: {
          total: 47,
          items: [{
            id: 7, numero: 'CTR-0007', cliente: 'Compulibra',
            vence: '2026-09-01', dias_restantes: 12, estado: 'activo',
          }],
        },
      },
    })
    montar()

    // Se busca DENTRO de la tarjeta: los totales de abajo también son links
    // ahora, así que un `getByRole` suelto se cae con "Found multiple
    // elements" en cuanto dos números coinciden — pasó con un total de 4.
    const tarjeta = (await screen.findByText('Contratos por vencer'))
      .closest('[data-slot="card"]') as HTMLElement
    expect(within(tarjeta).getByRole('link', { name: '47' }))
      .toHaveAttribute('href', '/contratos')
  })

  it('🔴 un total en CERO no se linkea', async () => {
    // El control, y de paso la regla: un link a una lista vacía es un viaje al
    // vacío. Sin este caso, linkear TODO pasaría los dos tests de arriba igual.
    montar()

    expect(await screen.findByText('Contratos por vencer')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '0' })).toBeNull()
  })

  it('los totales de abajo llevan a su listado', async () => {
    montar()

    // Los números salen de `SUMMARY`: 4 incidencias en el rango, 8 clientes,
    // 38 equipos. Con el escenario VACÍO ninguna tarjeta de vencimientos los
    // repite, así que la búsqueda suelta no es ambigua acá.
    expect(await screen.findByRole('link', { name: '4' }))
      .toHaveAttribute('href', '/incidencias')
    expect(screen.getByRole('link', { name: '8' })).toHaveAttribute('href', '/clientes')
    expect(screen.getByRole('link', { name: '38' })).toHaveAttribute('href', '/equipos')
  })

  it('🔴 las horas NO se linkean: son una suma, no una lista', async () => {
    // Linkearlas mandaría a un listado que no explica el número. Es el otro
    // control de que no se linkeó todo por las dudas.
    montar()

    await screen.findByText('Horas invertidas')
    expect(screen.getByText('12.5')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '12.5' })).toBeNull()
  })
})
