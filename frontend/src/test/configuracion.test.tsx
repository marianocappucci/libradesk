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
import { render as renderRTL, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
// Proveedores dejó de ser pestaña y se mudó a `proveedores.test.tsx` junto con
// la pantalla (2026-08-13).
import { Configuracion, CategoriasCard } from '../pages/Configuracion'
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

// 🔴 `role="tab"` y no `link`: desde el 2026-08-30 esta pantalla usa el `Tabs`
// de shadcn, a traves de `libra-ui/Configuracion`. Antes era un conmutador
// propio donde cada pestaña era una RUTA, con las clases de `tabs.tsx` copiadas
// a mano: se veia casi igual y era otro mecanismo. Lo que un lector de pantalla
// anuncia cambio con el, y estos tests son lo que lo fija.
const pestania = (nombre: string | RegExp) =>
  screen.getByRole('tab', { name: nombre })

describe('Configuración en pestañas', () => {
  it('las pestañas están, y son las de la familia', async () => {
    render(<Configuracion />, '/configuracion')
    await screen.findByText('Datos de la empresa')

    const nombres = screen.getAllByRole('tab').map((t) => t.textContent)
    expect(nombres).toEqual([
      'Empresa', 'Integraciones', 'Servicios', 'Tipos de incidencia', 'Datos / Backup',
    ])
    // 🔴 "Facturación" ya NO es de primer nivel: este producto no emite
    // comprobantes —manda lo facturable a Contalibra o a SOS Contador—, así que
    // es una INTEGRACIÓN y vive adentro de esa pestaña.
    expect(screen.queryByRole('tab', { name: 'Facturación' })).not.toBeInTheDocument()
    // Proveedores tampoco: tiene pantalla propia bajo Compras. Se afirma porque
    // mientras fue pestaña, el ítem del menú comercial apuntaba a esta ruta y
    // entrar por Compras se veía igual que entrar por Configuración.
    expect(screen.queryByRole('tab', { name: 'Proveedores' })).not.toBeInTheDocument()
  })

  it('🔴 cada pestaña muestra lo suyo y NADA de las otras', async () => {
    // El punto del pedido. Si todas siguieran renderizándose juntas, el
    // conmutador sería decorativo y la pantalla seguiría siendo igual de larga.
    render(<Configuracion />, '/configuracion')
    await screen.findByText('Datos de la empresa')
    expect(screen.queryByText('Tipos de incidencia', { selector: 'div' })).not.toBeInTheDocument()
  })

  it('la pestaña de tipos de incidencia muestra sólo el catálogo', async () => {
    render(<CategoriasCard />, '/configuracion/categorias')
    await screen.findByText('Hardware')
    expect(screen.queryByText('Datos de la empresa')).not.toBeInTheDocument()
  })

  it('la pestaña activa se marca con aria-selected, no sólo con color', async () => {
    // Sin esto habría que afirmar sobre clases de Tailwind, y un lector de
    // pantalla no distinguiría en cuál está. El atributo cambió de
    // `aria-current="page"` a `aria-selected` al pasar de enlaces a pestañas
    // de verdad: es exactamente lo que el rol nuevo anuncia.
    render(<Configuracion />, '/configuracion?seccion=categorias')
    await screen.findByText('Hardware')

    expect(pestania(/Tipos de incidencia/)).toHaveAttribute('aria-selected', 'true')
    expect(pestania('Empresa')).toHaveAttribute('aria-selected', 'false')
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
    render(<CategoriasCard />, '/configuracion/categorias')
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
    render(<CategoriasCard />, '/configuracion/categorias')
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

    // 🔴 Se espera el MENSAJE, no el titulo de la tarjeta. El titulo se rinde
    // enseguida; el formulario recien cuando llega `GET /api/config/empresa`, y
    // hasta entonces la tarjeta dice "Cargando…".
    //
    // Con el `await` sobre el titulo, el `queryByRole('button')` de abajo se
    // cumplia porque el formulario TODAVIA NO EXISTIA --o sea que pasaba igual
    // aunque el boton se le mostrara a un usuario de staff, que es justo lo que
    // este test mide--. Se destapo al migrar la pantalla al kit, que corre el
    // render un tick: el mismo test empezo a fallar sin que cambiara la
    // pantalla.
    expect(await screen.findByText(/Solo un administrador puede modificar/))
      .toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Guardar' })).not.toBeInTheDocument()
  })
})

// El bloque que comparaba esta pantalla con la de depositos se fue el
// 2026-08-30, y no por descuido: existia porque Configuracion IMITABA las
// pestañas de shadcn con las clases copiadas a mano, y habia que sostener que
// las dos copias no divergieran. Ahora Configuracion ES el primitivo --via
// `libra-ui/Configuracion`--, asi que no hay dos copias que comparar.
//
// 🔴 El `Conmutador` NO se fue: lo sigue usando depositos, donde cada pestaña
// es una ruta propia de verdad. Que su aspecto siga siendo el de `tabs.tsx` lo
// sostiene `pestanias-mismo-aspecto.test.ts`, que compara los dos archivos.
