// El TILE GRIS de los iconos (elegido por el humano el 2026-08-13, sobre la
// hoja comparativa que acompañó la vuelta de Fluent a lucide).
//
// ## Qué se puede probar acá y qué no
//
// jsdom no corre Tailwind: no hay hoja de estilos, así que `getComputedStyle`
// devuelve vacío para `bg-muted` y para la regla del acento. Preguntar por el
// color acá daría verde con el tile entero desarmado, que es peor que no
// preguntar. Lo que sí es real y sí se rompe solo es la ESTRUCTURA: quién
// envuelve a quién, y los atributos de los que cuelgan las reglas CSS.
//
// Por eso cada caso afirma sobre el gancho del que depende el aspecto:
//
//   - `[data-slot="icono-tile"]`  el recuadro, que lo pone `Tile`.
//   - `[data-active="true"]`      lo pone `SidebarMenuButton` de libra-ui, y es
//                                 de donde cuelga el borde `--marca`. Si el
//                                 paquete lo renombra, el ítem activo pierde el
//                                 acento sin que nada se rompa.
//   - `data-variant`/`data-size`  el par del que cuelga el `compoundVariant`
//                                 del `Button` que le da fondo gris al botón de
//                                 acción. Cambiar el `variant` de una pantalla
//                                 le saca el tile en silencio.
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'

const RESUMEN_DASHBOARD = {
  incidencias_por_estado: { abierta: 2, cerrada: 1 },
  incidencias_por_prioridad_abiertas: { alta: 1, media: 1 },
  incidencias_en_rango: 3,
  total_clientes_activos: 4,
  total_equipos: 7,
  horas_totales_invertidas: 12.5,
}

const CLIENTE = {
  id: 1, nombre: 'Clínica del Sol', empresa: null, email: null, telefono: null,
  ciudad: null, cuit: null, condicion_iva: null, domicilio: null,
  observaciones: null, tipo_facturacion: 'por_servicio', activo: true,
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/auth/me')) {
      return Promise.resolve(json({
        id: '1', username: 'ana', name: 'Ana', role: 'admin', active: true,
        nombre: 'Ana', modulos: [], empresa_nombre: 'Prueba', mp_pending_count: 0,
      }))
    }
    if (u.includes('/api/dashboard')) return Promise.resolve(json(RESUMEN_DASHBOARD))
    if (u.includes('/api/clientes/condiciones-iva')) return Promise.resolve(json([]))
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    return Promise.resolve(json([]))
  }))
})

const montar = (ruta: string) =>
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )

const tiles = (raiz: HTMLElement | Document = document) =>
  Array.from(raiz.querySelectorAll('[data-slot="icono-tile"]'))

describe('el tile del sidebar', () => {
  it('lo llevan TODOS los ítems del menú, no algunos', async () => {
    montar('/clientes')
    await screen.findAllByText('LibraDesk')

    const items = Array.from(document.querySelectorAll('[data-sidebar="menu-button"]'))
    expect(items.length).toBeGreaterThan(10)

    // El control que hace que esto valga: se cuentan los ítems SIN tile, no los
    // que tienen. Afirmar "hay tiles" pasaría con un solo ítem envuelto y 29
    // pelados, que es justo el defecto que `conTiles` existe para evitar.
    const pelados = items
      .filter((el) => !el.querySelector('[data-slot="icono-tile"]'))
      .map((el) => el.textContent?.trim())
    expect(pelados).toEqual([])
  })

  it('el ítem de la ruta actual expone el gancho del acento', async () => {
    montar('/clientes')
    await screen.findAllByText('LibraDesk')

    const activo = document.querySelector('[data-sidebar="menu-button"][data-active="true"]')
    expect(activo).not.toBeNull()
    expect(activo?.textContent).toContain('Clientes')
    // El selector de `index.css` baja desde este ancestro hasta el tile: si el
    // tile dejara de estar adentro, la regla no matchea y el ítem activo pierde
    // el borde sin que nada falle en tiempo de compilación.
    expect(activo?.querySelector('[data-slot="icono-tile"]')).not.toBeNull()
  })

  it('un ítem inactivo NO lo expone', async () => {
    // El control del caso de arriba: sin esto, `data-active="true"` podría
    // estar en todos los ítems y el test seguiría verde.
    montar('/clientes')
    await screen.findAllByText('LibraDesk')

    const activos = document.querySelectorAll('[data-sidebar="menu-button"][data-active="true"]')
    expect(activos.length).toBe(1)
  })
})

describe('el tile del título de pantalla', () => {
  it('envuelve al icono del encabezado, y el título sigue siendo un heading', async () => {
    montar('/clientes')
    const titulo = await screen.findByRole('heading', { name: 'Clientes' })

    const tile = titulo.querySelector('[data-slot="icono-tile"]')
    expect(tile).not.toBeNull()
    // El tile envuelve al SVG; no lo reemplaza. Si el script de migración
    // hubiera comido el icono, esto queda vacío y el encabezado pierde su
    // marca de identidad sin que nadie se entere.
    expect(tile?.querySelector('svg')).not.toBeNull()
  })

  it('el diálogo de alta NO lleva tile', async () => {
    // A propósito: el tile marca la identidad de la PANTALLA. Adentro de un
    // diálogo es decoración, y sin este control nada impediría que la próxima
    // pasada los meta en todos lados.
    montar('/clientes')
    await screen.findByRole('heading', { name: 'Clientes' })

    const encabezado = screen.getByRole('heading', { name: 'Clientes' })
    const tilesDelTitulo = tiles(encabezado).length
    expect(tilesDelTitulo).toBe(1)
  })
})

describe('el botón de acción de una fila', () => {
  it('declara el par variant/size del que cuelga su fondo gris', async () => {
    montar('/clientes')
    await screen.findByText('Clínica del Sol')

    const editar = screen.getByRole('button', { name: 'Editar cliente' })
    expect(editar).toHaveAttribute('data-variant', 'outline')
    expect(editar).toHaveAttribute('data-size', 'icon')
  })

  it('el destructivo sigue marcado como tal', async () => {
    // De ese `text-destructive` cuelga la regla que lo pinta con `--marca`.
    montar('/clientes')
    await screen.findByText('Clínica del Sol')

    const desactivar = screen.getByRole('button', { name: 'Desactivar cliente' })
    expect(desactivar.className).toContain('text-destructive')
    expect(desactivar).toHaveAttribute('data-size', 'icon')
  })

  it('el botón primario NO es de icono, así que no le toca el tile', async () => {
    // Control de alcance del `compoundVariant`: sólo los de icono. Si algún día
    // alcanzara al `outline` de tamaño normal, "Cancelar" en los diálogos
    // pasaría a ser un bloque gris.
    montar('/clientes')
    await screen.findByText('Clínica del Sol')

    const alta = screen.getByRole('button', { name: /Nuevo cliente/ })
    expect(alta).not.toHaveAttribute('data-size', 'icon')
  })
})

describe('no quedan iconos del set viejo', () => {
  it('todo lo que dibuja es un <svg> de lucide, sin restos de Fluent', async () => {
    // Los SVG de `fluent-color` traían gradientes con hex horneados
    // (`<linearGradient>`), que es lo único que los distingue del marcado de
    // lucide sin mirar el path. Si vuelve a aparecer uno, es que alguna pantalla
    // se quedó con el import viejo.
    montar('/clientes')
    await waitFor(() => expect(screen.getAllByText('LibraDesk').length).toBeGreaterThan(0))

    expect(document.querySelectorAll('linearGradient, radialGradient')).toHaveLength(0)
    // Y que efectivamente hay iconos dibujados: sin esto el caso de arriba pasa
    // en una pantalla vacía.
    const svgs = document.querySelectorAll('svg')
    expect(svgs.length).toBeGreaterThan(20)
    expect(within(document.body).getAllByText('LibraDesk').length).toBeGreaterThan(0)
  })
})
