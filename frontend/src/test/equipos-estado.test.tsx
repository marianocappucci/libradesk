// El estado del equipo con la pastilla de la suite, y el filtro por estado
// (pedido del humano, 2026-10-16).
//
// Dos quejas sobre lo que había: el reporte de Equipamiento pintaba el fondo de
// la celda en vez de usar `BadgeEstado` como el resto de la suite, y la lista
// de Equipos —que sí se clickea y abre la ficha con el historial— sólo
// filtraba por cliente, así que "qué tengo en reparación" había que ir a
// buscarlo al reporte, que no se clickea.
import { fireEvent, render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Equipos } from '../pages/Equipos'
import { ReporteDetalle } from '../pages/ReporteDetalle'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'staff' }, loading: false }),
}))

const render = (ui: ReactElement, ruta: string, patron = '*') =>
  renderRTL(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes><Route path={patron} element={ui} /></Routes>
    </MemoryRouter>,
  )

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

const EQUIPO = {
  id: 7, cliente_id: 1, tipo: 'Impresora', modelo: 'M404', marca: 'HP',
  serial: 'S-7', ubicacion_oficina: null, sector: null, deposito_id: null,
  deposito_nombre: null, estado: 'en_reparacion', fecha_adicion: null,
  proveedor_id: null, proveedor_nombre: null, referencias: [],
  garantia_vence: null, observaciones: null,
}

const VISTA = {
  slug: 'equipamiento', titulo: 'Equipamiento', filtros: [], generado: '2026-10-16T10:00:00',
  cantidad_filas: 1,
  columnas: [{ label: 'Tipo', numerica: false }, { label: 'Estado', numerica: false }],
  grupos: [{
    etiqueta: null,
    filas: [[
      { texto: 'Impresora', marca: null, tono: null },
      { texto: 'En reparación', marca: 'atencion', tono: 'atencion' },
    ]],
  }],
  totales: null,
}

let pedidos: string[] = []

beforeEach(() => {
  pedidos = []
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    pedidos.push(u)
    if (u.includes('/api/reportes/')) return Promise.resolve(json(VISTA))
    if (u.includes('/api/equipos')) return Promise.resolve(json([EQUIPO]))
    return Promise.resolve(json([]))
  }))
})

describe('El estado del equipo va en pastilla', () => {
  it('en la lista, "En reparación" lleva el tono de atención y no el neutro de la baja', async () => {
    render(<Equipos />, '/equipos')
    const fila = (await screen.findByText('M404')).closest('tr')!

    expect(within(fila).getByText('En reparación')).toHaveAttribute('data-tono', 'atencion')
  })

  it('en el reporte, el estado es una pastilla y la celda no lleva fondo', async () => {
    render(<ReporteDetalle />, '/reportes/equipamiento', '/reportes/:slug')
    const pastilla = await screen.findByText('En reparación')

    expect(pastilla).toHaveAttribute('data-tono', 'atencion')
    expect(pastilla.closest('td')!.className).not.toMatch(/bg-orange/)
  })
})

describe('La lista de equipos filtra por estado', () => {
  it('le pide al backend sólo los del estado elegido', async () => {
    render(<Equipos />, '/equipos')
    await screen.findByText('M404')

    fireEvent.click(screen.getByRole('combobox', { name: 'Filtrar por estado' }))
    fireEvent.click(await screen.findByRole('option', { name: 'En reparación' }))

    await waitFor(() => expect(pedidos).toContain('/api/equipos?estado=en_reparacion'))
    expect(screen.getByRole('button', { name: 'Limpiar filtros' })).toBeInTheDocument()
  })
})
