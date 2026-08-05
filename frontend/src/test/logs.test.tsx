// Pantalla de logs (admin-only).
//
// Lo que estos tests afirman, en orden de lo que se rompe sin que se note:
//
// 1. **Los filtros llegan al backend.** El filtrado es del lado del servidor
//    (la tabla está paginada de a 100): un filtro que sólo cambiara el estado
//    local se vería igual en pantalla y devolvería la misma primera página.
// 2. **Cambiar un filtro vuelve a la página 1.** Quedarse en la página 4 de un
//    resultado que ahora tiene 2 muestra una tabla vacía que parece un error.
// 3. **El diff se ve al desplegar.** Es la mitad del valor de la pantalla: sin
//    el antes/después, "editado" no dice qué se editó.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Logs } from '../pages/Logs'

const ACCIONES = {
  crear: { label: 'Creado', color: '#198754' },
  editar: { label: 'Editado', color: '#0d6efd' },
  borrar: { label: 'Borrado', color: '#dc3545' },
}

const RESPUESTA = {
  actividad: [
    {
      id: 3, ts: '2026-08-05 14:32:10', usuario: 'admin', accion: 'editar',
      entidad: 'cliente', entidad_id: 7, descripcion: 'Cliente — Compulibra',
      cambios: { nombre: ['Nombre viejo', 'Nombre nuevo'] },
    },
    {
      id: 2, ts: '2026-08-05 14:30:00', usuario: 'tecnico1', accion: 'borrar',
      entidad: 'equipo', entidad_id: 4, descripcion: 'Equipo — Notebook Dell',
      cambios: null,
    },
  ],
  total: 2,
  total_pages: 1,
  page: 1,
  entidades: ['cliente', 'equipo'],
  acciones: ACCIONES,
  usuarios: ['admin', 'tecnico1'],
  accesos: [
    { id: 9, ts: '2026-08-05 14:29:00', evento: 'login', username: 'admin', ip: '203.0.113.7', detalle: '' },
    { id: 8, ts: '2026-08-05 14:28:00', evento: 'login_fallido', username: 'fantasma', ip: '203.0.113.9', detalle: '' },
  ],
}

let urls: string[] = []

beforeEach(() => {
  urls = []
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    urls.push(String(url))
    return Promise.resolve(new Response(JSON.stringify(RESPUESTA), {
      status: 200, headers: { 'content-type': 'application/json' },
    }))
  }))
})

const render = () => renderRTL(<MemoryRouter><Logs /></MemoryRouter>)

async function esperarCarga() {
  await waitFor(() => expect(screen.getByText('Cliente — Compulibra')).toBeInTheDocument())
}

describe('Logs — actividad', () => {
  it('muestra qué pasó, quién lo hizo y cuándo', async () => {
    render()
    await esperarCarga()
    expect(screen.getByText('Editado')).toBeInTheDocument()
    // `admin` aparece dos veces —en la actividad y en los accesos—, así que
    // `getByText` fallaría por ambigüedad.
    expect(screen.getAllByText('admin').length).toBeGreaterThan(0)
    // `2026-08-05 14:32:10` se muestra como `05/08 14:32`, con la fecha
    // completa en el title.
    expect(screen.getByTitle('2026-08-05 14:32:10')).toHaveTextContent('05/08 14:32')
  })

  it('el antes y el después se ven al desplegar la fila', async () => {
    render()
    await esperarCarga()
    expect(screen.queryByText('Nombre viejo')).not.toBeInTheDocument()

    await userEvent.click(screen.getByText('Cliente — Compulibra'))
    expect(screen.getByText('Nombre viejo')).toBeInTheDocument()
    expect(screen.getByText('Nombre nuevo')).toBeInTheDocument()
  })

  it('una fila sin cambios no despliega nada', async () => {
    // Un borrado no tiene diff: la fila entera es la novedad.
    render()
    await esperarCarga()
    await userEvent.click(screen.getByText('Equipo — Notebook Dell'))
    expect(screen.queryByRole('table', { name: /cambios/i })).not.toBeInTheDocument()
  })
})

describe('Logs — filtros', () => {
  it('el filtro de entidad viaja al backend', async () => {
    render()
    await esperarCarga()
    urls = []

    const user = userEvent.setup()
    await user.click(screen.getByRole('combobox', { name: 'Entidad' }))
    await user.click(await within(await screen.findByRole('listbox')).findByRole('option', { name: 'equipo' }))

    await waitFor(() => expect(urls.some((u) => u.includes('entidad=equipo'))).toBe(true))
  })

  it('el filtro de fecha viaja al backend', async () => {
    render()
    await esperarCarga()
    urls = []

    await userEvent.type(screen.getByLabelText('Desde'), '2026-08-01')

    await waitFor(() => expect(urls.some((u) => u.includes('desde=2026-08-01'))).toBe(true))
  })

  it('cambiar un filtro vuelve a la página 1', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      urls.push(String(url))
      return Promise.resolve(new Response(
        JSON.stringify({ ...RESPUESTA, total: 250, total_pages: 3, page: String(url).includes('page=2') ? 2 : 1 }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ))
    }))
    const user = userEvent.setup()
    render()
    await esperarCarga()

    await user.click(screen.getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => expect(urls.some((u) => u.includes('page=2'))).toBe(true))
    urls = []

    await user.click(screen.getByRole('combobox', { name: 'Usuario' }))
    await user.click(await within(await screen.findByRole('listbox')).findByRole('option', { name: 'tecnico1' }))

    await waitFor(() => expect(urls.some((u) => u.includes('page=1'))).toBe(true))
    expect(urls.every((u) => !u.includes('page=2'))).toBe(true)
  })
})

describe('Logs — accesos', () => {
  it('el intento fallido se distingue del ingreso', async () => {
    render()
    await esperarCarga()
    expect(screen.getByText('Ingreso')).toBeInTheDocument()
    expect(screen.getByText('Intento fallido')).toBeInTheDocument()
    expect(screen.getByText('fantasma')).toBeInTheDocument()
  })

  it('muestra la IP real, que es el dato por el que se mira esta tabla', async () => {
    render()
    await esperarCarga()
    // La tabla de accesos es la segunda: la primera es la de actividad, que no
    // tiene columna de IP.
    const tablaAccesos = screen.getAllByRole('table').at(-1)!
    expect(within(tablaAccesos).getByText('203.0.113.7')).toBeInTheDocument()
  })
})
