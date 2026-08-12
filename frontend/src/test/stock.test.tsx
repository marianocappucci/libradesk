// La pantalla de stock. Se escribió al revisar cómo se veía: no hay navegador
// disponible contra este entorno —el panel corre en Windows y el dev server en
// WSL, y no se alcanzan—, así que la única forma de mirar la pantalla es
// renderizarla acá.
//
// El primer render ya destapó un defecto real (el Select arrancaba no
// controlado), así que el test que más vale de este archivo es el último: falla
// ante **cualquier** warning de React, que es como se ve ese tipo de bug.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Stock } from '../pages/Stock'

const CONSUMIBLES = [
  { id: 1, nombre: 'Plug RJ45', activo: true, stock_minimo: 50, costo: 120 },
  { id: 2, nombre: 'Cable UTP Cat 6 (m)', activo: true, stock_minimo: 100, costo: 900 },
]
const DEPOSITOS = [
  { id: 1, nombre: 'Depósito central', activo: true, descripcion: '', es_default: true },
  { id: 2, nombre: 'Kangoo Norte', activo: true, descripcion: '', es_default: false },
]

/** Stock por depósito del item 1. Se cambia por test. */
let stockDelItem = [
  { ...DEPOSITOS[0], stock: 149 },
  { ...DEPOSITOS[1], stock: 34 },
]

beforeEach(() => {
  stockDelItem = [{ ...DEPOSITOS[0], stock: 149 }, { ...DEPOSITOS[1], stock: 34 }]
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const u = String(url)
    const body = u.includes('/stock') ? stockDelItem
      : u.includes('/depositos-stock') ? DEPOSITOS
      : u.includes('/consumibles') ? CONSUMIBLES
      : []
    return new Response(JSON.stringify(body), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }))
})

afterEach(() => vi.unstubAllGlobals())

async function montarYElegir(nombre = 'Plug RJ45') {
  render(<MemoryRouter><Stock /></MemoryRouter>)
  await waitFor(() => expect(screen.getByText(/Stock de consumibles/)).toBeTruthy())
  await userEvent.click(screen.getByRole('combobox'))
  await userEvent.click(await screen.findByText(nombre))
  await waitFor(() => expect(screen.getByText('Kangoo Norte')).toBeTruthy())
}

describe('La pantalla de stock', () => {
  it('sin consumibles cargados dice qué hacer, no queda en blanco', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([]), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })))

    render(<MemoryRouter><Stock /></MemoryRouter>)

    expect(await screen.findByText(/Todavía no hay consumibles/)).toBeTruthy()
  })

  it('muestra cuánto hay en cada depósito y el total', async () => {
    await montarYElegir()

    expect(screen.getByText('Depósito central')).toBeTruthy()
    expect(screen.getByText('149')).toBeTruthy()
    expect(screen.getByText('34')).toBeTruthy()
    // 149 + 34: el total es la suma de los depósitos, no un dato aparte.
    expect(screen.getByText('183')).toBeTruthy()
  })

  it('🔴 avisa cuando el total está por debajo del mínimo', async () => {
    // El mínimo del Plug es 50 y el total baja a 12.
    stockDelItem = [{ ...DEPOSITOS[0], stock: 10 }, { ...DEPOSITOS[1], stock: 2 }]

    await montarYElegir()

    expect(screen.getByText(/por debajo del mínimo/)).toBeTruthy()
  })

  it('el mínimo se compara contra el TOTAL, no contra cada depósito', async () => {
    // 5 en la camioneta y 200 en el central no es faltante: es logística.
    stockDelItem = [{ ...DEPOSITOS[0], stock: 200 }, { ...DEPOSITOS[1], stock: 5 }]

    await montarYElegir()

    expect(screen.queryByText(/por debajo del mínimo/)).toBeNull()
  })

  it('🔴 no deja ningún warning en consola', async () => {
    // Este es el que importa. El Select arrancaba con `value={undefined}` —no
    // controlado— y pasaba a controlado al elegir un consumible; se avisa por
    // consola y nada lo hacía fallar. Se vio recién al renderizar la pantalla.
    //
    // ⚠️ Escucha `warn` **y** `error`: la primera versión de este test espiaba
    // sólo `console.error` y pasaba en verde **con el defecto presente**,
    // porque el aviso de Radix sale por `console.warn`. Un test que no puede
    // fallar es peor que ninguno.
    const avisos: string[] = []
    const spies = (['warn', 'error'] as const).map((nivel) =>
      vi.spyOn(console, nivel).mockImplementation((...args: unknown[]) => {
        avisos.push(String(args[0]))
      }),
    )

    await montarYElegir()

    spies.forEach((s) => s.mockRestore())
    expect(avisos).toEqual([])
  })
})
