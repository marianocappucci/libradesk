// La pantalla de stock con dos sucursales.
//
// Lo que se prueba acá es lo que distingue "filtrar por sucursal" de "esconder
// la mitad del sistema": **la tabla se recorta a la sucursal activa, pero el
// destino de una transferencia NO**. Si el selector de destino se filtrara, el
// depósito al que se quiere mandar la mercadería sería justamente el único que
// no aparece, y mover stock entre sucursales —que es la razón por la que el
// módulo existe— quedaría imposible desde la pantalla.
//
// El escenario está desbalanceado a propósito (149 en Chivilcoy, 3 en Mercedes):
// con la misma cantidad de los dos lados, una implementación que no filtra nada
// daría los mismos números y estos tests pasarían igual.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Stock } from '../pages/Stock'
import { SucursalProvider } from '../components/sucursal'

const SUCURSALES = [
  { id: 1, nombre: 'Chivilcoy', codigo: 'CHI', direccion: '' },
  { id: 2, nombre: 'Mercedes', codigo: 'MER', direccion: '' },
]
const CONSUMIBLES = [
  { id: 1, nombre: 'Plug RJ45', activo: true, stock_minimo: 50, costo: 120 },
]
const DEPOSITOS = [
  { id: 1, nombre: 'Central Chivilcoy', activo: true, descripcion: '',
    es_default: true, sucursal_id: 1, sucursal: 'Chivilcoy' },
  { id: 2, nombre: 'Kangoo Norte', activo: true, descripcion: '',
    es_default: false, sucursal_id: 1, sucursal: 'Chivilcoy' },
  { id: 3, nombre: 'Central Mercedes', activo: true, descripcion: '',
    es_default: false, sucursal_id: 2, sucursal: 'Mercedes' },
]
const STOCK = [
  { ...DEPOSITOS[0], stock: 149 },
  { ...DEPOSITOS[1], stock: 34 },
  { ...DEPOSITOS[2], stock: 3 },
]

/** Las URLs que la pantalla pidió, para poder afirmar sobre el filtrado. */
let pedidos: string[] = []

beforeEach(() => {
  pedidos = []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const u = String(url)
    pedidos.push(u)
    const body = u.includes('/sucursales') ? SUCURSALES
      : u.includes('/stock') ? STOCK
      : u.includes('/depositos-stock') ? DEPOSITOS
      : u.includes('/consumibles') ? CONSUMIBLES
      : []
    return new Response(JSON.stringify(body), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }))
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

/** Monta la pantalla con una sucursal ya elegida y el Plug seleccionado. */
async function montarEn(sucursalId: number | null) {
  // La sucursal activa se guarda en `localStorage` y no en la sesión: es una
  // decisión del puesto de trabajo. Sembrarla acá es lo mismo que hace el
  // usuario al elegirla en la barra.
  if (sucursalId !== null) {
    localStorage.setItem('libradesk.sucursal_activa', String(sucursalId))
  }
  render(
    <MemoryRouter><SucursalProvider><Stock /></SucursalProvider></MemoryRouter>,
  )
  await waitFor(() => expect(screen.getByText(/Stock de consumibles/)).toBeTruthy())
  await userEvent.click(screen.getByRole('combobox', { name: 'Consumible' }))
  // Por ROL y no por texto: desde que la pantalla entra mostrando el listado
  // (2026-08-15), cada nombre aparece dos veces —en la fila y en la opción del
  // desplegable— y un `findByText` suelto se cae con "Found multiple elements".
  await userEvent.click(await screen.findByRole('option', { name: 'Plug RJ45' }))
  await waitFor(() => expect(screen.getByText('Central Chivilcoy')).toBeTruthy())
}

describe('Stock con dos sucursales', () => {
  it('la tabla muestra sólo los depósitos de la sucursal activa', async () => {
    await montarEn(1)

    expect(screen.getByText('Central Chivilcoy')).toBeTruthy()
    expect(screen.getByText('Kangoo Norte')).toBeTruthy()
    // El de Mercedes no está en la tabla. Se busca por el texto de la celda:
    // aparecer dentro de un `<select>` cerrado no cuenta como estar en la tabla.
    expect(screen.queryByRole('cell', { name: /Central Mercedes/ })).toBeNull()
  })

  it('el total es el de la sucursal, y lo dice', async () => {
    await montarEn(1)

    // 149 + 34, sin los 3 de Mercedes. Si sumara los tres daría 186.
    expect(screen.getByText('183')).toBeTruthy()
    expect(screen.queryByText('186')).toBeNull()
    expect(screen.getByText(/Total en Chivilcoy/)).toBeTruthy()
  })

  it('mirando «Todas» los muestra a los tres', async () => {
    // El grupo de control: sin este, un filtro que esconde siempre el tercer
    // depósito pasaría los dos tests de arriba.
    await montarEn(null)

    expect(screen.getByRole('cell', { name: /Central Mercedes/ })).toBeTruthy()
    expect(screen.getByText('186')).toBeTruthy()
  })

  it('🔴 el destino de una transferencia incluye los depósitos de OTRA sucursal', async () => {
    await montarEn(1)

    await userEvent.click(screen.getByRole('button', { name: /Transferir/ }))
    const dialogo = await screen.findByRole('dialog')
    await userEvent.click(within(dialogo).getByRole('combobox', { name: /Desde/ }))
    await userEvent.click(await screen.findByRole('option', { name: /Central Chivilcoy/ }))
    await userEvent.click(within(dialogo).getByRole('combobox', { name: /Hacia/ }))

    // Es el punto entero del módulo: mandar mercadería a la otra sucursal.
    expect(await screen.findByRole('option', { name: /Central Mercedes/ })).toBeTruthy()
  })

  it('🔴 avisa que el stock se mueve en el acto al cruzar sucursales', async () => {
    await montarEn(1)

    await userEvent.click(screen.getByRole('button', { name: /Transferir/ }))
    const dialogo = await screen.findByRole('dialog')
    await userEvent.click(within(dialogo).getByRole('combobox', { name: /Desde/ }))
    await userEvent.click(await screen.findByRole('option', { name: /Central Chivilcoy/ }))
    await userEvent.click(within(dialogo).getByRole('combobox', { name: /Hacia/ }))
    await userEvent.click(await screen.findByRole('option', { name: /Central Mercedes/ }))

    // No hay estado "en tránsito": el destino cuenta la mercadería apenas se
    // confirma, aunque físicamente esté viajando. La pantalla tiene que decirlo.
    expect(await screen.findByText(/todavía esté viajando/)).toBeTruthy()
  })

  it('no avisa nada al transferir dentro de la misma sucursal', async () => {
    // El grupo de control del aviso: sin esto, un cartel que se muestra siempre
    // pasaría el test de arriba.
    await montarEn(1)

    await userEvent.click(screen.getByRole('button', { name: /Transferir/ }))
    const dialogo = await screen.findByRole('dialog')
    await userEvent.click(within(dialogo).getByRole('combobox', { name: /Desde/ }))
    await userEvent.click(await screen.findByRole('option', { name: /Central Chivilcoy/ }))
    await userEvent.click(within(dialogo).getByRole('combobox', { name: /Hacia/ }))
    await userEvent.click(await screen.findByRole('option', { name: /Kangoo Norte/ }))

    expect(screen.queryByText(/todavía esté viajando/)).toBeNull()
  })

  it('🔴 el stock por depósito se pide SIN filtrar por sucursal', async () => {
    // El filtrado de la tabla se hace en el cliente justamente para que este
    // pedido traiga los depósitos de todas las sucursales. Si algún día alguien
    // le agrega `sucursal_id` a esta URL, el selector de destino se queda sin
    // las otras sucursales y el defecto no se ve en ninguna pantalla —la tabla
    // sigue mostrando lo mismo—.
    await montarEn(1)

    const deStock = pedidos.filter((u) => /\/consumibles\/\d+\/stock/.test(u))
    expect(deStock.length).toBeGreaterThan(0)
    expect(deStock.every((u) => !u.includes('sucursal_id'))).toBe(true)
  })

  it('🔴 no deja ningún warning en consola', async () => {
    const avisos: string[] = []
    const spies = (['warn', 'error'] as const).map((nivel) =>
      vi.spyOn(console, nivel).mockImplementation((...args: unknown[]) => {
        avisos.push(String(args[0]))
      }),
    )

    await montarEn(1)

    spies.forEach((s) => s.mockRestore())
    expect(avisos).toEqual([])
  })
})
