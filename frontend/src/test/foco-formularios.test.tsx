// Escribir una palabra entera en un formulario, sin volver a hacer foco.
//
// Reportado por el usuario cargando el valor hora en la demo (2026-08-14):
//
// > "en nombre me escribió de a una letra, tenía que escribir una, volver a
// >  hacer foco con el mouse, escribir otra letra y así sucesivamente"
//
// ## Qué lo causa
//
// Un componente declarado **adentro** de otro se vuelve a crear en cada render.
// React compara los tipos por identidad, así que una función nueva es un tipo
// nuevo: en vez de actualizar el subárbol lo **desmonta y lo vuelve a montar**.
// El `<input>` pasa a ser otro nodo del DOM, el que tenía el foco queda
// desprendido, y la tecla siguiente se pierde en el aire.
//
// Pasaba en tres pantallas con el mismo patrón: el alta de servicios, el
// renombrado de tipos de incidencia y el ABM de proveedores.
//
// ## Por qué estos tests tipean letra por letra
//
// 🔴 **`escribirEn` no sirve para esto, y lo dice su propio docstring**: dispara
// un solo `change` con el valor entero, así que un campo que pierde el foco
// entre tecla y tecla lo pasaría igual. Acá el hecho a probar **es** la
// secuencia de teclas, y eso es `userEvent.type`.
import { render as renderRTL, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ConfiguracionCategorias, ConfiguracionServicios } from '../pages/Configuracion'
import { Proveedores } from '../pages/Proveedores'

// Admin: el alta de servicios está detrás del rol, y sin esto el botón no se
// renderiza y el test no probaría nada.
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'admin' }, loading: false }),
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

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    if ((opciones?.method ?? 'GET') !== 'GET') return Promise.resolve(json({ ok: true }))
    if (u.includes('/api/servicios/alicuotas')) return Promise.resolve(json([0, 0.105, 0.21, 0.27]))
    if (u.includes('/api/servicios')) return Promise.resolve(json([]))
    if (u.includes('/api/categorias')) {
      return Promise.resolve(json([
        { id: 1, nombre: 'Hardware', parent_id: null, ruta: 'Hardware', activo: true },
      ]))
    }
    if (u.includes('/api/proveedores')) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  }))
})

describe('🔴 se puede escribir una palabra entera de un tirón', () => {
  it('el nombre de un servicio nuevo', async () => {
    render(<ConfiguracionServicios />, '/configuracion/servicios')

    await userEvent.click(await screen.findByRole('button', { name: /Agregar servicio/i }))
    const nombre = await screen.findByLabelText('Nombre')
    await userEvent.type(nombre, 'Hora tecnica')

    // Con el defecto acá quedaba 'H': las once teclas siguientes iban a un nodo
    // que React ya había tirado.
    expect(nombre).toHaveValue('Hora tecnica')
    // Y el foco sigue donde el usuario lo dejó. Sin esto habría que volver a
    // clickear por cada letra, que es exactamente lo que se reportó.
    expect(nombre).toHaveFocus()
  })

  it('la descripción del mismo formulario', async () => {
    // El segundo campo del mismo form: si el arreglo fuera un `autoFocus` puesto
    // en el nombre en vez de la causa real, este test seguiría rojo.
    render(<ConfiguracionServicios />, '/configuracion/servicios')

    await userEvent.click(await screen.findByRole('button', { name: /Agregar servicio/i }))
    const desc = await screen.findByLabelText(/Descripción para el comprobante/i)
    await userEvent.type(desc, 'Hora de servicio tecnico')

    expect(desc).toHaveValue('Hora de servicio tecnico')
    expect(desc).toHaveFocus()
  })

  it('renombrar un tipo de incidencia', async () => {
    render(<ConfiguracionCategorias />, '/configuracion/categorias')
    await screen.findByText('Hardware')

    await userEvent.click(screen.getByRole('button', { name: 'Renombrar Hardware' }))
    const campo = await screen.findByLabelText('Nuevo nombre para Hardware')
    await userEvent.clear(campo)
    await userEvent.type(campo, 'Redes')

    expect(campo).toHaveValue('Redes')
    expect(campo).toHaveFocus()
  })

  it('el nombre de un proveedor nuevo', async () => {
    // Tercera pantalla con el mismo patrón. Se arregla el patrón y no la
    // instancia: la vez pasada se corrigió una sola y las otras dos volvieron
    // nueve días después.
    render(<Proveedores />, '/proveedores')

    await userEvent.click(await screen.findByRole('button', { name: /Nuevo proveedor/i }))
    const nombre = await screen.findByLabelText('Nombre del proveedor')
    await userEvent.type(nombre, 'Compu Service')

    expect(nombre).toHaveValue('Compu Service')
    expect(nombre).toHaveFocus()
  })
})
