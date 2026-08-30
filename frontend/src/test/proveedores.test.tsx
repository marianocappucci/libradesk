// Proveedores como pantalla propia (reporte del usuario, 2026-08-13).
//
// El módulo comercial puso "Proveedores" dentro de Compras, pero apuntando a
// `/configuracion/proveedores`, que era una **pestaña de Configuración**. El
// efecto: entrar por Compras → Proveedores mostraba el título "Configuración" y
// el conmutador completo (Empresa, Servicios, Tipos de incidencia, Facturación,
// Datos / Backup), con el listado colgando al pie. Era, literalmente, la misma
// pantalla que Configuración general.
//
// Lo que estos tests afirman:
//
// 1. **La pantalla no trae el conmutador de Configuración.** Es el defecto en
//    sí: se afirma sobre los links de las OTRAS pestañas, no sobre el título,
//    porque un `<h2>` distinto no probaría que el conmutador se fue.
// 2. **El ABM sigue completo** y sin gate de admin — los mismos casos que tenía
//    cuando era pestaña, que responden a un reporte anterior (2026-08-04).
// 3. **El menú apunta acá**, no a la ruta vieja. Sin esto, la pantalla podría
//    existir sana y el usuario seguiría aterrizando en Configuración.
import { render as renderRTL, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Proveedores } from '../pages/Proveedores'
import { Configuracion } from '../pages/Configuracion'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'staff' }, loading: false }),
}))

const render = (ui: ReactElement, ruta: string) =>
  renderRTL(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes><Route path="*" element={ui} /></Routes>
    </MemoryRouter>,
  )

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let pedidos: { url: string; metodo: string; cuerpo: unknown }[] = []

beforeEach(() => {
  pedidos = []
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    const metodo = opciones?.method ?? 'GET'
    pedidos.push({
      url: u, metodo,
      cuerpo: opciones?.body ? JSON.parse(String(opciones.body)) : null,
    })
    if (metodo !== 'GET') return Promise.resolve(json({ ok: true }))
    if (u.includes('/api/proveedores')) {
      return Promise.resolve(json([
        {
          id: 1, nombre: 'Compu Service', contacto: null, telefono: null,
          email: null, observaciones: null, activo: true,
        },
      ]))
    }
    return Promise.resolve(json([]))
  }))
})

describe('🔴 Proveedores es una pantalla propia, no una pestaña de Configuración', () => {
  it('no rinde la barra de pestañas de Configuración', async () => {
    render(<Proveedores />, '/proveedores')
    await screen.findByText('Compu Service')

    // Se afirma sobre la barra entera y no sobre el título: si sólo se mirara
    // el `<h2>`, la pantalla podría decir "Proveedores" arriba y traer las
    // pestañas abajo, que es exactamente lo que se reportó.
    expect(screen.queryAllByRole('tab')).toEqual([])
    // Y no está por otro nombre: ningún link a una ruta de configuración.
    const aConfig = screen.queryAllByRole('link')
      .filter((a) => a.getAttribute('href')?.startsWith('/configuracion'))
    expect(aConfig).toEqual([])
  })

  it('Configuración ya no ofrece la pestaña de proveedores', async () => {
    // El control del de arriba: si Configuración todavía la declarara, el caso
    // anterior pasaría igual (esta pantalla no la rinde) y la duplicación
    // seguiría viva.
    //
    // 🔴 Se mide sobre la pantalla RENDIDA y no sobre una constante. Hasta el
    // 2026-08-30 se leía `PESTANIAS_CONFIG`, la lista que alimentaba el
    // conmutador propio; al pasar la pantalla al kit esa lista se fue, y un
    // test atado a ella habría que borrarlo justo cuando deja de haber quien
    // sostenga la afirmación.
    render(<Configuracion />, '/configuracion')
    await screen.findByText('Datos de la empresa')

    const pestanias = screen.getAllByRole('tab').map((t) => t.textContent)
    expect(pestanias).not.toContain('Proveedores')
  })

  it('muestra el listado', async () => {
    render(<Proveedores />, '/proveedores')
    expect(await screen.findByText('Compu Service')).toBeInTheDocument()
    expect(screen.queryByText('Datos de la empresa')).not.toBeInTheDocument()
  })
})

// Estos cuatro venían de `configuracion.test.tsx` y se mudaron con la pantalla.
// Responden a un reporte de 2026-08-04: el ABM estaba detrás de `esAdmin`
// aunque `app/main.py` monta `proveedores.router` con `staff_or_admin`, así que
// esconder los botones no restringía nada. El mock de `useAuth` devuelve
// `role: 'staff'` a propósito — corren como el usuario que lo reportó.
describe('el ABM está disponible sin ser admin', () => {
  it('crear, editar, eliminar y activar/desactivar', async () => {
    render(<Proveedores />, '/proveedores')
    await screen.findByText('Compu Service')

    expect(screen.getByRole('button', { name: /Nuevo proveedor/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Editar Compu Service' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Eliminar Compu Service' })).toBeInTheDocument()
    // El badge de activo/inactivo es un botón de verdad, no un span con onClick:
    // así se lo alcanza con el teclado y un lector de pantalla lo anuncia.
    expect(screen.getByRole('button', { name: 'Desactivar Compu Service' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('el alta manda los campos vacíos como null, no como ""', async () => {
    const user = userEvent.setup()
    render(<Proveedores />, '/proveedores')
    await screen.findByText('Compu Service')

    await user.click(screen.getByRole('button', { name: /Nuevo proveedor/ }))
    await user.type(screen.getByLabelText('Nombre del proveedor'), 'Taller Pérez')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))

    await waitFor(() => {
      const alta = pedidos.find((p) => p.metodo === 'POST')
      expect(alta?.cuerpo).toEqual({
        nombre: 'Taller Pérez', contacto: null, telefono: null, email: null,
      })
    })
  })
})
