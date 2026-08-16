// La identidad de LibraDesk en las dos pantallas que la muestran: el logo y el
// nombre en Montserrat Bold #2d2d2d. Pedido del humano el 2026-08-16.
//
// El MECANISMO (que `logo` reemplace al box de la inicial, que `cn` mergee las
// clases) esta cubierto por los 12 tests de libra-ui v0.23.0. Lo de aca es el
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
        : String(url).includes('/api/dashboard')
          ? json({
              incidencias_por_estado: {}, incidencias_por_prioridad_abiertas: {},
              incidencias_en_rango: 0, total_clientes_activos: 0, total_equipos: 0,
              horas_totales_invertidas: 0,
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

/** El logo del encabezado. En el login es la unica imagen; en el shell autenticado también. */
function logoDelEncabezado() {
  return screen.getByRole('img', { name: 'LibraDesk' })
}

describe('el login', () => {
  it('🔴 muestra el logo en lugar de la inicial', async () => {
    sinSesion()
    montar('/login')
    await waitFor(() => expect(screen.getByLabelText('Usuario')).toBeInTheDocument())
    // El asset lo hashea Vite, asi que se afirma el nombre base y no la ruta
    // entera: fijar el hash haria fallar el test en cada rebuild.
    expect(logoDelEncabezado()).toHaveAttribute('src', expect.stringContaining('logo-libradesk'))
    // La contracara: si el logo no se hubiera pasado, libra-ui pintaria la "L".
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

  it('el logo mide 72 px', async () => {
    sinSesion()
    montar('/login')
    await waitFor(() => expect(screen.getByLabelText('Usuario')).toBeInTheDocument())
    expect(logoDelEncabezado().className).toContain('h-[72px]')
    expect(logoDelEncabezado().className).not.toContain('h-10')
  })
})

describe('la sidebar', () => {
  it('🔴 muestra el logo y el nombre con las mismas clases de marca', async () => {
    conSesion()
    montar('/dashboard')
    await waitFor(() => expect(screen.getByText('Prueba')).toBeInTheDocument())
    expect(logoDelEncabezado()).toHaveAttribute('src', expect.stringContaining('logo-libradesk'))
    const nombre = screen.getByText('LibraDesk')
    for (const clase of WORDMARK.split(' ')) expect(nombre.className).toContain(clase)
    expect(nombre.className).toContain('text-[15px]')
  })

  it('🔴 el logo baja a 32 px cuando la sidebar se colapsa', async () => {
    // Sin este override el logo de 36 px se sale de la barra de iconos, donde
    // el ancho util son 32. No se puede medir renderizando: el estado colapsado
    // lo pone un atributo del provider y jsdom no aplica Tailwind, asi que lo
    // que se afirma es que la regla condicional este declarada.
    conSesion()
    montar('/dashboard')
    await waitFor(() => expect(screen.getByText('Prueba')).toBeInTheDocument())
    const clases = logoDelEncabezado().className
    expect(clases).toContain('h-9')
    expect(clases).toContain('group-data-[collapsible=icon]:h-8')
    expect(clases).toContain('group-data-[collapsible=icon]:w-8')
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
