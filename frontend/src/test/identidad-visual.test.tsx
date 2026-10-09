// La identidad de LibraDesk en las dos pantallas que la muestran: la marca (el
// icono sobre un cuadrado de su color, libra-ui ADR-033) y el nombre en
// Montserrat Bold #2d2d2d. Pedido del humano el 2026-08-16 (el nombre) y el
// 2026-10-07 (la marca plana en lugar del logo ilustrado).
//
// El MECANISMO (que `producto` reemplace al box de la inicial, que `cn` mergee las
// clases) esta cubierto por los tests de libra-ui. Lo de aca es el
// CABLEADO de este producto, que es lo que libra-ui no puede ver: que las dos
// superficies lo pasen, y que lo pasen IGUAL.
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'
import { WORDMARK } from '../branding'

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

function sinSesion() {
  fetchMock.mockImplementation(() => Promise.resolve(json({ detail: 'No autenticado' }, 401)))
}

function conSesion() {
  fetchMock.mockImplementation((url: string) =>
    Promise.resolve(
      String(url).includes('/auth/me')
        ? json({
            id: '1', username: 'ana', name: 'Ana', nombre: 'Ana', role: 'admin',
            active: true, modulos: [], empresa_nombre: 'Prueba', mp_pending_count: 0,
          })
        : json([]),
    ),
  )
}

function montar(ruta: string) {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <AuthProvider><App /></AuthProvider>
    </MemoryRouter>,
  )
}

/** La marca del encabezado. En el login es la unica con rol `img`; en el shell autenticado también. */
function marcaDelEncabezado() {
  return screen.getByRole('img', { name: 'LibraDesk' })
}

/** El color de marca de LibraDesk en `libra-ui/identidad`. Desde libra-ui v0.124.0 (ADR-034) la marca es un SVG propio: el color es el `fill` del
 *  primer `<rect>` (el cuadrado de fondo), ya no un `style` del contenedor. */
function esLaMarcaDeLibraDesk(marca: HTMLElement) {
  // No es una <img> con un asset: es un SVG incrustado, con el cuadrado de su color y el dibujo propio encima.
  expect(marca.tagName).toBe('DIV')
  expect(marca).not.toHaveAttribute('src')
  expect(marca.querySelector('svg')).not.toBeNull()
  expect(marca.querySelector('svg > rect')!.getAttribute('fill')).toBe('#4f46e5')
}

describe('el login', () => {
  it('🔴 muestra la marca del producto en lugar de la inicial', async () => {
    sinSesion()
    montar('/login')
    await waitFor(() => expect(screen.getByLabelText('Usuario')).toBeInTheDocument())
    esLaMarcaDeLibraDesk(marcaDelEncabezado())
    // La contracara: si `producto` no se hubiera pasado, libra-ui pintaria la "L".
    expect(screen.queryByText('L')).not.toBeInTheDocument()
  })

  it('🔴 el nombre va en Montserrat Bold #2d2d2d, a 22 px', async () => {
    sinSesion()
    montar('/login')
    await waitFor(() => expect(screen.getByLabelText('Usuario')).toBeInTheDocument())
    const nombre = screen.getByText('LibraDesk')
    for (const clase of WORDMARK.split(' ')) expect(nombre.className).toContain(clase)
    expect(nombre.className).toContain('text-[22px]')
    // El default de libra-ui tiene que haber PERDIDO el merge: si sobreviviera,
    // el tamano lo decidiria el orden en que Tailwind emite las reglas.
    expect(nombre.className).not.toContain('text-xl')
  })

  it('la marca mide 48 px', async () => {
    sinSesion()
    montar('/login')
    await waitFor(() => expect(screen.getByLabelText('Usuario')).toBeInTheDocument())
    // `Login` la dibuja a `h-12 w-12` (libra-ui v0.124.0: antes `h-10`); el default del cuadrado (32 px) tiene que haber PERDIDO el merge.
    expect(marcaDelEncabezado().className).toContain('h-12')
    expect(marcaDelEncabezado().className).not.toContain('h-8')
  })
})

describe('la sidebar', () => {
  it('🔴 muestra la marca y el nombre con las mismas clases de marca', async () => {
    // `/reclamos` y no `/dashboard`: el Dashboard se sacó del producto
    // (2026-09-16). Cualquier pantalla protegida real sirve para este test,
    // que mide el shell autenticado y no la pantalla en sí.
    conSesion()
    montar('/reclamos')
    await waitFor(() => expect(screen.getByText('Prueba')).toBeInTheDocument())
    esLaMarcaDeLibraDesk(marcaDelEncabezado())
    const nombre = screen.getByText('LibraDesk')
    // Tipografía de marca sí; el color no: en la barra grafito (libra-ui ADR-043) el kit reemplaza el `text-[#2d2d2d]` del login por el
    // texto de la barra, que es el único que se lee ahí.
    for (const clase of WORDMARK.split(' ').filter((c) => !c.startsWith('text-[#') && !c.startsWith('dark:text-'))) expect(nombre.className).toContain(clase)
    expect(nombre.className).toContain('text-sidebar-foreground')
    expect(nombre.className).not.toContain('text-[#2d2d2d]')
    expect(nombre.className).toContain('text-[15px]')
  })

  it('🔴 la marca mide 32 px, que es lo que cabe cuando la sidebar se colapsa', async () => {
    // Con la sidebar en modo icono el ancho util son 32 px. `MarcaProducto` ya viene con `h-8 w-8 shrink-0`, asi que no hace falta ningun
    // override de colapsado (el logo de 36 px si lo necesitaba). No se puede medir renderizando: jsdom no aplica Tailwind.
    conSesion()
    montar('/reclamos')
    await waitFor(() => expect(screen.getByText('Prueba')).toBeInTheDocument())
    const clases = marcaDelEncabezado().className
    expect(clases).toContain('h-8')
    expect(clases).toContain('w-8')
    expect(clases).toContain('shrink-0')
  })
})

// 🔴 Los fuentes se leen con `fs`, como DATOS, por la misma razon que
// `encabezado-de-pantalla.test.ts`: con `import.meta.glob` cada archivo entra
// al grafo de modulos y su cobertura salta a 100 % sin un solo test nuevo.
describe('el color de marca se define una sola vez', () => {
  const COLOR = '#2d2d2d'

  function fuentes(dir: string): string[] {
    return readdirSync(join(process.cwd(), dir), { withFileTypes: true }).flatMap((e) =>
      e.isDirectory()
        ? fuentes(join(dir, e.name))
        : /\.tsx?$/.test(e.name) ? [join(dir, e.name)] : [],
    )
  }

  it('🔴 ningun archivo fuera de branding.ts escribe el color a mano', () => {
    // Las dos pantallas se ven por separado, asi que una tercera que copie el
    // color y despues diverja no la reporta nadie. Este es el unico chequeo que
    // mira TODO el arbol y no solo lo que algun test monta.
    const culpables = fuentes('src')
      .filter((f) => !f.endsWith('branding.ts') && !f.includes('/test/'))
      .filter((f) => readFileSync(join(process.cwd(), f), 'utf8').includes(COLOR))
    expect(culpables).toEqual([])
  })

  it('el control — branding.ts si lo tiene, y el lector ve los archivos', () => {
    // Sin esto, el caso de arriba pasaria en verde si `fuentes()` devolviera
    // una lista vacia o si el color hubiera cambiado y nadie lo notara.
    const todos = fuentes('src')
    expect(todos.length).toBeGreaterThan(50)
    expect(readFileSync(join(process.cwd(), 'src/branding.ts'), 'utf8')).toContain(COLOR)
  })
})
