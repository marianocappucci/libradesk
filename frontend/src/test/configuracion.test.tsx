// Configuración en pestañas (pedido 36, 2026-08-04).
//
// Antes las secciones eran tarjetas apiladas en una pantalla larga. Lo que
// estos tests afirman:
//
// 1. **Cada pestaña muestra lo suyo y nada más.** Es el punto del pedido: si
//    todas siguieran renderizándose juntas, el conmutador sería decorativo.
// 2. **Cada pestaña es una ruta**, y la activa se marca con `aria-current`. Sin
//    eso habría que afirmar sobre clases de Tailwind, y un lector de pantalla
//    no distinguiría en cuál está.
// 3. **El conmutador es el mismo que el de depósitos**, que es lo que pidió el
//    usuario — se verifica que las dos pantallas rindan la misma estructura.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
// Proveedores dejó de ser pestaña y se mudó a `proveedores.test.tsx` junto con
// la pantalla (2026-08-13).
import { Configuracion, ConfiguracionCategorias } from '../pages/Configuracion'
import { Depositos } from '../pages/Depositos'
import { escribirEn } from './escribir'

// `useAuth` viene del contexto; las pestañas sólo lo usan para saber si es
// admin, y acá alcanza con que no sea.
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'staff' }, loading: false }),
}))

const render = (ui: ReactElement, ruta: string) =>
  renderRTL(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes><Route path="*" element={ui} /></Routes>
    </MemoryRouter>,
  )

const CONFIG = {
  empresa_nombre: 'Compulibra', empresa_direccion: 'Suipacha 123',
  empresa_cuit: '20-12345678-9', empresa_telefono: '', empresa_email: '',
  empresa_iibb: '', empresa_iva_condition: 'Monotributista',
  empresa_inicio_actividades: '',
}

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
    if (u.includes('/api/config/empresa')) return Promise.resolve(json(CONFIG))
    if (u.includes('/api/categorias')) {
      return Promise.resolve(json([
        { id: 1, nombre: 'Hardware', parent_id: null, ruta: 'Hardware', activo: true },
      ]))
    }
    if (u.includes('/api/proveedores')) {
      return Promise.resolve(json([
        {
          id: 1, nombre: 'Compu Service', contacto: null, telefono: null,
          email: null, observaciones: null, activo: true,
        },
      ]))
    }
    if (u.includes('/api/depositos')) return Promise.resolve(json([]))
    if (u.includes('/api/clientes')) return Promise.resolve(json([]))
    return Promise.resolve(json([]))
  }))
})

const pestania = (nombre: string | RegExp) =>
  screen.getByRole('link', { name: nombre })

describe('Configuración en pestañas', () => {
  it('las pestañas están, y apuntan a rutas propias', async () => {
    render(<Configuracion />, '/configuracion')
    await screen.findByText('Datos de la empresa')

    expect(pestania('Empresa')).toHaveAttribute('href', '/configuracion')
    expect(pestania(/Tipos de incidencia/)).toHaveAttribute('href', '/configuracion/categorias')
    expect(pestania('Facturación')).toHaveAttribute('href', '/configuracion/facturacion')
    // Proveedores ya no está acá: tiene pantalla propia bajo Compras. Se afirma
    // porque mientras fue pestaña, el ítem del menú comercial apuntaba a esta
    // ruta y entrar por Compras se veía igual que entrar por Configuración.
    expect(screen.queryByRole('link', { name: 'Proveedores' })).not.toBeInTheDocument()
  })

  it('🔴 cada pestaña muestra lo suyo y NADA de las otras', async () => {
    // El punto del pedido. Si todas siguieran renderizándose juntas, el
    // conmutador sería decorativo y la pantalla seguiría siendo igual de larga.
    render(<Configuracion />, '/configuracion')
    await screen.findByText('Datos de la empresa')
    expect(screen.queryByText('Tipos de incidencia', { selector: 'div' })).not.toBeInTheDocument()
  })

  it('la pestaña de tipos de incidencia muestra sólo el catálogo', async () => {
    render(<ConfiguracionCategorias />, '/configuracion/categorias')
    await screen.findByText('Hardware')
    expect(screen.queryByText('Datos de la empresa')).not.toBeInTheDocument()
  })

  it('la pestaña activa se marca con aria-current, no sólo con color', async () => {
    render(<ConfiguracionCategorias />, '/configuracion/categorias')
    await screen.findByText('Hardware')

    expect(pestania(/Tipos de incidencia/)).toHaveAttribute('aria-current', 'page')
    expect(pestania('Empresa')).not.toHaveAttribute('aria-current')
  })
})

// El usuario reportó (2026-08-04) que en Configuración no se podía agregar,
// editar ni eliminar proveedores ni tipos de incidencia. La causa: los botones
// estaban detrás de `esAdmin`, pero `app/main.py` monta los dos routers con
// `staff_or_admin` — cualquier staff ya podía hacerlo por la API. Esconderlos no
// restringía nada, sólo hacía que las dos pestañas se vieran rotas.
//
// El mock de `useAuth` de arriba devuelve `role: 'staff'` a propósito: estos
// tests corren como el usuario que reportó el problema.
describe('🔴 el ABM de los catálogos está disponible sin ser admin', () => {
  it('tipos de incidencia: crear, renombrar, eliminar y agregar subcategoría', async () => {
    render(<ConfiguracionCategorias />, '/configuracion/categorias')
    await screen.findByText('Hardware')

    expect(screen.getByRole('button', { name: /Nueva categoría/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Subcategoría/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Renombrar Hardware' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Eliminar Hardware' })).toBeInTheDocument()
  })

  it('tipos de incidencia: la subcategoría se manda con su parent_id', async () => {
    // Que el botón exista no alcanza — lo que el usuario pidió es poder crear
    // subcategorías, y eso es el `parent_id` viajando en el POST.
    const user = userEvent.setup()
    render(<ConfiguracionCategorias />, '/configuracion/categorias')
    await screen.findByText('Hardware')

    await user.click(screen.getByRole('button', { name: /Subcategoría/ }))
    await escribirEn(screen.getByLabelText('Nombre de la categoría'), 'Impresoras')
    await user.click(screen.getByRole('button', { name: 'Agregar' }))

    await waitFor(() => {
      const alta = pedidos.find((p) => p.metodo === 'POST')
      expect(alta?.cuerpo).toEqual({ nombre: 'Impresoras', parent_id: 1 })
    })
  })

  // Los dos casos de proveedores viven ahora en `proveedores.test.tsx`, con la
  // pantalla.

  it('los datos de la empresa SÍ siguen siendo admin-only', async () => {
    // No es el mismo caso: el PUT de `/api/config/empresa` lleva
    // `Depends(require_admin)` de verdad, así que ahí mostrar el botón sería
    // ofrecer un 403.
    render(<Configuracion />, '/configuracion')
    await screen.findByText('Datos de la empresa')

    expect(screen.queryByRole('button', { name: 'Guardar' })).not.toBeInTheDocument()
    expect(screen.getByText(/Solo un administrador puede modificar/)).toBeInTheDocument()
  })
})

describe('El conmutador es el mismo que el de depósitos', () => {
  it('las dos pantallas rinden la misma estructura de pestañas', async () => {
    // El usuario pidió que las pestañas de Configuración se vieran como las de
    // depósitos. Se comparte el componente en vez de copiarlo, y esto lo fija:
    // si alguien duplicara el control, las dos estructuras divergirían.
    // **Un solo `parentElement`**: `asChild` colapsa el `<Button>` dentro del
    // `<Link>`, así que el padre directo del link YA es el conmutador. Con dos
    // niveles se comparaba el contenedor externo de la pantalla —que es
    // `grid gap-4` en las dos— y el test pasaba por el motivo equivocado:
    // seguía en verde aunque se duplicara el control.
    const { unmount } = render(<Depositos />, '/depositos')
    // Se espera por la pestaña y no por el título: desde el 2026-08-13 las dos
    // pantallas de depósitos se titulan igual ("Depósitos"), así que el título
    // ya no identifica a ésta. Y la pestaña es justo lo que este test mide.
    await screen.findByRole('link', { name: 'De la empresa' })
    const claseDepositos = pestania('De la empresa').parentElement!.className
    expect(claseDepositos).toContain('rounded-md')
    unmount()

    render(<Configuracion />, '/configuracion')
    await screen.findByText('Datos de la empresa')
    const cfg = pestania('Empresa').parentElement!

    expect(cfg.className).toBe(claseDepositos)
    // Y las dos marcan la activa igual.
    expect(within(cfg).getByRole('link', { name: 'Empresa' }))
      .toHaveAttribute('aria-current', 'page')
  })
})
