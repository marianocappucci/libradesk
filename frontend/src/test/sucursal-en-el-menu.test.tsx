// El selector de sucursal, en el menú del usuario (2026-08-14).
//
// Era una franja arriba del contenido, en las 40 pantallas. Pedido del humano:
// llevarlo al nombre del usuario, junto con "cambiar contraseña".
//
// Lo que hay que sostener acá:
//
// 1. Que **ya no esté suelto en la pantalla**. Si quedara dibujado afuera, el
//    pedido no estaría hecho aunque además apareciera en el menú.
// 2. Que **elegir siga funcionando** — el riesgo real de moverlo adentro de un
//    `DropdownMenu` de Radix es que el desplegable del `<Select>` cierre el menú
//    que lo contiene y no se pueda elegir nada.
// 3. Que **la elección persista**, que es lo que le da sentido: la sucursal
//    activa es del puesto de trabajo, no de la sesión.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Layout } from '../components/Layout'
import { AuthProvider } from '../context/AuthContext'
import { SucursalProvider } from '../components/sucursal'

const SUCURSALES = [
  { id: 1, nombre: 'Chivilcoy', codigo: 'CHI', direccion: 'Av.1' },
  { id: 2, nombre: 'Mercedes', codigo: 'MER', direccion: 'Av. 2' },
]

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

// El `AuthProvider` de verdad y no un mock de `useAuth`: el `Layout` lee la
// sesión del `useAuth` de **libra-ui**, no del re-export del producto, así que
// mockear `../context/AuthContext` no lo alcanza — el primer intento fallaba con
// "useAuth debe usarse dentro de AuthProvider". Con el provider real, además, el
// test ejercita el cableado que corre en producción.
const USUARIO = {
  id: '1', username: 'ana', name: 'Ana Perez', nombre: 'Ana Perez',
  role: 'admin', active: true, modulos: [], empresa_nombre: 'Lagrace',
}

function responder(url: string) {
  const u = String(url)
  if (u.includes('/auth/me')) return json(USUARIO)
  if (u.includes('/api/sucursales')) return json(SUCURSALES)
  return json([])
}

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(responder(url))))
})

function montar() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <SucursalProvider>
          <Layout><p>contenido</p></Layout>
        </SucursalProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

const abrirMenu = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(await screen.findByRole('button', { name: /Ana Perez/ }))
}

describe('el selector de sucursal vive en el menú del usuario', () => {
  it('🔴 no está suelto en la pantalla: hay que abrir el menú', async () => {
    // La primera mitad es la que dice que el pedido está hecho; la segunda, que
    // no se perdió en el camino.
    const user = userEvent.setup()
    montar()
    await screen.findByText('LibraDesk')
    expect(screen.queryByLabelText('Sucursal activa')).not.toBeInTheDocument()

    await abrirMenu(user)
    expect(await screen.findByLabelText('Sucursal activa')).toBeInTheDocument()
  })

  it('el nombre de la empresa sí queda a la vista, sin abrir nada', async () => {
    // Va en el encabezado del sidebar, no en el menú: es de la instancia y se
    // mira de reojo para saber en qué instalación estás.
    montar()
    expect(await screen.findByText('Lagrace')).toBeInTheDocument()
  })

  it('🔴 elegir una sucursal adentro del menú funciona y persiste', async () => {
    // El riesgo de meter un `<Select>` adentro de un `DropdownMenu`: que el
    // desplegable cierre el menú que lo contiene y no se pueda elegir nada.
    // Acá se mide el efecto —que la elección quede guardada—, no que el menú
    // siga abierto.
    const user = userEvent.setup()
    montar()
    await abrirMenu(user)

    // El `Select` de shadcn es Radix: un botón (`combobox`) que abre una lista
    // en un portal, no un `<select>` nativo — `selectOptions` no lo maneja.
    // Mismo camino que los demás tests del producto.
    await user.click(await screen.findByRole('combobox', { name: 'Sucursal activa' }))
    await user.click(await screen.findByRole('option', { name: /Mercedes/ }))

    await waitFor(() => {
      expect(localStorage.getItem('libradesk.sucursal_activa')).toBe('2')
    })
  })

  it('con una sola sucursal el selector no se dibuja', async () => {
    // Con una no ofrece nada; con cero no hay concepto. El menú tiene que
    // seguir abriendo igual — es donde además se cambia la contraseña.
    vi.stubGlobal('fetch', vi.fn((url: string) =>
      Promise.resolve(String(url).includes('/api/sucursales')
        ? json([SUCURSALES[0]])
        : responder(url)),
    ))
    const user = userEvent.setup()
    montar()
    await abrirMenu(user)

    expect(await screen.findByText('Cambiar contraseña')).toBeInTheDocument()
    expect(screen.queryByLabelText('Sucursal activa')).not.toBeInTheDocument()
  })
})
