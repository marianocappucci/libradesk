// Configuración en pestañas (pedido 36, 2026-08-04).
//
// Antes las tres secciones —datos de la empresa, tipos de incidencia y
// proveedores— eran tres tarjetas apiladas en una pantalla larga. Lo que estos
// tests afirman:
//
// 1. **Cada pestaña muestra lo suyo y nada más.** Es el punto del pedido: si
//    las tres siguieran renderizándose juntas, el conmutador sería decorativo.
// 2. **Cada pestaña es una ruta**, y la activa se marca con `aria-current`. Sin
//    eso habría que afirmar sobre clases de Tailwind, y un lector de pantalla
//    no distinguiría en cuál está.
// 3. **El conmutador es el mismo que el de depósitos**, que es lo que pidió el
//    usuario — se verifica que las dos pantallas rindan la misma estructura.
import { render as renderRTL, screen, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  Configuracion, ConfiguracionCategorias, ConfiguracionProveedores,
} from '../pages/Configuracion'
import { Depositos } from '../pages/Depositos'

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

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/api/config-empresa')) return Promise.resolve(json(CONFIG))
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
  it('las tres pestañas están, y apuntan a rutas propias', async () => {
    render(<Configuracion />, '/configuracion')
    await screen.findByText('Datos de la empresa')

    expect(pestania('Empresa')).toHaveAttribute('href', '/configuracion')
    expect(pestania(/Tipos de incidencia/)).toHaveAttribute('href', '/configuracion/categorias')
    expect(pestania('Proveedores')).toHaveAttribute('href', '/configuracion/proveedores')
  })

  it('🔴 cada pestaña muestra lo suyo y NADA de las otras', async () => {
    // El punto del pedido. Si las tres siguieran renderizándose juntas, el
    // conmutador sería decorativo y la pantalla seguiría siendo igual de larga.
    render(<Configuracion />, '/configuracion')
    await screen.findByText('Datos de la empresa')
    expect(screen.queryByText('Tipos de incidencia', { selector: 'div' })).not.toBeInTheDocument()
    expect(screen.queryByText('Proveedores de reparación')).not.toBeInTheDocument()
  })

  it('la pestaña de tipos de incidencia muestra sólo el catálogo', async () => {
    render(<ConfiguracionCategorias />, '/configuracion/categorias')
    await screen.findByText('Hardware')
    expect(screen.queryByText('Datos de la empresa')).not.toBeInTheDocument()
    expect(screen.queryByText('Proveedores de reparación')).not.toBeInTheDocument()
  })

  it('la pestaña de proveedores muestra sólo los proveedores', async () => {
    render(<ConfiguracionProveedores />, '/configuracion/proveedores')
    await screen.findByText('Compu Service')
    expect(screen.queryByText('Datos de la empresa')).not.toBeInTheDocument()
  })

  it('la pestaña activa se marca con aria-current, no sólo con color', async () => {
    render(<ConfiguracionProveedores />, '/configuracion/proveedores')
    await screen.findByText('Compu Service')

    expect(pestania('Proveedores')).toHaveAttribute('aria-current', 'page')
    expect(pestania('Empresa')).not.toHaveAttribute('aria-current')
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
    await screen.findByText('Depósitos de la empresa')
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
